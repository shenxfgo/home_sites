# Tasks 4-7 Report: Database Models

## Status: DONE

## Commits

| Task | Commit Hash | Message |
|------|------------|---------|
| Task 4 | `6a0052f` | feat: add VideoSource model |
| Task 5 | `b7269b6` | feat: add Video model with source relationship |
| Task 6 | `0a405e2` | feat: add Tag model with many-to-many video relationship |
| Task 7 | `ba9bfb1` | feat: add remaining database models (history, favorites, notifications, new_videos, subtitles) |

## Created Files

**Model files (backend/src/models/):**
- `backend/src/models/__init__.py` - Package exports
- `backend/src/models/source.py` - VideoSource model
- `backend/src/models/video.py` - Video model with source relationship
- `backend/src/models/tag.py` - Tag model and video_tags association table
- `backend/src/models/history.py` - PlayHistory model
- `backend/src/models/favorite.py` - Favorite model
- `backend/src/models/notification.py` - Notification model
- `backend/src/models/new_video.py` - NewVideo model
- `backend/src/models/subtitle.py` - Subtitle model

**Test files (backend/tests/test_models/):**
- `backend/tests/test_models/__init__.py` - Test package init
- `backend/tests/test_models/conftest.py` - Test fixtures (in-memory DB)
- `backend/tests/test_models/test_source.py` - VideoSource tests
- `backend/tests/test_models/test_video.py` - Video tests
- `backend/tests/test_models/test_tag.py` - Tag/VideoTag tests
- `backend/tests/test_models/test_history.py` - PlayHistory tests
- `backend/tests/test_models/test_favorite.py` - Favorite tests
- `backend/tests/test_models/test_notification.py` - Notification tests
- `backend/tests/test_models/test_new_video.py` - NewVideo tests
- `backend/tests/test_models/test_subtitle.py` - Subtitle tests

## Test Summary

All 11/11 tests pass:
- test_source.py: 2/2 passed
- test_video.py: 2/2 passed
- test_tag.py: 2/2 passed
- test_history.py: 1/1 passed
- test_favorite.py: 1/1 passed
- test_notification.py: 1/1 passed
- test_new_video.py: 1/1 passed
- test_subtitle.py: 1/1 passed

## Deviations from Plan

1. **Test isolation**: Tests use an in-memory SQLite database via a `db_session` fixture (in `conftest.py`) rather than the production `async_session_maker`. This provides proper test isolation -- each test gets a fresh database.

2. **Type validation**: Added a `CheckConstraint` on `VideoSource.type` to enforce valid values ('local', 'nas', 'minio') as required by the `test_video_source_type_validation` test. The plan's model code only had a comment but no actual constraint.

3. **Async session compatibility**: Added `lazy="selectin"` to the `Video.tags` and `Tag.videos` relationships to work correctly with async sessions. The default lazy loading strategy causes `MissingGreenlet` errors with async SQLAlchemy sessions.

## Issues

None. All tasks completed successfully with all tests passing.
