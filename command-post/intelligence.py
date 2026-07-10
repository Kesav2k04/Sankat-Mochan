"""
Command-post intelligence — the deterministic services from
docs/INTELLIGENCE-DESIGN.md (C1–C9, C13) at demo scale.

Governing rule: CODE owns orchestration and the source of truth; the LLM
(triage.py) is only consulted for the fuzzy parts (translate/urgency). The
LLM never emits an assignment or drives control flow (C12 structural defense).

Everything is in-memory (a demo doesn't need a DB). Every automated decision
appends a human-readable *why* to the audit log (C13) — that feeds the
dashboard's AI-activity drawer and the judges' explainability story.
"""
from __future__ import annotations

import math
import time
import uuid
from typing import Any

# ---- Tunables (INTELLIGENCE-DESIGN.md) ------------------------------------
CLUSTER_EPS_M = 100.0          # C1: distance threshold (flat fallback)
DEDUP_WINDOW_S = 10 * 60       # C2: same-source merge window
AGING_CAP_BOOST = 0.5          # C3: bounded aging (never lifts out of tier)
AGING_HALF_LIFE_S = 15 * 60    # C3: how fast the in-tier aging boost grows
STUCK_TIMEOUT_S = 10 * 60      # C4: assigned-but-silent → auto re-open
OFFLINE_AFTER_S = 15 * 60      # C4: responder heartbeat timeout
RESPONDER_SPEED_KMH = 12.0     # C5: rough field speed for the approx ETA
OPERATING_BBOX = (75.9, 11.4, 76.4, 11.95)  # C1: lon/lat sanity box (Wayanad)

ACTIVE_STATES = {"new", "triaged", "awaiting responder", "proposed", "assigned", "en route", "on-scene"}


def _now() -> float:
    return time.time()


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


class Store:
    """Single source of truth: reports, incidents, responders, audit log."""

    def __init__(self) -> None:
        self.reports: dict[str, dict[str, Any]] = {}      # report id -> report
        self.incidents: dict[str, dict[str, Any]] = {}    # incident id -> incident
        self.responders: dict[str, dict[str, Any]] = {}
        self.activity: list[dict[str, Any]] = []          # C13 append-only audit log
        self.metrics = {"pkt_rx": 0, "last_rx": None, "resolved": 0,
                        "response_times_s": [], "triage_latencies_ms": []}
        self._seed_responders()

    # ---- C13 audit log ------------------------------------------------
    def log(self, text: str) -> None:
        self.activity.append({"ts": _now(), "text": text})
        if len(self.activity) > 400:
            self.activity[:] = self.activity[-400:]

    # ---- C4 responder registry ----------------------------------------
    def _seed_responders(self) -> None:
        """Pre-registered roster for the demo (also fed by heartbeats later)."""
        base = [
            ("R1", "NDRF ALPHA", "heavy rescue · rope, cutting gear", 11.6800, 76.1330),
            ("R2", "FIRE BRAVO", "swift-water · 6 crew", 11.6905, 76.1255),
            ("R3", "MEDIC CHARLIE", "field medical · O2, stretchers", 11.6832, 76.1402),
            ("R4", "K9 DELTA", "search dogs · debris survey", 11.6752, 76.1288),
        ]
        for rid, callsign, cap, lat, lng in base:
            self.responders[rid] = {
                "id": rid, "callsign": callsign, "capability": cap,
                "lat": lat, "lng": lng, "status": "available",
                "assigned_incident": None, "last_seen": _now(),
            }

    def heartbeat(self, rid: str, lat: float | None = None, lng: float | None = None,
                  status: str | None = None) -> bool:
        r = self.responders.get(rid)
        if not r:
            return False
        r["last_seen"] = _now()
        if lat is not None and lng is not None:
            r["lat"], r["lng"] = lat, lng
        if status in {"available", "on_task"}:
            r["status"] = status
        return True

    def _refresh_responder_staleness(self) -> None:
        for r in self.responders.values():
            if _now() - r["last_seen"] > OFFLINE_AFTER_S and r["status"] != "offline":
                r["status"] = "offline"
                self.log(f"{r['callsign']} marked offline — no heartbeat "
                         f"{int((_now()-r['last_seen'])//60)}m")
                if r["assigned_incident"]:
                    self._reopen(r["assigned_incident"], f"{r['callsign']} went offline")

    # ---- ingest: C2 dedup → C1 cluster → C3 rank -----------------------
    def add_report(self, env: dict[str, Any], ai: dict[str, Any]) -> dict[str, Any] | None:
        """One validated envelope + its AI triage → report → incident. Returns
        the (possibly merged) incident, or None if fully deduped."""
        self.metrics["pkt_rx"] += 1
        self.metrics["last_rx"] = _now()
        if ai.get("latency_ms"):
            self.metrics["triage_latencies_ms"].append(ai["latency_ms"])

        report = {
            "id": env["id"], "origin": env["origin"], "ts": env.get("ts", 0),
            "received_at": _now(), "hops": env.get("hops", 0),
            "lang": env.get("lang", "en"), "gist": env.get("gist", ""),
            "english": ai.get("english") or env.get("gist", ""),
            "urgency": int(ai.get("urgency", env.get("urgency", 3))),
            "category": ai.get("category") or env.get("category") or "other",
            "lat": env.get("lat"), "lng": env.get("lng"),
            "location_hint": env.get("locationHint", ""),
            "confidence": ai.get("confidence"), "ai": bool(ai.get("ai")),
            "latency_ms": ai.get("latency_ms", 0),
            "audio": env.get("audio"),  # set by /voice_sos when audio saved
            "rationale": ai.get("rationale", ""),
        }
        self._sanitize_coords(report)

        # C7: sensor envelopes get their own handling flag
        report["is_sensor"] = report["category"] == "sensor"

        # C2 — same-source dedup (origin + window + same category)
        merged = self._dedup_same_source(report)
        if merged is not None:
            return merged

        self.reports[report["id"]] = report
        incident = self._cluster(report)                     # C1
        self._recompute_incident(incident)
        self._rank_all()                                     # C3
        if report["ai"]:
            self.log(f"triaged {report['id']}: {report['category']} urgency "
                     f"{report['urgency']} · translated {report['lang']}→en "
                     f"in {report['latency_ms']}ms")
        return incident

    def _sanitize_coords(self, report: dict[str, Any]) -> None:
        """C1 edge case: null-island / out-of-region coords are 'suspect' —
        keep them on the record but don't let them anchor a cluster."""
        lat, lng = report.get("lat"), report.get("lng")
        if lat is None or lng is None:
            return
        w, s, e, n = OPERATING_BBOX
        if not (s <= lat <= n and w <= lng <= e):
            report["location_suspect"] = True
            report["lat"] = report["lng"] = None

    def _dedup_same_source(self, report: dict[str, Any]) -> dict[str, Any] | None:
        """C2: same origin + short window + same category ⇒ MERGE (escalation
        update), never a new incident. Different category from the same origin
        is a NEW emergency — never merged."""
        for other in self.reports.values():
            if (other["origin"] == report["origin"]
                    and other["category"] == report["category"]
                    and abs(report["received_at"] - other["received_at"]) < DEDUP_WINDOW_S):
                inc = self._incident_of(other["id"])
                if inc is None or inc["status"] not in ACTIVE_STATES:
                    continue
                # merge policy: keep earliest id, MAX urgency, LATEST text
                other["urgency"] = max(other["urgency"], report["urgency"])
                other["english"] = report["english"] or other["english"]
                other["gist"] = report["gist"] or other["gist"]
                other["updates"] = other.get("updates", 0) + 1
                self._recompute_incident(inc)
                self._rank_all()
                self.log(f"merged update from {report['origin']} into {inc['id']} "
                         f"(same source, {other['category']}) — urgency now "
                         f"{other['urgency']}")
                return inc
        return None

    def _incident_of(self, report_id: str) -> dict[str, Any] | None:
        for inc in self.incidents.values():
            if report_id in inc["report_ids"]:
                return inc
        return None

    def _cluster(self, report: dict[str, Any]) -> dict[str, Any]:
        """C1 incremental clustering: attach to the nearest active incident
        within eps; else same location-hint lane; else new incident."""
        # lane 1: GPS
        if report["lat"] is not None:
            best, best_d = None, 1e9
            for inc in self.incidents.values():
                if inc["status"] not in ACTIVE_STATES or inc["lat"] is None:
                    continue
                d = haversine_km(report["lat"], report["lng"], inc["lat"], inc["lng"]) * 1000
                if d < best_d:
                    best, best_d = inc, d
            if best is not None and best_d <= CLUSTER_EPS_M:
                best["report_ids"].append(report["id"])
                self.log(f"clustered {report['id']} → {best['id']} "
                         f"({int(best_d)}m ≤ {int(CLUSTER_EPS_M)}m rule)")
                return best
        # lane 2: no GPS — group by location hint text
        elif report["location_hint"]:
            for inc in self.incidents.values():
                if (inc["status"] in ACTIVE_STATES and inc["lat"] is None
                        and inc["location_hint"]
                        and inc["location_hint"].lower() == report["location_hint"].lower()):
                    inc["report_ids"].append(report["id"])
                    self.log(f"clustered {report['id']} → {inc['id']} "
                             f"(same location hint '{report['location_hint']}')")
                    return inc

        inc = {
            "id": f"INC-{len(self.incidents) + 1:02d}",
            "report_ids": [report["id"]],
            "status": "new", "created_at": _now(),
            "assigned_to": None, "proposed": None,
            "assigned_at": None, "resolved_at": None,
            "lat": None, "lng": None, "location_hint": "",
        }
        self.incidents[inc["id"]] = inc
        self.log(f"new incident {inc['id']} from {report['id']}"
                 + (" (no GPS — location unknown lane)" if report["lat"] is None
                    and not report["location_hint"] else ""))
        return inc

    def _recompute_incident(self, inc: dict[str, Any]) -> None:
        """Derived fields: centroid, MAX urgency (cluster ≠ collapse),
        corroboration, sensor confirmation (C7)."""
        members = [self.reports[rid] for rid in inc["report_ids"] if rid in self.reports]
        if not members:
            return
        located = [m for m in members if m["lat"] is not None]
        if located:
            inc["lat"] = sum(m["lat"] for m in located) / len(located)
            inc["lng"] = sum(m["lng"] for m in located) / len(located)
        inc["location_hint"] = next((m["location_hint"] for m in members
                                     if m["location_hint"]), inc.get("location_hint", ""))
        humans = [m for m in members if not m["is_sensor"]]
        sensors = [m for m in members if m["is_sensor"]]
        inc["urgency"] = max(m["urgency"] for m in members)
        inc["report_count"] = len(humans)
        inc["origins"] = len({m["origin"] for m in humans})
        # C7: lone sensor = investigate (moderate); humans+sensor = confirmed
        inc["sensor_confirmed"] = bool(sensors and humans)
        inc["sensor_only"] = bool(sensors and not humans)
        if inc["sensor_only"]:
            inc["urgency"] = min(inc["urgency"], 3)  # investigate, don't over-dispatch
        if inc["sensor_confirmed"] and inc["status"] in ACTIVE_STATES:
            self.log(f"{inc['id']} sensor-corroborated — sensor + "
                     f"{len(humans)} human report(s) agree (highest confidence)")
        cats = [m["category"] for m in humans] or [m["category"] for m in members]
        inc["category"] = max(set(cats), key=cats.count)
        worst = max(members, key=lambda m: (m["urgency"], m["received_at"]))
        inc["headline"] = worst["english"]
        if inc["status"] == "new" and any(m["ai"] for m in members):
            inc["status"] = "triaged"

    # ---- C3 ranking -----------------------------------------------------
    def _rank_all(self) -> None:
        """Severity tier first; within a tier FIFO + bounded aging +
        corroboration boost. Each incident carries its why."""
        for inc in self.incidents.values():
            if inc["status"] not in ACTIVE_STATES:
                inc["rank_score"] = -1
                continue
            waited = _now() - inc["created_at"]
            aging = min(AGING_CAP_BOOST, AGING_CAP_BOOST * waited / AGING_HALF_LIFE_S)
            boost = 0.2 * (inc.get("origins", 1) - 1) + (0.3 if inc.get("sensor_confirmed") else 0)
            inc["rank_score"] = inc["urgency"] + min(0.9, aging + boost)
            why = [f"urgency {inc['urgency']}"]
            if inc.get("report_count", 1) > 1:
                why.append(f"{inc['report_count']} reports")
            if inc.get("sensor_confirmed"):
                why.append("sensor corroborated")
            mins = int(waited // 60)
            why.append(f"waited {mins//60}h{mins%60:02d}m" if mins >= 60 else f"waited {mins}m")
            inc["why"] = " · ".join(why)

    # ---- C5 nearest-responder proposal ----------------------------------
    def propose(self, incident_id: str) -> dict[str, Any] | None:
        """Greedy nearest-available proposal. Proposes — responder confirms."""
        self._refresh_responder_staleness()
        inc = self.incidents.get(incident_id)
        if not inc or inc["status"] not in ACTIVE_STATES:
            return None
        avail = [r for r in self.responders.values() if r["status"] == "available"]
        if not avail:
            inc["status"] = "awaiting responder"
            self.log(f"{inc['id']} awaiting responder — none available")
            return None
        if inc["lat"] is not None:
            best = min(avail, key=lambda r: haversine_km(inc["lat"], inc["lng"], r["lat"], r["lng"]))
            dist = haversine_km(inc["lat"], inc["lng"], best["lat"], best["lng"])
        else:
            best, dist = avail[0], None  # no GPS: nearest is unknowable — first available
        eta_min = int(dist / RESPONDER_SPEED_KMH * 60) + 1 if dist is not None else None
        inc["proposed"] = {
            "responder_id": best["id"], "callsign": best["callsign"],
            "distance_km": round(dist, 1) if dist is not None else None,
            "eta_min": eta_min,
        }
        inc["status"] = "proposed"
        self.log(f"proposed {best['callsign']} for {inc['id']} — nearest available"
                 + (f" {dist:.1f}km, ETA ~{eta_min}min (straight-line)" if dist is not None else ""))
        return inc["proposed"]

    # ---- C6 de-confliction: accept locks, first-write-wins ---------------
    def accept(self, incident_id: str, responder_id: str | None = None) -> tuple[bool, str]:
        inc = self.incidents.get(incident_id)
        if not inc:
            return False, "unknown incident"
        if inc["assigned_to"]:
            return False, "already taken"  # first write won
        rid = responder_id or (inc.get("proposed") or {}).get("responder_id")
        r = self.responders.get(rid) if rid else None
        if not r or r["status"] != "available":
            return False, "responder unavailable"
        inc["assigned_to"] = r["id"]
        inc["assigned_at"] = _now()
        inc["status"] = "en route"
        r["status"] = "on_task"
        r["assigned_incident"] = inc["id"]
        r["last_seen"] = _now()
        self.log(f"{r['callsign']} accepted {inc['id']} — locked "
                 f"(excluded from further assignment)")
        return True, "ok"

    def accept_from_mesh(self, ref_id: str, origin: str) -> bool:
        """C6: an ACCEPTED envelope arrived over the mesh (responder tapped
        Accept on their phone; refId = the SOS id). First-write-wins."""
        inc = self._incident_of(ref_id)
        if not inc:
            return False
        if inc["assigned_to"]:
            self.log(f"mesh accept for {inc['id']} from {origin} refused — "
                     f"already taken (first-write-wins)")
            return False
        # Field responder known only by mesh origin — register on the fly (C4).
        rid = f"mesh-{origin}"
        if rid not in self.responders:
            self.responders[rid] = {
                "id": rid, "callsign": f"FIELD {origin.upper()[:8]}",
                "capability": "mesh responder", "lat": None, "lng": None,
                "status": "available", "assigned_incident": None,
                "last_seen": _now(),
            }
        r = self.responders[rid]
        inc["assigned_to"] = rid
        inc["assigned_at"] = _now()
        inc["status"] = "en route"
        r["status"] = "on_task"
        r["assigned_incident"] = inc["id"]
        r["last_seen"] = _now()
        self.log(f"{r['callsign']} accepted {inc['id']} via mesh — locked")
        self._rank_all()
        return True

    def delivered_from_mesh(self, ref_id: str, origin: str) -> None:
        """DELIVERED is a transient stage-1 hint on the victim ladder — log it."""
        inc = self._incident_of(ref_id)
        self.log(f"report {ref_id} delivery-confirmed by {origin}"
                 + (f" ({inc['id']})" if inc else ""))

    def resolve(self, incident_id: str) -> bool:
        inc = self.incidents.get(incident_id)
        if not inc:
            return False
        inc["status"] = "resolved"
        inc["resolved_at"] = _now()
        self.metrics["resolved"] += 1
        if inc["assigned_at"]:
            self.metrics["response_times_s"].append(inc["resolved_at"] - inc["created_at"])
        r = self.responders.get(inc["assigned_to"] or "")
        if r:
            r["status"] = "available"
            r["assigned_incident"] = None
        self.log(f"{inc['id']} cleared — sector broadcast; duplicates auto-closed. "
                 f"New SOS from this area will NOT be suppressed")
        self._rank_all()
        return True

    def _reopen(self, incident_id: str, reason: str) -> None:
        inc = self.incidents.get(incident_id)
        if not inc or inc["status"] not in {"en route", "on-scene", "assigned"}:
            return
        excluded = inc["assigned_to"]
        inc["assigned_to"] = None
        inc["proposed"] = None
        inc["status"] = "awaiting responder"
        inc["exclude_responder"] = excluded
        self.log(f"re-opened {inc['id']} — {reason}; will reassign excluding "
                 f"the silent responder")
        self._rank_all()

    def check_stuck(self) -> None:
        """C4 stuck-assignment timeout — a victim never waits on a silent responder."""
        self._refresh_responder_staleness()
        for inc in self.incidents.values():
            if inc["status"] == "en route" and inc["assigned_at"]:
                r = self.responders.get(inc["assigned_to"] or "")
                quiet = _now() - (r["last_seen"] if r else inc["assigned_at"])
                if quiet > STUCK_TIMEOUT_S:
                    if r:
                        r["status"] = "offline"
                        r["assigned_incident"] = None
                    self._reopen(inc["id"], f"no progress in {int(quiet//60)}m")

    # ---- C8 capacity (derived, read-only) --------------------------------
    def capacity(self) -> dict[str, Any]:
        avail = sum(1 for r in self.responders.values() if r["status"] == "available")
        total = len(self.responders)
        backlog = sum(1 for i in self.incidents.values()
                      if i["status"] in ACTIVE_STATES and not i["assigned_to"])
        rts = self.metrics["response_times_s"]
        avg_resp_min = int(sum(rts) / len(rts) / 60) if rts else None
        uptime_hr = max((_now() - self.activity[0]["ts"]) / 3600, 1 / 60) if self.activity else 1
        return {
            "available": avail, "total": total, "backlog": backlog,
            "avg_response_min": avg_resp_min,
            "throughput_hr": round(self.metrics["resolved"] / uptime_hr, 1),
            "overwhelmed": backlog > avail,  # C8 flag
            "resolved": self.metrics["resolved"],
        }

    # ---- snapshot for the dashboard --------------------------------------
    def snapshot(self) -> dict[str, Any]:
        self._rank_all()
        lat_ms = self.metrics["triage_latencies_ms"]
        incidents = []
        for inc in self.incidents.values():
            members = [self.reports[rid] for rid in inc["report_ids"] if rid in self.reports]
            members.sort(key=lambda m: (-m["urgency"], m["received_at"]))
            incidents.append({**{k: v for k, v in inc.items() if k != "report_ids"},
                              "reports": members,
                              "waited_s": int(_now() - inc["created_at"])})
        incidents.sort(key=lambda i: (-(i["rank_score"]), i["id"]))
        return {
            "incidents": incidents,
            "responders": sorted(self.responders.values(), key=lambda r: r["id"]),
            "capacity": self.capacity(),
            "activity": self.activity[-60:],
            "metrics": {
                "pkt_rx": self.metrics["pkt_rx"],
                "last_rx": self.metrics["last_rx"],
                "median_triage_ms": (sorted(lat_ms)[len(lat_ms) // 2] if lat_ms else None),
                "critical_open": sum(1 for i in self.incidents.values()
                                     if i["status"] in ACTIVE_STATES and i["urgency"] >= 5
                                     and not i["assigned_to"]),
            },
        }


store = Store()
