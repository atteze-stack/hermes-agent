#!/usr/bin/env python3
"""ATTEZE — Hermes 프로필별 토큰 사용량을 대시보드(atteze-ops)로 올립니다.

Hermes 는 이미 세션·모델별 토큰과 비용을 각 프로필의 state.db
(`session_model_usage` 테이블)에 기록하고 있습니다. 이 스크립트는 그걸
프로필 단위로 합쳐서 `data/usage/hermes.json` 으로 GitHub 에 올립니다.
대시보드 수집기(GitHub Actions)는 Railway 컨테이너 안을 들여다볼 수 없으므로
**컨테이너 쪽에서 밀어주는** 방향이어야 합니다.

    /opt/data/state.db                     ← default 프로필
    /opt/data/profiles/<name>/state.db     ← 나머지 프로필
                    │
                    ├ (이 스크립트, 15분마다)
                    ▼
    atteze-ops:data/usage/hermes.json  ──▶ refresh.py 가 병합 ──▶ 대시보드

필요한 환경변수
    GH_DEPLOY_TOKEN   atteze-ops 에 쓸 수 있는 fine-grained 토큰 (Contents R/W).
                      Railway `hermes-agent` Variables 에 이미 등록돼 있습니다.
    HERMES_HOME       기본 /opt/data (Docker 이미지 기본값)
    USAGE_REPO        기본 atteze-stack/atteze-ops
    USAGE_PUSH_EVERY  --loop 기본 주기(초). 기본 900(15분)

사용법
    python3 scripts/atteze_usage_push.py           # 1회 실행
    python3 scripts/atteze_usage_push.py --loop    # 주기 실행 (게이트웨이와 함께 띄울 때)
    python3 scripts/atteze_usage_push.py --dry-run # 올리지 않고 결과만 출력

의존성 없음 — 표준 라이브러리만 씁니다(컨테이너에 추가 설치 불필요).
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

HERMES_HOME = os.environ.get("HERMES_HOME", "/opt/data")
REPO = os.environ.get("USAGE_REPO", "atteze-stack/atteze-ops")
FILE_PATH = os.environ.get("USAGE_FILE_PATH", "data/usage/hermes.json")
TOKEN = os.environ.get("GH_DEPLOY_TOKEN", "").strip()
LOOP_EVERY = int(os.environ.get("USAGE_PUSH_EVERY", "900"))

# Hermes 프로필 이름 → 대시보드 people[].id (ops.base.json 기준).
# 여기 없는 프로필은 이름 그대로 쓰되 대시보드에서는 매칭되지 않습니다.
PROFILE_TO_PERSON = {
    "secretary": "rt",     # 김서연 비서실장
    "developer": "dev",    # 이준호 과장
    "review":    "ops",    # 박지민 대리
    "designer":  "dsn",    # 정수아 과장
    "marketing": "mkt",    # 최유나 주임
    "video":     "vid",    # 한도윤 과장
}

DAYS_KEPT = 7          # 스파크라인용 보관 일수


def log(*a):
    print(datetime.now(KST).strftime("[%H:%M:%S]"), *a, flush=True)


# ── Hermes state.db 읽기 ────────────────────────────────────────────────

def _profile_dbs() -> list[tuple[str, str]]:
    """(프로필이름, state.db 경로) 목록. 없으면 빈 리스트."""
    out = []
    root = os.path.join(HERMES_HOME, "state.db")
    if os.path.exists(root):
        out.append(("default", root))
    pdir = os.path.join(HERMES_HOME, "profiles")
    if os.path.isdir(pdir):
        for name in sorted(os.listdir(pdir)):
            db = os.path.join(pdir, name, "state.db")
            if os.path.exists(db):
                out.append((name, db))
    return out


def _read_db(name: str, path: str, since_ts: float) -> dict:
    """한 프로필의 일자별 토큰·비용 합계. 스키마가 다르면 조용히 건너뜁니다.

    ⚠️ 읽기 전용으로만 연다(`mode=ro`). 게이트웨이가 같은 DB 를 쓰고 있으므로
    절대 쓰기를 하지 않는다 — 잠금이나 손상 위험을 만들지 않기 위해서다.
    """
    days: dict[str, dict] = {}
    try:
        uri = f"file:{urllib.request.pathname2url(path)}?mode=ro"
        con = sqlite3.connect(uri, uri=True, timeout=5)
    except Exception as e:
        log(f"  {name}: DB 열기 실패 — {e!r}")
        return days
    try:
        cur = con.cursor()
        cols = {r[1] for r in cur.execute(
            'PRAGMA table_info("session_model_usage")')}
        if not cols:
            log(f"  {name}: session_model_usage 테이블 없음 — 건너뜀")
            return days
        # 시각 컬럼 이름이 버전마다 다를 수 있어 있는 것을 골라 씁니다.
        # ⚠️ 2026-08-16 수정: 실제 스키마엔 updated_at/created_at/ts/timestamp가
        # 전혀 없고 first_seen/last_seen만 존재해서(developer/secretary/designer
        # state.db 로 확인) tcol 이 항상 None → 모든 행이 "오늘"로만 잡히는
        # 버그가 있었다. last_seen(최근 활동 시각)을 최우선으로 추가.
        tcol = next((c for c in ("last_seen", "updated_at", "created_at", "ts", "timestamp")
                     if c in cols), None)
        pick = [c for c in ("input_tokens", "output_tokens", "cache_read_tokens",
                            "cache_write_tokens", "reasoning_tokens") if c in cols]
        # ⚠️ 2026-08-16 수정: actual_cost_usd 컬럼은 항상 존재하지만 이 배포에서는
        # 전부 0.0 이고(실제 청구 반영 전), 실비용은 estimated_cost_usd 에 있다
        # (developer 14건 합계 $20.11, secretary 20건 $12.84 확인됨).
        # 예전 코드는 존재 여부만 보고 actual_cost_usd 를 무조건 우선해서
        # cost_usd 가 항상 0으로 올라가는 버그가 있었다 — 값이 0이 아닌
        # 컬럼을 우선한다(재계산이 아니라 "어느 컬럼을 쓸지"만 바꾼 것).
        costc = None
        for cand in ("actual_cost_usd", "estimated_cost_usd"):
            if cand not in cols:
                continue
            nonzero = cur.execute(
                f"SELECT COUNT(*) FROM session_model_usage WHERE {cand} > 0"
            ).fetchone()[0]
            if nonzero:
                costc = cand
                break
        if costc is None:
            costc = next((c for c in ("actual_cost_usd", "estimated_cost_usd")
                          if c in cols), None)
        if not pick:
            log(f"  {name}: 토큰 컬럼 없음 — 건너뜀")
            return days
        sel = ", ".join(pick) + (f", {costc}" if costc else "")
        if tcol:
            rows = cur.execute(
                f"SELECT {tcol}, {sel} FROM session_model_usage").fetchall()
        else:
            rows = [(None, *r) for r in
                    cur.execute(f"SELECT {sel} FROM session_model_usage").fetchall()]
        for row in rows:
            ts = _to_epoch(row[0])
            if ts is None:
                # 시각을 못 읽으면 오늘로 넣는다 — 빠뜨리는 것보다 낫다.
                ts = time.time()
            if ts < since_ts:
                continue
            day = datetime.fromtimestamp(ts, KST).strftime("%Y-%m-%d")
            d = days.setdefault(day, {"in": 0, "out": 0, "cache_read": 0,
                                      "cache_write": 0, "reasoning": 0,
                                      "cost_usd": 0.0, "rows": 0})
            vals = row[1:]
            for key, v in zip(pick, vals):
                short = {"input_tokens": "in", "output_tokens": "out",
                         "cache_read_tokens": "cache_read",
                         "cache_write_tokens": "cache_write",
                         "reasoning_tokens": "reasoning"}[key]
                d[short] += int(v or 0)
            if costc:
                d["cost_usd"] += float(vals[len(pick)] or 0)
            d["rows"] += 1
    except sqlite3.Error as e:
        log(f"  {name}: 조회 실패 — {e!r}")
    finally:
        con.close()
    return days


def _to_epoch(v) -> float | None:
    """DB 의 시각 값(정수 epoch / ms / ISO 문자열)을 초 단위 epoch 으로."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        f = float(v)
        return f / 1000.0 if f > 1e11 else f        # ms 로 저장된 경우 보정
    s = str(v).strip()
    if not s:
        return None
    try:
        return float(s) if s.replace(".", "", 1).isdigit() else \
            datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None


def collect() -> dict:
    since = (datetime.now(KST) - timedelta(days=DAYS_KEPT)).timestamp()
    people: dict[str, dict] = {}
    dbs = _profile_dbs()
    if not dbs:
        log(f"state.db 를 못 찾았습니다 (HERMES_HOME={HERMES_HOME})")
    for name, path in dbs:
        days = _read_db(name, path, since)
        if not days:
            continue
        pid = PROFILE_TO_PERSON.get(name, name)
        slot = people.setdefault(pid, {"profile": name, "days": {}})
        for day, d in days.items():
            cur = slot["days"].setdefault(day, {"in": 0, "out": 0, "cache_read": 0,
                                                "cache_write": 0, "reasoning": 0,
                                                "cost_usd": 0.0, "rows": 0})
            for k in cur:
                cur[k] += d.get(k, 0)
        log(f"  {name} → {pid}: {len(days)}일치, "
            f"오늘 {slot['days'].get(_today(), {}).get('in', 0)}in")
    return {
        "source": "hermes",
        "updated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "today": _today(),
        "people": people,
    }


def _today() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


# ── GitHub Contents API 로 올리기 ──────────────────────────────────────

def _api(method: str, url: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "atteze-usage-push/1.0",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8") or "{}")


def push(payload: dict) -> bool:
    """파일을 읽어 sha 를 얻고 PUT 한다. 동시 수정(409/412)은 한 번 재시도."""
    if not TOKEN:
        log("GH_DEPLOY_TOKEN 이 없습니다 — 올리지 않고 종료")
        return False
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    for attempt in (1, 2):
        sha = None
        try:
            sha = _api("GET", url).get("sha")
        except urllib.error.HTTPError as e:
            if e.code != 404:                      # 404 = 아직 파일 없음(정상)
                log(f"기존 파일 조회 실패: HTTP {e.code}")
                return False
        body = {
            "message": f"chore(usage): hermes 토큰 사용량 {payload['updated_at']}",
            "content": base64.b64encode(text.encode("utf-8")).decode("ascii"),
            "committer": {"name": "atteze-usage", "email": "bot@atteze.com"},
        }
        if sha:
            body["sha"] = sha
        try:
            _api("PUT", url, body)
            log(f"올림: {REPO}/{FILE_PATH} (사람 {len(payload['people'])}명)")
            return True
        except urllib.error.HTTPError as e:
            if e.code in (409, 422) and attempt == 1:
                log("동시 수정 감지 — 다시 시도")
                time.sleep(2)
                continue
            detail = e.read().decode("utf-8", "replace")[:200]
            log(f"올리기 실패: HTTP {e.code} {detail}")
            return False
        except Exception as e:
            log(f"올리기 실패: {e!r}")
            return False
    return False


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loop", nargs="?", type=int, const=LOOP_EVERY,
                    help=f"주기 실행(초). 값 없으면 {LOOP_EVERY}초")
    ap.add_argument("--dry-run", action="store_true", help="올리지 않고 출력만")
    a = ap.parse_args()

    while True:
        try:
            payload = collect()
            if a.dry_run:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            elif payload["people"]:
                push(payload)
            else:
                log("올릴 사용량이 없습니다 — 건너뜀")
        except Exception as e:                      # 루프는 절대 죽지 않게
            log(f"오류: {e!r}")
        if not a.loop:
            return 0
        time.sleep(a.loop)


if __name__ == "__main__":
    sys.exit(main())
