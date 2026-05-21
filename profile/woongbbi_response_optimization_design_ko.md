# Woongbbi Response Optimization Design

## 목적

- 웅삐모드에서만 응답 경로를 최적화한다.
- 모든 메시지를 같은 비용으로 해석하지 않고, 상황에 따라 `direct`, `fast`, `full` 경로로 나눈다.
- 목표는 무조건 빠른 응답이 아니라, 필요한 만큼만 해석 비용을 쓰는 것이다.

## 적용 범위

- 적용 대상: `woongbbi` mode
- 비적용 대상: `setting` mode
- setting mode는 항상 충분한 읽기와 충분한 판단을 우선하는 `full` 경로를 기본값으로 둔다.

## 핵심 원칙

1. 빠를 수 있을 때만 빠르게 간다.
2. 감정선과 관계 맥락이 중요한 메시지는 얕게 처리하지 않는다.
3. 앞단 최적화는 응답 품질을 해치지 않는 범위에서만 사용한다.
4. 라우터는 원본 상태 파일 여러 개를 직접 읽지 않고, 축약된 snapshot을 우선 참조한다.

## 목표 구조

### 1. direct path

- 규칙만으로 안전하게 바로 처리 가능한 경우
- 예:
  - `/웅삐온`
  - 단순 확인
  - 이미 스킬 호출이 명확한 경우
  - 짧은 고정 응답이 자연스러운 경우

특징:
- Codex 깊은 추론 최소화
- snapshot만 참고하거나, 아예 규칙만으로 처리
- 가장 낮은 비용

### 2. fast path

- 짧은 대화지만 약간의 맥락은 필요한 경우
- 예:
  - 직전 흐름을 그대로 받는 짧은 안부
  - 상태 파일에 충분한 근거가 이미 정리되어 있는 경우
  - 감정선이 복잡하지 않은 짧은 이어말하기

특징:
- snapshot 중심
- 최근 대화 요약, 현재 mood/activity, 반복 억제만 보고 답 가능
- full path보다 가볍지만 direct보다는 조금 깊다

### 3. full path

- 감정선, 관계 맥락, 애매함, 생성 판단이 중요한 경우
- 예:
  - 위로/애정/감정적 미묘함
  - 이미지/음성/링크/선톡 판단
  - 설정성 질문이 섞인 경우
  - 관계 온도 조절이 필요한 경우

특징:
- 현재 구조의 full Codex 응답 경로
- 필요한 참조 문서와 상태를 더 넓게 읽는다

### 4. deferred/background path

- 지금 답장 자체보다 뒤에서 정리해두는 것이 중요한 작업
- 예:
  - 강화학습 반영
  - 관계 메모
  - 반복 리포트
  - 감정 타임라인

특징:
- 사용자 응답과 분리
- worker가 담당

## Front Router

- 브리지 앞단에서 웅삐모드 메시지를 먼저 분류한다.
- 라우터는 아래 입력만 우선 본다.
  - 현재 mode
  - `chat_runtime_snapshot.json`
  - 메시지 길이
  - 메시지 유형 추정
  - 최근 왕복 여부
  - 직접 요청 키워드

### router output

- `direct`
- `fast`
- `full`
- `reject_or_defer`

## Chat Runtime Snapshot

- 경로: `/Users/kein/Desktop/woong-bb/state/chat_runtime_snapshot.json`
- worker가 주기적으로 갱신한다.
- 브리지와 fast path는 이 파일을 최우선으로 본다.

### snapshot 최소 필드

- `current_mode`
- `current_activity`
- `current_time_block`
- `surface_mood`
- `energy_level`
- `affection_level`
- `care_bias`
- `reply_variance_profile`
- `blocked_phrases`
- `conversation_guard_summary`
- `top_memory_keys`
- `available_rich_channels`
- `recommended_response_path`
- `last_updated_at`

### snapshot 목적

- 브리지가 원본 상태 파일 10개 이상 직접 읽지 않게 하기
- fast path 판정을 위한 얇은 현재 상태 제공
- 응답 경로 선택 비용을 줄이기

## Message Classification

### direct 후보

- 짧은 확인
- 명령형 토글
- 명확한 스킬 호출
- 완전 고정형 반응이 자연스러운 경우

### fast 후보

- 1~2문장 안부
- 직전 질문에 대한 짧은 대답
- 현재 mood/activity만 알면 자연스럽게 이어갈 수 있는 경우
- 관계 해석이 깊지 않은 경우

### full 후보

- 감정적으로 무거움
- 사진/음성/링크 관련 판단
- 애매하거나 중의적인 표현
- 관계 온도 조절 필요
- 기억, 여운, 생활 맥락을 더 깊게 써야 자연스러운 경우

## Heuristic Examples

### direct
- `잘잤어?`
- `지금 뭐해?`
- `목소리 보내줘`

### fast
- `나 이제 출근해 ㅋㅋ`
- `웅삐도 졸려?`
- `오늘 좀 피곤하네`

### full
- `요즘 나한테 어떤 마음이야?`
- `사진 보내고 싶지 않아?`
- `오늘 나 좀 많이 지친 것 같아`
- `갑자기 보고싶어졌어`

## Guard Rules

- 아래 중 하나라도 걸리면 `fast`에서 `full`로 승격한다.
  - 감정 위험도 높음
  - 최근 대화 흐름이 무거움
  - 최근 억제/보류가 있었음
  - 이미지/음성/링크 판단이 필요함
  - 직접적 관계 표현이 들어옴

## Fast Path 제약

- fast path는 새 이벤트를 만들지 않는다.
- fast path는 복잡한 멀티미디어 판단을 하지 않는다.
- fast path는 최근 snapshot과 최근 1~3개 메시지 요약만 사용한다.
- fast path 결과가 애매하면 바로 full로 승격한다.

## Worker 역할

- worker는 원본 상태를 계속 정리한다.
- 브리지 최적화 자체를 worker가 하지 않는다.
- worker는 아래만 준비한다.
  - snapshot 갱신
  - conversation guard 요약
  - 추천 경로 힌트
  - 최근 감정 여운 요약

## 브리지 역할

- 브리지는 현재 mode 확인
- 웅삐모드면 router 실행
- router 결과에 따라
  - direct 처리
  - fast prompt
  - full prompt
  로 분기

## Prompt Layering

### fast prompt

- snapshot 기반 현재 상태만 넣음
- 최근 메시지 소량만 넣음
- 문서 참조 최소화
- 짧고 자연스러운 답 우선

### full prompt

- 기존처럼 필요한 상태와 규칙을 더 넓게 사용
- 감정선, 기억, 관계, 멀티미디어 판단 가능

## 관측 로그

- 라우터 결과도 `response_decision_log.jsonl`에 남긴다.
- 필드 예:
  - `router_path`
  - `router_reason`
  - `router_inputs_summary`
  - `escalated_to_full`

## 구현 순서

1. snapshot 상태 파일 정의
2. worker에 snapshot 갱신 추가
3. 브리지에 woongbbi 전용 router 추가
4. fast/full prompt 분리
5. direct handler 목록 정리
6. decision log에 router 결과 기록

## 성공 기준

- 웅삐모드에서 단순 메시지는 더 얕은 비용으로 처리 가능
- 감정적으로 중요한 메시지는 계속 full path 유지
- setting mode는 기존처럼 충분히 생각하는 경로 유지
- 응답 품질 저하 없이 평균 해석 비용 감소
