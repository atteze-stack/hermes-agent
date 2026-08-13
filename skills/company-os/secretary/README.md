# secretary role notes

This folder holds secretary-role-specific operating notes. It is not a
skill on its own — the actual delegation procedure lives in
`../delegate-to-developer/SKILL.md`. This file only records facts specific
to running the `secretary` profile that were confirmed by hand during
setup (2026-08-13) so they don't need re-discovering.

## Confirmed requirements for the `secretary` profile

- Must have `kanban` in `platform_toolsets.cli` in its `config.yaml`, or
  `kanban_create`/`kanban_list`/etc. are not exposed as tools at all
  (`_check_kanban_orchestrator_mode()` in `tools/kanban_tools.py` gates on
  this). `--clone-from default` does NOT add this automatically — default's
  `cli` toolset list does not include `kanban`.
- Skills are NOT shared across profiles automatically. A skill created
  globally (`~/.hermes/skills/...`) is invisible to a profile created via
  `--clone-from` unless it existed in the source profile's `skills/` at
  clone time. New skills must be copied into
  `~/.hermes/profiles/secretary/skills/<category>/<name>/SKILL.md`
  explicitly, or preloaded per-session with `-s <skill-name>` (which still
  requires the skill file to exist in that profile's own skills tree —
  `hermes chat -s <name>` errors with "Unknown skill(s)" otherwise).
- `hermes -p secretary chat -q "..."` is the correct invocation to test
  secretary end-to-end (the `-p <profile>` flag comes before the
  subcommand, e.g. `hermes -p secretary chat -q "..."`, not
  `hermes chat -p secretary -q "..."`).

## Behavior actually observed in this environment

- Without the `delegate-to-developer` skill loaded, secretary defaulted to
  writing code itself instead of delegating (confirmed 2026-08-13: it
  started a FastAPI project directly in response to "Hello World API를
  만들어줘"). Loading the skill (`-s delegate-to-developer`, after copying
  it into the profile's skills tree) fixed this — secretary then called
  `kanban_create` with `assignee="developer"` correctly.
- See `../onboarding/NEW_EMPLOYEE_CHECKLIST.md` for the full checklist this
  incident is folded into.
