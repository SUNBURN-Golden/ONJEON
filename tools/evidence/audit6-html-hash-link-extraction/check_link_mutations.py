#!/usr/bin/env python3
"""Reject each Audit 6 defect using hash and CLI tests; mutate only in memory."""
import io
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
    hash_class = "test_html_content_hash.DownloadTargetsChangeTheHash."
    cli_test = ("test_verify_sources.CliDependencies."
                "test_detect_cli_reports_exact_audit6_link_extraction_changes")
    cases = {
        "omit_fnDown_onclick": hash_class + "test_fn_down_filename_changes_without_visible_text_changes",
        "omit_unquoted_href": hash_class + "test_exact_unquoted_href_filename_changes",
        "data_href_shadows_href": hash_class + "test_real_href_is_kept_regardless_of_data_href_order",
    }
    for mutation, hash_test in cases.items():
        def mutated(parser, tag, attrs):
            if mutation == "omit_fnDown_onclick":
                attrs = [(name, value) for name, value in attrs
                         if not (name == "onclick" and value and "fnDown(" in value)]
            elif mutation == "omit_unquoted_href":
                if re.search(r"\shref\s*=\s*[^\s'\"]", parser.get_starttag_text(), re.I):
                    attrs = [(name, value) for name, value in attrs if name != "href"]
            elif mutation == "data_href_shadows_href" and tag == "a":
                # Reproduce the old substring regex taking data-href first.
                first = next((value for name, value in attrs if name in {"href", "data-href"}), None)
                attrs = [(name, value) for name, value in attrs if name not in {"href", "data-href"}]
                if first is not None:
                    attrs.append(("href", first))
            original(parser, tag, attrs)

        for name in (hash_test, cli_test):
            suite = unittest.defaultTestLoader.loadTestsFromName(name)
            output = io.StringIO()
            with mock.patch.object(hch._ContentParser, "handle_starttag", mutated):
                result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
            if result.wasSuccessful() or result.errors or result.skipped or result.testsRun != 1:
                print(output.getvalue(), end="")
                print(f"MUTATION NOT REJECTED CLEANLY: {mutation}: {name}", flush=True)
                return 1
            print(f"MUTATION REJECTED: {mutation}: {name} "
                  f"({len(result.failures)} assertion failures)", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
