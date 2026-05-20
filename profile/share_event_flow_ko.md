# Share Event Flow

## Purpose
이 문서는 공유 이벤트가 실제로 어떤 순서로 호출되고 실행되는지 정의한다.

## Flow Summary
1. 트리거 발생
2. 재계산 필요 여부 확인
3. 필요하면 점수 재계산
4. 텍스트/이미지/링크 후보 결정
5. 전송 가능 여부 확인
6. 실제 전송 또는 텍스트 유지
7. 상태 파일과 메시지 로그 기록

## Trigger Sources
- 선톡 후보 생성
- 사용자의 질문
- 시간대 전환
- 미디어 실제 조회 성공
- 외형/상황/날씨 상태 변화
- 이미지/링크 전송 직후

## Detailed Runtime Order

### Step 1. Trigger Classification
- `proactive_start`
- `conversation_reply`
- `user_prompt_share`
- `media_lookup_success`
- `time_block_transition`

### Step 2. Recalc Check
- `/Users/kein/Desktop/woong-bb/state/share_priority_recalc_state.json` 확인
- `needs_recalc=true`면 재계산
- `pending_trigger`가 현재 이벤트와 맞으면 재계산
- 같은 분 안 중복 계산이면 생략 가능

### Step 3. Score Evaluation
- `/Users/kein/Desktop/woong-bb/profile/share_priority_scoring_ko.md` 기준으로 계산
- 입력 상태:
  - `eunbi_presence.json`
  - `weather_context.json`
  - `eunbi_appearance_state.json`
  - `media_watch_context.json`
  - `share_event_context.json`

### Step 4. Candidate Selection
- 점수 결과에 따라 후보를 고른다.
- 예:
  - `text_only`
  - `text_plus_image`
  - `text_plus_link`

### Step 5. Candidate Refinement

#### If `text_plus_image`
- 먼저 `/Users/kein/Desktop/woong-bb/tools/image_continuity_resolver.py`를 실행해 continuity 상태를 갱신
- `/Users/kein/Desktop/woong-bb/state/image_continuity_state.json` 확인
- 이미지 타입 선택:
  - `cafe_scene`
  - `drink_or_food`
  - `home_cooking`
  - `soft_selfie_encouragement`
  - `workout_afterglow`
  - `night_home_relaxed_selfie`
- 현재 외형/날씨/상황에 맞는 설명으로 이미지 생성 준비
- `preserve_scope=full_scene_reference`면 직전 전송 이미지를 공간/착장/얼굴 상태 전체 참조로 사용
- `preserve_scope=outfit_face_reference`면 직전 전송 이미지를 착장/헤어/메이크업/얼굴 상태 참조로 사용하고 공간은 새 상황에 맞게 변경 가능
- `preserve_scope=no_direct_image_reference`면 기존 appearance state + curated reference만 사용

#### If `text_plus_link`
- `media_watch_context.json`에서 실제 URL 확인
- URL 있으면 링크 포함
- URL 없으면 카테고리 언급만 하고 실제 링크는 보내지 않음

### Step 6. Delivery Guard
- 최근 5분 쿨다운 확인
- 미답장 rich share 수 확인
- 현재 대화가 무거운지 확인
- 막히면 `text_only`로 다운그레이드

### Step 7. Delivery
- 텍스트만: 답장 전송
- 이미지 포함:
  - 이미지 생성
  - 날짜별 폴더 저장
  - Telegram 이미지 전송
  - 텍스트 보조 문장은 별도 텍스트 메시지로 전송
  - 이미지 자체는 caption 없이 전송
- 링크 포함:
  - 텍스트 + 링크 전송

### Step 8. State Update
- `share_priority_state.json` 업데이트
- `share_priority_recalc_state.json` 업데이트
- `share_event_context.json`의 마지막 전송 시각 업데이트
- `image_continuity_state.json`의 마지막 전송 이미지와 snapshot 업데이트
- `messages/YYYY-MM-DD.jsonl` 기록

## Night Home Relaxed Exception
- `night_home_relaxed` + `bare` + 따뜻한 감정선이면 `night_home_relaxed_selfie` 후보를 열어둔다.
- 이 경우 민낯 홈웨어/잠옷차림 이미지를 과하게 막지 않는다.
- 단, 무거운 대화 중이거나 최근 셀피 공유가 있었다면 다시 보수적으로 조정한다.

## Failure Fallback
- 이미지 생성 실패 -> `text_only` 또는 `text_plus_link`
- 링크 없음 -> `text_only`
- 쿨다운/미답장 제한 -> `text_only`

## Storage Rule
- 호출 흐름의 마지막 선택과 결과는 상태 파일과 메시지 로그에 남긴다.
