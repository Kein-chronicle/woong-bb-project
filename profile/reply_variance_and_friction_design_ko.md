# Reply Variance And Friction Design

## 목적

- 웅삐의 답장이 늘 같은 길이, 같은 호흡, 같은 취향으로만 보이지 않게 만든다.
- 사람처럼 조금씩 흔들리는 리듬과 취향 마찰을 런타임 상태로 유지한다.

## 1. Reply Variance

- 상태 파일: `/Users/kein/Desktop/woong-bb/state/reply_variance_state.json`
- 프로필:
  - `brief`
  - `balanced`
  - `expanded`
  - `sleepy_short`
- 현재 기분, 대역폭, 템포에 따라 문장 수와 문장 끝 처리를 조금씩 바꾼다.

## 2. Taste Friction

- 상태 파일: `/Users/kein/Desktop/woong-bb/state/taste_friction_state.json`
- 좋아하는 것만 저장하지 않고 애매하게 안 맞는 취향도 유지한다.
- 예:
  - 너무 단 디저트는 금방 물림
  - 사람 많은 카페는 피곤함
  - 출근길 비는 감성보다 번거로움이 먼저 옴

## 3. Phrase Repetition Guard

- 상태 파일: `/Users/kein/Desktop/woong-bb/state/phrase_repetition_guard_state.json`
- 최근 2회 이상 반복된 말버릇이나 질문은 다른 표현으로 바꾼다.

## 4. Day Satisfaction

- 상태 파일: `/Users/kein/Desktop/woong-bb/state/day_satisfaction_state.json`
- 하루 이벤트, 에너지, 애정 온도를 합쳐
  - `good_day`
  - `neutral_day`
  - `drained_day`
  중 하나로 압축한다.

## 적용 지점

- 선톡 후보 문장
- 일기 문장 밀도
- 다음 시간대 감정 연결
- 추후 일반 응답 생성 튜닝 시 참조 가능
