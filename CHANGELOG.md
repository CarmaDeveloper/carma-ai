# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Added `APIKeyHeader` security scheme to enable "Authorize" button in Swagger UI for `Ai-Token`.

### Changed

- **Breaking Change:** Renamed `app/models` directory to `app/schemas` to distinguish Pydantic models from Database models.
- **Breaking Change:** Restructured API routes:
  - Moved all API routers to `app/api/v1/routers/`.
  - Consolidated all business logic endpoints under `/api/v1` prefix using a central router.
  - `health` endpoint remains at root level.
- Refactored `main.py` to use the new V1 router structure and improved lifespan management.
- Updated database initialization logic to correctly handle async table creation.

### Removed

- Removed legacy `ChatbotManagerService` (`app/db/chatbot_manager.py`) in favor of the new Repository pattern.
- Removed unused `chat` API and service files (`app/api/chat.py`, `app/services/chat.py`).
