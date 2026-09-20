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
    assert "not found" in response.json()["detail"]


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
