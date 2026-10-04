from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session

from .database import Base, SessionLocal, engine
from .schemas import EventCreate
from .models import Event, Attempt


# Create database tables
Base.metadata.create_all(bind=engine)


# Create FastAPI application
app = FastAPI(
    title="Nestack Webhook Delivery Engine",
    version="1.0.0"
)


# --------------------------------------------------
# Database dependency
# --------------------------------------------------

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# --------------------------------------------------
# Root endpoint
# --------------------------------------------------

@app.get("/")
def root():
    return {
        "message": "Webhook Delivery Engine is running"
    }


# --------------------------------------------------
# Create Event
# --------------------------------------------------

@app.post("/events", status_code=201)
def create_event(
    event_data: EventCreate,
    db: Session = Depends(get_db)
):
    event = Event(
        type=event_data.type,
        payload=event_data.payload,
        webhook_url=event_data.webhook_url,
        status="pending",
        next_attempt_at=None,
        attempt_count=0
    )

    db.add(event)
    db.commit()
    db.refresh(event)

    return {
        "id": event.id,
        "type": event.type,
        "payload": event.payload,
        "webhook_url": event.webhook_url,
        "status": event.status,
        "created_at": event.created_at,
        "attempts": []
    }


# --------------------------------------------------
# Get All Events
# --------------------------------------------------

@app.get("/events")
def get_events(
    db: Session = Depends(get_db)
):
    events = (
        db.query(Event)
        .order_by(Event.created_at.desc())
        .all()
    )

    result = []

    for event in events:

        attempts = (
            db.query(Attempt)
            .filter(Attempt.event_id == event.id)
            .order_by(Attempt.attempted_at.asc())
            .all()
        )

        result.append({
            "id": event.id,
            "type": event.type,
            "payload": event.payload,
            "webhook_url": event.webhook_url,
            "status": event.status,
            "created_at": event.created_at,
            "attempts": [
                {
                    "attempted_at": attempt.attempted_at,
                    "http_status": attempt.http_status,
                    "outcome": attempt.outcome
                }
                for attempt in attempts
            ]
        })

    return result


# --------------------------------------------------
# Get Single Event + Attempt History
# --------------------------------------------------

@app.get("/events/{event_id}")
def get_event(
    event_id: int,
    db: Session = Depends(get_db)
):
    event = (
        db.query(Event)
        .filter(Event.id == event_id)
        .first()
    )

    if not event:
        raise HTTPException(
            status_code=404,
            detail="Event not found"
        )

    attempts = (
        db.query(Attempt)
        .filter(Attempt.event_id == event.id)
        .order_by(Attempt.attempted_at.asc())
        .all()
    )

    return {
        "id": event.id,
        "type": event.type,
        "payload": event.payload,
        "webhook_url": event.webhook_url,
        "status": event.status,
        "created_at": event.created_at,
        "attempts": [
            {
                "attempted_at": attempt.attempted_at,
                "http_status": attempt.http_status,
                "outcome": attempt.outcome
            }
            for attempt in attempts
        ]
    }


# --------------------------------------------------
# Manually Retry Dead Event
# --------------------------------------------------

@app.post("/events/{event_id}/retry")
def retry_event(
    event_id: int,
    db: Session = Depends(get_db)
):
    event = (
        db.query(Event)
        .filter(Event.id == event_id)
        .first()
    )

    if not event:
        raise HTTPException(
            status_code=404,
            detail="Event not found"
        )

    if event.status != "dead":
        raise HTTPException(
            status_code=400,
            detail="Only dead events can be manually retried"
        )

    # Put the event back into the delivery queue
    event.status = "pending"
    event.next_attempt_at = None
    event.attempt_count = 0

    db.commit()
    db.refresh(event)

    return {
        "id": event.id,
        "type": event.type,
        "payload": event.payload,
        "webhook_url": event.webhook_url,
        "status": event.status,
        "created_at": event.created_at,
        "attempts": [
            {
                "attempted_at": attempt.attempted_at,
                "http_status": attempt.http_status,
                "outcome": attempt.outcome
            }
            for attempt in (
                db.query(Attempt)
                .filter(Attempt.event_id == event.id)
                .order_by(Attempt.attempted_at.asc())
                .all()
            )
        ]
    }