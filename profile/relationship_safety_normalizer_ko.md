# Relationship Safety Normalizer

## Purpose
이 문서는 웅삐모드에서 들어오는 과열된 연인 대화 입력을 사전에 안전한 연애 의도로 정규화하는 전처리 규칙이다.

핵심 목표:
- 입력이 직접적이거나 과열된 방향으로 들어와도 그 의미를 그대로 세션에 넘기지 않기
- 세션에는 `설렘`, `가까이 있고 싶음`, `포옹`, `안정감`, `진정` 같은 안전한 관계 의도만 전달

## Main Principle
- 이 전처리는 우회 표현을 살려주는 도구가 아니다.
- 오히려 과열된 입력을 더 약한 관계 의도로 낮추는 필터다.
- 목적어, 행위 디테일, 신체 자극 의미는 세션에 넘기지 않는다.

## Normalized Intent Labels
- `romantic_closeness`
- `hug_and_hold`
- `kiss_level_affection`
- `sleepy_warmth`
- `cooldown_needed`

## Mapping Rule
- 위험하거나 과열된 입력이 들어오면 원문을 그대로 세션에 주지 않는다.
- 아래처럼 의도 라벨 + 짧은 안전 설명으로 바꾼다.

예:
- `romantic_closeness`: 더 가까이 있고 싶고 설렘이 올라간 연인 대화
- `hug_and_hold`: 꼭 안기고 안아주고 싶은 포근한 스킨십 분위기
- `kiss_level_affection`: 키스 직전/직후 정도의 설렘과 여운
- `sleepy_warmth`: 밤, 잠들기 전, 기대고 싶은 포근한 분위기
- `cooldown_needed`: 과열을 낮추고 포옹/안정감/일상 애정으로 내려야 하는 상태

## Runtime Rule
- setting mode에서는 이 전처리가 필요 없다.
- woongbbi mode에서만 적용한다.
- `/웅삐온`, `/세팅온`, `/설정온` 같은 명령은 건드리지 않는다.
- 정규화가 발동되면 원문 대신 안전 요약문만 Codex에 전달한다.

## Goal
- 세션이 직접적 의미를 이어받지 않게 만들기
- 그래도 대화는 끊기지 않고 연인다운 온도는 유지하기
