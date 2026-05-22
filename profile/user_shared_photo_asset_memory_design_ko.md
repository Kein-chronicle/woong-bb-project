# User Shared Photo Asset Memory Design

## Purpose
오빠가 Telegram으로 보내준 사진을 단순 대화 입력으로만 쓰지 않고, 나중에 다시 참조할 수 있는 사진 자산으로 정리한다.

핵심 목표:
- 사진을 보고 반응하는 동시에 재사용 가능한 메타데이터를 남긴다.
- 컵, 악세사리, 커플티, 선물, 배경, 같이 찍은 느낌의 사진처럼 나중에 이미지 생성에 쓸 수 있는 요소를 찾는다.
- "그 컵 쓰는 모습", "같은 거 샀잖아", "커플티 입은 장면", "같이 찍은 사진 느낌" 같은 요청이 오면 과거 사진 자산을 찾아 참조한다.
- 오빠가 "같이 있는 장면", "오빠랑 같이", "둘이 찍은 사진"처럼 명시하면 오빠 얼굴도 참조해 같이 있는 장면을 만들 수 있게 한다.

## Classification
- change_type: `new_script_integration`
- application_scope: `hybrid`
- asset_type: `image`
- generation_update: 수신 사진을 자산 registry에 저장하고 이미지 생성 시 참조 후보로 검색한다.
- review_update: 참조 자산이 요청 맥락과 맞는지, 개인/민감 정보가 과하게 재사용되지 않는지 확인한다.

## Main Files
- Design: `/Users/kein/Desktop/woong-bb/profile/user_shared_photo_asset_memory_design_ko.md`
- Registry: `/Users/kein/Desktop/woong-bb/state/user_shared_photo_asset_registry.json`
- Tool: `/Users/kein/Desktop/woong-bb/tools/user_shared_photo_asset_memory.py`
- Incoming raw folder: `/Users/kein/Desktop/woong-bb/images/incoming/YYYY-MM-DD/`
- Reusable asset folder: `/Users/kein/Desktop/woong-bb/images/user_shared_assets/<asset_id>/`
- Latest incoming context: `/Users/kein/Desktop/woong-bb/state/incoming_image_context.json`

## Storage Layers

### 1. Incoming Raw
- 모든 Telegram 수신 사진은 먼저 `images/incoming/YYYY-MM-DD/`에 저장한다.
- 이 파일은 수신 원본에 가까운 기록이다.
- 대화 로그에는 `direction=incoming`, `type=image`, `path`, `caption`을 남긴다.

### 2. Reusable Asset
- 재사용 가능성이 있는 사진은 `images/user_shared_assets/<asset_id>/source.ext`로 복사한다.
- 같은 폴더에 `metadata.json`을 함께 둔다.
- 원본 수신 경로는 registry의 `source_paths`에 보존한다.
- 같은 이미지 해시가 이미 있으면 새 자산을 만들지 않고 기존 자산의 `last_seen_at`, `captions`, `analysis`를 보강한다.

### 3. Registry
- `state/user_shared_photo_asset_registry.json`은 전체 자산의 검색 인덱스다.
- registry는 `asset_id`, `kind`, `title`, `canonical_path`, `tags`, `analysis`, `generation_reuse`를 가진다.
- 이미지 생성 전에는 registry를 검색해 관련 자산 후보를 고른다.

## Asset Kinds
- `person_context`: 오빠가 보내준 셀피, 같이 있는 분위기의 사람 중심 사진
- `shared_object`: 컵, 텀블러, 책, 키링, 장비처럼 특정 물건
- `wearable`: 티셔츠, 후드, 커플룩, 유니폼, 모자, 신발
- `accessory`: 반지, 팔찌, 시계, 안경, 머리핀, 가방
- `cup_or_tableware`: 머그컵, 커피잔, 접시, 식기
- `food_drink`: 커피, 음료, 음식, 디저트
- `place_scene`: 부엌, 카페, 책상, 산책길 같은 장소/배경
- `couple_item`: 오빠와 웅삐가 공유하거나 맞춘 것으로 대화상 정해진 물건
- `reference_bundle`: 여러 요소가 같이 쓰이는 참조 묶음
- `user_shared_photo`: 아직 분류가 애매한 일반 수신 사진

## Metadata Shape
사진을 분석할 때 아래 정보를 최대한 채운다.

```json
{
  "asset_kind": "cup_or_tableware",
  "title": "휴가 아침 커피 머그컵",
  "visible_summary_ko": "오빠가 부엌에서 흰색 머그컵을 들고 찍은 커피 사진",
  "description_ko": "전체적으로 편한 휴가 아침, 집 부엌, 직접 내린 커피 분위기",
  "visible_elements": ["흰색 머그컵", "초록색 로고", "부엌 수납장", "검은 티셔츠"],
  "scene_tags": ["home_kitchen", "morning_coffee", "holiday_morning"],
  "object_tags": ["mug", "coffee", "white_green_cup"],
  "relationship_tags": ["user_shared_photo", "daily_life", "coffee_memory", "user_face_reference"],
  "reuse_triggers": ["그 컵", "커피 마시던 컵", "같은 컵 쓰는 모습", "같이 찍은 사진", "오빠랑 같이 있는 장면"],
  "reusable_subjects": [
    {
      "kind": "cup_or_tableware",
      "label_ko": "흰색과 초록색 포인트가 있는 커피 머그컵",
      "description_ko": "손잡이가 있는 흰색 머그컵, 안쪽과 로고가 초록색 계열",
      "visual_tags": ["white_mug", "green_logo", "coffee_cup"],
      "reuse_when": ["same_cup_scene", "eunbi_using_matching_item", "coffee_lifestyle_photo"],
      "confidence": 0.86
    }
  ],
  "generation_reuse": {
    "allowed": true,
    "default_strength": "supporting_reference",
    "requires_user_intent": true,
    "prompt_hints_ko": ["흰색 머그컵과 초록색 포인트를 손에 든 자연스러운 홈 카페 장면"],
    "face_reference": {
      "allowed": true,
      "requires_explicit_user_request": true,
      "allowed_when": ["같이 있는 장면", "오빠랑 같이", "둘이 찍은 사진", "오빠 얼굴도 같이"],
      "default_strength": "identity_reference_for_user_only",
      "notes": "웅삐 얼굴 참조는 은비 reference dataset을 쓰고, 이 사진은 오빠 얼굴/인상 참조로만 쓴다."
    }
  },
  "privacy": {
    "contains_user_face": true,
    "contains_other_people": false,
    "sensitive": false,
    "reuse_face_without_explicit_request": false,
    "reuse_user_face_with_explicit_request": true
  }
}
```

## Incoming Photo Runtime
1. Telegram bridge가 사진을 `images/incoming/YYYY-MM-DD/`에 저장한다.
2. 웅삐 워커는 이미지를 실제로 보고 짧은 대화 반응을 준비한다.
3. 답변 전 가능한 범위에서 `tools/user_shared_photo_asset_memory.py add`를 실행한다.
4. 분석 JSON에는 보이는 요소, 재사용 가능한 물건/착장/장소, 검색 트리거, 생성 재사용 가능 여부를 넣는다.
5. 답변에는 registry 저장 과정을 설명하지 않고, 자연스럽게 사진에 반응한다.

## Generation Retrieval Rule
이미지 생성 요청에 아래 표현이 들어오면 registry 검색을 먼저 한다.

- "같이 찍은 사진", "전에 보낸 사진 느낌", "아까 사진"
- "그 컵", "같은 컵", "커피 마시던 컵"
- "같은 거 샀잖아", "커플템", "커플티", "같은 옷"
- "그 악세사리", "그 안경", "그 반지", "그 팔찌"
- "그 장소", "부엌", "책상", "카페 분위기"

검색 순서:
1. `user_shared_photo_asset_registry.json`에서 query/tag/kind 기반 후보를 찾는다.
2. 현재 요청과 가장 가까운 `reuse_triggers`, `reusable_subjects`, `generation_reuse.prompt_hints_ko`를 확인한다.
3. `canonical_path`를 이미지 생성 참조 후보로 넣는다.
4. 웅삐 얼굴/몸 참조는 기존 `characters/woongbbi/eunbi` reference를 유지한다.
5. 오빠가 보낸 자산은 기본적으로 소품/착장/장소/분위기 참조로 사용한다.
6. 다만 오빠가 "같이 있는 장면", "오빠랑 같이", "둘이 찍은 사진"처럼 명시하면 `person_context` 자산의 오빠 얼굴을 user identity reference로 사용한다.
7. 오빠 얼굴 참조는 오빠에게만 적용하고, 웅삐 얼굴을 오빠 사진으로 대체하지 않는다.

## Privacy And Safety
- 오빠가 보낸 사진은 이 프로젝트 안의 개인 자산으로만 저장한다.
- 사진 속 사람의 신원, 민감한 속성, 건강 상태, 나이 등은 단정하지 않는다.
- `contains_user_face=true`인 자산은 기본적으로 소품/장소/맥락 참조로만 쓴다.
- 오빠 얼굴 자체를 재현하거나 같이 찍은 사진처럼 쓰는 것은 오빠의 명시적 요청이 있을 때 허용한다.
- 오빠가 이 프로젝트에서 자기 얼굴 참조를 같이 있는 장면 생성에 쓰라고 명시하면, `reuse_user_face_with_explicit_request=true`인 자산을 검색하고 참조한다.
- 얼굴 참조 허용은 오빠 얼굴에 한정한다. 사진 속 타인은 별도 명시가 없으면 참조하지 않는다.
- 타인이 함께 보이면 `contains_other_people=true`로 두고 이미지 생성 참조 강도를 낮춘다.
- 민감하거나 사적인 장면은 `generation_reuse.allowed=false`로 저장한다.

## Review Rule
생성 전에 선택된 user-shared asset이 아래 조건을 만족하는지 확인한다.

- 요청 맥락과 태그가 맞는가
- 오빠가 원한 대상이 소품인지, 착장인지, 장소인지 분명한가
- 얼굴/사람 참조가 필요 이상으로 강하게 들어가지 않았는가
- 오빠 얼굴 참조가 필요한 요청인지 명시되어 있는가
- 오빠 얼굴 참조가 웅삐 얼굴/몸 참조를 대체하지 않았는가
- 커플템이나 같은 물건 설정이 대화 기록과 충돌하지 않는가
- 웅삐의 얼굴/몸/기본 외형 참조를 사용자 사진으로 대체하지 않았는가

## Tool Usage

초기화:
```bash
python3 /Users/kein/Desktop/woong-bb/tools/user_shared_photo_asset_memory.py init
```

자산 등록:
```bash
python3 /Users/kein/Desktop/woong-bb/tools/user_shared_photo_asset_memory.py add \
  --image "/absolute/path/to/incoming.jpg" \
  --caption "오빠가 보낸 캡션" \
  --telegram-user "K8832353" \
  --analysis-json analysis.json
```

검색:
```bash
python3 /Users/kein/Desktop/woong-bb/tools/user_shared_photo_asset_memory.py search \
  --query "그 컵 커피" \
  --limit 5
```
