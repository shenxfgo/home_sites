# Video Platform Backend

Backend API for video management platform.

## Development

```bash
# Install dependencies
uv sync

# Run development server
uv run uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

## Testing

```bash
# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=src --cov-report=html
```