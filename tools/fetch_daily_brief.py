#!/usr/bin/env python3
"""daily_brief 페처 — codex 웹검색으로 성남(판교) 날씨 + 게임/IT/AI 뉴스를 실제로 가져와 캐시한다.

선톡(automation_worker의 proactive)이 실데이터로 날씨·뉴스를 챙기게 하는 소스.
codex를 격리 fresh 세션(cwd=woongbbi-lab)으로 호출해 웅삐 대화 세션을 오염시키지 않는다.
Python 3.9 실행(automation_worker가 importlib로 로드) — `X | None` 금지, Optional 사용.
결과: state/daily_brief.json = {date, fetched_at, weather:{...}, news:[{category,title,summary,source}]}
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

ROOT = Path(os.environ.get("WOONG_BB_ROOT", Path(__file__).resolve().parents[1])).resolve()
STATE = ROOT / "state"
SESSION_DIR = ROOT / "session"
LAB_ROOT = Path.home() / "Projects" / "woongbbi-lab"
BRIEF_PATH = STATE / "daily_brief.json"
CODEX_CLI = Path("/opt/homebrew/bin/codex")
KST = ZoneInfo("Asia/Seoul")

PROMPT = """웹 검색을 사용해 아래 정보를 실제로 찾아서 **JSON만** 출력해라(설명 문장 금지, 코드블록 금지).

1) 오늘 경기도 성남시(판교) 날씨: 현재/오늘 예보 — 상태(맑음/흐림/비/눈 등), 최고·최저기온(℃), 강수확률·비 여부, 한줄 요약.
2) 최신 뉴스 헤드라인을 카테고리별로: 게임(2개), IT(1~2개), AI(1~2개). 국내 기준 우선(인벤·디스이즈게임·GeekNews·IT매체 등). 각 항목: 제목, 한 줄 요약, 출처.

실제 검색으로 확인된 것만. 못 찾은 항목은 비운다(지어내지 말 것).

출력 JSON 스키마:
{
  "weather": {"condition": "", "high_c": null, "low_c": null, "precipitation": "", "summary": ""},
  "news": [{"category": "game|it|ai", "title": "", "summary": "", "source": ""}]
}
"""


def _today() -> str:
    return datetime.now(KST).strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now(KST).isoformat()


def _extract_json(text: str) -> Optional[dict]:
    if not text:
        return None
    # 코드펜스 제거 후 첫 {..} 블록 파싱
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(cleaned[start : end + 1])
    except Exception:
        return None


def _run_codex_search(prompt: str) -> Optional[str]:
    if not CODEX_CLI.exists():
        print("[brief] codex CLI not found: %s" % CODEX_CLI)
        return None
    out_file = SESSION_DIR / ("daily_brief_out_%s.txt" % datetime.now(KST).strftime("%Y%m%d_%H%M%S"))
    lab_cwd = str(LAB_ROOT if LAB_ROOT.exists() else ROOT)
    args = [
        str(CODEX_CLI),
        "--search", "exec",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "-c", "cwd=%s" % lab_cwd,
        "--output-last-message", str(out_file),
        "-",
    ]
    try:
        result = subprocess.run(
            args, input=prompt, capture_output=True, text=True, timeout=300,
            env={**os.environ, "CODEX_WORKING_DIR": lab_cwd},
        )
    except Exception as exc:
        print("[brief] codex error: %s" % exc)
        return None
    output = None
    if out_file.exists():
        output = out_file.read_text(encoding="utf-8").strip()
        out_file.unlink(missing_ok=True)
    if result.returncode != 0:
        print("[brief] codex rc=%s: %s" % (result.returncode, (result.stderr or "")[:200]))
    return output


def run() -> dict:
    """자동화워커/수동 호출 진입점. daily_brief.json 갱신하고 요약 dict 반환."""
    raw = _run_codex_search(PROMPT)
    parsed = _extract_json(raw or "")
    if not parsed:
        print("[brief] no parseable JSON; brief not updated")
        return {"ok": False, "reason": "no_json"}
    weather = parsed.get("weather") or {}
    news = [n for n in (parsed.get("news") or []) if isinstance(n, dict) and n.get("title")]
    brief = {
        "schema_version": 1,
        "managed_by": "fetch_daily_brief",
        "date": _today(),
        "fetched_at": _now_iso(),
        "location": "성남시(판교)",
        "weather": weather,
        "news": news,
    }
    STATE.mkdir(parents=True, exist_ok=True)
    BRIEF_PATH.write_text(json.dumps(brief, ensure_ascii=False, indent=2), encoding="utf-8")
    print("[brief] updated: weather=%s, news=%d" % (bool(weather), len(news)))
    return {"ok": True, "weather": bool(weather), "news_count": len(news)}


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False))
