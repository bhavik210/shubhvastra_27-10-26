import os, io, csv, json, hashlib
from datetime import date, datetime
from pathlib import Path
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, text, inspect
from sqlalchemy.engine import Engine
from werkzeug.security import generate_password_hash, check_password_hash
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as PDFImage

BASE = Path(__file__).resolve().parent
SIZES = ["M", "L", "XL", "XXL"]
REFERENCES = ["AGENT", "DIRECT", "CHAIN STORE", "EXPORTER"]

st.set_page_config(page_title="SHUBHVASTRA | Order Management", page_icon="🧵", layout="wide", initial_sidebar_state="expanded")

CSS = """
<style>
:root{--navy:#132b4a;--blue:#1769aa;--blue2:#eaf3fb;--line:#dfe6ef;--muted:#64748b}
.stApp{background:#f3f6fa;color:#1d2a3b}.block-container{padding-top:1rem;max-width:1500px}
[data-testid="stSidebar"]{background:#f8f6ef!important;color:#111827!important;border-right:1px solid #e5e0d5}
[data-testid="stSidebar"] *{color:#111827!important}
[data-testid="stSidebar"] [data-testid="stRadio"] label{padding:.5rem .6rem;border-radius:7px;color:#111827!important}
[data-testid="stSidebar"] [data-testid="stRadio"] label:hover{background:#eae5d8!important}
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-checked="true"]{background:#e5dfd0!important;font-weight:700!important}
[data-testid="stSidebar"] [data-testid="stRadio"] label p{color:#111827!important}
.brandbar{background:#132b4a;color:white;border-radius:12px;padding:15px 20px;display:flex;align-items:center;gap:14px;margin-bottom:1rem}
.brandtitle{font-weight:800;font-size:1.35rem;letter-spacing:.5px}.brandsub{color:#c5d5e8;font-size:.82rem}
.metric-card{background:white;border:1px solid #dfe6ef;border-radius:12px;padding:16px 18px;box-shadow:0 3px 12px #20344c07}
.metric-label{font-size:.82rem;color:#64748b;font-weight:650}.metric-value{font-size:1.9rem;font-weight:800;color:#132b4a;margin-top:5px}
.section-card{background:white;border:1px solid #dfe6ef;border-radius:12px;padding:16px 18px;margin-bottom:12px}
h1,h2,h3{color:#132b4a!important}div.stButton>button[kind="primary"]{background:#1769aa;border-color:#1769aa}
[data-testid="stDataFrame"]{background:white;border-radius:10px;border:1px solid #dbe4ef;overflow:hidden}
.small-note{color:#52657d;font-size:.86rem}
/* Professional contrast: readable alerts, buttons, labels and form controls */
[data-testid="stAlert"]{border-radius:10px!important;border:1px solid #cbd8e8!important;box-shadow:0 2px 8px rgba(19,43,74,.04)}
[data-testid="stAlert"] [data-testid="stMarkdownContainer"],
[data-testid="stAlert"] [data-testid="stMarkdownContainer"] p,
[data-testid="stAlert"] [data-testid="stMarkdownContainer"] strong{color:#17324f!important;opacity:1!important}
[data-testid="stAlert"] svg{fill:currentColor!important}
[data-testid="stAlert"]:has(svg[ data-testid="stIconWarning"]){background:#fff7df!important;border-color:#f0d58a!important}
[data-testid="stAlert"]:has(svg[ data-testid="stIconInfo"]){background:#eaf4ff!important;border-color:#b8d8fb!important}
[data-testid="stAlert"]:has(svg[ data-testid="stIconSuccess"]){background:#eaf8ef!important;border-color:#b8e2c5!important}
[data-testid="stAlert"]:has(svg[ data-testid="stIconError"]){background:#fff0f0!important;border-color:#f1b8b8!important}
.stApp, [data-testid="stMarkdownContainer"], [data-testid="stText"], label, p, li{color:#1d2a3b}
[data-testid="stWidgetLabel"] p, [data-testid="stWidgetLabel"] label{color:#243b53!important;font-weight:600!important}
input, textarea, [data-baseweb="select"]>div{color:#172b43!important;background:#fff!important;border-color:#cbd5e1!important}
[data-testid="stDownloadButton"] button, div.stButton>button, [data-testid="stFormSubmitButton"] button{background:#fff!important;color:#17406b!important;border:1px solid #b8c8da!important;border-radius:8px!important;font-weight:600!important;min-height:2.45rem;transition:all .15s ease}
div.stButton>button:hover, [data-testid="stDownloadButton"] button:hover, [data-testid="stFormSubmitButton"] button:hover{background:#eaf3fb!important;border-color:#1769aa!important;color:#103d69!important}
div.stButton>button[kind="primary"], [data-testid="stFormSubmitButton"] button[kind="primary"], [data-testid="stDownloadButton"] button[kind="primary"]{background:#1769aa!important;color:#fff!important;border-color:#1769aa!important}
div.stButton>button[kind="primary"] *, [data-testid="stFormSubmitButton"] button[kind="primary"] *{color:#fff!important}
[data-testid="stDataFrame"] *{color:#1d2a3b}
hr{border-color:#dbe4ef!important}
@media(max-width:800px){.block-container{padding-left:.7rem;padding-right:.7rem}.brandtitle{font-size:1.05rem}}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def db_url():
    url = os.getenv("DATABASE_URL", "").strip()
    try:
        url = url or str(st.secrets.get("DATABASE_URL", "")).strip()
    except Exception:
        pass
    # Reject the documentation example rather than attempting a connection to HOST.
    placeholders = ("USER:PASSWORD@HOST", "/DATABASE", "YOUR_HOST", "YOUR_PASSWORD")
    if any(marker.lower() in url.lower() for marker in placeholders):
        return ""
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg://", 1)
    elif url.startswith("postgresql://") and "+psycopg" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


@st.cache_resource
def get_engine() -> Engine:
    url = db_url()
    if url:
        return create_engine(url, pool_pre_ping=True, pool_recycle=300, future=True)
    # Local development only. Streamlit Cloud needs DATABASE_URL in App settings / Secrets.
    return create_engine(f"sqlite:///{BASE / 'shubhvastra_local.db'}", connect_args={"check_same_thread": False}, future=True)

engine = get_engine()


def q(sql, params=None):
    with engine.connect() as conn:
        return pd.read_sql_query(text(sql), conn, params=params or {})


def one(sql, params=None):
    df = q(sql, params)
    return None if df.empty else df.iloc[0].to_dict()


def run(sql, params=None, returning=False):
    with engine.begin() as conn:
        result = conn.execute(text(sql), params or {})
        if returning:
            row = result.fetchone()
            return row[0] if row else None
        return result.rowcount


def init_db():
    identity = "INTEGER PRIMARY KEY AUTOINCREMENT" if engine.dialect.name == "sqlite" else "INTEGER GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY"
    stmts = [
      f"CREATE TABLE IF NOT EXISTS agents (id {identity}, agent_name VARCHAR(200) NOT NULL UNIQUE, phone_number VARCHAR(100) NOT NULL, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)",
      f"CREATE TABLE IF NOT EXISTS parties (id {identity}, party_name VARCHAR(250) NOT NULL, phone_number VARCHAR(100) NOT NULL, address TEXT NOT NULL DEFAULT '', city VARCHAR(150) NOT NULL DEFAULT '', state VARCHAR(150) NOT NULL DEFAULT '', gst_number VARCHAR(100) NOT NULL DEFAULT '', reference VARCHAR(30) NOT NULL DEFAULT 'DIRECT', transport_details TEXT NOT NULL DEFAULT '', transport_gst_number VARCHAR(100) NOT NULL DEFAULT '', agent_id INTEGER NULL REFERENCES agents(id) ON DELETE RESTRICT, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)",
      f"CREATE TABLE IF NOT EXISTS orders (id {identity}, order_no INTEGER NOT NULL UNIQUE, order_date DATE NOT NULL, party_id INTEGER NOT NULL REFERENCES parties(id) ON DELETE RESTRICT, packaging TEXT NOT NULL DEFAULT '[]', gst_type VARCHAR(30) NOT NULL DEFAULT '', narration TEXT NOT NULL DEFAULT '', created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, cancelled INTEGER NOT NULL DEFAULT 0)",
      f"CREATE TABLE IF NOT EXISTS order_items (id {identity}, order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE, sr_no INTEGER NOT NULL, particulars VARCHAR(250) NOT NULL, piece_rate NUMERIC(12,2) NOT NULL DEFAULT 0, discount NUMERIC(12,2) NOT NULL DEFAULT 0)",
      f"CREATE TABLE IF NOT EXISTS order_item_sizes (id {identity}, order_item_id INTEGER NOT NULL REFERENCES order_items(id) ON DELETE CASCADE, size_code VARCHAR(10) NOT NULL, ordered_qty INTEGER NOT NULL CHECK(ordered_qty > 0), cancelled INTEGER NOT NULL DEFAULT 0, UNIQUE(order_item_id,size_code))",
      f"CREATE TABLE IF NOT EXISTS order_dispatches (id {identity}, order_size_id INTEGER NOT NULL REFERENCES order_item_sizes(id) ON DELETE RESTRICT, dispatched_size VARCHAR(10) NOT NULL, qty INTEGER NOT NULL CHECK(qty > 0), dispatch_date DATE NOT NULL, details TEXT NOT NULL DEFAULT '', invoice_number VARCHAR(150) NOT NULL DEFAULT '', created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)",
      f"CREATE TABLE IF NOT EXISTS sku_master (id {identity}, sku_number VARCHAR(250) NOT NULL UNIQUE, sale_rate NUMERIC(12,2) NOT NULL CHECK(sale_rate >= 0), created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)",
      f"CREATE TABLE IF NOT EXISTS users (id {identity}, username VARCHAR(100) NOT NULL UNIQUE, password_hash TEXT NOT NULL, role VARCHAR(20) NOT NULL DEFAULT 'staff', active INTEGER NOT NULL DEFAULT 1, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    ]
    with engine.begin() as conn:
        for stmt in stmts: conn.execute(text(stmt))
        # Add columns if upgrading a prior PostgreSQL schema.
        if engine.dialect.name == "postgresql":
            conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS cancelled INTEGER NOT NULL DEFAULT 0"))
            conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS gst_type VARCHAR(30) NOT NULL DEFAULT ''"))
            conn.execute(text("ALTER TABLE order_item_sizes ADD COLUMN IF NOT EXISTS cancelled INTEGER NOT NULL DEFAULT 0"))
            conn.execute(text("ALTER TABLE order_dispatches ADD COLUMN IF NOT EXISTS invoice_number VARCHAR(150) NOT NULL DEFAULT ''"))
        else:
            cols = {r[1] for r in conn.execute(text("PRAGMA table_info(orders)")).fetchall()}
            if "gst_type" not in cols:
                conn.execute(text("ALTER TABLE orders ADD COLUMN gst_type VARCHAR(30) NOT NULL DEFAULT ''"))
        # User accounts are created through first-run setup / Admin Panel.
        # Backfill SKU master from historic order items without changing saved order rates.
        conn.execute(text("""INSERT INTO sku_master(sku_number,sale_rate)
          SELECT TRIM(i.particulars), COALESCE(i.piece_rate,0) FROM order_items i
          WHERE TRIM(i.particulars)<>'' AND NOT EXISTS
          (SELECT 1 FROM sku_master s WHERE LOWER(s.sku_number)=LOWER(TRIM(i.particulars)))
          AND i.id=(SELECT MAX(i2.id) FROM order_items i2 WHERE LOWER(TRIM(i2.particulars))=LOWER(TRIM(i.particulars)))"""))

try:
    init_db()
except Exception as exc:
    # Never show the full connection string: it may contain database credentials.
    err = str(exc).lower()
    st.error("PostgreSQL database સાથે connection થઈ શક્યું નથી.")
    st.markdown("### આ રીતે સુધારો")
    st.markdown("""
1. Streamlit Cloud → **Manage app → Settings → Secrets** ખોલો.
2. `DATABASE_URL` ને તમારા PostgreSQL provider દ્વારા આપેલી **સંપૂર્ણ actual connection string** થી બદલો. `USER`, `PASSWORD`, `HOST`, `DATABASE` જેવા sample words જ રાખશો નહીં.
3. Connection string `postgresql://...` અથવા `postgresql+psycopg://...` formatમાં હોવી જોઈએ. Passwordમાં `@`, `#`, `/`, `:` જેવા special characters હોય તો URL-encode કરેલા હોવા જોઈએ.
4. PostgreSQL providerમાં database ચાલુ છે, credentials સાચાં છે અને external connections/SSL મંજૂર છે તેની ખાતરી કરો.
5. Secrets save કર્યા પછી app reboot કરો.

**Logs માં કઈ ભૂલ છે તે મુજબ:**
- `could not translate host name` → HOST/hostname ખોટું છે.
- `password authentication failed` → database username/password ખોટાં છે.
- `connection refused` અથવા timeout → database host/port, network access અથવા database status ચેક કરો.
- `database ... does not exist` → database name ખોટું છે અથવા database બનાવ્યું નથી.

આ test build માં application login disabled છે; PostgreSQL credentials ફક્ત database connection માટે છે.
""")
    with st.expander("Technical detail (credentials hidden)", expanded=True):
        if "could not translate host" in err or "name or service not known" in err or "temporary failure in name resolution" in err:
            st.code("CAUSE: PostgreSQL hostname resolve થતું નથી. DATABASE_URL માં provider આપેલો HOST તપાસો.")
        elif "password authentication failed" in err or "authentication failed" in err:
            st.code("CAUSE: PostgreSQL authentication નિષ્ફળ. Database username/password તપાસો; app login password અલગ છે.")
        elif "connection refused" in err:
            st.code("CAUSE: PostgreSQL server એ connection સ્વીકાર્યું નથી. Host/port, database status અને provider network access તપાસો.")
        elif "timeout" in err or "timed out" in err:
            st.code("CAUSE: PostgreSQL connection timeout. Provider database active છે અને external connections મંજૂર છે તેની ખાતરી કરો.")
        elif "does not exist" in err and "database" in err:
            st.code("CAUSE: PostgreSQL database મળતું નથી. Connection string માં database name તપાસો.")
        elif "no pg_hba.conf entry" in err or "not allowed to connect" in err:
            st.code("CAUSE: Provider તરફથી connection/IP મંજૂર નથી અથવા SSL/network policy મેળ ખાતી નથી.")
        elif "ssl" in err:
            st.code("CAUSE: SSL/TLS connection સમસ્યા. Provider ની ભલામણ કરેલી SSL connection string વાપરો.")
        elif "invalid connection option" in err or "invalid dsn" in err or "could not parse" in err:
            st.code("CAUSE: DATABASE_URL format ખોટું છે. Provider ની સંપૂર્ણ URI copy કરો; username/passwordમાં special characters URL-encode કરો.")
        elif "relation" in err and "does not exist" in err:
            st.code("CAUSE: Database schema/table અધૂરું છે. Logs માં tableનું નામ તપાસો; migration/setup ફરી ચકાસવું પડશે.")
        else:
            # Show a short sanitized cause. Never print the configured URI or credentials.
            import re
            safe_err = str(exc)
            configured_url = db_url()
            if configured_url:
                safe_err = safe_err.replace(configured_url, "[DATABASE_URL hidden]")
            safe_err = re.sub(r"(?i)(postgres(?:ql)?(?:\+psycopg)?://)[^\s'\"]+", r"\1[credentials hidden]", safe_err)
            safe_err = re.sub(r"(?i)(password|passwd|pwd)=([^\s&;]+)", r"\1=[hidden]", safe_err)
            st.code(f"{type(exc).__name__}: {safe_err[:500]}")
    st.stop()


# Authentication: first run requires creating the first administrator; no default credentials.
def current_user():
    return st.session_state.get("authenticated_user")

def is_admin():
    user = current_user()
    return bool(user and user.get("role") == "admin")

def require_login():
    return current_user() is not None

def show_first_admin_setup():
    st.title("SHUBHVASTRA — Initial Admin Setup")
    st.info("આ database માં હજી કોઈ user નથી. પહેલા મુખ્ય Admin username અને password બનાવો. કોઈ default password નથી.")
    with st.form("first_admin_setup"):
        username = st.text_input("Admin Username")
        password = st.text_input("Admin Password", type="password")
        confirm = st.text_input("Confirm Admin Password", type="password")
        submitted = st.form_submit_button("Create Main Admin", type="primary")
    if submitted:
        if not username.strip():
            st.error("Admin username જરૂરી છે.")
        elif len(password) < 10:
            st.error("Password ઓછામાં ઓછો 10 characters નો રાખો.")
        elif password != confirm:
            st.error("બંને password સરખા નથી.")
        elif one("SELECT id FROM users WHERE LOWER(username)=LOWER(:u)", {"u":username.strip()}):
            st.error("આ username પહેલેથી છે. બીજું username પસંદ કરો.")
        elif one("SELECT id FROM users WHERE role='admin' AND active=1 LIMIT 1"):
            st.error("Active Admin પહેલેથી છે. Login કરો.")
        else:
            run("INSERT INTO users(username,password_hash,role,active) VALUES(:u,:p,'admin',1)", {"u":username.strip(),"p":generate_password_hash(password)})
            st.success("Main Admin તૈયાર થયો. હવે તમારા username અને password થી login કરો.")
            st.rerun()

def show_login():
    st.title("SHUBHVASTRA Login")
    st.caption("તમારા Admin દ્વારા બનાવેલા username અને password થી જ login કરી શકશો.")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", type="primary", use_container_width=True)
    if submitted:
        user = one("SELECT id,username,password_hash,role,active FROM users WHERE LOWER(username)=LOWER(:u)", {"u":username.strip()})
        if user and int(user["active"]) == 1 and check_password_hash(user["password_hash"], password):
            st.session_state["authenticated_user"] = {"id":int(user["id"]),"username":user["username"],"role":user["role"]}
            st.rerun()
        else:
            st.error("Username અથવા password ખોટો છે, અથવા user disabled છે.")
    # Intentionally no Forgot Password option. Admin must reset staff passwords from Utilities.

def df_download(df, filename, label="CSV Download"):
    out = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(label, out, file_name=filename, mime="text/csv", use_container_width=False)

def order_pdf_bytes(order, items_df):
    buff = io.BytesIO()
    doc = SimpleDocTemplate(buff, pagesize=A4, rightMargin=10*mm, leftMargin=10*mm, topMargin=10*mm, bottomMargin=12*mm)
    styles = getSampleStyleSheet()
    small = styles["BodyText"]
    small.fontSize = 8
    small.leading = 10
    # Professional PDF header: Trishiv logo on the left, Shubhvastra logo on the right.
    app_dir = BASE
    trishiv_logo = app_dir / "static" / "trishiv_logo.jpg"
    shubhvastra_logo = app_dir / "static" / "shubhvastra_logo.png"
    logo_left = PDFImage(str(trishiv_logo), width=38*mm, height=30*mm, kind="proportional") if trishiv_logo.exists() else Paragraph("<b>TRISHIV ENTERPRISE LLP</b>", small)
    logo_right = PDFImage(str(shubhvastra_logo), width=49*mm, height=24*mm, kind="proportional") if shubhvastra_logo.exists() else Paragraph("<b>SHUBHVASTRA</b>", small)
    brand_row = Table([[logo_left, logo_right]], colWidths=[95*mm, 95*mm], hAlign="LEFT")
    brand_row.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"MIDDLE"),("ALIGN",(0,0),(0,0),"LEFT"),("ALIGN",(1,0),(1,0),"RIGHT"),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)]))
    title_style = ParagraphStyle("CompactOrderTitle", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, leading=14, alignment=TA_CENTER, spaceBefore=2, spaceAfter=5)
    story = [brand_row, Spacer(1, 2*mm), Paragraph("ORDER FORM", title_style), Spacer(1, 2*mm)]
    company_style = ParagraphStyle("CompanyContact", parent=small, fontSize=8, leading=10, textColor=colors.HexColor("#333333"), spaceAfter=1)
    story.extend([Paragraph("<b>Address:</b> 2005 New Sardar Traders Market (NSTM), Puna Kumbhariya Road, Surat 395010", company_style), Paragraph("<b>Phone Number:</b> 9537510757 (Bhavik), 9099444455 (Nimesh)", company_style), Spacer(1, 3*mm)])
    party_data = [
        [Paragraph(f"<b>Party Name:</b> {order.get('party_name','')}", small), Paragraph(f"<b>Order Number:</b> {order.get('order_no','')}", small)],
        [Paragraph(f"<b>Address:</b> {order.get('address','')}", small), Paragraph(f"<b>Order Date:</b> {str(order.get('order_date',''))[:10]}", small)],
        [Paragraph(f"<b>City, State:</b> {order.get('city','')}, {order.get('state','')}", small), Paragraph(f"<b>GST:</b> {order.get('gst_type','') or '-'}", small)],
        [Paragraph(f"<b>Phone:</b> {order.get('phone_number','')}", small), Paragraph(f"<b>Packaging:</b> {order.get('packaging','') or '-'}", small)],
        [Paragraph(f"<b>Party GST Number:</b> {order.get('gst_number','')}", small), Paragraph(f"<b>Agent:</b> {order.get('agent_name','') or '-'}", small)],
        [Paragraph(f"<b>Transport Name:</b> {order.get('transport_details','')}", small), Paragraph(f"<b>Transport ID:</b> {order.get('transport_gst_number','')}", small)],
    ]
    pt=Table(party_data,colWidths=[95*mm,95*mm])
    pt.setStyle(TableStyle([('GRID',(0,0),(-1,-1),0.4,colors.HexColor('#aab7c7')),('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#f7f9fc')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
    story.extend([pt, Spacer(1, 5*mm), Paragraph("ITEM DETAILS", styles["Heading2"])])
    data=[["Sr.","Particulars / SKU","M","L","XL","XXL","Discount","WSP Rate","Qty","Amount"]]
    total_qty=0; total_amount=0
    grouped={}
    for r in items_df.to_dict('records'):
        sr=r.get('Sr',''); sku=r.get('Particulars',''); key=(sr,sku,r.get('Discount',''),r.get('WSP Rate',r.get('Piece Rate','')))
        if key not in grouped: grouped[key]={"M":0,"L":0,"XL":0,"XXL":0}
        size=str(r.get('Size','')).upper()
        if size in grouped[key]: grouped[key][size]+=int(r.get('Qty',0) or 0)
    for (sr,sku,disc,rate),sizes in grouped.items():
        qty=sum(sizes.values()); amount=max(0,float(rate or 0)-float(disc or 0))*qty
        total_qty+=qty; total_amount+=amount
        data.append([str(sr),str(sku),str(sizes['M']),str(sizes['L']),str(sizes['XL']),str(sizes['XXL']),str(disc),str(rate),str(qty),f"{amount:,.2f}"])
    data.append(["","TOTAL","","","","","","",str(total_qty),f"{total_amount:,.2f}"])
    tab=Table(data,repeatRows=1,colWidths=[9*mm,43*mm,11*mm,11*mm,12*mm,13*mm,17*mm,19*mm,13*mm,23*mm])
    tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#132b4a')),('TEXTCOLOR',(0,0),(-1,0),colors.white),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),7.5),('GRID',(0,0),(-1,-1),0.45,colors.HexColor('#9aa8b8')),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('ALIGN',(2,1),(-1,-1),'RIGHT'),('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#eaf3fb')),('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]))
    story.extend([tab, Spacer(1, 4*mm)])
    if order.get('narration'): story.append(Paragraph(f"<b>Additional Order Details:</b> {order['narration']}",small))
    doc.build(story)
    return buff.getvalue()

def money(v):
    try: return f"₹{float(v):,.2f}"
    except Exception: return "₹0.00"

def table(sql, params=None, key=None):
    df = q(sql, params)
    st.dataframe(df, use_container_width=True, hide_index=True, key=key)
    return df

def get_parties(): return q("SELECT p.id,p.party_name,p.phone_number,p.address,p.city,p.state,p.gst_number,p.reference,p.transport_details,p.transport_gst_number,p.agent_id,COALESCE(a.agent_name,'') agent_name FROM parties p LEFT JOIN agents a ON a.id=p.agent_id ORDER BY p.party_name")
def get_skus(): return q("SELECT id,sku_number,sale_rate FROM sku_master ORDER BY sku_number")
def get_order_no(): return int(one("SELECT COALESCE(MAX(order_no),1100)+1 AS n FROM orders")["n"])
def get_dispatch_total(size_id): return int(one("SELECT COALESCE(SUM(qty),0) AS n FROM order_dispatches WHERE order_size_id=:id", {"id":int(size_id)})["n"])


def header():
    logo = BASE / "static" / "shubhvastra_logo.png"
    cols = st.columns([1,7,2])
    with cols[0]:
        if logo.exists(): st.image(str(logo), width=72)
    with cols[1]:
        st.markdown('<div class="brandtitle">SHUBHVASTRA</div><div class="brandsub">NEW VERSION 2026 · ORDER MANAGEMENT SYSTEM</div>', unsafe_allow_html=True)
    with cols[2]:
        st.caption("Secure Login · Admin Controlled")
    st.divider()


def login_screen():
    st.markdown("<div class='section-card'>", unsafe_allow_html=True)
    st.title("SHUBHVASTRA Login")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login", type="primary", use_container_width=True)
    if submitted:
        user = one("SELECT id,username,password_hash,role,active FROM users WHERE LOWER(username)=LOWER(:u)", {"u":username.strip()})
        if user and int(user["active"]) == 1 and check_password_hash(user["password_hash"], password):
            st.session_state["user"] = {"id":int(user["id"]),"username":user["username"],"role":user["role"]}
            st.rerun()
        else: st.error("Username અથવા password ખોટો છે.")
    st.markdown("</div>", unsafe_allow_html=True)


def page_dashboard():
    st.title("Dashboard")
    stats = [
      ("Total Parties", "SELECT COUNT(*) n FROM parties"),
      ("Total Agents", "SELECT COUNT(*) n FROM agents"),
      ("Total SKU", "SELECT COUNT(*) n FROM sku_master"),
      ("Total Orders", "SELECT COUNT(*) n FROM orders"),
      ("Pending Orders", "SELECT COUNT(DISTINCT o.id) n FROM orders o JOIN order_items i ON i.order_id=o.id JOIN order_item_sizes s ON s.order_item_id=i.id WHERE o.cancelled=0 AND s.cancelled=0 AND s.ordered_qty>(SELECT COALESCE(SUM(d.qty),0) FROM order_dispatches d WHERE d.order_size_id=s.id)")]
    cols=st.columns(5)
    for col,(label,sql) in zip(cols,stats):
        val=one(sql)["n"]
        with col: st.markdown(f"<div class='metric-card'><div class='metric-label'>{label}</div><div class='metric-value'>{val}</div></div>",unsafe_allow_html=True)
    st.subheader("All Parties")
    st.caption("Party list read-only છે. કોઈ field edit નહીં થાય; cell પસંદ કરીને Ctrl+C થી text copy કરી શકો છો.")
    search = st.text_input(
        "🔎 Search Party",
        placeholder="Party name, phone, city, GST, agent, transport અથવા reference લખો...",
        key="dashboard_party_search",
    )
    party_df = q("""
        SELECT
            p.party_name AS "Party Name",
            p.phone_number AS "Phone Number",
            p.city AS "City",
            p.gst_number AS "GST Number",
            COALESCE(a.agent_name, '') AS "Agent Name",
            p.transport_details AS "Transport Name",
            p.transport_gst_number AS "Transport ID",
            p.reference AS "Reference",
            p.address AS "Address"
        FROM parties p
        LEFT JOIN agents a ON a.id = p.agent_id
        ORDER BY p.party_name COLLATE NOCASE
    """)
    if search.strip() and not party_df.empty:
        needle = search.strip().casefold()
        mask = party_df.fillna("").astype(str).apply(
            lambda col: col.str.casefold().str.contains(needle, regex=False)
        ).any(axis=1)
        party_df = party_df.loc[mask].reset_index(drop=True)
    st.caption(f"કુલ {len(party_df)} પાર્ટી મળ્યા.")
    if str(current_user().get("role", "staff")).lower() == "staff":
        party_df = party_df[[c for c in ["Party Name", "City", "Transport Name", "Transport ID", "Address"] if c in party_df.columns]]
    st.dataframe(
        party_df.fillna(""),
        use_container_width=True,
        hide_index=True,
        height=560,
        key="dashboard_all_parties_readonly",
        column_config={
            "Party Name": st.column_config.TextColumn("Party Name", width="large"),
            "Phone Number": st.column_config.TextColumn("Phone Number", width="medium"),
            "City": st.column_config.TextColumn("City", width="medium"),
            "GST Number": st.column_config.TextColumn("GST Number", width="medium"),
            "Agent Name": st.column_config.TextColumn("Agent Name", width="medium"),
            "Transport Name": st.column_config.TextColumn("Transport Name", width="medium"),
            "Transport ID": st.column_config.TextColumn("Transport ID", width="medium"),
            "Reference": st.column_config.TextColumn("Reference", width="small"),
            "Address": st.column_config.TextColumn("Address", width="large"),
        },
    )
    if not party_df.empty and str(current_user().get("role", "staff")).lower() != "staff":
        df_download(party_df, "shubhvastra_all_parties.csv", "Download Party List CSV")


def page_agents():
    st.title("Agent Master")
    with st.expander("＋ Add New Agent", expanded=False):
        with st.form("agent_add"):
            a,b=st.columns(2); name=a.text_input("Agent Name *"); phone=b.text_input("Phone Number *")
            if st.form_submit_button("Save Agent",type="primary"):
                if not name.strip() or not phone.strip(): st.error("Agent Name અને Phone જરૂરી છે.")
                elif one("SELECT id FROM agents WHERE LOWER(agent_name)=LOWER(:n)",{"n":name.strip()}): st.error("આ Agent Name પહેલેથી છે.")
                else: run("INSERT INTO agents(agent_name,phone_number) VALUES(:n,:p)",{"n":name.strip(),"p":phone.strip()}); st.success("Agent save થયો."); st.rerun()
    df=table("SELECT id AS ID,agent_name AS \"Agent Name\",phone_number AS \"Phone Number\" FROM agents ORDER BY agent_name")
    if not df.empty:
        if is_admin():
            with st.expander("Edit Agent"):
                aid=st.selectbox("Select Agent",df.ID.tolist(),format_func=lambda x: df.loc[df.ID==x,"Agent Name"].iloc[0],key="agent_edit_id")
                old=one("SELECT * FROM agents WHERE id=:id",{"id":int(aid)})
                with st.form("agent_edit"):
                    n=st.text_input("Agent Name",old["agent_name"]); p=st.text_input("Phone Number",old["phone_number"])
                    if st.form_submit_button("Save Changes",type="primary"):
                        run("UPDATE agents SET agent_name=:n,phone_number=:p WHERE id=:id",{"n":n.strip(),"p":p.strip(),"id":int(aid)}); st.success("Agent update થયો."); st.rerun()


def page_parties():
    st.title("Party Master")
    agents=q("SELECT id,agent_name FROM agents ORDER BY agent_name")
    with st.expander("＋ Add New Party", expanded=False):
        with st.form("party_add"):
            c=st.columns(3); name=c[0].text_input("Party Name *"); phone=c[1].text_input("Phone Number *"); reference=c[2].selectbox("Reference",REFERENCES)
            c=st.columns(3); address=c[0].text_input("Address"); city=c[1].text_input("City *"); state=c[2].text_input("State *")
            c=st.columns(3); gst=c[0].text_input("Party GST Number"); transport=c[1].text_input("Transport Details"); tgst=c[2].text_input("Transport GST Number")
            aid=st.selectbox("Agent (optional)",[None]+agents.id.tolist(),format_func=lambda x:"— Select Agent —" if x is None else agents.loc[agents.id==x,"agent_name"].iloc[0])
            if st.form_submit_button("Save Party",type="primary"):
                if not all([name.strip(),phone.strip(),city.strip(),state.strip()]): st.error("Party Name, Phone, City અને State જરૂરી છે.")
                elif one("SELECT id FROM parties WHERE LOWER(party_name)=LOWER(:n) AND phone_number=:p AND LOWER(city)=LOWER(:c) AND LOWER(state)=LOWER(:s)",{"n":name.strip(),"p":phone.strip(),"c":city.strip(),"s":state.strip()}): st.error("આ જ વિગતોવાળી Party પહેલેથી છે.")
                else:
                    run("INSERT INTO parties(party_name,phone_number,address,city,state,gst_number,reference,transport_details,transport_gst_number,agent_id) VALUES(:n,:p,:a,:c,:s,:g,:r,:t,:tg,:aid)",{"n":name.strip(),"p":phone.strip(),"a":address.strip(),"c":city.strip(),"s":state.strip(),"g":gst.strip(),"r":reference,"t":transport.strip(),"tg":tgst.strip(),"aid":aid})
                    st.success("Party save થઈ."); st.rerun()
    search=st.text_input("Search Party Name / Phone / City")
    df=q("SELECT p.id AS ID,p.party_name AS \"Party Name\",p.phone_number AS Phone,p.address AS Address,p.city AS City,p.state AS State,p.gst_number AS GST,p.reference AS Reference,COALESCE(a.agent_name,'') AS Agent,p.transport_details AS Transport FROM parties p LEFT JOIN agents a ON a.id=p.agent_id WHERE (:q='' OR LOWER(p.party_name) LIKE LOWER(:likeq) OR p.phone_number LIKE :likeq OR LOWER(p.city) LIKE LOWER(:likeq)) ORDER BY p.party_name LIMIT 1000",{"q":search,"likeq":f"%{search}%"})
    st.dataframe(df,use_container_width=True,hide_index=True)
    if not df.empty:
        if is_admin():
            with st.expander("Edit Selected Party"):
                pid=st.selectbox("Select Party",df.ID.tolist(),format_func=lambda x:df.loc[df.ID==x,"Party Name"].iloc[0],key="party_edit_id")
                old=one("SELECT * FROM parties WHERE id=:id",{"id":int(pid)})
                with st.form("party_edit"):
                    c=st.columns(3); n=c[0].text_input("Party Name",old["party_name"]); p=c[1].text_input("Phone",old["phone_number"]); ref=c[2].selectbox("Reference",REFERENCES,index=REFERENCES.index(old["reference"]) if old["reference"] in REFERENCES else 1)
                    c=st.columns(3); a=c[0].text_input("Address",old["address"]); city=c[1].text_input("City",old["city"]); state=c[2].text_input("State",old["state"])
                    c=st.columns(3); gst=c[0].text_input("GST Number",old["gst_number"]); td=c[1].text_input("Transport",old["transport_details"]); tg=c[2].text_input("Transport GST",old["transport_gst_number"])
                    aid_opts=[None]+agents.id.tolist(); cur=old["agent_id"] if old["agent_id"] in aid_opts else None
                    aid=st.selectbox("Agent",aid_opts,index=aid_opts.index(cur),format_func=lambda x:"— None —" if x is None else agents.loc[agents.id==x,"agent_name"].iloc[0])
                    if st.form_submit_button("Save Changes",type="primary"):
                        run("UPDATE parties SET party_name=:n,phone_number=:p,address=:a,city=:c,state=:s,gst_number=:g,reference=:r,transport_details=:td,transport_gst_number=:tg,agent_id=:aid WHERE id=:id",{"n":n.strip(),"p":p.strip(),"a":a.strip(),"c":city.strip(),"s":state.strip(),"g":gst.strip(),"r":ref,"td":td.strip(),"tg":tg.strip(),"aid":aid,"id":int(pid)}); st.success("Party update થઈ."); st.rerun()
    if is_admin():
        df_download(df,"shubhvastra_parties.csv","Export Parties CSV")
        st.subheader("Import Parties CSV")
        uploaded=st.file_uploader("Party CSV upload કરો",type=["csv"],key="party_csv")
    else:
        uploaded=None
    if is_admin() and uploaded and st.button("Import Party CSV"):
        try:
            rows=list(csv.DictReader(io.StringIO(uploaded.getvalue().decode("utf-8-sig"))))
            agmap={str(x.agent_name).lower():int(x.id) for x in agents.itertuples()}; count=0
            with engine.begin() as conn:
                for idx,r in enumerate(rows,2):
                    nm=(r.get("Party Name") or "").strip(); ph=(r.get("Phone Number") or "").strip(); city=(r.get("City") or "").strip(); state=(r.get("State") or "").strip()
                    if not nm: continue
                    exists=conn.execute(text("SELECT id FROM parties WHERE LOWER(party_name)=LOWER(:n) AND phone_number=:p AND LOWER(city)=LOWER(:c) AND LOWER(state)=LOWER(:s)"),{"n":nm,"p":ph,"c":city,"s":state}).first()
                    if exists: continue
                    conn.execute(text("INSERT INTO parties(party_name,phone_number,address,city,state,gst_number,reference,transport_details,transport_gst_number,agent_id) VALUES(:n,:p,:a,:c,:s,:g,:r,:td,:tg,:aid)"),{"n":nm,"p":ph,"a":r.get("Address", ""),"c":city,"s":state,"g":r.get("Party GST Number", ""),"r":r.get("Reference","DIRECT") or "DIRECT","td":r.get("Transport Details",""),"tg":r.get("Transport GST Number",""),"aid":agmap.get((r.get("Agent Name") or "").strip().lower())}); count+=1
            st.success(f"{count} Party import થઈ."); st.rerun()
        except Exception as e: st.error(f"CSV import failed: {e}")


def page_sku():
    st.title("Item Master")
    tabs=st.tabs(["Add New SKU","Edit SKU"])
    with tabs[0]:
        with st.form("sku_add",clear_on_submit=True):
            c=st.columns(2); sku=c[0].text_input("SKU Number *"); rate=c[1].number_input("Sale Rate *",min_value=0.0,step=1.0,format="%.2f")
            if st.form_submit_button("Save SKU",type="primary"):
                if not sku.strip(): st.error("SKU Number જરૂરી છે.")
                elif one("SELECT id FROM sku_master WHERE LOWER(sku_number)=LOWER(:s)",{"s":sku.strip()}): st.error("આ SKU પહેલેથી છે.")
                else: run("INSERT INTO sku_master(sku_number,sale_rate) VALUES(:s,:r)",{"s":sku.strip(),"r":rate}); st.success("SKU save થયો."); st.rerun()
        table("SELECT sku_number AS \"SKU Number\",sale_rate AS \"Sale Rate\" FROM sku_master ORDER BY sku_number")
    with tabs[1]:
        if not is_admin():
            st.info("SKU edit માત્ર Admin કરી શકે છે.")
        else:
            df=get_skus()
            if df.empty: st.info("હજુ SKU નથી.")
            else:
                sid=st.selectbox("SKU List",df.id.tolist(),format_func=lambda x:df.loc[df.id==x,"sku_number"].iloc[0],key="sku_edit_id")
                old=one("SELECT * FROM sku_master WHERE id=:id",{"id":int(sid)})
                with st.form("sku_edit_form"):
                    n=st.text_input("SKU Number",old["sku_number"]); r=st.number_input("Sale Rate",min_value=0.0,value=float(old["sale_rate"]),step=1.0,format="%.2f")
                    if st.form_submit_button("Save Changes",type="primary"):
                        run("UPDATE sku_master SET sku_number=:s,sale_rate=:r,updated_at=CURRENT_TIMESTAMP WHERE id=:id",{"s":n.strip(),"r":r,"id":int(sid)}); st.success("SKU update થયો. જૂના orders ના rates બદલાતા નથી."); st.rerun()
                st.dataframe(df[["sku_number","sale_rate"]].rename(columns={"sku_number":"SKU Number","sale_rate":"Sale Rate"}),use_container_width=True,hide_index=True)
        st.caption("SKU Master ના rate માત્ર નવા Order માટે default થાય છે. જૂના order_items.piece_rate અલગથી સાચવાય છે.")
        if is_admin():
            df=get_skus(); df_download(df.rename(columns={"sku_number":"SKU Number","sale_rate":"Sale Rate"}),"shubhvastra_sku.csv","Export SKU CSV")


def page_order_form(edit_id=None):
    st.title("New Order" if not edit_id else f"Edit Order #{edit_id}")
    parties=get_parties(); skus=get_skus()
    if parties.empty: st.warning("Order બનાવવા પહેલાં Party Master માં Party ઉમેરો."); return
    existing=one("SELECT * FROM orders WHERE id=:id",{"id":int(edit_id)}) if edit_id else None
    if edit_id and not existing: st.error("Order મળ્યો નથી."); return
    if edit_id and one("SELECT d.id FROM order_dispatches d JOIN order_item_sizes s ON s.id=d.order_size_id JOIN order_items i ON i.id=s.order_item_id WHERE i.order_id=:id LIMIT 1",{"id":int(edit_id)}): st.error("Dispatch થયેલો order edit કરી શકાતો નથી."); return
    old_items=q("SELECT * FROM order_items WHERE order_id=:id ORDER BY sr_no",{"id":int(edit_id)}) if edit_id else pd.DataFrame()
    for ix,row in old_items.iterrows():
        if f"ord_sku_{ix}" not in st.session_state: st.session_state[f"ord_sku_{ix}"]=str(row.particulars)
        if f"ord_rate_{ix}" not in st.session_state: st.session_state[f"ord_rate_{ix}"]=float(row.piece_rate)
        if f"ord_disc_{ix}" not in st.session_state: st.session_state[f"ord_disc_{ix}"]=float(row.discount)
        sz=q("SELECT size_code,ordered_qty FROM order_item_sizes WHERE order_item_id=:id",{"id":int(row.id)})
        for size in SIZES:
            if f"ord_qty_{ix}_{size}" not in st.session_state: st.session_state[f"ord_qty_{ix}_{size}"]=int(sz.loc[sz.size_code==size,"ordered_qty"].sum())
    if "new_order_row_count" not in st.session_state: st.session_state["new_order_row_count"]=max(5,len(old_items) if edit_id else 5)
    row_count=max(5,int(st.session_state["new_order_row_count"]))
    pids=[0]+parties.id.astype(int).tolist()
    def label_party(pid):
        if not pid: return "Select Party"
        rr=parties.loc[parties.id==pid]
        return rr.iloc[0].party_name if not rr.empty else str(pid)
    default_party=int(existing["party_id"]) if existing else 0
    top=st.columns([2,1.2,1])
    party_key=f"ord_party_{edit_id or 'new'}"
    if party_key not in st.session_state: st.session_state[party_key]=default_party
    party_id=top[0].selectbox("Party Name *",pids,index=pids.index(st.session_state[party_key]) if st.session_state[party_key] in pids else 0,format_func=label_party,key=party_key,disabled=bool(edit_id))
    od_default=str(existing["order_date"])[:10] if existing else date.today().isoformat()
    od=top[1].date_input("Order Date *",value=date.fromisoformat(od_default),key=f"ord_date_{edit_id or 'new'}",disabled=bool(edit_id))
    shown_no=int(existing["order_no"]) if existing else get_order_no()
    top[2].text_input("Order Number",str(shown_no),disabled=True,key=f"ord_no_{edit_id or 'new'}")
    if party_id:
        party=parties.loc[parties.id==party_id].iloc[0]
        info=st.columns(4)
        info[0].text_input("Phone",str(party.phone_number),disabled=True,key=f"ord_phone_{edit_id or 'new'}")
        info[1].text_input("City",str(party.city),disabled=True,key=f"ord_city_{edit_id or 'new'}")
        info[2].text_input("State",str(party.state),disabled=True,key=f"ord_state_{edit_id or 'new'}")
        info[3].text_input("Agent",str(party.agent_name),disabled=True,key=f"ord_agent_{edit_id or 'new'}")
    st.subheader("Item Details")
    sku_options=[""]+skus.sku_number.tolist()
    rows=[]
    header=st.columns([.5,3,1,1,1,1,1.2,1.3,1.2])
    for col,label in zip(header,["Sr.","Particulars / SKU","M","L","XL","XXL","Discount","WSP Rate","Qty"]): col.markdown(f"**{label}**")
    last_filled=False
    for ix in range(row_count):
        old=old_items.iloc[ix] if edit_id and ix<len(old_items) else None
        c=st.columns([.5,3,1,1,1,1,1.2,1.3,1.2])
        c[0].write(str(ix+1))
        skey=f"ord_sku_{ix}"
        if skey not in st.session_state: st.session_state[skey]=str(old.particulars) if old is not None else ""
        cur=st.session_state[skey]
        opts=sku_options.copy()
        if cur and cur not in opts: opts.insert(1,cur)
        sku=c[1].selectbox("Particulars / SKU",opts,index=opts.index(cur) if cur in opts else 0,key=skey,label_visibility="collapsed")
        # Always derive a new-order row's rate from the currently selected SKU.
        # For edits, retain the rate already saved on that order.
        sku_rate = float(skus.loc[skus.sku_number==sku,"sale_rate"].iloc[0]) if not skus.empty and sku in skus.sku_number.tolist() else 0.0
        rate_default=float(old.piece_rate) if old is not None else sku_rate
        rkey=f"ord_rate_{ix}"
        if edit_id:
            if rkey not in st.session_state: st.session_state[rkey]=rate_default
        else:
            st.session_state[rkey]=sku_rate
        st.session_state[f"ord_last_sku_{ix}"]=sku
        sizes={}
        for j,size in enumerate(SIZES):
            qkey=f"ord_qty_{ix}_{size}"
            if qkey not in st.session_state: st.session_state[qkey]=0
            sizes[size]=c[2+j].number_input(size,min_value=0,step=1,key=qkey,label_visibility="collapsed")
        disc_key=f"ord_disc_{ix}"
        if disc_key not in st.session_state: st.session_state[disc_key]=float(old.discount) if old is not None else 0.0
        disc=c[6].number_input("Discount",min_value=0.0,step=1.0,format="%.2f",key=disc_key,label_visibility="collapsed",disabled=bool(edit_id))
        # Rate is fetched from SKU Master and displayed read-only without +/- controls.
        rate=float(st.session_state.get(rkey, rate_default) or 0)
        c[7].text_input("WSP Rate", value=f"{rate:,.2f}" if rate else "", key=f"ord_rate_display_{ix}_{edit_id or 'new'}", label_visibility="collapsed", disabled=True, placeholder="Auto rate")
        qty=sum(sizes.values())
        c[8].markdown(f"**{qty}**")
        rows.append({"sku":sku,"rate":rate,"discount":disc,"sizes":sizes})
        if ix==row_count-1 and (sku or qty>0): last_filled=True
    if last_filled and row_count<999:
        st.session_state["new_order_row_count"]=row_count+1
        st.rerun()
    packaging_options=["Chain Bag","Box Packing","Sherwani Bag Packaging"]
    old_pack=[]
    if existing:
        try: old_pack=json.loads(existing.get("packaging") or "[]")
        except Exception: old_pack=[]
    st.subheader("Packaging *")
    pack_cols=st.columns(3)
    packaging=[]
    for pi, pack_name in enumerate(packaging_options):
        if pack_cols[pi].checkbox(pack_name, value=(pack_name in old_pack), key=f"ord_pack_check_{pi}_{edit_id or 'new'}", disabled=bool(edit_id)):
            packaging.append(pack_name)
    st.subheader("GST *")
    gst_options=["5% GST","5-18% GST"]
    old_gst=str(existing.get("gst_type") or "") if existing else ""
    gst=st.radio("GST *",gst_options,index=gst_options.index(old_gst) if old_gst in gst_options else None,horizontal=True,key=f"ord_gst_{edit_id or 'new'}",disabled=bool(edit_id),label_visibility="collapsed")
    narration=st.text_area("Additional Order Details",value=str(existing["narration"] or "") if existing else "",key=f"ord_narration_{edit_id or 'new'}",disabled=bool(edit_id))
    buttons=st.columns(3)
    save=buttons[0].button("Save Order" if not edit_id else "Save Item Changes",type="primary",use_container_width=True)
    clean=buttons[1].button("Clean Form",use_container_width=True)
    if buttons[2].button("Order List",use_container_width=True): st.session_state["pending_page"]="Orders"; st.rerun()
    if clean:
        st.session_state["confirm_clean_order_form"]=True
    if st.session_state.get("confirm_clean_order_form"):
        st.warning("શું તમે આ આખું order form clean કરવા માંગો છો?")
        yes,no=st.columns(2)
        if yes.button("Yes, Clean Form",type="primary"):
            for k in list(st.session_state.keys()):
                if k.startswith(("ord_sku_","ord_rate_","ord_disc_","ord_qty_","ord_last_sku_","ord_pack_","ord_gst_","ord_narration_","ord_party_","ord_date_")): st.session_state.pop(k,None)
            st.session_state["new_order_row_count"]=5; st.session_state.pop("confirm_clean_order_form",None); st.session_state.pop("edit_order_id",None); st.session_state["pending_page"]="New Order"; st.rerun()
        if no.button("No, Go Back"): st.session_state.pop("confirm_clean_order_form",None); st.rerun()
    if save:
        try:
            if not party_id: raise ValueError("પહેલાં Party પસંદ કરો.")
            if not packaging: raise ValueError("Packaging પસંદ કરવું જરૂરી છે.")
            if not gst: raise ValueError("GST option પસંદ કરવો જરૂરી છે.")
            cleaned=[]
            for r in rows:
                if not str(r["sku"]).strip(): continue
                if sum(int(x) for x in r["sizes"].values())<=0: raise ValueError(f"{r['sku']}: ઓછામાં ઓછી એક size quantity આપો.")
                cleaned.append(r)
            if not cleaned: raise ValueError("ઓછામાં ઓછો એક item ઉમેરો.")
            with engine.begin() as conn:
                if edit_id:
                    conn.execute(text("UPDATE orders SET order_date=:d,party_id=:p,packaging=:pack,gst_type=:gst,narration=:n WHERE id=:id"),{"d":od,"p":int(party_id),"pack":json.dumps(packaging),"gst":gst,"n":narration.strip(),"id":int(edit_id)})
                    conn.execute(text("DELETE FROM order_items WHERE order_id=:id"),{"id":int(edit_id)}); oid=int(edit_id)
                    order_no=int(existing["order_no"])
                else:
                    if engine.dialect.name == "postgresql": conn.execute(text("LOCK TABLE orders IN EXCLUSIVE MODE"))
                    order_no=int(conn.execute(text("SELECT COALESCE(MAX(order_no),1100)+1 FROM orders")).scalar_one())
                    oid=conn.execute(text("INSERT INTO orders(order_no,order_date,party_id,packaging,gst_type,narration) VALUES(:no,:d,:p,:pack,:gst,:n) RETURNING id"),{"no":order_no,"d":od,"p":int(party_id),"pack":json.dumps(packaging),"gst":gst,"n":narration.strip()}).scalar_one()
                for ix,r in enumerate(cleaned,1):
                    iid=conn.execute(text("INSERT INTO order_items(order_id,sr_no,particulars,piece_rate,discount) VALUES(:o,:sr,:sku,:rate,:disc) RETURNING id"),{"o":oid,"sr":ix,"sku":r["sku"],"rate":r["rate"],"disc":r["discount"]}).scalar_one()
                    for size,qty in r["sizes"].items():
                        if int(qty)>0: conn.execute(text("INSERT INTO order_item_sizes(order_item_id,size_code,ordered_qty) VALUES(:i,:s,:q)"),{"i":iid,"s":size,"q":int(qty)})
            st.session_state["last_saved_order_id"]=int(oid); st.session_state["show_pdf_prompt"]=True
            st.success(f"Order #{order_no} save થયો. હવે PDF save કરવી છે?")
            st.rerun()
        except Exception as e: st.error(f"Order save ન થયો: {e}")
    if st.session_state.get("show_pdf_prompt") and st.session_state.get("last_saved_order_id"):
        st.info("શું આ Order ની PDF download કરવી છે?")
        y,n=st.columns(2)
        if y.button("Yes — Download PDF",type="primary"):
            oid=int(st.session_state["last_saved_order_id"])
            odf=q("SELECT o.*,p.party_name,p.phone_number,p.address,p.city,p.state,p.gst_number,p.transport_details,p.transport_gst_number,COALESCE(a.agent_name,'') agent_name FROM orders o JOIN parties p ON p.id=o.party_id LEFT JOIN agents a ON a.id=p.agent_id WHERE o.id=:id",{"id":oid}).iloc[0].to_dict()
            try: odf["packaging"]=", ".join(json.loads(odf.get("packaging") or "[]"))
            except Exception: pass
            it=q("SELECT i.sr_no AS Sr,i.particulars AS Particulars,i.piece_rate AS \"WSP Rate\",i.discount AS Discount,s.size_code AS Size,s.ordered_qty AS Qty,(SELECT COALESCE(SUM(d.qty),0) FROM order_dispatches d WHERE d.order_size_id=s.id) AS Dispatched FROM order_items i JOIN order_item_sizes s ON s.order_item_id=i.id WHERE i.order_id=:id ORDER BY i.sr_no,s.size_code",{"id":oid})
            st.download_button("Download Order PDF",order_pdf_bytes(odf,it),file_name=f"shubhvastra_order_{odf['order_no']}.pdf",mime="application/pdf",type="primary")
            st.caption("PDF download button દબાવીને file save કરો. પછી No / Continue દબાવો.")
        if n.button("No — Continue to New Order"):
            for k in list(st.session_state.keys()):
                if k.startswith(("ord_sku_","ord_rate_","ord_disc_","ord_qty_","ord_last_sku_","ord_pack_","ord_gst_","ord_narration_","ord_party_","ord_date_")): st.session_state.pop(k,None)
            st.session_state["new_order_row_count"]=5; st.session_state.pop("show_pdf_prompt",None); st.session_state.pop("last_saved_order_id",None); st.session_state.pop("edit_order_id",None); st.session_state["pending_page"]="New Order"; st.rerun()


def page_orders():
    st.title("Order List")
    if st.button("＋ Create New Order",type="primary"): st.session_state.pop("edit_order_id",None); st.session_state["pending_page"]="New Order"; st.rerun()
    search=st.text_input("Search Order Number / Party")
    df=q("SELECT o.id AS ID,o.order_no AS \"Order Number\",o.order_date AS \"Order Date\",p.party_name AS \"Party Name\",COALESCE(SUM(s.ordered_qty),0) AS Qty,COALESCE(SUM(s.ordered_qty * i.piece_rate),0) AS Amount,COALESCE(a.agent_name,'') AS \"Agent Name\",o.cancelled AS Cancelled FROM orders o JOIN parties p ON p.id=o.party_id LEFT JOIN agents a ON a.id=p.agent_id LEFT JOIN order_items i ON i.order_id=o.id LEFT JOIN order_item_sizes s ON s.order_item_id=i.id WHERE (:s='' OR CAST(o.order_no AS VARCHAR) LIKE :likeq OR LOWER(p.party_name) LIKE LOWER(:likeq)) GROUP BY o.id,o.order_no,o.order_date,p.party_name,a.agent_name,o.cancelled ORDER BY o.order_no ASC LIMIT 1000",{"s":search,"likeq":f"%{search}%"})
    st.dataframe(df.drop(columns=["ID"]) if not df.empty else df,use_container_width=True,hide_index=True)
    if not df.empty:
        oid=st.selectbox("Select Order to view/edit",df.ID.tolist(),format_func=lambda x:f"#{df.loc[df.ID==x,'Order Number'].iloc[0]} — {df.loc[df.ID==x,'Party Name'].iloc[0]}")
        c=st.columns(3)
        if c[0].button("View Order Details",use_container_width=True): st.session_state["selected_order"]=int(oid); st.session_state["pending_page"]="Order Details"; st.rerun()
        dispatched=bool(one("SELECT id FROM order_dispatches d JOIN order_item_sizes s ON s.id=d.order_size_id JOIN order_items i ON i.id=s.order_item_id WHERE i.order_id=:id LIMIT 1",{"id":int(oid)}))
        if c[1].button("Edit Order",disabled=dispatched,use_container_width=True): st.session_state["edit_order_id"]=int(oid); st.session_state["pending_page"]="New Order"; st.rerun()
        if c[2].button("Cancel / Restore Order",use_container_width=True):
            old=int(one("SELECT cancelled FROM orders WHERE id=:id",{"id":int(oid)})["cancelled"])
            run("UPDATE orders SET cancelled=:v WHERE id=:id",{"v":0 if old else 1,"id":int(oid)}); st.success("Order status update થયો."); st.rerun()
    if not df.empty:
        st.subheader("Order Actions")
        order_ids=df.ID.astype(int).tolist()
        chosen=st.selectbox("Choose Order",order_ids,format_func=lambda x:f"Order #{int(df.loc[df.ID==x, 'Order Number'].iloc[0])} — {df.loc[df.ID==x, 'Party Name'].iloc[0]}",key="orders_action_select")
        act=st.columns(4)
        if act[0].button("Edit Order",use_container_width=True):
            st.session_state["edit_order_id"]=int(chosen); st.session_state["pending_page"]="New Order"; st.rerun()
        pdfrow=one("SELECT o.*,p.party_name,p.phone_number,p.address,p.city,p.state,p.gst_number,p.transport_details,p.transport_gst_number,COALESCE(a.agent_name,'') agent_name FROM orders o JOIN parties p ON p.id=o.party_id LEFT JOIN agents a ON a.id=p.agent_id WHERE o.id=:id",{"id":int(chosen)})
        if pdfrow:
            pdfrow["packaging"] = ", ".join(json.loads(pdfrow.get("packaging") or "[]")) if str(pdfrow.get("packaging") or "").startswith("[") else str(pdfrow.get("packaging") or "")
            pdfitems=q("SELECT i.sr_no AS Sr,i.particulars AS Particulars,i.piece_rate AS \"WSP Rate\",i.discount AS Discount,s.size_code AS Size,s.ordered_qty AS Qty,(SELECT COALESCE(SUM(d.qty),0) FROM order_dispatches d WHERE d.order_size_id=s.id) AS Dispatched FROM order_items i JOIN order_item_sizes s ON s.order_item_id=i.id WHERE i.order_id=:id ORDER BY i.sr_no,s.size_code",{"id":int(chosen)})
            act[1].download_button("Download PDF",order_pdf_bytes(pdfrow,pdfitems),file_name=f"shubhvastra_order_{pdfrow['order_no']}.pdf",mime="application/pdf",use_container_width=True)
        if str(current_user().get("role", "staff")).lower() in ("admin", "member"):
            if act[2].button("Delete Order",use_container_width=True): st.session_state["confirm_delete_order_id"]=int(chosen)
        if str(current_user().get("role", "staff")).lower() in ("admin", "member") and st.session_state.get("confirm_delete_order_id")==int(chosen):
            st.warning("Delete order માટે authorized delete password નાખો. આ action પાછું ફેરવી શકાતું નથી.")
            dp=st.text_input("Delete Password",type="password",key="order_delete_password")
            if st.button("Confirm Delete",type="primary"):
                if dp != "9414": st.error("Password ખોટો છે.")
                else:
                    dispatched=one("SELECT d.id FROM order_dispatches d JOIN order_item_sizes s ON s.id=d.order_size_id JOIN order_items i ON i.id=s.order_item_id WHERE i.order_id=:id LIMIT 1",{"id":int(chosen)})
                    if dispatched: st.error("Dispatch થયેલો order delete કરી શકાતો નથી.")
                    else:
                        run("DELETE FROM order_items WHERE order_id=:id",{"id":int(chosen)}); run("DELETE FROM orders WHERE id=:id",{"id":int(chosen)})
                        st.session_state.pop("confirm_delete_order_id",None); st.success("Order delete થયો."); st.rerun()
    st.subheader("CSV Import / Export")
    a,b=st.columns(2)
    with a:
        sample=pd.DataFrame(columns=["Order Number (optional)","Order Date (YYYY-MM-DD)","Party Name","Particulars","Piece Rate","Discount","M Qty","L Qty","XL Qty","XXL Qty","Narration"])
        sample.loc[0]=["","2026-10-27","Existing Party","SKU-001",0,0,0,0,0,0,""]
        df_download(sample,"shubhvastra_order_import_template.csv","Download Order CSV Template")
        up=st.file_uploader("Order CSV Upload",type=["csv"],key="order_csv")
        if up and st.button("Import Order CSV",type="primary"):
            try:
                rows=list(csv.DictReader(io.StringIO(up.getvalue().decode("utf-8-sig")))); made=0
                with engine.begin() as conn:
                    for line,r in enumerate(rows,2):
                        pname=(r.get("Party Name") or "").strip(); sku=(r.get("Particulars") or "").strip(); od=(r.get("Order Date (YYYY-MM-DD)") or "").strip()
                        if not pname and not sku: continue
                        party=conn.execute(text("SELECT id FROM parties WHERE LOWER(party_name)=LOWER(:n) ORDER BY id LIMIT 1"),{"n":pname}).first()
                        if not party: raise ValueError(f"Row {line}: Party not found: {pname}")
                        if not sku: raise ValueError(f"Row {line}: Particulars missing")
                        datetime.strptime(od,"%Y-%m-%d")
                        nums={s:int(r.get(f"{s} Qty") or 0) for s in SIZES}
                        if sum(nums.values())<=0: raise ValueError(f"Row {line}: quantity missing")
                        given=(r.get("Order Number (optional)") or "").strip()
                        no=int(given) if given else int(conn.execute(text("SELECT COALESCE(MAX(order_no),1100)+1 FROM orders")).scalar_one())
                        if conn.execute(text("SELECT id FROM orders WHERE order_no=:n"),{"n":no}).first(): raise ValueError(f"Row {line}: duplicate order number {no}")
                        oid=conn.execute(text("INSERT INTO orders(order_no,order_date,party_id,narration) VALUES(:no,:d,:p,:n) RETURNING id"),{"no":no,"d":od,"p":int(party[0]),"n":r.get("Narration","")}).scalar_one()
                        iid=conn.execute(text("INSERT INTO order_items(order_id,sr_no,particulars,piece_rate,discount) VALUES(:o,1,:s,:r,:d) RETURNING id"),{"o":oid,"s":sku,"r":float(r.get("Piece Rate") or 0),"d":float(r.get("Discount") or 0)}).scalar_one()
                        for size,qty in nums.items():
                            if qty>0: conn.execute(text("INSERT INTO order_item_sizes(order_item_id,size_code,ordered_qty) VALUES(:i,:s,:q)"),{"i":iid,"s":size,"q":qty})
                        made+=1
                st.success(f"{made} order import થયા."); st.rerun()
            except Exception as e: st.error(f"CSV import રદ થયો: {e}")
    with b:
        exp=q("SELECT o.order_no AS \"Order Number\",o.order_date AS \"Order Date\",p.party_name AS \"Party Name\",i.particulars AS Particulars,i.piece_rate AS \"Piece Rate\",i.discount AS Discount,s.size_code AS Size,s.ordered_qty AS Qty,o.narration AS Narration FROM orders o JOIN parties p ON p.id=o.party_id JOIN order_items i ON i.order_id=o.id JOIN order_item_sizes s ON s.order_item_id=i.id ORDER BY o.order_no")
        df_download(exp,"shubhvastra_orders_export.csv","Export Orders CSV")


def page_order_details():
    oid=int(st.session_state.get("selected_order",0)); o=one("SELECT o.*,p.party_name,p.phone_number,p.address,p.city,p.state,p.reference,a.agent_name FROM orders o JOIN parties p ON p.id=o.party_id LEFT JOIN agents a ON a.id=p.agent_id WHERE o.id=:id",{"id":oid})
    if not o: st.error("Order મળ્યો નથી."); return
    st.title(f"Order #{o['order_no']} Details")
    st.write(f"**Party:** {o['party_name']} · **Date:** {o['order_date']} · **Phone:** {o['phone_number']}")
    st.write(f"**Address:** {o['address']}, {o['city']}, {o['state']} · **Agent:** {o['agent_name'] or '-'}")
    df=q("SELECT i.sr_no AS Sr,i.particulars AS Particulars,i.piece_rate AS \"Piece Rate\",i.discount AS Discount,s.size_code AS Size,s.ordered_qty AS Qty,s.cancelled AS Cancelled,(SELECT COALESCE(SUM(d.qty),0) FROM order_dispatches d WHERE d.order_size_id=s.id) AS Dispatched FROM order_items i JOIN order_item_sizes s ON s.order_item_id=i.id WHERE i.order_id=:id ORDER BY i.sr_no,s.size_code",{"id":oid})
    st.dataframe(df,use_container_width=True,hide_index=True)
    st.write("**Additional Order Details:**",o["narration"] or "—")
    df_download(df,f"order_{o['order_no']}_details.csv","Download Order Details CSV")
    pdf=order_pdf_bytes(o,df)
    st.download_button("Download A4 Order PDF",pdf,file_name=f"shubhvastra_order_{o['order_no']}.pdf",mime="application/pdf",type="primary")


def page_dispatch():
    st.title("Pending to Dispatched")
    df=q("""SELECT o.id order_id,o.order_no AS \"Order No\",o.order_date AS \"Order Date\",p.party_name AS \"Party Name\",i.particulars AS Particulars,s.id size_id,s.size_code AS Size,s.ordered_qty AS \"Ordered Qty\",s.cancelled AS Cancelled,(SELECT COALESCE(SUM(d.qty),0) FROM order_dispatches d WHERE d.order_size_id=s.id) AS Dispatched FROM orders o JOIN parties p ON p.id=o.party_id JOIN order_items i ON i.order_id=o.id JOIN order_item_sizes s ON s.order_item_id=i.id WHERE o.cancelled=0 ORDER BY o.order_no DESC,i.sr_no,s.size_code""")
    if not df.empty:
        df["Pending Qty"]=df["Ordered Qty"]-df["Dispatched"]
        st.dataframe(df.drop(columns=["order_id","size_id"]),use_container_width=True,hide_index=True)
        eligible=df[(df["Pending Qty"]>0)&(df["Cancelled"]==0)]
        if not eligible.empty:
            opts=eligible.size_id.astype(int).tolist()
            sid=st.selectbox("Select pending size row",opts,format_func=lambda x: f"Order #{eligible.loc[eligible.size_id==x,'Order No'].iloc[0]} · {eligible.loc[eligible.size_id==x,'Party Name'].iloc[0]} · {eligible.loc[eligible.size_id==x,'Particulars'].iloc[0]} · {eligible.loc[eligible.size_id==x,'Size'].iloc[0]} · Pending {eligible.loc[eligible.size_id==x,'Pending Qty'].iloc[0]}")
            rec=eligible.loc[eligible.size_id==sid].iloc[0]
            with st.form("dispatch_save"):
                c=st.columns(4); qty=c[0].number_input("Dispatch Qty",min_value=1,max_value=int(rec["Pending Qty"]),value=1,step=1); dd=c[1].date_input("Dispatch Date",value=date.today()); invoice=c[2].text_input("Invoice Number"); details=c[3].text_input("Details")
                if st.form_submit_button("Save Dispatch",type="primary"):
                    run("INSERT INTO order_dispatches(order_size_id,dispatched_size,qty,dispatch_date,details,invoice_number) VALUES(:id,:s,:q,:d,:t,:i)",{"id":int(sid),"s":str(rec["Size"]),"q":int(qty),"d":dd,"t":details.strip(),"i":invoice.strip()}); st.success("Dispatch save થયો."); st.rerun()
        else: st.success("કોઈ pending quantity બાકી નથી.")
    else: st.info("હજુ Order નથી.")
    st.subheader("Dispatch History")
    hist=q("SELECT d.id AS ID,o.order_no AS \"Order No\",p.party_name AS \"Party Name\",i.particulars AS Particulars,d.dispatched_size AS Size,d.qty AS Qty,d.dispatch_date AS \"Dispatch Date\",d.invoice_number AS \"Invoice Number\",d.details AS Details FROM order_dispatches d JOIN order_item_sizes s ON s.id=d.order_size_id JOIN order_items i ON i.id=s.order_item_id JOIN orders o ON o.id=i.order_id JOIN parties p ON p.id=o.party_id ORDER BY d.id DESC LIMIT 1000")
    st.dataframe(hist,use_container_width=True,hide_index=True); df_download(hist,"shubhvastra_dispatch_history.csv","Export Dispatch History")
    st.subheader("Import Dispatch CSV")
    sample=pd.DataFrame(columns=["Order Number","Party Name","Particulars","Size","Dispatch Qty","Dispatch Date (YYYY-MM-DD)","Invoice Number","Details"])
    df_download(sample,"shubhvastra_dispatch_import_template.csv","Download Dispatch CSV Template")
    up=st.file_uploader("Dispatch CSV upload",type=["csv"],key="dispatch_csv")
    if up and st.button("Import Dispatch CSV"):
        try:
            rows=list(csv.DictReader(io.StringIO(up.getvalue().decode("utf-8-sig")))); count=0
            with engine.begin() as conn:
                for line,r in enumerate(rows,2):
                    no=int(r.get("Order Number") or 0); pname=(r.get("Party Name") or "").strip(); sku=(r.get("Particulars") or "").strip(); size=(r.get("Size") or "").strip().upper(); qty=int(r.get("Dispatch Qty") or 0); dd=(r.get("Dispatch Date (YYYY-MM-DD)") or "").strip()
                    if not no and not pname and not sku: continue
                    if size not in SIZES or qty<=0: raise ValueError(f"Row {line}: Size/Dispatch Qty invalid")
                    datetime.strptime(dd,"%Y-%m-%d")
                    sr=conn.execute(text("SELECT s.id,s.ordered_qty,s.cancelled,o.cancelled order_cancelled,(SELECT COALESCE(SUM(d.qty),0) FROM order_dispatches d WHERE d.order_size_id=s.id) dispatched FROM order_item_sizes s JOIN order_items i ON i.id=s.order_item_id JOIN orders o ON o.id=i.order_id JOIN parties p ON p.id=o.party_id WHERE o.order_no=:no AND LOWER(p.party_name)=LOWER(:p) AND LOWER(i.particulars)=LOWER(:sku) AND s.size_code=:sz"),{"no":no,"p":pname,"sku":sku,"sz":size}).first()
                    if not sr: raise ValueError(f"Row {line}: Matching order/party/SKU/size not found")
                    if sr.cancelled or sr.order_cancelled or qty>int(sr.ordered_qty)-int(sr.dispatched): raise ValueError(f"Row {line}: dispatch quantity pending કરતાં વધુ છે")
                    conn.execute(text("INSERT INTO order_dispatches(order_size_id,dispatched_size,qty,dispatch_date,invoice_number,details) VALUES(:id,:s,:q,:d,:i,:t)"),{"id":int(sr.id),"s":size,"q":qty,"d":dd,"i":r.get("Invoice Number", ""),"t":r.get("Details", "")}); count+=1
            st.success(f"{count} dispatch row import થઈ."); st.rerun()
        except Exception as e: st.error(f"Dispatch import રદ થયો: {e}")


def page_reports():
    st.title("Order Reports")
    tabs=st.tabs(["Pending Order List","Agent Wise Order","SKU Wise State Sale Report"])
    with tabs[0]:
        df=q("SELECT o.order_no AS \"Order No\",o.order_date AS \"Order Date\",p.party_name AS \"Party Name\",i.particulars AS Particulars,s.size_code AS Size,s.ordered_qty AS \"Ordered Qty\",s.cancelled AS Cancelled,(SELECT COALESCE(SUM(d.qty),0) FROM order_dispatches d WHERE d.order_size_id=s.id) AS Dispatched FROM orders o JOIN parties p ON p.id=o.party_id JOIN order_items i ON i.order_id=o.id JOIN order_item_sizes s ON s.order_item_id=i.id WHERE o.cancelled=0 ORDER BY o.order_no DESC")
        if not df.empty: df["Pending Qty"]=(df["Ordered Qty"]-df["Dispatched"]).clip(lower=0)
        st.dataframe(df,use_container_width=True,hide_index=True); df_download(df,"shubhvastra_pending_order_list.csv","Export Pending Orders")
    with tabs[1]:
        agents=q("SELECT a.id,a.agent_name AS \"Agent Name\",COUNT(DISTINCT p.id) AS \"Party Count\",COUNT(DISTINCT o.id) AS \"Order Count\" FROM agents a LEFT JOIN parties p ON p.agent_id=a.id LEFT JOIN orders o ON o.party_id=p.id GROUP BY a.id,a.agent_name ORDER BY a.agent_name")
        st.caption("Agent પર click કરવા માટે નીચે Agent પસંદ કરો, પછી તેની Parties અને Party Orders જુઓ.")
        st.dataframe(agents.drop(columns=["id"]) if not agents.empty else agents,use_container_width=True,hide_index=True)
        if not agents.empty:
            aid=st.selectbox("Agent Name",agents.id.tolist(),format_func=lambda x:agents.loc[agents.id==x,"Agent Name"].iloc[0])
            parties=q("SELECT p.id,p.party_name AS \"Party Name\",p.city AS City,p.state AS State,COUNT(DISTINCT o.id) AS \"Order Count\" FROM parties p LEFT JOIN orders o ON o.party_id=p.id WHERE p.agent_id=:id GROUP BY p.id,p.party_name,p.city,p.state ORDER BY p.party_name",{"id":int(aid)})
            st.subheader("Party List"); st.dataframe(parties.drop(columns=["id"]) if not parties.empty else parties,use_container_width=True,hide_index=True)
            if not parties.empty:
                pid=st.selectbox("Party Name",parties.id.tolist(),format_func=lambda x:parties.loc[parties.id==x,"Party Name"].iloc[0])
                st.subheader("Party Order Details")
                odf=q("SELECT o.id,o.order_no AS \"Order No\",o.order_date AS \"Order Date\",o.narration AS \"Additional Order Details\",o.cancelled AS Cancelled FROM orders o WHERE o.party_id=:id ORDER BY o.order_no DESC",{"id":int(pid)})
                st.dataframe(odf.drop(columns=["id"]) if not odf.empty else odf,use_container_width=True,hide_index=True)
                if not odf.empty:
                    oid=st.selectbox("View Order",odf.id.tolist(),format_func=lambda x:f"Order #{odf.loc[odf.id==x,'Order No'].iloc[0]}")
                    det=q("SELECT i.particulars AS Particulars,i.piece_rate AS \"Piece Rate\",i.discount AS Discount,s.size_code AS Size,s.ordered_qty AS Qty,(SELECT COALESCE(SUM(d.qty),0) FROM order_dispatches d WHERE d.order_size_id=s.id) AS Dispatched FROM order_items i JOIN order_item_sizes s ON s.order_item_id=i.id WHERE i.order_id=:id ORDER BY i.sr_no,s.size_code",{"id":int(oid)})
                    st.dataframe(det,use_container_width=True,hide_index=True)
    with tabs[2]:
        df=q("SELECT i.particulars AS SKU,p.state AS State,SUM(s.ordered_qty) AS \"Ordered Qty\",SUM((SELECT COALESCE(SUM(d.qty),0) FROM order_dispatches d WHERE d.order_size_id=s.id)) AS \"Dispatched Qty\" FROM order_items i JOIN orders o ON o.id=i.order_id JOIN parties p ON p.id=o.party_id JOIN order_item_sizes s ON s.order_item_id=i.id GROUP BY i.particulars,p.state ORDER BY i.particulars,p.state")
        st.dataframe(df,use_container_width=True,hide_index=True)
        if is_admin(): df_download(df,"shubhvastra_sku_state_sale_report.csv","Export SKU State Report")


def page_users():
    if not is_admin():
        st.error("આ વિભાગ ફક્ત Main Admin માટે છે.")
        return
    st.title("Admin Panel / User Access")
    st.caption("અહીંથી login username/password, role અને user access નિયંત્રિત કરો. Login screen પર Forgot Password નથી.")
    with st.expander("Create New User", expanded=True):
        with st.form("new_user"):
            c=st.columns(3)
            username=c[0].text_input("Username", key="create_username")
            password=c[1].text_input("Password (minimum 10 characters)",type="password",key="create_password")
            role=c[2].selectbox("Role",["admin","member","staff"],format_func=lambda x:x.title(),key="create_role")
            if st.form_submit_button("Create User",type="primary"):
                if not username.strip() or len(password)<10:
                    st.error("Username અને ઓછામાં ઓછો 10-character password જરૂરી છે.")
                elif one("SELECT id FROM users WHERE LOWER(username)=LOWER(:u)",{"u":username.strip()}):
                    st.error("આ username પહેલેથી છે.")
                else:
                    run("INSERT INTO users(username,password_hash,role,active) VALUES(:u,:p,:r,1)",{"u":username.strip(),"p":generate_password_hash(password),"r":role})
                    st.success("User create થયો.")
                    st.rerun()
    df=q('SELECT id AS ID,username AS Username,role AS Role,active AS Active,created_at AS "Created At" FROM users ORDER BY username')
    st.subheader("Existing Users")
    st.dataframe(df.drop(columns=["ID"], errors="ignore"),use_container_width=True,hide_index=True)
    if not df.empty:
        uid=st.selectbox("Select User",df.ID.tolist(),format_func=lambda x:df.loc[df.ID==x,"Username"].iloc[0],key="admin_selected_user")
        selected=one("SELECT id,username,role,active FROM users WHERE id=:id",{"id":int(uid)})
        with st.form("edit_user_credentials"):
            st.write(f"Selected user: **{selected['username']}**")
            new_username=st.text_input("Change Username",value=selected["username"])
            new_password=st.text_input("Set New Password (leave blank to keep current)",type="password")
            new_role=st.selectbox("Role",["staff","admin"],index=0 if selected["role"]=="staff" else 1)
            active=st.checkbox("User can login",value=bool(selected["active"]))
            save=st.form_submit_button("Save User Settings",type="primary")
        if save:
            if not new_username.strip():
                st.error("Username ખાલી ન રાખો.")
            elif len(new_password)>0 and len(new_password)<10:
                st.error("નવો password ઓછામાં ઓછો 10 characters નો હોવો જોઈએ.")
            elif one("SELECT id FROM users WHERE LOWER(username)=LOWER(:u) AND id<>:id",{"u":new_username.strip(),"id":int(uid)}):
                st.error("આ username બીજા user દ્વારા વપરાય છે.")
            elif int(uid)==int(current_user()["id"]) and not active:
                st.error("તમારા પોતાના logged-in admin account ને disable કરી શકતા નથી.")
            else:
                params={"u":new_username.strip(),"r":new_role,"a":1 if active else 0,"id":int(uid)}
                run("UPDATE users SET username=:u,role=:r,active=:a WHERE id=:id",params)
                if new_password:
                    run("UPDATE users SET password_hash=:p WHERE id=:id",{"p":generate_password_hash(new_password),"id":int(uid)})
                if int(uid)==int(current_user()["id"]):
                    st.session_state["authenticated_user"].update({"username":new_username.strip(),"role":new_role})
                st.success("User settings update થઈ.")
                st.rerun()


BACKUP_TABLES = ["agents", "parties", "sku_master", "orders", "order_items", "order_item_sizes", "order_dispatches", "users"]
BACKUP_FORMAT_VERSION = 1


def make_full_backup():
    """Create a portable, app-level backup containing every application table."""
    payload = {"format": "shubhvastra_backup", "version": BACKUP_FORMAT_VERSION,
               "created_at": datetime.now().isoformat(timespec="seconds"),
               "source_database": engine.dialect.name, "tables": {}}
    for table_name in BACKUP_TABLES:
        payload["tables"][table_name] = q(f'SELECT * FROM "{table_name}"').to_dict(orient="records")
    raw = json.dumps(payload, ensure_ascii=False, default=str, indent=2).encode("utf-8")
    mem = io.BytesIO()
    import zipfile
    with zipfile.ZipFile(mem, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("shubhvastra_backup.json", raw)
        zf.writestr("README.txt", "SHUBHVASTRA app backup. Restore this ZIP from Utilities / Backup & Restore. Keep this file private because it may contain business and user data.")
    return mem.getvalue()


def _apply_backup_payload(payload):
    """Validate and restore a payload into the configured database."""
    if payload.get("format") != "shubhvastra_backup" or payload.get("version") != BACKUP_FORMAT_VERSION:
        raise ValueError("Backup format/version ઓળખી શકાયું નથી.")
    tables = payload.get("tables", {})
    if any(name not in tables or not isinstance(tables[name], list) for name in BACKUP_TABLES):
        raise ValueError("Backup માં જરૂરી tables ખૂટે છે અથવા data format ખોટો છે.")
    inspector = inspect(engine)
    for table_name in BACKUP_TABLES:
        if not inspector.has_table(table_name):
            raise ValueError(f"Database માં {table_name} table મળ્યું નથી. App ને પહેલાં reboot કરો.")
        allowed = {col["name"] for col in inspector.get_columns(table_name)}
        for row in tables[table_name]:
            if not isinstance(row, dict) or not set(row).issubset(allowed):
                raise ValueError(f"{table_name} table ના columns હાલના app સાથે મેળ ખાતા નથી. જૂના database માટે migration જરૂરી હોઈ શકે છે.")
    # Delete children first to satisfy foreign keys, then restore parents first.
    with engine.begin() as conn:
        for table_name in reversed(BACKUP_TABLES):
            conn.execute(text(f'DELETE FROM "{table_name}"'))
        for table_name in BACKUP_TABLES:
            rows = tables[table_name]
            if not rows:
                continue
            columns = list(rows[0].keys())
            if not columns:
                continue
            col_sql = ", ".join(f'"{c}"' for c in columns)
            val_sql = ", ".join(f':v{i}' for i in range(len(columns)))
            stmt = text(f'INSERT INTO "{table_name}" ({col_sql}) VALUES ({val_sql})')
            for row in rows:
                conn.execute(stmt, {f'v{i}': row.get(col) for i, col in enumerate(columns)})
        if engine.dialect.name == "postgresql":
            for table_name in BACKUP_TABLES:
                conn.execute(text(f"SELECT setval(pg_get_serial_sequence(:tbl, 'id'), COALESCE((SELECT MAX(id) FROM \"{table_name}\"), 1), (SELECT MAX(id) IS NOT NULL FROM \"{table_name}\"))"), {"tbl": table_name})
    return {name: len(tables[name]) for name in BACKUP_TABLES}


def restore_full_backup(uploaded_bytes, filename="backup.zip"):
    """Restore app ZIP backups or SQLite .db/.sqlite/.sqlite3 files."""
    import zipfile, sqlite3
    if uploaded_bytes[:16] == b"SQLite format 3\x00" or filename.lower().endswith((".db", ".sqlite", ".sqlite3")):
        source = sqlite3.connect(":memory:")
        try:
            source.deserialize(uploaded_bytes)
            available = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            missing = [name for name in BACKUP_TABLES if name not in available]
            if missing:
                raise ValueError("આ database માં Shubhvastra ના જરૂરી tables નથી: " + ", ".join(missing) + ". જો આ જૂની party_reporting.db છે તો પહેલા migration format માં convert કરવી પડશે.")
            payload = {"format": "shubhvastra_backup", "version": BACKUP_FORMAT_VERSION, "tables": {}}
            for name in BACKUP_TABLES:
                cursor = source.execute(f'SELECT * FROM "{name}"')
                columns = [item[0] for item in cursor.description]
                payload["tables"][name] = [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            source.close()
        return _apply_backup_payload(payload)
    try:
        with zipfile.ZipFile(io.BytesIO(uploaded_bytes), "r") as zf:
            if "shubhvastra_backup.json" not in zf.namelist():
                raise ValueError("આ ZIP માં Shubhvastra backup મળ્યું નથી. Full Backup ZIP અથવા .db/.sqlite database file પસંદ કરો.")
            payload = json.loads(zf.read("shubhvastra_backup.json").decode("utf-8"))
    except zipfile.BadZipFile as exc:
        raise ValueError("આ file ઓળખી શકાતી નથી. Shubhvastra backup .zip અથવા compatible .db/.sqlite/.sqlite3 ફાઇલ upload કરો. .rar સીધું support થતું નથી.") from exc
    return _apply_backup_payload(payload)


def make_sqlite_database_backup():
    """Export a portable SQLite database snapshot from the live app tables."""
    import sqlite3
    db = sqlite3.connect(":memory:")
    try:
        for table_name in BACKUP_TABLES:
            frame = q(f'SELECT * FROM "{table_name}"')
            frame.to_sql(table_name, db, if_exists="replace", index=False)
        db.commit()
        return db.serialize()
    finally:
        db.close()


def page_settings():
    st.title("Utilities / Admin Panel")
    if not is_admin():
        st.error("Utilities ફક્ત Main Admin માટે ઉપલબ્ધ છે.")
        return
    user_tab, backup_tab = st.tabs(["User Name & Password", "Backup & Restore"])
    with user_tab:
        page_users()
    with backup_tab:
        page_backup_restore()

def page_backup_restore():
    st.title("Backup & Restore")
    st.info("તમારો સંપૂર્ણ app data backup ZIP માં download કરો. પછી જરૂર પડે ત્યારે આ ZIP upload કરીને data restore કરી શકો છો.")
    st.subheader("Database Status")
    st.write(f"Database engine: **{engine.dialect.name}**")
    st.write(f"Database URL configured: **{'Yes' if db_url() else 'No — local SQLite mode'}**")
    if engine.dialect.name=="sqlite":
        st.warning("Local SQLite mode છે. Streamlit Cloud પર permanent/shared data માટે managed PostgreSQL અને DATABASE_URL configure કરવું જરૂરી છે.")
    st.divider()
    st.subheader("1. Full Backup Download")
    st.write("Party, Agent, SKU, Orders, order items, dispatch history અને app users સહિત તમામ tables નો backup.")
    try:
        backup_bytes = make_full_backup()
        st.download_button("⬇️ Download Full Backup ZIP", backup_bytes,
                           file_name=f"shubhvastra_backup_{date.today().isoformat()}.zip",
                           mime="application/zip", type="primary", use_container_width=False)
        sqlite_bytes = make_sqlite_database_backup()
        st.download_button("⬇️ Download Database File (.db)", sqlite_bytes,
                           file_name=f"shubhvastra_database_{date.today().isoformat()}.db",
                           mime="application/vnd.sqlite3", use_container_width=False)
    except Exception as e:
        st.error(f"Backup બનાવવામાં સમસ્યા: {e}")
    st.divider()
    st.subheader("2. Restore / Upload Previous Backup")
    st.warning("Restore કરવાથી હાલના app ના records replace થશે. Restore કરતાં પહેલાં ઉપરથી હાલનો backup download કરી રાખો.")
    uploaded_backup = st.file_uploader("Backup ZIP અથવા database file (.db, .sqlite, .sqlite3) upload કરો", type=["zip", "db", "sqlite", "sqlite3"], key="full_backup_restore")
    confirm_restore = st.checkbox("હું સમજું છું કે Restore કરવાથી હાલનો data replace થશે.", key="confirm_full_restore")
    if st.button("Restore Uploaded Backup", type="primary", disabled=(uploaded_backup is None or not confirm_restore)):
        try:
            counts = restore_full_backup(uploaded_backup.getvalue(), uploaded_backup.name)
            st.success("Backup restore સફળ થયું. Restored records: " + " · ".join(f"{name}: {count}" for name, count in counts.items()))
            st.rerun()
        except Exception as e:
            st.error(f"Restore નિષ્ફળ ગયું: {e}")
    st.caption("નોંધ: Shubhvastra backup ZIP અથવા આ app માંથી download કરેલી compatible .db/.sqlite/.sqlite3 ફાઇલ upload કરો. .rar અને CSV સીધા restore થતા નથી. જૂના/અલગ schema વાળા database માટે migration જરૂરી હોઈ શકે છે.")


# Apply navigation requests before creating the sidebar widget, so buttons can switch pages reliably.
if "pending_page" in st.session_state:
    st.session_state["main_navigation"] = st.session_state.pop("pending_page")
    st.session_state["page"] = st.session_state["main_navigation"]

header()
if not require_login():
    if int(one("SELECT COUNT(*) AS n FROM users WHERE role='admin' AND active=1")["n"]) == 0:
        show_first_admin_setup()
    else:
        show_login()
    st.stop()

user=current_user()
role_name = str(user.get("role", "staff")).lower()
if role_name == "admin":
    menu=["Dashboard","Party Master","Agent Master","Item Master","New Order","Orders","Order Details","Pending to Dispatched","Order Reports","Utilities / Admin Panel"]
elif role_name == "member":
    menu=["Dashboard","Party Master","Agent Master","Item Master","New Order","Orders","Order Details","Pending to Dispatched","Order Reports"]
else:
    menu=["Dashboard","Orders","Order Details","Pending to Dispatched","Order Reports"]
with st.sidebar:
    logo=BASE/"static"/"shubhvastra_logo.png"
    if logo.exists(): st.image(str(logo),width=125)
    st.markdown("### SHUBHVASTRA")
    st.caption(f"Order Management · 2026 · {user['role'].title()}")
    st.caption(f"Logged in: {user['username']}")
    if st.button("Logout",use_container_width=True):
        st.session_state.pop("authenticated_user",None)
        st.session_state.pop("main_navigation",None)
        st.rerun()
    default=st.session_state.get("page","Dashboard")
    if default not in menu: default="Dashboard"
    page=st.radio("Navigation",menu,index=menu.index(default),key="main_navigation")
    st.session_state["page"]=page
if page=="Dashboard": page_dashboard()
elif page=="Party Master": page_parties()
elif page=="Agent Master": page_agents()
elif page=="Item Master": page_sku()
elif page=="New Order":
    if str(user.get("role", "staff")).lower() == "staff": st.error("આ વિભાગ માટે પરવાનગી નથી.")
    else: page_order_form(st.session_state.get("edit_order_id"))
elif page=="Orders": page_orders()
elif page=="Order Details": page_order_details()
elif page=="Pending to Dispatched": page_dispatch()
elif page=="Order Reports": page_reports()
elif page=="Utilities / Admin Panel" and is_admin(): page_settings()

st.markdown(f"<div style='text-align:center;color:#8b98a9;font-size:11px;padding:20px'>SHUBHVASTRA · Secure Login · {user['role'].title()}</div>",unsafe_allow_html=True)
