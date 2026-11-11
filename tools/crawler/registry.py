"""Read-only source registry. Unknown CSV columns are deliberately ignored.

Only source_id and url are required, so the existing registry needs no migration.
Missing/blank policy fields default to terms_status=unknown and tier=C. Adapter
names are metadata, never imported or executed. No network or environment access.
"""
import csv
import math
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


class RegistryError(ValueError):
    pass


@dataclass(frozen=True)
class Source:
    source_id: str
    url: str
    terms_status: str = "unknown"
    tier: str = "C"
    min_interval_s: float = 0
    adapter: str = ""
    daily_cap: int | None = None  # None uses CrawlerConfig's default; zero disables.

    def __post_init__(self):
        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise RegistryError("source_id must be nonempty")
        try:
            parts = urlsplit(self.url)
            valid = (parts.scheme in {"http", "https"} and parts.hostname
                     and parts.username is None and parts.password is None)
            parts.port  # validate malformed ports without opening anything
        except (ValueError, TypeError, AttributeError):
            valid = False
        if not valid:
            raise RegistryError("url must be an absolute HTTP(S) URL without credentials")
        if self.terms_status not in {"allowed", "restricted", "unknown"}:
            raise RegistryError("invalid terms_status")
        if self.tier not in {"A", "B", "C", "D"}:
            raise RegistryError("invalid tier")
        if (isinstance(self.min_interval_s, bool)
                or not isinstance(self.min_interval_s, (int, float))
                or not math.isfinite(self.min_interval_s) or self.min_interval_s < 0):
            raise RegistryError("min_interval_s must be finite and nonnegative")
        if self.daily_cap is not None and (isinstance(self.daily_cap, bool)
                or not isinstance(self.daily_cap, int) or self.daily_cap < 0):
            raise RegistryError("daily_cap must be a nonnegative integer")
        if not isinstance(self.adapter, str):
            raise RegistryError("adapter must be a string")

    @property
    def host(self) -> str:
        return urlsplit(self.url).hostname.lower()


def load_registry(path) -> list[Source]:
    """Stream a caller-selected CSV opened only in read mode; never rewrite it.

    Malformed policy fields and duplicate IDs fail closed rather than accidentally
    scheduling a source under a more permissive default.
    """
    sources = []
    seen = set()
    with Path(path).open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        header = reader.fieldnames or []
        if not {"source_id", "url"}.issubset(header) or len(set(header)) != len(header):
            raise RegistryError("CSV needs unique columns including source_id and url")
        for row in reader:
            if None in row:
                raise RegistryError(f"row {reader.line_num}: extra CSV cells")
            value = lambda key, default="": (row.get(key) or "").strip() or default
            try:
                source = Source(
                    source_id=value("source_id"), url=value("url"),
                    terms_status=value("terms_status", "unknown"), tier=value("tier", "C"),
                    min_interval_s=float(value("min_interval_s", "0")),
                    adapter=value("adapter"),
                    daily_cap=int(value("daily_cap")) if value("daily_cap") else None,
                )
                if source.source_id in seen:
                    raise RegistryError("duplicate source_id")
            except ValueError as exc:
                raise RegistryError(f"row {reader.line_num}: {exc}") from None
            seen.add(source.source_id)
            sources.append(source)
    return sources
