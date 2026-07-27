# Review: Tasks 8-10 (FastAPI Main App, SourceService, Source API)

**Reviewer:** Task Reviewer
**Date:** 2026-07-27
**Commit:** 5088d7a
**Result:** PASS (with minor recommendations)

---

## Summary

Tasks 8-10 implement the FastAPI application entry point, SourceService CRUD layer, and Source REST API endpoints. All 30 new tests pass (45 total in the full suite). The implementation is faithful to the plan with several deliberate improvements (e.g., lifespan pattern instead of deprecated `on_event`).

---

## 1. Conformance to Plan

| Aspect | Plan | Implementation | Match |
|--------|------|----------------|-------|
| `backend/src/main.py` | FastAPI app with CORS, health check | Created with CORS, health check, lifespan | YES |
| `backend/src/__init__.py` | Empty package init | Empty (confirmed empty) | YES |
| `backend/src/services/__init__.py` | Empty package init | Empty docstring only | YES |
| `backend/src/services/source_service.py` | SourceService class with CRUD | Created with all CRUD + update_last_scan | YES |
| `backend/src/api/__init__.py` | Empty package init | Empty docstring only | YES |
| `backend/src/api/sources.py` | REST API with Pydantic models | Created with SourceCreate/Update/Response + endpoints | YES |
| Router prefix | `/api/sources` | `/api/sources` | YES |
| Health check | `GET /health` returns `{"status": "ok"}` | Correct | YES |
| API docs | `/docs` and `/redoc` | Configured in FastAPI constructor | YES |

**Deviation (positive):** The plan specified `@app.on_event("startup")` which is deprecated in modern FastAPI. The implementation correctly uses `lifespan` with `asynccontextmanager`, which is the recommended approach.

**Deviation (positive):** The `SourceResponse` model uses Pydantic v2 `model_config` dict and `@field_serializer` instead of the plan's `class Config: from_attributes = True` and `str` type annotations for datetimes. This is a better approach that properly serializes datetime objects to ISO strings.

---

## 2. Code Quality

### No Issues Found
- No `print()` statements in any source file
- No hardcoded values, no TODO/FIXME/HACK markers
- Proper docstrings on all classes and public methods
- Correct type annotations throughout (Python 3.11+ syntax: `str | None`, `list[...]`)
- Proper `# noqa` comments where needed (A002 for `type` param, E712 for boolean comparison, E402 for late import)

### Issues Found

**[MINOR] DeprecationWarning: `datetime.utcnow()` in `source_service.py:81`**

The `update_last_scan` method uses `datetime.utcnow()` which is deprecated since Python 3.12 and will be removed in a future version.

```python
# Current (line 81):
await self.update(source_id, last_scan_at=datetime.utcnow())

# Recommended:
await self.update(source_id, last_scan_at=datetime.now(datetime.UTC))
```

This affects the models as well (VideoSource, Video, etc.) which also use `lambda: datetime.utcnow()` as default values, but that is outside the scope of these three tasks.

---

## 3. Test Coverage

| Test File | Tests | Status |
|-----------|-------|--------|
| `tests/test_main.py` | 5 | All PASS |
| `tests/test_services/test_source_service.py` | 11 | All PASS |
| `tests/test_api/test_sources.py` | 14 | All PASS |
| **Total (tasks 8-10)** | **30** | **All PASS** |

**Test quality observations:**
- Tests cover happy paths, edge cases, and error conditions
- API tests properly use dependency overrides to isolate from the production database
- The `httpx.AsyncClient` with `httpx.ASGITransport` approach avoids Windows-specific aiosqlite thread crashes (good adaptation)
- Error response details are verified (e.g., `response.json()["detail"] == "Source not found"`)
- Edge cases tested: empty list, empty update body, invalid type, missing required fields, nonexistent IDs

**Test warnings (non-blocking):**
1. `StarletteDeprecationWarning` in `test_main.py` - Using `TestClient` with httpx is deprecated (Starlette recommends `httpx2`). This is a test infrastructure issue, not a code quality issue.
2. `PytestUnhandledThreadExceptionWarning` from aiosqlite in model tests - Windows-specific threading issue, unrelated to tasks 8-10.

---

## 4. API Design

| Endpoint | Method | Status Code | Design |
|----------|--------|-------------|--------|
| `/api/sources` | GET | 200 | Correct, supports `active_only` query param |
| `/api/sources` | POST | 201 | Correct, proper validation |
| `/api/sources/{source_id}` | GET | 200/404 | Correct |
| `/api/sources/{source_id}` | PUT | 200/400/404 | Correct, partial update with `model_dump(exclude_unset=True)` |
| `/api/sources/{source_id}` | DELETE | 204/404 | Correct, no content on success |
| `/health` | GET | 200 | Correct |

**Validation:**
- `SourceCreate`: name (1-255 chars), path (1-1024 chars), type (Literal["local","nas","minio"]), scan_interval (60-86400)
- `SourceUpdate`: All fields optional, same constraints when provided
- Proper 422 responses for validation errors (verified by tests)

**Dependency injection:**
- `get_session` yields database session
- `get_source_service` creates `SourceService(session)` from session dependency
- API tests override both dependencies for isolation

---

## 5. Findings Summary

| ID | Severity | Category | Description | Status |
|----|----------|----------|-------------|--------|
| F1 | MINOR | Deprecation | `datetime.utcnow()` in `source_service.py:81` | Recommended fix |
| F2 | INFO | Test Infra | StarletteDeprecationWarning for TestClient in test_main.py | Known limitation |
| F3 | INFO | Platform | aiosqlite thread warning on Windows in model tests | Unrelated to scope |

---

## 6. Verdict

**PASS**

The implementation is complete, well-structured, and meets all requirements from the plan. All 30 tests pass. The single minor issue (deprecated `datetime.utcnow()`) is recommended for future cleanup but does not affect correctness or test results.

---

## 7. Recommended Fixes

### F1: Replace deprecated `datetime.utcnow()`

**File:** `backend/src/services/source_service.py` (line 81)

```python
# Before:
from datetime import datetime
...
await self.update(source_id, last_scan_at=datetime.utcnow())

# After:
from datetime import datetime, timezone
...
await self.update(source_id, last_scan_at=datetime.now(timezone.utc))
```

This is a one-line change that eliminates the DeprecationWarning. The same pattern should be applied to all model defaults (`lambda: datetime.utcnow()`) in a future task.
