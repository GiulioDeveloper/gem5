#!/usr/bin/env python3
"""Structural lint for the docs/ knowledge base (see docs/wiki/SCHEMA.md).

Checks the wiki pages under docs/wiki/ for:
  - frontmatter: present, with valid type/status and an ISO `updated` date
  - wikilinks: every [[target]] / [[target#heading]] resolves, across the
    whole docs/ vault (wiki, legacy-log, raw); headings are checked for
    markdown targets
  - duplicate page names inside the wiki or clashing with any other vault
    file (bare [[name]] would be ambiguous in Obsidian); bare links must
    name wiki pages, legacy/raw files are linked by vault path
  - pages missing from index.md, and orphans (no inbound link from any
    page other than index.md and log.md)
  - published outputs (publish.md) whose source pages changed after the
    build date

Links to pages that do not exist yet are reported as "wanted" (gaps), not
errors. Exit status is 1 when there are errors, 0 otherwise.

Usage: python3 docs/tools/wiki_lint.py [--quiet]
"""

import argparse
import datetime
import re
import sys
from collections import defaultdict
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent
WIKI = DOCS / "wiki"
# Vault folders that are not part of the knowledge base.
SKIP_DIRS = {"_build", "gem5-sphinx", "gem5-sphinx-apidoc", ".obsidian"}
# Pages under the wiki that are not knowledge pages.
SKIP_WIKI_DIRS = {"_publish"}

TYPES = {
    "overview",
    "entity",
    "concept",
    "howto",
    "experiment",
    "finding",
    "method",
    "pitfall",
    "gem5",
    "garfield",
    "meta",
}
STATUSES = {"current", "draft", "open", "superseded"}
HUB_PAGES = {"index", "log"}

LINK_RE = re.compile(r"!?\[\[([^\]\|#]*)(?:#([^\]\|]*))?(?:\|[^\]]*)?\]\]")
FENCE_RE = re.compile(r"^\s*(```|~~~)")
INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")


def vault_files():
    """Every file in the vault, as paths relative to docs/."""
    out = []
    for p in DOCS.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(DOCS)
        if rel.parts[0] in SKIP_DIRS or rel.parts[0] == "tools":
            continue
        out.append(rel)
    return out


def strip_code(text):
    """Drop fenced code blocks and inline code, keeping line structure."""
    lines, in_fence = [], False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            lines.append("")
            continue
        lines.append("" if in_fence else INLINE_CODE_RE.sub("", line))
    return "\n".join(lines)


def parse_frontmatter(text):
    """Return (dict, error) for a minimal YAML frontmatter block."""
    if not text.startswith("---\n"):
        return None, "no frontmatter"
    end = text.find("\n---", 4)
    if end < 0:
        return None, "unterminated frontmatter"
    fm, key = {}, None
    for line in text[4:end].splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            key, val = m.group(1), m.group(2).strip()
            fm[key] = val
            continue
        if key and line.lstrip().startswith("- "):
            prev = fm.get(key)
            fm[key] = (prev if isinstance(prev, list) else []) + [
                line.strip()[2:]
            ]
    return fm, None


def headings(text):
    out = set()
    for line in strip_code(text).splitlines():
        m = HEADING_RE.match(line)
        if m:
            out.add(m.group(1).strip())
    return out


def parse_date(val):
    try:
        return datetime.date.fromisoformat(str(val).strip().strip("\"'"))
    except ValueError:
        return None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--quiet", action="store_true", help="print errors only"
    )
    args = ap.parse_args()

    files = vault_files()
    by_path = {}  # "legacy-log/garfield/README" -> rel path
    by_name = defaultdict(list)  # "README" -> [rel paths]
    for rel in files:
        key = rel.as_posix()
        by_path[key] = rel
        if rel.suffix == ".md":
            by_path[key[:-3]] = rel
            by_name[rel.stem].append(rel)

    wiki_pages = [
        rel
        for rel in files
        if rel.parts[0] == "wiki"
        and rel.suffix == ".md"
        and not SKIP_WIKI_DIRS.intersection(rel.parts)
    ]

    errors, warnings = [], []
    wanted = defaultdict(set)  # missing target -> referring pages
    inbound = defaultdict(set)  # page rel -> referring page stems
    text_cache, heading_cache, updated = {}, {}, {}

    def read(rel):
        if rel not in text_cache:
            text_cache[rel] = (DOCS / rel).read_text(errors="replace")
        return text_cache[rel]

    # Duplicate names inside the wiki make bare links ambiguous.
    stems = defaultdict(list)
    for rel in wiki_pages:
        stems[rel.stem].append(rel)
    for stem, rels in stems.items():
        if len(rels) > 1:
            errors.append(
                f"duplicate wiki page name '{stem}': "
                + ", ".join(r.as_posix() for r in rels)
            )

    # Obsidian resolves a bare [[name]] unpredictably when another vault
    # file has the same name, so wiki page names must be vault-unique.
    for stem, rels in stems.items():
        others = [r for r in by_name.get(stem, []) if r not in rels]
        if others:
            errors.append(
                f"wiki page name '{stem}' clashes with "
                + ", ".join(r.as_posix() for r in others)
            )

    def resolve(target, src):
        target = target.strip()
        if not target:
            return src  # [[#heading]] points into the same page
        if "/" in target:
            return by_path.get(target.lstrip("/"))
        # Bare names must be wiki pages; legacy/raw files need a path.
        if target in stems and len(stems[target]) == 1:
            return stems[target][0]
        if by_name.get(target) or target in by_path:
            return "outside"
        return None

    for rel in sorted(wiki_pages):
        name = rel.as_posix()
        text = read(rel)
        fm, err = parse_frontmatter(text)
        if err:
            errors.append(f"{name}: {err}")
            fm = {}
        else:
            if fm.get("type") not in TYPES:
                errors.append(f"{name}: bad or missing type {fm.get('type')!r}")
            if fm.get("status") not in STATUSES:
                errors.append(
                    f"{name}: bad or missing status {fm.get('status')!r}"
                )
            d = parse_date(fm.get("updated", ""))
            if d is None:
                errors.append(f"{name}: bad or missing updated date")
            else:
                updated[rel] = d
            if fm.get("type") not in ("meta",) and "sources" not in fm:
                warnings.append(f"{name}: no sources field")

        # Inline code is stripped before matching, so a backtick inside a
        # link would be checked against the stripped text; Obsidian would not.
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in re.finditer(r"\[\[[^\]]*`[^\]]*\]\]", line):
                warnings.append(
                    f"{name}:{lineno}: backtick inside link {m.group(0)}"
                )

        for lineno, line in enumerate(strip_code(text).splitlines(), 1):
            for m in LINK_RE.finditer(line):
                target, heading = m.group(1), m.group(2)
                dest = resolve(target, rel)
                where = f"{name}:{lineno}"
                if dest == "outside":
                    errors.append(
                        f"{where}: [[{target}]] is not a wiki page; link "
                        "legacy/raw files by vault path"
                    )
                    continue
                if dest is None:
                    if "/" in target:
                        errors.append(f"{where}: broken link [[{target}]]")
                    else:
                        wanted[target.strip()].add(name)
                    continue
                if dest != rel:
                    inbound[dest].add(rel.stem)
                if heading and dest.suffix == ".md":
                    if dest not in heading_cache:
                        heading_cache[dest] = headings(read(dest))
                    if heading.strip() not in heading_cache[dest]:
                        errors.append(
                            f"{where}: no heading '{heading}' in "
                            f"{dest.as_posix()}"
                        )

    # Index coverage and orphans.
    index_rel = Path("wiki/index.md")
    index_text = strip_code(read(index_rel)) if index_rel in files else ""
    indexed = {
        resolve(m.group(1), index_rel) for m in LINK_RE.finditer(index_text)
    }
    for rel in sorted(wiki_pages):
        if rel.stem in HUB_PAGES or rel.stem in ("SCHEMA", "publish"):
            continue
        if rel not in indexed:
            errors.append(f"{rel.as_posix()}: not listed in index.md")
        if not (inbound[rel] - HUB_PAGES):
            warnings.append(f"{rel.as_posix()}: orphan (only hub links)")

    # Published outputs whose sources changed after the build.
    publish_rel = Path("wiki/publish.md")
    if publish_rel in files:
        for line in read(publish_rel).splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 6 or cells[0] in ("name", "") or "---" in line:
                continue
            built = parse_date(cells[4])
            if built is None:
                errors.append(f"publish.md: output {cells[0]!r} has no date")
                continue
            for m in LINK_RE.finditer(cells[2]):
                dest = resolve(m.group(1), publish_rel)
                if dest in updated and updated[dest] > built:
                    errors.append(
                        f"publish.md: output {cells[0]!r} is stale: "
                        f"{dest.as_posix()} updated {updated[dest]} "
                        f"> built {built}"
                    )

    for e in errors:
        print(f"ERROR   {e}")
    if not args.quiet:
        for w in warnings:
            print(f"warn    {w}")
        for target in sorted(wanted):
            refs = ", ".join(sorted(wanted[target]))
            print(f"wanted  [[{target}]] <- {refs}")
        print(
            f"\n{len(wiki_pages)} wiki pages, {len(errors)} errors, "
            f"{len(warnings)} warnings, {len(wanted)} wanted pages"
        )
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
