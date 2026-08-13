# New Employee Checklist (new Hermes profile)

Follow this in order. Every step maps to a real, verifiable Hermes command
— do not skip verification and assume success. Each "Lesson" callout below
is a mistake actually made while setting up `secretary` and `developer` on
2026-08-13; they are here so nobody repeats them.

## 1. Profile creation

```
hermes profile create <name> --clone-from default --description "<one or two sentences: what this employee does, used by the kanban decomposer for role-based routing>"
```

Verify:
```
hermes profile show <name>
```
Expect: Model, Gateway (stopped is fine at this stage), Skills count > 0,
`.env: exists`, `SOUL.md: exists`.

> **Lesson:** `--description` is not cosmetic — pass it every time. It is
> read by the kanban auto-decomposer for role-based routing
> (`hermes profile create --help`).

## 2. API key confirmation

`--clone-from default` copies `.env`, so the new profile inherits the same
provider credentials as `default` automatically. Do NOT assume this without
checking — confirm:

```
hermes -p <name> config check
```
Look for the credential(s) your model provider needs (e.g.
`ANTHROPIC_API_KEY`) NOT showing as `○` (missing). If the new profile is
meant to use a *different* key/provider than default, set it explicitly
with `hermes -p <name> auth add <provider> --type api-key` before anything
else — do not rely on inheritance in that case.

## 3. `platform_toolsets.cli` — confirm `kanban` is present

```
hermes -p <name> config get platform_toolsets.cli
```

If `kanban` is NOT in the list, this profile cannot call `kanban_create`,
`kanban_list`, etc. — those tools are gated by
`_check_kanban_orchestrator_mode()` in `tools/kanban_tools.py`, which
requires `kanban` in the profile's toolset config.

> **Lesson (actually hit today):** `--clone-from default` copies `config.yaml`
> as-is, and `default`'s `cli` toolset list does NOT include `kanban`. The
> `secretary` profile silently had NO kanban tools until this was fixed by
> hand-editing `config.yaml` to add `kanban` under `platform_toolsets.cli`.
> Any profile that needs to CREATE or ROUTE kanban tasks (an "orchestrator"
> role, e.g. secretary) needs this. A profile that only ever EXECUTES tasks
> assigned to it (a "specialist" role, e.g. developer) does NOT need it —
> the dispatcher-spawned worker gets the task-lifecycle tools
> (`kanban_complete`, `kanban_block`, ...) automatically via
> `HERMES_KANBAN_TASK`, no toolset config required.

Fix (if missing, and this profile needs orchestrator-side kanban tools):
edit `<profile-dir>/config.yaml`, add `kanban` to the `platform_toolsets.cli`
list.

## 4. Skill copy confirmation

Skills are NOT shared across profiles automatically, even when cloned from
a source that has them — a skill created or updated AFTER the clone will
never appear in the new profile.

```
hermes -p <name> chat -q "list your available skills" -Q
```
or check the filesystem directly:
```
ls <profile-dir>/skills/<category>/<skill-name>/
```

> **Lesson (actually hit today):** `secretary` was given the
> `delegate-to-developer` skill AFTER the profile was cloned. It was
> invisible — `secretary` defaulted to writing code itself instead of
> delegating, because the skill simply did not exist in
> `profiles/secretary/skills/`. Fix: copy the skill directory manually:
> ```
> mkdir -p <profile-dir>/skills/<category>/<skill-name>
> cp <source-skills-dir>/<category>/<skill-name>/SKILL.md <profile-dir>/skills/<category>/<skill-name>/SKILL.md
> ```
> Then either preload it explicitly for a test
> (`hermes -p <name> chat -q "..." -s <skill-name>`) or trust that skill
> auto-discovery will surface it once it exists on disk for that profile.
> `hermes sync` is for cross-device/cross-org sync, NOT for copying a
> locally-created skill between local profiles — don't reach for it here.

## 5. Gateway confirmation

Decide whether this profile needs a live messaging gateway (Telegram/Slack)
or is purely a kanban worker/orchestrator invoked via CLI/dispatch.

- If it needs a gateway: configure it (`hermes -p <name> setup gateway` or
  manual `.env` token entry) and verify:
  ```
  hermes -p <name> gateway start
  hermes -p <name> status
  ```
- If it does NOT need one (most specialist/worker profiles, e.g.
  `developer`): explicitly note that in this profile's entry in
  `company.yaml` so nobody wastes time debugging a gateway that was never
  supposed to run. `hermes profile list` shows `Gateway: stopped` — that is
  the expected/correct state for a worker-only profile.

## 6. `company.yaml` registration

Add the new employee to `company-os/company.yaml` under `employees:`, and
if it should receive delegated work, add a `routing:` rule pointing to it.
Keep the entry to what's actually true today — do not add
approval/consensus/department fields that no code reads yet (see the
`company-os/README.md` design principles).

## 7. Test — end to end, before declaring the employee "onboarded"

Minimum bar: one real kanban task, created and dispatched, that reaches
`done`.

```
hermes kanban create "<simple test task>" --assignee <name> --priority <n> \
  --workspace "dir:<some throwaway absolute path you will clean up>" --json
hermes kanban dispatch --json
# wait, then:
hermes kanban show <task-id> --json
```
Expect `"status": "done"` and a `latest_summary` that actually describes
real work done (not a spawn/crash failure). If the new profile is an
orchestrator (delegates via a skill like `delegate-to-developer`), also
test the natural-language path end to end:
```
hermes -p <name> chat -q "<a request that should trigger delegation>" -Q --yolo -s <delegation-skill-name>
```
and confirm via `hermes kanban show <task-id>` that the resulting task has
a sensible `assignee`, `priority`, and (if relevant) `parents` — not copied
example values.

Clean up any throwaway workspace directories and test tasks/plugins once
you're done verifying.
