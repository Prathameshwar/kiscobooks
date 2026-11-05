# AGENTS.md

Repository instructions for Codex and other coding agents. Read [CLAUDE.md](CLAUDE.md) before changing application code; it contains the project's architecture, development, security, and testing rules.

## Mandatory: preserve local paths and publish through the folder mapping

These rules apply to this configured workspace at `C:\Pratham\Personal\softwares\bill`.

- Keep all existing project files and folders at their original local paths. Do not create a local `bll-pc` or `Pratham-POCs` folder, move or copy the project, or add junctions/symlinks to match GitHub's layout.
- GitHub destination: `O230008-CTO-10006ZE690/Pratham-POCs`, branch `main`, folder `bll-pc/`. The configured SSH remote is `git@github-hcl:O230008-CTO-10006ZE690/Pratham-POCs.git`.
- **Use `git publish` for publishing. Never use a direct `git push` from this workspace**, including explicit refspecs or force pushes. The local Git alias runs `.git/bill-publish.py`, which maps the committed local root into GitHub's `bll-pc/` folder and preserves the repository's other contents.
- The local branch and remote `main` intentionally have different directory layouts. Do not set an upstream to `origin/main`, pull/merge/rebase that branch into the local branch, reset the workspace to it, or change `push.default=nothing` to bypass the publishing workflow. Fetching for inspection is allowed.
- When committing and publishing are part of the authorized task, stage only that task's files. Other agents and the user may be editing concurrently; preserve their staged and unstaged work. Publish commits, not unfinished unrelated edits.
- Use this sequence with the actual task files:

  ```powershell
  git add -- path/to/changed-file
  git commit -m "Describe the completed change"
  git publish --dry-run
  git publish
  ```

- If the alias/helper is missing, or publishing reports that GitHub's `bll-pc` changed, stop publishing and report the condition. Continue independent local work. Do not fall back to a direct push, overwrite the publishing state, or rerun `--repair-initial-layout`.
- Publishing decision (2026-10-23): the user renamed the GitHub folder from `bill-poc/` to `bll-pc/`. The helper records `project_folder` in publication state; future `git publish` commands use that destination. The local workspace remains at its original path.
- The publishing alias, helper, and state live in local `.git` metadata and are not installed by cloning. In another checkout, inspect its configuration before applying this workflow; do not restructure files or invent a replacement mapping.
