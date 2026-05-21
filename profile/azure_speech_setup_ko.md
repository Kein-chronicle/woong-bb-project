# Azure Speech Setup

## 목적

- `woong-bb` 음성 기능을 붙일 때 어떤 값을 어디서 받아야 하는지 혼선 없이 고정한다.

## 준비 파일

- 예시 파일: `/Users/kein/Desktop/woong-bb/azure-speech.env.example`
- 실제 파일 권장 위치:
  - `/Users/kein/Desktop/woong-bb/azure-speech.env`
  - 또는 `/Users/kein/Desktop/woong-bb/session/azure-speech.env`

실제 비밀값은 저장소에 커밋하지 않는다.

## 마스터에게 받을 값

필수:
- `AZURE_SPEECH_KEY`
- `AZURE_SPEECH_REGION`

선택:
- `AZURE_SPEECH_ENDPOINT`

기본값 제공 가능:
- `AZURE_SPEECH_LOCALE=ko-KR`
- `AZURE_SPEECH_VOICE=ko-KR-SunHiNeural`
- `AZURE_SPEECH_OUTPUT_FORMAT=audio-24khz-48kbitrate-mono-mp3`
- `AZURE_SPEECH_RATE=-3%`
- `AZURE_SPEECH_PITCH=0%`
- `AZURE_SPEECH_VOLUME=medium`
- `AZURE_SPEECH_OUTPUT_DIR=/Users/kein/Desktop/woong-bb/voice-message`
- `WOONGBB_VOICE_SEND_ENABLED=false`
- `WOONGBB_VOICE_MAX_CHARS=220`

## Portal에서 확인할 위치

- Azure Portal
- 대상 Speech 리소스 진입
- `Keys and Endpoint`
- 여기서 아래를 확인
  - Key 1 또는 Key 2
  - Region
  - Endpoint

## 마스터가 보내줄 형식

이 형식 그대로 주면 된다.

```env
AZURE_SPEECH_KEY=...
AZURE_SPEECH_REGION=...
AZURE_SPEECH_ENDPOINT=...
```

`AZURE_SPEECH_ENDPOINT`는 없으면 생략 가능하다.

## 다음 단계

값을 받으면 아래 순서로 진행한다.

1. 실제 env 파일 생성
2. 한국어 읽기 정규화 규칙 파일 생성
3. SSML 템플릿 생성
4. Azure 호출 스크립트 연결
5. 텔레그램 음성 전송 경로 연결

## 저장 구조

- 음성 루트: `/Users/kein/Desktop/woong-bb/voice-message`
- 날짜별 폴더: `YYYY-MM-DD`
- 각 날짜 폴더마다 `INDEX.md`를 두고
  - 파일명
  - 생성 시각
  - 사용한 텍스트
  를 같이 남긴다.
