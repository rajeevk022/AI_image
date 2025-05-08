"""
AI Report Analyzer – FULL production build (May 2025)
──────────────────────────────────────────────────────
  • Free 3 reports → Razorpay Pro 300 — admin unlimited
  • Pointer‑numbered insights
  • Auto‑charts (≥2, ≤5) with seaborn styling
  • Excel & PDF export (all insights + charts)
  • Stable openai==0.28.1 syntax
  • Fixed Razorpay blank‑screen (st.stop only on success)
"""

import os, tempfile, requests, streamlit as st
import pandas as pd, matplotlib.pyplot as plt, seaborn as sns, fitz, openai, pyrebase
from io import BytesIO
from dotenv import load_dotenv
from firebase_config import firebase_config

# ─── 1. ENV & CONSTANTS ──────────────────────────────────────────
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")
RZP_SERVER     = os.getenv("RZP_SERVER")     # e.g. https://ai-image-1n31.onrender.com
RZP_KEY_ID     = os.getenv("RZP_KEY_ID")     # rzp_test_xxx / rzp_live_xxx
ADMIN_EMAIL    = "rajeevk021@gmail.com"
FREE_LIMIT, PRO_LIMIT = 3, 300

# ─── 2. Firebase init ───────────────────────────────────────────
firebase = pyrebase.initialize_app(firebase_config)
auth, db = firebase.auth(), firebase.database()

# ─── 3. Streamlit look & feel ───────────────────────────────────
st.set_page_config("AI Report Analyzer", "📊", layout="wide")
st.markdown(
    "<style>html,body,[class*=css]{font-family:'Poppins',sans-serif;}"
    ".stButton>button{background:linear-gradient(90deg,#ff4f9d,#ff77b1);border:none;"
    "border-radius:24px;padding:10px 32px;color:#fff;font-weight:600;font-size:14px;}</style>",
    unsafe_allow_html=True)

# ─── 4. Session dict ────────────────────────────────────────────
if "S" not in st.session_state:
    st.session_state.S = {"page":"login","insights":"","chart_paths":[],"df":pd.DataFrame()}
S = st.session_state.S

# ─── 5. Firebase helpers ────────────────────────────────────────
def load_user(email:str):
    if email == ADMIN_EMAIL:
        S.update(plan="admin", used=0, admin=True)
    else:
        key=email.replace(".","_")
        rec=db.child("users").child(key).get().val() or {}
        S.update(plan=rec.get("plan","free"), used=rec.get("report_count",0), admin=False)

def inc_usage():
    if S.get("admin"): return
    key=S["email"].replace(".","_")
    db.child("users").child(key).update({"report_count": S["used"]+1})
    S["used"] += 1

# ─── 6. Utility helpers ─────────────────────────────────────────
def numberify(text:str)->str:
    lines=[l.strip() for l in text.splitlines() if l.strip()]
    return "\n".join(f"{i+1}. {l.lstrip('-*0123456789. ')}" for i,l in enumerate(lines))

def auto_charts(df):
    charts, paths = [], []
    num=df.select_dtypes("number").columns
    cat=df.select_dtypes("object").columns

    if num.any():                                     # Histogram
        f,a=plt.subplots(); sns.histplot(df[num[0]].dropna(),ax=a,color="#ff78b3")
        a.set_title(f"Distribution of {num[0]}"); charts.append(("Histogram",f))
    if len(num)>=2:                                   # Line / Scatter
        f,a=plt.subplots(); df.plot(x=num[0],y=num[1],ax=a,color="#ff78b3")
        a.set_title(f"{num[1]} vs {num[0]}"); charts.append(("Line chart",f))
    if cat.any():                                     # Bar chart
        f,a=plt.subplots(); df[cat[0]].value_counts().head(10).plot(kind="bar",ax=a,color="#ff78b3")
        a.set_title(f"Top {cat[0]}"); charts.append(("Bar chart",f))

    if len(charts)==1: charts.append(charts[0])       # guarantee ≥2
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

# ─── 7. Razorpay popup (no blank screen) ────────────────────────
def open_razorpay(email)->bool:
    if not (RZP_SERVER and RZP_KEY_ID):
        st.error("Payment server not configured."); return False
    try:
        r=requests.post(f"{RZP_SERVER}/create-order",json={"email":email},timeout=8)
        r.raise_for_status(); order=r.json()
    except Exception as e:
        st.error(f"Order‑server error: {e}"); return False
    st.components.v1.html(f"""
      <script src="https://checkout.razorpay.com/v1/checkout.js"></script>
      <script>
        var o={{key:"{RZP_KEY_ID}",amount:"{order['amount']}",currency:"INR",
        name:"AI Report Analyzer",description:"Pro Plan",order_id:"{order['id']}",
        prefill:{{email:"{email}"}},theme:{{color:"#ff4f9d"}},
        handler:function(){{window.location.reload();}}}};
        new Razorpay(o).open();
      </script>""",height=650,scrolling=False)
    return True

# ─── 8. Login screen ───────────────────────────────────────────
def login_screen():
    st.title("AI Report Analyzer")
    colL,colR=st.columns(2)
    # Login
    with colL:
        email=st.text_input("Email").strip()
        pwd=st.text_input("Password",type="password")
        if st.button("Sign in"):
            try:
                auth.sign_in_with_email_and_password(email,pwd)
                S.update(page="dash",email=email); load_user(email); st.rerun()
            except: st.error("Invalid credentials")
    # Sign‑up
    with colR:
        email=st.text_input("New Email",key="su_em").strip()
        pwd=st.text_input("New Password",type="password",key="su_pw")
        if st.button("Create account"):
            try:
                auth.create_user_with_email_and_password(email,pwd)
                db.child("users").child(email.replace(".","_")).set({"plan":"free","report_count":0})
                st.success("Account created – log in.")
            except: st.error("Email exists")

# ─── 9. Dashboard ──────────────────────────────────────────────
def dashboard():
    admin=S.get("admin",False); plan=S.get("plan","free"); used=S.get("used",0)
    sb=st.sidebar; sb.write(f"User: **{S['email']}**")
    if admin: sb.success("Admin • Unlimited")
    elif plan=="free":
        sb.warning(f"Free • {FREE_LIMIT-used}/{FREE_LIMIT}")
        if sb.button("Upgrade to Pro (₹299)") and open_razorpay(S["email"]):
            st.stop()
    else: sb.success(f"Pro • {used}/{PRO_LIMIT}")
    if sb.button("Logout"): S["page"]="login"; st.rerun()

    if not admin and ((plan=="free" and used>=FREE_LIMIT) or (plan=="pro" and used>=PRO_LIMIT)):
        st.error("Quota exceeded – upgrade or wait."); return

    st.title("Dashboard")
    up=st.file_uploader("Upload CSV / Excel / PDF",["csv","xlsx","pdf"])
    if not up:
        if S["insights"]: results_view()
        return

    # PDF branch
    if up.type.endswith("pdf"):
        text="\n".join(p.get_text() for p in fitz.open(stream=up.read(),filetype="pdf"))
        if not text.strip(): st.error("PDF contains no text."); return
        with st.spinner("Summarising PDF …"):
            raw=openai.ChatCompletion.create(model="gpt-4o",
                messages=[{"role":"user","content":text[:9000]}],max_tokens=800)["choices"][0]["message"]["content"]
        S.update(insights=numberify(raw),chart_paths=[],df=pd.DataFrame()); results_view(); inc_usage(); return

    # CSV / Excel branch
    df=pd.read_csv(up) if up.name.endswith("csv") else pd.read_excel(up,engine="openpyxl")
    st.dataframe(df.head())
    if st.button("Generate Insights"):
        prompt=f"Summarise:\n{df.head(15).to_csv(index=False)}"
        with st.spinner("Analysing …"):
            raw=openai.ChatCompletion.create(model="gpt-4o",
                messages=[{"role":"user","content":prompt}],max_tokens=700)["choices"][0]["message"]["content"]
        charts,paths=auto_charts(df)
        S.update(insights=numberify(raw),chart_paths=paths,df=df); results_view(); inc_usage()

def results_view():
    st.subheader("🔍 Insights"); st.write(S["insights"])
    if S["chart_paths"]:
        st.subheader("📊 Charts")
        for p in S["chart_paths"]: st.image(p,use_container_width=True)
    if not S["df"].empty:
        st.download_button("Export as Excel",
            export_excel(S["df"],S["insights"],S["chart_paths"]),
            "ai_report.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.download_button("Export as PDF",
        export_pdf(S["insights"],S["chart_paths"]), "ai_report.pdf")

# ─── 10. Router ────────────────────────────────────────────────
if S["page"]=="login": login_screen()
else: dashboard()
