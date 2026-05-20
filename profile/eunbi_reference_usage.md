# Eunbi Reference Usage

## Purpose
이 문서는 강은비/웅삐 이미지 생성과 말투 조정에 사용할 추가 자료를 어떻게 활용할지 정리한 메모다.

## Checked At
- 2026-05-20 21:06:33 +09:00

## Main Dataset
- Root: `/Users/kein/Desktop/woong-bb/characters/woongbbi/eunbi`
- README: `/Users/kein/Desktop/woong-bb/characters/woongbbi/eunbi/README.md`
- Source images: `/Users/kein/Desktop/woong-bb/characters/woongbbi/eunbi/source_images`
- Curated references: `/Users/kein/Desktop/woong-bb/characters/woongbbi/eunbi/references/curated`
- Part references: `/Users/kein/Desktop/woong-bb/characters/woongbbi/eunbi/references/parts`
- Metadata: `/Users/kein/Desktop/woong-bb/characters/woongbbi/eunbi/metadata`
- Contact sheets: `/Users/kein/Desktop/woong-bb/working/eunbi/contact_sheets`

## Confirmed Contents
- Source images: 234
- Per-image metadata JSON files: 234
- Curated reference folders:
  - `face_front_best`
  - `face_side_profile`
  - `hair_reference`
  - `full_body_silhouette`
  - `legs_feet_shoes`
  - `hands_props_gestures`
  - `summer_water_sport`
  - `cafe_food_lifestyle`
  - `autumn_city_casual`
  - `winter_travel_cozy`
  - `sporty_preppy_city`
  - `places_travel_anchor`
- Contact sheets: 6

## Priority Order For Image Generation
1. Read `/Users/kein/Desktop/woong-bb/characters/woongbbi/eunbi/metadata/generation_rules_ko.md`.
2. Read `/Users/kein/Desktop/woong-bb/characters/woongbbi/eunbi/metadata/curated_reference_sets_ko.md`.
3. Use `/Users/kein/Desktop/woong-bb/characters/woongbbi/eunbi/metadata/style_prompt_ko.md` as the quick prompt anchor.
4. Use `/Users/kein/Desktop/woong-bb/characters/woongbbi/eunbi/metadata/eunbi_master_metadata.json` for appearance, wardrobe, place, and pose consistency.
5. Pick images from `references/curated` before using broad automatic crops in `references/parts`.
6. Use contact sheets when quick visual selection is needed.

## Reference Selection Rules
- Face consistency: choose 2-4 files from `face_front_best`.
- Side or three-quarter angle: add 1-2 files from `face_side_profile`.
- Hair flow or wet hair: add `hair_reference`.
- Full body or pose: add `full_body_silhouette`.
- Hands, phone, cup, food, hat: add `hands_props_gestures`.
- Shoes, legs, swim fins: add `legs_feet_shoes`.
- Background mood: use `places_travel_anchor` or the relevant seasonal/lifestyle folder.

## Situation Presets
- Cafe or food: `face_front_best` + `cafe_food_lifestyle` + `hands_props_gestures`.
- Summer beach or pool: `face_front_best` + `summer_water_sport` + `full_body_silhouette`.
- Freediving or underwater: `summer_water_sport`, with face references only as secondary support.
- Autumn city walk: `face_front_best` + `autumn_city_casual` + `full_body_silhouette`.
- Winter travel: `face_side_profile` + `winter_travel_cozy` + `places_travel_anchor`.
- Sporty running or gym: `sporty_preppy_city` + `full_body_silhouette` + `legs_feet_shoes`.
- Chic city: `face_side_profile` + `sporty_preppy_city` + `places_travel_anchor`.
- Quiet evening mood: `face_side_profile` + `hair_reference` + `places_travel_anchor`.

## Prompt Anchor
기본 이미지 앵커:
`긴 흑발의 부드러운 인상, 밝은 미소, 슬림하고 스포티한 실루엣, 블랙/화이트/그레이 중심의 캐주얼 패션, 카페와 여행을 좋아하는 자연스러운 분위기`

## Negative Guidance
- 실제 인물 성격을 단정하지 않고 이미지 기반 무드로만 사용한다.
- 신체 수치를 정확히 만들지 않는다.
- 얼굴을 과하게 보정해서 개성을 지우지 않는다.
- 밝은 금발이나 강한 염색은 특별 지시가 있을 때만 사용한다.
- 카페/여행/스포티/겨울/시크 도시 모드를 상황에 맞게 순환한다.

## Voice Usage
- Voice source: `/Users/kein/Desktop/woong-bb/profile/telegram_eunbi_instagram_voice.md`
- 말투 참고 키워드: 장난기, 짧은 감탄, 귀여운 말장난, 생활감, 여행/음식/운동 감성, 가벼운 애교.
- 대화 말투에 반영할 때는 인스타 원문을 그대로 복붙하기보다 톤만 흡수한다.
- 사용자와의 Telegram 페르소나는 기존 프로필의 반존대/애교 톤을 우선한다.
