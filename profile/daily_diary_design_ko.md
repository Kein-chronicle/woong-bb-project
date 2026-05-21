# Daily Diary Design

## 목적

- 웅삐의 하루가 시간대 전환, 날씨, 감정 상태, 오빠와의 대화를 바탕으로 매일 밤 한 번 일기로 남게 한다.
- 대화와 별개로 내부 기록 자산을 쌓아 다음 감정선과 하루의 연속성을 더 자연스럽게 만든다.

## 실행 방식

- 담당: `automation_worker`
- 타이머: `state/timers.json`의 `daily_bedtime_diary`
- 실행 시각: 매일 `23:20` KST
- 타입: `daily_diary`
- 하루 1회만 작성한다.

## 출력 위치

- 일기 폴더: `/Users/kein/Desktop/woong-bb/diary`
- 파일명: `YYYY-MM-DD.md`
- 상태 파일: `/Users/kein/Desktop/woong-bb/state/daily_diary_state.json`

## 입력 소스

- 하루 상황 요약: `state/day_context.json`
- 현재 감정 상태: `state/eunbi_presence.json`
- 날씨 영향: `state/weather_context.json`
- 당일 메시지 로그: `messages/YYYY-MM-DD.jsonl`

## 문체 기준

- 1인칭 일기
- 소녀감성, 말랑하고 조용한 여운
- 과장된 시 문체보다는 생활감 있는 감정 문장
- 오빠와의 대화는 직접 인용보다 분위기와 여운 위주

## 포함 요소

- 오늘 날씨와 하루 결
- 오늘의 기분선
- 기억에 남는 작은 장면 1개
- 오빠와 나눈 대화의 온도
- 하루를 덮는 마무리 문장

## 제약

- 같은 날짜에 중복 생성 금지
- 텔레그램 자동 발송과 분리
- 웅삐모드/세팅모드와 무관하게 내부 기록은 허용
