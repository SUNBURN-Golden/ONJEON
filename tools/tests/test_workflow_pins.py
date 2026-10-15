"""Every third-party `uses:` in .github/workflows must be pinned to a full 40-hex commit SHA.

A tag such as `actions/checkout@v4` can be moved by the action's owner, so a CI run could execute
different code than was reviewed. The workflows are not editable from the builder worktree and the
SHAs must be looked up from upstream, so the refs that were still tag-pinned when this check was
added are listed in KNOWN_UNPINNED. That list is a ratchet: a new unpinned ref fails, and so does a
listed ref that has since been pinned (delete its entry then).

The workflow edit itself is for the supervisor or a maintainer: resolve each tag with
`gh api repos/<owner>/<name>/git/ref/tags/<tag>` (dereference annotated tags to the commit SHA),
write `uses: owner/name@<sha> # <tag>`, and empty KNOWN_UNPINNED in the same change.
Run: python3 -m unittest discover -s tools/tests
"""
import collections
import re
import unittest
from pathlib import Path

WORKFLOWS = Path(__file__).resolve().parents[2] / ".github/workflows"
USES = re.compile(r"^\s*(?:-\s+)?uses:\s*(?P<ref>[^\s#]+)")
PINNED = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")

# {workflow file: {unpinned ref: occurrences}}; must shrink to {} once the workflows are pinned.
KNOWN_UNPINNED = {
    "ci.yml": {"actions/checkout@v4": 2},
    "sources.yml": {"actions/checkout@v4": 2, "actions/upload-artifact@v4": 2},
}


def unpinned_refs(text):
    """[(line number, ref)] for each non-local `uses:` that is not `<action>@<40 hex>`."""
    found = []
    for n, line in enumerate(text.splitlines(), 1):
        m = USES.match(line)
        if not m:
            continue
        ref = m.group("ref").strip("\"'")
        if not ref.startswith("./") and not PINNED.match(ref):
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


class WorkflowPins(unittest.TestCase):
    def test_workflows_exist(self):
        self.assertTrue(sorted(WORKFLOWS.glob("*.yml")), "no workflows found; wrong path?")

    def test_unpinned_refs_match_known_list(self):
        actual = {}
        for path in sorted(WORKFLOWS.glob("*.yml")):
            refs = unpinned_refs(path.read_text(encoding="utf-8"))
            if refs:
                actual[path.name] = dict(collections.Counter(r for _, r in refs))
        self.assertEqual(
            actual,
            KNOWN_UNPINNED,
            "third-party actions must be pinned as `uses: owner/name@<40-hex sha> # tag`; "
            "if a listed ref is now pinned, remove it from KNOWN_UNPINNED",
        )


if __name__ == "__main__":
    unittest.main()
