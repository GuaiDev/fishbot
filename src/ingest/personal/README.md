# src/ingest/personal/

Adapters for the user's own data exports.

Planned modules:
- `trip_import.py` — bulk import from CSV/GPX
- `photo_ingest.py` — extract EXIF metadata from your own fishing photos
- `sonar.py` — parse GPX/sonar logs from Lowrance, Garmin, Humminbird

This is YOUR data. These adapters are the one place in the codebase where
personally-identifying information is intentionally processed. Nothing here
should be shared or exported beyond the local database.
