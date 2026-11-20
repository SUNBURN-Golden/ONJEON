#!/usr/bin/env python3
"""Recompute V1 HTML sample baselines from a local content-addressed raw archive."""

import argparse
import csv
import stat
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import html_content_hash as hch  # noqa: E402
import source_archive as sa  # noqa: E402
import source_metadata as sm  # noqa: E402


def rebaseline(samples, raw_dir):
    with samples.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        required = {"sample_id", "format", "url", "sha256", "content_sha256", "content_hash_rule"}
        if not fields or not required.issubset(fields):
            raise ValueError("samples.csv is missing required columns")
        rows = list(reader)

    raw = sa.LocalStore(raw_dir)
    baselines = {}
    changed = False
    for row in rows:
        if row["format"] != "html":
            continue
        sample_id = row["sample_id"]
        digest = row["sha256"]
        try:
            _, host, _ = sm.https_origin(row["url"])
            body = raw.get(sa.object_key(digest))
            if sa.sha256_bytes(body) != digest:
                raise ValueError("archived bytes do not match the recorded SHA-256")
        except (OSError, ValueError) as e:
            raise ValueError(f"{sample_id}: {e}") from e
        content = hch.content_sha256(body, host)
        if (row["content_sha256"], row["content_hash_rule"]) != (content, hch.RULE):
            row.update(content_sha256=content, content_hash_rule=hch.RULE)
            changed = True
        baselines[sample_id] = content

    if not baselines:
        raise ValueError("samples.csv has no HTML samples")
    if changed:
        mode = stat.S_IMODE(samples.stat().st_mode)
        temp = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", newline="", dir=samples.parent,
                prefix=f".{samples.name}.", suffix=".tmp", delete=False,
            ) as f:
                temp = Path(f.name)
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            temp.chmod(mode)
            temp.replace(samples)
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)
    return baselines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, required=True, help="local archive directory containing objects/sha256")
    args = parser.parse_args(argv)
    try:
        baselines = rebaseline(sa.SAMPLES, args.raw_dir)
    except (OSError, ValueError, csv.Error) as e:
        print(e, file=sys.stderr)
        return 1
    for sample_id, digest in baselines.items():
        print(f"{sample_id} {hch.RULE} {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
