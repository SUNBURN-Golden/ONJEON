"""Schema lint, vocabulary-only enums, generated files, fixtures.

  python3 -I -m unittest discover -s packages/schemas/codegen/tests
"""
import copy
import json
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import gen  # noqa: E402
import schema_model as sm  # noqa: E402
import validate  # noqa: E402

FIXTURES = HERE / "fixtures"
REQUIRED_TYPES = [
    "Assertion", "ReleaseManifest", "EvaluationResult", "ScenarioResult", "CoverageDetail", "CompareView",
    "PlanView", "EvidenceView", "NeedResult", "PremiumObservation", "ContractSnapshot", "ErrorResponse",
]


def copy_schemas(dst: Path) -> Path:
    """A scratch copy of the pieces the loader reads."""
    shutil.copytree(sm.JSON_DIR, dst / "json")
    shutil.copy(sm.VOCAB_PATH, dst / "vocabulary.json")
    shutil.copy(sm.SCHEMAS_DIR / "Cargo.toml", dst / "Cargo.toml")
    return dst


def edit(path: Path, fn):
    doc = json.loads(path.read_text(encoding="utf-8"))
    fn(doc)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class Lint(unittest.TestCase):
    def test_current_schemas_pass_the_lint(self):
        model = sm.build_model()
        self.assertEqual(model.errors, [])
        roots = {s.name for s in model.structs.values() if s.root}
        self.assertEqual(roots, set(REQUIRED_TYPES))

    def lint_errors(self, mutate, vocab_mutate=None):
        with tempfile.TemporaryDirectory() as t:
            d = copy_schemas(Path(t))
            mutate(d / "json")
            if vocab_mutate:
                edit(d / "vocabulary.json", vocab_mutate)
            return sm.build_model(d / "json", d / "vocabulary.json", strict=False).errors

    def test_every_enum_comes_only_from_the_vocabulary(self):
        vocab = sm.load_vocab()
        for path in sm.JSON_DIR.glob("*.schema.json"):
            text = path.read_text(encoding="utf-8")
            doc = json.loads(text)
            if path.name == sm.VOCAB_FILE:
                self.assertEqual(doc, sm.vocabulary_schema(vocab))
                continue
            self.assertNotIn('"enum"', text, f"{path.name} has its own enum")
            self.assertNotIn('"const"', text, f"{path.name} has a const")
            self.assertNotIn('"oneOf"', text)
            self.assertNotIn('"anyOf"', text)
        axes = {a["id"]: [v["code"] for v in a["values"]] for a in vocab["axes"]}
        defs = json.loads((sm.JSON_DIR / sm.VOCAB_FILE).read_text(encoding="utf-8"))["$defs"]
        subsets = {}
        for axis in vocab["axes"]:
            for name, codes in axis.get("subsets", {}).items():
                self.assertLessEqual(set(codes), set(axes[axis["id"]]))
                subsets[name] = codes
        self.assertEqual({k: v["enum"] for k, v in defs.items()}, axes | subsets)

    def test_every_vocabulary_reference_points_at_a_live_enum(self):
        vocab_ids = set(sm.vocabulary_enums(sm.load_vocab()))
        used = set()
        for path in sm.JSON_DIR.glob("*.schema.json"):
            used |= set(re.findall(r'vocabulary\.schema\.json#/\$defs/([a-z_]+)', path.read_text(encoding="utf-8")))
        self.assertTrue(used)
        self.assertLessEqual(used, vocab_ids)

    def test_enum_subsets_require_unique_existing_codes_and_names(self):
        for name, codes in (
            ("for_snapshot", ["invented"]),
            ("for_snapshot", ["private_policy", "private_policy"]),
            ("for_snapshot", []),
            ("sensitivity", ["private_policy"]),
        ):
            with self.subTest(name=name, codes=codes):
                vocab = sm.load_vocab()
                sensitivity = next(a for a in vocab["axes"] if a["id"] == "sensitivity")
                sensitivity["subsets"] = {name: codes}
                with self.assertRaisesRegex(sm.SchemaError, "enum subset"):
                    sm.vocabulary_schema(vocab)

    def test_an_enum_in_a_schema_is_a_lint_error(self):
        def add_enum(d):
            edit(d / "plan_view.schema.json", lambda doc: doc["properties"]["tab"].update({"enum": ["current", "proposal"]}))
        errors = self.lint_errors(add_enum)
        self.assertTrue(any("enum outside vocabulary.schema.json" in e for e in errors), errors)

    def test_a_hand_edited_vocabulary_schema_is_a_lint_error(self):
        def tamper(d):
            edit(d / sm.VOCAB_FILE, lambda doc: doc["$defs"]["tri"]["enum"].append("maybe"))
        errors = self.lint_errors(tamper)
        self.assertTrue(any("differs from packages/schemas/vocabulary.json" in e for e in errors), errors)

    def test_a_vocabulary_change_without_regeneration_is_a_lint_error(self):
        def add_value(v):
            next(a for a in v["axes"] if a["id"] == "tri")["values"].append({"code": "maybe", "concept_ko": "x", "screen_ko": "x", "deprecated_aliases": []})
        errors = self.lint_errors(lambda d: None, add_value)
        self.assertTrue(any("differs from packages/schemas/vocabulary.json" in e for e in errors), errors)

    def test_pending_axes_must_move_to_the_vocabulary_once_it_has_them(self):
        pending = {
            m for p in sm.JSON_DIR.glob("*.schema.json")
            for m in re.findall(r'"x-onjeon-pending-axis": "([a-z_]+)"', p.read_text(encoding="utf-8"))
        }
        self.assertIn("judged_by", pending)
        self.assertNotIn("need_verdict", pending, "need_verdict entered the vocabulary in 1.6.0 and must be a $ref")
        self.assertFalse(pending & {a["id"] for a in sm.load_vocab()["axes"]})

        def add_axis(v):
            v["axes"].append({"id": "judged_by", "name_ko": "x", "applies_to": "x", "layer": "x", "concept_ko": "x",
                              "values": [{"code": "engine", "concept_ko": "x", "screen_ko": "x", "deprecated_aliases": []}]})
        def regen(d):
            pass
        with tempfile.TemporaryDirectory() as t:
            d = copy_schemas(Path(t))
            edit(d / "vocabulary.json", add_axis)
            (d / "json" / sm.VOCAB_FILE).write_text(json.dumps(sm.vocabulary_schema(sm.load_vocab(d / "vocabulary.json")), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            errors = sm.build_model(d / "json", d / "vocabulary.json", strict=False).errors
        self.assertTrue(any("pending axis 'judged_by' now exists" in e for e in errors), errors)

    def test_inline_objects_unknown_keywords_and_open_structs_are_rejected(self):
        def inline(d):
            edit(d / "plan_view.schema.json", lambda doc: doc["properties"].update(
                {"extra": {"type": "object", "properties": {"a": {"type": "string"}}, "additionalProperties": False}}))
        self.assertTrue(any("inline object" in e for e in self.lint_errors(inline)))

        def keyword(d):
            edit(d / "plan_view.schema.json", lambda doc: doc["properties"]["synthetic"].update({"oneOf": []}))
        self.assertTrue(any("unsupported keyword 'oneOf'" in e for e in self.lint_errors(keyword)))

        def open_struct(d):
            edit(d / "plan_view.schema.json", lambda doc: doc.pop("additionalProperties"))
        self.assertTrue(any("additionalProperties: false" in e for e in self.lint_errors(open_struct)))

    def test_deprecated_names_are_not_used_as_field_names(self):
        vocab = sm.load_vocab()
        deprecated = {al for t in vocab["timestamps"] for al in t["deprecated_aliases"]}
        deprecated |= {al for a in vocab["axes"] for al in a.get("field_aliases", [])}
        fields = {f.name for s in sm.build_model().structs.values() for f in s.fields}
        self.assertEqual(fields & deprecated, set())
        # and the canonical names are used instead
        self.assertIn("effective_from", fields)
        self.assertIn("review_status", fields)

    def test_money_is_integer_krw(self):
        for st in sm.build_model().structs.values():
            for f in st.fields:
                if "krw" in f.name or f.name in ("raw_amount",):
                    self.assertEqual(f.type.kind, "integer", f"{st.name}.{f.name}")
        self.assertNotIn("float", json.dumps([p.read_text(encoding="utf-8") for p in sm.JSON_DIR.glob("*.json")]).lower())


class Readme(unittest.TestCase):
    def test_pending_axis_table_matches_the_schemas(self):
        model = sm.build_model()
        rows = {}
        for st in model.structs.values():
            for f in st.fields:
                t = f.type
                while t.item is not None:
                    t = t.item
                if t.pending_axis:
                    rows.setdefault(t.pending_axis, []).append(f"`{st.name}.{f.name}`")
        text = (sm.SCHEMAS_DIR / "README.md").read_text(encoding="utf-8")
        section = text.split("### 어휘 승격 대기 축", 1)[1].split("\n### ", 1)[0]
        entries = re.findall(r"^\| `([a-z_]+)` \| ([^|\n]+) \| (T-[A-Z]{2}-\d{2}) \|$", section, re.M)
        table = {axis: (fields, owner) for axis, fields, owner in entries}
        self.assertEqual(len(entries), len(table), "README repeats a pending axis")
        self.assertEqual(set(table), set(rows), "README table and schemas disagree on pending axes")

        bundle = sm.SCHEMAS_DIR.parents[1] / "docs/blueprint/proposals/설계검토_결과/tasks.json"
        owners = {}
        for task in json.loads(bundle.read_text(encoding="utf-8"))["tasks"]:
            for axis in task.get("vocabulary_axes", []):
                if axis not in rows:
                    continue
                self.assertNotIn(axis, owners, f"multiple assignments for {axis}")
                owners[axis] = task["id"]

        for axis, fields in rows.items():
            self.assertIn(axis, owners, f"no task owns pending axis {axis}")
            self.assertEqual(table[axis], (", ".join(sorted(fields)), owners[axis]), axis)


class Generated(unittest.TestCase):
    def test_generated_files_are_up_to_date(self):
        self.assertEqual(gen.stale(gen.expected_outputs()), [])

    def test_all_three_languages_carry_every_axis_and_type(self):
        model = sm.build_model()
        rust = (sm.SCHEMAS_DIR / "src/generated/vocabulary.rs").read_text(encoding="utf-8")
        rust_t = (sm.SCHEMAS_DIR / "src/generated/types.rs").read_text(encoding="utf-8")
        ts = (gen.TS_DIR / "vocabulary.ts").read_text(encoding="utf-8")
        ts_t = (gen.TS_DIR / "types.ts").read_text(encoding="utf-8")
        dart = (gen.DART_DIR / "lib/src/vocabulary.dart").read_text(encoding="utf-8")
        dart_t = (gen.DART_DIR / "lib/src/types.dart").read_text(encoding="utf-8")
        for axis in model.axes:
            n = sm.pascal(axis)
            self.assertIn(f"pub enum {n} ", rust)
            self.assertIn(f"export const {n} = [", ts)
            self.assertIn(f"enum {n} {{", dart)
        for name in model.structs:
            self.assertIn(f"pub struct {name} {{", rust_t)
            self.assertIn(f"export interface {name} {{", ts_t)
            self.assertIn(f"class {name} {{", dart_t)

    def test_dart_reserved_words_and_unknown_values(self):
        dart = (gen.DART_DIR / "lib/src/vocabulary.dart").read_text(encoding="utf-8")
        self.assertIn("trueValue('true')", dart)
        self.assertIn("falseValue('false')", dart)
        self.assertIn("throw FormatException('unknown tri: $code')", dart)
        ts = (gen.TS_DIR / "vocabulary.ts").read_text(encoding="utf-8")
        self.assertIn("throw new Error(`unknown tri:", ts)

    def test_generation_is_deterministic(self):
        a = gen.expected_outputs()
        b = gen.expected_outputs()
        self.assertEqual(a, b)

    def test_generated_files_say_they_are_generated(self):
        for path in gen.expected_outputs():
            if path.suffix in (".rs", ".ts", ".dart"):
                self.assertIn("@generated", path.read_text(encoding="utf-8").splitlines()[0], path)


class EvidenceRefs(unittest.TestCase):
    def setUp(self):
        self.defs = json.loads((sm.JSON_DIR / "common.schema.json").read_text(encoding="utf-8"))["$defs"]
        self.forms = {k: v["pattern"] for k, v in self.defs.items() if k.endswith("Ref") and k not in ("EvidenceRef", "AssumptionRef", "AmountSource")}

    def test_evidence_ref_is_exactly_the_union_of_the_forms(self):
        inner = [p[1:-1] for p in self.forms.values()]
        self.assertEqual(self.defs["EvidenceRef"]["pattern"], "^(?:" + "|".join(inner) + ")$")
        self.assertEqual(len(self.forms), 10)

    SAMPLES = {
        "SegmentRef": "seg:0123456789ab:p12-14:terms:seg-1.0",
        "ClauseRef": "clause:seg:0123456789ab:p12-14:terms:seg-1.0/art7#p12:docproc-text@1.0@10,20,30,40",
        "EditionRef": "ted:01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "PremiumRef": "premium:01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "AssertionRef": "assertion:01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "RuleEvidenceRef": "rule:fixture-rule-001@1#0123456789ab",
        "ObservationRef": "obs:src:org:life-x/web/1/2026-10-01T09:00:00Z/0123456789abcdef",
        "RawRef": "raw:sha256:" + "0123456789abcdef" * 4,
        "EvaluationRef": "eval:01ARZ3NDEKTSV4RRFFQ69G5FAV",
        "CriterionRef": "crit:public-stat@2",
    }

    def test_each_form_accepts_its_sample_and_only_its_sample(self):
        full = re.compile(self.defs["EvidenceRef"]["pattern"])
        for name, sample in self.SAMPLES.items():
            self.assertTrue(re.search(self.forms[name], sample), name)
            self.assertTrue(full.search(sample), name)
            for other, pat in self.forms.items():
                if other != name:
                    self.assertFalse(re.search(pat, sample), f"{name} sample matched {other}")

    def test_malformed_refs_are_rejected(self):
        full = re.compile(self.defs["EvidenceRef"]["pattern"])
        for bad in [
            "", "raw:sha256:abc", "ted:not-a-ulid", "ted:01ARZ3NDEKTSV4RRFFQ69G5FAI",  # I is not a ULID letter
            "clause:seg:0123456789ab:p1-2:terms:v1/art1", "premium:", "a:01ARZ3NDEKTSV4RRFFQ69G5FAV",
            "fixture", "hana_2601_3d#c_2_1_art1_1", "seg:xyz:p1-2:terms:v1", "rule:r@1#abc", "crit:slug",
        ]:
            self.assertFalse(full.search(bad), bad)

    def test_the_grammar_doc_lists_every_form(self):
        text = (sm.SCHEMAS_DIR / "evidence_ref.md").read_text(encoding="utf-8")
        for name in self.forms:
            self.assertIn(name, text)


class Fixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.v = validate.Validator()
        cls.docs = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted(FIXTURES.glob("*.fixture.json"))}

    def test_every_required_type_has_a_fixture(self):
        have = {n.split(".")[0] for n in self.docs}
        self.assertEqual(have, set(REQUIRED_TYPES))

    def test_all_fixtures_validate(self):
        for name, doc in self.docs.items():
            self.assertEqual(self.v.validate(doc, name.split(".")[0]), [], name)

    def test_results_for_the_manifest_release_use_its_engine(self):
        manifest = self.docs["ReleaseManifest.fixture.json"]
        for name, doc in self.docs.items():
            if doc.get("release_id") != manifest["release_id"]:
                continue
            if name.startswith("EvaluationResult."):
                result = doc
            elif name.startswith("ScenarioResult.") and "evaluation" in doc:
                result = doc["evaluation"]
            else:
                continue
            with self.subTest(fixture=name):
                self.assertEqual(result["engine_version"], manifest["engine_version"])
                self.assertIn(result["schema_version"], manifest["rule_schema_versions"])

    def test_fixtures_are_marked_test_only(self):
        # Every fixture that carries an origin is origin=fixture and none is accepted, without
        # exception. An accepted (comparison-eligible) observation cannot be origin=fixture
        # (chk_fixture_never_accepted), so that case is built in memory by the Rust tests from the
        # fully populated fixture; it is never stored as a file that looks like real data.
        with_origin = {name: doc for name, doc in self.docs.items() if "origin" in doc}
        self.assertEqual(set(with_origin), {
            "Assertion.relation.fixture.json", "Assertion.value.fixture.json",
            "PremiumObservation.full.fixture.json", "PremiumObservation.raw.fixture.json",
            "PremiumObservation.unavailable.fixture.json",
        })
        for name, doc in with_origin.items():
            self.assertEqual(doc["origin"], "fixture", name)
            self.assertNotEqual(doc["review_status"], "accepted", name)
        for name, doc in self.docs.items():
            self.assertFalse(doc.get("comparison_eligible", False), name)
        full = self.docs["PremiumObservation.full.fixture.json"]
        self.assertTrue(full["comparison_basis_id"].startswith("cb-fixture"))
        for key in (
            "conditions", "package_binding", "source_as_of", "payment_cycle", "product_ref",
            "sales_config_ref", "components", "effective_from", "effective_to", "source_revision",
        ):
            self.assertIn(key, full)  # the fully populated shape is what the Dart/TS builds exercise

    def broken(self, name, fn):
        doc = copy.deepcopy(self.docs[name])
        fn(doc)
        return self.v.validate(doc, name.split(".")[0])

    def test_contract_snapshot_accepts_only_policy_and_health_sensitivity(self):
        name = "ContractSnapshot.fixture.json"
        for value in ("private_policy", "private_health"):
            with self.subTest(value=value):
                self.assertEqual(self.broken(name, lambda doc: doc.update(sensitivity=value)), [])
        for value in ("public_product", "genetic_private", "unknown", None):
            with self.subTest(value=value):
                errors = self.broken(name, lambda doc: doc.update(sensitivity=value))
                self.assertTrue(any(error.startswith("$.sensitivity:") for error in errors), errors)
        self.assertEqual(self.broken(name, lambda doc: doc.pop("sensitivity")), [
            "$: missing required 'sensitivity'",
        ])

    def test_public_view_dependencies_reject_excluded_contracts(self):
        for name in ("CoverageDetail.fixture.json", "ScenarioResult.blocked.fixture.json",
                     "NeedResult.fixture.json"):
            with self.subTest(fixture=name):
                doc = copy.deepcopy(self.docs[name])
                container = doc["layers"][0]["lines"][0] if name.startswith("CoverageDetail") else doc
                container["dependency"] = {"dependency_state": "held", "unknown_overlap": []}
                root = name.split(".")[0]
                self.assertEqual(self.v.validate(doc, root), [])
                container["dependency"]["excluded_contracts"] = [self.docs["ContractSnapshot.fixture.json"]["id"]]
                errors = self.v.validate(doc, root)
                self.assertEqual(len(errors), 1, errors)
                self.assertTrue(errors[0].endswith(".dependency: unknown field 'excluded_contracts'"), errors)

    def test_view_lines_require_nonempty_evidence_refs(self):
        name = "CoverageDetail.fixture.json"
        line = lambda doc: doc["layers"][0]["lines"][0]
        self.assertEqual(
            self.broken(name, lambda doc: line(doc).pop("refs")),
            ["$.layers[0].lines[0]: missing required 'refs'"],
        )
        self.assertEqual(
            self.broken(name, lambda doc: line(doc).update(refs=[])),
            ["$.layers[0].lines[0].refs: fewer than minItems"],
        )

    def test_compare_cell_refs_are_nonempty_evidence_refs_when_present(self):
        name = "CompareView.fixture.json"
        cell = lambda doc: doc["axes"][0]["per_column"][0]
        self.assertEqual(
            self.broken(name, lambda doc: cell(doc).update(refs=[])),
            ["$.axes[0].per_column[0].refs: fewer than minItems"],
        )
        errors = self.broken(name, lambda doc: cell(doc).update(refs=["unresolved"]))
        self.assertTrue(any("$.axes[0].per_column[0].refs[0]" in error for error in errors), errors)

    def test_missing_required_unknown_field_bad_enum_bad_pattern_are_rejected(self):
        n = "Assertion.relation.fixture.json"
        self.assertTrue(any("missing required 'evidence'" in e for e in self.broken(n, lambda d: d.pop("evidence"))))
        self.assertTrue(any("unknown field" in e for e in self.broken(n, lambda d: d.update(extra=1))))
        self.assertTrue(any("vocabulary" in e for e in self.broken(n, lambda d: d.update(criticality="c9"))))
        self.assertTrue(any("does not match" in e for e in self.broken(n, lambda d: d.update(id="a:lowercase"))))
        self.assertTrue(any("fewer than minItems" in e for e in self.broken(n, lambda d: d.update(evidence=[]))))
        self.assertTrue(any("does not match" in e for e in self.broken(n, lambda d: d["evidence"][0].update(ref="fixture#local"))))
        # a deprecated field name from before the vocabulary rename is an unknown field
        self.assertTrue(any("unknown field" in e for e in self.broken(n, lambda d: d["time"].update(valid_from="2026-01-01"))))

    def test_retired_and_estimated_prices_are_rejected(self):
        n = "PremiumObservation.raw.fixture.json"
        for bad in ("estimated", "estimated_range"):
            self.assertTrue(self.broken(n, lambda d: d.update(price_basis=bad)), bad)
        self.assertTrue(self.broken(n, lambda d: d.update(raw_amount=51290.5)))
        self.assertTrue(self.broken(n, lambda d: d.update(raw_amount=-1)))

    def test_premium_amount_may_be_omitted_and_unknown_reason_must_be_non_blank_text(self):
        n = "PremiumObservation.unavailable.fixture.json"
        self.assertNotIn("raw_amount", self.docs[n])
        self.assertFalse(self.broken(
            "PremiumObservation.raw.fixture.json", lambda d: d.update(raw_amount=0),
        ))
        for bad in ("", " \t\n", 0, None):
            with self.subTest(reason=bad):
                errors = self.broken(n, lambda d: d.update(unknown_reason=bad))
                self.assertTrue(any("unknown_reason" in e for e in errors), errors)

    def test_premium_subject_and_period_field_shapes(self):
        n = "PremiumObservation.full.fixture.json"
        for key, bad in (
            ("product_ref", ""), ("product_ref", "display name"),
            ("sales_config_ref", "product:other"), ("coverage_ref", "rider label"),
            ("effective_from", "2026-6-29"), ("effective_to", "2026-09-30T00:00:00Z"),
            ("effective_open_ended", "true"), ("source_revision", "https://example.invalid/price"),
            ("components", []), ("components", [{}]),
        ):
            with self.subTest(field=key, value=bad):
                self.assertTrue(any(key in e for e in self.broken(n, lambda d: d.update({key: bad}))))
        for key, bad in (("cov_ref", "rider label"), ("insured_amount_krw", -1), ("insured_amount_krw", 1.5)):
            with self.subTest(component_field=key, value=bad):
                errors = self.broken(n, lambda d: d["components"][0].update({key: bad}))
                self.assertTrue(any(key in e for e in errors), errors)

    def test_money_must_be_integer_krw(self):
        n = "ScenarioResult.evaluated.fixture.json"
        self.assertTrue(self.broken(n, lambda d: d["explain"]["amounts"][0].update(krw=5000000.5)))
        self.assertTrue(self.broken(n, lambda d: d["explain"]["amounts"][0].update(source="free text")))

    def test_unknown_states_are_not_silently_accepted(self):
        n = "PlanView.fixture.json"
        self.assertTrue(self.broken(n, lambda d: d["groups"][0].update(plan_action="maybe")))
        self.assertTrue(self.broken(n, lambda d: d["groups"][0]["price_line"].update(price_unavailable_reason="because")))
        self.assertTrue(self.broken(n, lambda d: d["groups"][0]["price_line"].update(man=[1.0, 2.0, 3.0])))

    def test_pending_axes_are_closed_by_pattern_not_open_text(self):
        n = "NeedResult.fixture.json"
        self.assertTrue(self.broken(n, lambda d: d.update(verdict="Has Spaces")))
        n = "ErrorResponse.fixture.json"
        self.assertTrue(self.broken(n, lambda d: d.update(code="ONJ-XX-V-001")))
        self.assertTrue(self.broken(n, lambda d: d.update(error_class="v")))


if __name__ == "__main__":
    unittest.main()
