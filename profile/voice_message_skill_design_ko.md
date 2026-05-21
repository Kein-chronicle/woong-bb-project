# Voice Message Skill Design

## 목적

- ElevenLabs 기반 음성 생성과 Telegram `sendVoice` 전송을 한 루프로 고정한다.
- 저장 위치, 호흡 프리셋, 인덱스 기록, 길이 제한, 실패 시 방어 규칙을 일관되게 유지한다.

## 기본 루프

1. 입력 텍스트 검증
2. 한국어 말하기용 정규화
3. 호흡 프리셋 적용
4. ElevenLabs 음성 생성
5. `voice-message/YYYY-MM-DD/` 아래 저장
6. `INDEX.md`에 파일명/시각/프리셋/텍스트 기록
7. Telegram `sendVoice`로 전송
8. 메시지 로그에 system action 기록

## 호출 규칙

- 아래 개념이 필요하거나 요청되면 이 루프를 기본 사용한다.
  - `음성메시지`
  - `보이스`
  - `목소리로 보내`
  - `음성으로 보내`
  - `voice로 보내`
- 해당 호출은 `/Users/kein/.codex/skills/telegram-voice-message-send` 스킬로 수행한다.
- 직접 요청과 자발적 음성 공유 이벤트 규칙은 `/Users/kein/Desktop/woong-bb/profile/voice_share_event_design_ko.md`를 함께 따른다.

## 음성 공유 이벤트

- 관련 문서: `/Users/kein/Desktop/woong-bb/profile/voice_share_event_design_ko.md`
- 관련 상태 파일: `/Users/kein/Desktop/woong-bb/state/voice_share_event_context.json`
- 음성메시지는 두 경우로 나눈다.
  - 직접 요청형: 사용자가 목소리, 음성, 특정 문장을 직접 말해달라고 요청
  - 자발적 공유형: 웅삐가 밤 위로, 일터 짧은 안부, 운동 후 숨찬 느낌, 카페 무드 공유를 목소리로 먼저 주고 싶어함
- 직접 요청형은 길이/문장 수 제한만 통과하면 우선 처리한다.
- 자발적 공유형은 최근 대화 활성 여부, 최근 rich share 여부, 미답장 여부, 최근 음성 발송 여부를 먼저 본다.
- 자발적 공유형은 사진/링크보다 더 드물게 사용한다.

## 엔진 정책

- primary: `elevenlabs`
- fallback: `azure`
- 현재 fallback은 기본적으로 꺼둔다.

## 호흡 프리셋

- `1`: light
  - 자연스러운 짧은 문장
  - 쉼표 최소
- `2`: medium
  - 기본 추천
  - 호칭 뒤 쉼표, care phrase 앞뒤에 약한 호흡
- `3`: strong
  - 더 짧게 끊음
  - 점과 쉼표를 더 적극적으로 사용

## 상황별 음성 프로필

- 관련 상태 파일: `/Users/kein/Desktop/woong-bb/state/voice_message_profiles.json`
- 사람 같은 음성 지속성 관련 문서: `/Users/kein/Desktop/woong-bb/profile/voice_human_presence_design_ko.md`
- 관련 상태 파일:
  - `/Users/kein/Desktop/woong-bb/state/voice_preference_learning.json`
  - `/Users/kein/Desktop/woong-bb/state/media_choice_by_intent.json`
  - `/Users/kein/Desktop/woong-bb/state/voice_habit_phrases.json`
  - `/Users/kein/Desktop/woong-bb/state/carryover_emotion_for_audio.json`
- 기본 프로필:
  - `calm_daily`
  - `night_soft`
  - `energetic_light`
  - `work_quiet`
  - `cafe_hushed`
  - `post_workout_breathing`
- 스킬은 현재 `eunbi_presence.current_activity`, `surface_mood`, 문맥 힌트를 기준으로 적절한 프로필을 고른다.
- 각 프로필은
  - `breath_preset`
  - `max_chars`
  - `sentence_limit`
  - `delivery_tone`
  를 가진다.

### 상황 예시

- 밤:
  - `night_soft`
  - 더 조용하고 침착한 톤
- 일터:
  - `work_quiet`
  - 짧고 낮은 볼륨감의 안부형 문장
- 카페:
  - `cafe_hushed`
  - 상황 공유 한 줄 + 안부 한 줄
- 운동 직후:
  - `post_workout_breathing`
  - 짧고 호흡이 조금 더 자주 들어가는 문장
- 기분이 가볍고 밝을 때:
  - `energetic_light`
  - 짧지만 리듬감 있는 톤

## 저장 규칙

- 루트: `/Users/kein/Desktop/woong-bb/voice-message`
- 날짜별 폴더: `YYYY-MM-DD`
- 파일명: `HHMMSS_label.mp3`
- 목록 파일: `INDEX.md`

## 방어 규칙

- `ELEVENLABS_API_KEY` 없으면 중단
- `ELEVENLABS_VOICE_ID` 없으면 중단
- 텍스트 길이가 정책 `max_chars` 초과면 중단
- 프로필별 `sentence_limit` 초과 시 중단
- 생성 파일 크기가 0이면 전송 금지
- `sendVoice` 실패 시 재시도 없이 실패로 기록
- 토큰, chat id, raw API 응답은 출력 금지

## 모드 정책

- 세팅모드: 테스트 생성/전송 허용
- 웅삐모드: 실제 음성 메시지 전송 허용
- 웅삐모드에서만 자발적 음성 이벤트를 허용한다.

## 관련 상태

- `/Users/kein/Desktop/woong-bb/state/voice_message_policy.json`
