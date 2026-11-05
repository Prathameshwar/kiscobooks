# AGENTS.md

Repository instructions for Codex and other coding agents. Read [CLAUDE.md](CLAUDE.md) before changing application code; it contains the project's architecture, development, security, and testing rules.

## Repository and publishing

- Keep project files at their existing local paths.
- The current GitHub repository is `Prathameshwar/kiscobooks`, branch `main`. Publish the repository root to `origin/main`.
- When committing, stage only the task's files. Preserve concurrent staged and unstaged work from other agents and the user.
- Before publishing, fetch `origin/main` and check for remote changes. Push committed changes with `git push origin main`; never force push or publish unfinished unrelated edits.
