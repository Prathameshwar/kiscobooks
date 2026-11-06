# AGENTS.md

Repository instructions for Codex and other coding agents. Read [CLAUDE.md](CLAUDE.md) before changing application code; it contains the project's architecture, development, security, and testing rules.

## Repository and publishing

- Keep project files at their existing local paths.
- The current GitHub repository is `Prathameshwar/kiscobooks`, branch `main`. Publish the repository root to `origin/main`.
- When committing, stage only the task's files. Preserve concurrent staged and unstaged work from other agents and the user.
- Before publishing, fetch `origin/main` and check for remote changes. Push committed changes with `git push origin main`; never force push or publish unfinished unrelated edits.

## VM access

For the Ubuntu VM at `201.18.205.54`, this Windows workstation has a saved Bitvise SSH Client profile at `C:\Users\Administrator\Documents\hostinger-vm.tlp`. If plain `ssh` cannot authenticate, use Bitvise's `sexec.exe` with that profile. For example, from PowerShell:

```powershell
& 'C:\Program Files (x86)\Bitvise SSH Client\sexec.exe' -profile='C:\Users\Administrator\Documents\hostinger-vm.tlp' -exitZero -cmd='hostname; id -un; pwd'
```

The profile carries the host key and authentication settings. Confirm the returned host and user before changing the VM. Do not put a password in a command, script, log, or repository file. This path is workstation specific; check that the profile exists before relying on it.
