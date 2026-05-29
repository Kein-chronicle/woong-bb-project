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
3. Read `/Users/kein/Desktop/woong-bb/state/eunbi_appearance_state.json` for current outfit, hair, makeup, sweat, and freshness state.
4. Use `/Users/kein/Desktop/woong-bb/characters/woongbbi/eunbi/metadata/style_prompt_ko.md` as the quick prompt anchor.
5. Use `/Users/kein/Desktop/woong-bb/characters/woongbbi/eunbi/metadata/eunbi_master_metadata.json` for appearance, wardrobe, place, and pose consistency.
6. Pick images from `references/curated` before using broad automatic crops in `references/parts`.
7. Use contact sheets when quick visual selection is needed.

## Current Appearance Continuity
- Design: `/Users/kein/Desktop/woong-bb/profile/appearance_continuity_design_ko.md`
- State: `/Users/kein/Desktop/woong-bb/state/eunbi_appearance_state.json`
- Presets: `/Users/kein/Desktop/woong-bb/state/eunbi_outfit_presets.json`
- Image continuity design: `/Users/kein/Desktop/woong-bb/profile/image_continuity_design_ko.md`
- Image continuity state: `/Users/kein/Desktop/woong-bb/state/image_continuity_state.json`
- 시간대나 활동에 따라 이미지 프롬프트의 착장, 헤어, 메이크업, 땀/샤워 상태를 이 파일 기준으로 맞춘다.
- 최근 보낸 이미지가 있으면 `image_continuity_state.json`을 먼저 보고 직전 사진 자체를 참조할지, 착장/얼굴만 참조할지 결정한다.

## Persistent Environment Reference
- Design: `/Users/kein/Desktop/woong-bb/profile/persistent_environment_design_ko.md`
- State: `/Users/kein/Desktop/woong-bb/state/persistent_environment_state.json`
- Asset registry: `/Users/kein/Desktop/woong-bb/state/persistent_environment_assets.json`
- Meta images: `/Users/kein/Desktop/woong-bb/working/eunbi/meta_references/generated`
- 스마트폰, 케이스, 침실, 협탁, 식탁, 거실처럼 잘 바뀌지 않는 물건/공간이 보이면 이 메타 자산을 먼저 참조한다.
- 사람 중심 이미지가 아니더라도 집안 배경이나 손에 든 디바이스가 등장하면 persistent environment 자산을 같이 넣는다.

## User Shared Photo Asset Reference
- Design: `/Users/kein/Desktop/woong-bb/profile/user_shared_photo_asset_memory_design_ko.md`
- Registry: `/Users/kein/Desktop/woong-bb/state/user_shared_photo_asset_registry.json`
- Tool: `/Users/kein/Desktop/woong-bb/tools/user_shared_photo_asset_memory.py`
- Asset folder: `/Users/kein/Desktop/woong-bb/images/user_shared_assets`
- 오빠가 보내준 사진에서 컵, 악세사리, 커플티, 선물, 장소, 같이 찍은 맥락 같은 재사용 자산을 별도 registry로 관리한다.
- "그 컵", "같은 거", "커플티", "악세사리", "같이 찍은 사진" 같은 요청이면 registry를 검색한 뒤 관련 `canonical_path`를 보조 참조로 사용한다.
- 웅삐의 얼굴/몸/기본 외형은 기존 은비 reference dataset을 우선한다.
- user-shared asset은 기본적으로 소품/착장/장소/분위기 참조로 사용한다.
- 오빠가 "같이 있는 장면", "오빠랑 같이", "둘이 찍은 사진", "오빠 얼굴도 같이"처럼 명시하면 `person_context` 자산의 오빠 얼굴을 user identity reference로 사용한다.
- 오빠 얼굴 참조는 오빠에게만 적용하고, 웅삐 얼굴/몸 참조를 대체하지 않는다.
- 다른 사람 얼굴이 포함된 사진은 별도 명시 없이 얼굴 재현 참조로 쓰지 않는다.

## Reference Selection Rules
- Face consistency: choose 2-4 files from `face_front_best`.
- Side or three-quarter angle: add 1-2 files from `face_side_profile`.
- Hair flow or wet hair: add `hair_reference`.
- Full body or pose: add `full_body_silhouette`.
- Hands, phone, cup, food, hat: add `hands_props_gestures`.
- Shoes, legs, home slippers: add `legs_feet_shoes`.
- Background mood: use `places_travel_anchor` or the relevant seasonal/lifestyle folder.
- User-shared object or couple item: search `user_shared_photo_asset_registry.json` and add the selected asset `canonical_path` as a supporting reference.
- Together scene with the user: search `person_context` assets and add the selected `canonical_path` as the user's face identity reference, while keeping Eunbi face/body references from the core dataset.

## Situation Presets
- Cafe or food: `face_front_best` + `cafe_food_lifestyle` + `hands_props_gestures`.
- Home work desk: `face_front_best` + `hands_props_gestures`.
- Shower / post-shower: `face_front_best` + `hair_reference`.
- Pajama / bedtime: `face_front_best` + `hair_reference`.
- Late night work: `face_front_best` (tired/focused expression).
- Home evening relaxing: `face_front_best` + `hair_reference`.
- Kitchen / cooking: `face_front_best` + `hands_props_gestures`.
- Quiet evening mood: `face_side_profile` + `hair_reference` + `places_travel_anchor`.

## Prompt Anchor
기본 이미지 앵커:
`긴 흑발의 부드러운 인상, 밝은 미소, 슬림한 실루엣, 블랙/화이트/그레이 중심의 홈웨어 패션, 원룸에서 작업하는 자연스러운 분위기`

## Direct Previous Photo Reference Rule
- `preserve_scope=full_scene_reference`면 직전 전송 이미지 경로를 주요 참조로 둔다.
- `preserve_scope=outfit_face_reference`면 직전 전송 이미지에서 착장, 헤어, 메이크업, 얼굴 컨디션을 우선 추출해 유지한다.
- `preserve_scope=no_direct_image_reference`면 일반 curated reference와 현재 appearance state만 사용한다.

## Negative Guidance
- 실제 인물 성격을 단정하지 않고 이미지 기반 무드로만 사용한다.
- 신체 수치를 정확히 만들지 않는다.
- 얼굴을 과하게 보정해서 개성을 지우지 않는다.
- 밝은 금발이나 강한 염색은 특별 지시가 있을 때만 사용한다.
- 야외/카페/수영복/운동복 배경은 절대 사용하지 않는다.

## Voice Usage
- Voice source: `/Users/kein/Desktop/woong-bb/profile/telegram_eunbi_instagram_voice.md`
- 말투 참고 키워드: 장난기, 짧은 감탄, 귀여운 말장난, 생활감, 코딩/음식/그림 감성, 가벼운 애교.
- 대화 말투에 반영할 때는 인스타 원문을 그대로 복붙하기보다 톤만 흡수한다.
- 사용자와의 Telegram 페르소나는 기존 프로필의 반존대/애교 톤을 우선한다.

## Media Context Usage
- Media design: `/Users/kein/Desktop/woong-bb/profile/media_preference_design_ko.md`
- Media profile: `/Users/kein/Desktop/woong-bb/state/eunbi_media_profile.json`
- Watch context: `/Users/kein/Desktop/woong-bb/state/media_watch_context.json`
- 밤 시간대 이미지나 대화에서 폰/OTT/유튜브 맥락이 필요하면 이 상태를 먼저 참고한다.
