"""WatchlistService for hand-picked queues such as 今晚看这些."""
from typing import cast

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.video import Video
from src.models.watchlist import Watchlist, WatchlistItem


def _with_videos() -> Select[tuple[Watchlist]]:
    """Load a list together with the videos of every item, in two extra queries.

    ``populate_existing`` is what lets the write routes hand back a usable
    queue: the row was just added or removed inside this session, so the copy
    in the identity map still holds the stale collection without it.

    返回类型写 ``Select[tuple[Watchlist]]`` 而不是 ``select``：后者是构造函数，不是
    类型，拿它当注解 mypy 会直接报 valid-type；``Select`` 的泛型参数是行类型，所以
    单表查询要包一层一元组。
    """
    return (
        select(Watchlist)
        .options(selectinload(Watchlist.items).selectinload(WatchlistItem.video))
        .execution_options(populate_existing=True)
    )


class DuplicateWatchlistNameError(ValueError):
    """The owner already has a list under that name.

    Names only have to be distinct inside one account, and the database now
    enforces that with a unique index, so the routes need to answer 409 rather
    than let the IntegrityError surface as a 500.
    """


class WatchlistService:
    """Service for managing one person's watchlists and the titles inside them.

    A queue is a personal asset, so every lookup carries the owner. Because all
    of the write paths read the row through :meth:`get_watchlist` first, that
    one filter is what makes another account's list come back as 404 instead of
    being renamed, deleted or edited.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_watchlists(
        self, user_id: int, video_id: int | None = None
    ) -> list[Watchlist]:
        """List the caller's watchlists, oldest first.

        ``video_id`` narrows the result to the lists holding that title, which is
        how the detail page knows which boxes to pre-tick.
        """
        query = _with_videos().where(Watchlist.owner_id == user_id)
        if video_id is not None:
            query = query.where(
                Watchlist.id.in_(
                    select(WatchlistItem.watchlist_id).where(
                        WatchlistItem.video_id == video_id
                    )
                )
            )
        result = await self.session.execute(query.order_by(Watchlist.id))
        return list(result.scalars().all())

    async def get_watchlist(
        self, user_id: int, watchlist_id: int
    ) -> Watchlist | None:
        """Get one of the caller's watchlists with its videos attached."""
        result = await self.session.execute(
            _with_videos().where(
                Watchlist.id == watchlist_id, Watchlist.owner_id == user_id
            )
        )
        return result.scalar_one_or_none()

    async def _read_back(self, user_id: int, watchlist_id: int) -> Watchlist:
        """Re-read a queue this account has just modified.

        :meth:`get_watchlist` 的 ``Optional`` 是给路由准备的（查不到就答 404）。
        写路径走到这一步，行是同一个事务里刚提交的、owner 过滤必然命中，所以这里
        把类型收窄一次，而不是在每个调用点各写一遍判空。
        """
        return cast(Watchlist, await self.get_watchlist(user_id, watchlist_id))

    async def create(
        self, user_id: int, name: str, description: str | None = None
    ) -> Watchlist:
        """Create an empty watchlist owned by the caller."""
        await self._require_free_name(user_id, name)
        watchlist = Watchlist(owner_id=user_id, name=name, description=description)
        self.session.add(watchlist)
        await self.session.commit()
        # Read it back: a just-added row has no loaded item collection, and the
        # routes all answer with one.
        return await self._read_back(user_id, watchlist.id)

    async def _require_free_name(self, user_id: int, name: str) -> None:
        result = await self.session.execute(
            select(Watchlist.id).where(
                Watchlist.owner_id == user_id, Watchlist.name == name
            )
        )
        if result.scalar_one_or_none() is not None:
            raise DuplicateWatchlistNameError(f"片单「{name}」已存在")

    async def update(
        self,
        user_id: int,
        watchlist_id: int,
        name: str | None = None,
        description: str | None = None,
    ) -> Watchlist:
        """Rename a watchlist or change what it says about itself."""
        watchlist = await self.get_watchlist(user_id, watchlist_id)
        if not watchlist:
            raise ValueError(f"片单 #{watchlist_id} 不存在")

        if name is not None:
            if name != watchlist.name:
                await self._require_free_name(user_id, name)
            watchlist.name = name
        if description is not None:
            watchlist.description = description
        await self.session.commit()
        return watchlist

    async def delete(self, user_id: int, watchlist_id: int) -> None:
        """Delete a watchlist and, with it, only its own rows in ``watchlist_items``."""
        watchlist = await self.get_watchlist(user_id, watchlist_id)
        if not watchlist:
            raise ValueError(f"片单 #{watchlist_id} 不存在")

        await self.session.delete(watchlist)
        await self.session.commit()

    async def add_video(self, user_id: int, watchlist_id: int, video_id: int) -> Watchlist:
        """Put a title at the end of the queue; being in it already changes nothing."""
        watchlist = await self.get_watchlist(user_id, watchlist_id)
        if not watchlist:
            raise ValueError(f"片单 #{watchlist_id} 不存在")

        video = (
            await self.session.execute(select(Video).where(Video.id == video_id))
        ).scalar_one_or_none()
        if not video:
            raise ValueError(f"视频 #{video_id} 不存在")

        already = (
            await self.session.execute(
                select(WatchlistItem)
                .where(WatchlistItem.watchlist_id == watchlist_id)
                .where(WatchlistItem.video_id == video_id)
            )
        ).scalar_one_or_none()
        if already is None:
            self.session.add(WatchlistItem(watchlist_id=watchlist_id, video_id=video_id))
            await self.session.commit()

        return await self._read_back(user_id, watchlist_id)

    async def remove_video(
        self, user_id: int, watchlist_id: int, video_id: int
    ) -> Watchlist:
        """Take one title out of the queue, leaving the video itself in the library."""
        watchlist = await self.get_watchlist(user_id, watchlist_id)
        if not watchlist:
            raise ValueError(f"片单 #{watchlist_id} 不存在")

        for item in list(watchlist.items):
            if item.video_id == video_id:
                watchlist.items.remove(item)
                await self.session.commit()
                break

        return await self._read_back(user_id, watchlist_id)
