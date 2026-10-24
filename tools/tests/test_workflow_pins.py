"""Every third-party `uses:` under .github/ must be pinned to a full 40-hex commit SHA.

A tag such as `actions/checkout@v4` can be moved by the action's owner, so a CI run could execute
different code than was reviewed. All current refs are pinned as `uses: owner/name@<sha> # <tag>`;
KNOWN_UNPINNED is a ratchet: a new unpinned ref fails, and so does a listed ref that has since been
pinned (delete its entry then).

Local `./` actions are exempt. Both `.yml` and `.yaml` are scanned, in .github/workflows/ and in
composite actions under .github/actions/. Action values must start on the same line as `uses:`;
empty values and block scalars are rejected, even when their contents are pinned or local.
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
    r'''(?P<entry>(?:^\s*(?:-\s+)?|(?<=[{,])\s*)(?:uses|"uses"|'uses')\s*:\s*)'''
    rf'''|{QUOTED}|\#.*$|(?P<flow>[{{}}\[\]])'''
)
BLOCK_SCALAR = re.compile(
    r'''^\s*(?:-\s+)?(?P<key>[\w-]+|"[^"]*"|'[^']*'):\s*'''
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


def action_scalar(line, start, in_flow):
    """Read the complete scalar; only flow mappings treat commas as separators."""
    end = start
    while end < len(line):
        char = line[end]
        if char == "#" and (end == start or line[end - 1].isspace()):
            break
        if in_flow and char in ",{}[]":
            break
        if char in "\"'":
            quoted = re.match(QUOTED, line[end:])
            if quoted:
                end += quoted.end()
                continue
        end += 1
    ref = line[start:end].strip()
    if re.fullmatch(QUOTED, ref):
        ref = ref[1:-1]
    return ref or "<empty or multiline uses value>", end


def unpinned_refs(text):
    """Report unpinned non-local refs and unsupported empty/multiline action values."""
    found = []
    block_indent = None
    flow_depth = 0
    for n, line in enumerate(text.splitlines(), 1):
        indent = len(line) - len(line.lstrip())
        if block_indent is not None:
            if not line.strip() or indent > block_indent:
                continue
            block_indent = None
        pos = 0
        while m := USES.search(line, pos):
            pos = m.end()
            if m.group("flow"):
                if m.group("flow") in "{[":
                    # Brackets inside an ordinary block scalar (e.g. a step name)
                    # do not turn subsequent action values into flow scalars.
                    if flow_depth or re.search(r"(?:^\s*(?:-\s+)?|:\s*)$", line[:m.start()]):
                        flow_depth += 1
                elif flow_depth:
                    flow_depth -= 1
            if m.group("entry") is None:
                continue
            ref, pos = action_scalar(line, pos, flow_depth > 0)
            if not ref.startswith("./") and not PINNED.fullmatch(ref):
                found.append((n, ref))
        # Inspect the header first so `uses: >-` cannot disappear with script bodies.
        if header := BLOCK_SCALAR.search(line):
            # A sequence dash precedes the key; sibling keys align with the key,
            # so they end the scalar even though they are indented past the dash.
            block_indent = header.start("key")
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

    def test_rejects_sha_prefix_with_scalar_suffix(self):
        pinned = "actions/checkout@" + "a" * 40
        for suffix in ("#mutable", ",mutable", " mutable", ", uses: a/b@main"):
            ref = pinned + suffix
            for key in ("uses", '"uses"', "'uses'"):
                for value in (ref, f'"{ref}"', f"'{ref}'"):
                    with self.subTest(key=key, value=value):
                        self.assertEqual(unpinned_refs(f"  - {key}: {value}"), [(1, ref)])
        for value in (pinned + "#mutable", pinned + " mutable"):
            with self.subTest(flow=value):
                self.assertEqual(unpinned_refs(f"- {{ uses: {value} }}"), [(1, value)])
        for name in ("Example [open", "Example {open", "Example ]closed", "Example }closed"):
            with self.subTest(name=name):
                ref = pinned + ",mutable"
                self.assertEqual(unpinned_refs(f"- name: {name}\n  uses: {ref}"), [(2, ref)])

    def test_comments_and_flow_separators_end_scalars(self):
        pinned = "actions/checkout@" + "a" * 40
        for value in (pinned, f'"{pinned}"', f"'{pinned}'"):
            for whitespace in (" ", "\t"):
                with self.subTest(value=value, whitespace=whitespace):
                    self.assertEqual(unpinned_refs(f"- uses: {value}{whitespace}# tag, example"), [])
            self.assertEqual(unpinned_refs(f"- {{uses: {value}, name: Checkout}}"), [])
            self.assertEqual(
                unpinned_refs(f"steps: [{{\n  uses: {value}, name: Checkout\n}}]"), []
            )

    def test_rejects_block_scalar_action_values(self):
        # Multiline uses values are deliberately unsupported, even for pinned/local actions.
        for key in ("uses", '"uses"', "'uses'"):
            for indicator in (">", ">-", ">+", ">2-", ">-2", "|", "|-", "|+", "|2", "|+2"):
                for ref in ("actions/checkout@v4", "a/b@" + "a" * 40, "./local"):
                    text = f"steps:\n  - {key}: {indicator} # action\n      {ref}\n"
                    with self.subTest(key=key, indicator=indicator, ref=ref):
                        self.assertEqual(unpinned_refs(text), [(2, indicator)])

    def test_rejects_empty_or_next_line_action_values(self):
        for key in ("uses", '"uses"', "'uses'"):
            for suffix in ("", " # action"):
                for value in (
                    "", "\n      actions/checkout@v4",
                    "\n\n      # comment\n      actions/checkout@v4",
                ):
                    text = f"steps:\n  - {key}:{suffix}{value}\n"
                    with self.subTest(key=key, suffix=suffix, value=value):
                        self.assertEqual(unpinned_refs(text), [(2, "<empty or multiline uses value>")])
        self.assertEqual(
            unpinned_refs("steps: [{uses:\n  actions/checkout@v4}]"),
            [(1, "<empty or multiline uses value>")],
        )

    def test_rejected_block_scalar_does_not_hide_following_action(self):
        text = "  - uses: >-\n      actions/checkout@v4\n  - uses: actions/cache@main\n"
        self.assertEqual(unpinned_refs(text), [(1, ">-"), (3, "actions/cache@main")])

    def test_multiline_step_name_does_not_hide_sibling_action(self):
        for key in ("name", '"name"', "'name'"):
            for indicator in ("|", "|-", "|+", "|2", "|+2", ">", ">-", ">+", ">2-", ">-2"):
                for prefix in ("  - ", "  -   ", "    "):
                    key_indent = " " * len(prefix)
                    text = (
                        f"steps:\n{prefix}{key}: {indicator} # step name\n"
                        f"{key_indent}  uses: example/text@v1\n"
                        f"{key_indent}uses: actions/checkout@v4\n"
                    )
                    with self.subTest(key=key, indicator=indicator, prefix=prefix):
                        self.assertEqual(unpinned_refs(text), [(4, "actions/checkout@v4")])
                        for ref in ("actions/checkout@" + "a" * 40, "./local"):
                            self.assertEqual(
                                unpinned_refs(text.replace("actions/checkout@v4", ref)), []
                            )

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
                        for entry, diagnostic in (
                            ("- uses: actions/checkout@v4", "actions/checkout@v4"),
                            ("- uses: a/b@" + "a" * 40 + "#mutable", "a/b@" + "a" * 40 + "#mutable"),
                            ("- uses: a/b@" + "a" * 40 + ",mutable", "a/b@" + "a" * 40 + ",mutable"),
                            ("- { uses: actions/checkout@v4 }", "actions/checkout@v4"),
                            ("steps:\n  - name: |\n      Checkout\n    uses: actions/checkout@v4", "actions/checkout@v4"),
                            ("steps:\n  - name: >-\n      Checkout\n    uses: actions/checkout@v4", "actions/checkout@v4"),
                            ("- uses: >-\n    actions/checkout@v4", ">-"),
                            ("- uses: |\n    actions/checkout@v4", "'|'"),
                            ("- uses:\n    actions/checkout@v4", "<empty or multiline uses value>"),
                        ):
                            with self.subTest(folder=folder, suffix=suffix, entry=entry):
                                path.write_text(entry + "\n", encoding="utf-8")
                                with self.assertRaises(AssertionError) as failure:
                                    guard.test_unpinned_refs_match_known_list()
                                self.assertIn(path.relative_to(root).as_posix(), str(failure.exception))
                                self.assertIn(diagnostic, str(failure.exception))
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
