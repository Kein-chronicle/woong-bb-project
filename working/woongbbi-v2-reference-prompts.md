# 웅삐 v2 레퍼런스 이미지 요구서

---

## 생성 구조

```
1단계: F (얼굴) → SP (공간) → OC (착장+공간 세트)
2단계: OC 1장 + F 1장 + 행동/표정/촬영 텍스트 프롬프트 → 실제 장면 이미지
```

---

## 고정 인물 설정 (전 이미지 공통)

```
Korean woman, mid-20s to early 30s appearance
Hair: long straight dark black hair, natural and clean
Face: small oval face, soft jawline, clear smooth skin, large dark expressive eyes
Body: slim, petite-to-average build
Style: photorealistic, no heavy makeup, natural skin texture
```

---

## 고정 공간 설정 (OC 전 이미지 공통)

```
Extremely small minimalist studio apartment (one-room)
Walls: warm off-white. Floor: light wood-grain laminate.
Window: small horizontal window showing only sky (no ground, no buildings)
Furniture: compact computer desk + monitor, single low bed, small dining table, mini kitchen
No outdoor scenes. No cafe. No park. No gym. Home only.
```

---

## F — 얼굴 레퍼런스 (6장)

> 목적: 얼굴 구조/피부/눈 고정. OC 생성과 실제 장면 생성 시 reference input으로 사용.
> 배경: 아웃포커스 오프화이트. 인물 단독.

### F-01 — 정면 중립 (안경 없음)
```
Photorealistic portrait photograph of a Korean woman in her mid-20s to early 30s.
Face: small oval face, soft jawline, clear smooth skin, large dark expressive eyes with natural lashes, small straight nose, soft closed lips in a neutral expression.
Hair: long straight dark black hair, slightly parted in the middle, falling naturally over shoulders. A few delicate face-framing strands near the temples.
No glasses. No makeup — natural bare skin with slight glow.
Shot: front-facing, eye-level, shallow depth of field.
Background: soft out-of-focus warm off-white.
Lighting: soft diffused natural light from slightly left.
Camera: 85mm portrait lens equivalent, f/2.0 bokeh.
Photorealistic, natural skin texture, no airbrushing.
```

### F-02 — 정면 미소 (안경 없음)
```
Same subject and facial structure as F-01.
Hair: long straight dark black hair, naturally down.
Expression: warm natural smile, slight cheek lift, eyes slightly squinted with genuine warmth. Lips softly parted in a gentle smile.
No glasses. Light natural glow on skin.
Shot: front-facing, eye-level, shallow depth of field.
Background: soft out-of-focus warm off-white.
Lighting: soft natural window light from left.
Camera: 85mm, f/2.0.
Photorealistic, warm and candid feel.
```

### F-03 — 3/4 측면 (안경 없음)
```
Same subject and facial structure as F-01.
Hair: long straight dark black hair falling naturally, slightly swept behind one ear on the near side.
Expression: soft neutral gaze directed slightly off-camera to the far side. Calm expression.
No glasses.
Shot: 3/4 angle (face turned ~45 degrees), eye-level, shallow depth of field.
Background: soft out-of-focus off-white.
Lighting: side lighting from the far side — natural and flattering.
Camera: 85mm, f/2.0.
Photorealistic.
```

### F-04 — 옆 프로필 (안경 없음)
```
Same subject and facial structure as F-01.
Hair: long straight dark black hair, falling behind shoulder in profile view.
Expression: calm, slight upward gaze.
No glasses.
Shot: pure side profile, face pointing left, eye-level.
Background: soft out-of-focus off-white.
Lighting: light from front, illuminating the visible cheek and jaw.
Camera: 85mm, f/2.0.
Photorealistic.
```

### F-05 — 정면 중립 (안경 착용)
```
Same subject and facial structure as F-01.
Hair: long straight dark black hair, naturally down.
Glasses: thin transparent clear-frame or thin silver metal frame. Rectangular lenses, slim bridge, slightly wide to suit the face. No tinted lenses.
Expression: neutral, calm. Eyes visible and expressive through clear lenses.
Shot: front-facing, eye-level.
Background: soft out-of-focus off-white.
Lighting: soft natural light from left. Minimal lens glare.
Camera: 85mm, f/2.0.
Photorealistic.
```

### F-06 — 정면 미소 (안경 착용)
```
Same subject and facial structure as F-01.
Hair: long straight dark black hair, naturally down.
Glasses: same thin clear or silver metal frame as F-05.
Expression: warm genuine smile, same warmth as F-02. Eyes lit up behind glasses.
Shot: front-facing, eye-level.
Background: soft out-of-focus off-white.
Lighting: soft natural light from left.
Camera: 85mm, f/2.0.
Photorealistic, warm and candid feel.
```

---

## SP — 공간 레퍼런스 (4장)

> 목적: 배경/조명/가구 배치 고정. OC 생성 시 배경 기준으로 사용.
> 인물 없음.

### SP-01 — 컴퓨터 데스크 구역
```
Photorealistic interior photograph of an extremely small minimalist studio apartment. No people.
Focus: computer desk area.
Desk: narrow long desk, light natural oak wood top, white or black thin metal legs.
Monitor: matte black 27-inch, thin bezels, slim silver stand, showing dark-background code editor.
Keyboard: full-size mechanical, gray/white keycaps, black body, cool white backlight, on large black mouse pad.
One simple ceramic white or dark navy mug on the desk.
Chair: compact black mesh ergonomic chair.
Window: small horizontal window above desk at upper wall level — only sky visible through it (overcast or blue). White frame, thin semi-transparent curtain.
Walls: warm off-white. Floor: light wood-grain laminate.
Lighting: cool white desk lamp, subtle blue-tinted work light.
Shot: straight-on frontal view of desk. Realistic interior photography, slightly wide angle.
```

### SP-02 — 침대 구역
```
Photorealistic interior photograph of an extremely small minimalist studio apartment. No people.
Focus: bed area.
Bed: single-size low platform bed, flat rectangular headboard, light beige or off-white oak wood, very low profile. White mattress cover.
Bedding: light soft comforter in pale mint green or white, naturally folded. Two pillows with white or light gray slightly rumpled cotton pillowcases.
Beside the bed: small round warm-yellow mood lamp on the floor or small surface, emitting soft warm amber glow.
Walls: warm off-white. Floor: light wood-grain.
Lighting: warm amber from the mood lamp, soft and cozy.
Shot: straight-on view of the bed. Realistic interior photography.
```

### SP-03 — 식탁 / 미니 주방 구역
```
Photorealistic interior photograph of an extremely small minimalist studio apartment. No people.
Focus: small dining table and compact kitchen.
Table: small round or square (~60cm), light oak wood top, thin black metal legs. One small folding stool beside it.
Kitchen: compact — 2-burner induction cooktop, small white refrigerator (waist height ~80-90cm), single-basin white sink, 1-2 small open shelves with a few plates/cups. Clean and minimal.
Walls: warm off-white. Floor: light wood-grain.
Lighting: warm natural overhead light.
Shot: angled view showing both table and kitchen corner. Realistic interior photography.
```

### SP-04 — 원룸 전체 광각
```
Photorealistic interior photograph of an extremely small minimalist studio apartment. No people. Wide angle.
Show entire room in one shot:
- Far wall: computer desk with monitor, keyboard, mug. Small window above showing only sky.
- Adjacent: single low platform bed with pale mint or white bedding.
- Near corner: small dining table and compact white kitchen. Bathroom door (closed) near kitchen.
Walls: warm off-white throughout. Floor: continuous light wood-grain laminate. Ceiling: low, white.
The room is extremely small — everything compact and close together. Minimal decoration, very clean.
Shot: wide-angle from near entrance looking into room, slightly elevated eye level.
Realistic interior photography, architectural quality.
```

---

## OC — 착장 레퍼런스 (13장)

> 목적: 착장+공간 조합 고정. 실제 장면 생성 시 F 이미지와 함께 reference input으로 사용.
> 공통: 인물 설정 = F-01/F-02 기준 얼굴. 배경 = SP 기준 초소형 원룸.
> 공통 네거티브: outdoor, beach, cafe exterior, park, street, gym, swimming pool, sports field.

### OC-01 — 기본 작업복 (O-01)
```
Photorealistic photograph. Korean woman at a compact computer desk in an extremely small minimalist studio room.
Outfit: oversized white short-sleeve t-shirt, wide round neckline — loose enough that a white bralette strap is naturally visible near the shoulder (not emphasized). Hem to mid-thigh. Short black cotton shorts, elastic waist.
Hair: long dark black hair in high ponytail. A few face-framing strands. One beige scrunchie on the wrist. Barefoot. No earrings. Natural skin.
Background: SP-01 desk area. Cool white monitor glow and desk lamp.
Shot: half-body, slight high angle, arm's-length selfie feel. Front or 3/4 angle.
Photorealistic, candid, natural.
```

### OC-02 — 후디 작업복 (O-02)
```
Photorealistic photograph. Korean woman at a compact computer desk in a tiny studio room.
Outfit: oversized light gray hoodie sweatshirt, no zipper (pullover), kangaroo pocket, thumb holes. Slightly stretched neckline reveals edge of thin white bra top strap near shoulder naturally. Light gray matching loose training shorts, drawstring waist. Barefoot. No earrings.
Hair: loose half-up style, top half gathered loosely, some strands framing face.
Background: SP-01 desk area. Cool white work lighting.
Shot: half-body, 3/4 or front. Casual and natural.
Photorealistic.
```

### OC-03 — 크롭 + 레깅스 (O-03)
```
Photorealistic photograph. Korean woman in a tiny studio room.
Outfit: mint green ribbed crop short-sleeve top — shows midriff (~3cm above waist). Thin bralette strap in matching or neutral color visible at shoulder naturally. Black 7/8 tight leggings, thick elastic waistband. White ankle socks.
Hair: high neat bun secured with black cushion hair clip. No bangs. Small round silver stud earrings.
Background: SP-02 bed area or open floor space. Daylight from window.
Shot: full body or 3/4 length, front-facing.
Photorealistic.
```

### OC-04 — 니트 + 와이드팬츠 (O-04)
```
Photorealistic photograph. Korean woman in a tiny studio room.
Outfit: oversized ivory/cream chunky knit sweater, wide boat neckline — loose boat neck naturally slips slightly off one shoulder revealing a bralette strap (not emphasized). Long sleeves past wrists. Beige wide-leg cotton trousers, elastic waist, ankle-length. Thick white ankle socks. No earrings.
Hair: long dark black hair down naturally, soft waves. No accessories.
Background: SP-02 bed area or SP-03 dining table. Warm ambient light.
Shot: upper body to full body, relaxed natural pose.
Photorealistic, cozy and warm feel.
```

### OC-05 — 민소매 + 숏팬츠 (O-05)
```
Photorealistic photograph. Korean woman in a tiny studio room.
Outfit: white slim-fit sleeveless tank top, two thin spaghetti straps — white or nude bra strap naturally visible alongside tank straps on both shoulders. Light sky blue cotton short shorts, elastic waist, slightly frayed hem. Barefoot. No earrings. One delicate thin white thread bracelet on wrist.
Hair: low side ponytail, beige fabric hair tie.
Background: SP-01 desk area with natural window light (daytime).
Shot: upper body or 3/4, slight high angle.
Photorealistic, summer casual feel.
```

### OC-06 — 오버핏 셔츠 (O-06)
```
Photorealistic photograph. Korean woman in a tiny studio room.
Outfit: oversized pastel lavender button-up shirt — only top 2 buttons fastened, open below. Open V neckline naturally reveals top edge of white or lavender bralette (not emphasized). Shirt hem to mid-thigh. Black mini shorts with elastic waist, just visible below hem. Barefoot. Small crescent moon silver earrings.
Hair: half-up style with two small silver clips pinning front sections back.
Background: SP-03 kitchen/dining or SP-04 full room. Warm afternoon light.
Shot: full body or 3/4, relaxed and natural.
Photorealistic.
```

### OC-07 — 잠옷 A — 긴소매 세트 (O-07)
```
Photorealistic photograph. Korean woman in a tiny studio bedroom.
Outfit: light lavender/lilac long-sleeve pajama set — pullover top with shallow V-neck that naturally reveals upper chest skin and faint top edge of soft bralette (no emphasis). Loose silhouette. Matching lavender long pajama pants, ankle length. Barefoot. No earrings.
Hair: long dark black hair loosely down, slightly disheveled and natural, as if relaxed at night or just woken up.
Background: SP-02 bed area. Warm amber mood lamp glow.
Shot: sitting on bed edge or standing near bed. Upper body or 3/4 length.
Photorealistic, soft and cozy feel.
```

### OC-08 — 잠옷 B — 민소매 숏 세트 (O-08)
```
Photorealistic photograph. Korean woman in a tiny studio bedroom.
Outfit: white pajama camisole top, thin spaghetti straps, subtle small cherry print in light pink, shallow square neckline. Bra strap naturally visible beside camisole strap on shoulder (no intentional emphasis). Matching white cherry-print loose pajama shorts, mid-thigh length. Barefoot. No earrings. Pink fabric scrunchie on wrist.
Hair: long dark black hair loosely down or messy half-up style.
Background: SP-02 bed area. Warm amber mood lamp.
Shot: sitting on bed, upper body, natural morning or night feel.
Photorealistic, soft and casual.
```

### OC-09 — 욕실 가운 (O-09)
```
Photorealistic photograph. Korean woman in a tiny studio room, near bathroom door or desk edge.
Outfit: white terry cotton bathrobe, knee-length (just above knee), short 3/4 sleeves, loosely tied with fabric belt at waist. V-opening at chest naturally shows collarbone, upper chest skin — no intentional exposure, just natural robe opening. Bare legs below knee. Barefoot or white slip-on slippers. No earrings.
Hair: white towel wrapped as turban on head OR damp dark hair falling loose with slight wet texture.
Skin: slightly flushed cheeks, warm skin tone as if just after shower. Natural dewy texture.
Background: SP-04 or near SP-03 kitchen area. Warm lighting.
Shot: upper body to 3/4, standing. No close-up of any specific area.
Photorealistic. Tasteful, no emphasis on chest.
```

### OC-10 — 수건 착장 (O-10)
```
Photorealistic photograph. Korean woman in a tiny studio room, near bed or bathroom doorway.
Outfit: one large white bath towel wrapped from under the arms to mid-thigh. Towel upper edge is above the chest line. Shoulders, collarbones, neck, and upper arms fully visible. Bare legs from mid-thigh down. Barefoot. No earrings. No accessories.
Hair: long dark black hair wet and naturally falling loose — darker and sleeker than usual due to water, slightly separated strands.
Skin: slightly flushed and dewy from shower.
Background: SP-02 bed area or near bathroom doorway. Warm ambient light.
Shot: upper body, 3/4 angle or front, natural and candid. No close-up of any body part. Subject-centered composition.
Photorealistic. Tasteful and natural, no emphasis on any specific area.
```

### OC-11 — 맨투맨 + 와이드팬츠 (O-11)
```
Photorealistic photograph. Korean woman in a tiny studio room.
Outfit: oversized oatmeal or light beige crewneck sweatshirt (no hood), thick French terry fabric, long sleeves with ribbed cuffs. Slightly worn-out neckline naturally reveals thin white or skin-tone bra top strap near shoulder. Length falls to hip. Dark gray wide-leg cotton trousers, elastic waist, ankle length. Thick white ankle socks. No earrings.
Hair: long dark black hair loosely down, naturally flowing.
Background: SP-02 bed area or SP-03 dining table. Warm ambient evening light.
Shot: upper body to 3/4 length, relaxed natural pose.
Photorealistic.
```

### OC-12 — 민소매 + 미니 스커트 (O-12)
```
Photorealistic photograph. Korean woman in a tiny studio room.
Outfit: white ribbed fitted sleeveless crop top, two thin spaghetti straps — slightly cropped above waist. Light beige bra strap naturally visible alongside thin top straps on both shoulders. Light cream or ivory linen mini skirt, elastic waistband, A-line, hem at mid-thigh. Barefoot. Small gold ball stud earrings.
Hair: loose half-up style, a few strands framing the face. Small cream satin ribbon hair tie.
Background: SP-01 desk area with natural window daylight, or SP-04 wide room view.
Shot: upper body or full body, front-facing or slight high angle. Summer casual feel.
Photorealistic.
```

### OC-13 — 크롭 스웨트 + 레깅스 (O-13)
```
Photorealistic photograph. Korean woman in a tiny studio room.
Outfit: light gray or soft lavender cropped crewneck sweatshirt (no hood) — hem ~3-4cm above navel, showing midriff. Slightly oversized at shoulders. Bralette strap naturally visible near shoulder. Dark navy or black full-length tight leggings, thick waistband. White ankle socks. No earrings.
Hair: high neat ponytail, black elastic.
Background: SP-01 desk area or SP-04 full room. Daylight or cool work lighting.
Shot: full body or 3/4, front-facing or slight angle.
Photorealistic.
```

---

## 실제 장면 생성 방식 (2단계)

OC 이미지 1장 + F 이미지 1장을 reference input으로 넣고 아래 텍스트 프롬프트 추가.

```
[행동] 중에서 1개 선택:
코딩 중 / 기지개 켜기 / 턱 괴기 / 밥 먹는 중 / 커피 들기 /
누워있기 / 폰 보기 / 요리 중 / 엎드려 있음

[표정] 중에서 1개:
중립 / 미소 / 집중 / 피곤함 / 귀여운 무표정 / 살짝 웃음 / 졸린 표정

[촬영 방식] 중에서 1개:
셀카 느낌 (handheld front camera) / 정면 / 반 측면 / 위에서 / 약간 아래에서

[안경]:
안경 없음 / 안경 착용 (작업 집중 중 빈도 높음, 취침/욕실 착장은 없음)

[조명] (공간별 고정):
작업 중 → cool white monitor glow + desk lamp
수면/취침 전 → warm amber mood lamp
새벽 야작 → only monitor light, dark room
낮 → natural window light
```

---

## 생성 순서 체크리스트

### 1단계 — 얼굴 레퍼런스
- [x] F-01 정면 중립 (안경 없음)
- [x] F-02 정면 미소 (안경 없음)
- [x] F-03 3/4 측면 (안경 없음)
- [x] F-04 옆 프로필 (안경 없음)
- [x] F-05 정면 중립 (안경 착용)
- [x] F-06 정면 미소 (안경 착용)

### 1단계 — 공간 레퍼런스 (인물 없음)
- [x] SP-01 컴퓨터 데스크
- [x] SP-02 침대
- [x] SP-03 식탁/주방
- [x] SP-04 전체 광각

### 2단계 — 착장 레퍼런스 (F 완료 후)
- [x] OC-01 기본 작업복
- [x] OC-02 후디 작업복
- [x] OC-03 크롭+레깅스
- [x] OC-04 니트+와이드팬츠
- [x] OC-05 민소매+숏팬츠
- [x] OC-06 오버핏 셔츠
- [x] OC-07 잠옷 A (긴소매)
- [x] OC-08 잠옷 B (민소매)
- [x] OC-09 욕실 가운
- [x] OC-10 수건 착장
- [x] OC-11 맨투맨+와이드팬츠
- [x] OC-12 민소매+미니 스커트
- [x] OC-13 크롭 스웨트+레깅스

**총 23장 (기본 세트) + OC 세트당 3종 변주 = 39장**

---

## 생성 완료 리소스 경로

**기본 경로**: `/Users/kein/Projects/woong-bb/working/eunbi/meta_references/generated/v2/`

### 얼굴 레퍼런스 (faces/)
```
F-01_front_neutral_no_glasses.png
F-02_front_smile_no_glasses.png
F-03_three_quarter_no_glasses.png
F-04_side_profile_no_glasses.png
F-05_front_neutral_glasses.png
F-06_front_smile_glasses.png
```

### 공간 레퍼런스 (spaces/)
```
SP-01_desk_area.png
SP-02_bed_area.png
SP-03_dining_kitchen.png
SP-04_room_wide.png
```

### 착장 레퍼런스 (outfits/) — 세트당 3종 변주
각 OC 세트는 `OC-XX-01`, `OC-XX-02`, `OC-XX-03` 3종으로 구성. 실제 장면 생성 시 1장 선택해서 사용.

| 세트 | 01 | 02 | 03 |
|---|---|---|---|
| OC-01 기본 작업복 | 흰 티 | 회색 티(연) | 회색 티(진) |
| OC-02 후디 작업복 | 회색 후디 | 변주 | 변주 |
| OC-03 크롭+레깅스 | 변주1 | 변주2 | 변주3 |
| OC-04~13 | 변주1 | 변주2 | 변주3 |

**파일명 패턴**: `OC-{번호}-{01~03}_{영문이름}.png`
