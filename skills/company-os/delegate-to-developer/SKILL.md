---
name: delegate-to-developer
description: "Use to hand coding work from secretary to developer profile."
version: 0.1.0
author: internal
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [kanban, delegation, company-os, secretary, developer]
    related_skills: []
---

# Delegate to Developer (secretary → developer via kanban)

Use this when, as the `secretary` profile, you have identified a concrete
piece of engineering work (bugfix, feature, refactor, script) that should be
executed by the `developer` profile instead of yourself.

This skill uses ONLY existing Hermes primitives:
- `kanban_create` tool (already available on the `secretary` profile's `cli`
  toolset via `kanban` in `platform_toolsets`)
- The existing kanban dispatcher (`kanban.review_dispatch`, `dispatch_once`)
  — no new engine, no new queue, no new DB.
- The `developer` Hermes profile, created via
  `hermes profile create developer --clone-from default --description "..."`.

**Do not use `delegate_task` for this.** `delegate_task` spawns an
in-process, ephemeral subagent that cannot itself call kanban tools
(delegate_task children are explicitly blocked from kanban mutations) and
whose result only returns to THIS conversation. `kanban_create` instead
creates a durable, cross-process task that the developer profile's own
dispatcher/worker will pick up independently — this is what you want for
real hand-off between two "employees".

## When to use

- The user (via JARVIS/Telegram/Slack) asked for something that requires
  writing/editing code, running tests, or a multi-step engineering task.
- You (secretary) have clarified scope enough to write a clear title + body
  (acceptance criteria) for the developer.
- You do NOT need the result synchronously in this turn — the developer
  task runs asynchronously; completion/blocked events flow back via the
  existing kanban notify-subscription mechanism if the requester is
  subscribed (`kanban_notify_subs`), or can be checked later with
  `kanban_show`/`kanban_list`.

## Steps

1. Confirm the `developer` profile exists and is described correctly:
   ```
   hermes profile show developer
   ```
   If missing, create it once (already done in this environment):
   ```
   hermes profile create developer --clone-from default --description "..."
   ```

2. From the secretary session, call the `kanban_create` tool with, at
   minimum:
   - `title`: short, action-oriented (e.g. "Fix null-pointer in invoice export")
   - `assignee`: `"developer"` — MUST match the Hermes profile name exactly
   - `body`: full spec — what to build/fix, acceptance criteria, any links
     or file paths already known. The developer worker reads this as its
     entire context; be as complete as you would be briefing a junior
     engineer who has zero conversation history with you.

   Optional but recommended fields (all native to `kanban_create`, see
   `tools/kanban_tools.py` schema — do not invent new ones):
   - `priority`: integer — see "Determining priority" below. Do NOT copy the
     example value from this document verbatim; it must reflect a real
     judgment about THIS request.
   - `max_runtime_seconds`: cap runaway workers.
   - `skills`: force-load a specialist skill on the developer worker, e.g.
     `["github-pr-workflow"]` if the task should end in a PR.
   - `idempotency_key`: pass a stable key (e.g. hash of the request) if this
     delegation might be triggered more than once for the same request —
     `kanban_create` will return the existing task instead of duplicating.
   - `parents`: parent task id(s) — see "Determining dependency" below.

## Determining priority (generic — any orchestrator profile, any assignee)

`priority` is an integer tiebreaker: `kanban_create`'s dispatcher orders
`ready` tasks by `priority DESC, created_at ASC` when multiple tasks compete
for the same assignee (see `hermes_cli/kanban_db.py`, `_dispatch_once_locked`
ready-lane query). It has NO effect when the assignee's queue is empty or
when nothing else is contending — so don't agonize over exact values, but do
apply real judgment using this fixed evaluation order. Stop as soon as a
step gives you a clear signal; later steps only matter as tiebreakers among
otherwise-equal requests.

1. **Urgency (긴급도)** — Is this blocking someone right now, or does it have
   a hard time constraint the requester stated ("need this in the next
   hour", "before the demo at 3pm")? High urgency → priority 8-10.
   Routine, no stated time pressure → priority 3-5. Explicitly "whenever,
   no rush" → priority 1-2.

2. **Importance (중요도)** — Independent of urgency: how much impact does
   this have (revenue, customer-facing breakage, security, blocking other
   people's work) vs. a nice-to-have or internal tool? High-impact but not
   urgent still deserves a priority bump over routine low-impact work.

3. **Assignee's current kanban queue length** — Before setting priority,
   check how much is already queued for this assignee:
   ```
   kanban_list(assignee="developer", status="ready")
   ```
   Read the `count` field. If the queue is empty (count=0), priority barely
   matters — pick from steps 1-2 and move on. If the queue is non-trivial
   (several ready tasks already), a genuinely urgent/important new request
   should outrank the backlog (raise priority); a routine one should NOT
   jump the queue (keep it at or below the existing average — do not
   default to a high number just because you can).

4. **Dependency** — See "Determining dependency" below FIRST if this task
   depends on unfinished work; a task gated by `parents` sits in `todo`
   until its parents are `done` regardless of priority, so don't over-think
   priority for a task that isn't dispatchable yet anyway.

5. **Deadline** — If the requester gave (or implied) a concrete deadline,
   let that dominate over steps 1-3: a task due today outranks a
   same-urgency task due next week even if today's task scored lower on
   step 1. There is no dedicated "deadline" field on `kanban_create` — encode
   the deadline in `body` (so the developer worker sees it) AND reflect its
   urgency in `priority`.

6. **CEO / requester override** — If the requester (the human, via
   JARVIS/Telegram/Slack) explicitly states a priority or says something
   like "this is top priority" / "drop everything else" — honor that
   directly, overriding whatever steps 1-5 would have produced. An explicit
   human instruction always wins over your own estimate.

This same six-step order applies regardless of which profile is doing the
delegating (secretary, or any future orchestrator profile) and regardless
of which profile is the assignee (developer, or any future specialist
profile) — it is not developer-specific or secretary-specific.

## Determining dependency (parents)

Only set `parents` when there is a REAL data/ordering dependency: the new
task needs something a specific other task produces, or another task is
explicitly waiting on this one to exist first. Check with `kanban_show` on
the candidate parent if unsure. Do not invent a dependency just because two
tasks are topically related — `kanban_create`'s dispatcher gates `parents`
tasks in `todo` until every parent reaches `done` (see `recompute_ready` in
`hermes_cli/kanban_db.py`), so an unnecessary dependency silently stalls
work that could have started immediately.

3. Report back to the user (via JARVIS) that the task was created, with the
   task id, e.g.: "Created task t_a91f for @developer — I'll let you know
   when it's done." Do not claim the work is finished; it has only been
   queued.

## "Done" means implemented → self-checked → deployed → confirmed running

The `body` you write is the developer worker's entire briefing — always make
"done" mean the FULL lifecycle, not just "code written". Bake this into the
acceptance criteria of every `kanban_create` body (adapt the specifics to the
task; do not paste this verbatim):

1. **Implement** the change.
2. **Self-check** before declaring done: run it, don't just read it. For a
   service this means actually starting it and hitting the endpoint (curl,
   etc.), not just "the code looks right" — this is what worked for the
   2026-08-14 lotto-API task (built, deployed, curl-tested repeatedly, THEN
   reported done with the evidence in `kanban_complete`'s `summary`).
3. **Deploy** wherever the task specifies (a real server, a repo push, a
   running process) — a task isn't done if the result only exists in a
   scratch dir nobody can reach.
4. **Confirm it's actually running** — re-check after deploy, not just after
   local build. Include the verification evidence (command run + result) in
   `kanban_complete`'s `summary`/`metadata` so a human reading the board
   later can see it was proven, not asserted.

**When to insert a reviewer checkpoint before "done":** for routine,
low-risk work (new script, isolated test app, internal tool) the developer's
own self-check above is enough — do not add process for its own sake. For
anything that touches shared/production infrastructure, costs money, or is
hard to undo (deploying to a real customer-facing service, changing DNS/
firewall rules, rotating credentials), the developer worker should call
`kanban_request_review(reviewer="review", summary="...")` INSTEAD of
`kanban_complete`. `review` is the company-wide review department profile
(2026-08-15) — a different model family from `developer` on purpose, and it
keeps its code-execution tools so it actually runs/tests the change instead
of eyeballing text. This uses the review lane Hermes already ships —
`kanban_request_review` / `kanban_request_changes` — no new engine, no new
agent. Say so explicitly in the task `body` when a task is risky enough to
warrant this (e.g. "this touches the production NAS — request review before
marking done"). `review` approves by creating a follow-on `kanban_create`
task reassigned back to `developer` (there is no separate `release` profile
— retired 2026-08-15, the CEO decided the implementer deploys their own
work after review clears rather than isolating deploy credentials on a
separate profile; see `조직도.md` §4 for the security trade-off this
implies) and completing its own task; it rejects via
`kanban_request_changes`, which returns the task to `developer`
automatically.

4. Do NOT poll in a tight loop. If the requester needs to be notified on
   completion, that is handled by kanban's existing notify-subscription
   mechanism (already wired into the gateway) — do not build a custom
   polling loop.

## Example tool call (illustrative — actual call is via the kanban_create tool, not shell)

This example shows the FIELDS to use, not a value to copy. `priority=7` here
reflects a specific judgment (customer-facing feature, requester said "this
week", empty developer queue at the time) — re-derive your own value from
the six-step process above for every real call; never paste this number.

```
kanban_create(
  title="Add CSV export to invoices page",
  assignee="developer",
  body=(
    "Add a 'Export CSV' button to /invoices. On click, stream all rows "
    "in the current filter as CSV. Acceptance criteria: (1) button visible "
    "only when >=1 invoice is listed, (2) CSV includes columns: id, client, "
    "amount, status, due_date, (3) works for >10k rows without timing out."
  ),
  priority=7,
)
```

## Pitfalls

- `assignee` must be the exact profile name (`developer`), not a display
  name like "Dev Team" — the dispatcher spawns `hermes -p <assignee>`
  verbatim (see `_default_spawn` in `hermes_cli/kanban_db.py`).
- Tasks without an `assignee` are never dispatched — always set it.
- Do not set `workspace_path` unless you specifically want the developer
  to share the secretary's own working directory (this risks the developer
  mutating files the secretary still needs). Omit it for a clean scratch
  workspace (the default).
- The developer profile must actually have credentials (`.env`) configured
  — if cloned via `--clone-from default`, it inherits the same API key as
  secretary, so this is already satisfied in this environment.
- This skill covers ONE-WAY delegation (secretary → developer); the
  developer worker itself decides whether a given task's risk warrants the
  `kanban_request_review` checkpoint above (see "'Done' means..."). Secretary
  does not run a separate approval workflow on top — see `company-os`
  roadmap below for anything beyond that.

## Relationship to the company.yaml roadmap

This skill hard-codes `assignee="developer"` and a manual title/body per
call. It intentionally does NOT invent a routing table, an approval engine,
or a consensus mechanism — those are out of scope for "existing features
only". See the `company-os` skill category description for how a future
`company.yaml` config is expected to generalize this pattern (employee
roster → profile description, routing rules, approval gates, consensus
policy) while still compiling down to the same `kanban_create` /
`hermes profile` primitives this skill uses directly.
