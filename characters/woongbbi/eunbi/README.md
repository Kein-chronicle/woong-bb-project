# Woongbbi / Eunbi Image Reference Dataset

Generated from `base_images/eunbi`.

## Folders
- `source_images/`: original images copied with stable English code names.
- `metadata/images/`: one JSON metadata file per image.
- `metadata/eunbi_master_metadata.json`: aggregate profile plus all image metadata.
- `metadata/image_based_persona_ko.md`: Korean persona/mood cues inferred from image presentation.
- `metadata/style_prompt_ko.md`: reusable image-generation prompt anchors.
- `metadata/generation_rules_ko.md`: situation, expression, outfit, pose, and reference-selection rules.
- `metadata/curated_reference_sets_ko.md`: human-picked reference sets for face, hair, body, season, fashion, and places.
- `metadata/reference_taxonomy.json`: machine-readable index for the curated sets.
- `references/parts/`: deterministic body/face/clothing crop references by part.
- `references/curated/`: selected source images plus preferred crops for prompt use.
- `references/contact_sheets/`: visual indexes for sources and crop samples.

## Counts
- Images: 234
- Part crop types per image: 15
- Total part references: 3510

## Caution
The body-part crops are broad, deterministic visual references, not anatomical detection. They are meant as quick generation references and should be manually cherry-picked for high-stakes prompts.
