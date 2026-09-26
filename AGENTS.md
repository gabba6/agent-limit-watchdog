# Rules for coding agents in this repository

Entry points: [README.md](README.md) (what and how), [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) (how it works).
If `privat/PLAN.md` exists, read it first: it is the maintainer's local status (never committed).

## Hard rules

- **Never spend money:** no extra usage, credits or rate-limit reset credits. Never operate limit or purchase
  menus by keystroke. Nothing in the code may select a menu option.
- **Test without usage:** no model calls for testing (`claude -p`, `codex exec`), except for an explicitly
  planned short live test. Default: fixtures, `./waechter.py simulate …`, `./waechter.py tick --dry-run`.
- **Global configuration** (`~/.claude/settings.json`, `~/.codex/hooks.json`, LaunchAgents) only through
  `install.sh` / `uninstall.sh`, always with a backup. Never change hooks that belong to other tools (e.g. Orca).
- **No secrets** in files, logs or chats. The ntfy topic lives only in the macOS keychain; mention only the
  service name `limit-waechter-ntfy`.
- **Other sessions:** only address Orca terminals whose `agentIdentity` is `claude` or `codex`; read the screen
  before every send; at most 2 automatic continuations per session and window.
- **Deleting** only with explicit approval of the maintainer.
- **The maintainer's live installation must keep working:** larger refactors happen in a separate working copy
  and are switched over only after the tests pass.

## Git and publishing

- Remote `origin` = public GitHub repository. Push only `main` (and release tags), only after the full test
  suite passes and a privacy scan found no personal data. Never push `privat-historie`.
- `privat/` and `config.local.toml` are never committed (see `.gitignore`).
- Stage files by explicit path only (never stage everything at once). One commit per checked milestone.

## Code conventions

- Python standard library only (`/usr/bin/python3` is 3.9 – no `tomllib`, no pip packages).
- Identifiers and comments are German (historical); every user-facing text goes through `lw/sprache.py` with
  both `de` and `en` and identical placeholders (checked by `tests/test_sprache.py`).
- New screen patterns in `lw/bildschirm.py` need a fixture in `tests/fixtures/bildschirme/` and a test case.

## Orchestration for multi-agent runs (maintainer's decision, 2026-09-26)

Applies to all Dynamic Workflows and subagents in this project until the maintainer changes it:

- Model: **Opus 5.5 for all agents**, including reviews.
- Effort: **low** for implementers (including fixers), **medium** for reviewers.
- Size: at most **8 agents per milestone**; the main session is the integrator and does the final review.
- Stop after every milestone with a short report; start the next milestone only when the maintainer says so.
  Stop before any new decision or approval.
