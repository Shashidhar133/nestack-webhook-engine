from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, Integer, JSON, String, Text

from .database import Base


def utc_now():
    """
    Return current UTC time as a timezone-naive datetime.

    SQLite does not reliably preserve timezone information,
    so the application stores UTC consistently without tzinfo.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Event(Base):
    __tablename__ = "events"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    type = Column(
        String(255),
        nullable=False
    )

    payload = Column(
        JSON,
        nullable=False
    )

    webhook_url = Column(
        Text,
        nullable=False
    )

    status = Column(
        String(20),
        nullable=False,
        default="pending"
    )

    created_at = Column(
        DateTime,
        default=utc_now,
        nullable=False
    )

    next_attempt_at = Column(
        DateTime,
        nullable=True
    )

    attempt_count = Column(
        Integer,
        default=0,
        nullable=False
    )


class Attempt(Base):
    __tablename__ = "attempts"

    id = Column(
        Integer,
        primary_key=True,
        index=True
    )

    event_id = Column(
        Integer,
        nullable=False,
        index=True
    )

    attempted_at = Column(
        DateTime,
        default=utc_now,
        nullable=False
    )

    http_status = Column(
        Integer,
        nullable=True
    )

    outcome = Column(
        String(20),
        nullable=False
    )