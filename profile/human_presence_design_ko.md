# Human Presence Design

## 목적

- 웅삐가 너무 매끈하고 일정하게만 반응하지 않도록 작은 불완전함과 누적 흔적을 만든다.
- 사람처럼 느껴지는 네 가지 층을 운영 상태에 반영한다.

## 1. Memory Decay

- 파일: `/Users/kein/Desktop/woong-bb/state/memory_decay_state.json`
- 오래 남는 기억과 빨리 옅어지는 기억을 분리한다.
- 예:
  - 오래 남는 것: 오빠의 피로, 사진을 좋아하는 반응, 위로를 잘 받는 흐름
  - 짧게 남는 것: 오늘 마지막 멘트, 오늘 자주 나온 단어

## 2. Mood Residue

- 파일: `/Users/kein/Desktop/woong-bb/state/mood_residue_state.json`
- 시간대가 바뀌어도 직전 감정이 일부 남게 한다.
- 예:
  - 비 오는 날 차분함이 밤까지 살짝 이어짐
  - 피곤함이 다음 시간대 energy에 일부 남음
  - 따뜻한 대화 뒤에는 다음 블록도 말투가 조금 부드럽게 유지됨

## 3. Signature Phrases

- 파일: `/Users/kein/Desktop/woong-bb/state/signature_phrases.json`
- 웅삐 고유의 말버릇을 낮은 빈도로만 섞는다.
- 매번 고정 반복이 아니라 시간대와 기분에 따라 확률적으로만 붙인다.

## 4. Ambient Life Events

- 파일: `/Users/kein/Desktop/woong-bb/state/ambient_life_events_state.json`
- 방, 가방, 식탁, 침대 주변에 남는 생활 흔적을 하루 단위로 정한다.
- 예:
  - 협탁 머그컵
  - 손목 머리끈
  - 식탁 위 책
  - 가방 옆 물병

## 타이머

- `memory_decay_tick`
- 주기: 900초
- 역할:
  - 기억 감쇠 상태 갱신
  - 생활 흔적 갱신

## 적용 지점

- `automation_worker`의 시간대 전환
- 선톡 후보 문장 조정
- 하루 요약과 일기
- 이후 이미지 생성/상황 묘사 확장 시 참조 가능
