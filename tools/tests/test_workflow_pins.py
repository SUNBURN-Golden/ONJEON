"""Every third-party `uses:` under .github/ must be pinned to a full 40-hex commit SHA.

A tag such as `actions/checkout@v4` can be moved by the action's owner, so a CI run could execute
different code than was reviewed. All current refs are pinned as `uses: owner/name@<sha> # <tag>`;
KNOWN_UNPINNED is a ratchet: a new unpinned ref fails, and so does a listed ref that has since been
pinned (delete its entry then).

Local `./` actions are exempt. Both `.yml` and `.yaml` are scanned, in .github/workflows/ and in
composite actions under .github/actions/.
Run: python3 -m unittest discover -s tools/tests
"""
import collections
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
GITHUB_DIR = ROOT / ".github"
QUOTED = r'"(?:\\.|[^"\\])*"|' r"'(?:''|[^'])*'"
# Read block and flow mapping entries. Consume other quoted scalars and comments so that
# text such as `run: echo "{ uses: actions/checkout@v4 }"` is not an action reference.
USES = re.compile(
    r'''(?:^\s*(?:-\s+)?|(?<=[{,])\s*)(?:uses|"uses"|'uses')\s*:\s*'''
    rf'''(?P<ref>{QUOTED}|[^\s#,{{}}\[\]]+)|{QUOTED}|\#.*$'''
)
BLOCK_SCALAR = re.compile(
    r'''^\s*(?:-\s+)?(?:[\w-]+|"[^"]*"|'[^']*'):\s*'''
    r"[|>](?:[1-9][+-]?|[+-][1-9]?)?\s*(?:#.*)?$"
)
PINNED = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")

# {file path relative to repo root: {unpinned ref: occurrences}}; all actions are SHA-pinned, so
# this is empty and any new unpinned ref fails the test below.
KNOWN_UNPINNED = {}


def action_files():
    """Workflow files and composite-action files, .yml and .yaml."""
    for pat in ("*.yml", "*.yaml"):
        yield from sorted((GITHUB_DIR / "workflows").glob(pat))
        yield from sorted((GITHUB_DIR / "actions").glob(f"**/{pat}"))


def unpinned_refs(text):
    """[(line number, ref)] for each non-local `uses:` that is not `<action>@<40 hex>`."""
    found = []
    block_indent = None
    for n, line in enumerate(text.splitlines(), 1):
        indent = len(line) - len(line.lstrip())
        if block_indent is not None:
            if not line.strip() or indent > block_indent:
                continue
            block_indent = None
        if BLOCK_SCALAR.search(line):
            block_indent = indent
            continue
        for m in USES.finditer(line):
            if m.group("ref") is None:
                continue
            ref = m.group("ref").strip("\"'")
            if not ref.startswith("./") and not PINNED.fullmatch(ref):
                found.append((n, ref))
    return found


class UnpinnedRefsParser(unittest.TestCase):
    def test_flags_tags_branches_and_short_shas(self):
        text = "\n".join([
            "steps:",
            "  - uses: actions/checkout@v4",
            "  - uses: actions/cache@main",
            "  - uses: actions/setup-python@" + "a" * 39,
            "  - uses: 'actions/upload-artifact@v4'  # comment",
            "  - uses: actions/checkout",
        ])
        self.assertEqual(
            [r for _, r in unpinned_refs(text)],
            ["actions/checkout@v4", "actions/cache@main",
             "actions/setup-python@" + "a" * 39, "actions/upload-artifact@v4", "actions/checkout"],
        )

    def test_accepts_full_sha_with_tag_comment_and_local_actions(self):
        sha = "0123456789abcdef0123456789abcdef01234567"
        text = f"  - uses: actions/checkout@{sha} # v4.2.2\n  - uses: ./.github/actions/x\n"
        self.assertEqual(unpinned_refs(text), [])

    def test_rejects_uppercase_or_non_hex_sha(self):
        self.assertEqual(len(unpinned_refs("  - uses: a/b@" + "A" * 40)), 1)
        self.assertEqual(len(unpinned_refs("  - uses: a/b@" + "g" * 40)), 1)

    def test_flow_mappings_flag_unpinned_refs(self):
        for entry in (
            "- { uses: actions/checkout@v4 }",
            "- { name: Checkout, uses: 'actions/checkout@v4' }",
            '- { "uses": "actions/checkout@v4" }',
            "steps: [{uses: actions/checkout@v4}, {uses: actions/cache@main}]",
            "steps: [{\n  uses: actions/checkout@v4\n}]",
        ):
            with self.subTest(entry=entry):
                self.assertIn("actions/checkout@v4", [r for _, r in unpinned_refs(entry)])
        self.assertEqual(
            unpinned_refs("steps: [{uses: actions/checkout@v4}, {uses: actions/cache@main}]"),
            [(1, "actions/checkout@v4"), (1, "actions/cache@main")],
        )

    def test_flow_mappings_accept_full_shas_and_local_actions(self):
        sha = "0123456789abcdef0123456789abcdef01234567"
        for ref in (f"actions/checkout@{sha}", "./.github/actions/x"):
            for quoted in (ref, f'"{ref}"', f"'{ref}'"):
                with self.subTest(ref=quoted):
                    self.assertEqual(unpinned_refs(f"- {{ uses: {quoted}, name: Checkout }}"), [])

    def test_comments_and_script_strings_are_not_actions(self):
        text = '''# - { uses: actions/checkout@v4 }
steps:
  - run: echo "{ uses: actions/checkout@v4 }"
  - run: |
      uses: actions/checkout@v4
      echo '{ uses: actions/checkout@v4 }'
  - name: 'Example, uses: actions/checkout@v4'
    run: echo ok # uses: actions/checkout@v4
  - uses: actions/cache@main
'''
        self.assertEqual(unpinned_refs(text), [(9, "actions/cache@main")])
        self.assertEqual(
            unpinned_refs("- { uses: actions/checkout@v4 } # example: |"),
            [(1, "actions/checkout@v4")],
        )


class WorkflowPinsDiscovery(unittest.TestCase):
    def test_guard_rejects_unpinned_actions_in_both_yaml_extensions(self):
        # Exercise the repository guard itself, including file discovery, without changing
        # real workflows. Each injected tag must make that guard fail for its own file/ref.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            github = root / ".github"
            guard = WorkflowPins("test_unpinned_refs_match_known_list")
            with mock.patch.multiple(__name__, ROOT=root, GITHUB_DIR=github):
                for folder in ("workflows", "actions/composite"):
                    for suffix in (".yml", ".yaml"):
                        path = github / folder / ("example" + suffix)
                        path.parent.mkdir(parents=True, exist_ok=True)
                        for entry in ("- uses: actions/checkout@v4",
                                      "- { uses: actions/checkout@v4 }"):
                            with self.subTest(folder=folder, suffix=suffix, entry=entry):
                                path.write_text(entry + "\n", encoding="utf-8")
                                with self.assertRaises(AssertionError) as failure:
                                    guard.test_unpinned_refs_match_known_list()
                                self.assertIn(path.relative_to(root).as_posix(), str(failure.exception))
                                self.assertIn("actions/checkout@v4", str(failure.exception))
                                path.write_text(
                                    "- { uses: a/b@" + "a" * 40 + " }\n", encoding="utf-8"
                                )
                                guard.test_unpinned_refs_match_known_list()
                        path.unlink()


class WorkflowPins(unittest.TestCase):
    def test_workflows_exist(self):
        self.assertTrue(list((GITHUB_DIR / "workflows").glob("*.y*ml")), "no workflows found; wrong path?")

    def test_unpinned_refs_match_known_list(self):
        actual = {}
        for path in action_files():
            refs = unpinned_refs(path.read_text(encoding="utf-8"))
            if refs:
                actual[path.relative_to(ROOT).as_posix()] = dict(collections.Counter(r for _, r in refs))
        self.assertEqual(
            actual,
            KNOWN_UNPINNED,
            "third-party actions must be pinned as `uses: owner/name@<40-hex sha> # tag`; "
            "if a listed ref is now pinned, remove it from KNOWN_UNPINNED",
        )


if __name__ == "__main__":
    unittest.main()
