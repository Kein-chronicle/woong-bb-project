# Reinforcement Learning Design

## Purpose
이 문서는 오빠와 대화할수록 어떤 주제, 어떤 말투, 어떤 행동이 좋은 반응을 얻는지 누적 학습하는 강화 시스템 설계다.

핵심 목표:
- 주제별 선호도 누적
- 행동별 보상/패널티 누적
- 말투/전달 방식 선호 누적
- 나중 대화와 선톡 후보 선택에 반영

## Main Files
- Design: `/Users/kein/Desktop/woong-bb/profile/reinforcement_learning_design_ko.md`
- State: `/Users/kein/Desktop/woong-bb/state/user_preference_reinforcement.json`
- Engine: `/Users/kein/Desktop/woong-bb/tools/reinforcement_engine.py`

## Data Model

상태 파일은 이제 단순 점수표가 아니라 아래를 함께 가진다.
- `processed_offsets`: 메시지 로그 파일별 마지막 처리 line
- `message_stats`: 긍정/부정/중립 반응 카운트
- `topic_scores`, `action_scores`, `style_scores`: 점수, hit 수, 최근 근거, 예시
- `bias_summary`: 지금 시점에서 우선할 것과 피할 것 요약
- `evidence_log`: 최근 강화/패널티 근거

### Topic Scores
- `appearance_compliment`
- `photo_request`
- `daily_checkin`
- `comfort_support`
- `affection_romance`
- `food_cafe`
- `exercise_health`
- `workday_empathy`
- `playful_teasing`
- `sleep_goodnight`
- `media_watch_talk`
- `setting_feedback`

### Action Scores
- `send_photo`
- `send_text_after_photo`
- `caption_inside_photo_message`
- `separate_text_message`
- `warm_comfort_reply`
- `cute_affection_reply`
- `daily_context_reply`
- `proactive_checkin`
- `appearance_description`
- `preference_learning`

### Style Scores
- `half_banmal_affectionate`
- `gentle_comfort`
- `playful_light`
- `concise_setting_mode`
- `image_without_caption`
- `text_separate_from_image`
- `initiative_with_context`

## Update Timing
- 기본 트리거는 `사용자 incoming 메시지`가 로그에 추가된 뒤다.
- reinforcement engine은 새 메시지를 읽고 아직 처리하지 않은 user 메시지만 분석한다.
- 한 번 처리한 메시지는 다시 점수 반영하지 않는다.

## Reward / Penalty Logic

### Positive Reward Examples
- `좋아`, `행복`, `기운 난다`, `고마워`, `따뜻하다`, `귀엽다`, `예쁘다`, `보고 싶다`
- 사진/외형 칭찬이면 `appearance_compliment`, `send_photo`, `image_without_caption` 등에 보너스
- 위로/다정함 반응이면 `comfort_support`, `warm_comfort_reply`, `gentle_comfort`
- 일상/생활감 반응이면 `daily_checkin`, `daily_context_reply`

### Negative / Preference Correction Examples
- `별로`, `부담`, `이상`, `겹친다`, `중복`, `캡션 없이`, `따로 보내`
- 전달 방식 수정이면 `caption_inside_photo_message` 패널티
- 원하는 형식이면 `image_without_caption`, `text_separate_from_image` 보너스
- 사용자가 직접 `이렇게 해줘`, `이렇게 유지`, `강화 시스템` 같은 방향을 주면 explicit correction으로 더 크게 반영

## Contextual Link
- 가능하면 직전 assistant/이미지 이벤트와 연결해서 어떤 행동에 대한 반응인지 같이 기록한다.
- 예:
  - 직전 이벤트가 `image`이고 다음 user 메시지가 칭찬이면 `send_photo` 보상
  - 직전 이벤트가 `text` 위로였고 user가 `따뜻하다`고 하면 `warm_comfort_reply` 보상
  - 직전 이미지가 caption 없이 갔고 반응이 좋으면 `image_without_caption` 보상
  - 직전 이미지 뒤에 caption 중복 수정이 오면 `caption_inside_photo_message` 패널티

## Runtime Timing
- `state/timers.json`의 `reinforcement_learning_tick`이 300초마다 엔진을 호출한다.
- 엔진은 이미 처리한 line을 `processed_offsets`로 건너뛴다.
- 따라서 누적은 계속 쌓이되 같은 메시지를 중복 학습하지 않는다.

## Usage
- 웅삐모드 대화와 선톡 후보 선택 시 높은 점수의 topic/action/style을 우선한다.
- 세팅모드에서는 이 상태를 보고 “뭘 좋아하는지”를 관제할 수 있다.
- `bias_summary.prefer_*`는 우선 강화할 축이다.
- `bias_summary.avoid_*`는 반복하면 안 되는 방식이다.
