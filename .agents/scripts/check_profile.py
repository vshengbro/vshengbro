#!/usr/bin/env python3
"""Validate profile Markdown local references and automation YAML."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]


def main() -> None:
    try:
        import yaml
    except ImportError as error:
        raise SystemExit("PyYAML is required for workflow validation; install pyyaml") from error
    workflows = sorted((ROOT / ".github/workflows").glob("*.y*ml"))
    if not workflows:
        raise SystemExit("no workflow YAML files found")
    for path in workflows:
        value = yaml.safe_load(path.read_text())
        if not isinstance(value, dict) or not isinstance(value.get("jobs"), dict) or not value["jobs"]:
            raise SystemExit(f"{path}: expected a nonempty jobs mapping")
    readme = (ROOT / "README.md").read_text()
    if not readme.strip():
        raise SystemExit("README.md is empty")
    count = 0
    for target in re.findall(r"(?:href|src)=[\"']([^\"']+)[\"']|!?\[[^]]*\]\(([^)]+)\)", readme):
        link = next((item for item in target if item), "").split("#", 1)[0].split("?", 1)[0]
        if not link or link.startswith(("http:", "https:", "mailto:", "data:", "//", "#")):
            continue
        local = (ROOT / unquote(link)).resolve()
        if not local.is_relative_to(ROOT) or not local.is_file():
            raise SystemExit(f"README.md: missing or outside repository: {link}")
        count += 1
    print(f"profile structure: {len(workflows)} workflow YAML files parsed, {count} local references verified")


if __name__ == "__main__":
    main()
