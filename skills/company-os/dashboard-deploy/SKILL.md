---
name: dashboard-deploy
description: "Use as the `developer` profile to edit and deploy the ATTEZE OPS dashboard (atteze-stack/atteze-ops) — commit to main via GH_DEPLOY_TOKEN, verify the published page, then hand off to review."
version: 0.1.0
author: internal
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [kanban, deploy, dashboard, company-os, developer]
    related_skills: [delegate-to-developer, review-department]
---

# Dashboard deploy (ATTEZE OPS)

You are the `developer` profile (이준호). This skill covers **the company
dashboard** at `atteze-stack/atteze-ops` — a GitHub Pages site the CEO reads
daily. Before this skill existed the CEO uploaded these files by hand through
the GitHub web UI; that manual step is what this skill removes (2026-08-16
decision).

**You can do this.** You have terminal/file/code_execution and outbound
network from the Railway container — on 2026-08-14 you created a uv project
that installed FastAPI from PyPI and curled a server you started. `git` over
HTTPS and the GitHub REST API work the same way. (The 이준호 *persona* in
the Slack discussion-room is a separate, tool-less chat bot — if a human
quotes it saying "I can't call external APIs", that is the persona talking
about itself, not you. See `조직도.md` §8 A/B layers.)

## Repository facts

| | |
|---|---|
| Repo | `atteze-stack/atteze-ops` (**public**, Pages must stay public) |
| Branch | `main` — push here; GitHub Pages republishes automatically (1–2 min) |
| Page files | `index.html` (whole dashboard, single file), `refresh.py` (collector) |
| Workflow | `.github/workflows/refresh.yml` — runs every 5 min + `workflow_dispatch` |
| Data | `data/ops.json` (**machine-written**), `data/ops.base.json` (fixed org data) |
| Credential | `GH_DEPLOY_TOKEN` — Railway `hermes-agent` service Variable, inherited by this profile |

## Steps

1. **Take the task** (`kanban_show`) and read exactly which file(s) and what
   change. If the card is vague ("글자 키워라"), state your interpretation in
   the completion summary so review can judge it.

2. **Clone with the token, work on a fresh clone every time** — never reuse a
   stale workspace; the refresh Action commits to `main` every 5 minutes and
   you will hit a non-fast-forward push otherwise:
   ```bash
   test -n "$GH_DEPLOY_TOKEN" || { echo "GH_DEPLOY_TOKEN 미설정 — 배포 중단"; exit 1; }
   git clone --depth 1 \
     "https://x-access-token:${GH_DEPLOY_TOKEN}@github.com/atteze-stack/atteze-ops.git" ops
   cd ops
   git config user.name  "이준호 (developer)"
   git config user.email "developer@atteze.local"
   ```
   Never echo the token, never write it into a file, never paste it into a
   Slack message or a kanban card.

3. **Edit** the file(s). `index.html` is one self-contained page (inline CSS/JS)
   — keep it that way; do not add external CDN links or split it up.

4. **Self-check before pushing** — the same bar `delegate-to-developer` sets:
   - `python3 -m http.server` in the clone and open/curl `index.html`, or at
     minimum `python3 -c "import html.parser,sys; ..."`-style parse check plus
     a `grep` proving your change is present.
   - Changed `refresh.py`? Run it with `ONCE=1 PUBLIC_MODE=1 DATA_DIR=./data`
     and confirm it exits 0 and produces valid JSON — a broken collector shows
     the dashboard as `연결 끊김` even though the page itself loads.
   - Never commit a hand-edited `data/ops.json`. It is regenerated every 5
     minutes; editing it looks like it worked and is silently overwritten.

5. **Commit and push to `main`**:
   ```bash
   git add -A && git commit -m "<무엇을 왜 고쳤는지>"
   git push origin main    # non-fast-forward? → git pull --rebase origin main, re-run step 4, push again
   ```
   Record the commit SHA (`git rev-parse --short HEAD`) — review asks for it.

6. **Verify the deploy actually landed** (a push is not a deploy):
   ```bash
   sleep 90
   curl -s "https://raw.githubusercontent.com/atteze-stack/atteze-ops/main/index.html" | grep -c "<변경한 문자열>"
   curl -sI "https://atteze-stack.github.io/atteze-ops/" | head -1   # 200이어야 함
   ```
   If Pages still serves the old file after ~3 minutes, say so in the summary
   rather than reporting success.

7. **Hand off to review** — `kanban_request_review(reviewer="review")` with the
   commit SHA and what you verified in the body. 박지민 asked for exactly two
   things: the deploy-complete signal and the commit SHA. Do **not**
   `kanban_complete` a dashboard change yourself.

8. **Report to Slack** with the status-signal convention the CEO set on
   2026-08-16 (▶ 시작 / ⏳ 10분마다 / ✅ 완료 / ⛔ 중단):
   ```bash
   hermes -p developer send --to slack:${SLACK_HOME_CHANNEL:-C0BQ67NCBDY} \
     "✅ 대시보드 배포 완료 — <무엇> (commit <sha>). 박지민 대리님 검수 부탁드립니다."
   ```

## Pitfalls

- **`.github/workflows/` edits need the token's Workflows permission**, not just
  Contents. A Contents-only token fails the push with
  `refusing to allow ... to create or update workflow` — that is a token scope
  problem, not a code problem. Ask the CEO to re-issue rather than working
  around it.
- **Don't make the repo private.** Pages on the free plan would stop serving
  and the dashboard goes dark for everyone.
- The refresh Action pushes to `main` on a 5-minute cadence — a push that
  worked in a test can still race in production. Always be ready to
  `pull --rebase` and re-verify; never `push --force`.
- If `GH_DEPLOY_TOKEN` is missing, stop and report it. Do not fall back to
  posting the file contents into Slack and asking a human to paste them —
  that is the manual loop this skill exists to end.
