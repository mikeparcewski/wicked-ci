"""Tests for the wicked docs lint (DT-21).

The r2/r4/r17/r23 fixtures carry the exact defect lines recon-2026-08
RECON-DOCS.md verified in the live corpus — proving the lint would have
caught docs-R2, docs-R4, docs-R17, and docs-R23 pre-merge.

Run:  python3 -m unittest discover -s docs-lint/tests -v
"""

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from docs_lint import lint_repo, load_registry  # noqa: E402

FIXTURES = HERE / "fixtures"
REGISTRY = load_registry(None)


def findings(fixture, **kw):
    return lint_repo(FIXTURES / fixture, REGISTRY, **kw).findings


class TestWouldHaveCaughtReconDefects(unittest.TestCase):
    """AC: the lint would have caught docs-R2/R4/R17/R23 pre-merge."""

    def test_r2_cargo_install_bin_claim(self):
        # wicked-estate/docs/mcp-integration.md:15 — a single cargo install
        # claimed to put wicked-estate-mcp on PATH.
        got = findings("r2")
        self.assertEqual(len(got), 1, got)
        f = got[0]
        self.assertEqual(f.rule, "install-cmd")
        self.assertIn("wicked-estate-mcp", f.message)
        self.assertIn("does not provide", f.message)
        self.assertEqual(f.path, "docs/mcp-integration.md")

    def test_r4a_nonexistent_plugin_subcommand(self):
        # wicked-garden/docs/getting-started.md:14 — `claude plugins add`
        got = [f for f in findings("r4") if f.path == "docs/getting-started.md"]
        self.assertEqual(len(got), 1, got)
        self.assertEqual(got[0].rule, "install-cmd")
        self.assertIn("'add' is not a `claude plugin` subcommand", got[0].message)

    def test_r4b_one_step_install_without_marketplace(self):
        # wicked-garden/README.md:57 — /plugin install with no marketplace add
        got = [f for f in findings("r4")
               if f.path == "README.md" and "marketplace add" in f.message]
        self.assertEqual(len(got), 1, got)
        self.assertIn("wicked-garden", got[0].message)

    def test_r4c_bus_is_not_a_plugin(self):
        # wicked-garden/README.md:74 — "/plugin install wicked-bus"
        got = [f for f in findings("r4")
               if f.path == "README.md" and "not an installable" in f.message]
        self.assertEqual(len(got), 1, got)
        self.assertIn("wicked-bus", got[0].message)

    def test_r17a_npx_of_a_bin_that_is_not_a_package(self):
        # wicked-vault/README.md:52-55 — npx wicked-vault-install (E404)
        got = [f for f in findings("r17") if f.rule == "install-cmd"]
        self.assertEqual(len(got), 1, got)
        self.assertIn("bin of 'wicked-vault'", got[0].message)

    def test_r17b_retired_sibling_reference(self):
        # wicked-vault/README.md:15 — "Sibling to wicked-bus / wicked-brain"
        got = [f for f in findings("r17") if f.rule == "retired-name"]
        self.assertEqual(len(got), 1, got)
        self.assertIn("wicked-brain", got[0].message)

    def test_r23_retirement_banner_one_step_install(self):
        # wicked-testing/README.md:8 — one-step `claude plugins install
        # wicked-garden` in the retirement table
        got = findings("r23")
        self.assertEqual(len(got), 1, got)
        self.assertEqual(got[0].rule, "install-cmd")
        self.assertIn("marketplace add", got[0].message)


class TestMarkersAndExemptions(unittest.TestCase):
    def test_clean_fixture_is_clean(self):
        # Every marker form (line / block / block-with-reason / whole-file,
        # md + JS + yaml comment syntax), every path exemption, the dot-path
        # and URI pattern exclusions, and correct install commands.
        self.assertEqual(findings("clean"), [])

    def test_unclosed_block_is_an_error_and_masks_nothing_else(self):
        got = findings("unclosed")
        self.assertEqual(len(got), 1, got)
        self.assertEqual(got[0].rule, "marker")
        self.assertIn("unclosed", got[0].message)
        self.assertEqual(got[0].line, 3)

    def test_stray_close_is_an_error(self):
        got = findings("stray-close")
        self.assertEqual(len(got), 1, got)
        self.assertEqual(got[0].rule, "marker")
        self.assertIn("without a matching open", got[0].message)


class TestVersionStamp(unittest.TestCase):
    def test_off_by_default(self):
        self.assertEqual(findings("versions"), [])

    def test_opt_in_catches_stale_stamp(self):
        got = findings("versions", check_versions=True)
        self.assertEqual(len(got), 1, got)
        self.assertEqual(got[0].rule, "version-stamp")
        self.assertIn("1.2.2", got[0].message)
        self.assertIn("1.2.3", got[0].message)


class TestScopePattern(unittest.TestCase):
    """The scope doc's regex exclusions, straight from section 1."""

    def _lint_text(self, text):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "README.md").write_text(text, encoding="utf-8")
            return lint_repo(td, REGISTRY).findings

    def test_dot_path_store_roots_excluded(self):
        self.assertEqual(self._lint_text(
            "the `.wicked-testing/` root and `~/.wicked-brain` archive\n"), [])

    def test_attribution_uri_excluded(self):
        self.assertEqual(self._lint_text(
            "chunks keep wicked-brain://project/doc-1 URIs\n"), [])

    def test_plain_mention_flagged(self):
        got = self._lint_text("wicked-signals routes intents\n")
        self.assertEqual([f.rule for f in got], ["retired-name"])

    def test_filename_mention_in_text_flagged_but_suffix_names_not(self):
        got = self._lint_text("see examples/wicked-testing.release.yml\n")
        self.assertEqual(len(got), 1, got)
        # plural continuations are other words, not the product
        self.assertEqual(self._lint_text("wicked-brains trivia night\n"), [])

    def test_npx_of_a_bin_ok_when_owner_installed_in_same_doc(self):
        # the sanctioned form: npm i -g wicked-bus && npx wicked-bus-install
        self.assertEqual(self._lint_text(
            "npm i -g wicked-bus && npx wicked-bus-install\n"), [])
        # ... including across lines in the same doc (update-skill shape)
        self.assertEqual(self._lint_text(
            "npm install -g wicked-vault@latest\n\nnpx wicked-vault-install\n"), [])

    def test_placeholder_plugin_name_skipped(self):
        self.assertEqual(self._lint_text(
            "claude plugins install wicked-{name}\n"), [])


if __name__ == "__main__":
    unittest.main()
