#!/usr/bin/env python3
"""Refresh the guide references of the `seo` skill from coreyhaines31/marketingskills (MIT).

Each upstream skill becomes references/<folder>/GUIDE.md (its SKILL.md without the frontmatter, so it is not
loaded as a separate skill) plus its own references/*.md next to it. Upstream evals are not copied.
Prints which guides changed and the upstream VERSIONS.md lines for them, then records the commit and the upstream
LICENSE text (MIT: the copyright notice must travel with the copies) in references/UPSTREAM.md.

Usage: sync_upstream.py [--dry-run] [--repo PATH_TO_LOCAL_CLONE]
Without --repo it shallow-clones the repo into a temporary folder.
"""
from __future__ import annotations

import argparse
import datetime as dt
import filecmp
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REFS = os.path.join(HERE, "..", "references")
REPO = "https://github.com/coreyhaines31/marketingskills.git"
MAP = {  # upstream skill -> folder in references/
    "seo-audit": "audit-checklist",
    "schema": "schema",
    "site-architecture": "site-architecture",
    "programmatic-seo": "programmatic-seo",
    "competitors": "competitor-pages",
    "ai-seo": "ai-visibility",
}


def strip_frontmatter(text: str) -> str:
    return re.sub(r"\A---\n.*?\n---\n+", "", text, flags=re.S)


def build(src_skill: str, dst: str) -> None:
    os.makedirs(dst, exist_ok=True)
    with open(os.path.join(src_skill, "SKILL.md")) as f:
        guide = strip_frontmatter(f.read())
    with open(os.path.join(dst, "GUIDE.md"), "w") as f:
        f.write(guide)
    src_refs = os.path.join(src_skill, "references")
    if os.path.isdir(src_refs):
        shutil.copytree(src_refs, os.path.join(dst, "references"), dirs_exist_ok=True)
        for root, _, files in os.walk(os.path.join(dst, "references")):  # links to the renamed SKILL.md
            for name in files:
                if name.endswith(".md"):
                    path = os.path.join(root, name)
                    with open(path) as f:
                        text = f.read()
                    if "](../SKILL.md)" in text:
                        with open(path, "w") as f:
                            f.write(text.replace("](../SKILL.md)", "](../GUIDE.md)"))


def upstream_md(commit: str, synced: str, licence: str) -> str:
    """references/UPSTREAM.md: source, commit, folder map and the upstream licence text."""
    return (f"# Upstream\n\nGuides in this folder come from https://github.com/coreyhaines31/marketingskills (MIT), "
            f"commit {commit}, synced {synced} by scripts/sync_upstream.py.\n\n"
            "| Upstream skill | Folder here |\n|---|---|\n"
            + "".join(f"| {s} | references/{d}/GUIDE.md |\n" for s, d in MAP.items())
            + "\n## Licence\n\nThe guides are copied unchanged except that each SKILL.md lost its frontmatter and became "
              "GUIDE.md (links to it now point to GUIDE.md; \"SKILL.md\" in the text means that GUIDE.md). Their "
              "licence:\n\n```text\n" + licence.strip() + "\n```\n")


def current_licence() -> str:
    """The licence text already recorded in UPSTREAM.md (kept when the clone has no LICENSE file)."""
    p = os.path.join(REFS, "UPSTREAM.md")
    m = re.search(r"```text\n(.*?)\n```", open(p).read(), re.S) if os.path.exists(p) else None
    return m.group(1) if m else ""


def same(a: str, b: str) -> bool:
    if not os.path.isdir(b):
        return False
    cmp = filecmp.dircmp(a, b)
    def walk(c):
        if c.left_only or c.right_only or c.diff_files or c.funny_files:
            return False
        return all(walk(s) for s in c.subdirs.values())
    return walk(cmp)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    tmp = None
    repo = a.repo
    if not repo:
        tmp = tempfile.mkdtemp()
        repo = os.path.join(tmp, "marketingskills")
        subprocess.run(["git", "clone", "-q", "--depth", "1", REPO, repo], check=True)
    commit = subprocess.run(["git", "-C", repo, "log", "-1", "--format=%h %cs"], capture_output=True, text=True).stdout.strip()
    versions = open(os.path.join(repo, "VERSIONS.md")).read() if os.path.exists(os.path.join(repo, "VERSIONS.md")) else ""
    changed = []
    for skill, folder in MAP.items():
        src = os.path.join(repo, "skills", skill)
        if not os.path.isdir(src):
            print(f"! upstream skill {skill} not found (renamed?)", file=sys.stderr)
            continue
        stage = tempfile.mkdtemp()
        build(src, stage)
        dst = os.path.join(REFS, folder)
        if not same(stage, dst):
            changed.append(skill)
            if not a.dry_run:
                shutil.rmtree(dst, ignore_errors=True)
                shutil.copytree(stage, dst)
        shutil.rmtree(stage, ignore_errors=True)
    print(f"upstream {commit}: {len(changed)} guide(s) changed: {', '.join(changed) or 'none'}")
    for skill in changed:
        for line in versions.splitlines():
            if re.match(rf"\|\s*{re.escape(skill)}\s*\|", line):
                print("  ", line.strip())
    if not a.dry_run:
        lic_path = os.path.join(repo, "LICENSE")
        licence = open(lic_path).read() if os.path.exists(lic_path) else current_licence()
        if not licence:
            print("! no LICENSE in the upstream clone and none recorded: add it to references/UPSTREAM.md by hand",
                  file=sys.stderr)
        with open(os.path.join(REFS, "UPSTREAM.md"), "w") as f:
            f.write(upstream_md(commit, str(dt.date.today()), licence))
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
