#!/usr/bin/env python3
"""Run a product task's required-ID tests. Missing implementations fail closed.

Registration: tools/task_tests/<task>/coverage.py, with a literal TEST_IDS list
of (required_id, "TestCaseClass.test_method") pairs. Each target must resolve to
one unittest in that module. Native Rust/Flutter/web tests use unittest adapters
that verify the native test count, exit status and evidence (see task_tests/README.md).
This is a task completion check, not a claim of product/release readiness.
"""
import argparse
import ast
from collections import Counter
import functools
import importlib.util
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = Path("docs/blueprint/proposals/설계검토_결과/tasks.json")
TASK_ID = re.compile(r"T-[A-Z]{2}-\d{2}")
TEST_ID = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def required_ids(task):
    ids = task.get("required_test_ids")
    require(isinstance(ids, list) and all(isinstance(i, str) and TEST_ID.fullmatch(i) for i in ids),
            "required_test_ids must be a list of test IDs")
    require(len(ids) == len(set(ids)), "duplicate required_test_ids")
    return ids


def inventory(path, required):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    assignments = [n.value for n in tree.body if isinstance(n, ast.Assign)
                   and any(isinstance(t, ast.Name) and t.id == "TEST_IDS" for t in n.targets)]
    require(len(assignments) == 1, "exactly one literal TEST_IDS assignment required")
    entries = ast.literal_eval(assignments[0])
    require(isinstance(entries, list) and bool(entries), "TEST_IDS must be a nonempty list")
    require(all(isinstance(e, (list, tuple)) and len(e) == 2
                and all(isinstance(s, str) and s for s in e) for e in entries),
            "TEST_IDS entries must be (required_id, Class.test_method) pairs")
    ids, targets = zip(*entries)
    missing, unlisted = sorted(set(required) - set(ids)), sorted(set(ids) - set(required))
    repeated = sorted(k for k, v in Counter(ids).items() if v > 1)
    reused = sorted(k for k, v in Counter(targets).items() if v > 1)
    require(not (missing or unlisted or repeated or reused),
            f"missing={missing}, unlisted={unlisted}, repeated={repeated}, reused_tests={reused}")
    require(all(re.fullmatch(r"[A-Za-z_]\w*\.test_\w+", target) for target in targets),
            "each target must be Class.test_method in coverage.py")
    return entries


class RequiredResult(unittest.TextTestResult):
    """An empty method is not a passing counterpart to a required ID.

    Only assertions run inside the registered test method count. Assertions
    in setUp/tearDown/cleanup fixtures cannot satisfy an empty method.
    """
    def startTest(self, test):
        super().startTest(test)
        test._required_assertions = 0
        test._required_counting = False
        for name in dir(test):
            method = getattr(test, name)
            if name.startswith("assert") and callable(method):
                @functools.wraps(method)
                def counted(*args, _method=method, **kwargs):
                    if test._required_counting:
                        test._required_assertions += 1
                    return _method(*args, **kwargs)
                setattr(test, name, counted)
        if isinstance(test, unittest.TestCase):
            name = test._testMethodName
            method = getattr(test, name)
            @functools.wraps(method)
            def counted_method(*args, _method=method, **kwargs):
                test._required_counting = True
                try:
                    return _method(*args, **kwargs)
                finally:
                    test._required_counting = False
            setattr(test, name, counted_method)

    def addSuccess(self, test):
        if not test._required_assertions:
            error = AssertionError("required-ID test ran no unittest assertions")
            self.addFailure(test, (AssertionError, error, None))
        else:
            super().addSuccess(test)


def run_task(root, task, stream):
    tid = task.get("id")
    require(isinstance(tid, str) and TASK_ID.fullmatch(tid), "invalid task ID")
    require(tid not in ("T-OP-00", "T-OP-09"), "daemon tasks use their own coverage runners")
    required = required_ids(task)
    # Removing an ID while leaving its prose description cannot create a passing empty denominator.
    tests = task.get("tests")
    require(isinstance(tests, list) and all(isinstance(t, str) for t in tests), "invalid tests")
    described = []
    for description in tests:
        if description.startswith("시험 "):
            match = re.match(r"시험 ([a-z][a-z0-9]*(?:-[a-z0-9]+)+)(?=[:(\s])", description)
            require(match and match[1] in required, f"unregistered prose test: {description}")
            described.append(match[1])
    require(set(described) == set(required) and len(described) == len(set(described)),
            "required IDs and prose descriptions must match exactly once")
    path = root / "tools/task_tests" / tid / "coverage.py"
    if not required and not path.exists():
        print(f"{tid}: required_test_ids=[] (no required-ID tests declared)", file=stream)
        return 0
    entries = inventory(path, required)
    spec = importlib.util.spec_from_file_location("task_coverage_" + tid.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    previous = sys.modules.get(spec.name)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        require(module.TEST_IDS == entries, "TEST_IDS changed during module execution")
        suite = unittest.TestSuite()
        for test_id, target in entries:
            cls_name, method = target.split(".")
            cls = getattr(module, cls_name, None)
            require(isinstance(cls, type) and issubclass(cls, unittest.TestCase)
                    and cls.__module__ == module.__name__ and callable(getattr(cls, method, None)),
                    f"{test_id}: missing local unittest {target}")
            case = cls(method)
            require(type(case) is cls and case._testMethodName == method,
                    f"{test_id}: test target changed during construction")
            print(f"{test_id} -> {target}", file=stream)
            suite.addTest(case)
        result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=RequiredResult).run(suite)
        ok = (result.wasSuccessful() and result.testsRun == len(required)
              and not result.skipped and not result.expectedFailures)
        print(f"{tid}: required={len(required)}, ran={result.testsRun}, "
              f"skipped={len(result.skipped)}, expected_failures={len(result.expectedFailures)}, "
              f"coverage={'PASS' if ok else 'FAIL'}", file=stream)
        return 0 if ok else 1
    finally:
        if previous is None:
            sys.modules.pop(spec.name, None)
        else:
            sys.modules[spec.name] = previous



def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", required=True)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        data = json.loads((root / args.registry).read_text(encoding="utf-8"), object_pairs_hook=unique_object)
        tasks = data["tasks"]
        require(isinstance(tasks, list) and all(isinstance(t, dict) for t in tasks), "tasks must be a list")
        tids = [t.get("id") for t in tasks]
        require(all(isinstance(tid, str) and TASK_ID.fullmatch(tid) for tid in tids)
                and len(set(tids)) == len(tids), "invalid/duplicate task IDs")
        matches = [t for t in tasks if t["id"] == args.task]
        require(len(matches) == 1, f"unknown task: {args.task}")
        sys.path.insert(0, str(root))
        return run_task(root, matches[0], sys.stdout)
    except (OSError, ValueError, SyntaxError, TypeError, KeyError, ImportError, AttributeError) as exc:
        print(f"{args.task}: coverage FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
