# Counterpart State Memory Design

## Purpose
- 상대가 직접 말한 상태를 단발성 추론으로 흘리지 않고, 해제 신호가 올 때까지 유지하는 기억 레이어를 정의한다.
- 최근 대화 몇 줄만 보고 `지금은 괜찮은데 어제 아팠던 거`나 `주말에 가기로 한 약속`을 놓치는 문제를 줄인다.
- `user_conversation_state.json`의 즉시 응답용 추론과 `counterpart_state_memory.json`의 지속 기억을 분리한다.

## Core Model
- `user_conversation_state.json`
  - 지금 답장 톤과 follow-up 억제 여부를 바로 결정하기 위한 현재 추론 요약.
- `counterpart_state_memory.json`
  - 상대가 말한 상태를 active/resolved로 관리하는 장기 상태 메모리.
  - 주말 약속, 최근 장소, 현재 위치 같은 sticky fact도 함께 보관.

## Active State Rules
- 아래 상태는 시작 신호가 잡히면 active로 유지한다.
  - `sleeping_or_falling_asleep`
  - `sick_or_unwell`
  - `driving_or_in_transit`
  - `traveling_or_on_business_trip`
  - `working_or_busy`
  - `resting`
  - `eating`
- active 상태는 시간이 지났다는 이유만으로 바로 지우지 않는다.
- 아래 둘 중 하나가 들어오면 resolved로 정리한다.
  - 명시적 해제 신호
  - 다른 상태가 들어오며 이전 상태 종료가 사실상 확정되는 경우

## Sticky Fact Rules
- 아래 정보는 별도 fact로 유지한다.
  - `weekend_plan`
  - `current_location`
  - `recent_place`
- fact는 active/resolved보다 `최근 기준으로 덮어쓰기`에 가깝다.
- fact는 기본 `value` 문자열을 유지하되, 가능하면 `attributes`에 구조화 정보를 함께 넣는다.
- 예:
  - `이번 주말 강릉 가기로 했어` -> `weekend_plan`
  - `지금 성수에 있어`, `부모님댁 왔어`, `시골 왔어` -> `current_location`
  - `어제 잠실 다녀왔어`, `오늘 성수 들렀어` -> `recent_place`

## Structured Fact Fields
- `weekend_plan.attributes`
  - `summary`
  - `date_hint`
  - `place`
  - `activities`
  - `companion_hint`
- `current_location.attributes`
  - `place`
  - `date_hint`
  - `companion_hint`
- `recent_place.attributes`
  - `place`
  - `date_hint`
  - `activities`
  - `companion_hint`
- `activities`는 `cafe`, `coffee`, `brunch`, `bakery`, `dessert`, `park`, `riverside`, `beach`, `mountain`, `hike`, `movie`, `drama`, `exhibition`, `concert`, `reading`, `bookstore`, `meal`, `dining_out`, `drive`, `workout`, `swim`, `run`, `bike`, `gym`, `pilates`, `yoga`, `walk`, `travel`, `date`, `shopping`, `grocery`, `reset`, `rest` 같은 태그로 구조화한다.

## Output Usage
- 선톡 guard는 `user_conversation_state.json`을 우선 사용하되, 그 값은 `counterpart_state_memory.json`에서 계산된 active state를 반영해야 한다.
- chat runtime snapshot에는 active state key와 sticky fact summary를 함께 넣는다.
- chat runtime snapshot에는 `counterpart_response_guard`도 함께 넣어서, 응답 직전 단계에서 질문 개수, 금지 표현, 권장 톤을 바로 읽을 수 있게 한다.
- chat runtime snapshot에는 `counterpart_fact_recall`도 함께 넣어서, 구조화된 fact를 어떤 방식으로 자연스럽게 회수할지까지 정리한다.
- chat runtime snapshot에는 `counterpart_recall_policy`도 함께 넣어서, fact별 회수 강도를 `soft/confirm/direct`로 조절한다.
- 회수 강도는 저장된 `place`, `activities`, `date_hint`, `companion_hint`에서 만든 화제 별칭과 최근 incoming 메시지의 부분 단서가 얼마나 겹치는지로 계산한다.
- `current_location`, `recent_place`, `weekend_plan`은 fact 종류별 신선도 기간을 따로 두고, 너무 지난 기억은 `suppress`로 내려 실제 답변에서 회수하지 않는다.
- 웅삐 응답 생성 시:
  - 상대가 아프면 걱정 톤 유지
  - 잔다고 했으면 기상 전까지 깨우는 흐름 억제
  - 출장/여행 중이면 답장 압박을 낮춤
  - 주말 약속/장소 기억은 후속 대화에서 회수 가능

## File Contract
- Design: `/Users/kein/Desktop/woong-bb/profile/counterpart_state_memory_design_ko.md`
- Runtime state: `/Users/kein/Desktop/woong-bb/state/counterpart_state_memory.json`
- Summary state: `/Users/kein/Desktop/woong-bb/state/user_conversation_state.json`
- Resolver code: `/Users/kein/Desktop/woong-bb/tools/automation/conversation_guard.py`

## Current Tradeoff
- 문장 구조가 아주 자유로운 한국어라 완전한 의미 추출기는 아니다.
- 대신 project-local 규칙 기반으로 시작/해제 신호를 안정적으로 관리한다.
- 새 패턴이 반복되면 이 문서와 `conversation_guard.py` 패턴 목록에 승격해서 계속 확장한다.
