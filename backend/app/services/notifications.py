"""Outbound notification channel: one interface, swappable backend.

This project has no email/SMS infrastructure and none is assumed. Every
place that needs to notify someone (a password-reset code, an emergency
contact when SOS fires) goes through `get_channel().send(...)`, which
defaults to logging the message -- visible in the server log, so a demo can
show "an email would have been sent here" without needing real credentials.

Swapping in a real backend (SMTP, SendGrid, Twilio SMS, Firebase Cloud
Messaging for push) means adding one class implementing `send()` and
pointing NOTIFICATION_CHANNEL at it -- nothing that calls `send()` needs to
change.
"""
from __future__ import annotations

from typing import Protocol

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class NotificationChannel(Protocol):
    def send(self, to: str, subject: str, body: str) -> bool:
        """Returns True if the message was handed off successfully."""
        ...


class ConsoleNotificationChannel:
    """Default channel: logs the message instead of sending it. Never fails,
    never needs credentials -- keeps the app fully runnable offline."""

    def send(self, to: str, subject: str, body: str) -> bool:
        logger.info("notification_sent", channel="console", to=to, subject=subject, body=body)
        return True


_channels: dict[str, NotificationChannel] = {
    "console": ConsoleNotificationChannel(),
}


def get_channel() -> NotificationChannel:
    return _channels.get(settings.NOTIFICATION_CHANNEL, _channels["console"])
