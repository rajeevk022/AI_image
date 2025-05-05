"""
AI Report Analyzer – FINAL full‑feature build
• Admin email unlimited
• Free (3) ➜ Razorpay Pro (300)
• Download Excel + PDF (insights + chart)
• Fixed login rerun, openpyxl dependency
"""
import os, tempfile, requests, streamlit as st
import pandas as pd, matplotlib.pyplot as plt, fitz, openai, pyrebase, seaborn as sns
from io import BytesIO
from dotenv import load_dotenv
from firebase_config import firebase_config

# ───────────────────────── 1. ENV & CONSTANTS
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

RZP_SERVER  = os.getenv("RZP_SERVER")      # https://razor-srv.onrender.com
RZP_KEY_ID  = os.getenv("RZP_KEY_ID")      # rzp_test_xxxxx

ADMIN_EMAIL = "rajeevk021@gmail.com"
FREE_LIMIT  = 3
PRO_LIMIT   = 300
PRO_PRICE   = 299   # INR

# ───────────────────────── 2. Firebase
firebase = pyrebase.initialize_app(firebase_config)
auth, db = firebase.auth(), firebase.database()

# ───────────────────────── 3. Style
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

# ───────────────────────── 4. Session state
if "state" not in st.session_state:
    st.session_state.state = {"page":"login"}
S = st.session_state.state

# ───────────────────────── 5. Firebase helpers
def load_user(email:str):
    if email == ADMIN_EMAIL:
        S.update(plan="admin", used=0, admin=True); return
    key=email.replace(".","_")
    rec=db.child("users").child(key).get().val() or {}
    S.update(plan=rec.get("plan","free"), used=rec.get("report_count",0), admin=False)

def bump_usage(email:str):
    if email==ADMIN_EMAIL: return
    key=email.replace(".","_"); new=S["used"]+1
    db.child("users").child(key).update({"report_count": new})
    S["used"]=new

# ───────────────────────── 6. Chart + export helpers
def smart_charts(df):
    charts=[]; num=df.select_dtypes("number").columns; cat=df.select_dtypes("object").columns
    if num.any():
        f,a=plt.subplots(); sns.histplot(df[num[0]].dropna(),ax=a,color="#ff78b3"); a.set_title(f"Dist {num[0]}"); charts.append((f,"Histogram"))
    if cat.any():
        f,a=plt.subplots(); df[cat[0]].value_counts().head(10).plot(kind="bar",ax=a,color="#ff78b3"); a.set_title(f"Top {cat[0]}"); charts.append((f,"Category bar"))
    if len(num)>=2:
        f,a=plt.subplots(); df.plot(x=num[0],y=num[1],ax=a,color="#ff78b3"); a.set_title(f"{num[1]} vs {num[0]}"); charts.append((f,"Line chart"))
    return charts[:5] if len(charts)>=2 else charts

def export_excel(df, insights, chart_path):
    bio=BytesIO()
    with pd.ExcelWriter(bio, engine="xlsxwriter") as w:
        df.to_excel(w,index=False,sheet_name="Data")
        ws=w.book.add_worksheet("Insights"); w.sheets["Insights"]=ws
        for i,l in enumerate(insights.split("\n")): ws.write(i,0,l)
        if chart_path: ws.insert_image(len(insights.split("\n"))+2,0,chart_path,{"x_scale":0.9,"y_scale":0.9})
    bio.seek(0); return bio

def export_pdf(insights, chart_path):
    from fpdf import FPDF
    pdf=FPDF(); pdf.add_page(); pdf.set_font("Arial","B",14); pdf.cell(0,10,"AI Report",ln=True)
    pdf.set_font("Arial",size=11)
    for l in insights.split("\n"): pdf.multi_cell(0,8,l)
    if chart_path: pdf.add_page(); pdf.image(chart_path,x=10,y=30,w=180)
    return BytesIO(pdf.output(dest="S").encode("latin1"))

# ───────────────────────── 7. Razorpay pop‑up
def open_razorpay(email):
    if not (RZP_SERVER and RZP_KEY_ID):
        st.error("Payment server not configured."); return
    order=requests.post(f"{RZP_SERVER}/create-order",json={"email":email}).json()
    html=f"""
    <script src="https://checkout.razorpay.com/v1/checkout.js"></script>
    <script>
      var o={{"key":"{RZP_KEY_ID}","amount":"{order['amount']}","currency":"INR",
      "name":"AI Report Analyzer","description":"Pro (₹{PRO_PRICE})","order_id":"{order['id']}",
      "prefill":{{"email":"{email}"}}, "theme":{{"color":"#ff4f9d"}},
      "handler":function(){{window.location.reload();}} }};
      new Razorpay(o).open();
    </script>"""
    st.components.v1.html(html,height=1)

# ───────────────────────── 8. Login UI
def login_ui():
    st.markdown("<h1>AI Report Analyzer</h1>",unsafe_allow_html=True)
    st.markdown("<p class='tag'>AI‑powered analytics at your fingertips ✨</p>",unsafe_allow_html=True)
    l,r=st.columns([0.4,0.6],gap="medium")

    with l:
        st.markdown("<div class='login-img'>",unsafe_allow_html=True)
        st.image("https://raw.githubusercontent.com/rajeevk022/AI_image/main/AI_image.png",use_container_width=True)
        st.markdown("</div>",unsafe_allow_html=True)

    with r:
        st.markdown("<div class='auth-box'>",unsafe_allow_html=True)
        tabL, tabS = st.tabs(["Login","Sign‑Up"])

        with tabL:
            with st.form("login"):
                email=st.text_input("Email",key="lg_email").strip()
                pwd=st.text_input("Password",type="password",key="lg_pwd").strip()
                ok=st.form_submit_button("Sign in")
            if ok:
                if not email or not pwd:
                    st.error("Missing email or password.")
                else:
                    try:
                        auth.sign_in_with_email_and_password(email,pwd)
                        S.update(page="dash",email=email); load_user(email); st.rerun()
                    except: st.error("Invalid credentials")

        with tabS:
            with st.form("signup"):
                em=st.text_input("Email",key="su_email").strip()
                pw=st.text_input("Password",type="password",key="su_pwd").strip()
                create=st.form_submit_button("Create account")
            if create:
                if not em or not pw:
                    st.error("Enter email & password.")
                else:
                    try:
                        auth.create_user_with_email_and_password(em,pw)
                        db.child("users").child(em.replace(".","_")).set({"plan":"free","report_count":0})
                        st.success("Account created – please log in.")
                    except: st.error("Email already registered")

        st.markdown("</div>",unsafe_allow_html=True)

# ───────────────────────── 9. Dashboard
def dashboard():
    admin=S.get("admin",False); plan=S.get("plan","free"); used=S.get("used",0)
    sb=st.sidebar; sb.write(f"User: **{S['email']}**")
    if admin: sb.success("Admin • Unlimited")
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
    up=st.file_uploader("Upload CSV / Excel / PDF",["csv","xlsx","pdf"])
    if not up: return

    if up.type.endswith("pdf"):
        text="\n".join(p.get_text() for p in fitz.open(stream=up.read(),filetype="pdf"))
        if not text.strip(): st.error("PDF has no extractable text"); return
        with st.spinner("Summarising PDF …"):
            out=openai.ChatCompletion.create(model="gpt-4o",messages=[{"role":"user","content":text[:9000]}],max_tokens=850)["choices"][0]["message"]["content"]
        st.subheader("🔍 PDF Insights"); st.write(out); bump_usage_if_needed(admin)
        return

    # CSV / Excel
    df=pd.read_csv(up) if up.name.endswith("csv") else pd.read_excel(up,engine="openpyxl")
    st.dataframe(df.head())
    if st.button("Generate Insights"):
        prompt=f"Summarize:\n{df.head(15).to_csv(index=False)}"
        with st.spinner("Analysing …"):
            insights=openai.ChatCompletion.create(model="gpt-4o",
                messages=[{"role":"user","content":prompt}],max_tokens=750)["choices"][0]["message"]["content"]
        st.subheader("🔍 Insights"); st.write(insights)
        charts=smart_charts(df); chart_path=""
        if charts:
            st.subheader("📊 Charts")
            for i,(fig,title) in enumerate(charts):
                st.write(f"**{title}**"); st.pyplot(fig)
                if i==0:
                    chart_path=tempfile.NamedTemporaryFile(delete=False,suffix=".png").name
                    fig.savefig(chart_path,dpi=220)
        st.download_button("Export Excel", export_excel(df,insights,chart_path),"report.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        st.download_button("Export PDF", export_pdf(insights,chart_path),"report.pdf")
        bump_usage_if_needed(admin)

def bump_usage_if_needed(admin_flag):
    if not admin_flag: bump_usage(S["email"])

# ───────────────────────── 10. Router
if S["page"]=="login":
    login_ui()
else:
    dashboard()

