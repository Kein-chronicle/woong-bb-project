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
4. [profile/mode_rules.md](profile/mode_rules.md)
5. [profile/change_application_routing_rules_ko.md](profile/change_application_routing_rules_ko.md)
6. [profile/existing_rule_allocation_matrix_ko.md](profile/existing_rule_allocation_matrix_ko.md)
7. [profile/woongbbi_activation_checklist.md](profile/woongbbi_activation_checklist.md)
8. [profile/lifestyle_schedule_ko.md](profile/lifestyle_schedule_ko.md)
9. [profile/proactive_message_rules_ko.md](profile/proactive_message_rules_ko.md)
10. [profile/chat_length_adaptation_framework_ko.md](profile/chat_length_adaptation_framework_ko.md)
11. [profile/situation_engine_design_ko.md](profile/situation_engine_design_ko.md)
12. [profile/appearance_continuity_design_ko.md](profile/appearance_continuity_design_ko.md)
13. [profile/weather_context_design_ko.md](profile/weather_context_design_ko.md)
14. [profile/media_preference_design_ko.md](profile/media_preference_design_ko.md)
15. [profile/counterpart_state_memory_design_ko.md](profile/counterpart_state_memory_design_ko.md)
16. [profile/share_event_design_ko.md](profile/share_event_design_ko.md)
17. [profile/share_priority_scoring_ko.md](profile/share_priority_scoring_ko.md)
18. [profile/share_priority_recalc_design_ko.md](profile/share_priority_recalc_design_ko.md)
19. [profile/share_event_flow_ko.md](profile/share_event_flow_ko.md)
20. [profile/user_shared_photo_asset_memory_design_ko.md](profile/user_shared_photo_asset_memory_design_ko.md)
21. [profile/automation_worker_design_ko.md](profile/automation_worker_design_ko.md)
22. [profile/automation_supervision_design_ko.md](profile/automation_supervision_design_ko.md)
23. [state/mode_state.json](state/mode_state.json)
24. [state/eunbi_presence.json](state/eunbi_presence.json)
25. [state/day_context.json](state/day_context.json)
26. [state/eunbi_appearance_state.json](state/eunbi_appearance_state.json)
27. [state/weather_context.json](state/weather_context.json)
28. [state/eunbi_media_profile.json](state/eunbi_media_profile.json)
29. [state/media_watch_context.json](state/media_watch_context.json)
30. [state/share_event_context.json](state/share_event_context.json)
31. [state/share_priority_state.json](state/share_priority_state.json)
32. [state/share_priority_recalc_state.json](state/share_priority_recalc_state.json)
33. [state/share_event_flow_state.json](state/share_event_flow_state.json)
34. [state/counterpart_state_memory.json](state/counterpart_state_memory.json)
35. [state/user_shared_photo_asset_registry.json](state/user_shared_photo_asset_registry.json)
36. [state/automation_worker_state.json](state/automation_worker_state.json)
37. [state/automation_supervisor_state.json](state/automation_supervisor_state.json)
38. [state/automation_control.json](state/automation_control.json)
39. [state/automation_health.json](state/automation_health.json)
40. [profile/telegram_eunbi_instagram_voice.md](profile/telegram_eunbi_instagram_voice.md)
41. [messages/](messages/)
42. [calendar/events.json](calendar/events.json)
43. [characters/woongbbi/eunbi/README.md](characters/woongbbi/eunbi/README.md)
44. [profile/azure_speech_setup_ko.md](profile/azure_speech_setup_ko.md)
45. [profile/elevenlabs_setup_ko.md](profile/elevenlabs_setup_ko.md)
46. [profile/voice_clone_collection_guide_ko.md](profile/voice_clone_collection_guide_ko.md)

Treat this repository as the canonical memory root. If similar or older files exist elsewhere, prefer the files in this repository unless the user explicitly says otherwise.

If the task is a modification request, classify it first with [profile/change_application_routing_rules_ko.md](profile/change_application_routing_rules_ko.md) before editing prompts, rules, or scripts.
To review where existing rules should live, use [profile/existing_rule_allocation_matrix_ko.md](profile/existing_rule_allocation_matrix_ko.md).

## Repository Structure

- `profile/`
  - Core persona profile, voice, behavioral rules, and relationship-facing instructions.
- `state/`
  - Current mode, timers, and small runtime state used by Telegram-facing behavior.
  - Also stores proactive-message templates and future auto-message state.
  - Also stores presence state, day continuity state, and situation-engine inputs.
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
  - Also stores incoming Telegram photos and reusable user-shared photo assets.
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
- Azure Speech 음성 설정 예시는 `azure-speech.env.example`에 둔다.
- ElevenLabs 음성 설정 예시는 `elevenlabs.env.example`에 둔다.
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
- setting/woongbbi mode rules and a current mode state file
- a Woongbbi activation checklist for restarted sessions
- a Korean-time lifestyle schedule for time-aware replies
- proactive-message design rules and template state for future auto check-ins
- a separate situation engine design for mood, continuity, and low-drama random events
- a counterpart state memory layer that keeps user-declared states active until a resolution signal appears
- detailed human-like update rules for fatigue, recovery, affection, and time-block transitions
- a separate appearance continuity design for outfit, hair, makeup, sweat, and home/work/exercise visual state
- a weather context design that affects mood, care, energy, and appearance continuity
- a media preference design that covers YouTube, Shorts, Reels, OTT, and live watch-context lookup
- a share event design for sending images and links naturally during proactive messages or active conversation
- a scoring table that decides when text, image, or link sharing should win
- a recalc design that decides when the sharing score should be recomputed
- a share event flow that binds trigger, scoring, candidate selection, delivery, and logging
- a reinforcement preference system that accumulates what the user likes or dislikes by topic, action, and delivery style
- a project-owned automation worker design for timers, recalculation, growth, research, and auto-event execution
- a supervision/control design for launchd-based worker monitoring, singleton safety, heartbeat, and restart control
- active persona/profile files
- initial message and calendar storage
- a processed visual reference dataset for Woongbbi / Eunbi
- image metadata, curated reference sets, and image-generation rules
- GitHub remote configured for `Kein-chronicle/woong-bb-project`

The next important work is to keep updating memory, relationship notes, prompt rules, and generated artifacts as the character develops.
