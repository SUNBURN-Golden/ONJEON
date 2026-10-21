import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import gen_dart as G  # noqa: E402


class GenDart(unittest.TestCase):
    def setUp(self):
        self.tokens = json.loads(G.SRC.read_text(encoding="utf-8"))

    def test_committed_output_is_current(self):
        self.assertTrue(G.OUT.exists(), "run gen_dart.py")
        self.assertEqual(G.render(self.tokens), G.OUT.read_text(encoding="utf-8"))

    def test_spec_core_colours(self):
        c = self.tokens["color"]
        for k, v in {"bg": "#F6F4EE", "accent": "#AE583F", "accent-text": "#A14529", "ink": "#1A1411", "ink-2": "#66554A"}.items():
            self.assertEqual(v, c[k], k)

    def test_bad_colour_rejected(self):
        t = copy.deepcopy(self.tokens)
        t["color"]["bg"] = "F6F4EE"
        with self.assertRaises(ValueError):
            G.render(t)

    def test_unknown_reference_rejected(self):
        t = copy.deepcopy(self.tokens)
        t["text"]["logo"]["color"] = "nope"
        with self.assertRaises(ValueError):
            G.render(t)
        t = copy.deepcopy(self.tokens)
        t["text"]["logo"]["weight"] = "nope"
        with self.assertRaises(ValueError):
            G.render(t)

    def test_no_model_or_home_strings(self):
        text = G.OUT.read_text(encoding="utf-8")
        self.assertNotIn("/home/", text)
        self.assertNotIn("/workspace", text)


if __name__ == "__main__":
    unittest.main()
