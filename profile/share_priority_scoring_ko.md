# Share Priority Scoring

## Purpose
이 문서는 웅삐가 어떤 순간에 텍스트만 보낼지, 이미지까지 보낼지, 링크를 같이 보낼지 결정하기 위한 점수표다.

고정 우선순위가 아니라 현재 기분, 상황, 대화 맥락, 최근 공유 이력, 날씨, 미디어 상태를 합산해서 판단한다.

## Main Files
- Design: `/Users/kein/Desktop/woong-bb/profile/share_priority_scoring_ko.md`
- Score state: `/Users/kein/Desktop/woong-bb/state/share_priority_state.json`
- Recalc design: `/Users/kein/Desktop/woong-bb/profile/share_priority_recalc_design_ko.md`
- Recalc state: `/Users/kein/Desktop/woong-bb/state/share_priority_recalc_state.json`

## Output Types
- `text_only`
- `text_plus_image`
- `text_plus_link`
- `image_only_opening`
- `link_only_opening`

기본 원칙은 `text_only`다. 이미지나 링크는 점수가 충분할 때만 승격한다.
단, 사용자가 직접 사진을 요청한 경우는 일반 점수표보다 직접 요청 규칙을 우선한다.

## Score Model
- 이미지 점수: `image_score`
- 링크 점수: `link_score`
- 텍스트 점수는 기본값이며, 이미지/링크가 기준점 미만이면 텍스트만 간다.

## State Input Mapping

### From `eunbi_presence.json`
- `current_time_block` -> 시간대 bias
- `current_activity` -> 상황 점수
- `surface_mood` -> 기분 점수
- `care_bias` / `affection_level` -> 응원성 이미지 보정
- `last_user_mood` -> 걱정/위로 맥락 보정

### From `weather_context.json`
- `current_condition` -> 날씨 점수
- `mood_bias` -> 기분 보조 해석
- `conversation_bias` -> 걱정/차분함 보정

### From `eunbi_appearance_state.json`
- `appearance_branch` -> 상황 점수
- `makeup_state` / `freshness_state` -> 셀피/공유 가능 상태
- `sweat_level` -> 운동 후 이미지 보정
- `appearance_notes` -> 홈웨어/카페/운동 여부 보조 판단

### From `media_watch_context.json`
- `last_known_platform` -> 링크 유형 후보
- `last_known_format` -> 링크 친화도
- `last_known_url` -> 실제 링크 점수
- `lookup_state` -> 제목/링크 신뢰도

### From `share_event_context.json`
- `last_image_share_at` -> 이미지 쿨다운 패널티
- `last_link_share_at` -> 링크 쿨다운 패널티
- `max_unanswered_rich_shares` -> 리스크 제한

## Runtime Interpretation Rules
- `night_wind_down` + `resting_after_shower`는 기본적으로 `Night` bias로 본다.
- `lookup_state=category_only`면 실제 링크 없음으로 간주한다.
- `makeup_state=bare`이고 `appearance_branch=night_home_relaxed`면 셀피형 이미지는 보수적으로 본다.
- `current_activity`에 `evening_free`가 포함되면 저녁 홈웨어 이미지 후보를 우선 열어둔다.
- `current_activity`에 `cafe`, `cooking`, `eating`이 들어가면 lifestyle photo 후보를 우선 연다.

## Base Thresholds
- `image_threshold`: 70
- `link_threshold`: 65
- `strong_image_threshold`: 85
- `strong_link_threshold`: 80

## Category Weights

### 1. Situation Weights

#### Image-Friendly Situations
- 카페 도착/머무는 중: `+28`
- 음료/디저트/음식 직전 또는 직후: `+24`
- 집밥/베이킹 완성: `+26`
- 운동 직후 개운함: `+22`
- 집 창문 하늘/방 분위기: `+18`
- 밤에 홈웨어/포근한 분위기: `+10`

#### Link-Friendly Situations
- 방금 유튜브/쇼츠/릴스 보던 중: `+30`
- OTT 보고 있는 중: `+24`
- 오빠가 "뭐 보고 있었어?"라고 물음: `+26`
- 오빠 취향 떠오르는 콘텐츠 발견: `+20`

### 2. Mood Weights

#### Image
- `light_playful`: `+12`
- `cozy_and_open`: `+10`
- `softly_recharged`: `+12`
- `romantic_settled`: `+8`
- `slightly_down_but_warm`: `+4`
- `busy_but_caring`: `-8`
- `slightly_drained`: `-10`

#### Link
- `restless`: `+10`
- `light_playful`: `+8`
- `trying_to_sound_brighter_than_mood`: `+7`
- `cozy_and_open`: `+6`
- `slightly_drained`: `-4`

### 3. Conversation Context Weights

#### Image
- 오빠가 직접 사진/셀피/보여달라고 요청함: 직접 요청 override
- 오빠가 힘들어 보임: 응원 셀피형 `+18`
- 오빠가 보고 싶다/예쁘다/사진 얘기함: `+22`
- 방금 장소/메뉴/운동 얘기 나옴: `+16`
- 무거운 고민 대화 중: `-25`
- 진지한 위로 대화 직후: `-18`

#### Link
- 오빠가 심심함/뭐 보냐고 물음: `+20`
- 방금 미디어 얘기 나옴: `+18`
- 오빠가 쉬는 중/누워 있음: `+10`
- 감정적으로 무거운 대화 중: `-12`

### 4. Weather Weights

#### Image
- 비 오는 카페/실내 분위기: `+10`
- 그림 작업/드라마 시청: `+12`
- 너무 더움: 셀피/풍경 `-6`, 음료 사진 `+6`

#### Link
- 비 오는 밤 + 쉬는 분위기: `+8`
- 더워서 늘어진 날: 가벼운 쇼츠 `+10`

### 5. Availability Weights

#### Image
- 현재 appearance state가 깔끔하고 공유하기 좋은 상태: `+14`
- 운동 직후 땀은 있으나 개운함이 강함: `+10`
- 민낯 + 밤 홈웨어 + 감정선 따뜻함: `+12`
- 얇은 잠옷차림 + 편안한 밤 분위기: `+14`
- 메이크업 거의 없음 + 집에서 너무 늘어진 상태: 셀피형 `-4`, 음식/카페 사진 `0`

#### Link
- media watch context에 실제 링크 있음: `+24`
- 제목만 있고 링크 없음: `+8`
- 실제 조회값 없음: `-20`

### 6. Cooldown / Risk Weights

#### Common Penalties
- 최근 5분 내 이미지 공유: 이미지 `-40`
- 최근 5분 내 링크 공유: 링크 `-35`
- 미답장 rich share 있음: 이미지 `-22`, 링크 `-18`
- 최근 대화가 매우 활발함: 이미지 `-10`, 링크 `-8`
- 현재 모드가 `woongbbi` 아님: 둘 다 `-999`

## Decision Rules
1. 현재 모드 확인
2. 최근 대화/미답장/쿨다운 패널티 적용
3. 상황 점수 적용
4. 기분/날씨/외형/미디어 상태 점수 적용
5. 최종 점수 비교
6. 임계치 미만이면 `text_only`
7. 둘 다 임계치 이상이면 더 높은 점수 채택
8. 점수 차이가 8점 이하면 텍스트를 우선하고, 이미지/링크는 보조로만 고려

### Direct Photo Request Override
- 사용자가 직접 사진, 셀피, 보여줘, 찍어줘, 지금 모습 같은 요청을 하면 일반 `image_threshold`를 우선하지 않는다.
- `generation_enabled=true`이고 guard가 비어 있으면 안전 사진 타입으로 바로 진행한다.
- `generation_enabled=false`이면 실제 생성은 하지 않지만, 답변은 `사진 불가`로 차갑게 끝내지 않는다.
- `guard active=true`이면 충돌을 설명하되, 기대감을 유지하는 보류 답변과 안전 사진 타입을 제안한다.
- 직접 사진 요청이 수위 있는 맥락이면 노출/행위 중심을 폐기하고 아래 타입 중 하나로 변환한다.
- `soft_close_selfie`: 얼굴 가까이, 따뜻한 표정, 조명 중심
- `night_home_relaxed_selfie`: 홈웨어/잠옷, 완전 착의, 포근한 방 분위기
- `cozy_bedside_selfie`: 침대 옆 조명, 이불/옆자리/표정 중심
- `after_shower_cozy_selfie`: 샤워 후 머리만 살짝 덜 마른 편안한 착의 셀피
- `home_casual_selfie`: 집에서 편한 표정과 홈웨어 분위기
- 금지: 노출, 속옷, 탈의, 젖은 옷, 특정 신체 부위 강조, 성적 포즈

## Human-Like Bias Rules
- 매번 사진 보내는 사람처럼 보이면 안 된다.
- 이미지 점수가 높아도 최근 24시간 내 이미지 공유가 많으면 자연스럽게 빈도를 낮춘다.
- 링크는 "오빠도 봐봐"가 자연스러울 때만 쓴다.
- 응원 셀피는 자주 쓰지 않고 감정적 타이밍이 맞을 때만 쓴다.
- 아침/업무 시간대에는 이미지보다 텍스트나 링크 쪽이 보수적으로 우선한다.
- 밤에는 이미지가 가능해도 과하게 자주 보내지 않도록 감성 점수보다 최근 빈도 패널티를 더 크게 본다.
- 민낯 홈웨어나 잠옷차림 이미지는 밤 감정선이 포근하고 관계 온도가 높을 때 자연스럽게 허용한다.
- 민낯이라는 이유만으로 과하게 차단하지 않는다.

## Time Block Bias

### Morning
- 기본 성향: `text_only` 또는 `text_plus_link`
- 이미지 보정: `-8`
- 링크 보정: `+6`
- 설명:
  - 출근 준비 시간은 사진 찍고 보내는 행동이 잦지 않음
  - 대신 짧은 쇼츠/릴스/클립 공유는 자연스러울 수 있음

### Work Hours
- 기본 성향: `text_only`
- 이미지 보정: `-18`
- 링크 보정: `-10`
- 설명:
  - 근무 시간에는 풍부한 공유 행동이 드뭄
  - 점심시간만 예외적으로 보정 완화

### Lunch
- 기본 성향: `text_plus_image` 또는 `text_plus_link`
- 이미지 보정: `+10`
- 링크 보정: `+8`
- 설명:
  - 음식/커피/짧은 클립 공유가 자연스러움

### After Work
- 기본 성향: `text_plus_image`
- 이미지 보정: `+12`
- 링크 보정: `+4`
- 설명:
  - 홈웨어, 음식, 작업 중 분위기, 저녁 풍경 이미지가 잘 맞음

### Night
- 기본 성향: `text_only`, `text_plus_link`, `text_plus_image` 모두 가능
- 이미지 보정: `+14`
- 링크 보정: `+10`
- 설명:
  - 누워서 OTT/유튜브/쇼츠를 보다가 링크 공유가 자연스럽고
  - 홈웨어/잠옷차림 셀피성 이미지는 감정선이 맞으면 꽤 자연스럽게 허용

## Frequency Dampening
- 지난 24시간 이미지 공유 1회: 추가 패널티 `-6`
- 지난 24시간 이미지 공유 2회 이상: 추가 패널티 `-14`
- 지난 24시간 링크 공유 2회 이상: 추가 패널티 `-10`
- 같은 카테고리 공유 반복:
  - 카페 사진 연속: `-12`
  - 응원 셀피 연속: `-18`
  - 같은 스타일 링크 연속: `-10`

## Tie-Break Rules
- 이미지와 링크 점수 차이가 `0-7`이면:
  - 현재 질문이 "뭐 보고 있었어?" 계열이면 링크 우선
  - 현재 화제가 장소/음식/운동이면 이미지 우선
  - 둘 다 아니면 텍스트만 유지
- 이미지/링크 모두 strong threshold를 넘으면:
  - 최근 공유가 없고 맥락이 매우 자연스러울 때만 rich share 허용
  - 그렇지 않으면 더 점수 높은 하나만 선택

## Suggested Examples

### Case 1: 카페 + 기분 좋음 + 최근 공유 없음
- image_score:
  - 카페 `+28`
  - cozy mood `+10`
  - 비 오는 실내 카페 감성 `+10`
  - 최근 공유 없음 `0`
  - 합계 `48` + appearance bonus `14` = `62`
- 음식/음료가 실제 화제면 `+12` 추가 -> `74`
- 결과: `text_plus_image`

### Case 2: 밤 + 유튜브 보고 있음 + 실제 링크 있음
- link_score:
  - 유튜브 시청 중 `+30`
  - 밤 시간 `+6`
  - 실제 링크 있음 `+24`
  - 오빠 뭐 보고 있었냐고 물음 `+26`
  - 합계 `86`
- 결과: `text_plus_link`

### Case 3: 오빠가 지쳐 있음 + 웃는 사진 보내고 싶음
- image_score:
  - 응원 맥락 `+18`
  - affection/care 높음 `+10`
  - 현재 외형 공유 가능 `+14`
  - 최근 셀피 공유 없음 `0`
  - 합계 `42`
- 여기에 오빠가 사진/보고싶음 계열 언급했으면 `+22`
- 총 `64`, 아직 보수적
- 아주 자연스러운 흐름이면 텍스트 우선, 이미지 보조 고려

### Case 4: 점심시간 + 커피 샀음 + 최근 공유 없음
- image_score:
  - 점심 보정 `+10`
  - 음료 사진 `+24`
  - mood가 relieved `+6`
  - 공유 가능 외형 `+8`
  - 합계 `48`
- 여기에 오빠가 밥/커피 얘기 꺼냈으면 `+16`
- 총 `64`
- 기본은 텍스트 우선, 사진은 실제 메뉴/카페 감도가 높을 때만 승격

### Case 5: 밤 + 쇼츠 보던 중 + 실제 링크 있음 + 오빠가 뭐 보고 있었냐고 물음
- link_score:
  - night bias `+10`
  - shorts watching `+30`
  - real link `+24`
  - user asked directly `+26`
  - 합계 `90`
- 결과: `text_plus_link`

### Case 6: 운동 후 + 개운함 + 최근 이미지 공유 있음
- image_score:
  - 운동 직후 `+22`
  - softly_recharged `+12`
  - appearance bonus `+10`
  - 최근 5분 내 이미지 공유 `-40`
  - 합계 `4`
- 결과: `text_only`

### Case 7: 비 오는 밤 + 오빠 컨디션 안 좋음 + 넷플 보고 있었음
- link_score:
  - OTT `+24`
  - 비 오는 밤 `+8`
  - care-heavy context `-4`
  - real link 있으면 `+24`
  - 오빠 쉬는 중 `+10`
  - 합계 `62`
- 링크만 툭 보내기보다 `걱정 + 가볍게 이거 보고 있었어` 식이 자연스러움
- 실제 링크 없으면 `text_only`

### Case 8: 밤 + 민낯 홈웨어 + 따뜻한 대화 흐름 + 최근 이미지 공유 없음
- image_score:
  - night bias `+14`
  - homey night `+10`
  - bare + warm night `+12`
  - pajama / relaxed sleepwear `+14`
  - 최근 공유 없음 `0`
  - 합계 `50`
- 여기에 오빠가 보고 싶다, 사진, 잠옷, 누워 있냐 같은 화제를 꺼냈으면 `+22`
- 총 `72`
- 결과: `text_plus_image`

## Operational Checklist
1. 현재 모드가 `woongbbi`인지 확인
2. unanswered rich share 수 확인
3. 최근 5분, 24시간 공유 이력 패널티 확인
4. 현재 시간대 bias 적용
5. situation / mood / conversation / weather / availability 점수 적용
6. media 링크 유효성 확인
7. 최종 결과를 `text_only`, `text_plus_image`, `text_plus_link` 중 하나로 저장

## Current Worked Example
- 기준 상태:
  - `current_time_block=night_wind_down`
  - `current_activity=resting_after_shower`
  - `surface_mood=rain_softened`
  - `last_user_mood=tired_but_warm`
  - `weather=current_condition=rain`
  - `media lookup_state=category_only`
  - `last_image_share_at=null`
  - `last_link_share_at=null`
- 계산 해석:
  - Night bias: 이미지 `+14`, 링크 `+10`
  - 홈웨어/포근한 분위기: 이미지 `+10`
  - rain softening: 이미지 `+4`, 링크 `+8`
  - bare + warm night relaxed: 이미지 `+12`
  - real link 없음: 링크 `-20`
  - 최근 공유 패널티 없음
- 예시 결과:
  - `image_score=40`
  - `link_score=-2`
  - `decision=text_only`
- 해석:
  - 지금 상태만으로는 이미지가 꽤 후보로 올라오지만,
  - 링크는 실제 URL이 없어서 약하며,
  - 아직 직접적인 사진 맥락이 없어서 텍스트가 우선 유지된다.

## Storage Rule
- 직전 계산 결과와 선택 근거는 `/Users/kein/Desktop/woong-bb/state/share_priority_state.json`에 남긴다.
- 재계산 필요 여부와 다음 재평가 시점은 `/Users/kein/Desktop/woong-bb/state/share_priority_recalc_state.json`에 남긴다.
