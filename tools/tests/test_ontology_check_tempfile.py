"""Bad-rule self-tests isolate temporary files from the frozen rule tree."""
import copy
import json
import os
import selectors
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[2]
CHECK_DIR = REPO / "docs/blueprint/proposals/온톨로지/검증"
sys.path.insert(0, str(CHECK_DIR))
import ontology_check as check  # noqa: E402


def rule_path(mutated):
    return Path(next(a for a in mutated["assertions"]
                     if a["id"] == "a:hana_rule")["rule_path"])


class BadRuleTemporaryFile(unittest.TestCase):
    def test_readable_mutation_outside_repo_and_cleanup_on_return(self):
        mutated = copy.deepcopy(check.ABOX)
        original = Path(check.ROOT) / rule_path(mutated)
        before = original.read_bytes()
        expected = json.loads(before)
        expected["evidence_refs"].append("hana_2601_3d#c_2_1_art5")
        sentinel = object()

        def inspect():
            path = rule_path(mutated)
            self.assertTrue(path.is_absolute())
            self.assertFalse(path.is_relative_to(REPO))
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), expected)
            return sentinel

        self.assertIs(check.with_bad_rule(mutated, inspect), sentinel)
        self.assertFalse(rule_path(mutated).exists())
        self.assertEqual(original.read_bytes(), before)

    def test_constraints_and_frozen_release_still_detect_bad_rule(self):
        for frozen, constraint, reason in (
            (False, "K9", "규칙 근거가 담보의 C0 basis 밖"),
            (True, "K15", "규칙 파일 해시가 고정값과 다름"),
        ):
            with self.subTest(frozen=frozen):
                mutated = copy.deepcopy(check.ABOX)
                violations = check.with_bad_rule(mutated, lambda: check.check_constraints(
                    check.view(mutated, check.CURRENT) if frozen else check.candidate_view(mutated)))
                self.assertTrue(any(cid == constraint and reason in message
                                    for cid, _, message in violations), violations)
                self.assertFalse(rule_path(mutated).exists())

    def test_cleanup_and_propagation_on_callback_exception(self):
        for error in (RuntimeError("callback failed"), KeyboardInterrupt()):
            with self.subTest(error=type(error).__name__):
                mutated = copy.deepcopy(check.ABOX)

                def fail():
                    self.assertTrue(rule_path(mutated).is_file())
                    raise error

                with self.assertRaises(type(error)) as caught:
                    check.with_bad_rule(mutated, fail)
                self.assertIs(caught.exception, error)
                self.assertFalse(rule_path(mutated).exists())

    def test_cleanup_when_serialization_fails(self):
        paths = []

        def fail_dump(data, stream, **kwargs):
            paths.append(Path(stream.name))
            raise OSError("write failed")

        with mock.patch.object(check.json, "dump", side_effect=fail_dump), \
                self.assertRaisesRegex(OSError, "write failed"):
            check.with_bad_rule(copy.deepcopy(check.ABOX), lambda: self.fail("callback ran"))
        self.assertEqual(len(paths), 1)
        self.assertFalse(paths[0].exists())

    def test_overlapping_calls_have_independent_files(self):
        barrier = threading.Barrier(2, timeout=10)

        def run(marker):
            mutated = copy.deepcopy(check.ABOX)

            def inspect():
                path = rule_path(mutated)
                data = json.loads(path.read_text(encoding="utf-8"))
                data["test_marker"] = marker
                path.write_text(json.dumps(data), encoding="utf-8")
                barrier.wait()
                self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["test_marker"], marker)
                barrier.wait()
                return path

            return check.with_bad_rule(mutated, inspect)

        with ThreadPoolExecutor(max_workers=2) as pool:
            paths = list(pool.map(run, ("first", "second")))
        self.assertNotEqual(paths[0], paths[1])
        for path in paths:
            self.assertFalse(path.is_relative_to(REPO))
            self.assertFalse(path.exists())

    @unittest.skipUnless(os.name == "posix", "SIGKILL regression requires POSIX")
    def test_killed_process_leaves_no_debris_in_rule_tree(self):
        rules = Path(check.ROOT) / "규칙"
        before = {p.name: p.read_bytes() for p in rules.iterdir() if p.is_file()}
        code = """
import copy, signal, sys
sys.path.insert(0, sys.argv[1])
import ontology_check as check
mutated = copy.deepcopy(check.ABOX)
def wait_for_kill():
    path = next(a['rule_path'] for a in mutated['assertions'] if a['id'] == 'a:hana_rule')
    print(path, flush=True)
    signal.pause()
check.with_bad_rule(mutated, wait_for_kill)
"""
        # The parent owns this directory so even the deliberately killed child's
        # OS-temp residue is removed after the test.
        with tempfile.TemporaryDirectory() as directory:
            env = dict(os.environ, TMPDIR=directory, TEMP=directory, TMP=directory)
            with subprocess.Popen([sys.executable, "-B", "-c", code, str(CHECK_DIR)],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, env=env) as child:
                try:
                    with selectors.DefaultSelector() as selector:
                        selector.register(child.stdout, selectors.EVENT_READ)
                        self.assertTrue(selector.select(timeout=10), "child did not reach callback")
                    line = child.stdout.readline().strip()
                    self.assertTrue(line, "child exited before callback")
                    path = Path(line)
                    self.assertFalse(path.is_relative_to(REPO))
                    self.assertEqual(path.parent, Path(directory))
                    self.assertTrue(path.is_file())
                    json.loads(path.read_text(encoding="utf-8"))
                    child.kill()
                    child.communicate(timeout=10)
                    self.assertLess(child.returncode, 0)
                    self.assertEqual(before, {p.name: p.read_bytes() for p in rules.iterdir() if p.is_file()})
                finally:
                    if child.poll() is None:
                        child.kill()
                    child.communicate(timeout=10)


if __name__ == "__main__":
    unittest.main()
