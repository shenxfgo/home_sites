# Task 1: Create Backend Project Structure

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/README.md`
- Create: `backend/.gitignore`

**Interfaces:**
- Consumes: None
- Produces: Project configuration file for uv dependency management

## Steps

### Step 1: Create pyproject.toml with uv project configuration

```toml
[project]
name = "video-platform-backend"
version = "0.1.0"
description = "Video management platform backend"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.109.0",
    "uvicorn[standard]>=0.27.0",
    "sqlalchemy>=2.0.25",
    "aiosqlite>=0.19.0",
    "pydantic>=2.5.0",
    "pydantic-settings>=2.1.0",
    "apscheduler>=3.10.4",
    "python-multipart>=0.0.6",
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",
    "python-dotenv>=1.0.0",
    "ffmpeg-python>=0.2.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.4.4",
    "pytest-asyncio>=0.23.3",
    "pytest-cov>=4.1.0",
    "httpx>=0.26.0",
    "black>=24.1.0",
    "ruff>=0.2.0",
    "mypy>=1.8.0",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.black]
line-length = 100
target-version = ['py311']

[tool.ruff]
line-length = 100
select = ["E", "F", "I", "N", "W"]
target-version = "py311"

[tool.mypy]
python_version = "3.11"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

### Step 2: Create README.md with project overview

```markdown
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
```

### Step 3: Create .gitignore

```gitignore
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
.venv/
env.bak/
venv.bak/
*.egg-info/
dist/
build/
.pytest_cache/
.coverage
htmlcov/
.mypy_cache/
.ruff_cache/
data/
*.db
*.db-journal
.env
.env.local
```

### Step 4: Commit

```bash
cd backend
git add pyproject.toml README.md .gitignore
git commit -m "feat: create backend project structure and configuration"
```