# Image Generation Guard Design

## Purpose
이 문서는 여러 Codex 세션이 동시에 이미지 생성을 수행할 때 결과 파일 이동이나 전송 단계가 꼬이지 않도록 막는 가드 규칙이다.

핵심 목표:
- 동시 이미지 생성/전송 충돌 방지
- 자발적 사진 전송 억제
- 직접 사진 요청 시 우회 응답 가능

## Main Files
- Design: `/Users/kein/Desktop/woong-bb/profile/image_generation_guard_design_ko.md`
- Global settings: `/Users/kein/Desktop/woong-bb/state/image_generation_settings.json`
- Guard state: `/Users/kein/Desktop/woong-bb/state/image_generation_guard.json`
- Lock file: `/Users/kein/Desktop/woong-bb/state/image_generation.lock`
- Helper: `/Users/kein/Desktop/woong-bb/tools/image_generation_guard.py`

## Why Session-Level Guard
- 시스템 기본 `imagegen` 스킬은 공용이므로 여기서 직접 수정하지 않는다.
- 대신 `woong-bb` 세션 루트에서 공용 락과 상태 파일을 관리한다.
- 이미지 생성, 생성본 이동, Telegram 이미지 전송 직전에는 먼저 전역 on/off를 확인하고, on일 때만 guard를 확인한다.

## Evaluation Order
1. `/Users/kein/Desktop/woong-bb/state/image_generation_settings.json` 확인
2. `generation_enabled=false`면 guard를 보지 않고 즉시 생성 보류 처리
3. `generation_enabled=true`일 때만 lock/guard 확인
4. guard가 비어 있으면 acquire 후 생성 진행

## Guard Rules

### 1. Single Active Image Job
- 한 번에 하나의 이미지 생성 작업만 `active=true`가 될 수 있다.
- active 상태가 살아 있으면 다른 세션은 새 이미지 작업을 시작하지 않는다.

### 2. Lock Contents
- `owner_tag`
- `pid`
- `session_kind`
- `purpose`
- `acquired_at`
- `last_touch_at`
- `ttl_seconds`

### 3. Stale Detection
- 아래 중 하나면 stale 후보로 본다.
  - pid 없음
  - pid는 있으나 프로세스 생존 확인 실패
  - `last_touch_at + ttl_seconds` 초과
- stale 후보는 `clear-stale` 또는 다음 정상 acquire 시 정리 가능하다.

## Decision Rules

### Proactive / Share Event
- 전역 설정이 off면 자발적 사진 생성/전송 금지
- 이 경우 상태는 `suppressed_by_generation_disabled`로 남긴다
- 다른 세션이 lock을 잡고 있으면 자발적 사진 생성/전송 금지
- 이 경우 이미지 share 점수를 0으로 내리고 텍스트만 허용
- 상태는 `suppressed_by_image_lock`로 남긴다

### Direct User Request For Photo
- 오빠가 직접 사진을 요청했는데 전역 설정이 off면 guard 확인도 하지 않는다.
- 웅삐모드에서는 상황형 우회 응답을 사용한다.
- 예:
  - `지금은 사진 바로 보내는 건 잠깐 쉬고 있어서, 조금 있다가 예쁘게 보내줄게`
  - `지금은 사진 쪽이 잠깐 안 돼서, 이따가 챙겨서 보내줄게`
- 세팅모드에서는 이미지 생성이 off라 지금은 보내지 않는다고 단백하게 말한다.
- 오빠가 직접 사진을 요청했는데 lock이 이미 잡혀 있으면 바로 생성하지 않는다.
- 웅삐모드에서는 상황형 우회 응답을 사용한다.
- 예:
  - `지금은 사진 바로 보내기 조금 애매해서, 이따 예쁘게 보내줄게`
  - `지금 잠깐 꼬일 수 있어서, 조금 있다가 더 예쁘게 찍어줄게`
- 세팅모드에서는 충돌 방지 때문에 보류했다고 단백하게 말한다.

### When Lock Is Free
- 이미지 생성 전 `acquire`
- 생성/이동/전송 완료 후 `release`
- 실패해도 `release` 또는 stale 정리 가능 상태를 남긴다

## Suggested Calls
```bash
python3 /Users/kein/Desktop/woong-bb/tools/image_generation_guard.py status
python3 /Users/kein/Desktop/woong-bb/tools/image_generation_guard.py acquire --owner-tag woong-bb-main --purpose selfie_request
python3 /Users/kein/Desktop/woong-bb/tools/image_generation_guard.py release --owner-tag woong-bb-main
python3 /Users/kein/Desktop/woong-bb/tools/image_generation_guard.py clear-stale
```

## Integration Points
- `/Users/kein/Desktop/woong-bb/profile/telegram_codex_rules.md`
- `/Users/kein/Desktop/woong-bb/profile/mode_rules.md`
- `/Users/kein/Desktop/woong-bb/profile/share_event_design_ko.md`
- 이후 automation worker가 붙으면 이미지 관련 작업 전에도 같은 guard를 확인한다
