# Share Event Flow

## Purpose
이 문서는 공유 이벤트가 실제로 어떤 순서로 호출되고 실행되는지 정의한다.

## Main Files
- Flow design: `/Users/kein/Desktop/woong-bb/profile/share_event_flow_ko.md`
- Share priority scoring: `/Users/kein/Desktop/woong-bb/profile/share_priority_scoring_ko.md`
- Share event context: `/Users/kein/Desktop/woong-bb/state/share_event_context.json`
- Image continuity state: `/Users/kein/Desktop/woong-bb/state/image_continuity_state.json`
- User-shared photo asset design: `/Users/kein/Desktop/woong-bb/profile/user_shared_photo_asset_memory_design_ko.md`
- User-shared photo asset registry: `/Users/kein/Desktop/woong-bb/state/user_shared_photo_asset_registry.json`
- User-shared photo asset tool: `/Users/kein/Desktop/woong-bb/tools/user_shared_photo_asset_memory.py`

## Flow Summary
1. 트리거 발생
2. 재계산 필요 여부 확인
3. 필요하면 점수 재계산
4. 텍스트/이미지/링크 후보 결정
5. 생성 세부 계획 준비
6. 생성물 검수 루프
7. 전송 가능 여부 확인
8. 실제 전송 또는 텍스트 유지
9. 상태 파일과 메시지 로그 기록

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
- 사용자가 직접 사진을 요청한 경우에는 점수표 임계치보다 직접 요청 override를 우선한다.
- 직접 요청 override가 켜지면 `generation_enabled`와 guard만 확인하고, 가능하면 안전한 `text_plus_image`로 진행한다.
- 불가능하면 `text_only`로 내려가되, 보류 답변에는 기대감과 안전 사진 타입을 남긴다.

### Step 5. Candidate Refinement

#### If `text_plus_image`
- 먼저 `/Users/kein/Desktop/woong-bb/tools/image_continuity_resolver.py`를 실행해 continuity 상태를 갱신
- `/Users/kein/Desktop/woong-bb/state/image_continuity_state.json` 확인
- `/Users/kein/Desktop/woong-bb/profile/generation_review_loop_design_ko.md` 기준으로 이번 요구 중 generation/review/hybrid를 분리
- 이미지 타입 선택:
  - `cafe_scene`
  - `drink_or_food`
  - `home_cooking`
  - `soft_selfie_encouragement`
  - `workout_afterglow`
  - `night_home_relaxed_selfie`
- 직접 사진 요청 또는 로맨틱 대화 중 사진 요청일 때 추가 타입:
  - `soft_close_selfie`
  - `cozy_bedside_selfie`
  - `after_shower_cozy_selfie`
  - `date_mood_mirror_selfie`
- 수위 있는 사진 요청은 노출/행위 중심을 버리고 위 안전 타입 중 가장 가까운 것으로 변환
- "그 컵", "같은 컵", "같은 거 샀잖아", "커플티", "그 악세사리", "같이 찍은 사진 느낌"처럼 오빠가 이전 수신 사진 자산을 가리키면 `user_shared_photo_asset_memory.py search`로 registry 후보를 찾는다.
- 후보가 있으면 `canonical_path`, `reusable_subjects`, `generation_reuse.prompt_hints_ko`를 보조 참조로 넣는다.
- 웅삐 얼굴/몸 참조는 기존 은비 reference dataset을 계속 우선한다.
- 오빠가 보낸 사진은 기본적으로 소품/착장/장소/분위기 참조로 사용한다.
- 오빠가 "같이 있는 장면", "오빠랑 같이", "둘이 찍은 사진", "오빠 얼굴도 같이"처럼 명시하면 `person_context` 자산의 오빠 얼굴을 user identity reference로 사용한다.
- 오빠 얼굴 참조는 오빠에게만 적용하고, 웅삐 얼굴/몸 참조를 대체하지 않는다.
- 다른 사람 얼굴이 들어간 자산은 별도 명시 없이 얼굴 재현 참조로 쓰지 않는다.
- 현재 외형/날씨/상황에 맞는 설명으로 이미지 생성 준비
- `preserve_scope=full_scene_reference`면 직전 전송 이미지를 공간/착장/얼굴 상태 전체 참조로 사용
- `preserve_scope=outfit_face_reference`면 직전 전송 이미지를 착장/헤어/메이크업/얼굴 상태 참조로 사용하고 공간은 새 상황에 맞게 변경 가능
- `preserve_scope=no_direct_image_reference`면 기존 appearance state + curated reference만 사용
- `generation + hybrid` 조건만 먼저 prompt/shot plan에 반영하고, 나머지는 검수 체크리스트로 남긴다

#### If `text_plus_link`
- `media_watch_context.json`에서 실제 URL 확인
- URL 있으면 링크 포함
- URL 없으면 카테고리 언급만 하고 실제 링크는 보내지 않음

### Step 6. Generation Review Loop

- 첫 생성 결과를 바로 쓰지 말고 검수한다.
- 검수 체크는 `review + hybrid` 조건으로 한다.
- 검수 결과는 아래 중 하나로 판정한다.
  - `accept`
  - `patch`
  - `regenerate`
  - `regenerate_from_previous`
- 최대 10회까지 반복한다.
- 각 시도와 판정은 `/Users/kein/Desktop/woong-bb/state/generation_review_state.json`과 `/Users/kein/Desktop/woong-bb/state/logs/response_decision_log.jsonl`에 남긴다.
- 이미지 예시:
  - 최근 각도 반복 여부
  - 셀피 authenticity
  - 현재 시간/상황/복장 적합성
  - continuity 유지 여부
  - user-shared asset을 썼다면 요청한 물건/착장/장소가 맞는지
  - user-shared asset의 사람 얼굴이 불필요하게 재현되지 않았는지
  - 같이 있는 장면이면 오빠 얼굴 참조가 요청과 맞게 적용됐는지
  - 웅삐 얼굴/몸 참조가 user-shared asset으로 대체되지 않았는지
  - 로맨틱 사진 요청이면 완전 착의, 얼굴/상반신/분위기 중심인지
  - 침대/샤워/잠옷 맥락이 노출이나 성적 포즈로 흐르지 않는지
- 텍스트 예시:
  - 어색한 문장 여부
  - 지금 대화 흐름과의 적합성
  - 시간대/관계 온도 적합성
  - 사진이 불가능할 때도 기대감과 다음 안전 대체안이 남아 있는지

### Step 7. Delivery Guard
- 최근 5분 쿨다운 확인
- 미답장 rich share 수 확인
- 현재 대화가 무거운지 확인
- 막히면 `text_only`로 다운그레이드

### Step 8. Delivery
- 텍스트만: 답장 전송
- 이미지 포함:
  - 이미지 생성
  - 날짜별 폴더 저장
  - Telegram 이미지 전송
  - 텍스트 보조 문장은 별도 텍스트 메시지로 전송
  - 이미지 자체는 caption 없이 전송
- 링크 포함:
  - 텍스트 + 링크 전송

### Step 9. State Update
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
