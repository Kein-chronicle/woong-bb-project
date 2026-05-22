# Review Observability Design

## 목적

- 세팅모드에서 웅삐의 대화/선톡/음성/감정 흐름을 검토하고 패턴 분석할 수 있게 한다.
- "무엇을 보냈는지"보다 "왜 그렇게 보냈는지"를 남기는 데 초점을 둔다.

## 관측 대상

### 1. response_decision_log
- 경로: `/Users/kein/Desktop/woong-bb/state/logs/response_decision_log.jsonl`
- 용도:
  - 텍스트/음성/이미지/링크 중 무엇을 골랐는지
  - planned / sudden 여부
  - 억제되었으면 이유가 무엇인지
  - 당시 활동, 기분, 가드 상태가 어땠는지

### 2. mood_timeline
- 경로: `/Users/kein/Desktop/woong-bb/state/mood_timeline.json`
- 용도:
  - 하루 동안 `surface_mood`, `energy`, `affection`, `care_bias`, `current_activity` 변화 기록
  - 왜 특정 시간대 답변/선톡 톤이 그랬는지 역추적

### 3. proactive_pattern_report
- 경로: `/Users/kein/Desktop/woong-bb/state/proactive_pattern_report.json`
- 용도:
  - planned / sudden 비율
  - 시간대별 선톡 시도/발송/억제 건수
  - 억제 사유 상위
  - 너무 규칙적인지 보는 지표

### 4. voice_feedback_log
- 경로: `/Users/kein/Desktop/woong-bb/state/logs/voice_feedback_log.jsonl`
- 용도:
  - 음성 생성 시 프로필, 호흡, 모음 늘임, stability/style 값 기록
  - 세팅모드에서 마스터 피드백을 수동으로 덧붙일 수 있는 기반

### 5. repetition_report
- 경로: `/Users/kein/Desktop/woong-bb/state/repetition_report.json`
- 용도:
  - 최근 3일/7일 자주 나온 표현, 질문, 말버릇
  - 반복 억제 상태가 실제로 어떤 패턴을 막고 있는지 요약

### 6. relationship_progress_notes
- 경로: `/Users/kein/Desktop/woong-bb/state/relationship_progress_notes.json`
- 용도:
  - 감정적으로 의미 있었던 대화
  - 오빠 반응이 좋았던 행동/표현
  - 위로, 사진, 음성, 장난 중 잘 먹힌 방식 누적

### 7. generation_review_state
- 경로: `/Users/kein/Desktop/woong-bb/state/generation_review_state.json`
- 용도:
  - 생성 세션별 요구 분리 기록
  - 시도 횟수
  - 각 시도별 검수 실패 항목
  - `accept / patch / regenerate / regenerate_from_previous / halt_manual_review` 판정

### 8. generation_review events in response_decision_log
- 경로: `/Users/kein/Desktop/woong-bb/state/logs/response_decision_log.jsonl`
- 용도:
  - 세션 생성
  - 요구 추가
  - 시도별 검수 결과
  - 어떤 이유로 패치/재생성 쪽으로 흘렀는지 추적

## 운영 원칙

- runtime 로그는 워커와 음성 스킬이 자동으로 남긴다.
- 수동 피드백은 세팅모드에서 별도 메모를 덧붙일 수 있다.
- 민감한 토큰/ID/raw API 응답은 어떤 로그에도 남기지 않는다.

## 갱신 트리거

- 선톡 판정 시: response_decision_log, proactive_pattern_report
- 시간대 전환 시: mood_timeline
- 음성 생성 시: voice_feedback_log
- 반복 상태 갱신 시: repetition_report
- 강화 학습/기억 감쇠 갱신 시: relationship_progress_notes
- 생성물 검수 루프 수행 시: generation_review_state, response_decision_log
