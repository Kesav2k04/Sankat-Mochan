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
import os
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
# Wire parsing already rejects invalid latitude/longitude ranges. Do not silently erase
# a valid phone fix merely because the laptop moved from Wayanad to Bengaluru. Deployments
# that need a tighter incident area can opt in with "west,south,east,north".
_bbox_raw = os.getenv("SANKAT_OPERATING_BBOX", "").strip()
try:
    OPERATING_BBOX = tuple(float(v) for v in _bbox_raw.split(",")) if _bbox_raw else None
    if OPERATING_BBOX is not None and len(OPERATING_BBOX) != 4:
        OPERATING_BBOX = None
except ValueError:
    OPERATING_BBOX = None

ACTIVE_STATES = {"new", "triaged", "awaiting responder", "proposed", "assigned", "en route", "on-scene"}

# ---- Sahayak agent TAGS (victim-conversation follow-ups) -------------------
# Wire format (ASCII, rides the normal SOS gist field, ≤244B trivially):
#   "TAGS c:3 inj:bleed trap:y hz:water mob:n unresp:y lm:old temple gate"
# Every value is an enum/small int validated HERE (untrusted mesh input, rule #8)
# and again implicitly by the phone before send. `lm` (landmark) is the only
# free-text value: it must be LAST, is length-capped, and is only ever rendered
# as plain text (rule #9). Unknown keys are dropped, never stored.
TAGS_PREFIX = "TAGS "
TAG_ENUMS: dict[str, set[str]] = {
    "inj": {"none", "bleed", "fracture", "burn", "breath", "uncon", "other"},
    "hz": {"none", "water", "fire", "collapse", "gas", "electric"},
    "trap": {"y", "n"},
    "mob": {"y", "n"},
    "unresp": {"y"},
}
TAG_COUNT_MAX = 99
TAG_LM_MAX = 48

_TAG_LABELS = {  # chip/humanized text — key: (label, value formatter)
    "inj": {"bleed": "bleeding", "fracture": "fracture", "burn": "burns",
            "breath": "breathing difficulty", "uncon": "unconscious", "other": "injured"},
    "hz": {"water": "rising water", "fire": "fire", "collapse": "collapse risk",
           "gas": "gas leak", "electric": "electrical hazard"},
}


def parse_tags(gist: str) -> dict[str, Any] | None:
    """Parse+validate a 'TAGS …' gist into a tag dict. Returns None when the
    payload isn't valid TAGS (caller falls back to normal handling). Only
    whitelisted keys with in-range values survive — everything else is dropped."""
    if not gist.startswith(TAGS_PREFIX):
        return None
    body = gist[len(TAGS_PREFIX):].strip()
    if not body:
        return None
    tags: dict[str, Any] = {}
    rest = body
    while rest:
        key, sep, after = rest.partition(":")
        key = key.strip().lower()
        if not sep or not key.isalpha():
            # A malformed TAIL (e.g. the phone's 244B gist-trim cut mid-pair) must not
            # discard the valid pairs before it; a malformed HEAD means not-TAGS at all.
            if tags:
                break
            return None
        if key == "lm":  # landmark consumes the remainder (free text, capped)
            lm = after.strip()[:TAG_LM_MAX]
            if lm:
                tags["lm"] = lm
            break
        value, _, rest = after.partition(" ")
        value = value.strip().lower()
        rest = rest.strip()
        if key == "c":
            if not value.isdigit() or not (1 <= int(value) <= TAG_COUNT_MAX):
                continue  # bad count: drop the pair, keep the rest
            tags["c"] = int(value)
        elif key in TAG_ENUMS:
            if value in TAG_ENUMS[key]:
                tags[key] = value
        # unknown key: dropped silently (untrusted input, no error surface)
    return tags or None


def humanize_tags(tags: dict[str, Any]) -> str:
    """Plain-text one-liner for headlines/audit-log — never raw wire format."""
    parts: list[str] = []
    if tags.get("c"):
        parts.append(f"{tags['c']} people" if tags["c"] > 1 else "1 person")
    if tags.get("inj") and tags["inj"] != "none":
        parts.append(_TAG_LABELS["inj"][tags["inj"]])
    if tags.get("trap") == "y":
        parts.append("trapped")
    if tags.get("hz") and tags["hz"] != "none":
        parts.append(_TAG_LABELS["hz"][tags["hz"]])
    if tags.get("mob") == "n":
        parts.append("cannot move")
    if tags.get("unresp") == "y":
        parts.append("UNRESPONSIVE")
    if tags.get("lm"):
        parts.append(f"near {tags['lm']}")
    return " · ".join(parts) or "situation update"


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
        # Per-session nodeId (== envelope `origin`) -> stable handset device_id, learned
        # from any envelope a phone sends. Lets a BLE-presence row (which the Pi only knows
        # by the per-session nodeId) collapse onto the SAME `mesh-{device_id}` responder that
        # this phone's ACCEPTED envelopes create — so one handset is one responder even after
        # its app restarts mid-session and its nodeId rolls over.
        self.node_device: dict[str, str] = {}
        self.activity: list[dict[str, Any]] = []          # C13 append-only audit log
        self.metrics = {"pkt_rx": 0, "last_rx": None, "resolved": 0,
                        "response_times_s": [], "triage_latencies_ms": []}
        # Demo roster OFF by default → the dashboard shows ONLY real data.
        # Set SANKAT_SEED_RESPONDERS=1 to pre-load the NDRF/FIRE/MEDIC/K9 roster.
        if os.getenv("SANKAT_SEED_RESPONDERS", "0") == "1":
            self._seed_responders()

    # ---- C13 audit log ------------------------------------------------
    def log(self, text: str) -> None:
        self.activity.append({"ts": _now(), "text": text})
        if len(self.activity) > 400:
            self.activity[:] = self.activity[-400:]

    # ---- C4 responder registry ----------------------------------------
    def _seed_responders(self) -> None:
        """Pre-registered roster for the demo (also fed by heartbeats later).

        Coordinates MUST sit inside the Bengaluru operating box — the same box the map
        centres on (web mapConfig.js) and the sample SOS clusters live in (models.py).
        They previously pointed at Wayanad (~11.68, 76.13), ~140 km away, so every
        seeded responder mobile fell off the edge of the command-post map and only the
        victim pins were ever visible. Placed near the four demo clusters instead."""
        base = [
            ("R1", "NDRF ALPHA", "heavy rescue · rope, cutting gear", 12.9350, 77.6210),   # Koramangala
            ("R2", "FIRE BRAVO", "swift-water · 6 crew", 12.9700, 77.6380),                 # Indiranagar
            ("R3", "MEDIC CHARLIE", "field medical · O2, stretchers", 12.9720, 77.5950),    # city centre
            ("R4", "K9 DELTA", "search dogs · debris survey", 12.9850, 77.6030),            # Shivajinagar
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

    def _responder_key(self, node_id: str) -> str:
        """Canonical responder id for a mesh node. Always `mesh-<device_id>` once the
        handset's stable id is known, else `mesh-<node_id>` — so the presence path
        (nodeId) and the ACCEPTED path (deviceId) converge on ONE key."""
        return f"mesh-{self.node_device.get(node_id) or node_id}"

    def _learn_device(self, node_id: str, device_id: str) -> None:
        """Record a nodeId→device_id mapping from an envelope, then fold any presence
        row still keyed by the pre-session `mesh-<node_id>` onto `mesh-<device_id>`."""
        if not node_id or not device_id or self.node_device.get(node_id) == device_id:
            return
        self.node_device[node_id] = device_id
        old_key, new_key = f"mesh-{node_id}", f"mesh-{device_id}"
        old = self.responders.get(old_key)
        if old is None or old.get("capability") != "mesh responder":
            return
        existing = self.responders.get(new_key)
        if existing is None:
            old["id"], old["device_id"] = new_key, device_id
            self.responders[new_key] = old
        else:
            # Both rows exist — merge presence into the device-keyed row.
            if old.get("status") == "available" and existing.get("status") != "on_task":
                existing["status"] = "available"
            existing["last_seen"] = max(existing["last_seen"], old["last_seen"])
        del self.responders[old_key]
        # Keep any incident that was assigned to the old key pointing at the survivor.
        for inc in self.incidents.values():
            if inc.get("assigned_to") == old_key:
                inc["assigned_to"] = new_key
        self.log(f"linked mesh node {node_id} → device {device_id} (deduped responder)")

    def mesh_responder(self, node_id: str, connected: bool, device_id: str = "") -> None:
        """Reflect an actual responder BLE link reported by the Pi."""
        self._learn_device(node_id, device_id)
        key = self._responder_key(node_id)
        responder = self.responders.get(key)
        if responder is None:
            responder = {
                "id": key,
                "callsign": f"FIELD {node_id.upper()}",
                "capability": "mesh responder",
                "device_id": self.node_device.get(node_id, ""),
                "lat": None,
                "lng": None,
                "status": "offline",
                "assigned_incident": None,
                "last_seen": _now(),
            }
            self.responders[key] = responder
        previous = responder["status"]
        # A presence event must not clobber an active assignment: a still-connected
        # responder that is mid-task stays on_task (it's busy, not free). Only mark
        # available when it isn't already carrying an incident.
        if connected:
            if previous != "on_task":
                responder["status"] = "available"
        else:
            responder["status"] = "offline"
        responder["last_seen"] = _now()
        if responder["status"] != previous:
            self.log(f"responder {node_id} {'connected to' if connected else 'left'} the Pi gateway")

    def mesh_responders_offline(self) -> None:
        """A dead Pi uplink means its BLE responders are no longer dispatchable."""
        for responder in self.responders.values():
            if responder.get("capability") == "mesh responder" and responder["status"] != "offline":
                responder["status"] = "offline"
                responder["last_seen"] = _now()

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
            "id": env["id"], "origin": env["origin"],
            # Stable per-handset id ("d" on the wire). `origin` is a per-SESSION node id
            # that rolls over every app restart, so it can't identify the same phone across
            # runs; device_id can. Used for same-source dedup (C2) and mesh-responder
            # identity so one handset never fans out into duplicate incidents/responders.
            "device_id": env.get("deviceId") or "",
            "ts": env.get("ts", 0),
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
            "voice_transcript": None,
            "voice_english": None,
            "rationale": ai.get("rationale", ""),
            # Server-side triage tags (triage.extract_tags → parse_tags), when the SOS text
            # carried enough detail. Same schema as the phone agent's TAGS, so _recompute's
            # agg_tags renders them in the chip row / ranking. None for bare/undetailed SOS.
            "tags": ai.get("tags") or None,
        }
        self._sanitize_coords(report)
        # Learn this handset's stable id so a later BLE-presence row for the same phone
        # (keyed only by the per-session nodeId) folds onto one responder.
        self._learn_device(report["origin"], report["device_id"])

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
        if OPERATING_BBOX is None:
            return
        w, s, e, n = OPERATING_BBOX
        if not (s <= lat <= n and w <= lng <= e):
            report["location_suspect"] = True
            report["lat"] = report["lng"] = None

    @staticmethod
    def _same_source(a: dict[str, Any], b: dict[str, Any]) -> bool:
        """Two reports come from the same handset. Prefer the stable device_id
        (survives the phone's per-session `origin` rolling over on app restart);
        fall back to `origin` only when a device_id is absent on either side, so an
        old-build phone still dedups within a session and two DIFFERENT phones with
        blank device_ids are never falsely merged."""
        da, db = a.get("device_id") or "", b.get("device_id") or ""
        if da and db:
            return da == db
        return a["origin"] == b["origin"]

    def _dedup_same_source(self, report: dict[str, Any]) -> dict[str, Any] | None:
        """C2: same source + short window + same category ⇒ MERGE (escalation
        update), never a new incident. Different category from the same source
        is a NEW emergency — never merged."""
        for other in self.reports.values():
            if (self._same_source(other, report)
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

    # ---- Sahayak agent TAGS merge --------------------------------------
    def merge_tags_update(self, env: dict[str, Any], tags: dict[str, Any]) -> dict[str, Any] | None:
        """A validated TAGS follow-up from the victim's on-phone agent. Bypasses
        LLM triage entirely (structured, machine-authored, already validated).

        Merge is by ORIGIN + window only — category is deliberately ignored,
        because the phone's agent reuses the original SOS category while LLM
        triage may have re-labelled the incident's earlier reports. The raw
        'TAGS …' wire string must never become gist/english/headline.

        received_at is refreshed on merge so a long conversation + check-in
        timeline (>10 min) keeps the window alive and the unresp escalation
        still lands on the SAME incident."""
        anchor: dict[str, Any] | None = None
        for other in self.reports.values():
            if (other["origin"] == env["origin"] and not other["is_sensor"]
                    and abs(_now() - other["received_at"]) < DEDUP_WINDOW_S):
                inc = self._incident_of(other["id"])
                if inc is None or inc["status"] not in ACTIVE_STATES:
                    continue
                if anchor is None or other["received_at"] > anchor["received_at"]:
                    anchor = other
        summary = humanize_tags(tags)
        if anchor is not None:
            inc = self._incident_of(anchor["id"])
            merged = dict(anchor.get("tags") or {})
            merged.update(tags)
            anchor["tags"] = merged
            if not anchor["gist"]:
                # The victim sent no words of their own — the humanized agent
                # summary beats the "no text details received" placeholder.
                # Never touches a report that carries real victim text.
                anchor["english"] = humanize_tags(merged)
            anchor["urgency"] = max(anchor["urgency"], env.get("urgency", 1))
            anchor["received_at"] = _now()  # keep the merge window alive
            anchor["updates"] = anchor.get("updates", 0) + 1
            self._recompute_incident(inc)
            self._rank_all()
            self.log(f"agent tags from {env['origin']} → {inc['id']}: {summary}"
                     f" — urgency now {anchor['urgency']}")
            return inc
        # Original SOS unknown (lost or aged out): file as a fresh report whose
        # gist is the HUMANIZED summary — never the raw wire string.
        fallback_env = {**env, "gist": summary}
        ai = {"urgency": env.get("urgency", 3), "category": env.get("category") or "other",
              "english": summary, "ai": False, "latency_ms": 0}
        incident = self.add_report(fallback_env, ai)
        if incident is not None:
            for rid in incident["report_ids"]:
                if rid == env["id"]:
                    self.reports[rid]["tags"] = dict(tags)
            self._recompute_incident(incident)
            self._rank_all()
            self.log(f"agent tags from {env['origin']} had no anchor SOS — "
                     f"filed as new report: {summary}")
        return incident

    def attach_voice(self, report_id: str, audio_url: str, transcript: str | None,
                     ai: dict[str, Any] | None = None) -> bool:
        """Attach a reassembled mesh recording to its original SOS.

        The text is used only when STT produced non-blank output. A failed/empty
        transcription still leaves playable audio on the report and never replaces a
        truthful structured headline with invented content.
        """
        report = self.reports.get(report_id)
        if report is None:
            return False
        report["audio"] = audio_url
        clean = (transcript or "").strip()
        if clean:
            report["voice_transcript"] = clean
            report["voice_english"] = (ai or {}).get("english") or clean
            # M5: a report that already carries typed mobile text is authoritative. The
            # voice clip only ADDS audio + a voice transcript/translation to it — it must
            # NOT touch urgency/rationale/ai/latency, or a benign voice add-on could inflate
            # a real typed SOS. Voice text becomes the PRIMARY text (and can set those
            # fields) only when the phone sent no typed details at all.
            if not report["gist"]:
                report["gist"] = clean
                report["english"] = report["voice_english"]
                report["urgency"] = max(
                    report["urgency"], int((ai or {}).get("urgency", report["urgency"]))
                )
                report["rationale"] = (ai or {}).get("rationale", report["rationale"])
                report["ai"] = bool((ai or {}).get("ai"))
                report["latency_ms"] = (ai or {}).get("latency_ms", 0)
        incident = self._incident_of(report_id)
        if incident is not None:
            self._recompute_incident(incident)
            self._rank_all()
        self.log(
            f"voice attached to {report_id}" +
            (" and transcribed" if clean else
             " (transcription pending)" if transcript is None else
             " (transcription unavailable)")
        )
        return True

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
        # The phone's exact words are the source of truth. AI translation remains on
        # the report as secondary text and must never replace what the mobile sent.
        inc["headline"] = worst["gist"] or worst["english"]
        # Sahayak agent tags: aggregate member tags (later reports win) for the
        # dashboard chip-row; unresponsive is a first-class flag for ranking.
        agg_tags: dict[str, Any] = {}
        for m in sorted(members, key=lambda m: m["received_at"]):
            if m.get("tags"):
                agg_tags.update(m["tags"])
        inc["tags"] = agg_tags
        inc["unresponsive"] = agg_tags.get("unresp") == "y"
        if not inc["headline"] and agg_tags:
            # Empty-details SOS + agent conversation: the humanized tag summary
            # becomes the headline (fills a blank — never replaces victim words).
            inc["headline"] = humanize_tags(agg_tags)
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
            if inc.get("unresponsive"):
                boost += 0.4  # victim stopped answering agent check-ins
            inc["rank_score"] = inc["urgency"] + min(0.9, aging + boost)
            why = [f"urgency {inc['urgency']}"]
            if inc.get("report_count", 1) > 1:
                why.append(f"{inc['report_count']} reports")
            if inc.get("sensor_confirmed"):
                why.append("sensor corroborated")
            if inc.get("unresponsive"):
                why.append("victim unresponsive")
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

    def accept_from_mesh(self, ref_id: str, origin: str, device_id: str = "") -> bool:
        """C6: an ACCEPTED envelope arrived over the mesh (responder tapped
        Accept on their phone; refId = the SOS id). First-write-wins."""
        inc = self._incident_of(ref_id)
        if not inc:
            return False
        if inc["assigned_to"]:
            self.log(f"mesh accept for {inc['id']} from {origin} refused — "
                     f"already taken (first-write-wins)")
            return False
        # Field responder registered on the fly (C4). Key by the STABLE device_id when the
        # phone sent one, so the same handset accepting after an app restart (new `origin`)
        # updates its existing row instead of adding a duplicate responder. `_learn_device`
        # also folds any earlier BLE-presence row for this node onto the same key. Old-build
        # phones with no device_id keep the per-session `mesh-{origin}` identity as before.
        self._learn_device(origin, device_id)
        rid = self._responder_key(origin)
        if rid not in self.responders:
            self.responders[rid] = {
                "id": rid, "callsign": f"FIELD {origin.upper()[:8]}",
                "capability": "mesh responder", "device_id": device_id,
                "lat": None, "lng": None,
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
