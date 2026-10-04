import hashlib
import hmac
import json
import os

import httpx
from dotenv import load_dotenv


load_dotenv()


WEBHOOK_SECRET = os.getenv(
    "WEBHOOK_SECRET",
    "nestack-webhook-secret-123"
)


def generate_signature(body: bytes) -> str:
    """
    Generate an HMAC-SHA256 signature from the exact
    HTTP request body that will be sent.
    """

    signature = hmac.new(
        WEBHOOK_SECRET.encode("utf-8"),
        body,
        hashlib.sha256
    ).hexdigest()

    return signature


async def send_webhook(
    webhook_url: str,
    payload: dict
):
    """
    Send the webhook request with an HMAC-SHA256 signature.

    Returns:
        (success, http_status)
    """

    # Serialize the payload once.
    # These exact bytes will be signed AND sent.
    body = json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True
    ).encode("utf-8")

    signature = generate_signature(body)

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": signature
    }

    try:
        async with httpx.AsyncClient(
            timeout=10.0
        ) as client:

            response = await client.post(
                webhook_url,
                content=body,
                headers=headers
            )

        if 200 <= response.status_code < 300:
            return True, response.status_code

        return False, response.status_code

    except (httpx.TimeoutException, httpx.RequestError):
        return False, None