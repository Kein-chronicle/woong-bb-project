# Automation Modules

`automation_worker.py` is the process entrypoint. Shared pieces live here so the worker does not keep growing as one file.

- `io.py`: JSON, JSONL, and timestamp helpers.
- `runtime_state.py`: singleton lock, health, supervisor, and control-plane state.
- `telegram_io.py`: Telegram text/voice delivery and outgoing message logging.
- `event_triggers.py`: event-trigger promise parsing and activity transition mapping.
- `conversation_guard.py`: recent-message loading and proactive conversation guard calculation.
- `diary.py`: daily diary summarization and file writing.
