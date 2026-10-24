"""Audit 1 `blueprint-axis-count`: the live axis count belongs in the generated vocabulary
document, not in hand-written prose. The generated document itself is on this node's no-edit
list, so it gains the count line when its owner runs `vocab_check.py --write`; the freshness
check accepts it until then. The two prose spots the finding names sit in documents this node
may not edit either; the expectedFailure tests below turn into unexpected success (a failing
run) as soon as the document owners apply the replacement wording recorded in
docs/review/2026-10-22_audit1_blueprint_axis_count.md, which is the cue to delete the decorators.
"""
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import vocab_check as vc

BLUEPRINT = ROOT / "docs/BLUEPRINT.md"
PROPOSAL = ROOT / "docs/blueprint/proposals/인계_설계책임/README.md"
GENERATED = ROOT / "docs/blueprint/VOCABULARY.md"
REVIEW = ROOT / "docs/review/2026-10-22_audit1_blueprint_axis_count.md"

AXIS_COUNT = re.compile(r"(\d+)\s*개의?\s*축")
VOCAB_POINTER = re.compile(r"vocabulary|어휘", re.IGNORECASE)


def vocab():
    return json.loads((ROOT / "packages/schemas/vocabulary.json").read_text(encoding="utf-8"))


def stale_counts(path, n_axes):
    """(line, claimed) pairs where a vocabulary-pointer line states a wrong axis count."""
    found = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if "vocab:allow" in line or not VOCAB_POINTER.search(line):
            continue
        for m in AXIS_COUNT.finditer(line):
            if int(m.group(1)) != n_axes:
                found.append((i, int(m.group(1))))
    return found


class GeneratedDoc(unittest.TestCase):
    """The count lives where vocab_check.py writes it, so it cannot drift from vocabulary.json.

    The committed document predates the count line -- it is on this node's no-edit list, so the
    owner adds the line with `vocab_check.py --write`. Until then the freshness check must
    accept it, and whatever count it states must be the live one."""

    def setUp(self):
        self.v = vocab()
        self.n = len(self.v["axes"])
        self.doc = GENERATED.read_text(encoding="utf-8")

    def test_render_states_the_live_axis_count(self):
        self.assertIn(f"전체 {self.n}개 축.", vc.render(self.v))

    def test_committed_doc_is_fresh_for_the_check(self):
        self.assertEqual(vc.generated_doc_problems(self.doc, vc.render(self.v), self.n), [])

    def test_states_no_wrong_axis_count(self):
        wrong = [m.group(1) for m in AXIS_COUNT.finditer(self.doc) if int(m.group(1)) != self.n]
        self.assertEqual(wrong, [])


class EditableContractDocs(unittest.TestCase):
    def test_no_stale_axis_count_where_the_pipeline_can_fix_it(self):
        findings = [p for p in vc.lint(vocab()) if " axes, vocabulary.json has " in p]
        self.assertEqual(findings, [])


class ProtectedDocs(unittest.TestCase):
    """docs/BLUEPRINT.md and docs/blueprint/proposals/ are on this node's no-edit list."""

    def setUp(self):
        self.v = vocab()
        self.n = len(self.v["axes"])

    @unittest.expectedFailure
    def test_blueprint_174_drops_the_count(self):
        self.assertEqual(stale_counts(BLUEPRINT, self.n), [])

    @unittest.expectedFailure
    def test_proposal_readme_53_drops_the_count(self):
        self.assertEqual(stale_counts(PROPOSAL, self.n), [])

    @unittest.expectedFailure
    def test_no_protected_document_reports_a_stale_count(self):
        self.assertEqual(vc.stale_axis_count_notices(self.v), [])


class ReviewRecord(unittest.TestCase):
    def test_tracks_both_open_spots_and_the_replacement_wording(self):
        text = REVIEW.read_text(encoding="utf-8")
        for needle in ("docs/BLUEPRINT.md", "174", "인계_설계책임/README.md", "53",
                       "31", "미수정", "전체 축"):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
