# Local data workspace

`raw/` stores source extracts exactly as retrieved. `processed/` stores deterministic outputs produced by RecoveryLens.

Both directories are excluded from version control except for placeholders. Public releases will publish small, documented analytical outputs only when source terms, file size, privacy, and reproducibility permit.

Never manually edit a raw source extract.

NOAA Storm Events downloads are stored under `raw/noaa/storm-events/`. The adjacent `manifest.json` records each file's source revision, retrieval timestamp, byte size, and SHA-256 checksum. Existing files without a matching manifest record are intentionally rejected rather than silently trusted or overwritten.

Parsed NOAA damage outputs are written under `processed/noaa/damage/`. They retain raw property and crop strings, explicit parse statuses, event-level known totals, annual summaries, and a JSON diagnostic summary. They can be regenerated from verified raw files and are not committed.
