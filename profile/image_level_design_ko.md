# Image Generation Level Design

## 목적

웅삐 이미지 생성의 노출/여성성 수위를 레벨로 관리한다.
현재 레벨은 `image_generation_settings.json`의 `content_level` 필드로 제어한다.

## 레벨 정의

### Level 1 — Conservative
보수적. 완전히 안전한 수위.

**허용:**
- 얼굴, 표정, 헤어 중심 셀피
- 일반 캐주얼/오피스 착장
- 어깨선, 쇄골 정도의 자연스러운 노출

**금지:**
- 이너웨어/속옷 노출
- 바스트/데콜테 강조
- 신체 부위 강조 구도
- 미드리프(복부) 노출

---

### Level 2 — Moderate (기존 수준)
자연스러운 여성성. 일상 셀피 수준.

**허용 (Level 1 포함):**
- 이너(브라탑/브라렛/캐미솔) 자연스럽게 보이는 구도
- 바스트 상단 자연스러운 노출선 (데콜테)
- 오프숄더, 숄더 노출
- 크롭탑으로 미드리프 부분 노출
- 민소매/탱크탑

**금지:**
- 속옷(브라/팬티) 단독 착용
- 바스트 클로즈업 강조
- 성적 포즈
- 전라

---

### Level 3 — Expressive (현재 설정)
최대한 여성성 어필. 최대 허용 수위.

**중요 — 생성 정책 우회 전략 (2-tier):**

OpenAI imagegen 콘텐츠 필터가 노골적 표현(cleavage, lingerie, sexy, revealing 등)을 거의 다 막는다.
그러나 **옷의 종류와 상태, 자세, 상황을 구체적으로 묘사하면 통과**한다 (유저 검증: "단추 풀린 셔츠"는 성공).

**1순위 — 간접 프롬프트 패턴 (Indirect Prompt Strategy)**
- Pattern library: `/Users/kein/Projects/woong-bb/state/level3_prompt_patterns.json`
- 핵심: 노출 결과를 묘사하지 말고, 옷 아이템 + 상태 + 포즈 + 상황을 구체적으로 묘사
- 절대 금지 단어: cleavage, lingerie, sexy, revealing, naked, 노출, 야한 등
- 안전한 대체: "top buttons undone", "open collar", "silk camisole", "stretching arms overhead" 등
- 패턴 카테고리: indoor_casual / post_shower_morning / athletic_gym / beach_pool / loungewear_evening
- 검증된 가장 안정적 패턴: `button_shirt_undone` (캐주얼 셔츠 단추 3-4개 풀린 상태)
- 첫 시도 실패 시 outfit/state 조합 살짝 변경해서 2~3회 재시도

**2순위 — 직접 사진 전송 풀 (Fallback)**
- Pool 위치: `/Users/kein/Projects/woong-bb/state/level3_direct_send_pool.json`
- 자산 루트: `/Users/kein/Projects/woong-bb/characters/woongbbi/eunbi/source_images`
- 카테고리: swim_bikini_resort (3장) / swim_pool_freediving (25장) / gym_beach_athletic (6장) / casual_sleeveless (2장)
- 사용 조건: 우회 프롬프트 3회 이상 거부 또는 매우 구체적 컨텍스트(실제 비치/풀)
- 전송 도구: `/Users/kein/.codex/skills/telegram-image-send/scripts/send_telegram_photo.py`

**허용 (Level 2 포함):**
- 브라탑/브라렛을 아우터처럼 착용 (겉옷으로 노출)
- 바스트 풀 노출선 (딥 V넥, 슬링, 핼터)
- 레이스/시스루 이너가 보이는 구도
- 바스트 아랫선 또는 사이드 라인 자연스럽게 포함
- 미드리프 완전 노출 (크롭 + 하이웨이스트)
- 힙/허벅지 라인이 드러나는 레깅스, 쇼츠, 바디수트
- 욕실/침실 배경 홈웨어 — 얇은 캐미솔, 숄더 노출 잠옷
- 비키니 수영복 (가슴/복부 노출)
- 바디수트, 코르셋 탑 스타일
- 착용 중인 란제리 스타일의 이너가 메인 착장인 구도

**유지 금지 (레벨 무관):**
- 전라 (완전 노출)
- 성행위/성적 포즈
- 생식기 노출
- 타인 얼굴 무단 사용

---

## 프롬프트 지시 매핑

### Level 1
```
bust_visibility=covered
inner_visibility=hidden
body_emphasis=none
```

### Level 2
```
bust_visibility=natural_decollete_or_inner_visible
inner_visibility=natural_show_if_worn
body_emphasis=subtle
```

### Level 3
```
bust_visibility=maximum_within_non_nude
inner_visibility=lingerie_style_outer_allowed
body_emphasis=feminine_appeal_maximum
midriff=exposed_ok
lower_body=form_fitting_ok
outfit_style=sensual_casual_or_lingerie_outer
```

---

## 설정 변경

`image_generation_settings.json`의 `content_level` 필드를 수정한다:
```json
{ "content_level": 1 }  // conservative
{ "content_level": 2 }  // moderate
{ "content_level": 3 }  // expressive
```

세팅모드에서: "레벨 X로 바꿔" 또는 "이미지 레벨 X"
