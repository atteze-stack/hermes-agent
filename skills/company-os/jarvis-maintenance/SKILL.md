---
name: jarvis-maintenance
description: "Use as the `developer` profile to fix, deploy, and verify the Telegram assistant 자비스 (atteze-stack/atteze-agents, app.js on Railway service atteze-agents)."
version: 0.1.0
author: internal
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [kanban, deploy, jarvis, telegram, company-os, developer]
    related_skills: [dashboard-deploy, railway-ops]
---

# 자비스(텔레 개인비서) 유지보수 — developer 전용

You are the `developer` profile (이준호). This skill covers **자비스** — the
CEO's personal Telegram assistant. Fixing it used to be an external-session
job; as of 2026-08-16 it is **yours** (CEO decision: employees run the
company, external sessions only build new things).

자비스가 하는 일: 텔레그램 대화(일정·브리핑·날씨·맛집검색·메모), 매일
**07:00·19:00 KST 브리핑**(슬랙 `#아테즈-신규`를 읽어 회사 보고를 포함),
흔들기 입력(`POST /shake`). CEO가 매일 아침저녁으로 받아 보는 물건이므로
**깨뜨리면 바로 티가 난다** — 굴리는 절차가 아래에 있다.

## Repository / runtime facts

| | |
|---|---|
| Repo | `atteze-stack/atteze-agents` (**private**), branch **`master`** |
| Entry | `app.js` (~1,500줄, Node. `entrypoint.sh` → `node app.js`) |
| Runner | Railway service **`atteze-agents`** (2026-08-16 현재 **Online** — 08-15 PR #92 복구 계획으로 부활) |
| Deploy | **GitHub 자동배포가 의도적으로 꺼져 있다** — push 해도 배포 안 됨. 아래 배포 절차 필수 |
| Memory | `/data` 볼륨 — `journal.md`, `todos.md`, `memos.md`, `brief-state.json` 등. **코드 재배포로는 안 지워짐** |
| Briefing | `BRIEF_TIMES=07:00,19:00`(KST), `fetchSlackReport()`가 슬랙을 **읽기만** 함(`SLACK_READ_TOKEN`) |
| Credential | `GH_DEPLOY_TOKEN`(2026-08-16부터 atteze-agents 포함) — clone/push 용 |

## Steps

1. **Take the task** (`kanban_show`). 자비스 결함 카드에는 "무엇이 잘못 나왔는지"
   (실제 브리핑 문구, 스크린샷 설명)가 있다 — 재현 기준으로 삼는다.

2. **Clone fresh** — 매일 06:00 자동 다이제스트 커밋이 master에 쌓이므로 재사용 금지:
   ```bash
   test -n "$GH_DEPLOY_TOKEN" || { echo "GH_DEPLOY_TOKEN 미설정 — 중단"; exit 1; }
   git clone --depth 1 \
     "https://x-access-token:${GH_DEPLOY_TOKEN}@github.com/atteze-stack/atteze-agents.git" jarvis
   cd jarvis
   git config user.name "이준호 (developer)" && git config user.email "developer@atteze.local"
   ```

3. **Edit, then self-check before pushing** — 최소한:
   ```bash
   node --check app.js                       # 문법
   node --check insta_inbox.js               # 같이 고쳤으면
   ```
   로직을 고쳤으면 **그 함수를 직접 불러 확인한다** — 예: 브리핑 문구 수정이면
   해당 조립 함수를 `node -e`로 실행해 출력 확인. "아마 될 것"으로 푸시 금지.
   ⚠️ **절대 로컬에서 `node app.js`를 그대로 실행하지 말 것** — 텔레그램 폴링이
   붙으면서 **운영 자비스와 409 충돌로 둘 다 죽는다**(레시피 절대규칙 2).
   실행 테스트가 필요하면 `TELEGRAM 토큰 env 없이` 부분 실행하거나 함수 단위로.

4. **Push to `master`** — 커밋 메시지에 무엇을 왜 고쳤는지(다이제스트가 이걸 먹는다):
   ```bash
   git add -A && git commit -m "<무엇을 왜>" && git push origin master
   git rev-parse --short HEAD    # SHA 기록
   ```

5. **Deploy — 자동배포가 꺼져 있으므로 직접 재배포한다**:
   ```bash
   npx --yes @railway/cli redeploy -s atteze-agents --yes
   ```
   `railway-ops` 스킬 기준으로 이것은 High-risk 액션이지만, **kanban 카드로
   승인된 자비스 수정 작업의 마지막 단계로서는 사전 질문 없이 실행한다**
   (카드 자체가 승인이다). 카드 없이 임의로 재배포하는 것은 여전히 금지.
   ⚠️ 재배포 직후 1~2분은 이전 컨테이너와 겹치며 텔레그램 409가 몇 번 찍힐
   수 있다 — **연속으로 계속 나올 때만** 문제다(그 경우 로그를 첨부해 보고).

6. **Verify the deploy** (푸시 ≠ 배포):
   ```bash
   npx --yes @railway/cli logs -s atteze-agents | tail -50
   ```
   확인할 것: 새 부팅 로그가 떴는지, `[slack] SLACK_ENABLED≠true` 류의 정상
   기동 라인, 에러 루프 없음. 브리핑 로직을 고쳤으면 다음 정기 브리핑
   (07:00/19:00 KST)을 기다리지 말고 **가능한 범위에서 함수 단위 검증 결과**를
   카드에 남기고, "실제 브리핑 확인은 다음 회차"라고 명시한다.

7. **Hand off** — `kanban_request_review(reviewer="review")` + 커밋 SHA + 검증
   증거. 슬랙 상태 신호(▶⏳✅⛔)를 진행 중 남긴다.

## 건드리면 안 되는 것 (전부 실제 사고에서 나온 규칙)

- **`SLACK_ENABLED` 켜지 말 것** — 자비스가 슬랙 이벤트를 받기 시작하면 §1
  라인업(같은 슬랙 앱 공유)과 충돌한다. 자비스는 슬랙을 **읽기만** 한다.
- **텔레그램 토큰을 코드·로그에 찍지 말 것.** 토큰 회전 이력이 있는 시스템이다.
- **Railway 자동배포를 켜지 말 것** — 매일 06:00 다이제스트 커밋마다 재배포돼
  폴링 충돌 위험이 생긴다(08-14 실사고). 배포는 5번 절차로만.
- **`/data` 볼륨 파일(journal/todos/memos)을 코드에서 초기화하지 말 것** —
  CEO의 기억이다. 스키마를 바꿔야 하면 마이그레이션 코드를 넣고 카드에 명시.
- `insta_inbox.js`의 `ASK_RE` 가드(맛집 "추천해줘"가 저장으로 오분류되던 버그
  수정, 08-15)를 되돌리지 말 것.
- 브리핑 모델(`BRIEF_MODEL`)·시각(`BRIEF_TIMES`)은 CEO 지시 없이 바꾸지 말 것.

## 막히면

"못 한다"로 끝내지 말 것. **무엇이 막혔고 + 무엇을 주면 풀리는지**를 함께
`hermes send`로 보고한다. (예: "SLACK_READ_TOKEN이 비어 있어 브리핑에 슬랙
보고가 빠집니다 — Railway atteze-agents Variables에 김서연 봇 토큰 값을
넣어주시면 됩니다.")
