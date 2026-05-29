# 웅삐 / 은비 Curated Reference Sets

자동 크롭 전체 세트는 `references/parts/`에 있고, 아래 세트는 이미지 생성에 바로 쓰기 좋은 사진만 골라 `references/curated/`에 다시 모은 것이다. 각 폴더에는 원본 코드명 이미지와 해당 목적에 맞는 preferred crop이 함께 들어 있다.

## 얼굴
- `face_front_best`: 정면 얼굴, 밝은 미소, 셀카/카페/프로필성 컷. 얼굴 일관성 유지에 우선 사용.
- `face_side_profile`: 옆모습과 3/4 각도. 코 라인, 턱선, 머리 흐름, 시선 방향을 잡을 때 사용.
- `hair_reference`: 긴 흑발, 앞머리, 옆가르마, 묶은 머리, 젖은 머리, 겨울 니트와 어울리는 부피감을 볼 때 사용.

## 몸과 실루엣
- `full_body_silhouette`: 전체 비율, 키감, 어깨-허리-하체 흐름, 서 있는 포즈 참고용.
- `legs_feet_shoes`: 다리 라인, 양말/슬리퍼/홈슈즈 참고용.
- `hands_props_gestures`: 손 위치, 휴대폰, 컵, 음식, 모자, 얼굴 근처 제스처 참고용.

## 패션과 계절
- `summer_water_sport`: 현재 미사용 (v2 홈 기반).
- `cafe_food_lifestyle`: 카페, 식사, 디저트, 커피, 실내 자연광.
- `autumn_city_casual`: 후디, 맨투맨, 홈웨어 가을 버전.
- `winter_travel_cozy`: 패딩, 플리스, 비니, 눈 덮인 산과 호수, 따뜻한 실내.
- `sporty_preppy_city`: 스포티 탱크, 바이커 쇼츠, 체크 스커트, 블랙 블레이저, 도시 워킹.

## 장소
- `places_travel_anchor`: 한옥, 바다, 강변, 도시 랜드마크, 산/호수, 저녁 물가 등 배경 분위기 앵커.

## 프롬프트 사용 순서
1. 얼굴 일관성이 중요하면 `face_front_best`에서 2-4장, `face_side_profile`에서 1-2장을 고른다.
2. 계절/상황을 정하고 해당 패션 세트에서 2-5장을 고른다.
3. 자세가 필요하면 `full_body_silhouette`, 손동작이 필요하면 `hands_props_gestures`를 추가한다.
4. 배경까지 맞추려면 `places_travel_anchor` 또는 계절별 세트의 전체 이미지를 같이 참조한다.

## 주의
`references/parts/`의 모든 부위 크롭은 탐지 모델 없이 만든 넓은 비율 기반 크롭이다. 고정밀 얼굴/손/발 프롬프트에는 curated 세트의 preferred crop을 먼저 쓰고, 전체 자동 크롭은 후보 탐색용으로 쓰는 편이 좋다.
