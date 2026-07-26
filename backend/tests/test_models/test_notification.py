import pytest


@pytest.mark.asyncio
async def test_create_notification(db_session):
    """Test creating notification"""
    from src.models.notification import Notification

    notification = Notification(
        type="scan_complete",
        title="Scan Complete",
        message="Found 5 new videos",
        data={"count": 5, "source_id": 1},
    )

    db_session.add(notification)
    await db_session.commit()
    await db_session.refresh(notification)

    assert notification.id is not None
    assert notification.type == "scan_complete"
    assert notification.read is False
    assert notification.data == {"count": 5, "source_id": 1}
