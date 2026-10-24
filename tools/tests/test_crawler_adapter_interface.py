"""CRAWL-04: pure adapter/validation tests. All synthetic data has origin=fixture.

No network, R2, environment files, wall-clock waits or random inputs are used.
MockAdapter deliberately lives here, never in the production crawler package.
"""
import ast
import dataclasses
import itertools
import json
import sys
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import urljoin

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import crawler  # noqa: E402
from crawler import validate as validation  # noqa: E402
from crawler.adapter import (AdapterRegistry, Classification, DiscoveryManifest, DocumentRef,  # noqa: E402
                             DuplicateAdapterError, SourceAdapter, UnknownAdapterError,
                             observation_metadata)
from crawler.config import CrawlerConfig, HARD_OBJECT_CAP_BYTES  # noqa: E402
from crawler.transport import BodyTooLargeError, Response, TransportError  # noqa: E402
from crawler.validate import (BodyStreamInfo, PREFIX_BYTES, RejectionReason as R,  # noqa: E402
                              validate_document)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "crawler"
PDF = (FIXTURES / "minimal.pdf").read_bytes()


class MockAdapter(SourceAdapter):
    """Parses only synthetic JSON marked origin=fixture; never performs I/O."""

    def discover(self, page_bytes, base_url):
        try:
            page = json.loads(page_bytes)
        except (UnicodeDecodeError, ValueError):
            return DiscoveryManifest([], "structure_changed", "unrecognized fixture listing")
        if not isinstance(page, dict) or page.get("origin") != "fixture":
            return DiscoveryManifest([], "structure_changed", "missing fixture structure")
        if page.get("blocked"):
            return DiscoveryManifest([], "blocked", "login required")
        if page.get("end") is not True or not isinstance(page.get("documents"), list):
            return DiscoveryManifest([], "structure_changed", "missing listing termination")
        docs = [DocumentRef(urljoin(base_url, row["url"]), row["kind"], row.get("title"))
                for row in page["documents"]]
        return DiscoveryManifest(docs, "complete" if docs else "empty_ok")

    def classify(self, response):
        if response.status in (401, 403, 429):
            return Classification("gap", f"http_{response.status}")
        if not 200 <= response.status < 300:
            return Classification("gap", "unexpected_http_status")
        return Classification("ok")


def listing(**overrides):
    page = {"origin": "fixture", "end": True, "documents": []}
    page.update(overrides)
    return json.dumps(page).encode("utf-8")


class AdapterContractTest(unittest.TestCase):
    def setUp(self):
        self.adapter = MockAdapter("fixture-source", "mock@1")

    def test_source_adapter_is_abstract_and_requires_both_operations(self):
        class IncompleteAdapter(SourceAdapter):
            def discover(self, page_bytes, base_url):
                return DiscoveryManifest([], "empty_ok")

        for cls in (SourceAdapter, IncompleteAdapter):
            with self.subTest(cls=cls), self.assertRaises(TypeError):
                cls("fixture-source", "1")

    def test_source_identity_and_version_required(self):
        for source_id, version in (("", "1"), (None, "1"), ("s", " "), ("s", 1)):
            with self.subTest(source_id=source_id, version=version), self.assertRaises(ValueError):
                MockAdapter(source_id, version)

    def test_discovery_resolves_document_refs(self):
        out = self.adapter.discover(listing(documents=[{
            "url": "policy.pdf", "kind": "pdf", "title": "Fixture policy",
        }]), "https://fixture.example/disclosure/")
        self.assertTrue(out.is_success)
        self.assertEqual(out.completeness, "complete")
        self.assertEqual(out.documents, (DocumentRef(
            "https://fixture.example/disclosure/policy.pdf", "pdf", "Fixture policy"),))
        self.assertIsNone(DocumentRef("https://fixture.example/untitled.pdf", "pdf").title)

    def test_empty_ok_is_explicit_success_and_errors_are_never_success(self):
        cases = (
            (listing(), "empty_ok", True),
            (listing(blocked=True), "blocked", False),
            (listing(end=False), "structure_changed", False),
            (b'{"origin":"fixture"}', "structure_changed", False),
            (b'<!-- origin=fixture --><html>login required</html>', "structure_changed", False),
        )
        for body, completeness, success in cases:
            with self.subTest(completeness=completeness, body=body):
                out = self.adapter.discover(body, "https://fixture.example/")
                self.assertEqual(out.completeness, completeness)
                self.assertEqual(out.is_success, success)
                self.assertFalse(out.documents)

    def test_partial_links_cannot_make_blocked_or_changed_listing_successful(self):
        for completeness in ("blocked", "structure_changed"):
            out = DiscoveryManifest([DocumentRef("https://fixture.example/a.pdf", "pdf")], completeness)
            self.assertFalse(out.is_success)
            self.assertEqual(len(out.documents), 1)

    def test_manifest_invariants_and_snapshot(self):
        doc = DocumentRef("https://fixture.example/a.pdf", "pdf")
        docs = [doc]
        manifest = DiscoveryManifest(docs, "complete")
        docs.clear()
        self.assertEqual(manifest.documents, (doc,))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            manifest.completeness = "empty_ok"
        for documents, completeness in (([], "complete"), ([doc], "empty_ok"),
                                        ([], "unknown"), (["a.pdf"], "complete")):
            with self.subTest(completeness=completeness), self.assertRaises(ValueError):
                DiscoveryManifest(documents, completeness)
        with self.assertRaises(ValueError):
            DiscoveryManifest([], "blocked", reason=" ")

    def test_document_ref_rejects_invalid_fields(self):
        for args in (("", "pdf"), ("a.pdf", ""), (None, "pdf"), ("a.pdf", "pdf", 1)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                DocumentRef(*args)

    def test_classification_leaves_body_unconsumed_and_gaps_have_reasons(self):
        def unread():
            raise AssertionError("classify must not consume the body")
            yield b""

        for status in (200, 206, 401, 403, 429, 302, 500):
            with self.subTest(status=status):
                result = self.adapter.classify(Response(status, {}, unread()))
                self.assertEqual(result.kind, "ok" if status in (200, 206) else "gap")
                if result.kind == "gap":
                    self.assertTrue(result.reason)
        for kind, reason in (("gap", None), ("gap", ""), ("ok", "bad"), ("unknown", None)):
            with self.subTest(kind=kind, reason=reason), self.assertRaises(ValueError):
                Classification(kind, reason)

    def test_metadata_versions_and_copies(self):
        expected = {"source_id": "fixture-source", "adapter_version": "mock@1",
                    "user_agent_version": crawler.__version__}
        self.assertEqual(observation_metadata(self.adapter), expected)
        custom = observation_metadata(self.adapter, "0.2.0")
        self.assertEqual(custom["user_agent_version"], "0.2.0")
        custom["adapter_version"] = "changed"
        self.assertEqual(observation_metadata(self.adapter), expected)
        with self.assertRaises(ValueError):
            observation_metadata(self.adapter, " ")
        with self.assertRaises(TypeError):
            observation_metadata(object())


class RegistryTest(unittest.TestCase):
    def test_exact_name_version_lookup_and_duplicate_rejection(self):
        class NextAdapter(MockAdapter):
            pass

        registry = AdapterRegistry()
        registry.register("mock", "1", MockAdapter)
        registry.register("mock", "2", NextAdapter)
        registry.register("other", "1", NextAdapter)
        self.assertIs(registry.resolve("mock", "1"), MockAdapter)
        self.assertIs(registry.resolve("mock", "2"), NextAdapter)
        self.assertIs(registry.resolve("other", "1"), NextAdapter)
        for cls in (MockAdapter, NextAdapter):
            with self.assertRaises(DuplicateAdapterError):
                registry.register("mock", "1", cls)
        self.assertIs(registry.resolve("mock", "1"), MockAdapter)
        for name, version in (("missing", "1"), ("mock", "3"), ("mock", "latest")):
            with self.subTest(name=name, version=version), self.assertRaises(UnknownAdapterError):
                registry.resolve(name, version)
        with self.assertRaises(UnknownAdapterError):
            AdapterRegistry().resolve("mock", "1")

    def test_registry_rejects_invalid_registrations_and_keys(self):
        registry = AdapterRegistry()
        for cls in (object, SourceAdapter, MockAdapter("s", "1"), None):
            with self.subTest(cls=cls), self.assertRaises(TypeError):
                registry.register("mock", "1", cls)
        for name, version in (("", "1"), ("mock", " "), (None, "1"), ("mock", 1)):
            with self.subTest(name=name, version=version):
                with self.assertRaises(ValueError):
                    registry.register(name, version, MockAdapter)
                with self.assertRaises(ValueError):
                    registry.resolve(name, version)


class DocumentValidationTest(unittest.TestCase):
    def check_reason(self, body, reason, declared_type="pdf", **info):
        chunks = [body] if isinstance(body, bytes) else body
        result = validate_document(BodyStreamInfo(iter(chunks), **info), declared_type)
        self.assertEqual(result.reason, reason)
        self.assertEqual(result.ok, reason is None)
        if reason is not None:
            self.assertIsInstance(result.reason, R)
        return result

    def test_minimal_valid_pdf_fixture_and_split_magic(self):
        self.assertIn(b"origin=fixture", PDF)
        self.assertTrue(PDF.startswith(b"%PDF-"))
        self.assertTrue(PDF.endswith(b"%%EOF\n"))
        for mime in (None, "application/pdf", " Application/PDF; charset=binary ",
                     "application/octet-stream", "binary/octet-stream"):
            with self.subTest(mime=mime):
                result = self.check_reason((PDF[i:i + 1] for i in range(len(PDF))), None,
                                           declared_type="application/pdf", content_type=mime,
                                           content_length=len(PDF))
                self.assertEqual(result.size_bytes, len(PDF))

    def test_doc_and_docx_signatures_and_mimes(self):
        # origin=fixture: signature samples, not full Office documents.
        for kind, mime, body in (
            ("doc", "application/msword", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1fixture"),
            ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
             b"PK\x03\x04fixture"),
        ):
            with self.subTest(kind=kind):
                self.check_reason(body, None, kind, content_type=mime)
                self.check_reason(PDF, R.MAGIC_MISMATCH, kind, content_type=mime)

    def test_zero_length_is_rejected_even_when_declared_nonzero(self):
        for body in ([], b"", [b"", b""]):
            with self.subTest(body=body):
                self.check_reason(body, R.EMPTY)
        self.check_reason([], R.EMPTY, content_length=10)

    def test_wrong_magic_and_conflicting_mime(self):
        for body in (b"%PD", b"not a PDF; origin=fixture", b"\xef\xbb\xbf%PDF-1.4"):
            with self.subTest(body=body):
                self.check_reason(body, R.MAGIC_MISMATCH, content_type="application/pdf")
        for mime in ("text/plain", "text/html", "application/msword", "image/png"):
            with self.subTest(mime=mime):
                self.check_reason(PDF, R.MIME_MISMATCH, content_type=mime)

    def test_login_error_and_challenge_html_are_not_documents(self):
        for marker, reason in (("login required", R.LOGIN_HTML), ("로그인이 필요합니다", R.LOGIN_HTML),
                               ('<input type="password">', R.LOGIN_HTML),
                               ("access denied", R.ERROR_HTML), ("internal server error", R.ERROR_HTML),
                               ("서비스 점검", R.ERROR_HTML), ("captcha", R.CHALLENGE_HTML),
                               ("verify you are human", R.CHALLENGE_HTML),
                               ("ordinary page", R.UNEXPECTED_HTML)):
            body = f"<!doctype html><!-- origin=fixture --><body>{marker}</body>".encode("utf-8")
            for kind in ("pdf", "doc", "docx"):
                for mime in (None, "text/html", "application/xhtml+xml", "application/pdf"):
                    with self.subTest(marker=marker, kind=kind, mime=mime):
                        self.check_reason((body[i:i + 3] for i in range(0, len(body), 3)), reason,
                                          kind, content_type=mime)

    def test_document_text_does_not_trigger_html_markers(self):
        self.check_reason(PDF + b"<html>login required captcha internal server error", None)

    def test_marker_inspection_is_bounded_but_stream_length_is_not(self):
        body = b"<html><!-- origin=fixture -->".ljust(PREFIX_BYTES, b" ") + b"captcha"
        self.check_reason(body, R.UNEXPECTED_HTML)
        with mock.patch.object(validation, "_prefix_rejection", wraps=validation._prefix_rejection) as check:
            result = self.check_reason(itertools.chain([PDF], itertools.repeat(b"x" * 65536, 20)), None)
            self.assertGreater(result.size_bytes, PREFIX_BYTES)
            self.assertEqual(len(check.call_args.args[0]), PREFIX_BYTES)

    def test_declared_oversize_does_not_read_the_stream(self):
        def unread():
            raise AssertionError("oversize Content-Length must be rejected before reading")
            yield b""

        self.check_reason(unread(), R.TOO_LARGE, content_length=HARD_OBJECT_CAP_BYTES + 1)

    def test_actual_hard_cap_and_boundary_with_reused_bounded_chunk(self):
        # origin=fixture: repeated shared chunk, no 64 MiB allocation.
        chunk = b"%PDF-" + b"x" * (65536 - 5)
        count = HARD_OBJECT_CAP_BYTES // len(chunk)
        result = self.check_reason(itertools.repeat(chunk, count), None)
        self.assertEqual(result.size_bytes, HARD_OBJECT_CAP_BYTES)
        for declared_length in (None, 1):
            body = itertools.chain(itertools.repeat(chunk, count), [b"x"])
            result = self.check_reason(body, R.TOO_LARGE, content_length=declared_length)
            self.assertEqual(result.size_bytes, HARD_OBJECT_CAP_BYTES + 1)

    def test_source_cap_can_only_lower_hard_cap_and_checks_actual_size(self):
        self.check_reason(PDF, None, object_cap_bytes=len(PDF))
        self.check_reason(PDF, R.TOO_LARGE, object_cap_bytes=len(PDF) - 1)
        self.check_reason([PDF, b"x"], R.TOO_LARGE, object_cap_bytes=len(PDF), content_length=1)
        for cap in (0, -1, True, 1.5, HARD_OBJECT_CAP_BYTES + 1):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                BodyStreamInfo([], object_cap_bytes=cap)

    def test_length_disagreement_and_invalid_metadata(self):
        for length in (0, 1, len(PDF) + 1):
            with self.subTest(length=length):
                self.check_reason(PDF, R.LENGTH_MISMATCH, content_length=length)
        for length in (-1, True, "100", 1.5):
            with self.subTest(length=length), self.assertRaises(ValueError):
                BodyStreamInfo([], content_length=length)
        with self.assertRaises(ValueError):
            BodyStreamInfo([], content_type=123)

    def test_stream_failures_never_count_as_success(self):
        for error, reason in ((BodyTooLargeError(), R.TOO_LARGE), (TransportError(), R.STREAM_ERROR),
                              (OSError(), R.STREAM_ERROR)):
            for first in (b"", PDF, PDF + b"x" * PREFIX_BYTES):
                def failing():
                    yield first
                    raise error

                with self.subTest(error=type(error), prefix_len=len(first)):
                    self.check_reason(failing(), reason)
        for invalid in ("text", None, bytearray(b"pdf")):
            with self.subTest(invalid=invalid):
                self.check_reason([PDF, invalid], R.INVALID_STREAM)

    def test_unknown_document_type_fails_closed(self):
        for kind in (None, "", "exe", "image/png"):
            with self.subTest(kind=kind):
                self.check_reason(PDF, R.UNSUPPORTED_TYPE, kind)
        with self.assertRaises(TypeError):
            validate_document(iter([PDF]), "pdf")

    def test_classify_ok_still_requires_document_validation(self):
        adapter = MockAdapter("fixture-source", "1")
        response = Response(200, {"Content-Type": "application/pdf"},
                            iter([b"<html><!-- origin=fixture -->login required</html>"]))
        self.assertEqual(adapter.classify(response).kind, "ok")
        result = validate_document(BodyStreamInfo(response.body_iter, response.headers["content-type"]), "pdf")
        self.assertEqual(result.reason, R.LOGIN_HTML)


class NodeSafetyTest(unittest.TestCase):
    def test_new_production_modules_are_pure_and_add_no_fetch_paths(self):
        root = Path(__file__).resolve().parent.parent / "crawler"
        allowed_imports = {"abc", "inspect", "dataclasses", "typing", "enum"}
        forbidden_calls = {"open", "read_bytes", "read_text", "write_bytes", "write_text", "request",
                           "fetch", "connect", "urlopen", "getenv", "sleep", "system", "popen"}
        for name in ("adapter.py", "validate.py"):
            tree = ast.parse((root / name).read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    self.assertLessEqual({a.name for a in node.names}, allowed_imports, name)
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    self.assertIn(node.module, allowed_imports, name)
                elif isinstance(node, ast.ImportFrom):
                    self.assertIn(node.module, (None, "config", "transport"), name)
                elif isinstance(node, ast.Call):
                    called = getattr(node.func, "attr", getattr(node.func, "id", ""))
                    self.assertNotIn(called, forbidden_calls, f"{name}:{node.lineno}")
        self.assertFalse(CrawlerConfig().network_enabled)
        self.assertNotIn("class MockAdapter", (root / "adapter.py").read_text())


if __name__ == "__main__":
    unittest.main()
