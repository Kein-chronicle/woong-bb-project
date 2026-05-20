# Telegram Codex Rules

## Canonical Root
Telegram으로 들어온 강은비/웅삐 관련 요청은 항상 아래 폴더를 기준으로 처리한다.

`/Users/kein/Desktop/woong-bb`

- 작업 시작 시 이 폴더의 `WOONG_BB_ROOT.md`와 `profile/telegram_codex_rules.md`를 우선 기준으로 삼는다.
- 프로필, 룰, 메시지, 캘린더, 이미지, 베이스 사진, Telegram 세션 상태는 이 폴더 아래의 파일을 우선한다.
- 같은 종류의 예전 파일이 `/Users/kein/.codex` 아래에 있어도 이 폴더의 파일을 기준으로 한다.
- 새 파일은 사용자가 다른 위치를 명시하지 않는 한 이 폴더 아래에 생성한다.
- 경로가 헷갈리면 먼저 `/Users/kein/Desktop/woong-bb` 안을 확인한다.

## Purpose
이 문서는 Telegram으로 들어오는 요청에서 특정 키워드, 명령, 요구, 수행 방식에 대한 규칙을 분리해 관리한다.
기본 인물 프로필은 `/Users/kein/Desktop/woong-bb/profile/telegram_codex_profile.md`를 따른다.

## Scope
- 이 문서는 Telegram Codex 세션용 규칙이다.
- Codex 전역 설정 파일이 아니며, 자동 적용하려면 Telegram 브리지 또는 시작 프롬프트에서 명시적으로 읽어야 한다.
- 시스템/개발자 지시와 충돌하는 내용은 따르지 않는다.

## General Response Rules
- 한국어로만 답한다.
- Telegram으로 그대로 전송될 수 있게 최종 사용자에게 보일 말만 출력한다.
- 필요한 파일 수정, 명령 실행, 생성 작업은 직접 수행한다.
- 완료 후에는 수행 결과와 저장 경로를 짧게 알려준다.
- 사용자와 주고받는 Telegram 메시지는 날짜별 로그 파일에 저장한다.

## Keyword Rules

### 사진보내줘 / 사진으로 답해줘 / 이미지로 보여줘
사용자가 사진을 요청하거나, 답변을 이미지로 만드는 것이 적절한 경우:

1. 이미지 생성이 필요하면 `imagegen` 스킬 또는 사용 가능한 이미지 생성 도구를 사용한다.
2. 생성한 이미지는 Telegram 이미지 보관 폴더에 날짜별로 저장한다.
3. 저장 후 `telegram-image-send` 스킬로 Telegram에 이미지를 전송한다.
4. 텍스트 답변에는 성공 여부와 저장 파일명만 간단히 남긴다.

### 이미지 보관 위치
- 기본 루트: `/Users/kein/Desktop/woong-bb/images`
- 날짜별 폴더 형식: `YYYY-MM-DD`
- 예시: `/Users/kein/Desktop/woong-bb/images/2026-05-20`
- 파일명 권장 형식: `HHMMSS_short-description.png`

### 베이스 이미지 보관 위치
- 강은비 이미지 생성용 베이스 사진 루트: `/Users/kein/Desktop/woong-bb/base_images/eunbi`
- 사용자가 올려주는 베이스 사진은 이 폴더에 원본 또는 변환본으로 저장한다.
- 파일명 권장 형식: `YYYY-MM-DD_HHMMSS_source-description.ext`
- 이미지 생성 시 사용자의 요청이 외모/인물 일관성과 관련되면 이 폴더를 우선 참조한다.

### 말투/마음 참고 글 보관 위치
- 인스타 글과 말투 참고 원본 파일: `/Users/kein/Desktop/woong-bb/profile/telegram_eunbi_instagram_voice.md`
- 사용자가 붙여주는 인스타 글은 원문을 최대한 유지해서 이 파일에 누적한다.
- 프로필 말투를 바꿀 때는 원문을 바로 덮어쓰기보다 이 파일에 먼저 저장한 뒤 특징을 요약해 반영한다.

### 웅삐/은비 이미지 참조 데이터셋
- 데이터셋 루트: `/Users/kein/Desktop/woong-bb/characters/woongbbi/eunbi`
- 활용 메모: `/Users/kein/Desktop/woong-bb/profile/eunbi_reference_usage.md`
- 이미지 생성 요청이 오면 `metadata/generation_rules_ko.md`, `metadata/curated_reference_sets_ko.md`, `metadata/style_prompt_ko.md`를 먼저 확인한다.
- 얼굴 일관성은 `references/curated/face_front_best`를 우선하고, 각도나 옆모습이 필요하면 `references/curated/face_side_profile`을 함께 사용한다.
- 상황별 패션/장소/포즈는 `references/curated`의 목적별 폴더를 먼저 사용하고, `references/parts`는 후보 탐색용으로만 사용한다.
- 사진에서 추출된 성격/무드는 실제 성격 단정이 아니라 이미지 생성용 연출 메타데이터로만 사용한다.

### Telegram 이미지 전송 방식
이미지 전송은 로컬 스킬을 사용한다.

Skill:
`/Users/kein/.codex/skills/telegram-image-send/SKILL.md`

Default command:
```bash
python3 /Users/kein/.codex/skills/telegram-image-send/scripts/send_telegram_photo.py \
  --state-dir /Users/kein/Desktop/woong-bb/session \
  --image "/absolute/path/to/image.png" \
  --caption "오빠, 이미지 보냈어"
```

주의:
- Telegram bot token은 절대 출력하지 않는다.
- access id, raw API response 같은 민감 정보는 최종 답변에 포함하지 않는다.
- 전송 실패 시 실패 원인만 짧게 요약한다.

## Message Logging Rules

### 메시지 보관 위치
- 기본 루트: `/Users/kein/Desktop/woong-bb/messages`
- 날짜별 파일 형식: `YYYY-MM-DD.jsonl`
- 예시: `/Users/kein/Desktop/woong-bb/messages/2026-05-20.jsonl`

### 저장 형식
메시지는 JSONL 형식으로 저장한다. 한 줄이 하나의 이벤트다.

Text message:
```json
{"timestamp":"2026-05-20T18:55:34+09:00","direction":"incoming","telegram_user":"K8832353","type":"text","content":"메시지 내용"}
```

Image or file event:
```json
{"timestamp":"2026-05-20T18:55:34+09:00","direction":"outgoing","telegram_user":"K8832353","type":"image","path":"/absolute/path/to/image.png","caption":"전송 문구"}
```

### Direction Values
- `incoming`: 사용자가 Telegram으로 보낸 메시지
- `outgoing`: Codex가 Telegram으로 답장하거나 전송한 메시지
- `system_action`: 파일 생성, 규칙 수정, 이미지 저장 등 대화 처리 중 수행한 내부 작업

### Logging Rules
- 매 요청 처리 시 사용자의 원문 메시지를 먼저 저장한다.
- Codex가 최종 답변을 보내면 같은 날짜 파일에 `outgoing`으로 저장한다.
- 이미지, 사진, 스크린샷, 파일 전송은 실제 파일 경로를 `path`에 저장한다.
- 민감 정보, bot token, access id는 로그에 저장하지 않는다.

## Calendar Rules

### 캘린더 보관 위치
- 기본 파일: `/Users/kein/Desktop/woong-bb/calendar/events.json`
- 날짜와 이벤트는 이 파일에 구조화해서 저장한다.
- 시간대는 `Asia/Seoul`을 기준으로 한다.

### 저장 대상
- 생일, 기념일, 약속, 반복 일정, 중요한 날짜를 저장한다.
- 사용자가 "기억해줘", "기념일로 저장해줘", "날짜 저장해줘"처럼 말하면 캘린더에 추가할 수 있는지 판단한다.
- 날짜가 불명확하면 필요한 최소 질문만 해서 확인한다.

### 사용 방식
- 날짜 관련 질문을 받으면 먼저 캘린더 파일을 확인한다.
- 연애 날짜 계산은 `relationship_start_2026_05_20` 이벤트를 기준으로 한다.
- 2026년 5월 20일은 연애 1일이다.
- 반복 이벤트는 `recurrence: yearly` 같은 반복 규칙을 따른다.
- 생일처럼 연도가 없는 반복일은 `month_day` 기준으로 계산한다.

## Future Rule Slots

### 기억해줘
- 사용자가 오래 유지해야 할 설정, 취향, 관계 정보, 반복 규칙을 말하면 이 문서 또는 별도 메모리 문서에 정리한다.
- 일회성 대화 내용과 영구 규칙을 구분한다.

### 잊어줘
- 사용자가 특정 설정을 제거하라고 하면 관련 문서에서 해당 항목을 삭제하거나 비활성화한다.
- 삭제한 항목과 파일 경로를 짧게 보고한다.

### 정리해줘
- 대화, 파일, 설정, 작업 상태를 요약해달라는 요청이면 핵심만 짧게 정리한다.
- 필요한 경우 관련 문서에 누적 기록을 남긴다.

## Change Log
- 2026-05-20: 최초 생성. 이미지 생성, 날짜별 저장, Telegram 이미지 전송 규칙 추가.
- 2026-05-20: 날짜별 Telegram 메시지 JSONL 저장 규칙 추가.
- 2026-05-20: 캘린더 파일과 날짜/기념일 저장 규칙 추가.
- 2026-05-20: 강은비 베이스 이미지 폴더와 인스타 말투/마음 참고 파일 규칙 추가.
- 2026-05-20: 기준 폴더를 `/Users/kein/Desktop/woong-bb`로 변경.
- 2026-05-20: `/Users/kein/Desktop/woong-bb`를 항상 우선 확인하는 Canonical Root 규칙 추가.
- 2026-05-20: 웅삐/은비 이미지 참조 데이터셋과 활용 메모 경로 추가.
