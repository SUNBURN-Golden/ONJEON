#!/usr/bin/env python3
"""Report release evidence coverage; this scaffold does not authorize release.

Exit 0: all declared rows/features covered; 1: incomplete; 2: invalid input.
See README.md beside this script for the version 1 evidence manifest contract.
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / "docs/blueprint/proposals/설계검토_결과"
PURPOSE = BUNDLE / "09_제품목적_대응표.md"
POST_MERGE = frozenset({"merged", "audit_queued", "done"})
ROW_IDS = {f"P{i:02}" for i in range(1, 20)}
TASK_ID = re.compile(r"T-[A-Z]{2}-\d{2}")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)


def strings(value):
    return (isinstance(value, list) and bool(value)
            and all(isinstance(s, str) and s.strip() for s in value)
            and len(set(value)) == len(value))


def read_contract(registry, purpose):
    data = read_json(registry)
    require(isinstance(data, dict) and isinstance(data.get("tasks"), list),
            "registry.tasks must be a list")
    tasks = set()
    for task in data["tasks"]:
        require(isinstance(task, dict), "task must be an object")
        tid = task.get("id")
        require(isinstance(tid, str) and TASK_ID.fullmatch(tid) and tid not in tasks,
                f"invalid or duplicate task: {tid}")
        tasks.add(tid)
    require(tasks, "empty task registry")

    rows, columns = {}, None
    for line in purpose.read_text(encoding="utf-8").splitlines():
        if not line.lstrip().startswith("|"):
            columns = None
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells[0] == "#":
            columns = [i for i, c in enumerate(cells) if c.startswith("구현 작업")]
        elif re.fullmatch(r"P\d+", cells[0]):
            pid = cells[0]
            require(pid in ROW_IDS and pid not in rows, f"unexpected/duplicate row: {pid}")
            require(columns and len(columns) == 1 and columns[0] < len(cells),
                    f"{pid}: missing implementation tasks column")
            refs = [s.strip().strip("`") for s in cells[columns[0]].split(",")]
            require(strings(refs) and set(refs) <= tasks, f"{pid}: invalid/unknown tasks")
            rows[pid] = {"tasks": refs}
    require(set(rows) == ROW_IDS, f"missing purpose rows: {sorted(ROW_IDS - rows.keys())}")

    features = {}
    require(isinstance(data.get("feature_registry"), list) and data["feature_registry"],
            "feature_registry must be a nonempty list")
    for feature in data["feature_registry"]:
        require(isinstance(feature, dict), "feature must be an object")
        fid = feature.get("id")
        require(isinstance(fid, str) and fid.strip() and fid not in features,
                f"invalid/duplicate feature: {fid}")
        require(strings(feature.get("tasks")) and set(feature["tasks"]) <= tasks,
                f"{fid}: invalid/unknown tasks")
        require(strings(feature.get("acceptance_tests")), f"{fid}: missing acceptance tests")
        require(type(feature.get("excluded")) is bool, f"{fid}: excluded must be boolean")
        features[fid] = feature
    return tasks, rows, features


def read_manifest(directory, tasks, rows, features):
    path = directory / "readiness.json"
    # Missing evidence is incomplete, never an empty passing denominator.
    if not directory.exists():
        return {"task_states": {}, "rows": {}, "features": {}}
    require(directory.is_dir(), "evidence must be a directory")
    if not path.exists():
        return {"task_states": {}, "rows": {}, "features": {}}
    data = read_json(path)
    require(isinstance(data, dict), "readiness.json must be an object")
    require(type(data.get("version")) is int and data["version"] == 1,
            "readiness.json version must be 1")
    require(set(data) == {"version", "task_states", "rows", "features"},
            "readiness.json requires only version, task_states, rows, features")
    for key, known in (("task_states", tasks), ("rows", rows), ("features", features)):
        require(isinstance(data[key], dict), f"{key} must be an object")
        require(set(data[key]) <= set(known), f"{key}: unknown IDs {sorted(set(data[key]) - set(known))}")
    require(all(isinstance(state, str) for state in data["task_states"].values()),
            "task_states values must be state strings")
    for group in ("rows", "features"):
        for key, record in data[group].items():
            require(isinstance(record, dict), f"{key}: evidence record must be an object")
            require(set(record) <= {"environment", "evidence", "acceptance_tests", "excluded", "scope_decision"},
                    f"{key}: unknown evidence fields")
    return data


def artifact_problem(directory, reference):
    if not isinstance(reference, str) or not reference.strip():
        return "invalid artifact path"
    relative = Path(reference)
    if relative.is_absolute() or ".." in relative.parts:
        return f"artifact must be relative within evidence directory: {reference}"
    path = (directory / relative).resolve()
    if not path.is_relative_to(directory.resolve()):
        return f"artifact escapes evidence directory: {reference}"
    try:
        if not path.is_file() or not path.read_bytes().strip():
            return f"missing/empty artifact: {reference}"
    except OSError:
        return f"unreadable artifact: {reference}"
    return None


def inspect_item(item, record, states, directory):
    reasons = []
    # No current P row or feature has approved whole-item exclusion. In
    # particular, ADR-0018's narrower denominator does not exclude P01.
    if (record.get("excluded", False) is not False or record.get("scope_decision")
            or item.get("excluded", False) or item.get("scope_decision")):
        reasons.append("unsupported exclusion: no approved whole-item scope decision")
    for tid in item["tasks"]:
        state = states.get(tid)
        if state not in POST_MERGE:
            reasons.append(f"{tid}: not post_merge (state={state or 'missing'})")
    if record.get("environment") != "release":
        reasons.append("missing release evidence environment (fixture/test evidence cannot close item)")
    evidence = record.get("evidence")
    if not strings(evidence):
        reasons.append("missing/invalid evidence references")
    else:
        for reference in evidence:
            problem = artifact_problem(directory, reference)
            if problem:
                reasons.append(problem)
    logs = record.get("acceptance_tests")
    names = set()
    if not isinstance(logs, list) or not logs:
        reasons.append("missing acceptance_tests execution logs")
    else:
        for log in logs:
            if (not isinstance(log, dict) or set(log) != {"name", "log", "exit_code"}
                    or not isinstance(log["name"], str) or not log["name"].strip()):
                reasons.append("invalid acceptance_tests execution record")
                continue
            name = log["name"]
            if name in names:
                reasons.append(f"duplicate acceptance test: {name}")
            names.add(name)
            if type(log["exit_code"]) is not int or log["exit_code"] != 0:
                reasons.append(f"acceptance test did not pass: {name}")
            problem = artifact_problem(directory, log["log"])
            if problem:
                reasons.append(f"{name}: {problem}")
    for name in item.get("acceptance_tests", []):
        if name not in names:
            reasons.append(f"missing acceptance test: {name}")
    return {"status": "open" if reasons else "closed", "reasons": reasons}


def check(registry, purpose, directory):
    tasks, rows, features = read_contract(registry, purpose)
    manifest = read_manifest(directory, tasks, rows, features)
    report = {"scope": "evidence coverage only; not T-OP-08 completion or release approval"}
    for group, items in (("rows", rows), ("features", features)):
        report[group] = {
            key: inspect_item(item, manifest[group].get(key, {}), manifest["task_states"], directory)
            for key, item in sorted(items.items())
        }
        report[group + "_counts"] = {
            status: sum(item["status"] == status for item in report[group].values())
            for status in ("open", "closed", "excluded")
        }
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=BUNDLE / "tasks.json")
    parser.add_argument("--purpose", type=Path, default=PURPOSE)
    parser.add_argument("--evidence", type=Path, default=ROOT / "docs/release-readiness/evidence")
    parser.add_argument("--json", action="store_true", help="emit structured diagnostics")
    args = parser.parse_args(argv)
    try:
        report = check(args.registry, args.purpose, args.evidence)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"cannot read release-readiness inputs: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for group, test_id in (("rows", "purpose-rows-all-closed"),
                               ("features", "release-readiness-rejects-incomplete")):
            for key, item in report[group].items():
                print(f"{key}: {item['status']}" + (": " + "; ".join(item["reasons"]) if item["reasons"] else ""))
            print(f"{test_id}: " + ", ".join(f"{k}={v}" for k, v in report[group + "_counts"].items()))
        print(report["scope"])
    return int(bool(report["rows_counts"]["open"] or report["features_counts"]["open"]))


if __name__ == "__main__":
    sys.exit(main())
