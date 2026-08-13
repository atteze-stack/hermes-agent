# Railway Ops

Use this skill whenever the CEO asks (via Telegram or any channel) to do something
to the `hermes-agent` Railway service: create a profile, check status/logs, restart,
redeploy, sync data, or run a one-off command inside the running container.

## Prerequisites (already set up, don't ask the user again)

- `RAILWAY_TOKEN` is set in this profile's `.env` (a Railway **project** token, scoped
  to the `respectful-vitality` project only).
- Railway CLI is available via `npx --yes @railway/cli` (installs on first use if not
  already global). If `railway` is not on PATH, prefix commands with `npx --yes @railway/cli`.

## Core pattern

Run a command directly inside the live `hermes-agent` container:

```
railway ssh -s hermes-agent -- <command>
```

- `-s hermes-agent` targets the correct service (there are two services in this
  project: `hermes-agent` and the old, offline `atteze-agents` — never target the
  latter, ever, for any reason).
- Environment defaults to `production` (the only environment in this project).
- Everything you could do in the Railway web Console, you can do here — `ls`, `cat`,
  editing files, running `hermes profile create ...`, etc.

## Risk tiers — this is the most important section

Every Railway action falls into exactly one tier. Follow the matching rule. Do not
downgrade a tier because a task "seems small" — go by the action itself.

### Low risk — run immediately, no notice needed
`hermes profile create`, `ls`/`cat`/`find` (read-only), `railway logs`, `railway status`,
`railway ssh ... -- ps`, gateway/health checks, kanban status queries, listing variable
**names** (`railway variables` without printing values).

### Medium risk — notify, then run in the same message
`hermes profile update` / config patches, skill sync / `git pull` inside the container,
`hermes` version updates. Say what you're about to do and why, then do it — don't wait
for a reply.

### High risk — show the exact command(s) you intend to run, then WAIT for an explicit
yes/no from the CEO before executing. Do not proceed on silence or on an ambiguous reply.
- `railway restart`, `railway redeploy`, any rollback
- `railway variables set` (secret/env changes)
- anything touching the volume: deleting/overwriting `kanban.db`, `auth.json`,
  `profiles/*`, backups, restores
- `rm` of anything under `/opt/data`
- Docker/image rebuilds
- the **first** deploy of any new profile or skill that hasn't run in production before

## Secrets: write-only, never read

You may run `railway variables set KEY=value` when the CEO gives you a value directly
(that's still a High-risk action — gate it like any other). You must **never** run a
command that prints a secret's value back (`railway variables get`, `cat .env`, `echo
$TOKEN`, etc.) into any chat, log, or report. If you need to confirm a secret is set,
confirm the **key exists**, never the value.

## Data migration SOP (kanban.db and anything similar)

Never copy-and-overwrite directly. Always:
1. **Backup** — copy the current file to a timestamped `.bak` alongside it.
2. **Checksum** — `sha256sum` the source.
3. **Copy** — transfer the file.
4. **Checksum** — `sha256sum` the destination, compare to step 2.
5. **Switch** — only after checksums match, point the running service at the new file
   (this step is itself High-risk if it requires a restart).

This whole sequence is Medium risk (notify + proceed) up through step 4; step 5 (or any
step that requires a restart) is High risk and needs approval.

## Common tasks

**Create a new profile:**
```
railway ssh -s hermes-agent -- hermes profile create <name> --clone-from default --description "<role description>"
```

**Check what profiles/files exist:**
```
railway ssh -s hermes-agent -- ls -la /opt/data/profiles
```

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

## Hard rule

Never target the `atteze-agents` service (it's intentionally offline; redeploying
it reintroduces the old Telegram bot and causes polling conflicts with this one).
