#!/usr/bin/env python3
"""Prove Audit 5 regressions reject lost href/onclick signals, only in memory."""
import re
import sys
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(TOOLS), str(TOOLS / "tests")]
import html_content_hash as hch  # noqa: E402


def main():
    original = hch._ContentParser.handle_starttag
    cases = {
        "omit_unquoted_href": [
            "test_html_content_hash.DownloadTargetsChangeTheHash."
            "test_unquoted_href_keeps_filename_while_removing_session",
            "test_verify_sources.CliDependencies."
            "test_detect_cli_reports_exact_audit5_download_filename_changes",
        ],
        "omit_onclick": [
            "test_html_content_hash.DownloadTargetsChangeTheHash."
            "test_file_down_filename_changes_without_visible_text_changes",
            "test_verify_sources.CliDependencies."
            "test_detect_cli_reports_exact_audit5_download_filename_changes",
        ],
    }
    for mutation, tests in cases.items():
        def mutated(parser, tag, attrs):
            unquoted = re.search(r"\bhref\s*=\s*[^\s'\"]", parser.get_starttag_text(), re.I)
            attrs = [(name, value) for name, value in attrs
                     if not (mutation == "omit_onclick" and name == "onclick")
                     and not (mutation == "omit_unquoted_href" and tag == "a"
                              and name == "href" and unquoted)]
            original(parser, tag, attrs)

        for name in tests:
            suite = unittest.defaultTestLoader.loadTestsFromName(name)
            with mock.patch.object(hch._ContentParser, "handle_starttag", mutated):
                result = unittest.TextTestRunner(verbosity=2).run(suite)
            if result.wasSuccessful() or result.errors or result.skipped or result.testsRun != 1:
                print(f"MUTATION NOT REJECTED CLEANLY: {mutation}: {name}", flush=True)
                return 1
            print(f"MUTATION REJECTED: {mutation}: {name}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
