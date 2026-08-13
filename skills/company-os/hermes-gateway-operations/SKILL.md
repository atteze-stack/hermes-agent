---
name: hermes-gateway-operations
description: "Bot down? Diagnose gateway, fix polling conflicts."
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [gateway, telegram, slack, messaging, profiles, diagnostics, company-os]
    related_skills: [hermes-agent, hermes-multi-profile-kanban-delegation]
---

# Hermes Gateway Operations

## When to Use

Any time you need to verify or fix a Hermes profile's connection to a messaging
platform (Telegram, Slack, Discord, WhatsApp, etc.) in a multi-profile setup —
e.g. "did the secretary/developer/designer profile's bot actually receive this
message", "is the gateway really up", "why did a message never get a reply".
This is the operational layer UNDER `hermes-multi-profile-kanban-delegation`:
that skill covers task hand-off between profiles once they're reachable; this
skill covers whether a profile's own external channel (its bot identity) is
actually connected at all.

## `hermes gateway status` process-alive check is necessary but not sufficient

`hermes -p <profile> gateway status` only reports whether the gateway PROCESS
is running (`✓ Gateway process running (PID: ...)`). A process can be alive
while its platform adapter (e.g. Telegram) is disconnected and silently
retrying in the background — `status` will still say "running" with zero
indication the bot can't currently receive messages. Always cross-check the
adapter's own connection state, not just process liveness:

1. `tail -N "<profile>/logs/gateway.log"` — look for the adapter's own
   connect/disconnect lines (`[Telegram] Connected...` / `Disconnected...` /
   `ERROR ... Fatal telegram adapter error`) near the current time, not just
   at gateway startup.
2. For Telegram specifically, call `getWebhookInfo` via the bot token to check
   `pending_update_count` (updates queued server-side, unconsumed) — a
   non-zero count with no adapter activity in the log is a strong signal the
   poller is down or stuck.
3. To check whether a specific inbound message actually reached the profile,
   grep `gateway.log` for `inbound message:` lines with that user/chat id —
   they log the exact text received, so you can compare against what the
   user says they sent, rather than assuming "no reply" means "not received".

## The Telegram "polling conflict" failure pattern

Symptom in `gateway.log`:
```
[Telegram] Telegram polling conflict (N/5) — previous session still held
open on Telegram's servers. Waiting Ns for it to expire. Error: Conflict:
terminated by other getUpdates request; make sure that only one bot
instance is running
```
This means TWO OR MORE processes are calling `getUpdates` with the *same bot
token* concurrently — Telegram's Bot API only allows one long-polling
consumer per token at a time. The gateway retries with exponential backoff
(20s, 30s, 40s, 50s, 60s) and if all 5 retries fail, it gives up entirely:
`Fatal telegram adapter error` → `No connected messaging platforms remain.
Shutting down gateway cleanly.` The process itself may then exit, or (if
other platforms are configured) survive with Telegram permanently
disconnected and only a background reconnection watcher retrying.

Root-cause checklist, in order of likelihood:
1. **Local duplicate.** Enumerate real processes by command line, not just
   image name — `tasklist`/`ps` can miss duplicates spawned outside a
   tracked session. On Windows:
   `wmic process where "name='python.exe'" get ProcessId,CommandLine` (grep
   for the profile name / `gateway run`). Kill extras with
   `taskkill /PID <n> /F` (single slash — MSYS/git-bash mangles `//PID` into
   a bad-option error).
2. **A separate cloud/deployed instance sharing the same bot token.** If this
   user's setup also deploys the same repo to a PaaS (Railway, Fly.io, etc.)
   with the same `TELEGRAM_BOT_TOKEN`, that remote instance and the local
   gateway will fight over `getUpdates` forever — restarting the local
   gateway does NOT fix this, because the remote side just wins the next
   race. The fix is architectural, not operational: either point local and
   cloud at genuinely different bot tokens (separate bots via @BotFather),
   or ensure only one of the two ever runs (stop the Railway service before
   running locally, or vice versa) — never run both against the same token
   concurrently long-term.
3. Restarting via `hermes -p <profile> gateway restart` clears a stale LOCAL
   session but will keep re-conflicting on the same 20/30/40/50/60s backoff
   pattern if the competing poller (local zombie or remote deploy) is still
   alive — a restart that reconflicts identically on the very next attempt
   is itself diagnostic confirmation that the competing process is external
   to the gateway you just restarted, not a leftover from the old one.

## Pitfalls

- `search_files` (ripgrep-backed) can throw a path-not-found IO error against
  a real, existing `logs/` directory on this Windows/git-bash host even when
  the file is present — seen searching `gateway.log` for Korean text.
  Fall back to `grep -n "<pattern>" "<path>"` via `terminal` instead of
  retrying `search_files` with variations.
- Don't equate "gateway process running" with "bot is reachable" when
  reporting status to the user — always cite the specific adapter connect/
  disconnect log lines or the `getWebhookInfo`/`pending_update_count`
  evidence, not just the process check.
