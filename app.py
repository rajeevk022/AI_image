"""
AI Report Analyzer – full production build (May 2025)
-----------------------------------------------------
• Freemium 3  →  Razorpay Pro 50  (admin unlimited)
• Pointer-numbered insights
• ≥2 ≤5 charts generated dynamically based on the dataset
• Excel + PDF export  (insights + EVERY chart)
• Handles CSV/Excel files up to 50k rows
• Razorpay Checkout inline (650 px iframe)
"""

import os, time, tempfile, requests, streamlit as st, threading, base64, re
import pandas as pd, matplotlib.pyplot as plt, seaborn as sns, numpy as np, fitz, openai, pyrebase
import traceback, sys
from io import BytesIO
from dotenv import load_dotenv
from datetime import datetime, timezone   # ← missing import added
from zoneinfo import ZoneInfo, available_timezones
# ────────────────────────────────────────────────────────────────────────
from firebase_config import firebase_config
import logging

logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# ────────────────────────────────────────────────────────────────────────
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

RZP_SERVER = os.getenv("RZP_SERVER")     # e.g. https://ai-image-1n31.onrender.com
RZP_KEY_ID = os.getenv("RZP_KEY_ID")     # rzp_test_xxx / rzp_live_xxx
# Price of the Pro plan in rupees. Default is 1 for testing.
PRO_PRICE = int(os.getenv("PRO_PRICE", "1"))

ADMIN_EMAIL = "rajeevk021@gmail.com"
FREE_LIMIT  = 3
PRO_LIMIT   = 50
# Prompt template for PDF financial analysis
PDF_PROMPT_TEMPLATE = """
You are a chartered financial analyst and forensic accountant known for crisp, insight-driven writing.

# 1. Context
You receive one PDF named "{pdf_filename}".
Mine it for **actionable insights**. Typical uploads include company earnings calls, quarterly/annual reports, investor decks, or brokerage research. If the PDF is a general business document, adapt gracefully.
Give special priority to any **audited financial statements**, **balance sheets**, or **sales statements** so these sections are never overlooked.

# 2. Format your reply **exactly** like this (in markdown):

## Executive Snapshot
- One paragraph (≤ 120 words) capturing the document's essence.

## Key Facts & Figures
| Metric | Latest Quarter | Previous Quarter | YoY Change (%) | Comment |
| --- | --- | --- | --- | --- |
(Leave blank cells if data is missing.)

## Management Commentary – Five Critical Takeaways
1. …
2. …
3. …
4. …
5. …

## Sales & Profit Trend (Last 2-4 Quarters)
Describe revenue, gross margin, operating profit, and net profit trends.
If numbers exist, list them; if only qualitative hints exist, paraphrase.

## Risks & Red Flags
- Bullet each risk (regulatory, competitive, debt, governance, etc.).

## Opportunities & Catalysts
- Bullet each upside driver (new products, market expansion, cost savings, etc.).

## Valuation Talk (if data permits)
- State current valuation multiples (P/E, EV/EBITDA, P/B) versus peer averages.
- Highlight any significant divergence and possible rationale.

## Verdict – **Invest / Watch / Avoid**
Choose one call. Provide 2-3 sentences of justification.

## Disclaimer
> This analysis is for **educational purposes only** and is **not** investment advice. Always do your own research or consult a registered financial professional before acting.

# 3. Style Guide
- Be concise yet data-rich; avoid fluff.
- Use active voice and plain English accessible to non-experts.
- Cite the exact page (e.g., "(p. 12)") whenever quoting numbers or statements.
- Where the PDF is silent on a required section, write "Information not provided" rather than guessing.
- Recommend chart types based on the nature of any numbers or tables rather than using a fixed list.

# 4. Fall-back Rules
If the PDF is **not** about a public company or lacks financial data:
- Omit "Valuation Talk" and "Verdict".
- Still populate other sections with whatever information is available.

Begin now. Do **not** reveal any internal reasoning—only produce the formatted report.
"""

# Prompt used when the PDF is not recognised as a stock market/financial document
GENERIC_PROMPT_TEMPLATE = """
You are an expert document analyst. Read the PDF named "{pdf_filename}" and craft a concise summary suited to its subject matter.

Format your response in markdown:

## Overview
A short paragraph summarising the overall topic and purpose of the document.

## Key Points
- Bullet the most important facts, arguments or figures found in the text.

## Additional Notes
- Mention any notable sections, data or next steps for the reader.
- If numerical tables appear, suggest chart types that best visualise them rather than relying on a fixed set of charts.

Do not mention any internal deliberations. Begin now.
"""
# ────────────────────────────────────────────────────────────────────────
firebase = pyrebase.initialize_app(firebase_config)
auth, db = firebase.auth(), firebase.database()
# ────────────────────────────────────────────────────────────────────────
st.set_page_config("AI Report Analyzer", "📊", layout="wide")
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700&display=swap');

:root, body, .stApp{
  color-scheme: light;
  background:#fff0f6 !important;
  color:#444;
  font-family:'Poppins',sans-serif;
}

h1{
  color:#ff4f9d;font-weight:700;text-align:center;letter-spacing:.6px;
  text-shadow:0 0 6px #ff99c9,0 0 12px #ff67b3,0 0 18px #ff4f9d,
              0 2px 4px rgba(255,79,157,.25);
}

.stTextInput>div>div>input{
  border:1.5px solid #ff77b1;border-radius:10px;padding:11px;font-size:15px;
  background:#fff;color:#444;
}

.stButton>button{
  background:linear-gradient(90deg,#ff4f9d,#ff77b1);
  color:#fff;border:none;border-radius:24px;padding:10px 32px;
  font-weight:600;font-size:15px;box-shadow:0 3px 12px rgba(255,79,157,.35);
}
.stButton>button:hover{background:linear-gradient(90deg,#e0438c,#ff5fa9);}

/* Always blue text for download buttons */
.stDownloadButton>button{color:#0066ff !important;}
.stDownloadButton>button:hover{color:#0066ff !important;}

/* Blue label for file uploader */
[data-testid="stFileUploader"] label{color:#0066ff !important;}

div[data-baseweb="tab"]        button{color:#000;font-weight:600;}
div[data-baseweb="tab"][aria-selected="true"] button{color:#ff4f9d !important;font-weight:700;}
div[data-baseweb="tab-highlight"]{background:#ff4f9d !important;}
div[data-baseweb="tab"]:hover   button{color:#ff4f9d !important;}

div[data-baseweb="tab-panel"]:nth-of-type(2) .stButton>button{
  background:#fff !important;color:#ff4f9d !important;border:2px solid #ff4f9d;
}
div[data-baseweb="tab-panel"]:nth-of-type(2) .stButton>button:hover{
  background:linear-gradient(90deg,#ff4f9d,#ff77b1) !important;color:#fff !important;
}

.streamlit-expanderHeader{color:#ff4f9d !important;font-weight:600;}
.streamlit-expanderContent,* .streamlit-expanderContent{color:#444 !important;}

div[data-baseweb="tab-list"]~div{
  background:#fff;border-radius:18px;padding:32px 28px;
  box-shadow:0 4px 20px rgba(0,0,0,.1);
}

/* Neon blue styling for specific login texts */
div[data-baseweb="tab"]:nth-of-type(1) button span,
div[data-baseweb="tab"]:nth-of-type(2) button span,
div[data-baseweb="tab-panel"]:nth-of-type(1) label{
  color:#00bfff !important;
  text-shadow:0 0 6px #00bfff;
}
</style>
""",
    unsafe_allow_html=True,
)
# ────────────────────────────────────────────────────────────────────────
if "S" not in st.session_state:
    st.session_state.S = {
        "page": "login",
        "insights": "",
        "chart_paths": [],
        "custom_insights": "",
        "custom_chart_paths": [],
        "df": pd.DataFrame(),
        "pdf_text": "",
    }
S = st.session_state.S
# Toggle flags for the expression builder UI
st.session_state.setdefault("show_calc_builder", False)
st.session_state.setdefault("show_param_builder", False)
# ────────────────────────────────────────────────────────────────────────

def get_current_uid():
    """Return UID from session or look it up by email."""
    uid = S.get("uid")
    if uid:
        return uid

    email = S.get("email")
    token = S.get("token")
    if not (email and token):
        return None

    try:
        rec = (
            db.child("users")
            .order_by_child("email")
            .equal_to(email)
            .get(token)
            .val()
        )
        if isinstance(rec, dict) and rec:
            uid = next(iter(rec.keys()))
            S["uid"] = uid
            return uid
    except Exception:
        pass
    return None

def load_user(uid, silent=False):
    """Loads user plan and usage data from Realtime Database."""
    log = st.write if not silent else lambda *a, **k: None
    log(f"--- Loading user data for UID: {uid} ---")
    try:
        # Attempt to fetch data from the user's node
        log(f"Fetching data from /users/{uid}")
        token = S.get("token")
        rec = db.child("users").child(uid).get(token).val()
        log(f"Raw data fetched for {uid}: {rec}")

        # Explicitly handle the case where no data exists (rec is None)
        if rec is None:
            rec = {}
            log("No data found for user in DB, treating as empty.")

        # Check if the fetched data is actually a dictionary (or compatible)
        if not isinstance(rec, dict):
             st.error(f"Unexpected data type found for user {uid}. Expected dictionary, got {type(rec)}.")
             log(f"Attempting to proceed with empty dictionary due to unexpected type.")
             rec = {} # Fallback to empty dict

        now = int(datetime.now(tz=timezone.utc).timestamp())
        # Check if the logged-in email is the admin email
        current_email = S.get("email", "")  # Get email safely from session state

        # Ensure the email is stored in the database. Older records created
        # before this field was added may not have it, which can break the
        # webhook upgrade process that relies on email lookups.
        if current_email and rec.get("email") != current_email:
            try:
                db.child("users").child(uid).update({"email": current_email}, token)
                log(f"Stored email '{current_email}' for {uid} in DB")
            except Exception as email_e:
                log(f"Failed to store email for {uid}: {email_e}")
        if current_email == ADMIN_EMAIL:
            S.update(plan="admin", used=0, admin=True, upgrade=True)
            log(f"User {uid} ({current_email}) identified as admin.")
            log("--- load_user finished for admin ---")
            return # Exit early for admin

        # Fetch plan details from the record, defaulting if keys are missing
        is_pro      = rec.get("upgrade", False)
        valid_until = rec.get("pro_valid_until", 0)
        plan_field  = str(rec.get("plan", "")).lower()
        log(
            f"Fetched 'upgrade': {is_pro}, 'pro_valid_until': {valid_until}, "
            f"'plan': {plan_field}"
        )

        # If the plan stored in the DB explicitly says "pro" (or "premium")
        # but the upgrade flag is missing, treat the user as upgraded. This
        # helps when manual DB edits set only the plan field.
        if plan_field in ("pro", "premium") and not is_pro:
            log(
                "Plan field indicates Pro access but upgrade flag is False – "
                "auto-correcting database record"
            )
            is_pro = True
            try:
                # Ensure plan is normalized to "pro" and add a default expiry
                if valid_until <= now:
                    valid_until = int(now + 30 * 24 * 3600)
                db.child("users").child(uid).update(
                    {
                        "upgrade": True,
                        "plan": "pro",
                        "pro_valid_until": valid_until,
                    },
                    token,
                )
            except Exception as corr_e:
                log(f"Failed to update plan/upgrade for {uid}: {corr_e}")

        # If the stored expiry timestamp is in the future we should treat
        # the user as Pro even if the upgrade flag wasn't set due to a
        # webhook or database glitch. In that case, auto-correct the flag
        # so future reads remain consistent.
        if valid_until > now and not is_pro:
            log(
                "Valid Pro expiry found but upgrade flag was False – "
                "auto-correcting database record"
            )
            is_pro = True
            try:
                db.child("users").child(uid).update({"upgrade": True}, token)
            except Exception as corr_e:
                log(f"Failed to update upgrade flag for {uid}: {corr_e}")

        # Check for expired Pro plan and downgrade if necessary
        if is_pro and valid_until < now:
            log(f"Pro plan for {uid} expired (valid until {valid_until}), downgrading.")
            rec["upgrade"] = False
            rec["plan"] = "free"
            rec["report_count"] = 0 # Reset count on downgrade

            # Add error handling for the database update itself
            try:
                db.child("users").child(uid).update(rec, token)
                log(f"Successfully updated user {uid} data in DB after downgrade.")
            except Exception as update_e:
                 st.error(f"Failed to update user {uid} data in DB after downgrade attempt: {update_e}")
                 log(f"Update failed traceback:")
                 traceback.print_exc(file=sys.stderr)
            is_pro = False # Ensure is_pro reflects the new state

        # Determine the current plan and usage count
        plan = "pro" if is_pro else "free"
        # Safely get report_count, ensuring it's an int
        report_count_raw = rec.get("report_count", 0)
        used = int(report_count_raw) if isinstance(report_count_raw, (int, float)) else 0
        log(f"Calculated current plan: {plan}, reports used: {used}")

        # Check if the user just upgraded in this session (optional logic)
        # This relies on the 'upgrade' state in S potentially being different from DB state initially
        # Note: This logic might need refinement depending on when S['upgrade'] is set.
        # For now, keeping original logic but logging it.
        if is_pro and not S.get("upgrade"):
            S["just_upgraded"] = True
            log(f"User {uid} just upgraded to Pro.")

        # Update the session state with the loaded user data
        # Ensure email and uid are kept from successful authentication login_screen handles this
        S.update(plan=plan, used=used, admin=False, upgrade=is_pro)
        log(f"Session state S updated for user {uid}: {S}")
        log("--- load_user finished successfully ---")

    except Exception as e:
        # This is the catch for errors during the database fetch or data processing
        log(f"--- Exception caught in load_user for UID {uid} ---")
        log(f"Specific error: {e}")
        # Print the full traceback to the console where your Streamlit app is running
        traceback.print_exc(file=sys.stderr)
        # Display the user-friendly error message in the Streamlit app
        st.error(
            "Login succeeded, but we couldn’t fetch your plan data. "
            "Please retry or contact support."
        )
        # Removed st.stop() from here to allow outer login_screen to handle stop/rerun.



# --- Assuming these imports are at the top of your script ---
# import streamlit as st
# import pyrebase # And db is initialized
# import traceback, sys # Or import globally

# --- Assuming S is defined globally or in the surrounding scope ---
# S = st.session_state.S


def inc_usage():
    """Increments the report usage count for the current user."""
    st.write("--- Incrementing usage count ---")
    if S.get("admin"):
        st.write("User is admin, usage not tracked.")
        return
    key = get_current_uid()
    if not key:
        st.error("Cannot increment usage: User ID not found.")
        return

    # Fetch the current count from the database before incrementing to avoid simple race conditions
    # This makes the increment safer, though a transaction would be fully atomic.
    st.write(f"Fetching current report count for UID: {key} before increment.")
    try:
        token = S.get("token")
        current_rec = db.child("users").child(key).get(token).val()
        if current_rec and isinstance(current_rec, dict):
            # Safely get current_used, defaulting to 0 if missing or not numeric
            current_used = int(current_rec.get("report_count", 0)) if isinstance(current_rec.get("report_count"), (int, float)) else 0
            new_used = current_used + 1
            st.write(f"Current usage from DB: {current_used}, new usage: {new_used}")
        else:
            # Fallback if data structure is unexpected or missing for some reason
            st.write(f"Could not fetch valid current usage from DB for {key}. Falling back to incrementing session state value ({S.get('used', 0)}).")
            new_used = (S.get("used", 0) or 0) + 1 # Use session state value as fallback

    except Exception as e:
        st.error(f"Failed to fetch current usage before incrementing for {key}: {e}")
        st.write("Fetch before increment traceback:")
        traceback.print_exc(file=sys.stderr)
        # Fallback to using session state value + 1 if fetching fails
        new_used = (S.get("used", 0) or 0) + 1

    # Update the value back to the database
    try:
        db.child("users").child(key).update({"report_count": new_used}, token)
    except Exception as upd_e:
        st.error(f"Failed to update usage for {key}: {upd_e}")
        traceback.print_exc(file=sys.stderr)

    S["used"] = new_used

# ----------------------------------------------------------------------
def fetch_saved_insights() -> dict:
    """Return dict of saved custom insights for the logged in user."""
    uid = get_current_uid()
    if not uid:
        return {}
    try:
        token = S.get("token")
        rec = db.child("users").child(uid).child("insights").get(token).val()
        return rec if isinstance(rec, dict) else {}
    except Exception:
        return {}


def save_custom_insight(name: str, config: dict):
    """Persist a custom insight configuration for the logged in user."""
    uid = get_current_uid()
    if not uid or not name:
        return
    try:
        token = S.get("token")
        db.child("users").child(uid).child("insights").child(name).set(config, token)
    except Exception as e:  # noqa: BLE001
        st.error(f"Failed to save insight: {e}")

# ----------------------------------------------------------------------
def numberify(text: str) -> str:
    """Format raw insight text into numbered sentences."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    formatted = []
    for l in lines:
        l = l.lstrip("-*0123456789. ")
        if not l.endswith(('.', '!', '?')):
            l += '.'
        formatted.append(l)
    return "\n".join(f"{i+1}. {formatted[i]}" for i in range(len(formatted)))
# ----------------------------------------------------------------------
def sample_data(df, max_tokens=10000):
    """Return CSV rows fitting roughly within a token budget."""
    approx_chars_per_token = 4
    max_chars = max_tokens * approx_chars_per_token
    lines = df.to_csv(index=False).splitlines()
    header, rows = lines[0], lines[1:]
    used_rows, size, out = [], len(header) + 1, []
    for r in rows:
        row_len = len(r) + 1
        if size + row_len > max_chars:
            break
        used_rows.append(r)
        size += row_len
    out = "\n".join([header] + used_rows)
    truncated = len(used_rows) < len(rows)
    return out, len(used_rows), truncated
# ----------------------------------------------------------------------
def auto_charts(df):
    """Generate charts dynamically based on the data."""
    charts, paths = [], []
    num = df.select_dtypes("number").columns
    cat = df.select_dtypes("object").columns
    if num.any():
        f, a = plt.subplots()
        sns.histplot(df[num[0]].dropna(), ax=a, color="#ff78b3")
        a.set_title(f"Distribution of {num[0]}")
        charts.append(("Histogram", f))

    if len(num) >= 2:
        corr = df[num].corr().abs()
        np.fill_diagonal(corr.values, 0)
        pair = corr.stack().idxmax()
        f, a = plt.subplots()
        sns.scatterplot(data=df, x=pair[0], y=pair[1], ax=a, color="#ff78b3")
        a.set_title(f"{pair[1]} vs {pair[0]}")
        charts.append(("Scatter", f))

    date_cols = [c for c in df.columns if "date" in c.lower()]
    if date_cols and num.any():
        d = pd.to_datetime(df[date_cols[0]], errors="coerce")
        f, a = plt.subplots()
        sns.lineplot(x=d, y=df[num[0]], ax=a, color="#ff78b3")
        a.set_title(f"{num[0]} over time")
        charts.append(("Time Series", f))

    if cat.any():
        f, a = plt.subplots()
        df[cat[0]].value_counts().head(10).plot(kind="bar", ax=a, color="#ff78b3")
        a.set_title(f"Top {cat[0]}")
        charts.append(("Bar", f))

    if len(charts) == 1:
        charts.append(charts[0])
    for _, fig in charts[:5]:
        p = tempfile.NamedTemporaryFile(delete=False, suffix=".png").name
        fig.savefig(p, dpi=220)
        paths.append(p)
    return charts[:5], paths

# ----------------------------------------------------------------------
def generate_chart_insights(chart_type: str, data: pd.DataFrame) -> str:
    """Return 5-50 sentence insight summary for a chart."""
    try:
        desc = data.describe(include="all").to_csv()
        prompt = (
            "Provide concise insights (between 5 and 50 sentences) for a "
            f"{chart_type} chart based on the following summary:\n{desc}"
            " If there are no notable insights reply with 'No significant insights.'"
        )
        resp = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
        )["choices"][0]["message"]["content"].strip()
        if resp.lower().startswith("no significant"):
            return "No significant insights."
        if len(resp.split(".")) < 5:
            return "No significant insights."
        return resp
    except Exception:
        return "No significant insights."
# ----------------------------------------------------------------------
def to_latin1(text: str) -> str:
    return text.encode("latin-1", "replace").decode("latin-1")

# ----------------------------------------------------------------------
def is_stock_market_pdf(text: str) -> bool:
    """Rudimentary check to see if the PDF text relates to stock markets."""
    if not text:
        return False
    keywords = [
        "stock", "share", "dividend", "equity", "earnings", "quarter",
        "bse", "nse", "nasdaq", "nyse", "profit", "loss", "balance sheet",
        "income statement", "cash flow", "market cap", "ipo",
    ]
    t = text.lower()
    score = sum(kw in t for kw in keywords)
    return score >= 3
# ----------------------------------------------------------------------
def generate_custom_insights(user_prompt: str):
    """Generate insights based on a user-provided prompt."""
    if not user_prompt:
        return

    if not S["df"].empty:
        summary = S["df"].describe(include="all").to_csv()
        sample, rows_used, _ = sample_data(S["df"])
        prompt = (
            f"{user_prompt}\n\nData sample ({rows_used} rows,"
            f" {len(S['df'].columns)} columns):\n{sample}\n\nSummary statistics:\n{summary}"
        )
    elif S.get("pdf_text"):
        prompt = f"{user_prompt}\n\n{S['pdf_text'][:50000]}"
    else:
        prompt = user_prompt

    with st.spinner("Analysing …"):
        raw = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=700,
        )["choices"][0]["message"]["content"]

    charts, paths = [], []
    if not S["df"].empty:
        charts, paths = auto_charts(S["df"])

    S.update(insights=numberify(raw), chart_paths=paths)

# ----------------------------------------------------------------------
def export_excel(df, insights, paths):
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="xlsxwriter") as w:
        df.to_excel(w, index=False, sheet_name="Data")
        ws = w.book.add_worksheet("Insights")
        w.sheets["Insights"] = ws
        for i, l in enumerate(insights.splitlines()):
            ws.write(i, 0, l)
        row = len(insights.splitlines()) + 2
        for p in paths:
            ws.insert_image(row, 0, p, {"x_scale": 0.9, "y_scale": 0.9})
            row += 22
    bio.seek(0)
    return bio
# ----------------------------------------------------------------------
def export_pdf(insights, paths):
    from fpdf import FPDF

    pdf = FPDF()
    pdf.set_auto_page_break(True, 15)
    pdf.add_page()
    pdf.set_font("Arial", size=11)
    for line in insights.splitlines():
        pdf.multi_cell(0, 8, to_latin1(line))
    for p in paths:
        pdf.add_page()
        pdf.image(p, x=10, y=30, w=180)
    return BytesIO(pdf.output(dest="S").encode("latin-1"))

# ----------------------------------------------------------------------
# Basic email validation regex
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

def _invalid_emails(emails: list[str]) -> list[str]:
    """Return any email addresses that do not match ``EMAIL_PATTERN``."""
    return [e for e in emails if not EMAIL_PATTERN.fullmatch(e)]

# ----------------------------------------------------------------------
def send_email(
    to_addrs, subject: str, body: str, attachments: list[tuple[str, bytes, str]]
) -> tuple[bool, str | None]:
    """Send an email with arbitrary attachments via SMTP.

    Returns a tuple ``(success, error_message)`` so callers can surface the
    specific reason when sending fails.
    """
    server = os.getenv("SMTP_SERVER")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    pwd = os.getenv("SMTP_PASSWORD")

    # Load variables from a .env file if they weren't set already. This allows
    # ``send_email`` to be imported in isolation without the rest of ``app``
    # having run ``load_dotenv()`` beforehand.
    if not (server and user and pwd):
        load_dotenv()
        server = server or os.getenv("SMTP_SERVER")
        user = user or os.getenv("SMTP_USER")
        pwd = pwd or os.getenv("SMTP_PASSWORD")

    if isinstance(to_addrs, str):
        to_addrs = [to_addrs]
    to_addrs = [e for e in to_addrs if e]

    if not to_addrs:
        err = "No recipients provided"
        logger.error(err)
        return False, err

    bad = _invalid_emails(to_addrs)
    if bad:
        err = "Invalid email address: " + ", ".join(bad)
        logger.error(err)
        return False, err

    if not (server and user and pwd):
        missing = []
        if not server:
            missing.append("SMTP_SERVER")
        if not user:
            missing.append("SMTP_USER")
        if not pwd:
            missing.append("SMTP_PASSWORD")
        err = "Missing SMTP configuration: " + ", ".join(missing)
        logger.error(err + ": server=%s user=%s", server, user)
        return False, err

    from email.message import EmailMessage
    import smtplib

    msg = EmailMessage()
    msg["Subject"] = subject or "Report"
    msg["From"] = user
    msg["To"] = ", ".join(to_addrs)
    msg.set_content(body or "No significant insights")

    for name, data, mime in attachments:
        try:
            main, sub = mime.split("/", 1)
            msg.add_attachment(data, maintype=main, subtype=sub, filename=name)
        except Exception:
            continue

    try:
        use_ssl = os.getenv("SMTP_SSL", "0") == "1" or port == 465
        if use_ssl:
            with smtplib.SMTP_SSL(server, port) as s:
                s.login(user, pwd)
                s.send_message(msg)
        else:
            with smtplib.SMTP(server, port) as s:
                s.starttls()
                s.login(user, pwd)
                s.send_message(msg)
        return True, None
    except Exception as e:
        logger.exception(
            "Failed to send email via %s:%s as %s", server, port, user
        )
        return False, str(e)


def generate_insight_title(text: str) -> str:
    """Return a short formal title for the given insights using OpenAI."""
    prompt = (
        "Create a short formal title (max 5 words) for these insights:\n" + text[:500]
    )
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
        )
        return resp["choices"][0]["message"]["content"].strip()
    except Exception:
        return "Insights Report"


def schedule_email(to_addrs: list[str], insights: str, csv: bytes, pdf: bytes, when: datetime, tz_name: str):
    """Persist an email schedule in the database for background delivery."""
    uid = get_current_uid()
    if not uid:
        return

    bad = _invalid_emails(to_addrs)
    if bad:
        st.error("Invalid email address: " + ", ".join(bad))
        return

    token = S.get("token")
    try:
        scheduled = db.child("users").child(uid).child("scheduled_emails").get(token).val() or {}
    except Exception:
        scheduled = {}

    report_count = len(scheduled)
    email_count = sum(len(v.get("emails", [])) for v in scheduled.values())
    if report_count >= 20 or email_count + len(to_addrs) > 50:
        st.error("Schedule limit reached (20 reports / 50 emails).")
        return

    title = generate_insight_title(insights)
    event = {
        "emails": to_addrs,
        "title": title,
        "insights": insights,
        "csv": base64.b64encode(csv).decode(),
        "pdf": base64.b64encode(pdf).decode(),
        "send_at": int(when.timestamp()),
        "tz": tz_name,
        "created": int(time.time()),
    }

    try:
        db.child("users").child(uid).child("scheduled_emails").push(event, token)
        st.success("Email scheduled.")
    except Exception as e:
        st.error(f"Failed to schedule email: {e}")
# ----------------------------------------------------------------------

def expression_builder(expr_key: str, dims: list[str], metrics: list[str]):
    """Interactive helper for building expressions."""

    # Ensure the expression key exists to avoid assignment errors when
    # widgets are used before any value has been set. Streamlit will raise a
    # ``StreamlitAPIException`` if we try to assign to a non-existent key
    # in some situations, so initialise it with an empty string.
    st.session_state.setdefault(expr_key, "")

    st.markdown("**Available Fields**")
    sel_field = st.selectbox(
        "Field", dims + metrics, key=f"{expr_key}_field"
    )
    def _insert_field():
        st.session_state[expr_key] = (
            st.session_state.get(expr_key, "") + f"{sel_field} "
        )
    st.button("Insert Field", key=f"{expr_key}_field_btn", on_click=_insert_field)

    st.markdown("**Functions**")
    funcs = ["sum", "mean", "count", "max", "min", "abs", "round"]
    sel_func = st.selectbox(
        "Function", funcs, key=f"{expr_key}_func"
    )
    def _insert_func():
        st.session_state[expr_key] = (
            st.session_state.get(expr_key, "") + f"{sel_func}("
        )
    st.button(
        "Insert Function",
        key=f"{expr_key}_func_btn",
        on_click=_insert_func,
    )

    st.markdown("**Symbols**: `+` `-` `*` `/` `(` `)`")
def open_razorpay(email) -> bool:
    if not (RZP_SERVER and RZP_KEY_ID):
        st.error("Payment server not configured.")
        return False

    def create_order(timeout):
        return requests.post(f"{RZP_SERVER}/create-order", json={"email": email}, timeout=timeout)

    try:
        resp = create_order(timeout=25)
    except requests.Timeout:
        time.sleep(1.5)
        try:
            resp = create_order(timeout=10)
        except Exception as e:
            st.error(f"Order-server timeout: {e}")
            return False
    except Exception as e:
        st.error(f"Order-server error: {e}")
        return False

    try:
        order = resp.json()
    except ValueError:
        st.error("Order-server returned non-JSON response.")
        return False

    st.components.v1.html(
        f"""
        <script src="https://checkout.razorpay.com/v1/checkout.js"></script>
        <script>
          var opt = {{
            key:"{RZP_KEY_ID}",amount:"{order['amount']}",currency:"INR",
            name:"AI Report Analyzer",description:"Premium Plan (₹{PRO_PRICE})",
            order_id:"{order['id']}",prefill:{{email:"{email}"}},
            theme:{{color:"#ff4f9d"}},
            handler:function(){{
              var msg=document.createElement('p');
              msg.innerText='Payment successful!';
              msg.style='font-size:1.2rem;color:green;text-align:center;margin-top:15px;';
              document.body.appendChild(msg);
            }}
          }};
          new Razorpay(opt).open();
        </script>
        """,
        height=650,
        scrolling=False,
    )
    return True
# ----------------------------------------------------------------------
# --- Assuming these imports are at the top of your script ---
# import streamlit as st
# import pyrebase # And firebase initialization like: firebase = pyrebase.initialize_app(firebase_config); auth, db = firebase.auth(), firebase.database()
# import time # Used for time.sleep
# import traceback, sys # Or import globally

# --- Assuming S is defined globally or in the surrounding scope ---
# S = st.session_state.S

# --- Assuming load_user is defined ---
# from .your_module import load_user # If load_user is in another file


def login_screen():
    """Handles user login and account creation."""
    st.title("AI Report Analyzer")
    left, right = st.columns([0.55, 0.45], gap="large")

    IMG_URL = "https://raw.githubusercontent.com/rajeevk022/AI_image/main/AI_image.png"
    with left:
        st.image(IMG_URL, use_container_width=True)

    with right:
        tab_login, tab_signup = st.tabs(["🔐 Login", "📝 Create Account"])

        # ---------------- LOGIN TAB ----------------
        with tab_login:
            email = st.text_input("Email", key="login_email").strip()
            pwd = st.text_input("Password", type="password", key="login_pwd")

            if st.button("Sign in", key="signin_btn"):
                # Debug logs below were useful during development but
                # clutter the interface during normal use. Commented out
                # to keep the login flow clean.
                # st.write("--- Attempting Login ---")
                # st.write(f"Attempting to sign in with email: {email}")
                # ① Auth
                try:
                    user = auth.sign_in_with_email_and_password(email, pwd)
                    uid = user.get("localId")
                    token = user.get("idToken")
                    # Debug output
                    # st.write(f"Authentication successful. Received raw user data: {user}")
                    # st.write(f"Extracted UID: {uid}")
                    # Check if UID and token are present as expected by original code
                    if not (uid and "idToken" in user):
                        # st.write("Authentication response missing expected UID or idToken.")
                        raise ValueError("Authentication token or UID missing from response.")

                except Exception as auth_e:
                    # st.write(f"Authentication failed: {auth_e}")
                    traceback.print_exc(file=sys.stderr) # Print auth failure traceback
                    st.error("❌ Invalid email or password.")
                    st.stop() # Stop the app flow on auth failure

                # st.write("Authentication step completed successfully.")

                # Store email and uid in session state immediately after successful auth
                S["email"] = email
                S["uid"] = uid
                S["token"] = token
                # st.write(f"Stored email ({email}) and uid ({uid}) in session state.")


                # ② Load plan
                # st.write("Calling load_user function...")
                try:
                    # load_user function now handles its own exceptions internally
                    load_user(uid)
                    # st.write("load_user function call completed.")
                    # Check if S['plan'] and S['used'] were updated by load_user
                    if S.get('plan') is None or S.get('used') is None:
                         # st.write("Warning: Session state 'plan' or 'used' not set by load_user.")
                         pass


                except Exception as load_e:
                    # This catch block is less likely to be hit now that load_user handles
                    # its database fetch errors, but it catches anything load_user might re-raise
                    # or other unexpected errors *after* the load_user call returns.
                    # st.write(f"Unexpected exception caught after calling load_user: {load_e}")
                    traceback.print_exc(file=sys.stderr)
                    st.error(
                        "An unexpected error occurred while finalizing login. "
                        "Please retry or contact support."
                    )
                    st.stop() # Stop the app flow on this unexpected error

                # ③ Success
                # st.write("Login process considered successful based on previous steps. Updating session state for navigation.")
                # S['email'] and S['uid'] are already set above.
                S["page"] = "dash" # Set the page to dashboard
                st.success("✅ Logged in! Redirecting…")
                # st.write("--- Login successful, rerunning ---")
                time.sleep(0.5) # Add a small delay before rerunning
                st.rerun() # Rerun the app to switch to the dashboard page

        # ---------------- SIGN-UP TAB ---------------
        with tab_signup:
            new_email = st.text_input("New Email", key="su_email").strip()
            new_pwd = st.text_input("New Password", type="password", key="su_pwd")

            if st.button("Create account", key="su_btn"):
                st.write("--- Attempting Sign Up ---")
                st.write(f"Attempting to create user with email: {new_email}")
                try:
                    user = auth.create_user_with_email_and_password(new_email, new_pwd)
                    uid = user.get("localId")
                    token = user.get("idToken")
                    st.write(f"User creation successful. Received UID: {uid}")
                    st.write(f"Initializing user data in DB for UID: {uid}")
                    # Use set() to create the initial user record in the database
                    db.child("users").child(uid).set(
                        {
                            "email": new_email,
                            "plan": "free",
                            "report_count": 0,
                            "upgrade": False,
                            # You might want to add created_at timestamp here
                            "created_at": int(datetime.now(tz=timezone.utc).timestamp())
                        },
                        token
                    )
                    st.write(f"User data initialized successfully for {uid}.")
                    st.success("✅ Account created! You can now log in.")
                    st.write("--- Sign Up successful ---")
                except Exception as su_e:
                    st.write(f"Sign up failed: {su_e}")
                    traceback.print_exc(file=sys.stderr)
                    st.error("⚠️ Email already registered or invalid.")
                    st.write("--- Sign Up failed ---")

    # ---------------- POLICIES ROW -----------------
    # ... (policies expanders remain unchanged) ...
    st.markdown("<br>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)

    with c1:
        with st.expander("📜 Terms of Service"):
            st.markdown(
                "**AnalytiGlow** grants a non-transferable licence for personal or business use of AI Report Analyzer.  \n"
                "Fair-use: Free 3 / month • Pro 50 / month. Abuse or reverse-engineering is prohibited.  \n"
                "We may update pricing or terms with notice."
            )

    with c2:
        with st.expander("🔐 Privacy Policy"):
            st.markdown(
                "We collect only email & usage metrics.  \n"
                "Uploads processed in-memory, never stored.  \n"
                "Third parties: Razorpay (payments) & OpenAI (inference).  \n"
                "Contact **rajeevk021@gmail.com** • Hulimavu Bangalore - 560076, India."
            )

    with c3:
        with st.expander("💸 Refund Policy"):
            st.markdown(
                f"Full refund within **10 days** of first Pro purchase (₹{PRO_PRICE}/mo).  \n"
                "Email **rajeevk021@gmail.com** with payment ID.  \n"
                "Refund issued in 5-7 business days. No refunds after 10 days or on renewals."
            )


# ----------------------------------------------------------------------
def dashboard():
    # Always fetch latest plan/usage so any completed payment immediately
    # reflects in the UI without requiring a manual refresh.
    uid = get_current_uid()
    if uid:
        try:
            load_user(uid, silent=True)
        except Exception as e:
            st.write(f"Failed to refresh user data: {e}")

    admin = S.get("admin", False)
    plan = S.get("plan", "free")
    used = S.get("used", 0)

    sb = st.sidebar
    sb.write(f"**👤 User:** {S['email']}")

    if S.get("just_upgraded"):
        st.success(
            "✅ Payment successful! Premium access enabled for 30 days with up to 50 reports."
        )
        S["just_upgraded"] = False

    if sb.button("🏠 Home"):
        st.rerun()

    if admin:
        sb.success("Admin • Unlimited")
    elif plan == "pro":
        remaining = max(0, PRO_LIMIT - used)
        sb.success(f"✅ Premium • {remaining}/{PRO_LIMIT} reports left")
    elif plan == "free":
        sb.warning(f"Free • {FREE_LIMIT - used}/{FREE_LIMIT}")
        upgrade_disabled = S.get("upgrade_in_progress", False)
        if sb.button(
            f"💳 Upgrade to Premium (₹{PRO_PRICE})",
            disabled=upgrade_disabled,
        ):
            S["upgrade_in_progress"] = True
            open_razorpay(S["email"])

            st.info(
                "🕒 Complete payment. This page will update once the payment succeeds."
            )
            uid = get_current_uid()
            for _ in range(30):
                time.sleep(2)
                load_user(uid, silent=True)
                if S.get("upgrade"):
                    S["just_upgraded"] = True

                    S["upgrade_in_progress"] = False
                    st.rerun()
            st.warning(
                "Payment not confirmed yet. If you completed the payment, please refresh."
            )

            st.stop()

    if sb.button("🚪 Logout"):
        S.clear()
        S["page"] = "login"
        st.rerun()

    if not admin and (
        (plan == "free" and used >= FREE_LIMIT)
        or (plan == "pro" and used >= PRO_LIMIT)
    ):
        st.error("Quota exceeded – upgrade to continue.")
        return

    st.title("Dashboard")
    up = st.file_uploader("Upload CSV / Excel / PDF", ["csv", "xlsx", "pdf"])

    if not up:
        show_results()
        return

    if up.type.endswith("pdf"):
        text = "\n".join(
            p.get_text() for p in fitz.open(stream=up.read(), filetype="pdf")
        )
        if not text.strip():
            st.error("PDF appears to have no extractable text."); return

        if is_stock_market_pdf(text):
            prompt = PDF_PROMPT_TEMPLATE.format(pdf_filename=up.name)
        else:
            prompt = GENERIC_PROMPT_TEMPLATE.format(pdf_filename=up.name)

        with st.spinner("Analysing PDF …"):
            messages = [
                {"role": "system", "content": prompt},
                {"role": "user", "content": text[:50000]},
            ]
            raw = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=4096,
            )["choices"][0]["message"]["content"]
        S.update(insights=raw, chart_paths=[], df=pd.DataFrame(), pdf_text=text)
        inc_usage()
        show_results()
        return

    max_rows = 50000
    if up.name.endswith("csv"):
        df_full = pd.read_csv(up)
    else:
        df_full = pd.read_excel(up, engine="openpyxl")
    S["df"] = df_full
    pd.set_option("display.max_rows", None)
    pd.set_option("display.max_columns", None)
    st.dataframe(df_full)
    if st.button("Generate Insights"):
        analysis_df = df_full.head(max_rows)
        summary = analysis_df.describe(include="all").to_csv()
        sample, rows_used, truncated = sample_data(analysis_df)
        if len(df_full) > max_rows:
            st.warning(
                f"Dataset has {len(df_full)} rows; analysis uses first {max_rows} rows due to token limits."
            )
        prompt = (
            "You are a data analyst. "
            "Provide concise, decision-oriented insights in numbered sentences. "
            "If no strong insights are present, offer a short overall summary. "
            "Recommend charts based on the data itself rather than a fixed set.\n\n"
            f"Data sample ({rows_used} rows, {len(df_full.columns)} columns):\n{sample}\n\nSummary statistics:\n{summary}"
        )
        with st.spinner("Analysing …"):
            raw = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=700,
            )["choices"][0]["message"]["content"]
        charts, paths = auto_charts(analysis_df)
        S.update(insights=numberify(raw), chart_paths=paths, df=df_full, pdf_text="")
        inc_usage()
        show_results()
        return

    show_results()
# ----------------------------------------------------------------------
def show_results():
    st.subheader("🔍 Insights")
    prompt = st.text_area(
        "Custom Insight Prompt",
        key="custom_prompt",
        placeholder="Ask a question or request a tailored analysis...",
    )
    if st.button("Generate Custom Insights", key="custom_btn"):
        if prompt.strip():
            generate_custom_insights(prompt)
            st.rerun()
        else:
            st.warning("Please enter a prompt before generating.")

    if st.button("Create Custom Insights", key="create_custom_btn"):
        S["page"] = "custom"
        st.rerun()

    st.write(S["insights"])
    if S["chart_paths"]:
        st.subheader("📊 Charts")
        for p in S["chart_paths"]:
            st.image(p, use_container_width=True)

    if not S["df"].empty:
        st.download_button(
            "📤 Export as Excel",
            data=export_excel(S["df"], S["insights"], S["chart_paths"]),
            file_name="ai_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    st.download_button(
        "📥 Export as PDF",
        data=export_pdf(S["insights"], S["chart_paths"]),
        file_name="ai_report.pdf",
        mime="application/pdf",
    )

def custom_insights_page():
    """Interactive builder for custom charts.

    The UI mimics a drag and drop experience using multiselect widgets so users
    can pick dimensions and metrics for rows and columns. It also supports
    simple calculated fields, grouping and parameters without any extra
    dependencies.
    """
    st.title("\U0001F4C8 Custom Insights Builder")

    # --- User info and saved insights ---------------------------------
    uid = get_current_uid()
    user_rec = {}
    if uid:
        try:
            token = S.get("token")
            user_rec = db.child("users").child(uid).get(token).val() or {}
        except Exception:
            user_rec = {}

    saved = fetch_saved_insights() if uid else {}

    with st.expander("User Info"):
        st.write(f"Email: {S.get('email', '')}")
        st.write(f"Plan: {user_rec.get('plan', 'free')}")
        st.write(f"Reports used: {user_rec.get('report_count', 0)}")
        sched = user_rec.get('scheduled_emails', {})
        if sched:
            st.write("Scheduled Emails:")
            for v in sched.values():
                tz_name = v.get('tz', 'UTC')
                tz = ZoneInfo(tz_name)
                when = datetime.fromtimestamp(v.get('send_at', 0), tz=timezone.utc).astimezone(tz)
                ts = when.strftime('%Y-%m-%d %H:%M')
                st.write(f"- {', '.join(v.get('emails', []))} at {ts} ({tz_name})")

        if saved:
            names = list(saved.keys())
            choice = st.selectbox("Saved Insights", names, key="saved_list")
            if st.button("Load Insight", key="load_saved"):
                data = saved.get(choice, {})
                st.session_state.rows_sel = data.get('rows', [])
                st.session_state.cols_sel = data.get('cols', [])
                st.session_state.chart_type = data.get('chart', 'Bar')
                S["custom_insights"] = data.get('insight', '')
                st.rerun()

    if S["df"].empty:
        st.warning("Upload a dataset on the Dashboard first.")
        if st.button("Back to Dashboard"):
            S["page"] = "dash"
            st.rerun()
        return

    df = S["df"]
    dims = [c for c in df.columns if df[c].dtype == object]
    metrics = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]

    # --- Calculated fields -------------------------------------------------
    with st.expander("➕ Add Calculated Field"):
        calc_name = st.text_input("Field name")
        calc_expr = st.text_input(
            "Pandas expression (e.g. col1 + col2)", key="calc_expr"
        )
        if st.button("Calculations", key="calc_builder_btn"):
            st.session_state.show_calc_builder = not st.session_state.show_calc_builder
        if st.session_state.show_calc_builder:
            expression_builder("calc_expr", dims, metrics)
        if st.button("Add Field") and calc_name and calc_expr:
            try:
                df[calc_name] = df.eval(calc_expr)
                if pd.api.types.is_numeric_dtype(df[calc_name]):
                    metrics.append(calc_name)
                else:
                    dims.append(calc_name)
                st.success(f"Added calculated field '{calc_name}'")
            except Exception as e:  # noqa: BLE001
                st.error(f"Error computing field: {e}")

    # --- Parameters -------------------------------------------------------
    with st.expander("⚙️ Parameters"):
        p_name = st.text_input("Parameter name")
        p_val = st.text_input("Value", key="p_val")
        if st.button("Calculations", key="param_builder_btn"):
            st.session_state.show_param_builder = not st.session_state.show_param_builder
        if st.session_state.show_param_builder:
            expression_builder("p_val", dims, metrics)
        if st.button("Set Parameter") and p_name:
            S.setdefault("params", {})[p_name] = p_val
            st.success(f"Set parameter '{p_name}' = {p_val}")

    # --- Select rows/columns ---------------------------------------------
    st.subheader("Fields")
    c1, c2 = st.columns(2)
    with c1:
        rows = st.multiselect("Rows", dims, key="rows_sel")
    with c2:
        cols = st.multiselect("Columns", metrics, key="cols_sel")

    chart = st.selectbox(
        "Chart Type",
        [
            "Bar",
            "Line",
            "Area",
            "Scatter",
            "Histogram",
            "Heatmap",
            "Pie",
            "Box",
            "Violin",
        ],
        key="chart_type",
    )

    # --- Grouping ---------------------------------------------------------
    with st.expander("📂 Groups"):
        grp_dim = st.selectbox("Group by", ["None"] + dims, index=0)
        agg_metric = st.selectbox("Aggregate", metrics)
        agg_func = st.selectbox("Function", ["sum", "mean", "count", "max", "min"])
        if st.button("Create Group") and grp_dim != "None":
            grouped = (
                df.groupby(grp_dim)[agg_metric]
                .agg(agg_func)
                .reset_index()
            )
            st.dataframe(grouped)

    if rows and cols:
        data = df.groupby(rows)[cols].sum().reset_index()
        fig = plt.figure()
        if chart == "Heatmap" and len(rows) >= 2 and len(cols) == 1:
            pivot = df.pivot_table(index=rows[0], columns=rows[1], values=cols[0], aggfunc="sum")
            sns.heatmap(pivot, annot=True, cmap="RdPu")
        elif chart == "Pie" and len(rows) == 1 and len(cols) == 1:
            plt.pie(data[cols[0]], labels=data[rows[0]], autopct="%1.1f%%")
        elif chart == "Box" and len(rows) == 1:
            for c in cols:
                sns.boxplot(x=data[rows[0]], y=data[c])
        elif chart == "Violin" and len(rows) == 1:
            for c in cols:
                sns.violinplot(x=data[rows[0]], y=data[c])
        else:
            x = data[rows[0]]
            for c in cols:
                if chart == "Bar":
                    plt.bar(x, data[c], label=c)
                elif chart == "Line":
                    plt.plot(x, data[c], label=c)
                elif chart == "Area":
                    plt.fill_between(x, data[c], alpha=0.5, label=c)
                elif chart == "Scatter":
                    plt.scatter(x, data[c], label=c)
                elif chart == "Histogram":
                    sns.histplot(data[c], label=c, kde=False)
            plt.legend()
        st.pyplot(fig)
        p = tempfile.NamedTemporaryFile(delete=False, suffix=".png").name
        fig.savefig(p, dpi=220)
        S["custom_chart_paths"] = [p]
        insight = generate_chart_insights(chart, data)
        S["custom_insights"] = insight
        st.markdown(insight)
        in_name = st.text_input("Insight Name", key="insight_name")
        if st.button("Save", key="save_insight") and in_name:
            cfg = {
                "rows": rows,
                "cols": cols,
                "chart": chart,
                "insight": insight,
                "created": int(time.time()),
            }
            save_custom_insight(in_name, cfg)
            st.success("Insight saved")
    else:
        st.info("Select at least one row and one column to plot.")

    if S["custom_chart_paths"]:
        st.download_button(
            "Export Chart & Insights (Excel)",
            data=export_excel(df, S["custom_insights"], S["custom_chart_paths"]),
            file_name="custom_chart.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        st.download_button(
            "Export Chart & Insights (PDF)",
            data=export_pdf(S["custom_insights"], S["custom_chart_paths"]),
            file_name="custom_chart.pdf",
            mime="application/pdf",
        )

    with st.expander("Schedule Email"):
        to_email = st.text_input("Send to Emails (comma separated)", key="sched_email")
        send_time = st.time_input("Send at", datetime.now().time())
        tz_names = sorted(available_timezones())
        local_tz = str(datetime.now().astimezone().tzinfo)
        tz_idx = tz_names.index(local_tz) if local_tz in tz_names else tz_names.index("UTC")
        tz_choice = st.selectbox("Timezone", tz_names, index=tz_idx)
        if st.button("Schedule Email") and to_email and S["custom_chart_paths"]:
            emails = [e.strip() for e in to_email.split(',') if e.strip()]
            bad = _invalid_emails(emails)
            if bad:
                st.error("Invalid email address: " + ", ".join(bad))
            else:
                local_zone = ZoneInfo(tz_choice)
                when_local = datetime.combine(datetime.now(local_zone).date(), send_time, tzinfo=local_zone)
                when = when_local.astimezone(timezone.utc)
                csv_data = S["df"].to_csv(index=False).encode() if not S["df"].empty else b""
                pdf_data = export_pdf(S["custom_insights"], S["custom_chart_paths"]).read()
                schedule_email(emails, S["custom_insights"], csv_data, pdf_data, when, tz_choice)

        if st.button("Send Email Now") and to_email and S["custom_chart_paths"]:
            emails = [e.strip() for e in to_email.split(',') if e.strip()]
            bad = _invalid_emails(emails)
            if bad:
                st.error("Invalid email address: " + ", ".join(bad))
            else:
                csv_data = S["df"].to_csv(index=False).encode() if not S["df"].empty else b""
                pdf_data = export_pdf(S["custom_insights"], S["custom_chart_paths"]).read()
                subject = generate_insight_title(S["custom_insights"])
                attachments = [
                    ("report.csv", csv_data, "text/csv"),
                    ("report.pdf", pdf_data, "application/pdf"),
                ]
                success, err = send_email(
                    emails, subject, S["custom_insights"], attachments
                )
                if success:
                    st.success("Email sent")
                else:
                    st.error(f"Failed to send email: {err}")

    if st.button("Back", key="back_btn"):
        S["page"] = "dash"
        st.rerun()
# ----------------------------------------------------------------------
if S["page"] == "login":
    login_screen()
elif S["page"] == "custom":
    custom_insights_page()
else:
    dashboard()
