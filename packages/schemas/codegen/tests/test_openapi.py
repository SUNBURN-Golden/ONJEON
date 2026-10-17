"""OpenAPI v1 (public, personal, console): lint, release_id, cache headers, skeleton non-exposure, fixtures.

  python3 -I -m unittest discover -s packages/schemas/codegen/tests
"""
import copy
import json
import re
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

import emit_api  # noqa: E402
import gen  # noqa: E402
import openapi_model as om  # noqa: E402
import schema_model as sm  # noqa: E402
import validate  # noqa: E402

API_FIXTURES = HERE / "api_fixtures"
# model-vendor names are assembled from pieces so this file does not itself contain them
MODEL_ID = re.compile("|".join(["cl" + "aude-", "gp" + "t-", "gem" + "ini-", "anthr" + "opic", "open" + "ai"]), re.I)
LEAK = re.compile("|".join(["/work" + "space", "/ho" + "me/", "/Users/", "AKIA[0-9A-Z]{12}", "sk-[A-Za-z0-9]{16}", "BEGIN [A-Z ]*PRIVATE KEY"]))

# SYSTEM_CONTRACT §10 and 02_구현계약 §2.1-2.3 (as drafted in this task)
EXPECTED_PUBLIC = {
    ("get", "/v1/releases/current"), ("get", "/v1/products"), ("get", "/v1/coverages/{cov_id}"),
    ("post", "/v1/comparisons"), ("post", "/v1/scenarios"), ("get", "/v1/evidence/{ref}"),
    ("post", "/v1/need-assessments"), ("get", "/v1/criteria/{id}"), ("get", "/v1/criteria-releases/current"),
    ("get", "/v1/coverage-status"), ("get", "/v1/gaps"), ("post", "/v1/error-reports"),
}
EXPECTED_PERSONAL = {
    ("post", "/v1/auth/sessions"), ("delete", "/v1/auth/sessions/current"), ("get", "/v1/me"),
    ("get", "/v1/me/export"), ("delete", "/v1/me/data"), ("get", "/v1/me/deletion-jobs/{id}"), ("post", "/v1/consents"),
    ("delete", "/v1/consents/{id}"), ("post", "/v1/profiles"), ("get", "/v1/profiles/{id}"),
    ("post", "/v1/policy-imports"), ("get", "/v1/policy-imports/{id}"), ("post", "/v1/policy-imports/{id}/confirm"),
    ("post", "/v1/family-history"), ("post", "/v1/evaluations"), ("get", "/v1/evaluations/{id}"),
    ("post", "/v1/me/need-assessments"), ("post", "/v1/me/assumptions"), ("post", "/v1/plans"),
    ("get", "/v1/plans/{id}"), ("post", "/v1/plans/{id}/diff"),
}
EXPECTED_SKELETON = {("post", "/v1/consultation-requests"), ("post", "/v1/quote-requests")}
CONSOLE_RESOURCES = {
    "sources", "denominator", "changes", "review-queue", "impact", "releases", "quality", "audit-log",
    "policy", "gaps", "acquisition-tasks", "deletion-jobs", "cost",
}


def routes(doc):
    return {(m, p) for p, m, _ in om.iter_operations(doc)}


class Spec(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = om.load_docs()
        cls.am = om.build()

    def test_documents_pass_the_lint(self):
        self.assertEqual(self.am.errors, [])

    def test_the_drafted_routes_are_exactly_the_contract_routes(self):
        self.assertEqual(routes(self.docs["public"]), EXPECTED_PUBLIC)
        self.assertEqual(routes(self.docs["personal"]), EXPECTED_PERSONAL | EXPECTED_SKELETON)
        console = routes(self.docs["console"])
        self.assertEqual({p.split("/")[3] for _, p in console}, CONSOLE_RESOURCES)
        self.assertTrue(all(p.startswith("/console/v1/") for _, p in console))

    def test_console_has_no_send_or_approve_route(self):
        for m, p in routes(self.docs["console"]):
            self.assertNotRegex(p, r"send|approve|publish|dispatch", p)
        self.assertEqual({m for m, p in routes(self.docs["console"]) if p == "/console/v1/policy"}, {"get", "put"})
        # the only write is the policy change, restricted to the policy owner
        writes = [(m, p) for m, p in routes(self.docs["console"]) if m != "get"]
        self.assertEqual(writes, [("put", "/console/v1/policy")])
        put = self.docs["console"]["paths"]["/console/v1/policy"]["put"]
        self.assertEqual(put["x-onjeon-roles"], ["policy_owner"])
        self.assertTrue(self.docs["console"]["x-onjeon-requires-2fa"])

    def test_every_success_body_requires_release_id_independently_of_the_lint(self):
        for o in self.am.ops:
            st = self.am.model.structs[o.response]
            f = next(x for x in st.fields if x.name == "release_id")
            self.assertTrue(f.required, o.id)
            self.assertEqual(f.type.kind, "string", o.id)
        # every response also carries the echo header (errors: only when a release is known)
        for surface, doc in self.docs.items():
            for _, _, o in om.iter_operations(doc):
                self.assertIn("X-Onjeon-Release-Id", o["responses"]["200"]["headers"], o["operationId"])

    def test_personal_and_console_responses_forbid_a_public_cache(self):
        for surface in ("personal", "console"):
            doc = self.docs[surface]
            self.assertEqual(doc["x-onjeon-cache-policy"]["public_cache"], "forbidden")
            self.assertEqual(doc["components"]["headers"]["CacheControl"]["schema"]["enum"], [om.PRIVATE_CACHE])
            for _, _, o in om.iter_operations(doc):
                self.assertNotIn("x-onjeon-cache-key", o, o["operationId"])
                for code, resp in o["responses"].items():
                    hdrs = om.response_headers(doc, resp)
                    ref = hdrs["Cache-Control"]["$ref"]
                    self.assertEqual(ref, "#/components/headers/CacheControl", f"{o['operationId']} {code}")
            for name in doc["components"]["responses"]:
                hdrs = doc["components"]["responses"][name]["headers"]
                self.assertEqual(hdrs["Cache-Control"]["$ref"], "#/components/headers/CacheControl", name)
        for o in self.am.ops:
            if o.surface != "public":
                self.assertEqual(o.cache, "private_no_store", o.id)

    def test_only_public_gets_are_publicly_cacheable_and_keyed_by_release(self):
        for o in self.am.ops:
            if o.surface != "public":
                continue
            if o.method == "GET":
                self.assertEqual(o.cache, "public_keyed", o.id)
                self.assertIn("release_id", o.cache_key, o.id)
            else:
                self.assertEqual(o.cache, "no_store", o.id)
        comparisons = next(o for o in self.am.ops if o.id == "create_comparison")
        self.assertIn("comparison_basis_id", comparisons.cache_key)

    def test_calculation_and_upload_requests_carry_an_idempotency_key(self):
        for op_id in ("create_scenario", "create_need_assessment", "create_policy_import", "create_evaluation",
                      "create_personal_need_assessment", "create_plan"):
            o = next(x for x in self.am.ops if x.id == op_id)
            st = self.am.model.structs[o.request]
            f = next((x for x in st.fields if x.name == "idempotency_key"), None)
            self.assertIsNotNone(f, op_id)
            self.assertTrue(f.required, op_id)

    def test_the_pdf_password_is_only_a_form_field_and_the_binary_part_is_not_a_type_field(self):
        form = self.am.model.structs["PolicyImportForm"]
        self.assertEqual([f.name for f in form.fields], ["profile_id", "idempotency_key", "password"])
        for surface in ("public", "console"):
            self.assertNotIn("password", json.dumps(self.docs[surface]))
        for name, st in self.am.model.structs.items():
            if name != "PolicyImportForm" and name != "SessionRequest":
                self.assertNotIn("password", [f.name for f in st.fields], name)

    def test_no_personal_or_health_field_names_in_public_or_console(self):
        banned = re.compile(r"resident|ssn|phone|email|birth|health|diagnos|name_ko|real_name|genetic|dna", re.I)
        for surface in ("public", "console"):
            for name, st in ((s.name, s) for s in self.am.structs_of(surface)):
                for f in st.fields:
                    self.assertNotRegex(f.name, banned, f"{surface}.{name}.{f.name}")

    def test_documents_hold_no_secret_path_or_model_identifier(self):
        for p in sorted(om.OPENAPI_DIR.glob("*.yaml")):
            text = p.read_text(encoding="utf-8")
            self.assertIsNone(LEAK.search(text), p.name)
            self.assertIsNone(MODEL_ID.search(text), p.name)


class Mutations(unittest.TestCase):
    """The lint must fail when the property it guards is removed."""

    @classmethod
    def setUpClass(cls):
        cls.docs = om.load_docs()

    def errors(self, mutate):
        docs = copy.deepcopy(self.docs)
        mutate(docs)
        return om.build(docs).errors

    def test_a_body_without_release_id_fails(self):
        def m(d):
            st = d["public"]["components"]["schemas"]["GapListResponse"]
            del st["properties"]["release_id"]
            st["required"].remove("release_id")
        self.assertTrue(any("no required release_id" in e for e in self.errors(m)))

    def test_an_optional_release_id_fails(self):
        def m(d):
            d["public"]["components"]["schemas"]["GapListResponse"]["required"].remove("release_id")
        self.assertTrue(any("no required release_id" in e for e in self.errors(m)))

    def test_a_missing_echo_header_fails(self):
        def m(d):
            del d["public"]["paths"]["/v1/gaps"]["get"]["responses"]["200"]["headers"]["X-Onjeon-Release-Id"]
        self.assertTrue(any("X-Onjeon-Release-Id" in e for e in self.errors(m)))

    def test_a_public_cache_header_on_a_personal_response_fails(self):
        def m(d):
            d["personal"]["components"]["headers"]["CacheControl"]["schema"] = {"type": "string", "enum": ["public, max-age=60"]}
        errs = self.errors(m)
        self.assertTrue(any("must pin Cache-Control" in e for e in errs), errs)

    def test_a_personal_response_without_cache_control_fails(self):
        def m(d):
            del d["personal"]["paths"]["/v1/me"]["get"]["responses"]["200"]["headers"]["Cache-Control"]
        self.assertTrue(any("must declare a resolvable Cache-Control" in e for e in self.errors(m)))

    def test_dropping_the_forbidden_directive_list_fails(self):
        def m(d):
            d["personal"]["x-onjeon-cache-policy"]["forbidden_directives"].remove("s-maxage")
        self.assertTrue(any("'s-maxage'" in e for e in self.errors(m)))

    def test_a_cache_key_on_a_personal_operation_fails(self):
        def m(d):
            d["personal"]["paths"]["/v1/me"]["get"]["x-onjeon-cache-key"] = ["release_id"]
        self.assertTrue(any("no public cache" in e for e in self.errors(m)))

    def test_a_public_get_that_is_not_cacheable_or_not_keyed_fails(self):
        def m(d):
            d["public"]["paths"]["/v1/gaps"]["get"]["x-onjeon-cache-key"] = ["about"]
        self.assertTrue(any("cache key must include release_id" in e for e in self.errors(m)))

        def m2(d):
            d["public"]["paths"]["/v1/gaps"]["get"]["responses"]["200"]["headers"]["Cache-Control"] = {"$ref": "#/components/headers/CacheControlNoStore"}
        self.assertTrue(any("publicly cacheable" in e for e in self.errors(m2)))

    def test_a_skeleton_operation_must_be_flagged_and_off(self):
        def m(d):
            del d["personal"]["paths"]["/v1/quote-requests"]["post"]["x-onjeon-flag-default"]
        self.assertTrue(any("x-onjeon-flag-default: false" in e for e in self.errors(m)))

        def m2(d):
            d["personal"]["paths"]["/v1/quote-requests"]["post"]["x-onjeon-flag-default"] = True
        self.assertTrue(any("x-onjeon-flag-default: false" in e for e in self.errors(m2)))

    def test_an_unmarked_skeleton_route_fails(self):
        def m(d):
            del d["personal"]["paths"]["/v1/quote-requests"]["post"]["x-onjeon-skeleton"]
        self.assertTrue(any("without x-onjeon-skeleton" in e for e in self.errors(m)))

    def test_a_skeleton_route_in_the_public_document_fails(self):
        def m(d):
            d["public"]["paths"]["/v1/gaps"]["get"]["x-onjeon-skeleton"] = True
        self.assertTrue(any("belong to the personal document" in e for e in self.errors(m)))

    @staticmethod
    def open_snake_strings(docs):
        """(document, schema, property, description) of every open snake_case string (pattern only, no $ref)."""
        snake = "^[a-z][a-z0-9_]*$"
        for name, doc in docs.items():
            for sname, s in doc["components"]["schemas"].items():
                for pname, ps in s.get("properties", {}).items():
                    if ps.get("pattern") == snake or (ps.get("items") or {}).get("pattern") == snake:
                        yield name, sname, pname, ps.get("description", "")

    def promoted_axis_clashes(self, docs):
        axes = {a["id"]: {v["code"] for v in a["values"]} for a in sm.load_vocab()["axes"]}
        out = []
        for doc, sname, pname, desc in self.open_snake_strings(docs):
            words = set(re.findall(r"[a-z][a-z0-9_]+", desc))
            if pname in axes:
                out.append(f"{doc}.{sname}.{pname}: the vocabulary has axis '{pname}'")
            out += [f"{doc}.{sname}.{pname}: candidates are the values of axis '{a}'" for a, codes in axes.items() if len(words) >= 2 and words <= codes]
        return out

    def test_open_strings_do_not_cover_an_axis_the_vocabulary_now_has(self):
        self.assertEqual(self.promoted_axis_clashes(self.docs), [])

    def test_the_promotion_check_catches_confirm_party_as_an_open_string(self):
        docs = copy.deepcopy(self.docs)
        docs["personal"]["components"]["schemas"]["UnresolvedFact"]["properties"]["confirm_party"] = {
            "type": "string", "pattern": "^[a-z][a-z0-9_]*$", "description": "확인 주체(어휘 승격 대기)"}
        self.assertTrue(any("confirm_party" in e for e in self.promoted_axis_clashes(docs)))

    def test_an_unknown_enum_reference_is_a_lint_error(self):
        def m(d):
            d["public"]["components"]["schemas"]["ProductListItem"]["properties"]["sale_status"] = {"$ref": "../json/vocabulary.schema.json#/$defs/no_such_axis"}
        self.assertTrue(self.errors(m))

    def test_an_inline_enum_in_a_component_is_a_lint_error(self):
        def m(d):
            d["public"]["components"]["schemas"]["GapItem"]["properties"]["task_state"] = {"type": "string", "enum": ["a", "b"]}
        self.assertTrue(any("enum outside vocabulary" in e for e in self.errors(m)))

    def test_duplicate_operation_ids_and_routes_fail(self):
        def m(d):
            d["public"]["paths"]["/v1/gaps"]["get"]["operationId"] = "list_products"
        self.assertTrue(any("also used by" in e for e in self.errors(m)))

        def m2(d):
            d["console"]["paths"]["/v1/gaps"] = d["public"]["paths"]["/v1/gaps"]
        errs = self.errors(m2)
        self.assertTrue(any("must start with /console/v1/" in e for e in errs), errs)


class Skeleton(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs = om.load_docs()
        cls.am = om.build()
        cls.out = emit_api.emit(cls.am, "0.0.0")
        cls.skel_ops = [o for o in cls.am.ops if o.skeleton]

    def test_exactly_the_reserved_features_are_skeleton_and_all_flags_are_off(self):
        self.assertEqual({(o.method.lower(), o.path) for o in self.skel_ops}, EXPECTED_SKELETON)
        for o in self.skel_ops:
            spec = self.docs["personal"]["paths"][o.path][o.method.lower()]
            self.assertIs(spec["x-onjeon-skeleton"], True)
            self.assertIs(spec["x-onjeon-flag-default"], False)
            self.assertEqual(spec["tags"], ["skeleton"])
        self.assertEqual({o.flag for o in self.skel_ops}, {"consultation_enabled", "quotes_enabled"})

    def tokens(self):
        toks = set()
        for o in self.skel_ops:
            toks |= {o.id, o.path, o.flag, o.request, o.response}
            toks |= {sm.pascal(o.id)}
        toks |= self.am.skeleton_only
        toks.discard(None)
        return toks

    def test_skeleton_only_types_are_exactly_the_ones_no_default_operation_reaches(self):
        self.assertEqual(self.am.skeleton_only, {
            "ConsultationRequestCreate", "ConsultationRequestReceipt", "QuoteRequestCreate", "QuoteRequestReceipt"})

    def test_default_generated_surface_never_names_a_skeleton_thing(self):
        toks = self.tokens()
        self.assertGreaterEqual(len(toks), 8)
        default_files = {
            "rust/operations.rs": self.out["rust"]["operations.rs"].split("#[cfg(feature = \"skeleton\")]")[0],
            "ts/types.ts": self.out["ts"]["types.ts"], "ts/operations.ts": self.out["ts"]["operations.ts"],
            "ts/index.ts": self.out["ts"]["index.ts"], "dart/types": self.out["dart"]["lib/src/types.dart"],
            "dart/operations": self.out["dart"]["lib/src/operations.dart"], "dart/lib": self.out["dart"]["lib/onjeon_api.dart"],
        }
        types_rs = self.out["rust"]["types.rs"]
        # Rust types: every skeleton struct is cfg-gated; remove the gated items and nothing is left
        gated = re.sub(r'(?:///[^\n]*\n)*#\[cfg\(feature = "skeleton"\)\]\n#\[derive[^\n]*\]\npub struct \w+ \{.*?\n\}\n\n?', "", types_rs, flags=re.S)
        default_files["rust/types.rs"] = gated
        for fname, text in default_files.items():
            for t in toks:
                self.assertNotIn(t, text, f"{fname} leaks skeleton token {t!r}")

    def test_every_skeleton_item_is_gated_and_the_skeleton_files_are_not_exported(self):
        rs_ops = self.out["rust"]["operations.rs"]
        self.assertEqual(rs_ops.count('#[cfg(feature = "skeleton")]'), 1)
        self.assertIn('#[cfg(feature = "skeleton")]\npub const SKELETON_OPERATIONS', rs_ops)
        types_rs = self.out["rust"]["types.rs"]
        for name in self.am.skeleton_only:
            idx = types_rs.index(f"pub struct {name} {{")
            self.assertTrue(types_rs[:idx].rstrip().endswith('#[cfg(feature = "skeleton")]\n#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]'), name)
        self.assertEqual(types_rs.count('#[cfg(feature = "skeleton")]'), len(self.am.skeleton_only))
        self.assertNotIn("skeleton", self.out["ts"]["index.ts"])
        self.assertNotIn("skeleton", self.out["dart"]["lib/onjeon_api.dart"])
        self.assertIn("skeletonOperations", self.out["ts"]["skeleton.ts"])
        self.assertIn("skeletonOperations", self.out["dart"]["lib/src/skeleton.dart"])
        # tsconfig lists skeleton.ts so it is type-checked, but only index.ts is the entry point
        self.assertEqual(json.loads(self.out["ts"]["package.json"])["types"], "index.ts")
        # the Cargo feature is off by default
        cargo = (sm.SCHEMAS_DIR.parent / "api-types" / "Cargo.toml").read_text(encoding="utf-8")
        self.assertRegex(cargo, r"(?m)^default = \[\]$")
        self.assertRegex(cargo, r"(?m)^skeleton = \[\]$")

    def test_leak_static_check_skeleton_tokens_stay_inside_skeleton_operations(self):
        """Delete the skeleton operations and their schemas from the personal document: no token may remain
        anywhere in the three documents. The same tokens may not appear in other hand-written product files."""
        toks = self.tokens()
        docs = copy.deepcopy(self.docs)
        paths = docs["personal"]["paths"]
        for o in self.skel_ops:
            del paths[o.path]
        for name in self.am.skeleton_only:
            del docs["personal"]["components"]["schemas"][name]
        for surface, doc in docs.items():
            text = json.dumps(doc, ensure_ascii=False)
            for t in toks:
                if t.startswith("ConsultationRequest") or t.startswith("QuoteRequest") or t.startswith("create_") or t.startswith("/v1/") \
                        or t.endswith("_enabled"):
                    self.assertNotIn(t, text, f"{surface} document leaks skeleton token {t!r} outside its skeleton operation")
        root = sm.SCHEMAS_DIR.parent
        hand_written = [root / "api-types" / "src" / "lib.rs", root / "api-types" / "src" / "checks.rs"]
        for p in hand_written:
            text = p.read_text(encoding="utf-8")
            for t in ("consultation", "quote-requests", "quotes_enabled", "ConsultationRequest", "QuoteRequest"):
                self.assertNotIn(t, text, f"{p.name} names skeleton token {t!r}")

    def test_skeleton_types_do_not_collect_user_data_for_future_features(self):
        for name in ("ConsultationRequestCreate", "QuoteRequestCreate"):
            fields = [f.name for f in self.am.model.structs[name].fields]
            self.assertEqual(fields, ["profile_id", "idempotency_key"], name)


class Generated(unittest.TestCase):
    def test_api_outputs_are_up_to_date_and_say_they_are_generated(self):
        out = gen.api_outputs()
        self.assertEqual(gen.stale(gen.expected_outputs()), [])
        for path, text in out.items():
            if path.suffix in (".rs", ".ts", ".dart"):
                self.assertIn("@generated", text.splitlines()[0], path)
        self.assertEqual(out, gen.api_outputs())  # deterministic

    def test_every_default_operation_and_api_type_is_in_all_three_languages(self):
        am = om.build()
        out = emit_api.emit(am, "0.0.0")
        for o in am.ops:
            if o.skeleton:
                continue
            for text in (out["rust"]["operations.rs"], out["ts"]["operations.ts"], out["dart"]["lib/src/operations.dart"]):
                self.assertIn(f'"{o.id}"', text)
        for st in am.api_structs:
            if st.name in am.skeleton_only:
                continue
            self.assertIn(f"pub struct {st.name} {{", out["rust"]["types.rs"])
            self.assertIn(f"export interface {st.name} {{", out["ts"]["types.ts"])
            self.assertIn(f"class {st.name} {{", out["dart"]["lib/src/types.dart"])

    def test_contract_types_are_not_redefined_by_the_api_crate(self):
        am = om.build()
        contract = {n for n, s in am.model.structs.items() if not s.file.startswith("api_")}
        api = {s.name for s in am.api_structs}
        self.assertEqual(contract & api, set())
        self.assertIn("ScenarioResult", contract)
        self.assertNotIn("pub struct ScenarioResult", gen.api_outputs()[gen.API_RUST_DIR / "types.rs"])


class ApiFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.am = om.build()
        cls.v = validate.Validator.__new__(validate.Validator)
        errs = []
        cls.v.files = sm.read_schema_files(sm.JSON_DIR)
        cls.v.files.update(om.pseudo_files(cls.am.docs, errs))
        cls.docs = {p.name: json.loads(p.read_text(encoding="utf-8")) for p in sorted(API_FIXTURES.glob("*.fixture.json"))}
        cls.where = {}
        for st in cls.am.api_structs:
            cls.where[st.name] = st.file

    def check(self, doc, type_name):
        errors = []
        ref = f"{self.where[type_name]}#/$defs/{type_name}"
        self.v._check(doc, {"$ref": ref}, "", "$", errors)
        return errors

    def test_fixtures_exist_and_validate(self):
        self.assertGreaterEqual(len(self.docs), 8)
        for name, doc in self.docs.items():
            self.assertEqual(self.check(doc, name.split(".")[0]), [], name)

    def test_fixtures_are_test_only_and_use_no_real_looking_data(self):
        for name, doc in self.docs.items():
            text = json.dumps(doc)
            self.assertIsNone(LEAK.search(text), name)
            self.assertNotIn("http", text, name)
        self.assertTrue(all(n.endswith(".fixture.json") for n in self.docs))

    def test_broken_documents_are_rejected(self):
        base = self.docs["CurrentReleaseResponse.fixture.json"]
        d = copy.deepcopy(base)
        del d["release_id"]
        self.assertTrue(any("missing required 'release_id'" in e for e in self.check(d, "CurrentReleaseResponse")))
        d = copy.deepcopy(base)
        d["release_id"] = "release-1"
        self.assertTrue(any("does not match" in e for e in self.check(d, "CurrentReleaseResponse")))
        d = copy.deepcopy(base)
        d["extra"] = 1
        self.assertTrue(any("unknown field" in e for e in self.check(d, "CurrentReleaseResponse")))
        d = copy.deepcopy(self.docs["ProductListResponse.fixture.json"])
        d["items"][0]["sale_status"] = "on_sale_maybe"
        self.assertTrue(any("vocabulary" in e for e in self.check(d, "ProductListResponse")))
        d = copy.deepcopy(self.docs["ReleaseListResponse.fixture.json"])
        d["items"][0]["created_at"] = "yesterday"
        self.assertTrue(self.check(d, "ReleaseListResponse"))

    def test_money_in_api_requests_is_integer_won_and_there_are_no_float_money_fields(self):
        floats = sorted(f"{s.name}.{f.name}" for s in self.am.api_structs for f in s.fields if f.type.kind == "number")
        # bounding-box coordinates are the only non-integer numbers; money is Krw
        self.assertEqual(floats, sorted(f"{n}.{c}" for n in ("SourceRegion", "ReviewRegion") for c in ("x0", "y0", "x1", "y1")))
        plan = self.am.model.structs["PlanCreateRequest"]
        budget = next(f for f in plan.fields if f.name == "budget_krw")
        self.assertEqual(budget.type.kind, "integer")


if __name__ == "__main__":
    unittest.main()
