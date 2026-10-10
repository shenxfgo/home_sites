"""Tests for the notification list, read and delete endpoints."""
import pytest


async def _create(db_session, title, reader_id=None):
    """Seed one broadcast notification, optionally read by one person."""
    from src.models.notification import Notification
    from src.models.read_state import NotificationRead

    notification = Notification(
        type="scan_complete",
        title=title,
        message="body",
    )
    db_session.add(notification)
    await db_session.commit()
    if reader_id is not None:
        db_session.add(
            NotificationRead(notification_id=notification.id, user_id=reader_id)
        )
        await db_session.commit()
    await db_session.refresh(notification)
    return notification


@pytest.mark.asyncio
async def test_delete_one_notification_leaves_the_others(client, db_session):
    """Deleting a row removes only that row."""
    first = await _create(db_session, "扫描完成 A")
    await _create(db_session, "扫描完成 B")

    response = await client.delete(f"/api/notifications/{first.id}")
    assert response.status_code == 204

    listing = await client.get("/api/notifications")
    titles = [item["title"] for item in listing.json()["items"]]
    assert titles == ["扫描完成 B"]


@pytest.mark.asyncio
async def test_delete_missing_notification_is_not_found(client):
    """A deleted or unknown id answers 404 rather than 500."""
    response = await client.delete("/api/notifications/99999")

    assert response.status_code == 404
    assert "不存在" in response.json()["detail"]


@pytest.mark.asyncio
async def test_clear_notifications_empties_the_list(client, db_session, signed_in_user):
    """The collection route wipes every row at once."""
    await _create(db_session, "A")
    await _create(db_session, "B", reader_id=signed_in_user.id)

    response = await client.delete("/api/notifications")
    assert response.status_code == 204

    listing = await client.get("/api/notifications")
    assert listing.json()["total"] == 0
    unread = await client.get("/api/notifications/unread")
    assert unread.json()["count"] == 0


@pytest.mark.asyncio
async def test_clear_on_an_empty_list_is_not_an_error(client):
    """Clearing nothing is a no-op, not a failure."""
    response = await client.delete("/api/notifications")

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_drops_the_unread_count(client, db_session):
    """Unread rows that are deleted stop being counted."""
    unread = await _create(db_session, "未读")
    await _create(db_session, "另一条")

    before = await client.get("/api/notifications/unread")
    assert before.json()["count"] == 2

    await client.delete(f"/api/notifications/{unread.id}")

    after = await client.get("/api/notifications/unread")
    assert after.json()["count"] == 1


@pytest.mark.asyncio
async def test_mark_all_read_writes_one_row_per_unread_notification(
    client, db_session, signed_in_user, make_user
):
    """read-all 那个循环体一次也没走过：接口只被空库存过。

    三条通知里两条我自己没读、一条别人读过了——通知是全户广播的，别人读过不等于
    我读过，所以三条都要给我写一行；反过来，这次请求不许往别人那一列里多写一行。

    电池 M2（#198）：把那个循环的迭代源换成空列表，红的就是这一条——它先红在
    「我这边该有三行」上，而不是红在 unread 计数上，因为计数走的是同一句 SQL。
    """
    from sqlalchemy import func, select

    from src.models.read_state import NotificationRead

    mine_a = await _create(db_session, "扫描完成 A")
    mine_b = await _create(db_session, "扫描完成 B")
    someone = await make_user("someone-else")
    shared = await _create(db_session, "扫描完成 C", reader_id=someone.id)

    response = await client.post("/api/notifications/read-all")

    assert response.status_code == 204

    rows = await db_session.scalars(
        select(NotificationRead.notification_id).where(
            NotificationRead.user_id == signed_in_user.id
        )
    )
    assert sorted(rows.all()) == sorted([mine_a.id, mine_b.id, shared.id])
    assert (await client.get("/api/notifications/unread")).json()["count"] == 0

    other_rows = await db_session.scalar(
        select(func.count())
        .select_from(NotificationRead)
        .where(NotificationRead.user_id == someone.id)
    )
    assert other_rows == 1

