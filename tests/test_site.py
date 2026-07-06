"""Static checks for the landing page in site/.

Stdlib only. Verifies the three deliverable files exist, the HTML is
well-formed (balanced non-void tags), required section anchors exist,
local href/src targets resolve, and external links stay on the allowlist.
"""
import unittest
from html.parser import HTMLParser
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input",
        "link", "meta", "source", "track", "wbr"}
REQUIRED_IDS = {"problem", "how", "features", "install", "usage"}
ALLOWED_EXTERNAL = {
    "https://github.com/eliknut/cloudctx",
    "https://github.com/larsakerlund/loft",
}


class _Audit(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.errors = []
        self.ids = set()
        self.refs = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        for key in ("href", "src"):
            if a.get(key):
                self.refs.append(a[key])
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(
                "mismatched </%s> at line %d" % (tag, self.getpos()[0]))
        else:
            self.stack.pop()


def _parse():
    audit = _Audit()
    audit.feed((SITE / "index.html").read_text(encoding="utf-8"))
    return audit


class SiteTests(unittest.TestCase):
    def test_deliverables_exist(self):
        for name in ("index.html", "style.css", "favicon.svg"):
            self.assertTrue((SITE / name).is_file(), "missing site/" + name)

    def test_html_well_formed(self):
        audit = _parse()
        self.assertEqual(audit.errors, [])
        self.assertEqual(audit.stack, [], "unclosed tags: %s" % audit.stack)

    def test_required_sections(self):
        self.assertLessEqual(REQUIRED_IDS, _parse().ids)

    def test_links_resolve(self):
        audit = _parse()
        for ref in audit.refs:
            if ref.startswith(("http://", "https://")):
                self.assertIn(ref, ALLOWED_EXTERNAL)
            elif ref.startswith("#"):
                self.assertIn(ref[1:], audit.ids, "broken anchor " + ref)
            else:
                self.assertTrue((SITE / ref).is_file(),
                                "broken local ref " + ref)


if __name__ == "__main__":
    unittest.main()
