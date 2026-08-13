---
name: delegate-to-designer
description: "Use to hand design work from secretary to designer profile."
version: 0.1.0
author: internal
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [kanban, delegation, company-os, secretary, designer]
    related_skills: [delegate-to-developer]
---

# Delegate to Designer (secretary → designer via kanban)

Use this when, as the `secretary` profile, you have identified a concrete
piece of visual design work (banner, marketing image, social post graphic,
UI mockup) that should be executed by the `designer` profile instead of
yourself.

This skill is the design-role sibling of `delegate-to-developer` — same
mechanism, same priority/dependency judgment, different assignee and body
conventions. If you have not read `delegate-to-developer/SKILL.md`, read it
first; this file does not repeat the general rationale.

This skill uses ONLY existing Hermes primitives:
- `kanban_create` tool (already available on the `secretary` profile's `cli`
  toolset via `kanban` in `platform_toolsets`)
- The existing kanban dispatcher (`kanban.review_dispatch`, `dispatch_once`)
  — no new engine, no new queue, no new DB.
- The `designer` Hermes profile, created via
  `hermes profile create designer --clone-from default --description "..."`,
  with `image_gen.openai.model` set to a `gpt-image-2-*` tier and its own
  `OPENAI_API_KEY` in that profile's `.env` (see
  `company-os/onboarding/NEW_EMPLOYEE_CHECKLIST.md`).

**Do not use `delegate_task` for this.** Same rationale as
`delegate-to-developer`: `delegate_task` children cannot call kanban tools
and their result never leaves this conversation. `kanban_create` creates a
durable, cross-process task that designer's own dispatcher/worker picks up
independently.

## When to use

- The user (via JARVIS/Telegram/Slack) asked for a banner, promotional
  image, social media graphic, UI mockup, or similar visual asset.
- You (secretary) have clarified enough to write a clear title + body:
  what the image is for, exact text/copy that must appear on it (verbatim —
  do not paraphrase a requested slogan), format/aspect ratio if stated
  (e.g. "Instagram post" implies square or portrait), and any brand/style
  constraints the requester mentioned.
- You do NOT need the result synchronously in this turn — same async
  hand-off pattern as `delegate-to-developer`.

## Steps

1. Confirm the `designer` profile exists and is set up for image generation:
   ```
   hermes profile show designer
   ```
   If missing, it must be created AND configured for image_gen before any
   delegation will actually produce an image — see
   `company-os/onboarding/NEW_EMPLOYEE_CHECKLIST.md`. A `kanban_create`
   call to a `designer` profile that has no working image_gen credentials
   will spawn a worker that cannot produce the asset.

2. From the secretary session, call the `kanban_create` tool with, at
   minimum:
   - `title`: short, action-oriented (e.g. "Instagram banner — Fall menu launch")
   - `assignee`: `"designer"` — MUST match the Hermes profile name exactly
   - `body`: full brief — purpose (e.g. "Instagram promotional banner"),
     EXACT text/copy to include on the image (quote it verbatim, in the
     original language the requester used), any format hints (square /
     portrait / landscape — see `_SIZES` in
     `plugins/image_gen/openai/__init__.py` for the aspect ratios the
     backend actually supports: landscape 1536x1024, square 1024x1024,
     portrait 1024x1536), and any style/brand notes. The designer worker
     reads this as its entire context.

   Optional but recommended fields (all native to `kanban_create` — see
   `delegate-to-developer/SKILL.md`'s "Determining priority" and
   "Determining dependency" sections, which apply here UNCHANGED — do not
   re-derive a new priority scheme for design work):
   - `priority`: integer — follow the SAME six-step process
     (urgency → importance → assignee's kanban queue length via
     `kanban_list(assignee="designer", status="ready")` → dependency →
     deadline → CEO/requester override) documented in
     `delegate-to-developer/SKILL.md`. That logic is generic across
     profiles by design; do not duplicate or diverge from it here.
   - `max_runtime_seconds`: image generation can take up to ~2 minutes at
     the `gpt-image-2-high` tier — leave headroom (e.g. 5-10 minutes) rather
     than the tight caps that make sense for a fast code task.
   - `parents`: see `delegate-to-developer/SKILL.md`'s "Determining
     dependency" — same rule, no design-specific exception.

3. Report back to the user (via JARVIS) that the task was created, with the
   task id, e.g.: "Created task t_a91f for @designer — I'll let you know
   when the banner is ready." Do not claim the image exists yet.

4. Do NOT poll in a tight loop — same notify-subscription mechanism as
   `delegate-to-developer`.

## Example tool call (illustrative — actual call is via the kanban_create tool, not shell)

This example shows the FIELDS to use, not a value to copy. `priority=6`
here reflects a specific judgment (customer-facing marketing asset,
requester implied "soon" but gave no hard deadline, empty designer queue
at the time) — re-derive your own value from the six-step process in
`delegate-to-developer/SKILL.md` for every real call.

```
kanban_create(
  title="Instagram banner — Fall menu launch",
  assignee="designer",
  body=(
    "Create an Instagram promotional banner (square, 1024x1024) for a "
    "restaurant's fall menu launch. The banner MUST include this exact "
    "text: '가을 신메뉴 출시'. Warm autumn color palette (orange/brown tones), "
    "appetizing food imagery suggestive of seasonal dishes. Save the final "
    "image file in the task workspace and verify it opens correctly before "
    "calling kanban_complete."
  ),
  priority=6,
  max_runtime_seconds=600,
)
```

## Pitfalls

- `assignee` must be exactly `"designer"` — same mechanical requirement as
  `delegate-to-developer` (`_default_spawn` in `hermes_cli/kanban_db.py`
  spawns `hermes -p <assignee>` verbatim).
- Always set `--workspace dir:<absolute-path>` (or the `workspace_path`
  field) when the human actually needs the generated image file afterward.
  The default `scratch` workspace is deleted on task completion — an image
  generated there is gone the moment the task finishes, even though the
  task shows `done`. This is the SAME pitfall documented in
  `delegate-to-developer/SKILL.md`, but it bites harder here because the
  deliverable IS the file, not just information in the summary.
- Quote requested copy/slogans VERBATIM in `body`. Do not paraphrase or
  translate marketing text — the designer worker will render exactly what
  it's given, and a paraphrase becomes a wrong image, not just a wrong
  description.
- `designer` does NOT need `kanban` in `platform_toolsets.cli` (it is a
  specialist/worker profile, not an orchestrator) — do not add it
  needlessly; see `company-os/onboarding/NEW_EMPLOYEE_CHECKLIST.md` step 3.
- This skill only covers ONE-WAY delegation (secretary → designer), same
  scope limitation as `delegate-to-developer`.

## Relationship to the company.yaml roadmap

Same as `delegate-to-developer`: this skill hard-codes `assignee="designer"`
and manual title/body per call, and intentionally implements no routing
table, approval engine, or consensus mechanism of its own. `company.yaml`'s
`routing:` entry for design/banner/image requests is a human-readable
pointer to this skill's existence — it does not (yet) get parsed by any
code. See `company-os/README.md`'s design principles before changing that.
