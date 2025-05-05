"""
AI Report Analyzer – Hardened build (May 2025)
• Admin unlimited
• Free (3) ➜ Razorpay Pro (300)
• Login bug fixed (st.rerun replaces deprecated experimental_rerun)
"""
import os, tempfile, requests, streamlit as st
import pandas as pd, matplotlib.pyplot as plt, fitz, openai, pyrebase
from io import BytesIO
from dotenv import load_dotenv
from firebase_config import firebase_config

# ── 1. ENV & CONSTANTS ───────────────────────────────────────
load_dotenv()
openai.api_key  = os.getenv("OPENAI_API_KEY")
RZP_SERVER      = os.getenv("RZP_SERVER")      # e.g. https://razor-srv.onrender.com
RZP_KEY_ID      = os.getenv("RZP_KEY_ID")      # rzp_test_xxx

FREE_LIMIT      = 3
PRO_LIMIT       = 300
ADMIN_EMAIL     = "rajeevk021@gmail.com"

# ── 2. Firebase ──────────────────────────────────────────────
firebase = pyrebase.initialize_app(firebase_config)
auth, db = firebase.auth(), firebase.database()

# ── 3. Theme (feminine split‑card) ───────────────────────────
st.set_page_config("AI Report Analyzer", "💖", layout="wide")
st.markdown("""
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

# ── 4. Session wrapper ───────────────────────────────────────
if "state" not in st.session_state:
    st.session_state.state = {"page":"login"}
S = st.session_state.state

# ── 5. Firebase helpers ─────────────────────────────────────
def load_record(email:str):
    if email == ADMIN_EMAIL:
        S.update(plan="admin", used=0, admin=True); return
    key = email.replace(".","_")
    rec = db.child("users").child(key).get().val() or {}
    S.update(plan=rec.get("plan","free"), used=rec.get("report_count",0), admin=False)

def inc_usage(email:str):
    if email == ADMIN_EMAIL: return
    key = email.replace(".","_")
    new = S["used"] + 1
    db.child("users").child(key).update({"report_count": new})
    S["used"] = new

# ── 6. Razorpay checkout pop‑up (guarded) ───────────────────
def open_razorpay(email:str):
    if not (RZP_SERVER and RZP_KEY_ID):
        st.error("Payment server not configured."); return
    order=requests.post(f"{RZP_SERVER}/create-order",json={"email":email}).json()
    html=f"""
    <script src="https://checkout.razorpay.com/v1/checkout.js"></script>
    <script>
      var o={{"key":"{RZP_KEY_ID}","amount":"{order['amount']}","currency":"INR",
      "name":"AI Report Analyzer","description":"Pro Plan (₹299)","order_id":"{order['id']}",
      "prefill":{{"email":"{email}"}}, "theme":{{"color":"#ff4f9d"}},
      "handler":function(){{window.location.reload();}} }};
      new Razorpay(o).open();
    </script>"""
    st.components.v1.html(html,height=1)

# ── 7. Login UI ──────────────────────────────────────────────
def login_ui():
    st.markdown("<h1>AI Report Analyzer</h1>",unsafe_allow_html=True)
    st.markdown("<p class='tag'>AI‑powered analytics at your fingertips ✨</p>",unsafe_allow_html=True)
    left,right = st.columns([0.4,0.6], gap="medium")

    with left:
        st.markdown("<div class='login-img'>",unsafe_allow_html=True)
        st.image("https://raw.githubusercontent.com/rajeevk022/AI_image/main/AI_image.png",use_container_width=True)
        st.markdown("</div>",unsafe_allow_html=True)

    with right:
        st.markdown("<div class='auth-box'>",unsafe_allow_html=True)
        tab_log, tab_sig = st.tabs(["Login","Sign‑Up"])

        # Login
        with tab_log:
            with st.form("login_form"):
                email = st.text_input("Email", key="lg_email").strip()
                pwd   = st.text_input("Password",type="password", key="lg_pwd").strip()
                ok = st.form_submit_button("Sign in")
            if ok:
                if not email or not pwd:
                    st.error("Please enter email & password.")
                else:
                    try:
                        auth.sign_in_with_email_and_password(email,pwd)
                        S.update(page="dash", email=email); load_record(email); st.rerun()
                    except: st.error("Invalid credentials")

        # Sign‑up
        with tab_sig:
            with st.form("signup_form"):
                em = st.text_input("Email", key="su_em").strip()
                pw = st.text_input("Password",type="password", key="su_pw").strip()
                ok = st.form_submit_button("Create account")
            if ok:
                if not em or not pw:
                    st.error("Enter email & password.")
                else:
                    try:
                        auth.create_user_with_email_and_password(em,pw)
                        db.child("users").child(em.replace(".","_")).set({"plan":"free","report_count":0})
                        st.success("Account created – please log in.")
                    except: st.error("Email already registered")

        st.markdown("</div>",unsafe_allow_html=True)

# ── 8. Dashboard ─────────────────────────────────────────────
def dashboard():
    admin = S.get("admin",False)
    plan, used = S.get("plan","free"), S.get("used",0)

    sb = st.sidebar
    sb.write(f"User: **{S['email']}**")
    if admin:
        sb.success("Admin • Unlimited")
    elif plan=="free":
        sb.warning(f"Free • {FREE_LIMIT-used}/{FREE_LIMIT}")
        if sb.button("Upgrade to Pro (₹299)"): open_razorpay(S["email"]); st.stop()
    else:
        sb.success(f"Pro • {used}/{PRO_LIMIT}")

    if sb.button("Logout"):
        S["page"]="login"; st.rerun()

    if not admin and ((plan=="free" and used>=FREE_LIMIT) or (plan=="pro" and used>=PRO_LIMIT)):
        st.error("Quota exceeded – upgrade or wait."); return

    st.title("Dashboard")
    up = st.file_uploader("Upload CSV / Excel or PDF", ["csv","xlsx","pdf"])
    if not up: return

    # ── CSV / Excel
    if up.type in ("text/csv","application/vnd.ms-excel","application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"):
        df = pd.read_csv(up) if up.name.endswith("csv") else pd.read_excel(up)
        st.dataframe(df.head())
        if st.button("Generate Insights"):
            with st.spinner("Analysing …"):
                prompt=f"Summarize key insights:\n{df.head(15).to_csv(index=False)}"
                insights=openai.ChatCompletion.create(model="gpt-4o",
                    messages=[{"role":"user","content":prompt}],max_tokens=700)["choices"][0]["message"]["content"]
            st.subheader("🔍 Insights"); st.write(insights)
            charts=[]
            num=df.select_dtypes("number").columns.tolist()
            if num: charts.append((df[num[0]].hist(color='#ff78b3').get_figure(),"Histogram"))
            if len(num)>=2: charts.append((df.plot(x=num[0],y=num[1],color='#ff78b3').get_figure(),"Line"))
            for fig,title in charts: st.write(f"**{title}**"); st.pyplot(fig)
            st.download_button("Download insights (.txt)", insights.encode(),"insights.txt")
            if not admin: inc_usage(S["email"])

    # ── PDF
    else:
        text="\n".join(p.get_text() for p in fitz.open(stream=up.read(),filetype="pdf"))
        if not text.strip(): st.error("PDF has no extractable text"); return
        with st.spinner("Summarising …"):
            out=openai.ChatCompletion.create(model="gpt-4o",
                messages=[{"role":"user","content":text[:9000]}],max_tokens=850)["choices"][0]["message"]["content"]
        st.subheader("🔍 PDF Insights"); st.write(out)
        if not admin: inc_usage(S["email"])

# ── 9. Router ────────────────────────────────────────────────
if S["page"] == "login":
    login_ui()
else:
    dashboard()

