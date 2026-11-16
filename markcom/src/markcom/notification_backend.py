from abc import ABC, abstractmethod

from desktop_notifier import Urgency


class NotificationError(RuntimeError):
    """A backend's own failure, raised so callers need not import that backend's libraries."""


class NotificationBackend(ABC):
    """Shows one notification; may raise OSError, RuntimeError or NotificationError."""

    @abstractmethod
    def send(self, title: str, message: str, urgency: Urgency, display_sec: int) -> None: ...
