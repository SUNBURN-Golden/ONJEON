#!/usr/bin/env python3
"""Run policy regressions against the baseline and in-memory policy removals."""
import io
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
BASELINE = "94c8b64cefb1ced5341d3e24e690915d085b3d5b"
AUDIT6 = "89fbd7e13b8b97c248c60688fab077cc7fd7323e"
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "tools/tests")]


def snapshot(revision, path):
    return subprocess.check_output(["git", "show", f"{revision}:{path}"], cwd=ROOT, text=True)


def check(name, source, cases):
    module = types.ModuleType("verify_sources_mutant")
    module.__file__ = str(ROOT / "tools/verify_sources.py")
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    suite = unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName(case, tests) for case in cases)
    output = io.StringIO()
    with mock.patch.object(tests, "vs", module):
        result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    print(f"=== {name} ===\n{output.getvalue()}")
    if result.errors or result.skipped or not result.failures:
        raise AssertionError(f"{name}: expected assertion failures, no errors/skips")


# Replay the original tests with the sources they exercised. Audit 8 replaced
# the same-origin redirect handler and its test cases with a no-redirect policy.
tests = types.ModuleType("test_verify_sources_fetch_audit6")
test_path = "tools/tests/test_verify_sources_fetch.py"
tests.__file__ = str(ROOT / test_path)
exec(compile(snapshot(AUDIT6, test_path), tests.__file__, "exec"), tests.__dict__)
source = snapshot(AUDIT6, "tools/verify_sources.py")
baseline = snapshot(BASELINE, "tools/verify_sources.py")
host_check = '''    if origin[1] not in registered_source_hosts():
        raise FetchRejected("url_disallowed: host is not in the source host registry")
'''
assert host_check in source
check("baseline permits arbitrary initial HTTPS hosts", baseline,
      ["SourceHostRegistry.test_adding_a_sample_url_does_not_register_its_host",
       "SourceHostRegistry.test_unregistered_initial_hosts_never_open_or_retry"])
check("remove host admission", source.replace(host_check, ""),
      ["SourceHostRegistry.test_adding_a_sample_url_does_not_register_its_host",
       "SourceHostRegistry.test_unregistered_initial_hosts_never_open_or_retry",
       "RedirectPolicy.test_same_origin_redirect_still_requires_registered_host"])
check("remove redirect origin comparison", source.replace(
    "if origin != target_origin:", "if False:"),
    ["RedirectPolicy.test_every_redirect_code_refuses_cross_origin_before_standard_handler"])
check("remove initial HTTPS validation", source.replace(
    "origin = sm.https_origin(url)",
    "p = urllib.parse.urlsplit(url)\n        origin = ('https', p.hostname, p.port or 443)"),
    ["RedirectPolicy.test_non_https_and_credentialed_initial_urls_never_open"])
print("Baseline and three policy-removal mutations rejected by assertions.")
