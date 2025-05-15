"""
AI Report Analyzer – full production build (May 2025)
-----------------------------------------------------
• Freemium 3  →  Razorpay Pro 300  (admin unlimited)
• Pointer‑numbered insights
• ≥2 ≤5 charts  (hist, line, bar)  auto‑generated
• Excel + PDF export  (insights + EVERY chart)
• Razorpay Checkout opens inline (650 px iframe) – fixed blank‑line bug
• openai==0.28.1 syntax
"""

import os, tempfile, requests, streamlit as st
import pandas as pd, matplotlib.pyplot as plt, seaborn as sns, fitz, openai, pyrebase
from io import BytesIO
from dotenv import load_dotenv
from firebase_config import firebase_config

# ─── ENV & CONSTANTS ────────────────────────────────────────────
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

RZP_SERVER  = os.getenv("RZP_SERVER")   # e.g. https://ai-image-1n31.onrender.com
RZP_KEY_ID  = os.getenv("RZP_KEY_ID")   # rzp_test_xxx / rzp_live_xxx

ADMIN_EMAIL      = "rajeevk021@gmail.com"
FREE_LIMIT  = 3
PRO_LIMIT = 50
# ─── Firebase init ──────────────────────────────────────────────
firebase = pyrebase.initialize_app(firebase_config)
auth, db = firebase.auth(), firebase.database()

# ─── Streamlit theming ──────────────────────────────────────────
st.set_page_config("AI Report Analyzer", "📊", layout="wide")
st.markdown(
        """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700&display=swap');
    html,body,[class*='css']{font-family:'Poppins',sans-serif;}
    body{background:linear-gradient(110deg,#fff4fa 0%,#ffffff 55%,#fff4fa 100%);}
    h1{color:#d81b60;font-weight:700;text-align:center;margin:6px 0 2px;}
    .tag{font-size:16px;color:#6f6f6f;text-align:center;margin:0 0 18px;font-style:italic;}
    .login-img img{width:100%;height:420px;object-fit:cover;border-radius:18px;box-shadow:0 4px 18px rgba(216,27,96,.25);}
    .auth-box{background:#fff;border-radius:18px;padding:36px 32px;box-shadow:0 4px 18px rgba(0,0,0,.1);}
    .stTextInput>div>div>input{border:1.4px solid #d81b60;border-radius:10px;padding:11px;font-size:15px;}
    .stButton>button{background:linear-gradient(90deg,#ff4f9d,#ff77b1);border:none;border-radius:24px;padding:10px 32px;
                     color:#fff;font-weight:600;font-size:15px;box-shadow:0 3px 14px rgba(255,79,157,.35);}
    .stButton>button:hover{background:linear-gradient(90deg,#e0438c,#ff5fa9);}
    </style>
    """, unsafe_allow_html=True)

# ─── Session shortcut ───────────────────────────────────────────
if "S" not in st.session_state:
    st.session_state.S = {"page":"login","insights":"","chart_paths":[],"df":pd.DataFrame()}
S = st.session_state.S

# ─── Firebase helpers ───────────────────────────────────────────
def load_user(email):
    key = email.replace(".", "_")
    rec = db.child("users").child(key).get().val() or {}

    if email == ADMIN_EMAIL:
        S.update(plan="admin", used=0, admin=True, upgrade=True)
    else:
        plan = "pro" if rec.get("upgrade") else "free"
        upgrade = rec.get("upgrade", False)
        report_count = rec.get("report_count", 0)

        # Force default values in DB if missing
        if "report_count" not in rec:
            db.child("users").child(key).update({"report_count": 0})
        if "upgrade" not in rec:
            db.child("users").child(key).update({"upgrade": False})
        if "plan" not in rec:
            db.child("users").child(key).update({"plan": "free"})

        if upgrade and not S.get("upgrade"):
            S["just_upgraded"] = True

        S.update(
            plan=plan,
            used=int(report_count),
            admin=False,
            upgrade=upgrade
        )




def inc_usage():
    if S.get("admin"): return
    key=S["email"].replace(".","_")
    db.child("users").child(key).update({"report_count": S["used"]+1})
    S["used"] += 1

# ─── Utility helpers ───────────────────────────────────────────
def numberify(text:str)->str:
    lines=[l.strip() for l in text.splitlines() if l.strip()]
    return "\n".join(f"{i+1}. {l.lstrip('-*0123456789. ')}" for i,l in enumerate(lines))

def auto_charts(df):
    charts, paths = [], []
    num=df.select_dtypes("number").columns
    cat=df.select_dtypes("object").columns
    if num.any():                                          # Histogram
        f,a=plt.subplots(); sns.histplot(df[num[0]].dropna(),ax=a,color="#ff78b3")
        a.set_title(f"Distribution of {num[0]}"); charts.append(("Histogram",f))
    if len(num)>=2:                                        # Line
        f,a=plt.subplots(); df.plot(x=num[0],y=num[1],ax=a,color="#ff78b3")
        a.set_title(f"{num[1]} vs {num[0]}"); charts.append(("Line chart",f))
    if cat.any():                                          # Bar
        f,a=plt.subplots(); df[cat[0]].value_counts().head(10).plot(kind="bar",ax=a,color="#ff78b3")
        a.set_title(f"Top {cat[0]}"); charts.append(("Bar chart",f))
    if len(charts)==1: charts.append(charts[0])            # ensure ≥2
    for _,fig in charts[:5]:
        p=tempfile.NamedTemporaryFile(delete=False,suffix=".png").name
        fig.savefig(p,dpi=220); paths.append(p)
    return charts[:5], paths

def export_excel(df, insights, paths):
    bio=BytesIO()
    with pd.ExcelWriter(bio,engine="xlsxwriter") as w:
        df.to_excel(w,index=False,sheet_name="Data")
        ws=w.book.add_worksheet("Insights"); w.sheets["Insights"]=ws
        for i,l in enumerate(insights.splitlines()): ws.write(i,0,l)
        row=len(insights.splitlines())+2
        for p in paths: ws.insert_image(row,0,p,{"x_scale":0.9,"y_scale":0.9}); row+=22
    bio.seek(0); return bio

def export_pdf(insights, paths):
    from fpdf import FPDF
    pdf=FPDF(); pdf.set_auto_page_break(True,15)
    pdf.add_page(); pdf.set_font("Arial",size=11)
    [pdf.multi_cell(0,8,l) for l in insights.splitlines()]
    for p in paths: pdf.add_page(); pdf.image(p,x=10,y=30,w=180)
    return BytesIO(pdf.output(dest="S").encode("latin1"))

# ─── Razorpay popup (inline 650 px) ────────────────────────────
def open_razorpay(email) -> bool:
    """Create order → open Razorpay Checkout. Handles cold‑start timeouts."""
    if not (RZP_SERVER and RZP_KEY_ID):
        st.error("Payment server not configured."); return False

    # helper to call /create-order with retry
    def create_order(timeout):
        return requests.post(f"{RZP_SERVER}/create-order",
                             json={"email": email}, timeout=timeout)

    try:
        resp = create_order(timeout=25)          # generous first call
    except requests.Timeout:
        # one quick retry (cold start usually finished by now)
        time.sleep(1.5)
        try:
            resp = create_order(timeout=10)
        except Exception as e:
            st.error(f"Order‑server timeout: {e}")
            return False
    except Exception as e:
        st.error(f"Order‑server error: {e}")
        return False

    try:
        order = resp.json()
    except ValueError:
        st.error("Order‑server returned non‑JSON response.")
        return False

    # Inject checkout (650 px iframe)
    st.components.v1.html(
        f"""
        <script src="https://checkout.razorpay.com/v1/checkout.js"></script>
        <script>
          var opt = {{
            key: "{RZP_KEY_ID}",
            amount: "{order['amount']}",
            currency: "INR",
            name: "AI Report Analyzer",
            description: "Pro Plan (₹299)",
            order_id: "{order['id']}",
            prefill: {{ email: "{email}" }},
            theme: {{ color: "#ff4f9d" }},
            handler: function () {{ window.location.reload(); }}
          }};
          new Razorpay(opt).open();
        </script>
        """,
        height=650,
        scrolling=False,
    )
    return True

# ─── Login screen with image ───────────────────────────────────
IMG_URL = "https://raw.githubusercontent.com/rajeevk022/AI_image/main/AI_image.png"

def login_screen():
    st.title("AI Report Analyzer")
    left, right = st.columns([0.55, 0.45])

    with left:
        st.image(IMG_URL, use_container_width=True)

    with right:
        st.markdown("### 🔐 Login")
        email = st.text_input("Email").strip()
        pwd = st.text_input("Password", type="password")

        if st.button("Sign in"):
            try:
                user = auth.sign_in_with_email_and_password(email, pwd)
                if "idToken" not in user:
                    raise Exception("Missing token")
                load_user(email)
                S.update(page="dash", email=email)
                st.success("✅ Logged in successfully! Redirecting...")
                time.sleep(0.5)
                st.rerun()
                st.stop()  # prevent any further execution
            except Exception as e:
                st.error("❌ Invalid credentials. Please try again.")
                st.stop()

        st.markdown("---\n### 📝 Create Account")
        new_email = st.text_input("New Email", key="su_em").strip()
        new_pwd = st.text_input("New Password", type="password", key="su_pw")

        if st.button("Create account"):
            try:
                auth.create_user_with_email_and_password(new_email, new_pwd)
                db.child("users").child(new_email.replace(".", "_")).set({
                    "plan": "free",
                    "report_count": 0,
                    "upgrade": False
                })
                st.success("✅ Account created! You can now log in.")
            except:
                st.error("❌ That email is already registered or invalid.")
        st.markdown("---\n### 📝 Create Account")
        new_email = st.text_input("New Email", key="su_em").strip()
        new_pwd = st.text_input("New Password", type="password", key="su_pw")

        if st.button("Create account"):
            try:
                auth.create_user_with_email_and_password(new_email, new_pwd)
                db.child("users").child(new_email.replace(".", "_")).set({
                    "plan": "free",
                    "report_count": 0,
                    "upgrade": False
                })
                st.success("✅ Account created! You can now log in.")
            except:
                st.error("❌ That email is already registered or invalid.")

# ─── Dashboard ────────────────────────────────────────────────
def dashboard():
    admin = S.get("admin", False)
    plan = S.get("plan", "free")
    used = S.get("used", 0)

    sb = st.sidebar
    sb.write(f"**👤 User:** {S['email']}")

    # Show upgrade success message once
    if S.get("just_upgraded"):
        st.success("✅ You have successfully upgraded to Pro!")
        S["just_upgraded"] = False

    # Sidebar buttons
    if sb.button("🏠 Home"):
        st.rerun()

    if admin:
        sb.success("Admin • Unlimited")
    elif plan == "pro":
        sb.success("✅ Pro user – 50 reports per month")
    elif plan == "free":
        sb.warning(f"Free • {FREE_LIMIT - used}/{FREE_LIMIT}")  
        if sb.button("💳 Upgrade to Pro (₹299)"):
              open_razorpay(S["email"])
              st.info("🕒 Please complete the payment. Once done, click 'Home' to refresh your status.")
              st.stop()

    if sb.button("🚪 Logout"):
        S.clear()
        S["page"] = "login"
        st.rerun()

    # Quota block for non-admins
    if not admin and (
        (plan == "free" and used >= FREE_LIMIT) or
        (plan == "pro" and used >= PRO_LIMIT)
    ):
        st.error("Quota exceeded – upgrade to continue.")
        return

    # Dashboard body
    st.title("Dashboard")
    up = st.file_uploader("Upload CSV / Excel / PDF", ["csv", "xlsx", "pdf"])

    if not up:
        if S.get("insights"): show_results()
        return

    # ── PDF Analysis ──
    if up.type.endswith("pdf"):
        text = "\n".join(p.get_text() for p in fitz.open(stream=up.read(), filetype="pdf"))
        if not text.strip():
            st.error("PDF appears to have no extractable text.")
            return
        with st.spinner("Analysing PDF …"):
            raw = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": text[:9000]}],
                max_tokens=800
            )["choices"][0]["message"]["content"]
        S.update(insights=numberify(raw), chart_paths=[], df=pd.DataFrame())
        show_results()
        inc_usage()
        return

    # ── Excel/CSV Analysis ──
    df = pd.read_csv(up) if up.name.endswith("csv") else pd.read_excel(up, engine="openpyxl")
    st.dataframe(df.head())
    if st.button("Generate Insights"):
        prompt = f"Summarise:\n{df.head(15).to_csv(index=False)}"
        with st.spinner("Analysing …"):
            raw = openai.ChatCompletion.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=700
            )["choices"][0]["message"]["content"]
        charts, paths = auto_charts(df)
        S.update(insights=numberify(raw), chart_paths=paths, df=df)
        show_results()
        inc_usage()

def show_results():
    st.subheader("🔍 Insights")
    st.write(S["insights"])
    if S["chart_paths"]:
        st.subheader("📊 Charts")
        for p in S["chart_paths"]:
            st.image(p, use_container_width=True)

    if not S["df"].empty:
        st.download_button("📤 Export as Excel",
                           data=export_excel(S["df"], S["insights"], S["chart_paths"]),
                           file_name="ai_report.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           key="export_excel_btn")

    st.download_button("📥 Export as PDF",
                       data=export_pdf(S["insights"], S["chart_paths"]),
                       file_name="ai_report.pdf",
                       mime="application/pdf",
                       key="export_pdf_btn")



# ─── Router ───────────────────────────────────────────────────
if S["page"]=="login": login_screen()
else: dashboard()
