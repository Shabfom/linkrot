import unittest

from linkrot.extract import anchors, links, slugify


class LinkExtraction(unittest.TestCase):
    def targets(self, text, **kw):
        return [l.target for l in links(text, **kw)]

    def test_inline_image_reference_and_autolinks(self):
        text = (
            "See [the docs](https://example.com/docs \"Docs\") and ![logo](img/logo.png).\n"
            "Also <https://example.org> and [a ref][r].\n"
            "\n"
            "[r]: ./other.md#setup\n"
        )
        self.assertEqual(
            self.targets(text),
            ["https://example.com/docs", "img/logo.png", "https://example.org", "./other.md#setup"],
        )

    def test_brackets_inside_link_text(self):
        self.assertEqual(self.targets("[see [1]](notes.md)"), ["notes.md"])

    def test_code_is_ignored(self):
        text = "```\n[not](a-link.md)\n```\nUse `[x](y)` here, but [this](real.md) counts.\n"
        self.assertEqual(self.targets(text), ["real.md"])

    def test_tilde_fence_closed_only_by_tildes(self):
        text = "~~~\n```\n[still](code.md)\n~~~\n[after](yes.md)\n"
        self.assertEqual(self.targets(text), ["yes.md"])

    def test_line_numbers(self):
        found = links("one\n\n[x](a.md)\n")
        self.assertEqual(found[0].line, 3)

    def test_html(self):
        text = '<a href="https://example.com/?a=1&amp;b=2">x</a><img src="p.png">'
        self.assertEqual(self.targets(text, is_html=True), ["https://example.com/?a=1&b=2", "p.png"])


class Anchors(unittest.TestCase):
    def test_github_slugs(self):
        self.assertEqual(slugify("Getting Started!"), "getting-started")
        self.assertEqual(slugify("What's `new` in 2.0?"), "whats-new-in-20")
        self.assertEqual(slugify("[Links](x.md) & more"), "links--more")
        self.assertEqual(slugify("Café au lait"), "café-au-lait")

    def test_duplicates_get_numbered(self):
        text = "# Usage\n## Usage\n### Usage\n"
        self.assertEqual(anchors(text), {"usage", "usage-1", "usage-2"})

    def test_setext_and_html_ids(self):
        text = 'Install\n=======\n\nNotes\n-----\n\n<a id="custom"></a>\n\n- item\n---\n'
        self.assertEqual(anchors(text), {"install", "notes", "custom"})

    def test_headings_in_code_dont_count(self):
        self.assertEqual(anchors("```\n# not a heading\n```\n# Real\n"), {"real"})


if __name__ == "__main__":
    unittest.main()
