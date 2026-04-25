#!/usr/bin/env python3
"""Regenerate docs/feature-flags.md from config.py inline annotations.

Run after adding, removing, or moving feature flags in
``backend/app/core/config.py``. The script reads the ``# ── Feature Flags ──``
section, walks it linearly while tracking the current ``--- Section ---``
header, and emits a markdown reference with a quick-reference table and
per-flag detail.

Usage:
    python3 backend/scripts/generate_feature_flags_doc.py

Writes to:
    docs/feature-flags.md (overwrites)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "backend" / "app" / "core" / "config.py"
OUTPUT_PATH = REPO_ROOT / "docs" / "feature-flags.md"


def parse_flags(source: str) -> list[dict]:
    lines = source.splitlines(keepends=True)

    start_idx = next(
        (i for i, line in enumerate(lines) if "── Feature Flags ──" in line),
        None,
    )
    if start_idx is None:
        sys.exit("FATAL: '── Feature Flags ──' header not found in config.py")

    end_idx = next(
        (
            i
            for i, line in enumerate(lines[start_idx + 1:], start_idx + 1)
            if line.strip().startswith("# ──") and "Feature" not in line
        ),
        len(lines),
    )

    section_lines = lines[start_idx:end_idx]
    flags: list[dict] = []
    current_section = "Uncategorized"
    buffered_comments: list[str] = []

    for raw_line in section_lines:
        line = raw_line.strip()
        if line.startswith("#"):
            body = line.lstrip("#").strip()
            section_match = re.match(r"^---\s+(.+?)\s+---$", body)
            if section_match:
                current_section = section_match.group(1)
                buffered_comments = []
            else:
                buffered_comments.append(body)
            continue

        flag_match = re.match(r"(FEATURE_[A-Z0-9_]+):\s*bool\s*=\s*(\w+)", line)
        if flag_match:
            depends = []
            required = []
            for c in buffered_comments:
                if c.startswith("Depends on:"):
                    depends.append(c.replace("Depends on:", "").strip())
                elif c.startswith("Required by:"):
                    required.append(c.replace("Required by:", "").strip())
            flags.append(
                {
                    "name": flag_match.group(1),
                    "default": flag_match.group(2),
                    "section": current_section,
                    "depends": depends,
                    "required": required,
                }
            )
            buffered_comments = []
            continue

        if line:
            buffered_comments = []

    return flags


def render(flags: list[dict]) -> str:
    out: list[str] = []
    out.append("# Feature Flags Reference")
    out.append("")
    out.append(
        "Auto-generated from inline annotations in "
        "`backend/app/core/config.py`. All feature flags default to `false` and "
        "must be explicitly set per environment. Re-run "
        "`backend/scripts/generate_feature_flags_doc.py` when flags are added or "
        "removed."
    )
    out.append("")
    out.append(
        "> Don't enable a flag in production without running its dependent "
        "migrations, verifying staging behavior, and updating the runbook for "
        "the affected feature."
    )
    out.append("")
    out.append("## Quick Reference")
    out.append("")
    out.append("| Flag | Default | Section | Depends on |")
    out.append("|------|---------|---------|------------|")
    for f in flags:
        deps_short = ", ".join(f["depends"]) if f["depends"] else "—"
        out.append(
            f"| `{f['name']}` | `{f['default'].lower()}` | {f['section']} | {deps_short} |"
        )
    out.append("")
    out.append("## Detail")
    out.append("")

    last_section = None
    for f in flags:
        if f["section"] != last_section:
            out.append(f"### {f['section']}")
            out.append("")
            last_section = f["section"]
        out.append(f"#### `{f['name']}`")
        out.append("")
        out.append(f"- **Default:** `{f['default'].lower()}`")
        if f["depends"]:
            out.append(f"- **Depends on:** {', '.join(f['depends'])}")
        for r in f["required"]:
            out.append(f"- **Required by:** {r}")
        out.append(
            f"- **Rollback:** Set `{f['name']}=false`, restart backend. No "
            "migration to revert."
        )
        out.append("")

    out.append("## Enabling a flag — checklist")
    out.append("")
    out.append(
        "1. Verify each `Depends on:` entry is satisfied — env var set, related "
        "flag enabled, migration applied."
    )
    out.append(
        "2. In staging: set the flag, restart, exercise the feature manually and "
        "via load test."
    )
    out.append(
        "3. If staging is clean for ≥48h, enable in prod via Render dashboard "
        "env vars."
    )
    out.append("4. Watch Sentry, BetterStack, and `/api/health` for regressions.")
    out.append(
        "5. If something breaks: flip back to `false`, restart. There's no data "
        "to roll back."
    )
    out.append("")

    return "\n".join(out)


def main() -> None:
    source = CONFIG_PATH.read_text()
    flags = parse_flags(source)
    if not flags:
        sys.exit("FATAL: no flags extracted — config.py format may have changed.")
    OUTPUT_PATH.write_text(render(flags))
    print(f"wrote {OUTPUT_PATH} ({len(flags)} flags)")


if __name__ == "__main__":
    main()
