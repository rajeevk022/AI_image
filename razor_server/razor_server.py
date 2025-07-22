import os, razorpay, time
from fastapi import FastAPI, Request, HTTPException
from firebase_admin import credentials, initialize_app, db, auth

# ① Replace PROJECT-ID with your Firebase project ID
initialize_app(credentials.ApplicationDefault(),
               {"databaseURL": "https://ai-report-analyzer-594dd-default-rtdb.asia-southeast1.firebasedatabase.app/"})

KEY  = os.getenv("RZP_KEY")
SECRET = os.getenv("RZP_SECRET")
WEBHOOK_SECRET = os.getenv("RZP_WEBHOOK_SECRET")
client = razorpay.Client(auth=(KEY, SECRET))
# Price for the Pro subscription in rupees. Default is 1 for testing
# Set the PRO_PRICE environment variable to override.
PRICE = int(os.getenv("PRO_PRICE", "1"))  # INR

app = FastAPI()

@app.get("/health")
def health(): return {"ok": True}

@app.post("/create-order")
async def create_order(req: Request):
    email = (await req.json())["email"]
    order = client.order.create({"amount": PRICE*100, "currency": "INR",
                                 "receipt": email, "payment_capture": 1})
    return order

@app.post("/webhook")
async def webhook(req: Request):
    body = await req.body()
    sig  = req.headers.get("X-Razorpay-Signature", "")
    try:
        razorpay.Utility.verify_webhook_signature(body, sig, WEBHOOK_SECRET)
    except razorpay.errors.SignatureVerificationError:
        raise HTTPException(400, "Bad signature")

    data = await req.json()

    # We care only about successful capture events
    if data.get("event") == "payment.captured":
        pay   = data["payload"]["payment"]["entity"]
        status = pay.get("status")
        email  = pay.get("email")

        # Fallback to the order receipt (set to the user's email) if the
        # payment object does not include an email. Some Razorpay flows omit
        # the email field, which previously caused upgrades to fail.
        if not email:
            oid = pay.get("order_id")
            if oid:
                try:
                    order = client.order.fetch(oid)
                    email = order.get("receipt")
                except Exception:
                    email = None

        if status == "captured" and email:
            try:
                uid = auth.get_user_by_email(email).uid
            except Exception:
                uid = None

            if uid:
                valid_until = int(time.time() + 30*24*3600)     # +30 days
                db.reference(f"users/{uid}").update({
                    "plan":            "pro",
                    "upgrade":         True,
                    "report_count":    0,
                    "pro_valid_until": valid_until,
                    "email":           email,
                })
    return {"ok": True}

