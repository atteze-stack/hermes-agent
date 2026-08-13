---
name: hermes-multi-profile-kanban-delegation
description: "Use to set up Hermes profiles delegating work via kanban."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [kanban, profiles, delegation, multi-agent, company-os]
    related_skills: [hermes-agent, cross-model-independent-review, sdlc-review]
---

# Hermes Multi-Profile Kanban Delegation

## When to Use

You are building or operating a setup where one Hermes profile (an
"orchestrator" / "secretary" role) hands durable, cross-process work to
another Hermes profile (a "specialist" / "developer" role) via the
`kanban_create` tool or `hermes kanban create` CLI — NOT via `delegate_task`.
This is the pattern for anything shaped like "multiple semi-autonomous
Hermes profiles acting as employees, coordinating through a shared task
board." Any user-specific routing skill (e.g. a hand-authored
"delegate-to-X" skill wiring one named profile to another) sits ON TOP of
these mechanics — this skill is the reusable substrate underneath it, and
is the right place to check when the substrate itself misbehaves, even if
the user-owned routing skill on top of it can't be edited by you (protected
— see Pitfalls).

`delegate_task` and `kanban_create` solve different problems — verified
against `tools/delegate_tool.py` and `hermes_cli/kanban_db.py` in-session:
`delegate_task` spawns an ephemeral, in-process subagent whose result only
returns to the calling conversation, and its children are explicitly
blocked from calling kanban tools at all (`_reject_delegated_child_mutation`
in `tools/kanban_tools.py`). `kanban_create` instead writes a durable SQLite
row that a target profile's own dispatcher/worker process picks up
independently, in its own process, on its own schedule. Use `kanban_create`
whenever the hand-off needs to survive past this conversation or be picked
up by a genuinely separate profile identity.

## Setup Checklist (in order)

1. Create profiles with a role description — the description field is not
   cosmetic, `hermes profile create --help` documents it as consumed by the
   kanban decomposer for role-based routing:
   ```
   hermes profile create <name> --clone-from default --description "..."
   ```
2. **Explicitly enable the `kanban` toolset on the delegating (orchestrator)
   profile.** `--clone-from default` does NOT carry this — Hermes' default
   `platform_toolsets.cli` list has no `kanban` entry. Without it,
   `kanban_create`/`kanban_list`/etc. are invisible to that profile's agent,
   and the agent will silently do the work itself instead of delegating —
   there is no error, so this is easy to miss in testing. Fix: edit that
   profile's own `config.yaml` (find it with `hermes -p <name> config path`)
   and add `kanban` under `platform_toolsets.cli:`.
3. Initialize the board once: `hermes kanban init`.
4. Any skill that should govern how the orchestrator profile delegates
   (assignee choice, priority policy, body format) must live under THAT
   profile's own `skills/<category>/<name>/` directory, not just the
   global/default one. Each Hermes profile has its own independent
   `skills/` tree, populated at `profile create` time — a skill authored
   or edited AFTER a profile already exists is invisible to that profile
   until you copy the skill directory into its tree (or the profile is
   recreated/cloned again). For one-off manual verification you can force
   preload with `hermes -p <profile> chat -q "..." -s <skill-name>`, but
   that is a test-only stopgap, not how it will trigger unprompted in real
   usage.
5. Tasks only dispatch with an explicit `assignee` matching a real Hermes
   profile name exactly (case/spelling) — `_default_spawn` in
   `hermes_cli/kanban_db.py` runs `hermes -p <assignee> ...` verbatim.
6. Either run `hermes gateway start` (dispatches automatically on an
   interval) or manually tick `hermes kanban dispatch` after creating a
   task — a task sitting in `ready` does nothing until a dispatch tick
   claims it.

## Choosing `--workspace` / `workspace_kind`

- `scratch` (default) — fresh tmp dir, **deleted when the task completes**.
  Fine for verification-only tasks; wrong if you or the user need to
  inspect the output afterward.
- `dir:<absolute path>` — persists. The directory must already exist
  before you create the task; `dir:` does not create it for you
  (`mkdir -p` it first).
- `worktree` / `worktree:<path>` — git worktree, for tasks inside an
  existing repo.

## Priority: don't cargo-cult the example value

`priority` is a dispatch-order tiebreaker among tasks competing for the
same assignee — it is not a general "importance" field, and it has no
effect when only one task is queued. In live testing, an orchestrator
profile copied `priority=5` from a routing skill's example call without
checking the actual queue, and admitted under questioning that the number
had no basis. Before setting a non-default priority, check the assignee's
actual backlog first (`hermes kanban list` / `kanban_list` filtered to
that assignee) and only raise it when there's a concrete reason (explicit
urgency, or it blocks other pending work). Omit `priority` when there's no
such signal rather than inventing a number.

## CLI syntax gotcha

`hermes -p <profile>` is a global flag but the command still needs a
subcommand after it: `hermes -p secretary chat -q "..."` works;
`hermes -p secretary -q "..."` (omitting `chat`) fails argument parsing —
the parser tries to interpret the query text itself as the subcommand
name and errors with "invalid choice".

## The kanban engine already has retry, dependencies, and concurrency control

Before building any custom queue/retry/dependency logic on top of kanban,
check `references/kanban-engine-mechanics.md` — it summarizes what
`hermes_cli/kanban_db.py` already implements (circuit-breaker retry via
`consecutive_failures`/`max_retries`, parent/child dependency gating via
`task_links`, per-assignee concurrency caps, AI-driven review lane). Most
"we need to build X" instincts for a kanban-based multi-profile setup are
already covered natively; verify against that reference before writing new
plumbing.

## Verifying a third-party Hermes plugin's claimed workflow actually fires

If a plugin claims to enforce a workflow (e.g. injecting a mandatory
bootstrap skill at session start via a `pre_llm_call`/`on_session_start`
hook), don't assume it works just because install succeeded and
`hermes plugins list` shows it enabled. Ask the target profile directly
in a fresh session whether it saw the injected context and, critically,
whether it TRUSTED it as a real instruction versus treating it as
plain text appended to the user message. A hook that appends free text to
the first user turn is not the same as a system-level instruction, and a
model can (correctly, as a prompt-injection defense) decline to treat
self-asserting "you must follow this" text embedded in a message as
authoritative. See `references/plugin-hook-trust-verification.md` for the
concrete technique and a worked example.

## A "running"/"done" specialist task can still have silently produced the wrong deliverable

A worker profile completing a kanban task without error does NOT mean it
used the tool you assumed it would use. If a specialist profile's task
depends on a capability tool (image_gen, a paid API-backed tool, etc.)
that is gated behind a `check_fn` readiness check, and that check fails,
the tool is simply absent from the model's schema for that turn — there is
no error, no warning surfaced to the kanban task or its summary, the agent
just does something else that looks plausible (e.g. writing an HTML mockup
instead of calling image_gen to make a real image) and reports success.
`hermes profile show <name>` and even `hermes kanban show <task>` will look
completely healthy in this failure mode. Before trusting delegated output
that depends on a gated tool, verify the check_fn actually passes for that
specific profile — see `references/capability-tool-readiness-check.md` for
the concrete two-part check (config key presence AND credential validity)
worked out against the `image_gen` tool, which generalizes to any
`check_fn`-gated tool.

## Pitfalls

- **A skill wiring one specific profile to another (e.g. a hand-authored
  "delegate-to-<role>" skill) is very likely user-owned, not
  curator-managed** — if you (an autonomous curator pass) try to patch it
  and get a "not curator-managed" / "user-owned" refusal, don't force it.
  Recommend `hermes curator adopt <name>` to the user, or land the fix
  here instead if it's about the underlying mechanics rather than that
  skill's specific routing logic.
- `hermes plugins install <owner>/<repo> --enable` run with a leading
  `-p <profile>` global flag installs into THAT profile's own isolated
  `plugins/` directory (under its own `HERMES_HOME`) — verified by
  installing into one profile and confirming the sibling default/other
  profiles' plugin directories were untouched. Good for testing a plugin
  on one "employee" without affecting others.
- A "Warning: doesn't contain plugin.yaml/plugin.json/__init__.py" message
  during `hermes plugins install` can be a false alarm if the repo nests
  its manifest under a dotted directory (e.g. `.hermes-plugin/`) — confirm
  with `hermes plugins list` afterward (look for the plugin listed
  `enabled` with a real version) before concluding the install failed.

## Related skills

- `hermes-gateway-operations` — covers whether a profile's messaging
  platform adapter (Telegram/Slack/etc) is actually connected at all
  (polling conflicts, log-based diagnosis). Check that skill FIRST if a
  profile that should be reachable via a bot isn't responding — this
  skill assumes the channel is already up and only covers kanban
  task hand-off between profiles.
- `cross-model-independent-review` — for getting an independent second
  opinion FROM a different model/provider; unrelated mechanism to kanban
  delegation but often used alongside it (e.g. reviewing a delegation
  plan before executing it).
- `sdlc-review` — governs the review LANE once a task reaches `review`
  status (approve / request changes / escalate). This skill covers
  getting tasks created and dispatched in the first place; `sdlc-review`
  covers what happens after an implementer requests review.
