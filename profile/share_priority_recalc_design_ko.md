# Share Priority Recalc Design

## Purpose
이 문서는 공유 우선순위 점수표를 언제 다시 계산해야 하는지 정의한다.

핵심은 "항상 계산"이 아니라, 상태가 의미 있게 바뀐 순간에만 재평가하는 것이다.

## Main Files
- Design: `/Users/kein/Desktop/woong-bb/profile/share_priority_recalc_design_ko.md`
- Recalc state: `/Users/kein/Desktop/woong-bb/state/share_priority_recalc_state.json`

## Recalc Trigger Categories

### 1. Time Block Transition
- `waking_up -> getting_ready`
- `getting_ready -> commuting_to_work`
- `morning_shift -> lunch_break`
- `afternoon_shift -> commuting_home`
- `commuting_home -> dinner_or_cooking`
- `dinner_or_cooking -> exercise_or_cafe`
- `exercise_or_cafe -> night_wind_down`

이런 전환은 공유 성향이 크게 바뀌므로 재계산한다.

### 2. Situation State Update
- `current_activity`가 바뀜
- `surface_mood`가 바뀜
- `weather_context`가 바뀜
- `appearance_branch`가 바뀜
- `media_watch_context`가 갱신됨

### 3. Conversation Event Trigger
- 사용자가 `뭐 하고 있었어`, `뭐 보고 있었어`, `사진`, `보고싶다`, `힘내` 같은 공유 친화 키워드를 말함
- 사용자가 지침, 피곤함, 우울함을 표현함
- 최근 대화의 감정선이 가벼움에서 진지함으로 또는 반대로 바뀜

### 4. Rich Share Lifecycle
- 이미지 전송 직후
- 링크 전송 직후
- 미답장 상태가 해소됨
- 최근 5분 쿨다운 해제됨

## Recalc Priority

### Immediate
- 사용자가 직접 공유 관련 질문을 함
- 실제 링크가 새로 확보됨
- 이미지를 방금 보냈음
- 현재 모드 전환됨

### Soon
- 시간대 전환
- 날씨 상태 갱신
- 운동/카페/식사/귀가 같은 활동 전환

### Lazy
- 단순 시간이 몇 분 흘렀을 뿐 큰 상태 변화 없음
- 이런 경우는 다음 명시적 이벤트까지 재계산 생략 가능

## Suggested Trigger Map
- `/웅삐온` 직후: 1회 계산
- 선톡 후보 생성 직전: 계산
- 유저 메시지 수신 직후: 키워드와 감정선 확인 후 조건부 계산
- 미디어 실제 조회 성공 직후: 계산
- 외형 상태 전환 직후: 조건부 계산
- 이미지/링크 전송 후: 쿨다운 반영 계산

## Minimal Runtime Fields
- `needs_recalc`
- `last_recalc_at`
- `last_recalc_reason`
- `next_suggested_recalc_at`
- `pending_trigger`

## Practical Rule
- 상태가 안 바뀌었으면 반복 계산하지 않는다.
- 같은 분 안에 중복 계산을 막는다.
- 다만 사용자가 직접 공유를 유도하는 질문을 하면 즉시 재계산한다.
