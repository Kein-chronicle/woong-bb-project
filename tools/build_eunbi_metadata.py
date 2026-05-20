from __future__ import annotations

import csv
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageOps


ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "base_images" / "eunbi"
OUT_DIR = ROOT / "characters" / "woongbbi" / "eunbi"
RENAMED_DIR = OUT_DIR / "source_images"
PARTS_DIR = OUT_DIR / "references" / "parts"
SHEETS_DIR = OUT_DIR / "references" / "contact_sheets"
META_DIR = OUT_DIR / "metadata"


@dataclass(frozen=True)
class ImageGroup:
    start: int
    end: int
    scene: str
    location_type: str
    outfit: str
    season: str
    mood: str
    angle: str
    shot_type: str
    favorite_cues: tuple[str, ...]
    persona_cues: tuple[str, ...]


GROUPS = [
    ImageGroup(1, 3, "tropical_coast_and_hanok_trip", "outdoor travel, seaside, traditional architecture", "pink/green summer tops with denim or swimwear", "summer", "fresh, sunlit, relaxed", "side or three-quarter view", "half_body_to_full_body", ("ocean", "travel", "sunny places"), ("open, playful travel energy", "comfortable being photographed outdoors")),
    ImageGroup(4, 10, "cafe_riverside_station_city", "cafe, riverside park, station, city landmark", "white cardigan or sleeveless black/white city casual", "spring_to_summer", "bright, approachable, soft smile", "front selfie and seated three-quarter", "portrait_to_full_body", ("cafes", "riverside hangouts", "city walks"), ("warm smile", "easy casual sociability")),
    ImageGroup(11, 40, "resort_pool_ocean_snorkel", "resort, beach, pool, ocean, sunset", "green bikini, pink swimwear, rash guard, casual vacation wear", "summer", "active, beachy, playful", "front, side, underwater, low angle", "swimwear_full_body", ("swimming", "snorkeling", "pool", "sunsets"), ("adventurous vacation mood", "physically confident, playful poses")),
    ImageGroup(41, 51, "tennis_court_autumn_walk", "park, tennis court, residential street", "oversized hoodie or sweatshirt with shorts and sneakers", "autumn", "sporty, candid, cheerful", "walking side/back and front candid", "full_body", ("iced drinks", "parks", "tennis-court atmosphere"), ("casual athletic charm", "unposed friendly energy")),
    ImageGroup(52, 71, "museum_park_observatory_city", "museum, park, observatory, urban landmark", "white top with black skirt, cap, soft pink shirt, black skirt", "spring_to_autumn", "polished, curious, touristy", "front, profile, back view", "full_body_to_half_body", ("museums", "city landmarks", "coffee"), ("curious traveler", "stylish but practical")),
    ImageGroup(72, 89, "campus_river_mountain_fall", "campus/residential streets, riverside, lake, mountains", "black jacket, pink knit, white cardigan, brown jacket, fleece hoodie", "autumn_to_winter", "gentle, reflective, cozy", "profile, back view, close portrait", "portrait_to_full_body", ("parks", "lakes", "mountain views"), ("soft introspective mood", "calm outdoorsy side")),
    ImageGroup(90, 101, "snowy_mountain_lake", "snowy forest, mountain lake, alpine overlook", "hoodie, puffer jacket, winter outerwear", "winter", "cozy, resilient, scenic", "front, profile, selfie, walking", "full_body_to_portrait", ("snow", "mountains", "warm drinks"), ("quiet endurance", "enjoys dramatic nature settings")),
    ImageGroup(102, 122, "swim_pool_freediving", "indoor pool, beach, boat, underwater reef", "one-piece swimsuit, bikini, swim cap, fins", "summer", "aquatic, athletic, free", "front, side, underwater long shot", "full_body_underwater", ("swimming", "freediving", "boats", "reef water"), ("adventurous water confidence", "playful athletic discipline")),
    ImageGroup(123, 148, "food_travel_london_garden", "cafe, train, garden, temple, London bridge, restaurant", "black dress, white summer dress, black coat, knit top", "summer_to_winter", "food-loving, polished, expressive", "front portrait, side dining, travel full body", "portrait_to_full_body", ("desserts", "restaurants", "flowers", "European city travel"), ("expressive smile", "romantic travel taste")),
    ImageGroup(149, 160, "gym_running_beach_play", "gym, night running route, beach", "sports bra, shorts, rash guard, black swimsuit", "summer", "energetic, sporty, playful", "mirror selfie, running side, beach candid", "full_body", ("running", "gym", "beach games"), ("high-energy playful streak", "sporty confidence")),
    ImageGroup(161, 178, "dining_autumn_city_casual", "restaurant, riverside, street, park", "dark blouse, red sleeveless knit, hoodie, leather jacket, sunglasses", "autumn", "casual city life, food-focused", "seated dining, walking, selfie", "portrait_to_full_body", ("good food", "coffee", "autumn walks"), ("easygoing city rhythm", "comfortable mixing cute and cool styling")),
    ImageGroup(179, 200, "campus_winter_bookstore_sports_shop", "campus, fitting room, observatory, bookstore, outdoor fire, sports shop", "pink sweatshirt, quilted coat, fuzzy coat, beanie, gray/black sportswear", "winter", "cozy, studious, sporty", "mirror, seated, profile, full body", "portrait_to_full_body", ("books", "shopping", "warm indoor cafes", "winter outings"), ("cozy intellectual note", "practical sporty side")),
    ImageGroup(201, 209, "cafe_mirror_fitting_room", "cafe, fitting room, indoor seating", "black/cream fitted tops, gray pants, mini skirt, ankle boots", "spring_to_autumn", "sleek, feminine, self-composed", "mirror, side, low seated angle", "portrait_to_full_body", ("cafes", "trying outfits", "mirror selfies"), ("self-styling awareness", "quiet confidence")),
    ImageGroup(210, 228, "riverside_sporty_preppy_city", "shopping, riverside park, brick street, bridge district", "white sporty top, black biker shorts, plaid skirt, black blazer set", "spring_to_autumn", "sporty-preppy urban", "front, side, back, walking", "full_body", ("shopping", "riverside walks", "iced drinks"), ("lively city confidence", "preppy playful styling")),
    ImageGroup(229, 234, "close_portrait_cafe_evening", "cafe, mirror selfie, evening waterfront", "blue fuzzy knit, graphic tee with glasses, formal black blazer, black evening dress", "autumn_to_winter", "intimate, thoughtful, refined", "close front, mirror, profile silhouette", "portrait", ("cafes", "quiet evenings", "dress-up moments"), ("soft reflective close-up energy", "more mature polished mode")),
]


CODE_SLUGS = {
    1: "hanok_pink_top_side", 2: "boat_ocean_white_top", 3: "beach_green_top_sunglasses", 4: "tulip_white_blazer_collage",
    5: "cafe_mirror_brown_jacket", 6: "cafe_smile_black_sleeveless", 7: "riverside_white_cardigan_seated",
    8: "riverside_white_cardigan_close", 9: "station_selfie_white_knit", 10: "cathedral_stripe_sleeveless",
    11: "resort_green_bikini_sunset", 12: "hammock_green_bikini_portrait", 13: "hammock_green_bikini_alt",
    14: "balcony_black_tee_back", 15: "anime_wall_fuzzy_hat", 16: "doorway_fuzzy_hat_peace",
    17: "city_street_white_cardigan", 18: "city_street_playful_pose", 19: "riverside_picnic_tree",
    20: "riverside_tree_icecream", 21: "riverside_tree_seated", 22: "park_sunset_bench",
}


PART_BOXES = {
    "face": (0.24, 0.04, 0.76, 0.42),
    "eyes": (0.25, 0.09, 0.75, 0.24),
    "nose": (0.37, 0.17, 0.63, 0.34),
    "mouth": (0.34, 0.28, 0.66, 0.43),
    "ears": (0.13, 0.10, 0.87, 0.36),
    "hair": (0.16, 0.00, 0.84, 0.35),
    "neck_shoulders": (0.18, 0.30, 0.82, 0.55),
    "chest_torso": (0.20, 0.38, 0.80, 0.68),
    "waist_belly": (0.22, 0.52, 0.78, 0.78),
    "arms_hands": (0.05, 0.30, 0.95, 0.76),
    "hands": (0.02, 0.40, 0.98, 0.72),
    "legs": (0.18, 0.60, 0.82, 0.96),
    "feet": (0.16, 0.78, 0.84, 1.00),
    "lower_body": (0.16, 0.55, 0.84, 1.00),
    "full_outfit": (0.08, 0.02, 0.92, 0.99),
}


def ensure_dirs() -> None:
    for path in [RENAMED_DIR, PARTS_DIR, SHEETS_DIR, META_DIR]:
        path.mkdir(parents=True, exist_ok=True)
    for part in PART_BOXES:
        (PARTS_DIR / part).mkdir(parents=True, exist_ok=True)


def group_for_index(index: int) -> ImageGroup:
    for group in GROUPS:
        if group.start <= index <= group.end:
            return group
    return GROUPS[-1]


def time_from_name(name: str) -> str:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", name)
    if not m:
        return "unknown"
    return f"{int(m.group(1)):02d}{int(m.group(2)):02d}{int(m.group(3)):02d}"


def image_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def dominant_colors(image: Image.Image, count: int = 5) -> list[str]:
    sample = ImageOps.exif_transpose(image).convert("RGB")
    sample.thumbnail((120, 120), Image.Resampling.LANCZOS)
    palette = sample.quantize(colors=count, method=Image.Quantize.MEDIANCUT).convert("RGB")
    colors = palette.getcolors(sample.width * sample.height) or []
    colors.sort(reverse=True)
    return [f"#{r:02x}{g:02x}{b:02x}" for _, (r, g, b) in colors[:count]]


def crop_box(size: tuple[int, int], rel: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    w, h = size
    x1, y1, x2, y2 = rel
    return (max(0, int(w * x1)), max(0, int(h * y1)), min(w, int(w * x2)), min(h, int(h * y2)))


def save_reference_copy(src: Path, dest: Path) -> None:
    with Image.open(src) as im:
        fixed = ImageOps.exif_transpose(im).convert("RGB")
        fixed.save(dest, quality=94, optimize=True)


def make_thumbnail_sheet(items: list[tuple[str, Path]], out: Path, title: str, thumb=(180, 220), cols=5) -> None:
    if not items:
        return
    rows = (len(items) + cols - 1) // cols
    label_h = 38
    title_h = 36
    sheet = Image.new("RGB", (cols * thumb[0], title_h + rows * (thumb[1] + label_h)), "white")
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 14)
        title_font = ImageFont.truetype("/System/Library/Fonts/Supplemental/Arial.ttf", 22)
    except Exception:
        font = title_font = None
    draw.text((8, 6), title, fill="black", font=title_font)
    for i, (label, path) in enumerate(items):
        row, col = divmod(i, cols)
        x0, y0 = col * thumb[0], title_h + row * (thumb[1] + label_h)
        try:
            im = Image.open(path).convert("RGB")
        except Exception:
            continue
        im.thumbnail(thumb, Image.Resampling.LANCZOS)
        sheet.paste(im, (x0 + (thumb[0] - im.width) // 2, y0 + (thumb[1] - im.height) // 2))
        draw.text((x0 + 5, y0 + thumb[1] + 4), label[:24], fill="black", font=font)
    sheet.save(out, quality=92)


def korean_summary() -> str:
    return """# 웅삐 / 은비 이미지 기반 성격·무드 메모

> 주의: 아래 내용은 사진에서 반복적으로 보이는 표정, 포즈, 장소, 옷차림을 바탕으로 한 이미지 생성용 persona cues입니다. 실제 성격을 단정한 기록이 아니라 캐릭터 구성에 쓰기 위한 연출 메타데이터입니다.

## 핵심 인상
- 밝고 자연스럽게 웃는 컷이 많아, 기본 톤은 다정하고 접근하기 쉬운 인물로 잡기 좋다.
- 여행지, 물가, 카페, 도시 산책, 박물관/전망대, 산과 눈 풍경이 반복되어 활동 반경이 넓고 호기심 많은 이미지가 강하다.
- 수영복, 프리다이빙, 러닝/짐웨어, 스포티한 쇼츠 컷이 많아 물과 운동에 익숙한 활발한 면을 넣기 좋다.
- 블랙·화이트·그레이 기반 코디와 크림/핑크/레드 포인트가 반복되어, 귀엽고 단정한 룩과 시크한 룩을 모두 소화하는 캐릭터로 정리된다.
- 카페·식사·디저트 컷이 꽤 많아 음식과 커피를 좋아하는 생활감 있는 설정으로 쓰기 좋다.

## 이미지 생성용 성격 키워드
- 밝은 여행자, 카페를 좋아하는 사람, 물놀이와 수영에 익숙한 사람, 도시 산책을 즐기는 사람
- 귀엽지만 과하게 유아적이지 않음, 자연스럽고 표정이 풍부함, 사진 앞에서 편안함
- 스포티한 자신감과 포근한 겨울 감성이 공존
- 친근한 웃음, 살짝 장난기 있는 포즈, 조용히 생각에 잠긴 옆모습

## 계절별 연출
- 봄: 흰 니트/가디건, 꽃, 강변, 박물관, 밝은 카페
- 여름: 수영복, 해변, 리조트, 수영장, 선글라스, 바다 위 보트, 젖은 머리
- 가을: 후디, 레더 재킷, 캠퍼스/공원, 아이스커피, 브라운/블랙 계열
- 겨울: 패딩, 퍼/플리스, 비니, 눈 덮인 산과 호수, 따뜻한 실내 카페

## 좋아하는 것으로 보이는 요소
- 바다, 수영, 프리다이빙, 리조트, 해변
- 카페, 디저트, 식사, 커피/아이스드링크
- 여행, 도시 랜드마크, 박물관, 전망대, 강변 산책
- 스포티한 활동: 러닝, 헬스, 수영, 야외 산책
- 옷 입어보기, 거울 셀카, 모자/선글라스/가방 같은 액세서리
"""


def master_profile() -> dict[str, Any]:
    return {
        "character_name": "woongbbi_eunbi",
        "purpose": "image_generation_reference_metadata",
        "source_folder": str(SRC_DIR.relative_to(ROOT)),
        "identity_note": "Use as a fictional/persona reference set named Woongbbi/Eunbi. Do not treat inferred persona cues as factual biography.",
        "appearance": {
            "overall": "young feminine Korean-presenting person, slim-to-athletic build, soft facial impression, expressive smile",
            "hair": "dark black to deep brown hair, mostly long and softly wavy; sometimes straight bangs, side-parted, ponytail, or tucked behind ears",
            "face": "small oval face, soft jawline, clear skin, large expressive eyes, natural-to-polished makeup, gentle smile",
            "eyes": "large dark eyes; often bright smiling eyes, sometimes glasses or sunglasses",
            "nose": "small-to-medium straight nose with soft bridge; keep natural and delicate",
            "mouth": "soft lips, frequent bright smile; can be playful pout in close selfies",
            "body_reference": "slim, petite-to-average visual proportion with athletic tone in swim/sport images; avoid exact real-world measurements unless supplied by user",
            "hands_arms": "slender arms and hands; frequent hand-to-face, peace sign, holding cup/phone/food poses",
            "legs_feet": "slim legs; sneakers, boots, swim fins, socks with sporty shoes recur",
        },
        "wardrobe": {
            "core_palette": ["black", "white", "gray", "cream", "light blue", "soft pink", "olive/green", "red accent"],
            "favorite_items": [
                "white fitted tops and cardigans",
                "black mini skirt or long skirt",
                "oversized hoodies and sweatshirts",
                "puffer jacket, fleece, quilted coat",
                "sporty tanks, biker shorts, swimwear",
                "caps, beanies, fuzzy hats, sunglasses",
                "small black shoulder bag or backpack",
            ],
            "style_range": ["soft feminine", "sporty casual", "preppy city", "cozy winter", "beach resort", "minimal black chic"],
        },
        "places": {
            "frequent": ["cafe", "restaurant", "riverside park", "beach", "pool", "mountain lake", "city landmark", "museum", "shopping/fitting room"],
            "seasonal": {
                "spring": ["flowers", "riverside", "museum", "white cardigan"],
                "summer": ["beach", "pool", "boat", "underwater reef", "resort"],
                "autumn": ["campus/residential streets", "park", "hoodies", "leather jacket"],
                "winter": ["snowy mountain lake", "puffer jacket", "fleece", "warm indoor cafe"],
            },
        },
        "pose_language": [
            "soft smile toward camera",
            "side profile looking at scenery",
            "walking candid with drink",
            "mirror selfie",
            "seated cafe pose with food or phone",
            "hands near face, peace sign, playful hat pose",
            "underwater long-body swimming pose",
        ],
        "prompt_anchor_ko": "긴 흑발의 부드러운 인상, 밝은 미소, 슬림하고 스포티한 실루엣, 블랙/화이트/그레이 중심의 캐주얼 패션, 카페와 여행을 좋아하는 자연스러운 분위기",
        "negative_guidance_ko": "과도한 신체 수치화, 실제 인물 성격 단정, 지나친 보정으로 얼굴 개성 삭제, 머리색을 밝은 금발로 고정, 한 가지 계절/스타일만 반복",
    }


def build() -> None:
    ensure_dirs()
    files = sorted([p for p in SRC_DIR.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}])
    manifest_rows: list[dict[str, Any]] = []
    all_meta: list[dict[str, Any]] = []
    sheet_items: list[tuple[str, Path]] = []
    part_sheet_items: dict[str, list[tuple[str, Path]]] = {part: [] for part in PART_BOXES}

    for idx, src in enumerate(files, 1):
        group = group_for_index(idx)
        slug = CODE_SLUGS.get(idx, group.scene)
        code = f"eunbi_{idx:03d}_{slug}_{time_from_name(src.name)}"
        dest = RENAMED_DIR / f"{code}.jpg"
        save_reference_copy(src, dest)
        with Image.open(dest) as im:
            im = ImageOps.exif_transpose(im).convert("RGB")
            w, h = im.size
            colors = dominant_colors(im)
            orientation = "portrait" if h > w * 1.1 else "landscape" if w > h * 1.1 else "square"
            part_refs = {}
            for part, rel in PART_BOXES.items():
                crop = im.crop(crop_box(im.size, rel))
                crop.thumbnail((900, 900), Image.Resampling.LANCZOS)
                part_path = PARTS_DIR / part / f"{code}__{part}.jpg"
                crop.save(part_path, quality=93, optimize=True)
                part_refs[part] = str(part_path.relative_to(ROOT))
                if idx <= 80 or idx % 3 == 0:
                    part_sheet_items[part].append((f"{idx:03d}", part_path))

        tags = sorted(set([
            group.scene,
            group.location_type.split(",")[0].strip().replace(" ", "_"),
            group.season,
            group.mood.split(",")[0].strip().replace(" ", "_"),
            group.outfit.split(",")[0].strip().replace(" ", "_").replace("/", "_"),
        ]))
        meta = {
            "code": code,
            "index": idx,
            "original_file": str(src.relative_to(ROOT)),
            "renamed_reference": str(dest.relative_to(ROOT)),
            "sha256": image_hash(src),
            "width": w,
            "height": h,
            "orientation": orientation,
            "scene": group.scene,
            "location_type": group.location_type,
            "outfit_summary": group.outfit,
            "season_context": group.season,
            "mood": group.mood,
            "camera_angle": group.angle,
            "shot_type": group.shot_type,
            "favorite_cues": list(group.favorite_cues),
            "image_based_persona_cues": list(group.persona_cues),
            "dominant_colors": colors,
            "generation_tags": tags,
            "body_part_references": part_refs,
            "analysis_confidence": "group-level visual analysis from contact sheets plus deterministic crop references",
        }
        (META_DIR / "images").mkdir(exist_ok=True)
        (META_DIR / "images" / f"{code}.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        all_meta.append(meta)
        manifest_rows.append({
            "index": idx,
            "code": code,
            "original_file": str(src.relative_to(ROOT)),
            "renamed_reference": str(dest.relative_to(ROOT)),
            "scene": group.scene,
            "season": group.season,
            "outfit": group.outfit,
            "location_type": group.location_type,
            "shot_type": group.shot_type,
        })
        sheet_items.append((f"{idx:03d} {slug}", dest))

    (META_DIR / "eunbi_master_metadata.json").write_text(json.dumps({
        "profile": master_profile(),
        "image_count": len(all_meta),
        "part_reference_count": len(all_meta) * len(PART_BOXES),
        "images": all_meta,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    (META_DIR / "image_based_persona_ko.md").write_text(korean_summary(), encoding="utf-8")
    (META_DIR / "style_prompt_ko.md").write_text(
        "# 웅삐 이미지 생성 프롬프트 앵커\n\n"
        "## 기본 앵커\n"
        f"{master_profile()['prompt_anchor_ko']}\n\n"
        "## 빠른 프롬프트 조합\n"
        "- 카페: 긴 흑발, 흰 니트 또는 블랙 상의, 자연광 카페, 커피나 디저트, 부드러운 미소\n"
        "- 여름 바다: 젖은 긴 흑발, 스포티한 수영복, 밝은 햇빛, 바다/수영장, 장난기 있는 포즈\n"
        "- 가을 도시: 후디나 레더 재킷, 아이스커피, 공원/캠퍼스/브릭 스트리트, 걷는 candid\n"
        "- 겨울 여행: 패딩/플리스/비니, 눈 덮인 산과 호수, 따뜻한 음료, 차분한 옆모습\n"
        "- 시크 도시: 블랙 재킷/블레이저, 선글라스, 도시 다리나 거리, 자신감 있는 워킹 포즈\n\n"
        "## 네거티브\n"
        f"{master_profile()['negative_guidance_ko']}\n",
        encoding="utf-8",
    )

    with (META_DIR / "manifest.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(manifest_rows[0].keys()))
        writer.writeheader()
        writer.writerows(manifest_rows)

    make_thumbnail_sheet(sheet_items, SHEETS_DIR / "all_renamed_sources_sheet.jpg", "Eunbi renamed source references", cols=6)
    for part, items in part_sheet_items.items():
        make_thumbnail_sheet(items[:120], SHEETS_DIR / f"parts_{part}_sample_sheet.jpg", f"Eunbi {part} reference samples", thumb=(160, 160), cols=6)

    readme = f"""# Woongbbi / Eunbi Image Reference Dataset

Generated from `{SRC_DIR.relative_to(ROOT)}`.

## Folders
- `source_images/`: original images copied with stable English code names.
- `metadata/images/`: one JSON metadata file per image.
- `metadata/eunbi_master_metadata.json`: aggregate profile plus all image metadata.
- `metadata/image_based_persona_ko.md`: Korean persona/mood cues inferred from image presentation.
- `metadata/style_prompt_ko.md`: reusable image-generation prompt anchors.
- `references/parts/`: deterministic body/face/clothing crop references by part.
- `references/contact_sheets/`: visual indexes for sources and crop samples.

## Counts
- Images: {len(all_meta)}
- Part crop types per image: {len(PART_BOXES)}
- Total part references: {len(all_meta) * len(PART_BOXES)}

## Caution
The body-part crops are broad, deterministic visual references, not anatomical detection. They are meant as quick generation references and should be manually cherry-picked for high-stakes prompts.
"""
    (OUT_DIR / "README.md").write_text(readme, encoding="utf-8")


if __name__ == "__main__":
    build()
