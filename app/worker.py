import asyncio
from datetime import datetime, timedelta, timezone

from .database import SessionLocal
from .models import Event, Attempt
from .delivery import send_webhook


# Retry schedule:
# After attempt 1 failure → 30 seconds
# After attempt 2 failure → 5 minutes
# After attempt 3 failure → 30 minutes
#
# There are 4 total attempts.
RETRY_DELAYS = [
    30,
    5 * 60,
    30 * 60
]


def utc_now():
    """
    Return current UTC time as a timezone-naive datetime.

    SQLite stores datetime values without timezone information,
    so we use the same format everywhere.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def process_event(event: Event, db):
    """
    Attempt to deliver one webhook event.
    """

    current_attempt = event.attempt_count + 1

    print(
        f"[Worker] Attempting event {event.id} "
        f"(attempt {current_attempt}/4)"
    )

    success, http_status = await send_webhook(
        event.webhook_url,
        event.payload
    )

    # Record attempt history
    attempt = Attempt(
        event_id=event.id,
        attempted_at=utc_now(),
        http_status=http_status,
        outcome="success" if success else "failed"
    )

    db.add(attempt)

    # Increase total attempt count
    event.attempt_count += 1

    if success:

        # ------------------------------------------
        # SUCCESS
        # ------------------------------------------

        event.status = "delivered"
        event.next_attempt_at = None

        print(
            f"[Worker] Event {event.id} delivered successfully "
            f"(HTTP {http_status})"
        )

    else:

        # ------------------------------------------
        # FAILURE
        # ------------------------------------------

        print(
            f"[Worker] Event {event.id} failed "
            f"(HTTP {http_status})"
        )

        # Four attempts have now been used
        if event.attempt_count >= 4:

            event.status = "dead"
            event.next_attempt_at = None

            print(
                f"[Worker] Event {event.id} marked as DEAD "
                f"after 4 failed attempts"
            )

        else:

            # Determine retry delay
            retry_index = event.attempt_count - 1
            delay_seconds = RETRY_DELAYS[retry_index]

            # Mark the latest delivery as failed,
            # but keep it eligible for automatic retry.
            event.status = "failed"

            event.next_attempt_at = (
                utc_now()
                + timedelta(seconds=delay_seconds)
            )

            print(
                f"[Worker] Event {event.id} marked as FAILED"
            )

            print(
                f"[Worker] Event {event.id} "
                f"will retry in {delay_seconds} seconds"
            )

            print(
                f"[Worker] Next attempt at: "
                f"{event.next_attempt_at}"
            )

    db.commit()


async def worker_loop():
    """
    Continuously look for events that are ready for delivery.
    """

    print("[Worker] Delivery worker started")

    while True:

        db = SessionLocal()

        try:

            now = utc_now()

            events = (
                db.query(Event)
                .filter(
                    Event.status.in_(["pending", "failed"]),
                    (
                        Event.next_attempt_at.is_(None)
                        | (Event.next_attempt_at <= now)
                    )
                )
                .order_by(Event.created_at.asc())
                .all()
            )

            for event in events:

                await process_event(
                    event,
                    db
                )

        except Exception as error:

            print(
                f"[Worker] Unexpected error: {error}"
            )

            db.rollback()

        finally:

            db.close()

        # Check for new work every second
        await asyncio.sleep(1)