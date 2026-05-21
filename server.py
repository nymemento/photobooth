from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
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
BASE_URL = os.getenv("BASE_URL", "https://photobooth-production-e5fa.up.railway.app")

# Keyed by Stripe checkout session id. In-memory only — wiped on Railway restart.
sessions = {}

PRODUCTS = {
    "print": {"name": "Print (2 copies)", "amount": 1111},
    "download": {"name": "Download (e-mail)", "amount": 555},
}


@app.get("/")
async def root():
    return {"status": "Memento Booth API is running", "timestamp": datetime.now().isoformat()}


ORDER_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Memento</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Helvetica Neue', Arial, sans-serif; background: #f8f8f8; color: #1a1a1a; min-height: 100vh; }
  .header { background: #f0ede8; padding: 40px 20px; text-align: center; }
  .header h1 { font-size: 32px; font-weight: 300; letter-spacing: 2px; }
  .container { max-width: 480px; margin: 0 auto; padding: 24px 20px; }
  .product { display: flex; justify-content: space-between; align-items: center; padding: 24px 0; border-bottom: 1px solid #e5e5e5; }
  .product-info h2 { font-size: 18px; font-weight: 500; margin-bottom: 4px; }
  .product-info .price { font-size: 16px; color: #666; }
  .qty { display: flex; align-items: center; gap: 16px; }
  .qty button { width: 36px; height: 36px; border-radius: 50%; border: 1.5px solid #ccc; background: white; font-size: 18px; cursor: pointer; display: flex; align-items: center; justify-content: center; }
  .qty button:active { background: #f0f0f0; }
  .qty span { font-size: 18px; min-width: 20px; text-align: center; }
  .email-section { margin-top: 32px; }
  .email-section p { font-size: 15px; color: #444; margin-bottom: 12px; }
  .email-section input { width: 100%; padding: 16px; font-size: 16px; border: 1.5px solid #ddd; border-radius: 8px; outline: none; }
  .email-section input:focus { border-color: #6B1D2A; }
  .checkout-btn { display: block; width: 100%; margin-top: 24px; padding: 18px; background: #1a1a1a; color: white; border: none; border-radius: 8px; font-size: 18px; font-weight: 500; cursor: pointer; letter-spacing: 0.5px; }
  .checkout-btn:disabled { background: #999; cursor: not-allowed; }
  .checkout-btn:active:not(:disabled) { background: #333; }
  .error { color: #c0392b; margin-top: 12px; font-size: 14px; text-align: center; }
</style>
</head>
<body>
<div class="header"><h1>Memento</h1></div>
<div class="container">
  <div class="product">
    <div class="product-info">
      <h2>Print (2 copies)</h2>
      <div class="price">$11.11</div>
    </div>
    <div class="qty">
      <button onclick="adjust('print',-1)">-</button>
      <span id="print-qty">0</span>
      <button onclick="adjust('print',1)">+</button>
    </div>
  </div>
  <div class="product">
    <div class="product-info">
      <h2>Download (e-mail)</h2>
      <div class="price">$5.55</div>
    </div>
    <div class="qty">
      <button onclick="adjust('download',-1)">-</button>
      <span id="download-qty">0</span>
      <button onclick="adjust('download',1)">+</button>
    </div>
  </div>
  <div class="email-section">
    <p>Enter your email address to receive your download.</p>
    <input type="email" id="email" placeholder="Email Address">
  </div>
  <button class="checkout-btn" id="checkout-btn" disabled onclick="checkout()">Select an item</button>
  <div class="error" id="error"></div>
</div>
<script>
const qty = { print: 0, download: 0 };
const prices = { print: 1111, download: 555 };

function adjust(item, delta) {
  qty[item] = Math.max(0, Math.min(5, qty[item] + delta));
  document.getElementById(item + '-qty').textContent = qty[item];
  updateBtn();
}

function updateBtn() {
  const total = qty.print * prices.print + qty.download * prices.download;
  const btn = document.getElementById('checkout-btn');
  if (total === 0) {
    btn.textContent = 'Select an item';
    btn.disabled = true;
  } else {
    btn.textContent = 'Checkout  $' + (total / 100).toFixed(2);
    btn.disabled = false;
  }
}

async function checkout() {
  const email = document.getElementById('email').value;
  const errEl = document.getElementById('error');
  errEl.textContent = '';

  if (qty.download > 0 && !email) {
    errEl.textContent = 'Email is required for downloads.';
    return;
  }

  const btn = document.getElementById('checkout-btn');
  btn.disabled = true;
  btn.textContent = 'Loading...';

  try {
    const res = await fetch('/create-checkout', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ print_qty: qty.print, download_qty: qty.download, email })
    });
    const data = await res.json();
    if (data.checkout_url) {
      window.location.href = data.checkout_url;
    } else {
      errEl.textContent = data.detail || 'Something went wrong.';
      updateBtn();
    }
  } catch (e) {
    errEl.textContent = 'Connection error. Please try again.';
    updateBtn();
  }
}
</script>
</body>
</html>"""


@app.get("/order", response_class=HTMLResponse)
async def order_page():
    return ORDER_PAGE


@app.post("/create-checkout")
async def create_checkout(request: Request):
    data = await request.json()
    print_qty = data.get("print_qty", 0)
    download_qty = data.get("download_qty", 0)
    email = data.get("email", "")

    if print_qty == 0 and download_qty == 0:
        raise HTTPException(status_code=400, detail="Select at least one item")

    line_items = []
    if print_qty > 0:
        line_items.append({
            "price_data": {
                "currency": "usd",
                "product_data": {"name": "Print (2 copies)"},
                "unit_amount": PRODUCTS["print"]["amount"],
            },
            "quantity": print_qty,
        })
    if download_qty > 0:
        line_items.append({
            "price_data": {
                "currency": "usd",
                "product_data": {"name": "Download (e-mail)"},
                "unit_amount": PRODUCTS["download"]["amount"],
            },
            "quantity": download_qty,
        })

    checkout_params = {
        "payment_method_types": ["card"],
        "line_items": line_items,
        "mode": "payment",
        "success_url": f"{BASE_URL}/success",
        "cancel_url": f"{BASE_URL}/order",
        "metadata": {
            "print_qty": str(print_qty),
            "download_qty": str(download_qty),
        },
    }

    if email:
        checkout_params["customer_email"] = email

    checkout_session = stripe.checkout.Session.create(**checkout_params)

    return {"checkout_url": checkout_session.url, "session_id": checkout_session.id}


@app.get("/success", response_class=HTMLResponse)
async def success_page():
    return """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Memento</title>
<style>
  body { font-family: 'Helvetica Neue', Arial, sans-serif; display: flex; align-items: center;
    justify-content: center; min-height: 100vh; background: #f8f8f8; color: #1a1a1a; text-align: center; }
  h1 { font-size: 28px; font-weight: 300; letter-spacing: 2px; margin-bottom: 12px; }
  p { font-size: 16px; color: #666; }
</style></head>
<body><div><h1>Thank you</h1><p>Return to the booth to start your session.</p></div></body></html>"""


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
        metadata = session_data.get("metadata", {})

        sessions[session_id] = {
            "payment_id": session_id,
            "amount": session_data["amount_total"],
            "status": "paid",
            "used": False,
            "created_at": datetime.now().isoformat(),
            "customer_email": session_data.get("customer_details", {}).get("email"),
            "print_qty": int(metadata.get("print_qty", "0")),
            "download_qty": int(metadata.get("download_qty", "0")),
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
            "print_qty": session.get("print_qty", 0),
            "download_qty": session.get("download_qty", 0),
        }
    return {"valid": False}


@app.get("/session/latest")
async def latest_session(since: str = ""):
    for sid, session in reversed(list(sessions.items())):
        if not session["used"]:
            if since and session["created_at"] <= since:
                continue
            return {
                "valid": True,
                "session_id": sid,
                "print_qty": session.get("print_qty", 0),
                "download_qty": session.get("download_qty", 0),
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
async def generate_qr():
    order_url = f"{BASE_URL}/order"

    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(order_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    img_str = base64.b64encode(buffer.getvalue()).decode()

    return {
        "qr_code": img_str,
        "order_url": order_url,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
