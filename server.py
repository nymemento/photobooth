from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse, Response
import stripe
import os
import json
import uuid
import tempfile
import shutil
from datetime import datetime, timedelta
from twilio.rest import Client as TwilioClient
import resend
import qrcode
from io import BytesIO
import base64

app = FastAPI(title="Memento Booth API")

ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET")
BASE_URL = os.getenv("BASE_URL", "https://photobooth-production-e5fa.up.railway.app")

TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE = os.getenv("TWILIO_PHONE_NUMBER")

resend.api_key = os.getenv("RESEND_API_KEY")
RESEND_FROM = os.getenv("RESEND_FROM_EMAIL", "Memento <photos@nymemento.com>")

SESSIONS_DIR = os.getenv("SESSIONS_DIR", "/data")
SESSIONS_FILE = os.path.join(SESSIONS_DIR, "sessions.json")
SESSIONS_BACKUP = os.path.join(SESSIONS_DIR, "sessions.backup.json")
PHOTOS_DIR = os.path.join(SESSIONS_DIR, "photos")
SESSION_MAX_AGE_DAYS = 30


def _ensure_dir():
    os.makedirs(SESSIONS_DIR, exist_ok=True)
    os.makedirs(PHOTOS_DIR, exist_ok=True)


def load_sessions():
    """Load sessions from persistent JSON file with backup fallback."""
    _ensure_dir()
    for filepath in [SESSIONS_FILE, SESSIONS_BACKUP]:
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    print(f"Loaded {len(data)} sessions from {filepath}")
                    return data
        except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
            print(f"Could not load {filepath}: {e}")
            continue
    print("No existing sessions found, starting fresh")
    return {}


def save_sessions():
    """Atomic write: write to temp file, then rename. Keeps a backup."""
    _ensure_dir()
    try:
        # Write to temp file first
        fd, tmp_path = tempfile.mkstemp(dir=SESSIONS_DIR, suffix=".json.tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(sessions, f, indent=2)
        except Exception:
            os.unlink(tmp_path)
            raise

        # Backup the current file before replacing
        if os.path.exists(SESSIONS_FILE):
            shutil.copy2(SESSIONS_FILE, SESSIONS_BACKUP)

        # Atomic rename (same filesystem)
        shutil.move(tmp_path, SESSIONS_FILE)
    except Exception as e:
        print(f"ERROR saving sessions: {e}")
        # Last-resort direct write
        try:
            with open(SESSIONS_FILE, "w") as f:
                json.dump(sessions, f)
        except Exception as e2:
            print(f"CRITICAL: Could not save sessions at all: {e2}")


def cleanup_old_sessions():
    """Remove used sessions older than SESSION_MAX_AGE_DAYS to prevent file bloat."""
    cutoff = (datetime.now() - timedelta(days=SESSION_MAX_AGE_DAYS)).isoformat()
    removed = 0
    to_remove = []
    for sid, session in sessions.items():
        if session.get("used") and session.get("created_at", "") < cutoff:
            to_remove.append(sid)
    for sid in to_remove:
        del sessions[sid]
        removed += 1
    if removed > 0:
        save_sessions()
        print(f"Cleaned up {removed} old sessions")


sessions = load_sessions()
cleanup_old_sessions()

# Temporary media store for MMS images — keyed by random ID.
media_store = {}

PRODUCTS = {
    "print": {"name": "Print (2 copies)", "amount": 1111},
    "download": {"name": "Download (e-mail)", "amount": 555},
}

LOGO_PATH = os.path.join(os.path.dirname(__file__), "logo.png")


@app.get("/")
async def root():
    total = len(sessions)
    unused = sum(1 for s in sessions.values() if not s.get("used"))
    return {
        "status": "Memento Booth API is running",
        "timestamp": datetime.now().isoformat(),
        "sessions_total": total,
        "sessions_available": unused,
        "persistence": SESSIONS_FILE,
    }


@app.get("/logo.png")
async def serve_logo():
    if os.path.exists(LOGO_PATH):
        with open(LOGO_PATH, "rb") as f:
            return Response(content=f.read(), media_type="image/png")
    raise HTTPException(status_code=404, detail="Logo not found")


ORDER_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Memento</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Helvetica Neue', Arial, sans-serif; background: #f8f8f8; color: #1a1a1a; min-height: 100vh; }
  .header { background: #f0ede8; padding: 30px 20px; text-align: center; }
  .header img { height: 50px; }
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
  .email-section input:focus { border-color: #b11b21; }
  .checkout-btn { display: block; width: 100%; margin-top: 24px; padding: 18px; background: #b11b21; color: white; border: none; border-radius: 8px; font-size: 18px; font-weight: 500; cursor: pointer; letter-spacing: 0.5px; }
  .checkout-btn:disabled { background: #f5f6ee; color: #999; cursor: not-allowed; }
  .checkout-btn:active:not(:disabled) { background: #640003; }
  .error { color: #c0392b; margin-top: 12px; font-size: 14px; text-align: center; }
</style>
</head>
<body>
<div class="header"><img src="/logo.png" alt="Memento"></div>
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
    <p>Enter your e-mail to receive your download.</p>
    <input type="email" id="email" placeholder="you@example.com">
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
  const email = document.getElementById('email').value.trim();
  const errEl = document.getElementById('error');
  errEl.textContent = '';

  if (qty.download > 0 && (!email || !email.includes('@'))) {
    errEl.textContent = 'Valid e-mail is required for downloads.';
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
        "allow_promotion_codes": True,
        "metadata": {
            "print_qty": str(print_qty),
            "download_qty": str(download_qty),
            "email": email,
        },
    }

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
            "email": metadata.get("email", ""),
            "print_qty": int(metadata.get("print_qty", "0")),
            "download_qty": int(metadata.get("download_qty", "0")),
        }

        save_sessions()
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
    save_sessions()

    return {"status": "started", "message": "Session activated"}


@app.get("/media/{media_id}")
async def serve_media(media_id: str):
    if media_id not in media_store:
        raise HTTPException(status_code=404, detail="Media not found")
    return Response(content=media_store[media_id], media_type="image/jpeg")


@app.post("/sms/send")
async def send_sms(request: Request):
    data = await request.json()
    phone = data.get("phone", "")
    image_base64 = data.get("image", "")
    session_id = data.get("session_id", "")

    if not phone and session_id and session_id in sessions:
        phone = sessions[session_id].get("phone", "")

    if not phone:
        raise HTTPException(status_code=400, detail="No phone number provided")

    if not phone.startswith("+"):
        phone = "+1" + phone.lstrip("1")

    image_data = base64.b64decode(image_base64.replace("data:image/jpeg;base64,", ""))
    media_id = str(uuid.uuid4())
    media_store[media_id] = image_data
    media_url = f"{BASE_URL}/media/{media_id}"

    try:
        client = TwilioClient(TWILIO_SID, TWILIO_AUTH)
        client.messages.create(
            body="Here's your photo strip from New York Memento!",
            from_=TWILIO_PHONE,
            to=phone,
            media_url=[media_url],
        )
        print(f"MMS sent to {phone}")
        return {"status": "sent", "phone": phone}
    except Exception as e:
        print(f"MMS failed to {phone}: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/email/send")
async def send_email(request: Request):
    data = await request.json()
    to_email = data.get("email", "")
    image_base64 = data.get("image", "")
    session_id = data.get("session_id", "")

    if not to_email and session_id and session_id in sessions:
        to_email = sessions[session_id].get("email", "")

    if not to_email:
        raise HTTPException(status_code=400, detail="No email provided")

    image_data = base64.b64decode(image_base64.replace("data:image/jpeg;base64,", ""))

    try:
        resend.Emails.send({
            "from": RESEND_FROM,
            "to": [to_email],
            "subject": "Your photo strip from New York Memento",
            "html": "<p>Thanks for visiting New York Memento! Here's your photo strip.</p>",
            "attachments": [
                {
                    "filename": "memento-strip.jpg",
                    "content": list(image_data),
                    "content_type": "image/jpeg",
                }
            ],
        })
        print(f"Email sent to {to_email}")
        return {"status": "sent", "email": to_email}
    except Exception as e:
        print(f"Email failed to {to_email}: {e}")
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/photos/upload")
async def upload_photo(request: Request):
    data = await request.json()
    session_id = data.get("session_id", "")
    image_base64 = data.get("image", "")

    if not session_id or not image_base64:
        raise HTTPException(status_code=400, detail="session_id and image required")

    image_data = base64.b64decode(image_base64.replace("data:image/jpeg;base64,", ""))
    photo_path = os.path.join(PHOTOS_DIR, f"{session_id}.jpg")
    with open(photo_path, "wb") as f:
        f.write(image_data)

    if session_id in sessions:
        sessions[session_id]["has_photo"] = True
        save_sessions()

    print(f"Photo saved for session {session_id} ({len(image_data)} bytes)")
    return {"status": "saved", "session_id": session_id}


@app.get("/admin/photos/{session_id}/image")
async def get_photo(session_id: str):
    photo_path = os.path.join(PHOTOS_DIR, f"{session_id}.jpg")
    if not os.path.exists(photo_path):
        raise HTTPException(status_code=404, detail="Photo not found")
    with open(photo_path, "rb") as f:
        return Response(content=f.read(), media_type="image/jpeg")


ADMIN_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Memento Admin — Photos</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Helvetica Neue', Arial, sans-serif; background: #f8f8f8; color: #1a1a1a; padding: 24px; }
  h1 { font-size: 24px; font-weight: 300; letter-spacing: 2px; margin-bottom: 24px; }
  .search { display: flex; gap: 12px; margin-bottom: 24px; }
  .search input { flex: 1; padding: 12px 16px; font-size: 16px; border: 1.5px solid #ddd; border-radius: 8px; outline: none; }
  .search input:focus { border-color: #b11b21; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 20px; }
  .card { background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
  .card img { width: 100%; cursor: pointer; }
  .card .info { padding: 16px; font-size: 14px; }
  .card .info .phone { font-weight: 500; font-size: 16px; margin-bottom: 4px; }
  .card .info .meta { color: #888; }
  .card .actions { padding: 0 16px 16px; display: flex; gap: 8px; }
  .card .actions a { padding: 8px 16px; border-radius: 6px; font-size: 13px; text-decoration: none;
    background: #b11b21; color: white; }
  .empty { text-align: center; color: #999; padding: 60px 0; font-size: 18px; }
</style>
</head>
<body>
<h1>MEMENTO — Photo Lookup</h1>
<div class="search">
  <input type="text" id="search" placeholder="Search by email..." oninput="filter()">
</div>
<div class="grid" id="grid"></div>
<div class="empty" id="empty" style="display:none">No matching sessions found.</div>
<script>
let allSessions = [];

async function load() {
  const res = await fetch('/admin/photos/data');
  allSessions = await res.json();
  render(allSessions);
}

function filter() {
  const q = document.getElementById('search').value.toLowerCase().trim();
  if (!q) { render(allSessions); return; }
  render(allSessions.filter(s => s.email.toLowerCase().includes(q)));
}

function render(sessions) {
  const grid = document.getElementById('grid');
  const empty = document.getElementById('empty');
  if (sessions.length === 0) { grid.innerHTML = ''; empty.style.display = ''; return; }
  empty.style.display = 'none';
  grid.innerHTML = sessions.map(s => `
    <div class="card">
      <img src="/admin/photos/${s.session_id}/image" alt="Photo strip"
           onclick="window.open(this.src, '_blank')" loading="lazy">
      <div class="info">
        <div class="phone">${s.email || 'No email'}</div>
        <div class="meta">${s.date} &middot; $${(s.amount/100).toFixed(2)}</div>
      </div>
      <div class="actions">
        <a href="/admin/photos/${s.session_id}/image" download="${s.session_id}.jpg">Download</a>
      </div>
    </div>
  `).join('');
}

load();
</script>
</body>
</html>"""


@app.get("/admin/photos", response_class=HTMLResponse)
async def admin_photos_page():
    return ADMIN_PAGE


@app.get("/admin/photos/data")
async def admin_photos_data():
    results = []
    for sid, session in sorted(sessions.items(), key=lambda x: x[1].get("created_at", ""), reverse=True):
        if not session.get("has_photo"):
            continue
        results.append({
            "session_id": sid,
            "email": session.get("email", ""),
            "date": session.get("created_at", "")[:16].replace("T", " "),
            "amount": session.get("amount", 0),
            "print_qty": session.get("print_qty", 0),
            "download_qty": session.get("download_qty", 0),
        })
    return results


@app.get("/qr/generate")
async def generate_qr():
    order_url = f"{BASE_URL}/order"

    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(order_url)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#3B3530", back_color="#cdc2b0")
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
