"""
AI Report Analyzer – Bullet‑list & Multi‑chart export build
• Numbered insights in UI + Excel + PDF
• Exports every chart
• Insights persist after Export buttons are pressed
"""
import os, tempfile, requests, streamlit as st
import pandas as pd, matplotlib.pyplot as plt, seaborn as sns, fitz, openai, pyrebase
from io import BytesIO
from dotenv import load_dotenv
from firebase_config import firebase_config

# ─── 1. ENV / CONSTANTS ──────────────────────────────────────
load_dotenv()
openai.api_key  = os.getenv("OPENAI_API_KEY")

RZP_SERVER      = os.getenv("RZP_SERVER")
RZP_KEY_ID      = os.getenv("RZP_KEY_ID")

ADMIN_EMAIL     = "rajeevk021@gmail.com"
FREE_LIMIT      = 3
PRO_LIMIT       = 300

# ─── 2. Firebase ─────────────────────────────────────────────
firebase = pyrebase.initialize_app(firebase_config)
auth, db = firebase.auth(), firebase.database()

# ─── 3. Page style (unchanged) ───────────────────────────────
st.set_page_config("AI Report Analyzer", "💖", layout="wide")
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
    """,
    unsafe_allow_html=True,
)

# ─── 4. Session state defaults ───────────────────────────────
if "state" not in st.session_state:
    st.session_state.state = {
        "page": "login",
        "insights": "",
        "chart_paths": []
    }
S = st.session_state.state

# ─── 5. Firebase helpers ─────────────────────────────────────
def load_user(email: str):
    if email == ADMIN_EMAIL:
        S.update(plan="admin", used=0, admin=True)
    else:
        key = email.replace(".", "_")
        rec = db.child("users").child(key).get().val() or {}
        S.update(plan=rec.get("plan", "free"),
                 used=rec.get("report_count", 0),
                 admin=False)

def increment_usage():
    if S.get("admin"): return
    key = S["email"].replace(".", "_")
    db.child("users").child(key).update({"report_count": S["used"] + 1})
    S["used"] += 1

# ─── 6. Helpers: insights formatting & exports ───────────────
def numberify(text: str) -> str:
    """convert any bullet or dash lines into '1. 2. 3.' numbered list"""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    numbered = [f"{i+1}. {l.lstrip('-*0123456789. ')}"
                for i, l in enumerate(lines)]
    return "\n".join(numbered)

def export_excel(df, insights:str, chart_paths:list):
    bio = BytesIO()
    with pd.ExcelWriter(bio, engine="xlsxwriter") as w:
        df.to_excel(w, sheet_name="Data", index=False)
        ws = w.book.add_worksheet("Insights"); w.sheets["Insights"] = ws
        for i, line in enumerate(insights.splitlines()): ws.write(i, 0, line)
        row = len(insights.splitlines()) + 2
        for cp in chart_paths:
            ws.insert_image(row, 0, cp, {"x_scale": 0.9, "y_scale": 0.9})
            row += 22
    bio.seek(0); return bio

def export_pdf(insights:str, chart_paths:list):
    from fpdf import FPDF
    pdf = FPDF(); pdf.set_auto_page_break(True, 15)
    pdf.add_page(); pdf.set_font("Arial", size=11)
    for l in insights.splitlines(): pdf.multi_cell(0, 8, l)
    for cp in chart_paths:
        pdf.add_page(); pdf.image(cp, x=10, y=30, w=180)
    return BytesIO(pdf.output(dest="S").encode("latin1"))

# ─── 7. Chart generator (returns figs & saved paths) ─────────
def smart_charts(df):
    charts, paths = [], []
    num = df.select_dtypes("number").columns
    cat = df.select_dtypes("object").columns

    if num.any():
        f, ax = plt.subplots(); sns.histplot(df[num[0]], ax=ax, color="#ff78b3")
        ax.set_title(f"Distribution of {num[0]}"); charts.append(("Histogram", f))
    if len(num) >= 2:
        f, ax = plt.subplots(); df.plot(x=num[0], y=num[1], ax=ax, color="#ff78b3")
        ax.set_title(f"{num[1]} vs {num[0]}"); charts.append(("Line chart", f))
    if cat.any():
        f, ax = plt.subplots(); df[cat[0]].value_counts().head(10).plot(kind="bar", ax=ax, color="#ff78b3")
        ax.set_title(f"Top {cat[0]}"); charts.append(("Bar chart", f))

    for title, fig in charts:
        path = tempfile.NamedTemporaryFile(delete=False, suffix=".png").name
        fig.savefig(path, dpi=220)
        paths.append(path)
    return charts, paths

# ─── 8. Razorpay pop‑up (unchanged) ──────────────────────────
def open_razorpay(email):
    if not (RZP_SERVER and RZP_KEY_ID):
        st.error("Payment server not configured."); return
    order = requests.post(f"{RZP_SERVER}/create-order", json={"email": email}).json()
    st.components.v1.html(f"""
        <script src="https://checkout.razorpay.com/v1/checkout.js"></script>
        <script>
        var o={{key:"{RZP_KEY_ID}",amount:"{order['amount']}",currency:"INR",
                 name:"AI Report Analyzer",description:"Pro (₹299)",order_id:"{order['id']}",
                 prefill:{{email:"{email}"}},theme:{{color:"#ff4f9d"}},
                 handler:function(){{window.location.reload();}}}};
        new Razorpay(o).open();
        </script>""", height=1)

# ─── 9. Login UI (small tweaks) ──────────────────────────────
def login_ui():
    st.markdown("<h1>AI Report Analyzer</h1>", unsafe_allow_html=True)
    st.markdown("<p class='tag'>AI‑powered analytics at your fingertips ✨</p>", unsafe_allow_html=True)
    l, r = st.columns([0.4, 0.6], gap="medium")

    with l:
        st.markdown("<div class='login-img'>", unsafe_allow_html=True)
        st.image("https://raw.githubusercontent.com/rajeevk022/AI_image/main/AI_image.png", use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with r:
        st.markdown("<div class='auth-box'>", unsafe_allow_html=True)
        tabL, tabS = st.tabs(["Login", "Sign‑Up"])
        with tabL:
            with st.form("login"):
                email = st.text_input("Email", key="lg_email").strip()
                pwd = st.text_input("Password", type="password", key="lg_pwd")
                ok = st.form_submit_button("Sign in")
            if ok:
                if not email or not pwd:
                    st.error("Enter email & password.")
                else:
                    try:
                        auth.sign_in_with_email_and_password(email, pwd)
                        S.update(page="dash", email=email); load_user(email); st.rerun()
                    except: st.error("Invalid credentials")
        with tabS:
            with st.form("signup"):
                em = st.text_input("Email", key="su_email").strip()
                pw = st.text_input("Password", type="password", key="su_pwd")
                ok = st.form_submit_button("Create account")
            if ok:
                if not em or not pw:
                    st.error("Fill both fields.")
                else:
                    try:
                        auth.create_user_with_email_and_password(em, pw)
                        db.child("users").child(em.replace(".", "_")).set({"plan": "free", "report_count": 0})
                        st.success("Account created – please log in.")
                    except: st.error("Email already registered")
        st.markdown("</div>", unsafe_allow_html=True)

# ─── 10. Dashboard ───────────────────────────────────────────
def dashboard():
    admin = S.get("admin", False); plan = S.get("plan", "free"); used = S.get("used", 0)
    sb = st.sidebar
    sb.write(f"User: **{S['email']}**")
    if admin: sb.success("Admin • Unlimited")
    elif plan == "free":
        sb.warning(f"Free • {FREE_LIMIT - used}/{FREE_LIMIT}")
        if sb.button("Upgrade to Pro (₹299)"): open_razorpay(S["email"]); st.stop()
    else:
        sb.success(f"Pro • {used}/{PRO_LIMIT}")

    if sb.button("Logout"):
        S["page"] = "login"; st.rerun()

    # Quota check
    if not admin and ((plan == "free" and used >= FREE_LIMIT) or (plan == "pro" and used >= PRO_LIMIT)):
        st.error("Quota exceeded – upgrade or wait."); return

    st.title("Dashboard")
    up = st.file_uploader("Upload CSV / Excel / PDF", ["csv", "xlsx", "pdf"])
    if not up:  # Show previous results if any
        if S.get("insights"):
            st.subheader("🔍 Insights"); st.write(S["insights"])
            if S.get("chart_paths"):
                st.subheader("📊 Charts")
                for cp in S["chart_paths"]: st.image(cp, use_container_width=True)
                export_buttons()
        return

    # ---------------- PDF -----------------
    if up.type.endswith("pdf"):
        text = "\n".join(p.get_text() for p in fitz.open(stream=up.read(), filetype="pdf"))
        if not text.strip(): st.error("PDF has no extractable text."); return
        with st.spinner("Summarising PDF …"):
            out = openai.ChatCompletion.create(model="gpt-4o",
                messages=[{"role": "user", "content": text[:9000]}], max_tokens=850)["choices"][0]["message"]["content"]
        S.update(insights=numberify(out), chart_paths=[])
        st.subheader("🔍 Insights"); st.write(S["insights"]); export_buttons(); increment_usage(); return

    # ---------------- CSV / Excel -----------------
    df = pd.read_csv(up) if up.name.endswith("csv") else pd.read_excel(up, engine="openpyxl")
    st.dataframe(df.head())

    if st.button("Generate Insights"):
        with st.spinner("Analysing …"):
            prompt = f"Summarise:\n{df.head(15).to_csv(index=False)}"
            raw = openai.ChatCompletion.create(model="gpt-4o",
                messages=[{"role": "user", "content": prompt}], max_tokens=750)["choices"][0]["message"]["content"]
        insights = numberify(raw)
        charts, paths = smart_charts(df)
        S.update(insights=insights, chart_paths=paths, df=df)
        # Display
        st.subheader("🔍 Insights"); st.write(insights)
        st.subheader("📊 Charts")
        for title, fig in charts: st.write(f"**{title}**"); st.pyplot(fig)
        export_buttons()
        increment_usage()

def export_buttons():
    if not S.get("insights"): return
    st.download_button("Export Excel",
        export_excel(S["df"], S["insights"], S["chart_paths"]),
        "report.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.download_button("Export PDF",
        export_pdf(S["insights"], S["chart_paths"]), "report.pdf")

# ─── 11. Router ──────────────────────────────────────────────
if S["page"] == "login":
    login_ui()
else:
    dashboard()
