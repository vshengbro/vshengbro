---
name: profile-maintenance
description: Verify the GitHub profile README and automation workflows before committing; use when changing profile text, image assets, or .github workflows.
---

# Profile maintenance

1. Read the root `AGENTS.md`, inspect `README.md`, and preserve the profile's external link intent and generated metrics artifact.
2. Run `python3 .agents/scripts/verify.py policy` after editing this skill, hook, or policy file. This checks Agent Skills frontmatter, entry points, and script configuration.
3. Run `python3 .agents/scripts/verify.py preflight` before committing: it parses all workflow YAML and checks local README targets. Hosted Actions execution and live external URLs need separate verification.
4. Inspect `git diff --cached --check` and staged paths, commit in English Conventional Commit form, and never bypass installed hooks. The repository-local `.agents/hooks/pre-commit` calls the same verifier.

There is no application unit-test target or production source-line denominator. Report those as not applicable rather than fabricate a coverage percentage.
