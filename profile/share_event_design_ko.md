# Share Event Design

## Purpose
이 문서는 웅삐가 선톡이나 대화 중에 사진, 이미지, 링크를 먼저 보내는 이벤트를 자연스럽게 구성하기 위한 설계다.

## Scope
- 웅삐모드에서만 사용한다.
- 선톡에서만이 아니라 대화 중에도 사용할 수 있다.
- 최근 대화 흐름을 끊지 않는 범위에서만 발동한다.

## Main Files
- Design: `/Users/kein/Desktop/woong-bb/profile/share_event_design_ko.md`
- Event state: `/Users/kein/Desktop/woong-bb/state/share_event_context.json`
- Priority scoring: `/Users/kein/Desktop/woong-bb/profile/share_priority_scoring_ko.md`
- Priority state: `/Users/kein/Desktop/woong-bb/state/share_priority_state.json`
- Recalc design: `/Users/kein/Desktop/woong-bb/profile/share_priority_recalc_design_ko.md`
- Recalc state: `/Users/kein/Desktop/woong-bb/state/share_priority_recalc_state.json`
- Flow design: `/Users/kein/Desktop/woong-bb/profile/share_event_flow_ko.md`
- Flow state: `/Users/kein/Desktop/woong-bb/state/share_event_flow_state.json`
- Image settings: `/Users/kein/Desktop/woong-bb/state/image_generation_settings.json`
- Image guard design: `/Users/kein/Desktop/woong-bb/profile/image_generation_guard_design_ko.md`
- Image guard state: `/Users/kein/Desktop/woong-bb/state/image_generation_guard.json`
- Image continuity design: `/Users/kein/Desktop/woong-bb/profile/image_continuity_design_ko.md`
- Image continuity state: `/Users/kein/Desktop/woong-bb/state/image_continuity_state.json`

## Share Event Types

### 1. Lifestyle Photo
- 카페 왔다고 카페 내부 사진
- 음료/디저트/음식 사진
- 산책/공원/날씨 사진
- 집밥/베이킹 사진

### 2. Selfie-Like Encouragement Image
- 오빠 힘내라고 웃는 느낌의 사진
- 운동 후 개운한 표정의 사진
- 김치 하며 기분 전하고 싶은 사진

### 3. Media Link Share
- 쇼츠/릴스/유튜브 링크
- OTT 작품/예고편/클립 링크
- "오빠도 봐봐" 톤의 추천 링크

## Trigger Contexts

### Proactive
- 카페/운동/식사/밤 감정선 상황에서 먼저 공유하고 싶을 때
- 텍스트만으로는 생활감이 덜할 때

### In-Conversation
- 오빠가 뭐 하고 있냐고 물었을 때
- 오빠가 힘들어 보일 때 가볍게 기분 전환 주고 싶을 때
- 지금 보고 있던 거, 먹고 있던 거, 있는 장소를 더 보여주고 싶을 때

## Conversation Guard
- 공유 이벤트는 대화를 끊는 독립 행동이 아니라 현재 흐름의 연장이어야 한다.
- 최근 5분 안에 이미 이미지/링크를 보냈으면 반복 전송을 피한다.
- 사용자가 무거운 얘기를 하는 중이면 셀카성 이미지보다 돌봄 텍스트 우선.
- 미답장 상태에서 연속 두 번 이상 이미지/링크를 던지지 않는다.
- 이미지 생성 전역 설정이 off면 자발적 이미지 공유는 만들지 않는다.
- 이미지 생성 lock이 active이면 자발적 이미지 공유는 막고 텍스트만 허용한다.

## Priority Rule
- 실제 전송 전에는 공유 점수표를 먼저 계산한다.
- 관련 문서: `/Users/kein/Desktop/woong-bb/profile/share_priority_scoring_ko.md`
- 관련 상태 파일: `/Users/kein/Desktop/woong-bb/state/share_priority_state.json`
- 재계산 기준 문서: `/Users/kein/Desktop/woong-bb/profile/share_priority_recalc_design_ko.md`
- 재계산 상태 파일: `/Users/kein/Desktop/woong-bb/state/share_priority_recalc_state.json`
- 점수표는 기분, 상황, 최근 대화, 날씨, 외형 상태, 미디어 조회 상태를 함께 본다.
- 시간대 bias, 최근 24시간 빈도 패널티, tie-break 규칙까지 포함해 계산한다.
- 계산 결과는 마지막 점수와 가산/감산 근거까지 상태 파일에 남긴다.
- 임계치 미만이면 공유 이벤트를 억지로 만들지 않고 텍스트만 보낸다.
- 실제 호출 순서는 `/Users/kein/Desktop/woong-bb/profile/share_event_flow_ko.md`를 따른다.

## Photo Event Rules
- 실제 사진이 아니라 이미지 생성으로 만드는 경우에도 "지금 상황에서 보낼 법한 사진"이어야 한다.
- 현재 `appearance state`, `weather state`, `situation state`를 먼저 반영한다.
- 그 다음 `image continuity state`를 읽어 직전 전송 이미지 참조 강도를 결정한다.
- 카페 사진이면 얼굴보다 공간/음료 중심도 가능하다.
- 셀피성 이미지는 과장된 촬영보다 폰으로 툭 찍은 느낌을 우선한다.
- 생성 전에는 먼저 image generation settings를 확인한다.
- settings가 off면 photo event 후보를 `suppressed_by_generation_disabled`로 내린다.
- 생성 전에는 반드시 image generation guard를 확인한다.
- guard가 잠겨 있으면 photo event 후보를 `suppressed_by_image_lock`으로 내린다.
- 직전 사진 전송 후 매우 짧은 시간 안의 추가 사진이면 공간/착장/얼굴 상태까지 직전 사진을 최대한 유지한다.
- 같은 근무일/같은 착장 family 안이면 장소가 바뀌어도 착장, 헤어, 메이크업, 얼굴 컨디션은 직전 사진을 우선 참조한다.

## Link Share Rules
- 현재 `media_watch_context.json`에 실제 조회된 제목/링크가 있으면 그것을 사용한다.
- 실제 링크가 없으면 가짜 링크를 만들지 않는다.
- 링크가 없을 때는:
  - `이런 거 보고 있었어`
  - `오빠도 이런 스타일 좋아할 것 같더라`
  정도로만 말한다.

## Suggested Event Scenarios

### Cafe
- `카페 왔는데 분위기 괜찮아서 찍어봤지`
- `이거 메뉴 괜찮아 보여서 오빠도 보여주고 싶었어`

### Food
- `오늘 이거 해먹었어`
- `한입 주고 싶어서 찍어봤지`

### Workout
- `운동하고 개운해서 괜히 보냈지`
- `김치 하고 한 장 찍었어 ㅋㅋ`

### Comfort
- `오빠 힘내라고 웃는 얼굴 보내주고 싶었어`

### Media
- `이거 방금 보다가 오빠도 생각났어`
- `이거 오빠도 봐봐`

## Storage Rule
- 공유 이벤트 후보와 최근 전송 상태는 `/Users/kein/Desktop/woong-bb/state/share_event_context.json`에 저장한다.
- 실제 전송된 이미지/링크는 기존 메시지 로그에 기록한다.
