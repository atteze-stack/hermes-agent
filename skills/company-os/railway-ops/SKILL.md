# Railway Ops

Use this skill whenever the CEO asks (via Telegram or any channel) to do something
to the `hermes-agent` Railway service: check status/logs, restart, redeploy, or
manage variables.

## Prerequisites (already set up, don't ask the user again)

- `RAILWAY_TOKEN` is a Railway **project** token (scoped to the `respectful-vitality`
  project only), set as a Railway service Variable — it's already in this
  container's process environment, no `.env` edit needed.
- Railway CLI is available via `npx --yes @railway/cli` (installs on first use if not
  already global). If `railway` is not on PATH, prefix commands with `npx --yes @railway/cli`.

## Important: `railway ssh` is NOT available to you

We tested this directly (2026-08-14): `railway ssh -s hermes-agent -- <command>`
returns `Unauthorized` even with `RAILWAY_TOKEN` set and an SSH key registered to the
CEO's account. Root cause: SSH auth is tied to a specific **logged-in user**, not a
project token — a project token has no user identity for the SSH transport to
authenticate as. The fix (a personal access token) would give you access to every
project in the CEO's workspace, not just this one, so we're deliberately not doing
that.

**Practical result**: arbitrary shell exec inside the container (`ls`, `cat`, editing
files, running one-off `hermes` commands) is a human-via-Railway-Console task, not
something you can do. If the CEO asks you to do something that would require
`railway ssh`, say so plainly and ask them to run it in the Console — don't attempt
`railway ssh` yourself, it will just fail.

Everything below this line uses commands that work fine with the project token.

## Risk tiers — this is the most important section

Every Railway action falls into exactly one tier. Follow the matching rule. Do not
downgrade a tier because a task "seems small" — go by the action itself.

### Low risk — run immediately, no notice needed
`railway status`, `railway logs`, listing variable **names** (`railway variables`
without printing values), gateway/health checks, kanban status queries.

### Medium risk — notify, then run in the same message
Nothing currently maps here for Railway-CLI actions specifically (profile/config
changes now happen via the Console, which is human-driven anyway). Kept as a tier
for future non-ssh commands that fit this profile.

### High risk — show the exact command(s) you intend to run, then WAIT for an explicit
yes/no from the CEO before executing. Do not proceed on silence or on an ambiguous reply.
- `railway restart`, `railway redeploy`, any rollback
- `railway variables set` (secret/env changes)
- anything that would require `railway ssh` — flag it to the CEO instead of attempting it

## Secrets: write-only, never read

You may run `railway variables set KEY=value` when the CEO gives you a value directly
(that's still a High-risk action — gate it like any other). You must **never** run a
command that prints a secret's value back (`railway variables get`, `echo $TOKEN`,
etc.) into any chat, log, or report. If you need to confirm a secret is set, confirm
the **key exists**, never the value.

## Data migration SOP (kanban.db and anything similar)

This requires `railway ssh` (file-level access inside the container), which you don't
have — hand this off to the CEO/Console. If it ever becomes automatable, the SOP is:
Backup → Checksum → Copy → Checksum → Switch, with the Switch step always High risk.

## Common tasks

**Redeploy the latest build (no code change, just restart with current image) — High risk:**
```
railway redeploy -s hermes-agent
```
(Code changes/deploys normally happen via `git push` to `main` — Railway
auto-deploys on push. Only use `railway redeploy`/`railway restart` for a
same-image restart, and only after approval.)

**Restart without rebuilding — High risk:**
```
railway restart -s hermes-agent
```

**Check recent logs — Low risk:**
```
railway logs -s hermes-agent
```

**Check deployment/service status — Low risk:**
```
railway status
```

## Hard rule

Never target the `atteze-agents` service (it's intentionally offline; redeploying
it reintroduces the old Telegram bot and causes polling conflicts with this one).
