from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import stripe
import os
from datetime import datetime
import qrcode
from io import BytesIO
import base64

app = FastAPI(title="Memento Booth API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")

# Keyed by Stripe checkout session id. In-memory only — wiped on Railway restart.
sessions = {}


@app.get("/")
async def root():
    return {"status": "Memento Booth API is running", "timestamp": datetime.now().isoformat()}


@app.post("/stripe-webhook")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event["type"] == "checkout.session.completed":
        session_data = event["data"]["object"]
        session_id = session_data["id"]

        sessions[session_id] = {
            "payment_id": session_id,
            "amount": session_data["amount_total"],
            "status": "paid",
            "used": False,
            "created_at": datetime.now().isoformat(),
            "customer_email": session_data.get("customer_details", {}).get("email"),
        }

        print(f"Payment received for session {session_id}")

    return {"status": "success"}


@app.get("/session/check/{token}")
async def check_session(token: str):
    if token in sessions:
        session = sessions[token]
        return {
            "valid": True,
            "used": session["used"],
            "status": session["status"],
        }
    return {"valid": False}


@app.post("/session/start/{token}")
async def start_session(token: str):
    if token not in sessions:
        raise HTTPException(status_code=404, detail="Invalid session token")

    if sessions[token]["used"]:
        raise HTTPException(status_code=400, detail="Session already used")

    sessions[token]["used"] = True
    sessions[token]["started_at"] = datetime.now().isoformat()

    return {"status": "started", "message": "Session activated"}


@app.post("/email/send")
async def send_email(request: Request):
    data = await request.json()
    email = data.get("email")
    image_base64 = data.get("image")

    # TODO: wire SendGrid in Phase 2
    print(f"Would send email to: {email}")

    return {"status": "sent", "email": email}


@app.get("/qr/generate")
async def generate_qr(amount: int = 1100):
    checkout_session = stripe.checkout.Session.create(
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": "usd",
                "product_data": {
                    "name": "Photo Booth Session",
                    "description": "2 strips (4 photos each)",
                },
                "unit_amount": amount,
            },
            "quantity": 1,
        }],
        mode="payment",
        success_url="https://newyorkmemento.com/success",
        cancel_url="https://newyorkmemento.com/cancel",
    )

    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(checkout_session.url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    img_str = base64.b64encode(buffer.getvalue()).decode()

    return {
        "qr_code": img_str,
        "checkout_url": checkout_session.url,
        "session_id": checkout_session.id,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
