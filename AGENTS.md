# Repository agent guide

## Project
This repository is the `vshengbro` GitHub profile: `README.md` is the published profile page, `metrics.svg` is an image artifact, and `.github/workflows/` updates metrics and timestamps. There is no application runtime, package manager, or source tree. Keep the profile content and its links accurate; never embed credentials or generated secrets.

## Before committing
Inspect `git status --short` and the staged diff. Do not stage unrelated edits or workflow-generated artifacts by accident. Run `python3 .agents/scripts/verify.py preflight` and `git diff --cached --check`, then let the installed Git hooks run without bypasses. Commit subjects, bodies, and PR text are English; use a Conventional Commit subject. Check any changed external links against the actual target before publishing.

## Tests
The repository has no executable unit under test. The preflight script validates the root Markdown, the Agent Skill, policy wiring, workflow YAML, and local links. A changed workflow needs its own GitHub Actions execution; local checks do not prove hosted automation ran.

## Coverage
Source-line unit coverage is not applicable to a profile-only repository with no production code. Report the file types and checks performed; never invent a numeric unit-test percentage. The policy script fails rather than reporting a test it did not run.

Use `.agents/skills/profile-maintenance/SKILL.md` for the specific maintenance workflow. The installed global Git hook dispatches `.agents/hooks/pre-commit`, which runs `.agents/scripts/verify.py staged` without replacing other hooks.
