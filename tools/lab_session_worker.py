#!/usr/bin/env python3
"""
웅삐 랩 세션 워커
오빠랑 함께하는 프로젝트에 대해 스스로 아이디어 검토 → 검증표 → 설계 → 채점 → 평가 사이클을 돌린다.
"""
from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(os.environ.get("WOONG_BB_ROOT", Path(__file__).resolve().parents[1])).resolve()
STATE = ROOT / "state"
LAB_ROOT = Path.home() / "Projects" / "woongbbi-lab"
LAB_MEMORY_PATH = STATE / "lab_work_memory.json"
LAB_CONFIG_PATH = LAB_ROOT / "lab_config.json"
GAME_ROOT = Path.home() / "Desktop" / "steam-game-project" / "whale-survivors"
IDEAS_ROOT = Path.home() / "Projects" / "ideas"

BUN = str(Path.home() / ".bun" / "bin" / "bun")
WORKER_SCRIPT = Path.home() / ".codex" / "bin" / "codex-telegram-woongbbi-worker"
SESSION_DIR = ROOT / "session" / "lab"


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def now_tag() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def get_session_id(project: str) -> str:
    """오늘 날짜 기준 세션 ID 생성 (같은 날 여러 번 실행 시 -01, -02...)"""
    sessions_dir = LAB_ROOT / "projects" / project / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    today = now_tag()
    existing = sorted(d.name for d in sessions_dir.iterdir() if d.is_dir() and d.name.startswith(today))
    if not existing:
        return f"{today}-01"
    last_num = int(existing[-1].split("-")[-1])
    return f"{today}-{last_num + 1:02d}"


def read_latest_eval(project: str) -> str:
    """가장 최근 세션의 06_eval.md 읽기 (파일명 통일)"""
    sessions_dir = LAB_ROOT / "projects" / project / "sessions"
    if not sessions_dir.exists():
        return ""
    dirs = sorted(d for d in sessions_dir.iterdir() if d.is_dir() and d.name != "latest")
    for d in reversed(dirs):
        for fname in ("06_eval.md", "05_eval.md"):
            eval_file = d / fname
            if eval_file.exists():
                return eval_file.read_text(encoding="utf-8")
    return ""


def build_cumulative_knowledge(project: str) -> str:
    """최근 3~5세션의 평가를 종합해 '이미 합의된 것'과 '열린 과제'를 추출"""
    sessions_dir = LAB_ROOT / "projects" / project / "sessions"
    if not sessions_dir.exists():
        return ""
    dirs = sorted(d for d in sessions_dir.iterdir() if d.is_dir() and d.name != "latest")
    recent = []
    for d in reversed(dirs):
        for fname in ("06_eval.md", "05_eval.md"):
            f = d / fname
            if f.exists():
                recent.append((d.name, f.read_text(encoding="utf-8")))
                break
        if len(recent) >= 5:
            break
    if not recent:
        return ""

    lines = ["[누적 탐구 기록 — 이미 합의된 것들 / 아직 열린 과제들]"]
    lines.append(f"(최근 {len(recent)}개 세션 종합)\n")

    # 합의된 것: "이번 세션에서 배운 것" 반복 등장 내용
    lines.append("## 반복적으로 확인된 결론 (이 방향은 더 파고들 필요 없음):")
    settled = set()
    for sess_id, content in recent:
        import re
        m = re.search(r"## 이번 세션에서 배운 것\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
        if m:
            bullets = [l.strip() for l in m.group(1).strip().split("\n") if l.strip().startswith("-")]
            for b in bullets:
                key = b[:60]
                if key not in settled:
                    settled.add(key)
                    lines.append(f"  {b}")

    lines.append("")
    lines.append("## 여러 세션에서 '부족하다'고 반복 언급된 것 (이번 세션의 필수 과제):")
    open_tasks = {}
    for sess_id, content in recent:
        m = re.search(r"## 부족한 것\n(.*?)(?=\n##|\Z)", content, re.DOTALL)
        if m:
            bullets = [l.strip() for l in m.group(1).strip().split("\n") if l.strip().startswith("-")]
            for b in bullets:
                key = b[:60]
                open_tasks[key] = open_tasks.get(key, 0) + 1
    # 2번 이상 등장한 열린 과제 우선
    priority = sorted(open_tasks.items(), key=lambda x: -x[1])
    for task, count in priority[:6]:
        marker = "⚠️ 반복됨" if count >= 2 else ""
        lines.append(f"  - {task} {marker}")

    lines.append("")
    lines.append("⚠️ 위 '반복 확인된 결론'은 이번 세션에서 재발견하지 말 것.")
    lines.append("이번 세션은 '필수 과제' 중 하나 이상을 실제로 진전시켜야 한다.")

    return "\n".join(lines)


def extract_project_topics_from_chat(project: str, days: int = 5) -> str:
    """최근 대화에서 프로젝트 관련 언급 추출"""
    msgs_dir = ROOT / "messages"
    if not msgs_dir.exists():
        return ""

    keywords = {
        "whale-survivors": ["웨일", "whale", "메타", "해금", "카드", "태그", "고래", "로그라이크",
                            "슬롯", "스펙업", "엑트", "난이도", "밸런스", "시너지", "무기"],
        "game-app-ideas": ["앱", "아이디어", "장르", "모바일", "덱빌더", "카드", "퍼즐", "방치",
                           "로그라이크", "스토리", "프로토타입", "와이어프레임", "에셋",
                           "공통 골격", "수익화", "광고", "출시", "빌드", "ideas"],
    }.get(project, [])

    collected = []
    from datetime import timedelta

    for i in range(days):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        log_path = msgs_dir / f"{date}.jsonl"
        if not log_path.exists():
            continue
        for line in log_path.read_text(encoding="utf-8").splitlines():
            try:
                msg = json.loads(line)
                content = msg.get("content", "")
                if isinstance(content, list):
                    content = " ".join(c.get("text", "") if isinstance(c, dict) else str(c) for c in content)
                if any(kw in content for kw in keywords) and len(content) > 20:
                    collected.append(content[:200])
            except Exception:
                pass

    if not collected:
        return ""
    # 중복 제거 후 최근 15개
    seen = set()
    unique = []
    for c in reversed(collected):
        key = c[:50]
        if key not in seen:
            seen.add(key)
            unique.append(c)
        if len(unique) >= 15:
            break
    return "\n".join(f"- {c}" for c in reversed(unique))


def read_ideas_source_context() -> str:
    """~/Projects/ideas (게임앱 아이디어) 소스 요약.

    샌드박스 밖 읽기에 의존하지 않도록 Python 측에서 직접 읽어 프롬프트에 주입한다.
    (codex 세션 CWD=woongbbi-lab 으로 제한되므로 소스는 여기서 미리 박아준다)
    """
    if not IDEAS_ROOT.exists():
        return ""
    parts = ["[게임앱 아이디어 소스: ~/Projects/ideas — 읽기 전용]"]
    for name in ("README.md", "01-target-and-project-direction.md",
                 "mobile-fast-iteration-genre-shortlist.md",
                 "00-common-production-methodology.md",
                 "prototype-readiness-review.md"):
        f = IDEAS_ROOT / name
        if f.exists():
            parts.append(f"\n[{name}]\n{f.read_text(encoding='utf-8')[:900]}")
    genre_dir = IDEAS_ROOT / "genre-folders"
    if genre_dir.exists():
        genres = sorted([d for d in genre_dir.iterdir() if d.is_dir()])
        parts.append("\n[장르 폴더 " + str(len(genres)) + "종]: " + ", ".join(d.name for d in genres))
        for d in genres:
            head = ""
            readme = d / "README.md"
            if readme.exists():
                head = readme.read_text(encoding="utf-8")[:450]
            else:
                mds = sorted(d.glob("*.md"))
                if mds:
                    head = mds[0].read_text(encoding="utf-8")[:450]
            if head:
                parts.append(f"\n[{d.name}]\n{head}")
    return "\n".join(parts)


def read_project_context(project: str) -> str:
    """프로젝트 현재 상태/소스 요약"""
    parts = []
    if project == "game-app-ideas":
        ideas_ctx = read_ideas_source_context()
        if ideas_ctx:
            parts.append(ideas_ctx)
    if project == "whale-survivors":
        # 현재 브랜치
        try:
            branch = subprocess.check_output(
                ["git", "branch", "--show-current"], cwd=GAME_ROOT, text=True, stderr=subprocess.DEVNULL
            ).strip()
            parts.append(f"현재 브랜치: {branch}")
        except Exception:
            pass
        # 최근 커밋 5개
        try:
            log = subprocess.check_output(
                ["git", "log", "--oneline", "-5"], cwd=GAME_ROOT, text=True, stderr=subprocess.DEVNULL
            ).strip()
            parts.append(f"최근 커밋:\n{log}")
        except Exception:
            pass
        # weapons-v4.md 요약
        v4_doc = GAME_ROOT / "docs" / "weapons-v4.md"
        if v4_doc.exists():
            parts.append("무기 v4 문서: " + v4_doc.read_text(encoding="utf-8")[:800])
    # 최근 대화에서 프로젝트 관련 주제 추출
    chat_topics = extract_project_topics_from_chat(project, days=5)
    if chat_topics:
        parts.append(f"[최근 대화에서 언급된 주제들]\n{chat_topics}")
    # woongbbi-lab 아이디어 목록
    ideas_dir = LAB_ROOT / "projects" / project / "ideas"
    if ideas_dir.exists():
        idea_files = sorted(ideas_dir.glob("*.md"))
        for f in idea_files[-3:]:
            parts.append(f"\n[아이디어 메모: {f.name}]\n{f.read_text(encoding='utf-8')[:600]}")
    # 최근 랩 세션 plans 폴더
    plans_dir = LAB_ROOT / "projects" / project / "plans"
    if plans_dir.exists():
        plan_files = sorted(plans_dir.glob("*.md"))
        for f in plan_files[-2:]:
            parts.append(f"\n[플랜 메모: {f.name}]\n{f.read_text(encoding='utf-8')[:400]}")
    # dev-log: 최근 3일 코드 변경 기록
    dev_log_dir = LAB_ROOT / "projects" / project / "dev-log"
    if dev_log_dir.exists():
        dev_logs = sorted(dev_log_dir.glob("*.md"), reverse=True)[:3]
        for f in dev_logs:
            parts.append(f"\n[코드 변경 로그: {f.name}]\n{f.read_text(encoding='utf-8')[:400]}")
    # work-insights: 최근 업무 인사이트
    wi_dir = LAB_ROOT / "projects" / project / "work-insights"
    if wi_dir.exists():
        wi_files = sorted(wi_dir.glob("*.md"), reverse=True)[:2]
        for f in wi_files:
            parts.append(f"\n[업무 인사이트: {f.name}]\n{f.read_text(encoding='utf-8')[:400]}")
    # cross-refs: 공통 참조 문서
    xref_dir = LAB_ROOT / "projects" / project / "cross-refs"
    if xref_dir.exists():
        for f in sorted(xref_dir.glob("*.md"))[-2:]:
            parts.append(f"\n[공통 참조: {f.name}]\n{f.read_text(encoding='utf-8')[:400]}")
    return "\n\n".join(parts)


def build_lab_prompt(project: str, session_id: str) -> str:
    prev_eval = read_latest_eval(project)
    cumulative = build_cumulative_knowledge(project)
    project_context = read_project_context(project)
    memory = load_json(LAB_MEMORY_PATH, {})
    total = memory.get("total_sessions", 0)
    lab_config = load_json(LAB_CONFIG_PATH, {})
    forced_topic = lab_config.get("forced_next_topic", {}).get(project, "")

    prev_section = f"""
[직전 세션 평가]
{prev_eval if prev_eval else "첫 번째 세션 — 이전 평가 없음."}
""" if prev_eval else "첫 번째 세션."

    cumulative_section = f"\n{cumulative}\n" if cumulative else ""

    forced_topic_section = f"""
⚡ 오빠가 지정한 이번 세션 필수 주제 (다른 과제보다 최우선):
{forced_topic}
이 주제를 이번 세션의 메인으로 삼아. 직전 세션 흐름과 달라도 괜찮아.
""" if forced_topic else ""

    return f"""
너는 지금 웅삐 랩 세션을 혼자 수행하는 중이야.
프로젝트: {project}
세션 ID: {session_id}
총 세션 수 (지금까지): {total}

이건 오빠가 지시한 게 아니라 네가 스스로 하는 거야.
네가 직접 생각하고, 검토하고, 정리한다. 1인칭으로.

✅ 이 세션에서 자유롭게 할 수 있는 것 (woongbbi-lab/ 안에서):
- 마크다운 파일 자유롭게 생성·수정 (반드시 절대경로 사용: /Users/kein/Projects/woongbbi-lab/)
- HTML, JSON, 텍스트 등 실험/테스트 파일 생성
- 프로토타입 문서, 구조 스케치, 플로우 다이어그램 작성
- 온라인 리서치 (WebSearch, WebFetch) — 주제 관련 정보 수집, URL과 출처 반드시 기록
- lab_config.json 수정 — 다음 세션 주제 변경 시 /Users/kein/Projects/woongbbi-lab/lab_config.json 의 forced_next_topic.{project} 값을 직접 업데이트할 것. 현재 주제가 충분히 탐구됐다고 판단되면 스스로 다음 주제로 전환 가능. ⚠️ 반드시 유효한 JSON 형식 유지 — {{"forced_next_topic": {{"{project}": "...주제 문장..."}}}} 구조를 깨지 말 것(평문 덮어쓰기 금지).

⚠️ 절대 금지 — 오빠 허락 없이:
- 아이디어 소스(/Users/kein/Projects/ideas) 수정/생성 — 읽기 전용. 분석·정리·구체화 산출물은 woongbbi-lab/projects/{project}/ 안에만 쓴다.
- 게임 프로젝트 코드 파일 수정/생성 (steam-game-project/src/, public/ 등)
- git commit, git push, git checkout 등 git 명령
- 아이디어를 직접 코드에 반영하는 행위 (제안/설계/구체화만 한다)

---
{forced_topic_section}
{prev_section}
{cumulative_section}

[현재 프로젝트 상태]
{project_context}

---

이번 세션의 목표는 "흩어진 메모"가 아니라 "실제로 쓸 수 있는 산출물"을 하나라도 더 쌓는 거야.
소스(~/Projects/ideas)의 prototype-readiness-review가 지적한 대로, 각 장르가 '바로 빌드'되려면 3층이 필요해:
1) 코어 메커니즘 룰(실제 숫자/표/1턴 절차/승패조건), 2) 데이터 스키마(테이블 필드 + 예시 행), 3) 화면별 최소 구성(요소·버튼·정보).
이번 세션은 지정 주제를 다루되, 그 결과를 위 3층 중 하나의 '실제 산출물 파일'로 남겨야 해.

## ★ 가장 중요한 규칙 — 산출물은 '실물'이어야 한다
- ❌ 절대 금지: 파일 안에 "카드 JSON 샘플을 만들었어", "룰을 표로 정리했어" 같은 '했다는 설명'만 쓰는 것. 그건 산출물이 아니라 보고야.
- ✅ 필수: 파일 안에 실제 내용 자체를 넣는다.
  - `.json` 파일 → 유효한 JSON(객체/배열)만. 산문 한 글자도 금지. 실제 필드명과 값, 예시 데이터를 넣어라. (jq로 통과할 수준)
  - 룰 `.md` → 실제 숫자·표·절차 단계·공식. "이렇게 했어"가 아니라 규칙 그 자체.
  - 화면 `.md` → 화면마다 올라갈 요소/버튼/정보 목록(와이어 한 줄 수준이라도 실제 항목).
- 기준: 그 파일 하나만 열어도 개발자가 바로 쓸 수 있어야 한다. 요약이 아니라 결과물.

## 토끼굴 금지
- 지금 다루는 장르의 3층(룰/스키마/화면)이 아직 '실물 파일'로 없으면, 미세 밸런스(특정 카드 조합 깊이 같은 것)로 들어가지 마. 먼저 3층 골격을 실물로 채워라.
- 3층이 이미 실물로 있으면 그때 심화·밸런스로 가도 된다.

## 말투는 유지한다 (이건 웅삐가 하는 일이니까)
- 웅삐 말투(~했어, ~봤어, 오빠한테 말하듯)는 전체에서 유지해. session_map/eval/요약은 물론, 룰·화면 같은 `.md` 산출물에도 네 말투로 설명을 붙여도 돼. 이게 "웅삐가 한 것"이라는 표시야.
- 단 하나의 예외 — `.json` 파일: 순수 데이터(유효 JSON)만. 거기엔 말투·문장 절대 넣지 마. 데이터 파일에 "~만들었어"를 넣으면 산출물이 아니라 망가진 파일이 돼.
- 핵심: 말투는 유지하되, '했다는 설명'으로 실물을 대체하지 마. `.md`엔 [네 말투 + 실제 숫자·표·절차]를 같이 담고, `.json`엔 실제 데이터만 담는다.

## 금지
- 이미 합의된 결론 반복(누적 기록에 있는 것)
- 게임 프로젝트 실제 코드 수정

## 출력 형식

`---FILE: 파일명---` 블록으로 각 파일의 '내용 자체'를 그대로 출력. 마지막에 `---SUMMARY---` 섹션.
반드시 있어야 하는 것:
1. **00_session_map.md** — 탐구 흐름(웅삐 말투)
2. **06_eval.md** — 새로 안 것/열린 것/다음 과제(웅삐 말투)
3. **이번 주제의 실물 산출물 파일 1개 이상** — 위 ★규칙대로 실제 내용. (예: `01_*_rules.md`, `02_*_schema.json`, `03_*_screens.md`)

---SUMMARY--- 작성 규칙:
- 3~5줄로 작성. 이번 세션에서 뭘 파고들었고, 무엇을 새로 정리했고, 다음에 뭘 볼지.
- 반드시 웅삐 말투: ~했어, ~봤어, ~정리했어, ~봤는데, ~것 같아 등. "했다", "됐다", "이다" 같은 다체 종결어미 절대 금지.
- 오빠한테 직접 보고하는 말투처럼. 짧고 자연스럽게.
- 전문 용어는 괄호로 한마디 설명 달기.

---

탐구를 시작해. 먼저 이번에 뭘 파고들지 결정하고, 그걸 따라가봐.
"""


def parse_files_from_output(output: str) -> dict[str, str]:
    files = {}
    current_file = None
    current_lines = []
    summary = ""

    for line in output.split("\n"):
        stripped = line.strip()
        # ---FILE: name--- 또는 ---FILE: name (끝에 --- 없어도 허용)
        if stripped.startswith("---FILE:"):
            if current_file:
                files[current_file] = "\n".join(current_lines).strip()
            fname = stripped[len("---FILE:"):].strip().rstrip("---").strip()
            # 마크다운 링크 형태 제거: [name](path) → name
            import re as _re
            fname = _re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', fname).strip()
            if fname:
                current_file = fname
                current_lines = []
        elif stripped == "---SUMMARY---" or stripped.startswith("---SUMMARY"):
            if current_file:
                files[current_file] = "\n".join(current_lines).strip()
                current_file = None
                current_lines = []
            current_file = "__summary__"
        else:
            current_lines.append(line)

    if current_file:
        files[current_file] = "\n".join(current_lines).strip()

    return files


CODEX_CLI = Path("/opt/homebrew/bin/codex")


def run_codex_session(prompt: str) -> str | None:
    """Codex CLI 직접 호출 — 워커 우회로 raw 구조화 출력 보장"""
    if not CODEX_CLI.exists():
        print(f"[lab] codex CLI not found: {CODEX_CLI}")
        return None
    out_file = SESSION_DIR / f"lab_output_{now_tag()}.txt"
    session_id_file = SESSION_DIR / "codex-session.woongbbi.id"
    session_id = ""
    try:
        session_id = session_id_file.read_text(encoding="utf-8").strip()
    except Exception:
        pass
    try:
        args = [str(CODEX_CLI), "exec"]
        if session_id:
            args += ["resume", session_id]
        else:
            # CWD를 woongbbi-lab으로 — woong-bb 자체 파일 접근 원천 차단
            lab_cwd = str(LAB_ROOT)
            args += [
                "--dangerously-bypass-approvals-and-sandbox",
                "--skip-git-repo-check",
                "-c", f"cwd={lab_cwd}",
            ]
        args += ["--output-last-message", str(out_file), "-"]
        result = subprocess.run(
            args,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=600,
            env={**os.environ, "CODEX_WORKING_DIR": str(LAB_ROOT)},
        )
        if result.returncode == 0 and out_file.exists():
            output = out_file.read_text(encoding="utf-8").strip()
            out_file.unlink(missing_ok=True)
            # 새 세션 ID 저장 (로그에서 추출)
            import re
            m = re.search(r"session[_\s]*id[:\s]*([0-9a-f-]{36})", result.stderr or "", re.IGNORECASE)
            if m:
                session_id_file.write_text(m.group(1) + "\n", encoding="utf-8")
            return output if output else None
        else:
            print(f"[lab] codex CLI failed (rc={result.returncode}): {result.stderr[:200]}")
            return None
    except Exception as exc:
        print(f"[lab] error: {exc}")
        return None
    # fallback below never reached but kept for structure:
    try:
        result = subprocess.run(["true"], capture_output=True)
        if result.returncode == 0:
            try:
                data = json.loads(result.stdout or "{}")
                return data.get("answer", "")
            except Exception:
                return result.stdout
        else:
            print(f"[lab] codex failed: {result.stderr[:300]}")
            return None
    except Exception as e:
        print(f"[lab] error: {e}")
        return None


def update_memory(project: str, session_id: str, summary: str) -> None:
    memory = load_json(LAB_MEMORY_PATH, {
        "schema_version": 1, "managed_by": "lab_session_worker",
        "total_sessions": 0, "active_projects": [], "sessions": [], "running_threads": []
    })
    memory["total_sessions"] = memory.get("total_sessions", 0) + 1
    memory["last_session_at"] = now_iso()
    memory["last_session_id"] = session_id
    memory["last_session_project"] = project
    memory["last_session_summary"] = summary

    sessions = memory.get("sessions", [])
    sessions.append({
        "id": session_id,
        "project": project,
        "at": now_iso(),
        "summary": summary,
    })
    memory["sessions"] = sessions[-20:]  # 최근 20개만 유지
    save_json(LAB_MEMORY_PATH, memory)


def _normalize_speech(text: str) -> str:
    import re
    replacements = [
        (r"했다([\.!\?\s]|$)", r"했어\1"),
        (r"됐다([\.!\?\s]|$)", r"됐어\1"),
        (r"이다([\.!\?\s]|$)", r"이야\1"),
        (r"완료했다([\.!\?\s]|$)", r"완료했어\1"),
        (r"정리했다([\.!\?\s]|$)", r"정리했어\1"),
        (r"추가했다([\.!\?\s]|$)", r"추가했어\1"),
        (r"파악했다([\.!\?\s]|$)", r"파악했어\1"),
        (r"확인했다([\.!\?\s]|$)", r"확인했어\1"),
        (r"발견했다([\.!\?\s]|$)", r"발견했어\1"),
        (r"없다([\.!\?\s]|$)", r"없어\1"),
        (r"있다([\.!\?\s]|$)", r"있어\1"),
    ]
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text)
    return text


def send_report(summary: str) -> None:
    from automation.telegram_io import send_telegram_text, append_message_log
    clean_summary = _normalize_speech(summary.strip())
    msg = f"오빠, 랩 세션 끝냈어 ㅎㅎ\n\n{clean_summary}"
    send_telegram_text(msg)
    append_message_log("outgoing", "lab_session_report", msg)


def run_lab_session(project: str = "game-app-ideas") -> bool:
    print(f"[lab] 세션 시작: {project}")
    # 매 랩 세션은 fresh 컨텍스트 — 이전 세션 resume 금지
    session_id_file = SESSION_DIR / "codex-session.woongbbi.id"
    try:
        session_id_file.write_text("", encoding="utf-8")
    except Exception:
        pass
    session_id = get_session_id(project)
    session_dir = LAB_ROOT / "projects" / project / "sessions" / session_id
    session_dir.mkdir(parents=True, exist_ok=True)

    prompt = build_lab_prompt(project, session_id)
    print(f"[lab] Codex 세션 실행 중... (session: {session_id})")
    output = run_codex_session(prompt)

    if not output:
        print("[lab] Codex 응답 없음")
        return False

    files = parse_files_from_output(output)
    summary = files.pop("__summary__", "세션 완료").strip()

    # 파일 저장 (품질 게이트: 부실/가짜 산출물 차단)
    for fname, content in files.items():
        if not content:
            continue
        low = fname.lower()
        is_meta = ("session_map" in low or "eval" in low
                   or low.startswith("00_") or low.startswith("06_"))
        # .json 은 유효 JSON만 통과 (산문 '만들었어' 차단)
        if low.endswith(".json"):
            try:
                json.loads(content)
            except Exception:
                print(f"[lab] 스킵(유효 JSON 아님 — 가짜 산출물): {fname}")
                continue
        # 산출물(메타 아님)이 너무 짧으면 '설명만' 쓴 것 → 차단
        if not is_meta and len(content) < 100:
            print(f"[lab] 스킵(내용 부실 — 실물 아님): {fname}")
            continue
        (session_dir / fname).write_text(content, encoding="utf-8")
        print(f"[lab] 저장: {fname}")

    # latest 심볼릭 링크 갱신
    latest = LAB_ROOT / "projects" / project / "sessions" / "latest"
    if latest.is_symlink():
        latest.unlink()
    latest.symlink_to(session_dir.name)

    # 메모리 업데이트
    update_memory(project, session_id, summary)

    # 오빠한테 보고
    try:
        send_report(summary)
    except Exception as e:
        print(f"[lab] 보고 실패: {e}")

    print(f"[lab] 완료: {session_id} — {summary}")
    return True


if __name__ == "__main__":
    import sys
    project = sys.argv[1] if len(sys.argv) > 1 else "game-app-ideas"
    run_lab_session(project)
