#!/usr/bin/env python3
"""wicked docs lint (DT-21, recon-2026-08 docs-R25).

Cross-repo docs lint for the wicked-* family. Three rules:

  retired-name   A retired product name (per the registry) in a live doc,
                 outside historical markers and exempt paths, is a defect.
                 Contract: docs/docs-lint-scope.md (DT-22).
  install-cmd    Parse-level smoke validation of documented install
                 commands (npm / npx / cargo install / claude plugin) against
                 a static family registry. No network.
  version-stamp  Optional (--check-versions): version stamps in docs that
                 name one of the repo's own packages must match the
                 manifest version.

Exit codes: 0 clean, 1 findings, 2 usage error.

Stdlib only; runs on macOS / Linux / Windows (python3 or python).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath

# --------------------------------------------------------------------------
# Registry (static, parse-level — the allowlists the lint reads).
# docs-lint/registry.json overrides/extends these defaults.
# --------------------------------------------------------------------------

DEFAULT_REGISTRY = {
    # Retired product names: a mention in a live doc is a defect unless
    # marker-annotated or path-exempt (docs/docs-lint-scope.md section 1).
    "retired_names": ["testing", "brain", "signals"],
    # npm packages that exist (family scope: only wicked-* tokens are checked)
    "npm_packages": [],
    # bin name -> owning npm package (bins are NOT installable package names)
    "npm_bins": {},
    # cargo crate -> list of [[bin]] names it installs
    "cargo_crates": {},
    # installable Claude Code plugin names
    "claude_plugins": [],
    # valid `claude plugin <subcommand>` set (from `claude plugin --help`)
    "claude_plugin_subcommands": [],
}

# --------------------------------------------------------------------------
# Path scope (docs/docs-lint-scope.md sections 3-4)
# --------------------------------------------------------------------------

PRUNE_DIRS = {".git", "node_modules", "dist", "build", "target", "archived"}
EXEMPT_SEGMENTS = {
    ".product",
    ".wicked-testing",
    ".wicked-qe",
    ".wicked-vault",
    "scenarios",
}
CODE_SEGMENTS = {"src", "lib", "bin", "scripts", "hooks", "tests", "test", "e2e"}
LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "Cargo.lock"}
SITE_EXTS = {".astro", ".ts", ".tsx", ".js", ".css", ".md"}
MD_TREES = {"docs", "reqs", "skills", ".claude"}
BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".pdf",
    ".woff", ".woff2", ".ttf", ".otf", ".eot", ".zip", ".gz", ".tar",
    ".mp4", ".webm", ".wasm", ".node", ".db",
}


DEFAULT_SITE_SRCS = ("site/src",)


def is_scanned(rel: PurePosixPath, site_srcs=DEFAULT_SITE_SRCS) -> bool:
    """Is this repo-relative path in the lint's docs surface?"""
    parts = rel.parts
    base = rel.name
    ext = rel.suffix.lower()

    if any(p in PRUNE_DIRS for p in parts):
        return False
    if any(p in EXEMPT_SEGMENTS for p in parts):
        return False
    if base == "CHANGELOG.md":
        return False
    if any("migration" in p.lower() for p in parts):
        return False
    if base in LOCKFILES:
        return False
    # The lint's own definition and configuration.
    if base == "docs-lint-scope.md" or parts[0] == "docs-lint":
        return False

    # Root-level *.md (README.md, CLAUDE.md, AGENTS.md, ...)
    if len(parts) == 1:
        return ext == ".md" and not base.startswith(".")

    # site/src/** — the one deliberate code-tree exception (site copy is
    # user-facing narrative). Repos whose site source lives elsewhere
    # (e.g. the apex site's root src/) pass --site-src.
    posix = rel.as_posix()
    for src_root in site_srcs:
        if posix.startswith(src_root.rstrip("/") + "/"):
            return ext in SITE_EXTS

    # docs/**, reqs/**, skills/**, .claude/**  (*.md, minus nested code trees)
    if parts[0] in MD_TREES:
        if any(p in CODE_SEGMENTS for p in parts[1:-1]):
            return False
        return ext == ".md"

    # packages/*/README.md — published npm READMEs
    if parts[0] == "packages" and len(parts) == 3 and base == "README.md":
        return True

    # examples/** — teaching configs
    if parts[0] == "examples":
        if any(p in CODE_SEGMENTS for p in parts[1:-1]):
            return False
        if base.startswith(".") or ext in BINARY_EXTS:
            return False
        return True

    return False


# --------------------------------------------------------------------------
# Historical markers (docs/docs-lint-scope.md section 2)
# --------------------------------------------------------------------------

# A marker is a comment leader + token, matched as a substring of a line.
MARKER_RE = re.compile(r"(<!--|/\*|//|#)\s*(/?historical(?:-doc)?)(?![\w-])")
# Trivia allowed before an alone-on-its-line marker (whitespace, blockquote
# '>', list '-'/'*', JSX '{', comment-continuation '*').
ALONE_BEFORE_RE = re.compile(r"[\s>*{(\-]*\Z")
# Comment closers that may trail an alone marker (with optional reason).
TRAILING_CLOSERS = ("-->", "*/", "}", ")")


def _marker_alone(line: str, m: re.Match) -> bool:
    """Marker alone on its line (ignoring comment syntax / an optional reason)."""
    if not ALONE_BEFORE_RE.match(line[: m.start()]):
        return False
    rest = line[m.end():].strip()
    while True:
        stripped = False
        for closer in TRAILING_CLOSERS:
            if rest.endswith(closer):
                rest = rest[: -len(closer)].strip()
                stripped = True
        if not stripped:
            break
    if not rest:
        return True
    # An optional reason after the token: `: ...` or `— ...` / `- ...`
    return rest.startswith((":", "—", "–", "-"))


# --------------------------------------------------------------------------
# Rule regexes
# --------------------------------------------------------------------------

def retired_re(names) -> re.Pattern:
    """The scope doc's pattern:  (^|[^.\\w-])wicked-(testing|brain|signals)(?!://)\\b

    Excludes dot-path store roots (.wicked-testing/, ~/.wicked-brain) and
    wicked-brain:// attribution URIs by construction.
    """
    alt = "|".join(re.escape(n) for n in names)
    return re.compile(r"(^|[^.\w-])wicked-(%s)(?!://)\b" % alt)


# claude plugin CLI + /plugin slash-command forms
CLAUDE_CLI_RE = re.compile(r"\bclaude\s+plugins?\s+([a-z][\w-]*)")
SLASH_PLUGIN_RE = re.compile(r"(^|[\s`'\">])/plugins?\s+([a-z][\w-]*)")
PLUGIN_NAME_RE = re.compile(r"\s+([\w.@/-]+)")

NPX_RE = re.compile(r"\bnpx\s+(?:-y\s+|--yes\s+)?([\w.@-]+)")
NPM_INSTALL_RE = re.compile(r"\bnpm\s+(?:install|i|add)\b([^`\n;&|#]*)")
CARGO_INSTALL_RE = re.compile(r"\bcargo\s+install\s+([^`\n;&|#]*)")
WICKED_TOKEN_RE = re.compile(r"\bwicked(?:-[\w]+)*\b")
_TOKEN_TRIM = "`'\".,;:()[]{}<>*"

MARKETPLACE_ADD_RE = re.compile(r"marketplace\s+add\b")


class Finding:
    __slots__ = ("path", "line", "rule", "message")

    def __init__(self, path, line, rule, message):
        self.path, self.line, self.rule, self.message = path, line, rule, message

    def __repr__(self):  # pragma: no cover
        return f"{self.path}:{self.line}: [{self.rule}] {self.message}"


def _tokens(argstr: str):
    """Whitespace tokens with surrounding punctuation trimmed."""
    out = []
    skip_next = False
    for raw in argstr.split():
        if skip_next:
            skip_next = False
            continue
        if raw.startswith("-"):
            # skip value-taking cargo/npm flags conservatively
            if raw in ("--version", "--vers", "--tag", "--branch", "--rev",
                       "--root", "--git", "--path", "--registry"):
                skip_next = True
            continue
        tok = raw.strip(_TOKEN_TRIM)
        if tok:
            out.append(tok)
    return out


class Linter:
    def __init__(self, root: Path, registry: dict, check_versions=False,
                 site_srcs=DEFAULT_SITE_SRCS):
        self.root = root
        self.reg = registry
        self.check_versions = check_versions
        self.site_srcs = tuple(site_srcs)
        self.retired = retired_re(registry["retired_names"])
        self.findings: list[Finding] = []
        self.files_scanned = 0

    # -- file iteration ----------------------------------------------------

    def iter_files(self):
        import os
        hits = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(d for d in dirnames
                                 if d not in PRUNE_DIRS
                                 and d not in EXEMPT_SEGMENTS)
            for fn in filenames:
                path = Path(dirpath) / fn
                if path.is_symlink():
                    continue
                rel = PurePosixPath(path.relative_to(self.root).as_posix())
                if is_scanned(rel, self.site_srcs):
                    hits.append((path, rel))
        return sorted(hits, key=lambda t: t[1])

    def run(self) -> list[Finding]:
        for path, rel in self.iter_files():
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "\x00" in text[:1024]:
                continue  # binary
            self.files_scanned += 1
            self.lint_file(rel, text)
        if self.check_versions:
            self.lint_versions()
        self.findings.sort(key=lambda f: (f.path, f.line))
        return self.findings

    # -- per-file lint -----------------------------------------------------

    def lint_file(self, rel: PurePosixPath, text: str):
        lines = text.splitlines()

        # Whole-file marker within the first 15 lines.
        for line in lines[:15]:
            m = MARKER_RE.search(line)
            if m and m.group(2) == "historical-doc":
                return

        depth = 0
        open_line = 0
        for i, line in enumerate(lines, start=1):
            line_exempt = False
            m = MARKER_RE.search(line)
            if m:
                token = m.group(2)
                if token == "/historical" and _marker_alone(line, m):
                    if depth == 0:
                        self.add(rel, i, "marker",
                                 "block close marker without a matching open")
                    else:
                        depth -= 1
                    line_exempt = True
                elif token == "historical":
                    if _marker_alone(line, m):
                        if depth == 0:
                            open_line = i
                        depth += 1
                    line_exempt = True
                elif token == "historical-doc":
                    # Below line 15 it does not exempt the file; treat it as
                    # a line marker (lenient).
                    line_exempt = True

            if depth > 0 or line_exempt:
                continue
            self.lint_line(rel, i, line, text)

        if depth > 0:
            self.add(rel, open_line, "marker",
                     "unclosed historical block (opened here) — an unclosed "
                     "block would mask the rest of the file; add the close "
                     "marker")

    # -- per-line content rules ---------------------------------------------

    def lint_line(self, rel, i, line, filetext):
        for m in self.retired.finditer(line):
            self.add(rel, i, "retired-name",
                     f"retired product name 'wicked-{m.group(2)}' outside a "
                     "historical marker (see docs/docs-lint-scope.md)")
        self.lint_claude_plugin(rel, i, line, filetext)
        self.lint_npm(rel, i, line, filetext)
        self.lint_cargo(rel, i, line)

    def lint_claude_plugin(self, rel, i, line, filetext):
        subs = set(self.reg["claude_plugin_subcommands"])
        plugins = set(self.reg["claude_plugins"])
        hits = [(m.start(1), m.group(1), m.end(1))
                for m in CLAUDE_CLI_RE.finditer(line)]
        hits += [(m.start(2), m.group(2), m.end(2))
                 for m in SLASH_PLUGIN_RE.finditer(line)]
        for _, sub, end in hits:
            if subs and sub not in subs:
                self.add(rel, i, "install-cmd",
                         f"'{sub}' is not a `claude plugin` subcommand "
                         f"(valid: {', '.join(sorted(subs))})")
                continue
            if sub != "install":
                continue
            nm = PLUGIN_NAME_RE.match(line, end)
            if not nm:
                continue
            name = nm.group(1).split("@")[0].strip(_TOKEN_TRIM)
            if not name.startswith("wicked-"):
                continue
            if name.endswith("-"):
                continue  # template placeholder, e.g. wicked-{name}
            if name not in plugins:
                self.add(rel, i, "install-cmd",
                         f"'{name}' is not an installable Claude Code plugin "
                         f"(known: {', '.join(sorted(plugins))})")
            elif not MARKETPLACE_ADD_RE.search(filetext):
                self.add(rel, i, "install-cmd",
                         f"one-step plugin install of '{name}' without a "
                         "`claude plugins marketplace add ...` step anywhere "
                         "in this file — fails for a fresh user")

    def _check_npm_token(self, rel, i, tok, filetext=None):
        name = tok.split("@")[0] if not tok.startswith("@") else tok
        if not name.startswith("wicked") or name.endswith("-"):
            return
        pkgs = set(self.reg["npm_packages"])
        bins = self.reg["npm_bins"]
        if name in pkgs:
            return
        if name in bins:
            owner = bins[name]
            # `npx <bin>` is legitimate when the owning package is
            # npm-installed in the same doc (npx resolves the on-PATH /
            # local bin instead of fetching a registry package) — the
            # sanctioned `npm i -g wicked-bus && npx wicked-bus-install`
            # form. Standalone it 404s (docs-R17).
            if filetext is not None and re.search(
                    r"\bnpm\s+(?:install|i|add|update)\b[^\n]*\b%s\b"
                    % re.escape(owner), filetext):
                return
            self.add(rel, i, "install-cmd",
                     f"'{name}' is not an npm package — it is a bin of "
                     f"'{owner}'; install the package first "
                     f"(`npm i -g {owner} && {name}`)")
        else:
            self.add(rel, i, "install-cmd",
                     f"'{name}' is not a known npm package in the family "
                     "registry (docs-lint/registry.json)")

    def lint_npm(self, rel, i, line, filetext):
        for m in NPX_RE.finditer(line):
            self._check_npm_token(rel, i, m.group(1).strip(_TOKEN_TRIM),
                                  filetext=filetext)
        for m in NPM_INSTALL_RE.finditer(line):
            for tok in _tokens(m.group(1)):
                if WICKED_TOKEN_RE.fullmatch(tok.split("@")[0]):
                    self._check_npm_token(rel, i, tok)

    def lint_cargo(self, rel, i, line):
        crates = self.reg["cargo_crates"]
        for m in CARGO_INSTALL_RE.finditer(line):
            installed = [t.split("@")[0] for t in _tokens(m.group(1))
                         if WICKED_TOKEN_RE.fullmatch(t.split("@")[0])]
            provided_bins = set()
            for crate in installed:
                if crate not in crates:
                    self.add(rel, i, "install-cmd",
                             f"'{crate}' is not a known cargo crate in the "
                             "family registry (docs-lint/registry.json)")
                elif not crates[crate]:
                    self.add(rel, i, "install-cmd",
                             f"`cargo install {crate}` fails — '{crate}' is a "
                             "library crate with no [[bin]]")
                else:
                    provided_bins.update(crates[crate])
            if not installed:
                continue
            # Bin-claim check (docs-R2): a same-line claim that a bin lands
            # on PATH which the installed crates do not provide.
            remainder = line[:m.start()] + line[m.end():]
            for tok in WICKED_TOKEN_RE.findall(remainder):
                for crate, bins in crates.items():
                    if tok in bins and tok not in provided_bins \
                            and crate not in installed:
                        self.add(rel, i, "install-cmd",
                                 f"claims bin '{tok}' which `cargo install "
                                 f"{' '.join(installed)}` does not provide — "
                                 f"'{tok}' is a bin of crate '{crate}'")

    # -- optional version-stamp assert (docs-R25 c, belt-and-braces w/ R7) --

    def lint_versions(self):
        versions = {}
        for pj in [self.root / "package.json",
                   *sorted(self.root.glob("packages/*/package.json"))]:
            try:
                data = json.loads(pj.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if data.get("name") and data.get("version"):
                versions[data["name"]] = data["version"]
        for ct in [self.root / "Cargo.toml",
                   *sorted(self.root.glob("crates/*/Cargo.toml"))]:
            try:
                text = ct.read_text(encoding="utf-8")
            except OSError:
                continue
            nm = re.search(r'(?ms)^\[package\].*?^name\s*=\s*"([^"]+)"', text)
            vm = re.search(r'(?ms)^\[package\].*?^version\s*=\s*"([^"]+)"', text)
            if nm and vm:
                versions.setdefault(nm.group(1), vm.group(1))
        if not versions:
            return
        stamp_res = {
            name: re.compile(
                r"%s\s*[@ ]\s*v?(\d+\.\d+\.\d+)" % re.escape(name))
            for name in versions
        }
        for path, rel in self.iter_files():
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                for name, sre in stamp_res.items():
                    for m in sre.finditer(line):
                        if m.group(1) != versions[name]:
                            self.add(rel, i, "version-stamp",
                                     f"'{name}' stamped {m.group(1)} but the "
                                     f"manifest says {versions[name]}")

    def add(self, rel, line, rule, message):
        self.findings.append(Finding(str(rel), line, rule, message))


# --------------------------------------------------------------------------


def load_registry(path: Path | None) -> dict:
    reg = dict(DEFAULT_REGISTRY)
    if path is None:
        default = Path(__file__).resolve().parent / "registry.json"
        path = default if default.is_file() else None
    if path is not None:
        reg.update(json.loads(Path(path).read_text(encoding="utf-8")))
    return reg


def lint_repo(root, registry=None, check_versions=False,
              site_srcs=DEFAULT_SITE_SRCS) -> Linter:
    linter = Linter(Path(root), registry or load_registry(None),
                    check_versions, site_srcs)
    linter.run()
    return linter


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="wicked docs lint (scope: docs/docs-lint-scope.md)")
    ap.add_argument("root", nargs="?", default=".", help="repo root to lint")
    ap.add_argument("--registry", help="path to registry.json (family allowlists)")
    ap.add_argument("--check-versions", action="store_true",
                    help="also assert version stamps against manifests")
    ap.add_argument("--site-src", action="append", default=None,
                    metavar="DIR",
                    help="site-source root(s) scanned as user-facing "
                         "narrative (default: site/src; pass e.g. --site-src "
                         "src for a repo whose site lives at root src/)")
    ap.add_argument("--list-files", action="store_true",
                    help="print the scanned file set and exit")
    args = ap.parse_args(argv)

    root = Path(args.root)
    if not root.is_dir():
        print(f"docs-lint: not a directory: {root}", file=sys.stderr)
        return 2
    registry = load_registry(Path(args.registry) if args.registry else None)
    site_srcs = tuple(args.site_src) if args.site_src else DEFAULT_SITE_SRCS

    linter = Linter(root, registry, args.check_versions, site_srcs)
    if args.list_files:
        for _, rel in linter.iter_files():
            print(rel)
        return 0

    findings = linter.run()
    for f in findings:
        print(f"{f.path}:{f.line}: [{f.rule}] {f.message}")
    if findings:
        print(f"docs-lint: {len(findings)} finding(s) in {root} "
              f"({linter.files_scanned} files scanned)")
        return 1
    print(f"docs-lint: clean ({linter.files_scanned} files scanned) in {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
