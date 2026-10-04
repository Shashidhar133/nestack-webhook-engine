import hashlib
import hmac
import os

from fastapi import FastAPI, Header, HTTPException, Request
from dotenv import load_dotenv
import uvicorn


load_dotenv()


SECRET = os.getenv(
    "WEBHOOK_SECRET",
    "nestack-webhook-secret-123"
)


app = FastAPI(
    title="Test Webhook Receiver"
)


@app.post("/webhook")
async def receive_webhook(
    request: Request,
    x_webhook_signature: str | None = Header(default=None)
):
    body = await request.body()

    expected_signature = hmac.new(
        SECRET.encode("utf-8"),
        body,
        hashlib.sha256
    ).hexdigest()

    if x_webhook_signature != expected_signature:
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature"
        )

    payload = await request.json()

    print("\n========== WEBHOOK RECEIVED ==========")
    print("Payload:", payload)
    print("Signature:", x_webhook_signature)
    print("Signature verified: YES")
    print("======================================\n")

    return {
        "message": "Webhook received successfully"
    }


if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=9000
    )