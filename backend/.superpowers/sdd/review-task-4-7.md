# Review Report: Tasks 4-7 (Database Models)

**Reviewer:** task-reviewer
**Date:** 2026-07-26
**Status:** CONDITIONAL PASS

---

## 1. Scope

Review of database model layer implementation covering:
- SQLAlchemy async base (`src/database/base.py`)
- Session management (`src/database/session.py`)
- 8 ORM models (`src/models/`)
- Associated tests (`tests/test_models/`, `tests/test_database.py`)

---

## 2. Files Under Review

### Source Files
| File | Purpose | Status |
|------|---------|--------|
| `src/database/base.py` | Async declarative base | OK |
| `src/database/session.py` | Engine, session maker, init_db, get_session | OK |
| `src/database/__init__.py` | Package exports | OK |
| `src/models/__init__.py` | Model re-exports | OK |
| `src/models/source.py` | VideoSource model | OK |
| `src/models/video.py` | Video model | OK |
| `src/models/tag.py` | Tag + video_tags association | OK |
| `src/models/history.py` | PlayHistory model | OK |
| `src/models/favorite.py` | Favorite model | OK |
| `src/models/notification.py` | Notification model | OK |
| `src/models/new_video.py` | NewVideo model | OK |
| `src/models/subtitle.py` | Subtitle model | OK |

### Test Files
| File | Tests | Status |
|------|-------|--------|
| `tests/conftest.py` | sys.path setup | OK |
| `tests/test_database.py` | 1 test | PASS |
| `tests/test_models/conftest.py` | db_session fixture | OK |
| `tests/test_models/test_source.py` | 2 tests | PASS |
| `tests/test_models/test_video.py` | 2 tests | PASS |
| `tests/test_models/test_tag.py` | 2 tests | PASS |
| `tests/test_models/test_history.py` | 1 test | PASS |
| `tests/test_models/test_favorite.py` | 1 test | PASS |
| `tests/test_models/test_notification.py` | 1 test | PASS |
| `tests/test_models/test_new_video.py` | 1 test | PASS |
| `tests/test_models/test_subtitle.py` | 1 test | PASS |

---

## 3. Test Results

```
15 passed, 31 warnings in 0.81s
```

All 15 tests pass. 31 warnings are all `DeprecationWarning` for `datetime.utcnow()` (see Issue #1).

---

## 4. Issues Found

### Issue #1 (MEDIUM): `datetime.utcnow()` Deprecation Warning

**Affected files:** All 8 model files (10 occurrences total)

**Problem:** `datetime.utcnow()` is deprecated since Python 3.12 and will be removed in a future version. All models use it as a default value:
```python
default=lambda: datetime.utcnow()
```

**Fix:** Replace with `datetime.now(datetime.UTC)`:
```python
from datetime import datetime, timezone
# ...
default=lambda: datetime.now(timezone.utc)
```

**Priority:** Medium -- currently produces deprecation warnings; will break on future Python versions.

---

### Issue #2 (LOW): `test_config.py` Environment Variable Leaking

**File:** `tests/test_config.py`

**Problem:** Tests set `os.environ` values without cleanup. The `test_load_settings_from_env` test sets `API_PORT=9000` and `API_HOST=127.0.0.1`, and `test_invalid_port_raises_validation_error` sets `API_PORT=invalid`. These values persist across tests because `from src.config import Settings` is done inside each test function (which works around the caching issue), but the environment is not restored.

**Fix:** Use `monkeypatch.setenv` / `monkeypatch.delenv`, or wrap with `os.environ` cleanup:
```python
def test_load_settings_from_env(monkeypatch):
    monkeypatch.setenv("API_PORT", "9000")
    monkeypatch.setenv("API_HOST", "127.0.0.1")
    from src.config import Settings
    settings = Settings()
    assert settings.api_port == 9000
```

**Priority:** Low -- tests pass in isolation, but ordering dependencies are fragile.

---

### Issue #3 (LOW): `test_config.py` Re-imports Settings Inside Functions

**File:** `tests/test_config.py`

**Problem:** Each test does `from src.config import Settings` inside the function body rather than at module top. This is likely a workaround for the global `settings = Settings()` at module level in `src/config.py`, which would fail if env vars are invalid. This is a code smell.

**Recommendation:** Use `monkeypatch` and top-level imports, or test `Settings` construction separately from the global singleton.

**Priority:** Low.

---

### Issue #4 (INFO): Plan/Review Artifacts Missing

**Problem:** The review instructions reference these files which do not exist:
- `docs/superpowers/plans/2026-07-26-backend-foundation.md`
- `.superpowers/sdd/progress.md`
- `.superpowers/sdd/tasks-4-7-report.md`
- `.superpowers/sdd/review-tasks-4-7.md`

These are likely supposed to be created by the implementer as part of the workflow. Without the plan document, I cannot verify exact specification compliance (field names, table structures, etc.) against the original design. The review is based on general best practices and the visible implementation.

**Priority:** Info -- workflow artifact gap, not a code defect.

---

## 5. Code Quality Assessment

### Positive Findings
- **No print statements** in any source file.
- **No hardcoded secrets or credentials** -- all configuration via `pydantic-settings`.
- **Complete docstrings** on all models and test functions.
- **Proper `__repr__` methods** on all models for debugging.
- **Type annotations** throughout using `Mapped[]` with proper SQLAlchemy 2.0 style.
- **Correct relationship definitions** -- Video-Source (many-to-one), Video-Tag (many-to-many with association table), foreign keys with `ondelete="CASCADE"`.
- **CheckConstraint** on VideoSource.type to enforce valid values ('local', 'nas', 'minio').
- **Test fixture** uses in-memory SQLite, properly creates/drops all tables, and disposes engine.
- **All models registered** via `__init__.py` imports, ensuring `Base.metadata.create_all` sees them.
- **`expire_on_commit=False`** set correctly for async sessions.
- **`get_session`** uses async generator with proper cleanup in `finally` block.

### Architecture Quality
- Clean separation: `database/` for infrastructure, `models/` for domain.
- Models use SQLAlchemy 2.0 declarative style with `Mapped[]` type annotations.
- Association table (`video_tags`) properly defined as `Table` with composite primary key.
- All foreign keys reference correct parent tables with CASCADE delete.

---

## 6. Verdict

**CONDITIONAL PASS**

The implementation is well-structured, follows SQLAlchemy 2.0 best practices, all tests pass, and the code quality is solid. However:

- The `datetime.utcnow()` deprecation (Issue #1) should be fixed before merge to avoid accumulating technical debt.
- The test environment leaking (Issue #2) should be fixed to prevent fragile test ordering.

These are not blockers for passing, but they are recommended fixes.

**Recommendation:** Fix Issue #1 and #2, then re-run tests to confirm clean pass with zero warnings.
