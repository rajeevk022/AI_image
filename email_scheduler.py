import time, os, base64
from firebase_config import firebase_config
import pyrebase
from app import send_email
import logging

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

firebase = pyrebase.initialize_app(firebase_config)
auth, db = firebase.auth(), firebase.database()

# Expect EMAIL_SCHEDULER_TOKEN env for authentication
TOKEN = os.getenv("FIREBASE_TOKEN")

while True:
    try:
        users = db.child("users").get(TOKEN).val() or {}
        now_ts = int(time.time())
        for uid, rec in users.items():
            schedules = rec.get("scheduled_emails", {})
            for key, ev in list(schedules.items()):
                if ev.get("send_at", 0) <= now_ts:
                    attachments = []
                    if ev.get("csv"):
                        attachments.append(("report.csv", base64.b64decode(ev["csv"]), "text/csv"))
                    if ev.get("pdf"):
                        attachments.append(("report.pdf", base64.b64decode(ev["pdf"]), "application/pdf"))
                    subject = ev.get("title", "Insights Report")
                    success = send_email(
                        ev.get("emails", []), subject, ev.get("insights", ""), attachments
                    )
                    if success:
                        logger.info("Sent scheduled email to %s", ev.get("emails", []))
                    else:
                        logger.error("Failed to send scheduled email to %s", ev.get("emails", []))
                    db.child("users").child(uid).child("scheduled_emails").child(key).remove(TOKEN)
    except Exception as e:
        logger.exception("Scheduler error: %s", e)
    time.sleep(60)
