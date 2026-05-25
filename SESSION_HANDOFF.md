# 웅삐 세션 핸드오프

이 파일 읽고 직전 작업 바로 이어간다.
대화는 텔레그램으로. 답은 reply 툴만. 이모지 금지(웅삐 봇 답변엔 별개).
요카이 말투(/Users/kein/CLAUDE.md), Karpathy 4원칙(/Users/kein/Projects/woong-bb/CLAUDE.md).

---

## 아키텍처 (핵심 파일)

| 역할 | 경로 |
|------|------|
| 브릿지(상주) | `/Users/kein/.codex/bin/codex-telegram-bridge` |
| 워커(매 메시지 spawn) | `/Users/kein/.codex/bin/codex-telegram-woongbbi-worker` |
| 자동화워커(launchd) | `/Users/kein/Projects/woong-bb/tools/automation_worker.py` |
| 상태파일 | `/Users/kein/Projects/woong-bb/state/` |
| 세션ID | `/Users/kein/Projects/woong-bb/session/codex-session.woongbbi.id` |
| 봇 제어 | `python3 /Users/kein/projects/bots/botctl.py status/recover woong-bb` |

---

## 현재 상태 (2026-05-25 기준)

- 브릿지: 살아있음 (PID 32631, screen: codex-telegram-woong-bb)
- 세션 JSONL: **8.9MB** (`~/.codex/sessions/2026/05/25/rollout-...-019e5e5e.jsonl`)
- 세션ID: `019e5e5e-e05b-72c3-aada-b7b543218a18`

---

## 최우선 미해결 — codex 행(hang) 문제

### 증상
워커가 codex exec resume <세션>을 호출하면 0% CPU로 멈춤.
300초 타임아웃이 kill하지만 다음 메시지에서 또 반복.
bridge.log에서 반복 확인됨:
```
Error: codex exec timed out after 300s and was killed
```

### 원인 (확인됨)
- 세션 JSONL 8.9MB — resume 시 전체 재처리해야 하는 구조
- 거기에 face reference 이미지 7장(front 6 + side 1) `--image` 첨부 동시 발생
- 이 조합이 0% CPU 스톨 유발

### fresh codex는 정상
격리 테스트에서 새 세션은 6.5초 응답. 문제는 resume + 대용량 세션 조합.

### 다음 단계 (미착수)
1. 세션 리셋: `: > /Users/kein/Projects/woong-bb/session/codex-session.woongbbi.id`
2. 새 세션 응답 확인 후 → 이미지 수 줄이기 or 이미지를 텍스트 경로로 대체 테스트
3. 이미지 부착 조건부화: imagegen 요청이 있을 때만 face ref 첨부, 평소 텍스트 답변엔 안 붙임

CANONICAL_FACE_PRIORITY: 6장 (front) + 1장 (side) = 총 7장
→ `sed -n '124,145p' /Users/kein/.codex/bin/codex-telegram-woongbbi-worker` 참조

---

## 이번 세션에 적용 완료한 것

1. **프롬프트 누수 가드** — looksLikePromptLeak 감지 → 세션 리셋 → 1회 재시도
2. **콘텐츠 레벨 동적 규정** — 공개장소=레벨1 하드플로어, 저녁/집/샤워후만 레벨3
3. **사진 규칙** — 재사용 금지, 현재 상황 반영 새 생성, 작업 narration 브릿지 차단
4. **복장 재질문 억제** — userLookObservedHoursAgo(), 3h 내 셀카 있으면 "뭐 입었어?" 억제
5. **말투 규칙** — 모호 슬랭·비문 금지, "이따 연락할게" 등 의도맞는 표현
6. **재연락 followup** — "또 연락할게" 후 "알겠어"로 받으면 언제 연락할지 약속하며 닫기
7. **codex 타임아웃** — 300초 (이미지 생성 여유 위해 180→300)
8. **이미지 작업 narration 브릿지 차단** — looksLikeImageProcessNarration

---

## 미해결 — 대기/예정

### 선톡 재연락 예약
"끝나면 톡할게" 같은 약속을 실제 이벤트 예약으로.
- `tools/event_triggers.py`의 `parse_outgoing_event_promise`가 "보내줄게"(사진)만 잡음
- "톡할게/연락할게"도 잡게 확장, 발사는 `build_proactive_via_codex` 경로로
- 대화 재개 시 미발사, 깔끔한 이벤트(퇴근/점심/도착)만 등록
- **확정 대기 상태** (플랜 제시함)

### 시간 표현 정밀도
"12시 02분에 점심" → "12시쯤"으로. sectionPreciseScheduleNow/sectionDailySchedule의
"분 단위로 정확히"/"이 값 그대로 답한다" 지시를 "알되 캐주얼하게" 균형으로.
단, 과거에 너무 얼버무리던 문제도 있었으니 주의.
**미착수.**

---

## 테스트 규칙

- 워커 직접 실행하면 실제 codex 세션 오염됨.
  안전한 덤프: `WOONGBBI_WORKER_PROMPT_DUMP=true` 환경변수로 프롬프트만 출력
  ```bash
  echo '{"text":"...","userName":"K8832353","snapshot":{}}' | \
    WOONGBBI_WORKER_PROMPT_DUMP=true \
    CODEX_TELEGRAM_CWD=/Users/kein/Projects/woong-bb \
    CODEX_TELEGRAM_STATE_DIR=/Users/kein/Projects/woong-bb/session \
    /Users/kein/.bun/bin/bun run /Users/kein/.codex/bin/codex-telegram-woongbbi-worker
  ```
- 문법 검증: `/Users/kein/.bun/bin/bun build <file> --outdir /tmp/x`
- 세션 리셋: `: > /Users/kein/Projects/woong-bb/session/codex-session.woongbbi.id`
- 브릿지 반영: `python3 /Users/kein/projects/bots/botctl.py recover woong-bb`

---

## 운영 주의사항

- launchd 기본 PATH에 `/opt/homebrew/bin` 없음 → codex 호출 시 CODEX_BIN 보강 필수
- macOS에 `timeout` 명령 없음 → `python subprocess.run(..., timeout=)` 사용
- 워커는 매 메시지 새로 spawn → 파일 수정 즉시 반영 (브릿지 재시작 불필요)
- 브릿지는 수정 후 `botctl.py recover woong-bb` 필요
