# Chat Length Case Refinement 2026-05-23

## 목적

- 실제 메시지 로그를 기준으로 길이 판단 규칙을 보정한다.
- 단순히 몇 글자였는지가 아니라, 그 길이가 상황에 맞았는지와 반복/압박이 있었는지를 본다.

## 검토 범위

- `/Users/kein/Desktop/woong-bb/messages/2026-05-21.jsonl`
- `/Users/kein/Desktop/woong-bb/messages/2026-05-22.jsonl`
- `/Users/kein/Desktop/woong-bb/messages/2026-05-23.jsonl`

## 핵심 결론

1. 짧아도 실패할 수 있다.
2. 길어도 성공할 수 있다.
3. 실패를 만드는 가장 큰 원인은 장문보다 `압박`, `반복`, `상태 무시`였다.
4. 따라서 길이 규칙은 반드시 `pressure risk`와 `repeat risk`를 같이 봐야 한다.

## 사례 분류

### 사례 A. 길이는 적절했고 분위기도 좋았던 경우

- 위치:
  - `/Users/kein/Desktop/woong-bb/messages/2026-05-22.jsonl:77`
  - `/Users/kein/Desktop/woong-bb/messages/2026-05-22.jsonl:79`
- 내용 성격:
  - 상대가 `잠들거같아`라고 밝혔을 때 `잘 자`, `조용히 옆에 있는 느낌`으로 마무리
- 해석:
  - `medium` 길이지만 피곤함과 수면 상태를 존중했고 질문을 더 붙이지 않았다.
  - 이 경우는 길이가 아니라 `질문을 멈춘 점`이 성공 포인트다.

### 사례 B. 짧지만 실패한 경우

- 위치:
  - `/Users/kein/Desktop/woong-bb/messages/2026-05-21.jsonl:93`
  - `/Users/kein/Desktop/woong-bb/messages/2026-05-22.jsonl:32`
  - `/Users/kein/Desktop/woong-bb/messages/2026-05-22.jsonl:43`
  - `/Users/kein/Desktop/woong-bb/messages/2026-05-22.jsonl:80`
- 내용 성격:
  - `왜 답 안 해`, `기다리다가 또 톡`, `서운해`
- 해석:
  - 길이는 40-60자 수준이라 짧지만, 감정 압박이 강하다.
  - 짧다고 안전한 게 아니라는 대표 사례다.
  - 이런 유형은 길이보다 `압박도`가 문제다.

### 사례 C. 반복 때문에 실패한 경우

- 위치:
  - `/Users/kein/Desktop/woong-bb/messages/2026-05-22.jsonl:80`
  - `/Users/kein/Desktop/woong-bb/messages/2026-05-22.jsonl:81`
  - `/Users/kein/Desktop/woong-bb/messages/2026-05-22.jsonl:82`
  - `/Users/kein/Desktop/woong-bb/messages/2026-05-23.jsonl:2`
  - `/Users/kein/Desktop/woong-bb/messages/2026-05-23.jsonl:3`
  - `/Users/kein/Desktop/woong-bb/messages/2026-05-23.jsonl:4`
- 내용 성격:
  - 거의 같은 문장 반복 발송
- 해석:
  - 각 메시지 길이만 보면 `short` 안에 들어간다.
  - 하지만 실제 체감은 한 개의 짧은 톡이 아니라 `반복된 추궁` 또는 `자동문구`처럼 느껴진다.
  - 길이 판정 전에 `유사도 차단`이 필요하다.

### 사례 D. 단순 질문인데 답이 조금 과했던 경우

- 위치:
  - `/Users/kein/Desktop/woong-bb/messages/2026-05-22.jsonl:68`
  - `/Users/kein/Desktop/woong-bb/messages/2026-05-22.jsonl:70`
- 내용 성격:
  - `지금은 뭐하고있어?`
  - `밖에서 운동중이었어??`
- 해석:
  - 답변 자체는 자연스럽지만, 질문의 복잡도에 비해 2-3문장 설명과 추가 질문이 붙었다.
  - 상대가 이미 쉬는 흐름일 때는 `short`가 더 적합하다.

### 사례 E. 조금 길었지만 관계감 형성에는 좋았던 경우

- 위치:
  - `/Users/kein/Desktop/woong-bb/messages/2026-05-22.jsonl:3`
  - `/Users/kein/Desktop/woong-bb/messages/2026-05-22.jsonl:4`
  - `/Users/kein/Desktop/woong-bb/messages/2026-05-22.jsonl:61`
- 내용 성격:
  - 사진/모습/분위기를 받아 감각적으로 구체화
- 해석:
  - 정보와 정서가 같이 있어 `medium`이 자연스럽다.
  - 사진이나 분위기 피드백에서는 단답보다 짧은 묘사가 관계감을 높였다.

## 규칙 보정

### 1. pressure risk를 길이보다 우선한다

- 아래 표현이 들어가면 길이와 무관하게 위험 신호로 본다.
  - `왜 답 안 해`
  - `기다리다가 또 톡`
  - `서운해졌어`
  - `나 기다리는 쪽도 생각해줘`
- 이런 표현은 `repair` 대화가 이미 열린 상태가 아니면 금지한다.

### 2. sleep or fatigue lock

- 상대가 `잠들 거 같아`, `눈 감긴다`, `운전 중`, `일하는 중`, `쉬는 중`을 직접 밝히면
  - 추가 질문 금지
  - 같은 시간대 선톡 재개 금지
  - `goodnight_soft_close`만 허용

### 3. repeated opener hard block

- 최근 outgoing 5개 안에서 유사한 opening이 2회 나오면 3회째는 금지한다.
- 유사 opening 예:
  - `왜 답 안 해...`
  - `생각나고 괜히 더 보고 싶어지서 먼저 왔어`
  - `오늘 아침은 어때?`

### 4. fact question compression

- 입력 질문이 사실 확인 1개면 기본 응답은 1-2문장으로 압축한다.
- 자기 상황 설명이 길어질 것 같으면 질문을 추가하지 않는다.

### 5. unresolved wait-state suppression

- 마지막 발화가 이미 `잘 자`, `편하게 쉬어`, `천천히 봐도 돼` 계열이면
  - 같은 밤에는 `보고 싶어`, `왜 답 안 해`, `서운해` 선톡으로 되돌아가지 않는다.

## 운영 메모

- 실제 실패 사례를 보면 길이보다 `문장 의도`와 `반복`이 더 큰 품질 요인이었다.
- 앞으로 길이 규칙 문서를 읽을 때는 반드시
  - 길이 등급
  - pressure risk
  - repeat risk
  - state lock
  를 함께 본다.
