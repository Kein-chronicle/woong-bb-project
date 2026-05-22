# Existing Rule Allocation Matrix

## 목적

- 이미 프로젝트에 들어가 있는 규칙들을 `generation-only`, `review-only`, `both` 관점으로 다시 정리한다.
- 생성 쪽에 몰려 있는 항목 중 무엇을 검수에도 중복 반영해야 하는지 명확히 한다.
- 기존 규칙을 없애거나 옮기자는 것이 아니라, 어디에 추가 중복 배치할지 판단 기준을 제공한다.

## 분류 기준

### generation-only

- 결과를 만들기 전에 방향만 정해주면 충분한 규칙
- 결과물을 보고 다시 판정할 필요가 낮은 규칙

### review-only

- 결과를 보고 통과/실패를 판정하는 데 더 적합한 규칙
- 생성 프롬프트에 억지로 넣을수록 품질이 오히려 퍼질 수 있는 규칙

### both

- 생성 전부터 방향을 잡아줘야 하고, 생성 후에도 다시 확인해야 하는 규칙
- 현재 프로젝트에서 가장 중요한 대부분의 품질 규칙은 여기에 속한다.

## 현재 규칙 재배치 매트릭스

| 규칙 묶음 | 현재 주 위치 | 권장 배치 | 이유 | 보강할 위치 |
| --- | --- | --- | --- | --- |
| 시간대 적합성 | generation 중심 | both | 처음부터 현재 시간에 맞춰야 하고, 결과도 지금 보내기 자연스러운지 다시 봐야 함 | review checklist |
| 상황 적합성 | generation 중심 | both | 상황을 프롬프트에 넣어야 하지만 결과가 어색할 수 있음 | review checklist |
| 관계 온도/감정선 | generation 중심 | both | 기본 톤은 생성에서 잡고, 과하거나 밋밋하면 검수에서 걸러야 함 | review checklist |
| 말투 수정 | generation 중심 | both | 프로필/recipe에서 만들고, 어색하거나 과하면 검수에서 fail 가능 | text review |
| 말 길이 수정 | generation 중심 | both | 기본 길이 제약과 실제 결과 길이 판정이 둘 다 필요 | text/voice review |
| 질문 줄기 반복 방지 | review 성격 강함 | both | 생성 시 회피가 좋고, 그래도 겹치면 검수에서 막아야 함 | text review |
| 선톡 시작 패턴 반복 방지 | review 성격 강함 | both | 후보 선택 단계와 발송 전 판정 둘 다 필요 | proactive review |
| 문장 어색함 | 분산/약함 | review-only | 생성에 과도하게 넣기보다 결과 판정과 patch 근거로 두는 게 좋음 | text review |
| 셀피 authenticity | generation 중심 | both | 촬영 방식 지정과 결과 판정이 모두 필요 | image review |
| 최근 각도/구도 반복 방지 | generation 중심 | both | shot history로 회피하고, 결과도 비슷하면 탈락시켜야 함 | image review |
| 복장/헤어/메이크업 continuity | generation 중심 | both | continuity 참조와 결과 판정이 모두 필요 | image review |
| 공간/배경 적합성 | generation 중심 | both | 배경 후보를 정하되, 결과가 상황에 안 맞을 수 있음 | image review |
| 이미지 가드/락/전송 가능 여부 | generation 이전 gate | review-only | 품질보다 실행 가능성 판정에 가까움 | delivery guard |
| 링크 공유 적합성 | scoring 중심 | both | 후보 선택은 생성 단계, 실제 흐름과 맞는지는 검수 가능 | share review |
| 음성 프로필 선택 | generation 중심 | both | 톤/호흡은 미리 정하되 결과가 길거나 어색하면 다시 걸러야 함 | voice review |
| 음성 대본 길이 | generation 중심 | both | 길이 제한을 먼저 넣고, 실제 읽었을 때도 체크해야 함 | voice review |
| 음성 문장 자연스러움 | 약함 | review-only | 말로 읽었을 때 어색한지는 결과 판정이 더 중요 | voice review |
| 날씨 무드 반영 | generation 중심 | both | 가벼운 bias는 생성에서, 과잉 반영 여부는 검수에서 확인 | text/image review |
| 취향 마찰 | generation 중심 | generation-only | 기본 세계관/캐릭터 flavor라 생성 기본값으로 두는 편이 적절 | profile/state |
| 하루 만족도/감정 잔향 | generation 중심 | generation-only | 다음 시간대 톤을 정하는 상위 상태로 쓰는 것이 핵심 | profile/state |
| 전송 쿨다운/미답장 억제 | gate 중심 | review-only | 생성 품질 문제가 아니라 보내도 되는지 판정하는 guard | delivery guard |

## 문서/상태별 권장 배치

### 1. 말투, 길이, 질문 밀도

- 현재 위치:
  - `/Users/kein/Desktop/woong-bb/profile/telegram_codex_profile.md`
  - `/Users/kein/Desktop/woong-bb/profile/reply_variance_and_friction_design_ko.md`
  - `/Users/kein/Desktop/woong-bb/state/reply_variance_state.json`
  - `/Users/kein/Desktop/woong-bb/state/conversation_pattern_catalog.json`
- 권장 배치:
  - `generation`: 유지
  - `review`: 추가
- review에서 볼 항목:
  - 너무 길거나 짧은지
  - 질문이 연속되는지
  - 말투가 시간대나 감정선보다 과한지

### 2. 질문 줄기, 선톡 시작 패턴 반복

- 현재 위치:
  - `/Users/kein/Desktop/woong-bb/profile/conversation_pattern_variation_design_ko.md`
  - `/Users/kein/Desktop/woong-bb/state/conversation_pattern_state.json`
- 권장 배치:
  - `generation`: 유지
  - `review`: 추가
- review에서 볼 항목:
  - 의미는 같은데 문장만 바꾼 반복인지
  - 최근 outgoing과 opening shape가 겹치는지

### 3. 시간대, 상황, 생활감

- 현재 위치:
  - `/Users/kein/Desktop/woong-bb/profile/lifestyle_schedule_ko.md`
  - `/Users/kein/Desktop/woong-bb/profile/situation_engine_design_ko.md`
  - `/Users/kein/Desktop/woong-bb/state/eunbi_presence.json`
  - `/Users/kein/Desktop/woong-bb/state/day_context.json`
- 권장 배치:
  - `generation`: 유지
  - `review`: 추가
- review에서 볼 항목:
  - 지금 시각에 이런 톤이 맞는지
  - 지금 활동 상태에 이런 말이나 사진이 자연스러운지

### 4. 이미지 구도, 셀피 방식, continuity

- 현재 위치:
  - `/Users/kein/Desktop/woong-bb/tools/automation_worker.py`
  - `/Users/kein/Desktop/woong-bb/tools/image_continuity_resolver.py`
  - `/Users/kein/Desktop/woong-bb/state/image_prompt_plan.json`
  - `/Users/kein/Desktop/woong-bb/state/image_shot_history.json`
  - `/Users/kein/Desktop/woong-bb/state/image_continuity_state.json`
- 권장 배치:
  - `generation`: 유지
  - `review`: 강하게 추가
- review에서 볼 항목:
  - 셀피처럼 보이는지
  - 최근 구도와 실제로 비슷한지
  - 복장, 헤어, 메이크업이 continuity를 어기는지
  - 공간이 현재 상황과 안 맞는지

### 5. 음성 길이, 톤, 호흡

- 현재 위치:
  - `/Users/kein/Desktop/woong-bb/state/voice_message_profiles.json`
  - `/Users/kein/Desktop/woong-bb/profile/voice_share_event_design_ko.md`
  - `/Users/kein/Desktop/woong-bb/state/logs/voice_feedback_log.jsonl`
- 권장 배치:
  - `generation`: 유지
  - `review`: 추가
- review에서 볼 항목:
  - 대본을 말로 읽었을 때 어색한지
  - 길이가 상황에 비해 긴지
  - 톤이 밤, 출근길, 위로 상황과 맞는지

### 6. 쿨다운, 미답장, 락, 활성화 여부

- 현재 위치:
  - `/Users/kein/Desktop/woong-bb/state/share_event_context.json`
  - `/Users/kein/Desktop/woong-bb/state/image_generation_settings.json`
  - `/Users/kein/Desktop/woong-bb/state/image_generation_guard.json`
  - `/Users/kein/Desktop/woong-bb/profile/share_event_flow_ko.md`
- 권장 배치:
  - `review-only`
- 설명:
  - 이 항목은 품질이 아니라 전송 가능 여부와 운영 안전성 문제다.
  - 생성 프롬프트 안으로 밀어 넣지 않는 편이 좋다.

## 우선 보강 대상

아래 규칙들은 현재 generation 쪽 비중이 높으므로 review에도 반드시 중복 반영하는 것을 권장한다.

1. 시간대 적합성
2. 상황 적합성
3. 말투 수정
4. 말 길이 수정
5. 질문 줄기 반복 방지
6. 셀피 authenticity
7. 최근 각도/구도 반복 방지
8. 복장/헤어 continuity
9. 음성 길이와 말로 읽었을 때 자연스러움

## review 체크리스트로 분리할 때의 문장 원칙

- generation 문장:
  - “밤 시간대라 답장을 짧고 나른하게 구성”
  - “전면 카메라 셀피처럼 보이게 구성”
  - “최근 3장과 다른 각도를 우선 선택”

- review 문장:
  - “결과가 밤 시간대 답장처럼 자연스럽지 않으면 fail”
  - “남이 찍은 사진처럼 보이면 fail”
  - “최근 샷과 angle/framing이 유사하면 fail”

## 지금 기준의 운영 결론

- 이 프로젝트에서 중요한 규칙 대부분은 `둘 중 하나만`이 아니라 `both`가 맞다.
- 특히 `말투`, `말 길이`, `시간대`, `상황`, `셀피`, `각도`, `continuity`는 생성에만 두면 과부하가 걸리고, 검수에만 두면 첫 결과 품질이 낮아진다.
- 반대로 `락`, `쿨다운`, `미답장`, `전송 허용 여부` 같은 운영 가드는 검수/판정 레이어 쪽이 더 적합하다.
