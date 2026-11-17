from app.notifications.queue import ClaimNotification


class FakeNotificationService:
    def __init__(self, error: Exception | None = None) -> None:
        self.sent: list[ClaimNotification] = []
        self.error = error

    async def notify(self, notification: ClaimNotification) -> None:
        if self.error is not None:
            raise self.error
        self.sent.append(notification)
