import os
import razorpay
import time
from fastapi import FastAPI, Request, HTTPException, status
from firebase_admin import credentials, initialize_app, db, auth
from datetime import datetime, timezone
import logging
import traceback
import sys # Import sys for printing full tracebacks

# --- Logging Setup ---
# Configure logging to see detailed messages in your server's logs
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Environment Variables ---
# Fetch all critical environment variables at the top
RZP_KEY = os.getenv("RZP_KEY")
RZP_SECRET = os.getenv("RZP_SECRET")

# Apply .strip() immediately upon retrieval to eliminate any hidden leading/trailing whitespace
_raw_webhook_secret = os.getenv("RZP_WEBHOOK_SECRET")
RZP_WEBHOOK_SECRET = _raw_webhook_secret.strip() if _raw_webhook_secret else None


# --- Critical Startup Checks for Environment Variables ---
if not all([RZP_KEY, RZP_SECRET, RZP_WEBHOOK_SECRET]):
    logger.critical("CRITICAL ERROR: Missing one or more required environment variables (RZP_KEY, RZP_SECRET, RZP_WEBHOOK_SECRET).")
    logger.critical("Please set these securely on your production environment (Render dashboard -> Environment).")
    # In a real production scenario, you might want to exit if not configured
    # sys.exit(1) # Uncomment if you want the app to crash on missing env vars

if not RZP_WEBHOOK_SECRET:
    logger.critical("CRITICAL ERROR: RZP_WEBHOOK_SECRET is not set at startup. Webhook verification will fail!")
else:
    logger.info(f"RZP_WEBHOOK_SECRET present at startup. Length: {len(RZP_WEBHOOK_SECRET)}")


# --- Firebase Admin SDK Initialization ---
# IMPORTANT: This uses Application Default Credentials.
# Ensure your server environment (e.g., Render) has access to your Firebase project.
# The service account needs "Firebase Realtime Database Admin" and "Firebase Authentication Admin" roles.
try:
    # Ensure databaseURL matches your project's default RTDB instance
    initialize_app(credentials.ApplicationDefault(),
                   {"databaseURL": "https://ai-report-analyzer-594dd-default-rtdb.asia-southeast1.firebasedatabase.app/"})
    logger.info("Firebase Admin SDK initialized successfully.")
except Exception as e:
    logger.critical(f"Failed to initialize Firebase Admin SDK: {e}")
    logger.critical("Ensure GOOGLE_APPLICATION_CREDENTIALS is set in Render's environment variables and service account has proper permissions.")
    sys.exit(1) # Exit if Firebase cannot initialize, as it's a core dependency

# --- Razorpay Client Initialization ---
try:
    client = razorpay.Client(auth=(RZP_KEY, RZP_SECRET))
    logger.info("Razorpay client initialized.")
except Exception as e:
    logger.critical(f"Failed to initialize Razorpay client: {e}")
    sys.exit(1) # Exit if Razorpay client cannot initialize

# Price for the Pro subscription in rupees (in the smallest currency unit, e.g., paise).
PRO_PRICE_INR = int(os.getenv("PRO_PRICE", "1")) # This is the price in whole rupees (ensure it's set on Render)
PRO_PRICE_PAISE = PRO_PRICE_INR * 100 # Razorpay expects amount in paise

logger.info(f"Configured PRO_PRICE: {PRO_PRICE_INR} INR ({PRO_PRICE_PAISE} paise).")

app = FastAPI()

# --- Health Check Endpoint ---
@app.get("/health")
def health():
    """Simple health check endpoint to confirm the server is running."""
    logger.info("Health check requested.")
    return {"ok": True, "message": "AI Report Analyzer Razorpay Backend is healthy."}

# --- Create Order Endpoint ---
@app.post("/create-order")
async def create_order(req: Request):
    """
    Creates a Razorpay order.
    The user's email is passed in the order notes for better webhook reliability.
    """
    try:
        data = await req.json()
        email = data.get("email")

        if not email:
            logger.error("create-order: Request received without an 'email' field.")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email is required to create an order.")

        # Pass the user's email in the `notes` field of the order.
        # This is CRUCIAL for identifying the user later in the webhook.
        notes = {"user_email": email}

        order = client.order.create({
            "amount": PRO_PRICE_PAISE,  # Amount in smallest currency unit (e.g., paise for INR)
            "currency": "INR",
            "receipt": email,           # Good practice to set the receipt for Razorpay's records
            "payment_capture": 1,       # Auto-capture payment upon success
            "notes": notes              # IMPORTANT: Include user_email here
        })
        logger.info(f"Order {order['id']} created successfully for email: {email}.")
        return order
    except Exception as e:
        logger.exception(f"ERROR: Failed to create Razorpay order for email {email}: {e}") # Uses exception for traceback
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create Razorpay order: {e}")

# --- Webhook Endpoint ---
@app.post("/webhook")
async def webhook(req: Request):
    """
    Handles Razorpay webhook events to update user status in Firebase Realtime Database.
    This endpoint MUST be publicly accessible and registered in your Razorpay Dashboard.
    """
    body = await req.body()
    sig = req.headers.get("X-Razorpay-Signature", "")
    event_type = req.headers.get("X-Razorpay-Event")

    logger.info(f"Webhook received. Event: '{event_type}'. Signature present: {bool(sig)}.")

    # --- CRITICAL DEBUGGING LINES FOR RZP_WEBHOOK_SECRET ---
    # These logs will show what value RZP_WEBHOOK_SECRET holds when the webhook function is called.
    logger.info(f"DEBUG (inside webhook): RZP_WEBHOOK_SECRET type: {type(RZP_WEBHOOK_SECRET)}")
    # IMPORTANT: Updated log message to confirm length AFTER stripping
    logger.info(f"DEBUG (inside webhook): RZP_WEBHOOK_SECRET value length (after strip): {len(RZP_WEBHOOK_SECRET) if RZP_WEBHOOK_SECRET else 0}")
    if RZP_WEBHOOK_SECRET:
        # Mask the secret for security in logs, but show its start/end
        logger.info(f"DEBUG (inside webhook): RZP_WEBHOOK_SECRET (masked): {RZP_WEBHOOK_SECRET[:3]}...{RZP_WEBHOOK_SECRET[-3:]}")
    else:
        logger.error("DEBUG (inside webhook): RZP_WEBHOOK_SECRET is None or empty at webhook call time! This will cause verification to fail.")
        # Raise an immediate HTTP 500 error if the secret is truly missing here
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server webhook secret is not configured correctly.")
    # --- END CRITICAL DEBUGGING LINES ---


    # --- 1. Verify Webhook Signature ---
    # This is a critical security step to ensure the webhook is from Razorpay.
    if not sig:
        logger.warning("Webhook received with no X-Razorpay-Signature header. Skipping verification.")
        # For security, you might want to raise an error here and not return 200 OK.
        # But for debugging, we'll let it proceed to hit the verify_webhook_signature call.
        # raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing X-Razorpay-Signature header.")

    try:
        # This is the line that was causing the TypeError if RZP_WEBHOOK_SECRET was invalid
        razorpay.Utility.verify_webhook_signature(body, sig, RZP_WEBHOOK_SECRET)
        logger.info("Webhook signature verified successfully.")
    except razorpay.errors.SignatureVerificationError:
        logger.error("CRITICAL ERROR: Webhook signature verification failed! Possible tampering or incorrect secret.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad signature.") # Bad signature means reject request
    except Exception as e:
        logger.exception(f"CRITICAL ERROR: An unexpected exception occurred during webhook signature verification: {e}")
        # Return 500 internal server error for other unexpected errors during verification
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Internal error during signature verification: {e}")

    data = await req.json()

    # --- 2. Check Event Type ---
    # We are primarily interested in successful payment/order events.
    # 'order.paid' is often more direct for subscriptions.
    if event_type == "payment.captured" or event_type == "order.paid":
        logger.info(f"Processing relevant event type: '{event_type}'.")

        # --- 3. Reliable User Email Extraction ---
        user_email = None
        order_id_from_webhook = None

        # Prioritize 'order.paid' event data as it directly contains order notes
        if event_type == "order.paid":
            order_entity = data.get("payload", {}).get("order", {}).get("entity", {})
            user_email = order_entity.get("notes", {}).get("user_email")
            order_id_from_webhook = order_entity.get("id")
            logger.info(f"Extracted from 'order.paid' event: email='{user_email}', order_id='{order_id_from_webhook}'.")

        # Fallback for 'payment.captured' or if email wasn't in 'order.paid' notes
        if not user_email and "payment" in data.get("payload", {}):
            pay_entity = data["payload"]["payment"]["entity"]
            user_email = pay_entity.get("email")
            # Use already extracted order_id if present, else get from payment entity
            order_id_from_webhook = pay_entity.get("order_id") if not order_id_from_webhook else order_id_from_webhook
            logger.info(f"Extracted from payment entity: email='{user_email}', order_id='{order_id_from_webhook}'.")

        # Last resort: Fetch order details from Razorpay API if email is still missing
        if not user_email and order_id_from_webhook:
            try:
                logger.info(f"Attempting to fetch order '{order_id_from_webhook}' from Razorpay API for email.")
                order_from_api = client.order.fetch(order_id_from_webhook)
                user_email = order_from_api.get("receipt")
                logger.info(f"Successfully fetched email '{user_email}' from Razorpay API for order '{order_id_from_webhook}'.")
            except Exception as e:
                logger.exception(f"ERROR: Failed to fetch order '{order_id_from_webhook}' from Razorpay API: {e}")
                user_email = None # Ensure email is None if API call fails

        if not user_email:
            logger.error("Could not reliably extract user email from webhook payload after all attempts. Cannot proceed with update.")
            # Important: Always return 200 OK to Razorpay to prevent re-delivery attempts,
            # even if we can't process it. Log the error for manual investigation.
            return {"ok": False, "message": "User email not found in webhook payload"}, status.HTTP_200_OK

        logger.info(f"Identified user email for potential upgrade: '{user_email}'.")

        # --- 4. Find User UID in Firebase ---
        uid = None
        try:
            # First, try to get UID from Firebase Authentication (most direct and canonical)
            firebase_user = auth.get_user_by_email(user_email)
            uid = firebase_user.uid
            logger.info(f"UID found via Firebase Auth: '{uid}'.")
        except Exception as e_auth:
            logger.warning(f"User '{user_email}' not found in Firebase Authentication directly ({e_auth}). Attempting Realtime Database lookup.")
            # Fallback to Realtime Database lookup (if not found in Auth or user registered without Auth)
            try:
                # Query RTDB for user by email. Assumes email is stored under user's UID node.
                snapshot = db.reference("users") \
                    .order_by_child("email") \
                    .equal_to(user_email).get()

                if isinstance(snapshot, dict) and snapshot:
                    uid = next(iter(snapshot.keys())) # Get the first (and hopefully only) matching UID
                    logger.info(f"UID found via Realtime Database query: '{uid}'.")
                else:
                    logger.warning(f"User '{user_email}' not found in Realtime Database either (snapshot empty or not dict).")
            except Exception as e_db:
                logger.exception(f"ERROR: Realtime Database lookup failed for '{user_email}': {e_db}")

        if not uid:
            logger.error(f"Final: Could not determine UID for email '{user_email}'. Cannot update user status.")
            return {"ok": False, "message": f"UID not found for email: {user_email}"}, status.HTTP_200_OK

        # --- 5. Update User Status in Firebase Realtime Database ---
        try:
            # Calculate expiry time for Pro plan (e.g., 30 days from now)
            # Use timezone.utc for consistent, epoch timestamps across systems.
            valid_until_timestamp = int(datetime.now(tz=timezone.utc).timestamp() + 30 * 24 * 3600) # +30 days in seconds

            updates = {
                "plan": "pro",             # Set plan to "pro"
                "upgrade": True,           # Mark as upgraded
                "report_count": 0,         # Reset usage count for the new Pro period
                "pro_valid_until": valid_until_timestamp, # Set expiry timestamp (epoch seconds)
                "email": user_email,       # Ensure email is consistently stored for future lookups
            }

            db.reference(f"users/{uid}").update(updates)
            logger.info(f"SUCCESS: User '{user_email}' (UID: {uid}) successfully updated to Pro plan in Firebase RTDB.")

        except Exception as e_update:
            logger.exception(f"CRITICAL ERROR: Failed to update user '{user_email}' (UID: {uid}) in Firebase Realtime Database: {e_update}")
            return {"ok": False, "message": "Failed to update Firebase"}, status.HTTP_200_OK

    else:
        logger.info(f"Received webhook event '{event_type}' but it is not handled by this function. Ignoring.")

    # --- 6. Always Return 200 OK to Razorpay ---
    # This is crucial. If you don't return 200, Razorpay will keep retrying the webhook.
    return {"ok": True}, status.HTTP_200_OK
