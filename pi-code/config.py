"""
Config loading. Everything the gateway does is driven from JSON + env overrides —
no radio pin, frequency, UUID, or peer address is baked into the code.

Resolution order (last wins):
  1. config.example.json  (defaults, checked in)
  2. config.json          (local, gitignored)  or  $SANKAT_CONFIG
  3. env vars             SANKAT_<DOTTED__PATH>, '.' written as '__'

  e.g.  SANKAT_LORA__TX_POWER_DBM=10
        SANKAT_RADIOS__FIELD__DIO0_GPIO=4
        SANKAT_BLE__PEERS__FIELD=AA:BB:CC:DD:EE:FF
        SANKAT_UPLINK__URL=http://10.148.169.50:8000/sos

Secrets (rule 2) never live in the JSON — pass them via env only.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Dict

HERE = Path(__file__).resolve().parent
ENV_PREFIX = "SANKAT_"


class ConfigError(RuntimeError):
    pass


def _strip_comments(node: Any) -> Any:
    if isinstance(node, dict):
        return {k: _strip_comments(v) for k, v in node.items() if not k.startswith("_")}
    if isinstance(node, list):
        return [_strip_comments(v) for v in node]
    return node


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _coerce(raw: str) -> Any:
    """Env vars are strings; recover the JSON type the caller meant."""
    low = raw.strip().lower()
    if low in ("null", "none", ""):
        return None
    if low in ("true", "false"):
        return low == "true"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _apply_env(cfg: Dict[str, Any]) -> Dict[str, Any]:
    for env_key, raw in os.environ.items():
        if not env_key.startswith(ENV_PREFIX) or env_key == "SANKAT_CONFIG":
            continue
        path = env_key[len(ENV_PREFIX):].lower().split("__")
        node: Any = cfg
        for part in path[:-1]:
            if not isinstance(node, dict) or part not in node:
                node = None
                break
            node = node[part]
        if isinstance(node, dict) and path[-1] in node:
            node[path[-1]] = _coerce(raw)
        else:
            raise ConfigError(f"{env_key} does not match any key in the config schema")
    return cfg


def load(path: str | os.PathLike | None = None) -> Dict[str, Any]:
    defaults_path = HERE / "config.example.json"
    if not defaults_path.exists():
        raise ConfigError(f"missing {defaults_path}")
    cfg = _strip_comments(json.loads(defaults_path.read_text()))

    local = Path(path) if path else Path(os.environ.get("SANKAT_CONFIG", HERE / "config.json"))
    if local.exists():
        cfg = _deep_merge(cfg, _strip_comments(json.loads(local.read_text())))

    cfg = _apply_env(cfg)
    _validate(cfg)
    return cfg


def _validate(cfg: Dict[str, Any]) -> None:
    # Which radio node(s) this board actually runs. Defaults to both for the original
    # single-Pi bench; a split board (Pi=gateway, UNO Q=field) lists just one.
    active = cfg.get("run", {}).get("nodes")
    if not isinstance(active, list) or not active or not all(isinstance(n, str) for n in active):
        raise ConfigError("run.nodes must be a non-empty list of radio names, e.g. [\"field\"]")
    if len(set(active)) != len(active):
        raise ConfigError(f"run.nodes has duplicates: {active}")

    for node in active:
        r = cfg["radios"].get(node)
        if not r:
            raise ConfigError(f"run.nodes lists '{node}' but there is no radios.{node} block")
        transport = r.get("transport", "spi")
        if transport not in ("spi", "serial", "bridge"):
            raise ConfigError(f'radios.{node}.transport must be "spi", "serial" or "bridge"')
        if transport == "bridge":
            # A bridge radio is the UNO Q's own MCU, reached over the Router Bridge unix
            # socket — no device path, no SPI chip-select or GPIO pins. socket_path is
            # optional (defaults to /var/run/arduino-router.sock).
            if "socket_path" in r and (
                not isinstance(r["socket_path"], str) or not r["socket_path"]
            ):
                raise ConfigError(f"radios.{node}.socket_path must be a non-empty string")
        elif transport == "serial":
            # A serial radio (the UNO Q field modem) is reached over a device path and
            # needs no SPI chip-select or GPIO pins.
            if not isinstance(r.get("serial_port"), str) or not r["serial_port"]:
                raise ConfigError(
                    f'radios.{node}.serial_port must be set for a serial radio, '
                    'e.g. "/dev/ttyACM0"')
            if "serial_baud" in r and (
                not isinstance(r["serial_baud"], int)
                or isinstance(r["serial_baud"], bool) or r["serial_baud"] <= 0
            ):
                raise ConfigError(f"radios.{node}.serial_baud must be a positive int")
        else:
            for key in ("cs", "rst_gpio", "dio0_gpio"):
                if not isinstance(r.get(key), int):
                    raise ConfigError(f"radios.{node}.{key} must be an int")

    # These two only bite when a single board drives more than one SPI radio (both on the
    # same bus, inches apart). A split board runs one radio, so they are vacuous. Serial
    # radios carry no chip-select or GPIO pins, so they are exempt from both.
    spi_nodes = [n for n in active if cfg["radios"][n].get("transport", "spi") == "spi"]
    if len(spi_nodes) > 1:
        cs = [cfg["radios"][n]["cs"] for n in spi_nodes]
        if len(set(cs)) != len(cs):
            raise ConfigError("radios on one board must sit on different SPI chip-selects")
        pins = [cfg["radios"][n][k] for n in spi_nodes for k in ("rst_gpio", "dio0_gpio")]
        if len(set(pins)) != len(pins):
            raise ConfigError(f"radio GPIO pins must be unique, got {pins}")

    if cfg["lora"]["tx_repeats"] < 1:
        raise ConfigError("lora.tx_repeats must be >= 1")
    if cfg["uplink"]["enabled"] and not cfg["uplink"]["url"]:
        raise ConfigError("uplink.enabled is true but uplink.url is unset")

    v = cfg["voice"]
    node_id = v.get("node_id")
    if not isinstance(node_id, str) or not (1 <= len(node_id) <= 4) or not node_id.isalnum():
        raise ConfigError("voice.node_id must be 1-4 alphanumeric characters")
    for key in ("nack_quiet_s", "sweep_interval_s", "upload_connect_s", "upload_read_s"):
        if key in v and (not isinstance(v.get(key), (int, float)) or v[key] <= 0):
            raise ConfigError(f"voice.{key} must be a positive number")
    if "upload_concurrency" in v and (
        not isinstance(v["upload_concurrency"], int)
        or isinstance(v["upload_concurrency"], bool)
        or v["upload_concurrency"] < 1
    ):
        raise ConfigError("voice.upload_concurrency must be an int >= 1")

    ing = cfg.get("ingest", {})
    if "global_frames_per_s" in ing and (
        not isinstance(ing["global_frames_per_s"], (int, float))
        or ing["global_frames_per_s"] <= 0
    ):
        raise ConfigError("ingest.global_frames_per_s must be a positive number")
    for key in ("queue_max", "seen_max"):
        if key in ing and (
            not isinstance(ing[key], int) or isinstance(ing[key], bool) or ing[key] < 1
        ):
            raise ConfigError(f"ingest.{key} must be an int >= 1")
    if "outbox_max" in cfg.get("uplink", {}) and (
        not isinstance(cfg["uplink"]["outbox_max"], int)
        or isinstance(cfg["uplink"]["outbox_max"], bool)
        or cfg["uplink"]["outbox_max"] < 1
    ):
        raise ConfigError("uplink.outbox_max must be an int >= 1")


def lora_config(cfg: Dict[str, Any]):
    from sx127x import LoraConfig
    l = cfg["lora"]
    return LoraConfig(
        frequency_hz=l["frequency_hz"],
        spreading_factor=l["spreading_factor"],
        bandwidth_hz=l["bandwidth_hz"],
        coding_rate=l["coding_rate"],
        tx_power_dbm=l["tx_power_dbm"],
        sync_word=l["sync_word"],
        preamble_len=l["preamble_len"],
        crc=l["crc"],
        max_payload=l["max_payload"],
        spi_bus=l["spi"]["bus"],
        spi_speed_hz=l["spi"]["speed_hz"],
    )
