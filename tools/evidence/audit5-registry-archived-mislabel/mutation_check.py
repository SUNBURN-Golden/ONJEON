"""Reintroduce each audit defect only in the CLI test's disposable script."""
import io
import shutil
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools/tests"))
import test_registry_normalize as tests


def check_mutation(label, mutate, expected_failures):
    copyfile = shutil.copyfile
    copies = []

    def copy_mutated_script(source, destination, *args, **kwargs):
        result = copyfile(source, destination, *args, **kwargs)
        if Path(source) == Path(tests.rn.__file__):
            script = Path(destination)
            script.write_text(mutate(script.read_text(encoding="utf-8")), encoding="utf-8")
            copies.append(script)
        return result

    output = io.StringIO()
    suite = unittest.TestSuite([tests.RegistryCli(
        "test_repairs_legacy_registry_with_empty_access_log_from_another_directory")])
    with patch.object(tests.shutil, "copyfile", side_effect=copy_mutated_script):
        result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    print(f"{label}: {len(copies)} disposable scripts, "
          f"{len(result.failures)} failures, {len(result.errors)} errors")
    print(output.getvalue())
    if len(copies) != 2 or len(result.failures) != expected_failures or result.errors:
        raise SystemExit(f"{label}: expected detection for both empty-log forms")


def archived_again(source):
    old = 'return "unqueried", "공시 URL 접근 확인(reachable). 원문 무결성 검사·불변 보관 전"'
    if source.count(old) != 1:
        raise SystemExit("reachable branch was not found exactly once")
    return source.replace(old, 'return "archived", ""')


def empty_guard_removed(source):
    before, function = source.split("def normalize_access_log(path):", 1)
    guard = "    if not rows:\n        return 0\n"
    if function.count(guard) != 1:
        raise SystemExit("empty access-log guard was not found exactly once")
    return before + "def normalize_access_log(path):" + function.replace(guard, "", 1)


if __name__ == "__main__":
    check_mutation("reachable -> archived", archived_again, expected_failures=4)
    check_mutation("empty access-log guard removed", empty_guard_removed, expected_failures=2)
    print("PASS: both historical defects detected; repository script/CSVs unchanged")
