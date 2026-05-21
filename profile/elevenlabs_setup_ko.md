# ElevenLabs Setup

## 목적

- 웅삐 고유 음성 클론을 붙이기 전에 어떤 값을 받아야 하는지 고정한다.

## 준비 파일

- 예시 파일: `/Users/kein/Desktop/woong-bb/elevenlabs.env.example`
- 실제 파일 권장 위치:
  - `/Users/kein/Desktop/woong-bb/elevenlabs.env`
  - 또는 `/Users/kein/Desktop/woong-bb/session/elevenlabs.env`

실제 비밀값은 저장소에 커밋하지 않는다.

## 마스터에게 받을 값

초기 필수:
- `ELEVENLABS_API_KEY`

클론 생성 후 필수:
- `ELEVENLABS_VOICE_ID`

기본값 제공 가능:
- `ELEVENLABS_MODEL_ID=eleven_multilingual_v2`
- `ELEVENLABS_OUTPUT_FORMAT=mp3_44100_128`
- `ELEVENLABS_STABILITY=0.42`
- `ELEVENLABS_SIMILARITY_BOOST=0.82`
- `ELEVENLABS_STYLE=0.18`
- `ELEVENLABS_USE_SPEAKER_BOOST=true`
- `ELEVENLABS_OUTPUT_DIR=/Users/kein/Desktop/woong-bb/voice-message`
- `WOONGBB_VOICE_SEND_ENABLED=false`
- `WOONGBB_VOICE_MAX_CHARS=220`

## 마스터가 보내줄 형식

가입 직후:

```env
ELEVENLABS_API_KEY=...
```

클론 생성 후:

```env
ELEVENLABS_VOICE_ID=...
```

## 권장 저장 구조

- 원본 음성 수집 루트: `/Users/kein/Desktop/woong-bb/voice-clone-sources/eunbi`
- 업로드 전 정리 폴더: `/Users/kein/Desktop/woong-bb/voice-clone-sources/eunbi/cleaned`
- 메모/대본 목록: `/Users/kein/Desktop/woong-bb/voice-clone-sources/eunbi/INDEX.md`

## 다음 단계

1. API 키 수령
2. 음성 수집 폴더 구성
3. 업로드용 샘플 정리 규칙 작성
4. Voice clone 생성 후 `VOICE_ID` 반영
5. ElevenLabs 호출 스크립트 연결
