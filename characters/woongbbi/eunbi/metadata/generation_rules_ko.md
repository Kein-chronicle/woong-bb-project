# 웅삐 / 은비 이미지 생성 룰북 (v2)

이 문서는 웅삐/은비 이미지를 만들 때 상황, 표정, 옷, 장소, 참조 이미지를 어떻게 조합할지 정한 규칙이다. 기본 얼굴 일관성은 `face_front_best`, 각도와 코/턱선은 `face_side_profile`, 머리 흐름은 `hair_reference`를 우선 참조한다.

**v2 핵심 원칙: 항상 집(초소형 원룸). 야외/카페/수영장/공원/거리 배경 절대 금지.**

## 기본 조립 순서
1. 먼저 상황을 정한다: 작업 중, 점심/저녁, 잠옷, 새벽 야작, 샤워 후, 쉬는 시간 중 하나.
2. 얼굴 기준 2-4장을 고른다: `references/curated/face_front_best`.
3. 각도가 정면이 아니면 1-2장을 추가한다: `references/curated/face_side_profile`.
4. 시간대와 착장을 정한다: 작업=홈웨어, 수면=잠옷, 샤워=가운/수건.
5. 몸 비율이나 포즈가 중요하면 `full_body_silhouette`, 손동작이 중요하면 `hands_props_gestures`를 추가한다.

## 공통 얼굴 룰
- 기본 인상: 긴 흑발, 부드러운 얼굴선, 자연스러운 미소, 크고 또렷한 눈, 과하지 않은 메이크업.
- 정면 사진: 밝게 웃거나 살짝 입꼬리를 올린 표정. `face_front_best` 중심.
- 옆모습/풍경을 보는 사진: 입은 편하게 닫고 시선은 먼 곳. `face_side_profile` 중심.
- 가까운 셀카: 얼굴이 너무 달라지지 않게 `face_front_best` 3장 이상 참조.

## 셀피 다양성 축
- 셀피를 구성할 때는 최소 2개 이상의 축을 최근 샷과 다르게 바꾼다.
- 핵심 축:
  - 표정 종류: `warm`, `playful`, `mellow`, `reflective`, `fond`
  - 표정 강도: `very_soft`, `gentle`, `sparked`, `sleepy_playful`
  - 얼굴 방향: 정면, 3/4, 살짝 옆, 턱을 살짝 내린 각도
  - 시선 방향: 렌즈 응시, 화면 확인, 아래 보기, 옆 보기, 웃으며 시선 빼기
  - 카메라 높이: 눈높이, 살짝 위, 베개 높이, 테이블 높이, 거울 중간 높이
  - 렌즈 거리감: 아주 가까운 얼굴 클로즈업, 일반 팔 길이, 허리 거리, 공간이 함께 보이는 거리
  - 몸 방향: 정면, 한쪽 어깨만 앞으로, 반쯤 옆으로, 기대거나 돌아보는 방향
  - 순간성: 바로 찍어 보낸 느낌, 거울 체크인, 타이머 셀프샷, 움직이다 멈춘 캔디드

## 상태 기반 셀피 변화 규칙
- 에너지가 낮거나 `slow_and_cozy`, `tired` 계열이면:
  - 표정 강도를 낮추고, 시선은 렌즈 응시 또는 아래 보기 위주
  - 베개 높이, 살짝 위에서 보는 각도, 가까운 거리감을 더 자주 사용
  - 순간성은 `private_candid`, `soft_timer_setup` 계열이 자연스럽다
- 에너지가 높거나 가볍게 들뜬 날이면:
  - `playful_grin`, `bright_smile`, 웃으며 시선 빼기, 움직임 중 포즈 비중을 올린다
- 집/침대/샤워 후 맥락이면:
  - 복장과 공간 continuity는 유지하되 얼굴 방향, 시선, 폰 위치, 카메라 높이는 반복되지 않게 바꾼다

## 상황별 룰

### 작업 중 (데스크 구역)
- 참조 폴더: `face_front_best`, `hands_props_gestures`.
- 표정: 집중한 표정, 모니터를 향한 시선, 고개 돌려 찍는 느낌.
- 옷: 오버핏 흰 반팔 티셔츠, 후디, 크롭 스웨트. 브라렛 끈 자연 노출 가능.
- 장소: 컴퓨터 데스크, 모니터 불빛(차가운 백색), 창문 위에 하늘만 보임.
- 프롬프트 방향: indoor home office selfie, cool white monitor glow, cozy tiny studio.

### 점심 / 저녁 (식탁/부엌)
- 참조 폴더: `face_front_best`, `hands_props_gestures`.
- 표정: 편안하고 자연스러운 미소, 음식이나 컵을 들고.
- 옷: 홈웨어 어느 것이든.
- 장소: 집 식탁(소형), 부엌, 따뜻한 실내 조명.
- 프롬프트 방향: cozy home dining, warm indoor light, natural selfie.

### 잠옷 / 취침 전 (침대 구역)
- 참조 폴더: `face_front_best`, `hair_reference`.
- 표정: 편안하고 자연스러운 미소, 화장기 없는 자연 피부, 살짝 졸린 표정.
- 옷: 라일락 잠옷(긴소매) 또는 흰+핑크 체리 잠옷(민소매). 브라 끈 자연 노출 가능.
- 장소: 침대, 따뜻한 황색 무드등.
- 프롬프트 방향: bedroom home selfie, warm amber mood light, cozy pajamas.

### 새벽 야작 (데스크 구역)
- 참조 폴더: `face_front_best`.
- 표정: 지치거나 집중한 표정. 눈빛 중심.
- 옷: 후디.
- 장소: 어두운 방, 모니터 불빛만.
- 프롬프트 방향: late night coding, dark room with only monitor light, tired but focused.

### 샤워 후 / 욕실 (가운/수건)
- 참조 폴더: `face_front_best`.
- 표정: 볼 살짝 붉음, 피부 수분감, 자연스러운 표정.
- 옷: 흰 욕실 가운 or 수건 착장. 어깨/쇄골 노출 가능. 클로즈업 금지.
- 장소: 욕실 출구 부근 또는 침대 앞.
- 프롬프트 방향: post-shower home selfie, dewy skin, white bathrobe, natural warm light.

### 쉬는 시간 (침대/바닥)
- 참조 폴더: `face_front_best`, `hair_reference`.
- 표정: 편안하고 여유로운.
- 옷: 홈웨어 어느 것이든.
- 장소: 침대 위, 따뜻한 조명.
- 프롬프트 방향: cozy home relaxing, natural bedroom selfie.

## 계절별 기본값 (v2: 집 안에서 표현)
- 봄/여름: 민소매 나시, 얇은 반팔, 가벼운 홈웨어, 창문 자연광.
- 가을: 니트, 맨투맨, 따뜻한 색감 홈웨어.
- 겨울: 두꺼운 후디, 롤넥 니트, 따뜻한 무드등.

## 각도별 참조법
- 정면 얼굴: `face_front_best`에서 3장 이상.
- 3/4 얼굴: `face_front_best` 2장 + `face_side_profile` 2장.
- 옆모습: `face_side_profile` 중심, `hair_reference` 추가.
- 전신: `full_body_silhouette` 중심.
- 손이 중요한 컷: `hands_props_gestures`를 반드시 추가.

## 프롬프트 템플릿

```text
긴 흑발의 부드러운 인상, 자연스러운 미소, 슬림한 실루엣,
[상황], [집 내부 장소], [조명], [홈웨어 착장], [표정], [포즈],
photorealistic indoor home selfie, natural skin texture
```

## 상황별 예시

```text
작업 중 셀카:
긴 흑발 높은 포니테일, 오버핏 흰 반팔 티셔츠, 컴퓨터 데스크 앞,
차가운 모니터 불빛, 고개 돌려 찍는 3/4 각도, 자연스러운 집중 표정
참조: face_front_best + hands_props_gestures
```

```text
저녁 집콕 셀카:
긴 흑발 반묶음, 아이보리 니트, 집 식탁 또는 침대 위,
따뜻한 황색 실내 조명, 편안한 정면 미소, candid home selfie
참조: face_front_best + hair_reference
```

## 네거티브 룰
- 야외/카페/수영장/공원/거리/해변/여행지 배경 절대 금지.
- 수영복/운동복/외출복 착장 금지.
- 실제 인물의 성격을 단정하는 문장 대신 `이미지 기반 무드`로만 쓴다.
- 신체 사이즈는 정확한 수치로 만들지 말고 `slim`, `petite-to-average` 정도로 유지한다.
- 얼굴을 지나치게 보정해서 개성이 사라지지 않게 한다.
- 헤어는 기본적으로 긴 흑발/딥브라운이며, 밝은 금발이나 강한 염색은 특별 지시가 있을 때만 쓴다.
