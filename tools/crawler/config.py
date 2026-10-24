"""Crawler settings: one validated, frozen dataclass loaded from a JSON file.

Safe defaults: network_enabled is False and nothing else (env, argument, test hook) can turn it on;
the only way is `"network_enabled": true` in the config file, and transport.py additionally needs
the env flag ONJEON_CRAWLER_ALLOW_NETWORK=1. Unknown or duplicate keys are rejected.
"""
import json
import math
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Mapping

HARD_OBJECT_CAP_BYTES = 64 * 1024 * 1024  # no object ever held in memory above this (300 MB cgroup)
MAX_CONFIG_FILE_BYTES = 1024 * 1024


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class CrawlerConfig:
    contact: str = ""
    network_enabled: bool = False
    per_host_min_interval_s: float = 5
    per_host_concurrency: int = 1
    max_global_hosts: int = 4
    max_attempts: int = 3
    daily_request_cap_default: int = 200
    robots_cache_ttl_s: float = 86400
    spool_dir: str = "var/crawler/spool"
    spool_cap_bytes: int = 1_500_000_000
    object_cap_bytes: int = HARD_OBJECT_CAP_BYTES
    state_db: str = "var/crawler/state.sqlite3"

    def __post_init__(self):
        _str(self, "contact", max_len=200, allow_empty=True)
        _bool(self, "network_enabled")
        _num(self, "per_host_min_interval_s", lo=1, hi=86400)
        _int(self, "per_host_concurrency", lo=1, hi=4)
        _int(self, "max_global_hosts", lo=1, hi=16)
        _int(self, "max_attempts", lo=1, hi=3)  # spec hard cap: at most 3 attempts per request
        _int(self, "daily_request_cap_default", lo=1, hi=100_000)
        _num(self, "robots_cache_ttl_s", lo=60, hi=7 * 86400)
        _str(self, "spool_dir", max_len=1024)
        _int(self, "spool_cap_bytes", lo=1, hi=1 << 40)
        _int(self, "object_cap_bytes", lo=1, hi=HARD_OBJECT_CAP_BYTES)
        _str(self, "state_db", max_len=1024)
        if self.object_cap_bytes > self.spool_cap_bytes:
            raise ConfigError("object_cap_bytes must not exceed spool_cap_bytes")


def _fail(name: str, why: str):
    raise ConfigError(f"config {name}: {why}")


def _bool(cfg, name):
    if not isinstance(getattr(cfg, name), bool):
        _fail(name, "must be true or false")


def _int(cfg, name, lo, hi):
    v = getattr(cfg, name)
    if isinstance(v, bool) or not isinstance(v, int):
        _fail(name, "must be an integer")
    if not lo <= v <= hi:
        _fail(name, f"must be between {lo} and {hi}")


def _num(cfg, name, lo, hi):
    v = getattr(cfg, name)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        _fail(name, "must be a finite number")
    if not lo <= v <= hi:
        _fail(name, f"must be between {lo} and {hi}")


def _str(cfg, name, max_len, allow_empty=False):
    v = getattr(cfg, name)
    if not isinstance(v, str):
        _fail(name, "must be a string")
    if not v and not allow_empty:
        _fail(name, "must not be empty")
    if len(v) > max_len or "\x00" in v:
        _fail(name, "too long or contains NUL")


def config_from_dict(data: Mapping[str, Any]) -> CrawlerConfig:
    if not isinstance(data, Mapping):
        raise ConfigError("config must be a JSON object")
    known = {f.name for f in fields(CrawlerConfig)}
    unknown = sorted(str(k) for k in data if k not in known)
    if unknown:
        raise ConfigError(f"unknown config keys: {', '.join(unknown)}")
    return CrawlerConfig(**dict(data))


def _no_duplicates(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ConfigError(f"duplicate config key: {k}")
        out[k] = v
    return out


def load_config(path) -> CrawlerConfig:
    p = Path(path)
    with p.open("rb") as f:
        raw = f.read(MAX_CONFIG_FILE_BYTES + 1)
    if len(raw) > MAX_CONFIG_FILE_BYTES:
        raise ConfigError("config file too large")
    try:
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=_no_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        raise ConfigError(f"config is not valid UTF-8 JSON: {type(e).__name__}") from None
    return config_from_dict(data)
