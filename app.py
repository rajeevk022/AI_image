"""
AI Report Analyzer – full production build (May 2025)
-----------------------------------------------------
• Freemium 3  →  Razorpay Pro 50  (admin unlimited)
• Pointer-numbered insights
• ≥2 ≤5 charts  (hist, line, bar)  auto-generated
• Excel + PDF export  (insights + EVERY chart)
• Razorpay Checkout inline (650 px iframe)
"""

import os, time, tempfile, requests, streamlit as st
import pandas as pd, matplotlib.pyplot as plt, seaborn as sns, fitz, openai, pyrebase
from io import BytesIO
from dotenv import load_dotenv
from datetime import datetime, timezone   # ← missing import added
from firebase_config import firebase_config
# ────────────────────────────────────────────────────────────────────────
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

RZP_SERVER = os.getenv("RZP_SERVER")     # e.g. https://ai-image-1n31.onrender.com
RZP_KEY_ID = os.getenv("RZP_KEY_ID")     # rzp_test_xxx / rzp_live_xxx

ADMIN_EMAIL = "rajeevk021@gmail.com"
FREE_LIMIT  = 3
PRO_LIMIT   = 50
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

div[data-baseweb="tab"]        button{color:#ff4f9d !important;font-weight:600;}
div[data-baseweb="tab"][aria-selected="true"] button{font-weight:700;}
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
        "df": pd.DataFrame(),
    }
S = st.session_state.S
# ────────────────────────────────────────────────────────────────────────
def load_user(uid, token):
    rec = db.child("users").child(uid).get(token).val() or {}
    now = int(datetime.now(tz=timezone.utc).timestamp())

    if S.get("email") == ADMIN_EMAIL:
        S.update(plan="admin", used=0, admin=True, upgrade=True)
        return

    is_pro      = rec.get("upgrade", False)
    valid_until = rec.get("pro_valid_until", 0)

    if is_pro and valid_until < now:                     # expired -> downgrade
        rec.update({"upgrade": False, "plan": "free", "report_count": 0})
        db.child("users").child(uid).update(rec, token)
        is_pro = False

    plan = "pro" if is_pro else "free"
    used = int(rec.get("report_count", 0))

    if is_pro and not S.get("upgrade"):
        S["just_upgraded"] = True

    S.update(plan=plan, used=used, admin=False, upgrade=is_pro)
# ----------------------------------------------------------------------
def inc_usage():
    if S.get("admin"):
        return
    key = S.get("uid")
    new_used = S["used"] + 1
    token = S.get("token")
    db.child("users").child(key).update({"report_count": new_used}, token)
    S["used"] = new_used
# ----------------------------------------------------------------------
def numberify(text: str) -> str:
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    return "\n".join(f"{i+1}. {l.lstrip('-*0123456789. ')}" for i, l in enumerate(lines))
# ----------------------------------------------------------------------
def auto_charts(df):
    charts, paths = [], []
    num = df.select_dtypes("number").columns
    cat = df.select_dtypes("object").columns
    if num.any():
        f, a = plt.subplots()
        sns.histplot(df[num[0]].dropna(), ax=a, color="#ff78b3")
        a.set_title(f"Distribution of {num[0]}")
        charts.append(("Histogram", f))
    if len(num) >= 2:
        f, a = plt.subplots()
        df.plot(x=num[0], y=num[1], ax=a, color="#ff78b3")
        a.set_title(f"{num[1]} vs {num[0]}")
        charts.append(("Line chart", f))
    if cat.any():
        f, a = plt.subplots()
        df[cat[0]].value_counts().head(10).plot(kind="bar", ax=a, color="#ff78b3")
        a.set_title(f"Top {cat[0]}")
        charts.append(("Bar chart", f))
    if len(charts) == 1:
        charts.append(charts[0])
    for _, fig in charts[:5]:
        p = tempfile.NamedTemporaryFile(delete=False, suffix=".png").name
        fig.savefig(p, dpi=220)
        paths.append(p)
    return charts[:5], paths
# ----------------------------------------------------------------------
def to_latin1(text: str) -> str:
    return text.encode("latin-1", "replace").decode("latin-1")
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
            name:"AI Report Analyzer",description:"Pro Plan (₹299)",
            order_id:"{order['id']}",prefill:{{email:"{email}"}},
            theme:{{color:"#ff4f9d"}},
            handler:function(){{window.location.reload();}}
          }};
          new Razorpay(opt).open();
        </script>
        """,
        height=650,
        scrolling=False,
    )
    return True
# ----------------------------------------------------------------------
def login_screen():
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
                # ① Auth
                try:
                    user = auth.sign_in_with_email_and_password(email, pwd)
                    uid = user.get("localId")
                    token = user.get("idToken")
                    if not (uid and token):
                        raise ValueError("token missing")
                except Exception:
                    st.error("❌ Invalid email or password.")
                    st.stop()

                # ② Load plan
                try:
                    load_user(uid, token)
                except Exception as e:
                    import traceback, sys

                    traceback.print_exc(file=sys.stderr)
                    st.error(
                        "Login succeeded, but we couldn’t fetch your plan data. "
                        "Please retry or contact support."
                    )
                    st.stop()

                # ③ Success
                S.update(page="dash", email=email, uid=uid, token=token)
                st.success("✅ Logged in! Redirecting…")
                time.sleep(0.5)
                st.rerun()

        # ---------------- SIGN-UP TAB ---------------
        with tab_signup:
            new_email = st.text_input("New Email", key="su_email").strip()
            new_pwd = st.text_input("New Password", type="password", key="su_pwd")

            if st.button("Create account", key="su_btn"):
                try:
                    user = auth.create_user_with_email_and_password(new_email, new_pwd)
                    uid = user.get("localId")
                    token = user.get("idToken")
                    db.child("users").child(uid).set(
                        {
                            "email": new_email,
                            "plan": "free",
                            "report_count": 0,
                            "upgrade": False,
                        }
                    , token)
                    st.success("✅ Account created! You can now log in.")
                except Exception:
                    st.error("⚠️ Email already registered or invalid.")

    # ---------------- POLICIES ROW -----------------
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
                "Full refund within **10 days** of first Pro purchase (₹299/mo).  \n"
                "Email **rajeevk021@gmail.com** with payment ID.  \n"
                "Refund issued in 5-7 business days. No refunds after 10 days or on renewals."
            )
# ----------------------------------------------------------------------
def dashboard():
    admin = S.get("admin", False)
    plan = S.get("plan", "free")
    used = S.get("used", 0)

    sb = st.sidebar
    sb.write(f"**👤 User:** {S['email']}")

    if S.get("just_upgraded"):
        st.success("✅ You have successfully upgraded to Pro!")
        S["just_upgraded"] = False

    if sb.button("🏠 Home"):
        st.rerun()

    if admin:
        sb.success("Admin • Unlimited")
    elif plan == "pro":
        remaining = max(0, PRO_LIMIT - used)
        sb.success(f"✅ Pro • {remaining}/{PRO_LIMIT} reports left")
    elif plan == "free":
        sb.warning(f"Free • {FREE_LIMIT - used}/{FREE_LIMIT}")
        if sb.button("💳 Upgrade to Pro (₹299)"):
            open_razorpay(S["email"])
            st.info("🕒 Complete payment, then click 'Home' to refresh status.")
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
        if S.get("insights"):
            show_results()
        return

    if up.type.endswith("pdf"):
        text = "\n".join(
            p.get_text() for p in fitz.open(stream=up.read(), filetype="pdf")
        )
        if not text.strip():
            st.error("PDF appears to have no extractable text."); return
        with st.spinner("Analysing PDF …"):
            raw = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": text[:9000]}],
                max_tokens=800,
            )["choices"][0]["message"]["content"]
        S.update(insights=numberify(raw), chart_paths=[], df=pd.DataFrame())
        show_results(); inc_usage(); return

    df = pd.read_csv(up) if up.name.endswith("csv") else pd.read_excel(up, engine="openpyxl")
    st.dataframe(df.head())
    if st.button("Generate Insights"):
        prompt = f"Summarise:\n{df.head(15).to_csv(index=False)}"
        with st.spinner("Analysing …"):
            raw = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=700,
            )["choices"][0]["message"]["content"]
        charts, paths = auto_charts(df)
        S.update(insights=numberify(raw), chart_paths=paths, df=df)
        show_results(); inc_usage()
# ----------------------------------------------------------------------
def show_results():
    st.subheader("🔍 Insights")
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
# ----------------------------------------------------------------------
if S["page"] == "login":
    login_screen()
else:
    dashboard()
