"""Tests for tools/html_content_hash.py (rule html-visible-text-v1).

The fixture is synthetic. When ONJEON_ARCHIVE_RAW points at a local raw store (file layout of
tools/source_archive.py), the same properties are also checked on the archived KB original and its
refetch. Run: python3 -m unittest discover -s tools/tests
"""
import hashlib
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import html_content_hash as h  # noqa: E402

FIXTURE = (Path(__file__).parent / "fixtures/disclosure_page.html").read_bytes()
HOST = "www.kbinsure.co.kr"
KB_ORIGINAL = "6ade7ccbb07bfa9ae002ec686131167fa308e6a2d0b7730d85b34698b13ed0b2"
KB_REFETCH = "f6dff4a742ed43bcf94a44513ee57c3b810cdb67b3117b1f06fc869945ab4723"


def ch(raw):
    return h.content_sha256(raw, HOST)


def sub(old, new, raw=FIXTURE):
    assert old.encode() in raw, old
    return raw.replace(old.encode(), new.encode(), 1)


class MeaningfulChangesChangeTheHash(unittest.TestCase):
    cases = {
        "title": ("간병인 지원비용 |", "간병인 지원비용 변경 |"),
        "product name": ("상해입원일당(1일이상)", "상해입원일당(181일이상)"),
        "effective date": ("적용일: 2026-07-01", "적용일: 2026-08-01"),
        "price": ("147,000원", "149,000원"),
        "payout condition": ("180일 한도", "120일 한도"),
        "linked document": ("25465_2_1.pdf", "25465_3_1.pdf"),
        "table row": ("<tr><td>2024-04-01~2026-06-30</td><td>144,000원</td></tr>", ""),
        "un-hidden column": ("<!-- <th>나이</th> -->", "<th>나이</th>"),
    }

    def test_each_meaningful_change(self):
        base = ch(FIXTURE)
        for name, (old, new) in self.cases.items():
            with self.subTest(name):
                self.assertNotEqual(ch(sub(old, new)), base, f"{name} change was normalized away")


class VolatileTokensDoNotChangeTheHash(unittest.TestCase):
    cases = {
        "session id in script": ("AAAAsession1111", "BBBBsession2222"),
        "server node marker in title": ("[A]</title>", "[B]</title>"),
        "jsessionid in link": ("jsessionid=XYZ123", "jsessionid=QQQ999"),
        "cache buster in link": ("_t=1700000000", "_t=1800000000"),
        "whitespace reflow": ("<p>지급 조건:", "<p>\n   지급 조건:"),
    }

    def test_each_volatile_change(self):
        base = ch(FIXTURE)
        for name, (old, new) in self.cases.items():
            with self.subTest(name):
                changed = sub(old, new)
                self.assertNotEqual(hashlib.sha256(changed).hexdigest(), hashlib.sha256(FIXTURE).hexdigest())
                self.assertEqual(ch(changed), base, f"{name} should be ignored")

    def test_node_marker_is_host_specific(self):
        changed = sub("[A]</title>", "[B]</title>")
        self.assertNotEqual(h.content_sha256(changed, "example.org"), h.content_sha256(FIXTURE, "example.org"))


class ArchivedOriginals(unittest.TestCase):
    """Runs only with a local archive (originals are not in the public repository)."""

    def setUp(self):
        root = os.environ.get("ONJEON_ARCHIVE_RAW")
        if not root:
            self.skipTest("ONJEON_ARCHIVE_RAW not set")
        self.root = Path(root)

    def obj(self, digest):
        return (self.root / f"objects/sha256/{digest[:2]}/{digest[2:4]}/{digest}").read_bytes()

    def test_kb_refetch_differs_in_bytes_but_not_in_content(self):
        a, b = self.obj(KB_ORIGINAL), self.obj(KB_REFETCH)
        self.assertEqual(hashlib.sha256(a).hexdigest(), KB_ORIGINAL)
        self.assertNotEqual(hashlib.sha256(b).hexdigest(), KB_ORIGINAL)
        self.assertEqual(ch(a), ch(b))

    def test_kb_original_price_change_is_detected(self):
        a = self.obj(KB_ORIGINAL)
        price = "147,000".encode("euc-kr")
        self.assertIn(price, a)
        self.assertNotEqual(ch(a.replace(price, "149,000".encode("euc-kr"), 1)), ch(a))


if __name__ == "__main__":
    unittest.main()
