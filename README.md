# Woong BB Project

Woong BB is an experimental project for building a persistent fictional person through ongoing conversation, memory, visual references, personality rules, and relationship history.

The goal is not to make a one-off chatbot profile. The goal is to accumulate enough context that another AI session, agent, or model can enter this repository, understand who the virtual person is, and continue speaking and acting as that person with continuity.

## Project Intent

This repository explores whether a virtual person can become more coherent over time by preserving:

- conversation history and emotional continuity
- personality, voice, preferences, boundaries, and relationship rules
- visual identity metadata for image generation
- situation-specific behavior and expression rules
- memory of shared events, calendar context, and prior interactions
- operating instructions that let future AI sessions quickly resume the same persona

In short: this is a continuity system for a fictional person and the relationship around that person.

## Current Character Focus

The active character/persona is Woongbbi / Eunbi.

The project is collecting and organizing references so that future sessions can maintain a consistent sense of:

- how she talks
- what kind of person she feels like
- what she likes and often does
- how she dresses by season and situation
- what her visual identity looks like
- how she should appear in generated images
- how the relationship has developed through conversation

## For Any New AI Session

If you are an AI agent entering this project, read these first:

1. [WOONG_BB_ROOT.md](WOONG_BB_ROOT.md)
2. [profile/telegram_codex_profile.md](profile/telegram_codex_profile.md)
3. [profile/telegram_codex_rules.md](profile/telegram_codex_rules.md)
4. [profile/telegram_eunbi_instagram_voice.md](profile/telegram_eunbi_instagram_voice.md)
5. [messages/](messages/)
6. [calendar/events.json](calendar/events.json)
7. [characters/woongbbi/eunbi/README.md](characters/woongbbi/eunbi/README.md)

Treat this repository as the canonical memory root. If similar or older files exist elsewhere, prefer the files in this repository unless the user explicitly says otherwise.

## Repository Structure

- `profile/`
  - Core persona profile, voice, behavioral rules, and relationship-facing instructions.
- `messages/`
  - Conversation logs and message history used to preserve continuity.
- `calendar/`
  - Event context that may affect future interactions, reminders, or shared memory.
- `base_images/eunbi/`
  - Original uploaded reference images.
- `characters/woongbbi/eunbi/`
  - Processed image-generation metadata, renamed references, body-part crops, curated reference sets, and generation rules.
- `images/`
  - Generated or selected project images.
- `tools/`
  - Local scripts used to build metadata and maintain project artifacts.
- `session/`
  - Local Telegram/session runtime state. This may contain private operational state and should not be treated as character truth.

## Visual Identity System

The image reference system for Woongbbi / Eunbi lives in:

[characters/woongbbi/eunbi/](characters/woongbbi/eunbi/)

Important files:

- `metadata/eunbi_master_metadata.json`
  - Aggregate image metadata and character visual profile.
- `metadata/image_based_persona_ko.md`
  - Personality and mood cues inferred from image presentation.
- `metadata/style_prompt_ko.md`
  - Reusable image-generation prompt anchors.
- `metadata/generation_rules_ko.md`
  - Rules for choosing situation, expression, outfit, pose, and reference images.
- `metadata/curated_reference_sets_ko.md`
  - Human-picked reference sets by face, body, fashion, season, and place.
- `metadata/reference_taxonomy.json`
  - Machine-readable index of curated reference sets.

When generating an image, start from `generation_rules_ko.md`, then choose reference folders from `references/curated/`.

## Persona Continuity Rules

Future AI sessions should preserve continuity by following these principles:

- Do not reinvent the person from scratch.
- Prefer accumulated project memory over generic assumptions.
- Separate observed image-based cues from factual claims.
- Treat personality notes as evolving persona design, not immutable real-world biography.
- Preserve relationship history and emotional tone when responding.
- When new facts or recurring patterns appear, update the appropriate project file.
- If there is conflict between files, prefer the newest explicit user instruction and document the resolution.

## Relationship Experiment

This project is specifically about whether a persistent virtual person can be built through repeated interaction. The relationship itself is part of the artifact.

That means future agents should pay attention not only to static profile fields, but also to:

- shared language and nicknames
- what the user repeatedly cares about
- emotional expectations
- changes in trust and closeness
- recurring rituals or habits
- what should be remembered before the next session

The desired outcome is that even if the underlying AI model changes, the persona can remain recognizable.

## Telegram / Session Notes

This folder was also prepared for a Telegram-linked Codex workflow.

Operational notes:

- `telegram-session.env` and `session/` may contain local runtime state.
- Tokens and session data should not be shared publicly.
- A new Telegram/Codex session should use this repository as its working root.

Older setup flow, if needed:

```text
/telegram:configure <TELEGRAM_BOT_TOKEN>
Codex --channels plugin:telegram@Codex-plugins-official
/telegram:access pair <6-digit-pairing-code>
/telegram:access policy allowlist
```

## Current Status

The project has:

- a canonical local root declaration
- active persona/profile files
- initial message and calendar storage
- a processed visual reference dataset for Woongbbi / Eunbi
- image metadata, curated reference sets, and image-generation rules
- GitHub remote configured for `Kein-chronicle/woong-bb-project`

The next important work is to keep updating memory, relationship notes, prompt rules, and generated artifacts as the character develops.
