"""FastAPI main application entry point."""
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from src.config import settings
from src.database import init_db, async_session_maker
from src.models import *  # noqa: F401, F403 - Import all models to register them
from src.models.source import VideoSource
from src.scheduler import scheduler


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: startup and shutdown events."""
    # Startup: initialize database and start scheduler
    await init_db()

    # Load active sources and schedule them
    async with async_session_maker() as session:
        result = await session.execute(
            select(VideoSource).where(VideoSource.is_active == True)  # noqa: E712
        )
        sources = list(result.scalars().all())
        for source in sources:
            scheduler.add_source_job(source.id, source.scan_interval)

    scheduler.start()

    yield

    # Shutdown: stop scheduler
    scheduler.stop()


app = FastAPI(
    title="Video Platform API",
    description="Backend API for video management platform",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


# Include API routers
from src.api.sources import router as sources_router  # noqa: E402
from src.api.videos import router as videos_router  # noqa: E402
from src.api.subtitles import router as subtitles_router  # noqa: E402
from src.api.tags import router as tags_router  # noqa: E402
from src.api.scan import router as scan_router  # noqa: E402
from src.api.stream import router as stream_router  # noqa: E402
from src.api.history import router as history_router  # noqa: E402
from src.api.favorites import router as favorites_router  # noqa: E402
from src.api.notifications import router as notifications_router  # noqa: E402
from src.api.transcode import router as transcode_router  # noqa: E402
from src.api.scheduler import router as scheduler_router  # noqa: E402
from src.api.settings import router as settings_router  # noqa: E402

app.include_router(sources_router)
app.include_router(videos_router)
app.include_router(subtitles_router)
app.include_router(tags_router)
app.include_router(scan_router)
app.include_router(stream_router)
app.include_router(history_router)
app.include_router(favorites_router)
app.include_router(notifications_router)
app.include_router(transcode_router)
app.include_router(scheduler_router)
app.include_router(settings_router)
