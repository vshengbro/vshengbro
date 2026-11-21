#!/usr/bin/env python3
"""Fail-closed repository policy, tests, and coverage gate (stdlib only)."""
from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import sys
import tempfile
try:
    import tomllib
except ImportError:  # Python 3.9/3.10: install tomli.
    import tomli as tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
HEADINGS = ("## Project", "## Before committing", "## Tests", "## Coverage")


class GateError(Exception):
    pass


def command(args: list[str], *, capture: bool = False) -> str:
    if not isinstance(args, list) or not args or not all(isinstance(a, str) and a for a in args):
        raise GateError(f"invalid argv command: {args!r}")
    print("+", " ".join(args), flush=True)
    try:
        done = subprocess.run(args, cwd=ROOT, check=False, text=True, capture_output=capture)
    except OSError as error:
        raise GateError(f"cannot execute {args[0]}: {error}") from error
    if done.returncode:
        if capture:
            print(done.stderr, file=sys.stderr)
        raise GateError(f"command returned {done.returncode}: {' '.join(args)}")
    return done.stdout if capture else ""


def command_set(value: object, label: str) -> list[list[str]]:
    if not isinstance(value, list):
        raise GateError(f"{label}: expected an array of argv arrays")
    for argv in value:
        if not isinstance(argv, list) or not argv or not all(isinstance(x, str) and x for x in argv):
            raise GateError(f"{label}: invalid argv: {argv!r}")
    return value


def skill_frontmatter(path: Path) -> None:
    match = re.match(r"\A---\n(.*?)\n---\n(.+)\Z", path.read_text(), re.S)
    if not match or not match[2].strip():
        raise GateError(f"{path}: missing YAML frontmatter or Markdown body")
    raw = match[1]
    try:
        import yaml  # Optional; basic frontmatter is validated without it.
    except ImportError:
        fields: dict[str, str] = {}
        for line in raw.splitlines():
            item = re.fullmatch(r"(name|description):\s*(.+)", line)
            if not item or item[1] in fields:
                raise GateError(f"{path}: install PyYAML to validate extended YAML frontmatter")
            fields[item[1]] = item[2].strip().strip("\"'")
    else:
        fields = yaml.safe_load(raw)
    if not isinstance(fields, dict) or fields.get("name") != path.parent.name:
        raise GateError(f"{path}: name must match skill directory")
    name = fields["name"]
    if not isinstance(name, str) or len(name) > 64 or not NAME.fullmatch(name):
        raise GateError(f"{path}: invalid Agent Skills name")
    desc = fields.get("description")
    if not isinstance(desc, str) or not 1 <= len(desc) <= 1024:
        raise GateError(f"{path}: description must be 1..1024 characters")
    if "compatibility" in fields and (not isinstance(fields["compatibility"], str) or not 1 <= len(fields["compatibility"]) <= 500):
        raise GateError(f"{path}: invalid compatibility field")
    if "metadata" in fields and (not isinstance(fields["metadata"], dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in fields["metadata"].items())):
        raise GateError(f"{path}: invalid metadata map")


def validate() -> dict:
    policy_path = ROOT / ".agents/policy.json"
    if not policy_path.is_file():
        raise GateError("missing .agents/policy.json")
    policy = json.loads(policy_path.read_text())
    if policy.get("schema_version") != 1 or policy.get("project") != ROOT.name:
        raise GateError("policy schema/project mismatch")
    if policy.get("kind") not in ("rust", "data", "site", "python", "docs"):
        raise GateError("unknown policy kind")
    if not isinstance(policy.get("source_patterns"), list) or not policy["source_patterns"]:
        raise GateError("source_patterns must be nonempty")
    checks = policy.get("checks", {})
    for part in ("style", "unit"):
        command_set(checks.get(part), f"checks.{part}")
    doc = ROOT / "AGENTS.md"
    if not doc.is_file():
        raise GateError("missing exact-case root AGENTS.md")
    text = doc.read_text()
    if not all(heading in text for heading in HEADINGS):
        raise GateError("AGENTS.md lacks required project/commit/tests/coverage headings")
    for link in (".agents/skills/", ".agents/hooks/pre-commit", ".agents/scripts/verify.py"):
        if link not in text:
            raise GateError(f"AGENTS.md lacks reference to {link}")
    skills = sorted((ROOT / ".agents/skills").glob("*/SKILL.md"))
    if not skills:
        raise GateError("no .agents/skills/*/SKILL.md")
    for path in skills:
        skill_frontmatter(path)
    hook = ROOT / ".agents/hooks/pre-commit"
    if not hook.is_file() or "verify.py staged" not in hook.read_text():
        raise GateError("repository hook must invoke verify.py staged")
    if policy["kind"] == "rust":
        manifest = tomllib.loads((ROOT / "Cargo.toml").read_text())
        for section, value in (("[workspace.package]", manifest.get("workspace", {}).get("package")), ("[package]", manifest.get("package"))):
            if value and "exclude" in value and not {"AGENTS.md", ".agents"}.issubset(set(value["exclude"])):
                raise GateError(f"{section} excludes must contain AGENTS.md and .agents")
        if not any(value and "exclude" in value for value in (manifest.get("workspace", {}).get("package"), manifest.get("package"))):
            raise GateError("Rust package needs Cargo exclude entries")
    cover = policy.get("coverage", {})
    if not isinstance(cover, dict):
        raise GateError("missing coverage policy")
    typ = cover.get("type")
    if policy["kind"] == "rust" and typ != "llvm-cov":
        raise GateError("Rust coverage must use llvm-cov")
    if policy["kind"] == "data" and typ != "validated-files":
        raise GateError("dataset coverage must count validated files")
    if typ == "llvm-cov":
        cmds = command_set([cover.get("command")], "coverage.command")
        if "{report}" not in cmds[0]:
            raise GateError("coverage.command needs {report} placeholder")
        minimum = cover.get("minimum_changed_lines_percent")
        if isinstance(minimum, bool) or not isinstance(minimum, (int, float)) or not 0 <= minimum <= 100:
            raise GateError("coverage changed-line percentage must be 0..100")
    elif typ == "command":
        command_set(cover.get("commands"), "coverage.commands")
    elif typ == "not-applicable":
        if not cover.get("reason"):
            raise GateError("not-applicable coverage needs concrete reason")
    elif typ != "validated-files":
        raise GateError("unsupported coverage policy")
    print(f"policy: {ROOT.name} OK", flush=True)
    return policy


def staged() -> list[str]:
    raw = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"], cwd=ROOT, check=True, capture_output=True).stdout
    return [item.decode("utf-8", "surrogateescape") for item in raw.split(b"\0") if item]


def changed_rust_lines(paths: list[str]) -> dict[str, set[int]]:
    changed: dict[str, set[int]] = {}
    for path in paths:
        if not path.endswith(".rs") or path.startswith("tests/") or "/tests/" in path:
            continue
        spans = changed.setdefault(path, set())
        for row in command(["git", "diff", "--cached", "--unified=0", "--", path], capture=True).splitlines():
            match = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", row)
            if match:
                start, count = int(match[1]), int(match[2] or "1")
                spans.update(range(start, start + count))
    return changed


def rust_coverage(policy: dict, paths: list[str]) -> None:
    with tempfile.TemporaryDirectory(prefix="agent-coverage-") as temp:
        target = str(Path(temp) / "coverage.lcov")
        args = [target if item == "{report}" else item for item in policy["coverage"]["command"]]
        command(args)
        report = Path(target)
        if not report.is_file():
            raise GateError("cargo llvm-cov returned 0 but did not write LCOV")
        rows = report.read_text().splitlines()
    files: dict[str, dict[int, bool]] = {}
    current: str | None = None
    for row in rows:
        if row.startswith("SF:"):
            try:
                current = str(Path(row[3:]).resolve().relative_to(ROOT))
            except ValueError:
                current = None
            if current is not None:
                files.setdefault(current, {})
        elif row.startswith("DA:") and current is not None:
            try:
                line, hits, *_ = row[3:].split(",")
                number = int(line)
                files[current][number] = files[current].get(number, False) or int(hits) > 0
            except (ValueError, IndexError) as error:
                raise GateError(f"malformed LCOV row: {row}") from error
        elif row == "end_of_record":
            current = None
    total = sum(map(len, files.values()))
    covered = sum(sum(lines.values()) for lines in files.values())
    if total == 0:
        raise GateError("LCOV has zero executable lines")
    print(f"overall line coverage: {covered}/{total} ({covered / total:.1%})")
    measured = 0
    hits = 0
    for path, lines in changed_rust_lines(paths).items():
        if lines and path not in files:
            raise GateError(f"changed Rust source omitted from LCOV: {path}")
        for number in lines:
            if number in files.get(path, {}):
                measured += 1
                hits += files[path][number]
    if measured:
        actual = 100 * hits / measured
        floor = policy["coverage"]["minimum_changed_lines_percent"]
        print(f"changed executable line coverage: {hits}/{measured} ({actual:.2f}%), minimum {floor}%")
        if actual < floor:
            raise GateError("changed executable line coverage below minimum")
    else:
        print("changed executable line coverage: N/A (no staged instrumented lines)")


def data_coverage() -> None:
    raw = subprocess.run(["git", "ls-files", "-z", "--", "*.json", "*.jsonl"], cwd=ROOT, capture_output=True, check=True).stdout
    paths = [item.decode("utf-8", "surrogateescape") for item in raw.split(b"\0") if item and not item.startswith(b".agents/")]
    if not paths:
        raise GateError("no tracked JSON/JSONL files")
    for path in paths:
        data = (ROOT / path).read_text()
        if path.endswith(".jsonl"):
            if data and not data.endswith("\n"):
                raise GateError(f"{path}: missing final newline")
            for number, line in enumerate(data.splitlines(), 1):
                if not line or not isinstance(json.loads(line), dict):
                    raise GateError(f"{path}:{number}: JSONL line must be an object")
        else:
            json.loads(data)
    print(f"validated-file coverage: {len(paths)}/{len(paths)} (100%)")


def coverage(policy: dict, paths: list[str]) -> None:
    cover = policy["coverage"]
    if cover["type"] == "llvm-cov":
        rust_coverage(policy, paths)
    elif cover["type"] == "validated-files":
        data_coverage()
    elif cover["type"] == "command":
        for args in cover["commands"]:
            command(args)
    else:
        print("source-line coverage not applicable:", cover["reason"])


def preflight(policy: dict, paths: list[str]) -> None:
    for group in ("style", "unit"):
        for args in policy["checks"][group]:
            command(args)
    coverage(policy, paths)


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in ("policy", "staged", "preflight", "coverage"):
        raise GateError("usage: verify.py {policy|staged|preflight|coverage}")
    policy = validate()
    mode = sys.argv[1]
    if mode == "policy":
        return
    paths = staged()
    if mode == "coverage":
        coverage(policy, paths)
    elif mode == "preflight":
        preflight(policy, paths)
    else:
        selected = [p for p in paths if not p.startswith(".agents/") and p != "AGENTS.md" and any(fnmatch.fnmatch(p, pattern) for pattern in policy["source_patterns"])]
        if selected:
            unstaged = set(command(["git", "diff", "--name-only"], capture=True).splitlines())
            if unstaged.intersection(selected):
                raise GateError("staged source differs from worktree: " + ", ".join(sorted(unstaged.intersection(selected))))
            print("staged source:", ", ".join(selected))
            preflight(policy, paths)
        else:
            print("no staged source; policy checks passed")


if __name__ == "__main__":
    try:
        main()
    except (GateError, OSError, json.JSONDecodeError, tomllib.TOMLDecodeError) as error:
        print(f"agent policy FAIL: {error}", file=sys.stderr)
        sys.exit(1)
