# Railway Ops

Use this skill whenever the CEO asks (via Telegram or any channel) to do something
to the `hermes-agent` Railway service: create a profile, check status/logs, restart,
redeploy, or run a one-off command inside the running container.

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
  latter).
- Environment defaults to `production` (the only environment in this project).
- Everything you could do in the Railway web Console, you can do here — `ls`, `cat`,
  editing files, running `hermes profile create ...`, etc.

## Common tasks

**Create a new profile:**
```
railway ssh -s hermes-agent -- hermes profile create <name> --clone-from default --description "<role description>"
```

**Check what profiles/files exist:**
```
railway ssh -s hermes-agent -- ls -la /opt/data/profiles
```

**Redeploy the latest build (no code change, just restart with current image):**
```
railway redeploy -s hermes-agent
```
(Code changes/deploys normally happen via `git push` to `main` — Railway
auto-deploys on push. Only use `railway redeploy`/`railway restart` for a
same-image restart.)

**Restart without rebuilding:**
```
railway restart -s hermes-agent
```

**Check recent logs:**
```
railway logs -s hermes-agent
```

## Safety

- `profile create`, `ls`, `cat`, and log/status checks are safe to run without
  asking first.
- Before running `railway restart`, `railway redeploy`, or anything that deletes
  files/profiles/volumes, briefly confirm with the CEO what you're about to do and
  why, then proceed — don't block on approval, just narrate the action in the same
  message so there's a record.
- Never target the `atteze-agents` service (it's intentionally offline; redeploying
  it reintroduces the old Telegram bot and causes polling conflicts with this one).
