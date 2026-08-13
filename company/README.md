# company-os

This directory holds the "JARVIS AI Company OS" configuration and operating
procedures. It is intentionally minimal — every mechanism it relies on is a
Hermes feature that already exists (Hermes Profiles, `kanban_create` /
the kanban dispatcher, `platform_toolsets`, skill directories). **No new
task engine, queue, or approval system has been built here.** See the
`hermes-agent-skill-authoring`/`hermes-agent` skills for how Hermes itself
works; this folder only documents how WE use it to run a small "company"
of profiles.

## Structure

```
company-os/
    README.md                          — this file
    company.yaml                       — declarative roster + routing (stub; extend only when a real feature needs it)
    onboarding/
        NEW_EMPLOYEE_CHECKLIST.md      — steps to add a new profile ("employee") without repeating today's mistakes
    secretary/                         — secretary-role specific notes/config (currently just this README pointer)
    delegate-to-developer/             — SKILL.md: secretary → developer hand-off via kanban_create
    hermes-multi-profile-kanban-delegation/ — SKILL.md: general orchestrator/specialist pattern (curator-authored overview)
```

## Design principles (do not violate when extending this folder)

1. **No new engine.** Task creation/queueing/retry/dependency/worker
   assignment is 100% `kanban_create` + the existing kanban dispatcher
   (`hermes_cli/kanban_db.py`). If you think you need a new mechanism here,
   first re-read `docs/hermes-kanban-v1-spec.pdf` and the `kanban_*` tool
   schemas in `tools/kanban_tools.py` — the feature you want probably
   already exists (priority, parents/dependencies, `max_runtime_seconds`,
   `skills`, `max_retries`, `model`/`provider` overrides, `review` status,
   notify-subscriptions).
2. **Employees are Hermes Profiles.** `hermes profile create <name>
   --clone-from default --description "..."`. The `--description` is not
   decoration — Hermes' own kanban decomposer reads it for role-based
   routing (see `hermes profile create --help`).
3. **Delegation is `kanban_create`, not `delegate_task`.** `delegate_task`
   children cannot call kanban tools and their result never leaves the
   calling conversation — it is for ephemeral in-process fan-out, not
   durable cross-profile hand-off. See `delegate-to-developer/SKILL.md` for
   the full rationale.
4. **`company.yaml` is a declaration, not code.** It should only ever list
   facts (who exists, which profile they map to, simple routing rules) that
   a thin, later-built reader translates directly into calls to the
   existing primitives above. Do not add `approval:`, `consensus:`,
   `department:`, `notification:`, `calendar:`, etc. sections until an
   actual skill/tool exists that reads and acts on them — an unused config
   section is a lie about what the system does.
5. **Every profile-level fact must be verified with a real Hermes command**
   before being written down here (see `onboarding/NEW_EMPLOYEE_CHECKLIST.md`
   for the exact commands). Do not assume a new profile inherits toolsets,
   skills, or credentials — it may not.
