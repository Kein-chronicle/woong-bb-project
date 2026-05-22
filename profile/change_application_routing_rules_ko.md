# Change Application Routing Rules

## 목적

- 패턴 변경, 조건 추가, 신규 스크립트 반영, 말투 수정, 말 길이 수정 같은 요청이 들어왔을 때 어디에 반영해야 하는지 공통 규정으로 고정한다.
- 다른 세션이 들어와도 같은 분류와 같은 용어로 수정 작업을 이어받게 한다.
- 생성 프롬프트만 계속 비대해지는 것을 막고, 생성과 검수의 책임을 분리한다.

## 적용 범위

- setting mode에서 수행하는 설계, 룰, 스크립트 수정 작업 전반
- woongbbi mode의 텍스트, 선톡, 이미지, 음성 생성과 검수 흐름
- 다른 Codex 세션이 이 프로젝트를 이어서 수정할 때의 공통 작업 규칙

## 최상위 원칙

1. 새 요구는 바로 코드 한 군데에 박지 말고 먼저 `generation`, `review`, `hybrid` 중 어디에 속하는지 분류한다.
2. 생성 품질을 올리는 요구와 결과물 판정 요구를 분리한다.
3. 한 번에 완벽하게 만들기보다 `생성 -> 검수 -> patch/regenerate` 루프를 우선한다.
4. 표현 수정은 가능한 한 좁은 레이어에 반영하고, 세계관, 상황, 상태 변화는 상위 설계 문서와 상태에도 반영한다.
5. 반복적으로 등장하는 수정은 개별 세션 메모가 아니라 프로젝트 규정 문서에 승격한다.

## 공통 분류 타입

### generation

- 첫 생성물의 방향을 정하는 요구
- 프롬프트, 샷 플랜, 음성 프로필, 대화 조리법, 선택 로직 쪽에 반영

### review

- 생성 후 결과가 통과 가능한지 판정하는 요구
- 검수 체크리스트, 실패 판정, 반복 억제, 재생성 조건에 반영

### hybrid

- 생성 전에도 반영해야 하고, 생성 후에도 다시 체크해야 하는 요구
- 시간대 적합성, 상황 적합성, 말투 톤, 말 길이, 셀피 authenticity, continuity 계열은 기본적으로 여기에 둔다.

## 요청 타입별 기본 라우팅 규칙

### 패턴 변경

- 예: 질문 패턴, 선톡 시작 패턴, 대화 흐름 shape, 이미지 샷 패턴
- 기본 적용:
  - `generation`: 다음 후보를 고르는 선택 로직, recipe, pattern catalog
  - `review`: 최근 반복 감지, 패턴 중복 탈락 규칙
  - 기본값은 `hybrid`

### 조건 추가

- 예: 시간대 조건, 상황 조건, 관계 온도 조건, 착장 조건
- 기본 적용:
  - 세계관이나 상황을 미리 맞춰야 하면 `generation`
  - 결과가 맞는지 판정만 하면 되면 `review`
  - 대부분은 생성과 판정을 함께 건드리므로 기본값은 `hybrid`

### 신규 스크립트 반영

- 예: 새 helper, 새 상태 갱신기, 새 후처리기, 새 검수 도구
- 기본 적용:
  - 생성물 자체를 만드는 스크립트면 `generation`
  - 품질 판정, 후처리, 보류, 재시도 도구면 `review`
  - 생성 후 수정 지시를 다시 넣는 도구면 `hybrid`

### 말투 수정

- 예: 더 장난기 있게, 덜 들이대게, 반존대 강도 조정
- 기본 적용:
  - 기본 말투를 만드는 프로필, recipe에 반영
  - 어색하거나 과한 톤을 검수 체크에도 반영
  - 기본값은 `hybrid`

### 말 길이 수정

- 예: 답장 1-2문장 선호, 음성 대본 길이 축소, 선톡 길이 짧게
- 기본 적용:
  - 생성 기본 길이 제약은 `generation`
  - 너무 길거나 너무 짧은 결과 탈락은 `review`
  - 기본값은 `hybrid`

## Asset별 적용 기준

### Text

- `generation`:
  - 말투, 기본 길이, 질문/서술 비율, 시간대 톤, 관계 온도
- `review`:
  - 문장 어색함, 맥락 부조화, 반복 질문, 과도한 장문, 지금 보내기 어색함
- `hybrid` 권장:
  - 말투 수정, 길이 수정, 시간대 적합성, 선톡 패턴 변경

### Image

- `generation`:
  - shot type, angle, selfie method, outfit, background, continuity preserve scope
- `review`:
  - 셀피처럼 안 보임, 최근 각도 반복, 복장 불일치, 상황 부적합
- `hybrid` 권장:
  - 각도 다양화, 셀피 authenticity, 복장, 시간대, 상황 적합성

### Voice

- `generation`:
  - 음성 프로필, 호흡, 길이, 감정 톤, 문장 리듬
- `review`:
  - 읽으면 어색함, 너무 긴 대본, 상황과 안 맞는 감정 톤
- `hybrid` 권장:
  - 말 길이, 다정함 강도, 밤, 출근길, 위로 톤

## 실제 반영 위치 규칙

### generation 쪽 반영 우선 위치

- `/Users/kein/Desktop/woong-bb/profile/*.md`
- `/Users/kein/Desktop/woong-bb/tools/automation_worker.py`
- `/Users/kein/Desktop/woong-bb/state/image_prompt_plan.json`
- 관련 state, recipe, catalog 파일

### review 쪽 반영 우선 위치

- `/Users/kein/Desktop/woong-bb/profile/generation_review_loop_design_ko.md`
- `/Users/kein/Desktop/woong-bb/profile/review_observability_design_ko.md`
- `/Users/kein/Desktop/woong-bb/state/generation_review_state.json`
- `/Users/kein/Desktop/woong-bb/state/logs/response_decision_log.jsonl`
- `/Users/kein/Desktop/woong-bb/tools/generation_review_loop.py`

### hybrid 반영 규칙

- 같은 요구를 generation, review 양쪽에 동시에 넣는다.
- 단 wording은 다르게 둔다.
  - generation: 어떻게 처음부터 만들 것인가
  - review: 무엇이 나오면 실패로 볼 것인가

## 수정 요청 처리 순서

1. 요청을 `변경 타입`으로 먼저 분류한다.
2. 그다음 `generation/review/hybrid`를 판정한다.
3. 영향을 받는 asset을 고른다.
4. 반영 위치를 정한다.
5. 좁은 수정이면 `patch`, 방향 자체가 바뀌면 `regenerate` 계열을 택한다.
6. 반복적으로 쓸 규칙이면 반드시 문서화한다.

## 세션 간 전달용 표준 용어

- `change_type`
  - `pattern_change`
  - `constraint_addition`
  - `new_script_integration`
  - `tone_adjustment`
  - `length_adjustment`
- `application_scope`
  - `generation`
  - `review`
  - `hybrid`
- `asset_type`
  - `text`
  - `image`
  - `voice`
- `execution_action`
  - `patch`
  - `regenerate`
  - `regenerate_from_previous`
  - `accept`
  - `hold`

## 세션 인계 템플릿

```text
change_type: tone_adjustment
application_scope: hybrid
asset_type: text
request_summary: 밤 시간대 답장은 조금 더 짧고 나른하게
generation_update: proactive/reply recipe에서 밤 답장 길이와 어휘를 낮춘다
review_update: 밤 답장이 과하게 길거나 텐션이 높으면 실패로 본다
execution_action: patch
source_of_truth: /Users/kein/Desktop/woong-bb/profile/change_application_routing_rules_ko.md
```

## 기본 판정 가이드

- 아래 중 하나면 기본적으로 `generation-only`가 아니라 `hybrid`로 본다.
  - 말투 수정
  - 말 길이 수정
  - 시간대 적합성
  - 상황 적합성
  - 이미지 각도 다양화
  - 셀피 authenticity

- 아래 중 하나면 `review` 비중을 높인다.
  - 어색함 제거
  - 반복 억제
  - 결과물 사용 가능 여부 판정
  - 지금 전송해도 되는지 여부

- 아래 중 하나면 `generation` 비중을 높인다.
  - 신규 기본 규칙 추가
  - 후보 선택 로직 변경
  - 프롬프트, 프로필, 샷 플랜 구조 변경

## 프로젝트 규정

- 다른 세션이 수정 요청을 받으면 이 문서를 먼저 확인한다.
- 분류 없이 바로 프로필이나 스크립트를 수정하지 않는다.
- 반복 가능한 규칙은 세션 내 임시 판단으로 끝내지 않고 문서에 승격한다.
- 문서와 코드가 함께 바뀌는 수정이면 문서를 먼저 기준으로 맞춘다.
- 기존 규칙이 이미 어디에 들어가 있는지 다시 볼 때는 `/Users/kein/Desktop/woong-bb/profile/existing_rule_allocation_matrix_ko.md`를 함께 확인한다.
