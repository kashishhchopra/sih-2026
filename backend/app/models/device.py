"""IoT wearable ("smart band") devices linked to a tourist.

Bands push periodic telemetry (location, heart rate, battery, a physical SOS
button, fall detection) authenticated by a per-device key rather than a user
JWT -- a wearable cannot hold a login session, and its credential should be
revocable independently of the tourist's own account.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.time import utc_now
from app.db.session import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    tourist_id: Mapped[int] = mapped_column(ForeignKey("tourists.id"), index=True)

    # bcrypt hash of the device's API key -- same treatment as a user password.
    hashed_key: Mapped[str] = mapped_column(String, nullable=False)

    firmware_version: Mapped[str] = mapped_column(String, default="1.0.0")
    battery_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_heartbeat: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    @property
    def is_online(self) -> bool:
        """A band that hasn't phoned home in 10 minutes is considered offline --
        worth flagging on the admin roster since a dead/removed band silently
        stops protecting its wearer."""
        if self.last_heartbeat is None:
            return False
        return (utc_now() - self.last_heartbeat).total_seconds() < 600
