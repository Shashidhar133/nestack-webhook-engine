# Nestack Webhook Delivery Engine

A reliable webhook delivery engine built with **Python, FastAPI, SQLite, SQLAlchemy, and httpx**.

The system accepts events through an API, stores them persistently, and delivers them asynchronously to webhook endpoints using a custom background worker with retry handling and HMAC-SHA256 request signing.

---

## Features

* Event ingestion through REST API
* Persistent SQLite storage
* Background webhook delivery worker
* Automatic retries with the required schedule:

  * Attempt 1 → immediate
  * Attempt 2 → after 30 seconds
  * Attempt 3 → after 5 minutes
  * Attempt 4 → after 30 minutes
* Maximum of 4 total delivery attempts
* HMAC-SHA256 webhook signatures
* Attempt history for every event
* Dead-event handling
* Manual retry for dead events
* Webhook delivery timeout handling
* Restart-safe retry state through SQLite
* No Celery, RQ, BullMQ, or other queue libraries

---

## Tech Stack

* **Python**
* **FastAPI**
* **SQLAlchemy**
* **SQLite**
* **httpx**
* **python-dotenv**
* **Uvicorn**

---

## Project Structure

```text
nestack-webhook-engine/
│
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── delivery.py
│   └── worker.py
│
├── .env
├── .gitignore
├── requirements.txt
├── run_worker.py
├── test_receiver.py
└── README.md
```

---

## Setup

### 1. Clone the repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_URL>
cd nestack-webhook-engine
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

### 3. Activate the virtual environment

Windows PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

### 4. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 5. Configure environment variables

Create a `.env` file:

```env
WEBHOOK_SECRET=nestack-webhook-secret-123
```

The `.env` file should not be committed to Git.

---

# Running the Application

The application uses two processes:

1. FastAPI API server
2. Background delivery worker

Open two terminals.

### Terminal 1 — Start API

```bash
python -m uvicorn app.main:app --reload
```

The API will run at:

```text
http://127.0.0.1:8000
```

Swagger documentation:

```text
http://127.0.0.1:8000/docs
```

### Terminal 2 — Start Worker

```bash
python run_worker.py
```

The worker continuously checks for pending and scheduled events.

---

# Optional Test Receiver

A local webhook receiver is included for testing.

Open another terminal:

```bash
python test_receiver.py
```

The receiver runs at:

```text
http://127.0.0.1:9000/webhook
```

It validates the HMAC-SHA256 signature before accepting the webhook.

---

# API Endpoints

## Create Event

```http
POST /events
```

Example request:

```json
{
  "type": "payment.success",
  "payload": {
    "payment_id": "pay_test_001",
    "amount": 1500,
    "currency": "INR"
  },
  "webhook_url": "http://127.0.0.1:9000/webhook"
}
```

Example response:

```json
{
  "id": 1,
  "type": "payment.success",
  "payload": {
    "payment_id": "pay_test_001",
    "amount": 1500,
    "currency": "INR"
  },
  "webhook_url": "http://127.0.0.1:9000/webhook",
  "status": "pending",
  "created_at": "2026-10-04T06:06:10.518741",
  "attempts": []
}
```

---

## List Events

```http
GET /events
```

Returns all stored events along with their delivery attempt history.

---

## Get Event

```http
GET /events/{id}
```

Returns a specific event and all delivery attempts.

Example:

```http
GET /events/1
```

---

## Manually Retry Dead Event

```http
POST /events/{id}/retry
```

Only events with status `dead` can be manually retried.

Manual retry:

* Resets the attempt counter
* Makes the event pending again
* Preserves previous attempt history

---

# Event Statuses

| Status      | Meaning                                       |
| ----------- | --------------------------------------------- |
| `pending`   | Waiting for delivery                          |
| `failed`    | Latest delivery failed and retry is scheduled |
| `delivered` | Webhook was successfully delivered            |
| `dead`      | Four delivery attempts failed                 |

---

# Retry Strategy

The system allows a maximum of **4 delivery attempts**.

```text
Attempt 1
   │
   ├── Success → DELIVERED
   │
   └── Failure
        │
        └── Wait 30 seconds
              │
              ▼
         Attempt 2
              │
              ├── Success → DELIVERED
              │
              └── Failure
                   │
                   └── Wait 5 minutes
                         │
                         ▼
                    Attempt 3
                         │
                         ├── Success → DELIVERED
                         │
                         └── Failure
                              │
                              └── Wait 30 minutes
                                    │
                                    ▼
                               Attempt 4
                                    │
                                    ├── Success → DELIVERED
                                    │
                                    └── Failure
                                         │
                                         ▼
                                       DEAD
```

The retry time is persisted in the database using `next_attempt_at`.

The worker polls approximately once per second, so an eligible retry can be dispatched within roughly one second of its scheduled time.

---

# Webhook Security

Each webhook request contains an HMAC-SHA256 signature.

Header:

```http
X-Webhook-Signature: <signature>
```

The signature is generated using the configured `WEBHOOK_SECRET`.

The exact serialized request body is signed and the same bytes are sent to the webhook endpoint.

Conceptually:

```text
HMAC-SHA256(
    WEBHOOK_SECRET,
    request_body
)
```

The test receiver independently calculates the signature and rejects requests with an invalid signature.

---

# Delivery Behavior

The worker uses `httpx` to send webhook requests.

A response is considered successful when the webhook endpoint returns:

```text
HTTP 2xx
```

The following are treated as failures:

* HTTP 4xx
* HTTP 5xx
* Connection errors
* Timeout errors

The HTTP client timeout is **10 seconds**.

Each attempt is recorded in the `attempts` table with:

* Attempt timestamp
* HTTP status, when available
* Outcome

---

# Persistence and Restart Behavior

SQLite is used as the persistent datastore.

The following information survives application or worker restarts:

* Events
* Event status
* Attempt count
* Scheduled retry time
* Attempt history

When the worker starts again, it reads the database and continues processing events that are still pending or whose retry time has arrived.

Because delivery and event-state updates are persisted through database transactions, completed attempt state is retained across restarts.

If a process crashes before an attempt transaction is committed, that in-flight attempt may not appear in the attempt history and can be attempted again after restart. This is a limitation of the simple custom worker design and avoids claiming exactly-once delivery.

Webhook delivery therefore follows an **at-least-once delivery model**.

---

# Architecture

```text
                 ┌───────────────────┐
                 │     Client        │
                 └─────────┬─────────┘
                           │
                           │ POST /events
                           ▼
                 ┌───────────────────┐
                 │     FastAPI       │
                 │       API         │
                 └─────────┬─────────┘
                           │
                           │ Store event
                           ▼
                 ┌───────────────────┐
                 │      SQLite       │
                 │                   │
                 │ Events + Attempts │
                 └─────────┬─────────┘
                           │
                           │ Poll
                           ▼
                 ┌───────────────────┐
                 │ Background Worker │
                 └─────────┬─────────┘
                           │
                           │ HMAC signed
                           │ HTTP POST
                           ▼
                 ┌───────────────────┐
                 │ Webhook Endpoint  │
                 └─────────┬─────────┘
                           │
                  ┌────────┴────────┐
                  │                 │
                2xx             Failure
                  │                 │
                  ▼                 ▼
              Delivered       Schedule Retry
                                    │
                                    ▼
                              Retry / Dead
```

---

# Database Model

### Events

Stores:

* Event ID
* Event type
* JSON payload
* Webhook URL
* Current status
* Creation time
* Next retry time
* Attempt count

### Attempts

Stores:

* Attempt ID
* Event ID
* Attempt timestamp
* HTTP status
* Outcome

This keeps the current event state separate from the complete delivery history.

---

# Testing

The implementation was tested with:

* Successful webhook delivery
* Network/connection failures
* Automatic retries
* 30-second retry scheduling
* 5-minute retry scheduling
* 30-minute retry scheduling
* Four-attempt dead-letter behavior
* Manual retry of dead events
* HMAC-SHA256 signature verification
* Attempt history retrieval
* Rejection of manual retry for non-dead events

Example successful receiver output:

```text
========== WEBHOOK RECEIVED ==========
Payload: {'amount': 2000, 'currency': 'INR', 'payment_id': 'pay_test_002'}
Signature: <HMAC-SHA256 signature>
Signature verified: YES
======================================
```

---

# Design Decisions

### Why SQLite?

SQLite keeps the project simple while providing persistent storage without requiring an external database service.

### Why a custom worker?

The assessment requires implementing the delivery worker without using queue libraries such as Celery, RQ, or BullMQ.

### Why persist `next_attempt_at`?

Persisting the next retry time allows the worker to resume scheduled deliveries after a restart.

### Why store attempts separately?

Separating attempt history from the event allows the system to maintain a complete delivery audit trail.

### Why HMAC-SHA256?

HMAC provides a way for the receiving system to verify that the webhook was generated using the shared secret and that the request body was not modified.

---

# Limitations

This implementation intentionally keeps the architecture simple for the assessment.

Potential production improvements include:

* Multiple worker coordination
* Distributed locking
* PostgreSQL for larger workloads
* Queue-based horizontal scaling
* Idempotency handling
* Rate limiting
* Authentication for management APIs
* Metrics and monitoring
* Structured logging
* Exponential backoff configuration
* Dead-letter queue infrastructure

---

# License

This project was created as part of the Nestack SDE assessment.
