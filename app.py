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
from reportlab.lib.enums import TA_CENTER
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
      f"CREATE TABLE IF NOT EXISTS orders (id {identity}, order_no INTEGER NOT NULL UNIQUE, order_date DATE NOT NULL, delivery_date DATE NULL, party_id INTEGER NOT NULL REFERENCES parties(id) ON DELETE RESTRICT, packaging TEXT NOT NULL DEFAULT '[]', gst_type VARCHAR(30) NOT NULL DEFAULT '', narration TEXT NOT NULL DEFAULT '', created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, cancelled INTEGER NOT NULL DEFAULT 0)",
      f"CREATE TABLE IF NOT EXISTS order_items (id {identity}, order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE, sr_no INTEGER NOT NULL, particulars VARCHAR(250) NOT NULL, piece_rate NUMERIC(12,2) NOT NULL DEFAULT 0, discount NUMERIC(12,2) NOT NULL DEFAULT 0)",
      f"CREATE TABLE IF NOT EXISTS order_item_sizes (id {identity}, order_item_id INTEGER NOT NULL REFERENCES order_items(id) ON DELETE CASCADE, size_code VARCHAR(10) NOT NULL, ordered_qty INTEGER NOT NULL CHECK(ordered_qty > 0), cancelled INTEGER NOT NULL DEFAULT 0, UNIQUE(order_item_id,size_code))",
      f"CREATE TABLE IF NOT EXISTS order_dispatches (id {identity}, order_size_id INTEGER NOT NULL REFERENCES order_item_sizes(id) ON DELETE RESTRICT, dispatched_size VARCHAR(10) NOT NULL, qty INTEGER NOT NULL CHECK(qty > 0), dispatch_date DATE NOT NULL, details TEXT NOT NULL DEFAULT '', invoice_number VARCHAR(150) NOT NULL DEFAULT '', created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)",
      f"CREATE TABLE IF NOT EXISTS order_size_cancellations (id {identity}, order_size_id INTEGER NOT NULL REFERENCES order_item_sizes(id) ON DELETE CASCADE, qty INTEGER NOT NULL CHECK(qty > 0), details TEXT NOT NULL DEFAULT '', cancelled_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)",
      f"CREATE TABLE IF NOT EXISTS sku_master (id {identity}, sku_number VARCHAR(250) NOT NULL UNIQUE, sale_rate NUMERIC(12,2) NOT NULL CHECK(sale_rate >= 0), created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)",
      f"CREATE TABLE IF NOT EXISTS users (id {identity}, username VARCHAR(100) NOT NULL UNIQUE, password_hash TEXT NOT NULL, role VARCHAR(20) NOT NULL DEFAULT 'staff', active INTEGER NOT NULL DEFAULT 1, agent_id INTEGER NULL REFERENCES agents(id) ON DELETE RESTRICT, created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    ]
    with engine.begin() as conn:
        for stmt in stmts: conn.execute(text(stmt))
        # Add columns if upgrading a prior PostgreSQL schema.
        if engine.dialect.name == "postgresql":
            conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS cancelled INTEGER NOT NULL DEFAULT 0"))
            conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS gst_type VARCHAR(30) NOT NULL DEFAULT ''"))
            conn.execute(text("ALTER TABLE orders ADD COLUMN IF NOT EXISTS delivery_date DATE NULL"))
            conn.execute(text("ALTER TABLE order_item_sizes ADD COLUMN IF NOT EXISTS cancelled INTEGER NOT NULL DEFAULT 0"))
            conn.execute(text("ALTER TABLE order_dispatches ADD COLUMN IF NOT EXISTS invoice_number VARCHAR(150) NOT NULL DEFAULT ''"))
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS agent_id INTEGER NULL REFERENCES agents(id) ON DELETE RESTRICT"))
        else:
            cols = {r[1] for r in conn.execute(text("PRAGMA table_info(orders)")).fetchall()}
            if "gst_type" not in cols:
                conn.execute(text("ALTER TABLE orders ADD COLUMN gst_type VARCHAR(30) NOT NULL DEFAULT ''"))
            if "delivery_date" not in cols:
                conn.execute(text("ALTER TABLE orders ADD COLUMN delivery_date DATE NULL"))
            user_cols = {r[1] for r in conn.execute(text("PRAGMA table_info(users)")).fetchall()}
            if "agent_id" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN agent_id INTEGER NULL REFERENCES agents(id) ON DELETE RESTRICT"))
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
        user = one("SELECT id,username,password_hash,role,active,agent_id FROM users WHERE LOWER(username)=LOWER(:u)", {"u":username.strip()})
        if user and int(user["active"]) == 1 and check_password_hash(user["password_hash"], password):
            st.session_state["authenticated_user"] = {"id":int(user["id"]),"username":user["username"],"role":user["role"],"agent_id":(int(user["agent_id"]) if user.get("agent_id") is not None else None)}
            st.rerun()
        else:
            st.error("Username અથવા password ખોટો છે, અથવા user disabled છે.")
    # Intentionally no Forgot Password option. Admin must reset staff passwords from Utilities.

def df_download(df, filename, label="CSV Download"):
    out = df.to_csv(index=False).encode("utf-8-sig")
    st.download_button(label, out, file_name=filename, mime="text/csv", use_container_width=False)

def order_pdf_bytes(order, items_df):
    buff = io.BytesIO()
    doc = SimpleDocTemplate(buff, pagesize=A4, rightMargin=10*mm, leftMargin=10*mm, topMargin=8*mm, bottomMargin=12*mm)
    styles = getSampleStyleSheet()
    small = ParagraphStyle("OrderInfoSmall", parent=styles["BodyText"], fontName="Helvetica", fontSize=8, leading=10, textColor=colors.HexColor("#222222"))
    title_style = ParagraphStyle("CompactOrderTitle", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=11, leading=13, alignment=TA_CENTER, spaceBefore=0, spaceAfter=5)
    label_style = ParagraphStyle("OrderInfoLabel", parent=small, fontName="Helvetica-Bold")
    # Requested header: centered title above both company logos.
    story = [Paragraph("ORDER FORM", title_style), Spacer(1, 2*mm)]
    app_dir = BASE
    trishiv_logo = app_dir / "static" / "trishiv_logo.jpg"
    shubhvastra_logo = app_dir / "static" / "shubhvastra_logo.png"
    logo_left = PDFImage(str(trishiv_logo), width=47*mm, height=35*mm, kind="proportional") if trishiv_logo.exists() else Paragraph("<b>TRISHIV ENTERPRISE LLP</b>", small)
    logo_right = PDFImage(str(shubhvastra_logo), width=49*mm, height=25*mm, kind="proportional") if shubhvastra_logo.exists() else Paragraph("<b>SHUBHVASTRA</b>", small)
    brand_row = Table([[logo_left, logo_right]], colWidths=[95*mm, 95*mm], hAlign="LEFT")
    brand_row.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),("ALIGN",(0,0),(0,0),"LEFT"),("ALIGN",(1,0),(1,0),"RIGHT"),
        ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),0),
        ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0)]))
    story.extend([brand_row, Spacer(1, 2*mm)])
    company_style = ParagraphStyle("CompanyContact", parent=small, fontSize=8, leading=10, textColor=colors.HexColor("#333333"), spaceAfter=1)
    story.extend([
        Paragraph("<b>Address:</b> 2005 New Sardar Traders Market (NSTM), Puna Kumbhariya Road, Surat 395010", company_style),
        Paragraph("<b>Phone Number:</b> 9537510757 (Bhavik), 9099444455 (Nimesh)", company_style),
        Spacer(1, 3*mm)
    ])
    def cell(label, value):
        val = str(value or "-").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return Paragraph(f"<b>{label}:</b> {val}", small)
    party_left = [
        cell("Party Name", order.get("party_name")),
        cell("Address", order.get("address")),
        cell("City", order.get("city")),
        cell("State", order.get("state")),
        cell("Phone Number", order.get("phone_number")),
        cell("GST Number", order.get("gst_number")),
    ]
    order_right = [
        cell("Order Number", order.get("order_no")),
        cell("Order Date", str(order.get("order_date",""))[:10]),
        cell("Delivery Date", str(order.get("delivery_date",""))[:10] if order.get("delivery_date") else "-"),
    ]
    first_data = [[party_left, order_right]]
    first_table = Table(first_data, colWidths=[95*mm,95*mm], hAlign="LEFT")
    first_table.setStyle(TableStyle([
        ("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#aab7c7")),
        ("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#f7f9fc")),
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),
        ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
    ]))
    transport_left = [cell("Transport Name", order.get("transport_details")), cell("Transport ID", order.get("transport_gst_number"))]
    gst_right = [cell("GST", order.get("gst_type")), cell("Packaging Details", order.get("packaging"))]
    second_table = Table([[transport_left, gst_right]], colWidths=[95*mm,95*mm], hAlign="LEFT")
    second_table.setStyle(TableStyle([
        ("GRID",(0,0),(-1,-1),0.4,colors.HexColor("#aab7c7")),
        ("BACKGROUND",(0,0),(-1,-1),colors.HexColor("#f7f9fc")),
        ("VALIGN",(0,0),(-1,-1),"TOP"),
        ("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),
        ("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),
    ]))
    story.extend([first_table, Spacer(1,2*mm), second_table, Spacer(1,5*mm), Paragraph("ITEM DETAILS", styles["Heading2"])])
    data=[["Sr.","Particulars / SKU","M","L","XL","XXL","Discount","WSP Rate","Qty","Amount"]]
    total_qty=0; total_amount=0; grouped={}
    for r in items_df.to_dict("records"):
        sr=r.get("Sr",""); sku=r.get("Particulars","")
        key=(sr,sku,r.get("Discount",""),r.get("WSP Rate",r.get("Piece Rate","")))
        if key not in grouped: grouped[key]={"M":0,"L":0,"XL":0,"XXL":0}
        size=str(r.get("Size","")).upper()
        if size in grouped[key]: grouped[key][size]+=int(r.get("Qty",0) or 0)
    for (sr,sku,disc,rate),sizes in grouped.items():
        qty=sum(sizes.values()); amount=max(0,float(rate or 0)-float(disc or 0))*qty
        total_qty+=qty; total_amount+=amount
        data.append([str(sr),str(sku),str(sizes["M"]),str(sizes["L"]),str(sizes["XL"]),str(sizes["XXL"]),str(disc),f"{float(rate or 0):,.2f}",str(qty),f"{amount:,.2f}"])
    data.append(["","TOTAL","","","","","","",str(total_qty),f"{total_amount:,.2f}"])
    tab=Table(data,repeatRows=1,colWidths=[9*mm,43*mm,11*mm,11*mm,12*mm,13*mm,17*mm,19*mm,13*mm,23*mm])
    tab.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#F7F4EA")),("TEXTCOLOR",(0,0),(-1,0),colors.black),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),7.5),("GRID",(0,0),(-1,-1),0.45,colors.HexColor("#9aa8b8")),("VALIGN",(0,0),(-1,-1),"MIDDLE"),("ALIGN",(2,1),(-1,-1),"RIGHT"),("BACKGROUND",(0,-1),(-1,-1),colors.HexColor("#eaf3fb")),("FONTNAME",(0,-1),(-1,-1),"Helvetica-Bold"),("LEFTPADDING",(0,0),(-1,-1),3),("RIGHTPADDING",(0,0),(-1,-1),3),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)]))
    story.extend([tab, Spacer(1,4*mm)])
    if order.get("narration"): story.append(Paragraph(f"<b>Additional Order Details:</b> {str(order['narration'])}",small))
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
        user = one("SELECT id,username,password_hash,role,active,agent_id FROM users WHERE LOWER(username)=LOWER(:u)", {"u":username.strip()})
        if user and int(user["active"]) == 1 and check_password_hash(user["password_hash"], password):
            st.session_state["user"] = {"id":int(user["id"]),"username":user["username"],"role":user["role"],"agent_id":(int(user["agent_id"]) if user.get("agent_id") is not None else None)}
            st.rerun()
        else: st.error("Username અથવા password ખોટો છે.")
    st.markdown("</div>", unsafe_allow_html=True)



def page_agent_portal(view="dashboard"):
    """Read-only portal strictly scoped to the logged-in agent's assigned parties."""
    user = current_user() or {}
    aid = user.get("agent_id")
    agent = one("SELECT id, agent_name FROM agents WHERE id=:id", {"id": int(aid)}) if aid is not None else None
    if not agent:
        st.error("આ Agent user સાથે Agent Master mapping મળતું નથી. Admin ને mapping સુધારવા કહો.")
        return
    aid = int(agent["id"])
    agent_name = str(agent["agent_name"])

    if view == "dashboard":
        st.title(f"My Dashboard — {agent_name}")
        parties = q('''SELECT p.party_name AS "Party Name",p.phone_number AS "Phone Number",
            p.city AS City,p.state AS State,p.address AS Address,p.gst_number AS "GST Number",
            p.transport_details AS "Transport Name",p.transport_gst_number AS "Transport ID"
            FROM parties p WHERE p.agent_id=:aid ORDER BY p.party_name''', {"aid": aid})
        summary = one("SELECT COUNT(*) AS parties FROM parties WHERE agent_id=:aid", {"aid": aid})
        pending = one('''SELECT COUNT(DISTINCT o.id) AS orders, COALESCE(SUM(CASE WHEN o.cancelled=0 AND s.cancelled=0 THEN CASE WHEN s.ordered_qty-COALESCE((SELECT SUM(d.qty) FROM order_dispatches d WHERE d.order_size_id=s.id),0)-COALESCE((SELECT SUM(c.qty) FROM order_size_cancellations c WHERE c.order_size_id=s.id),0)>0 THEN s.ordered_qty-COALESCE((SELECT SUM(d.qty) FROM order_dispatches d WHERE d.order_size_id=s.id),0)-COALESCE((SELECT SUM(c.qty) FROM order_size_cancellations c WHERE c.order_size_id=s.id),0) ELSE 0 END ELSE 0 END),0) AS qty
            FROM orders o JOIN parties p ON p.id=o.party_id JOIN order_items i ON i.order_id=o.id JOIN order_item_sizes s ON s.order_item_id=i.id
            WHERE p.agent_id=:aid AND o.cancelled=0 AND s.cancelled=0 AND s.ordered_qty>COALESCE((SELECT SUM(d.qty) FROM order_dispatches d WHERE d.order_size_id=s.id),0)+COALESCE((SELECT SUM(c.qty) FROM order_size_cancellations c WHERE c.order_size_id=s.id),0)''', {"aid": aid})
        dispatched = one('''SELECT COUNT(DISTINCT o.id) AS orders, COALESCE(SUM(d.qty),0) AS qty FROM order_dispatches d JOIN order_item_sizes s ON s.id=d.order_size_id JOIN order_items i ON i.id=s.order_item_id JOIN orders o ON o.id=i.order_id JOIN parties p ON p.id=o.party_id WHERE p.agent_id=:aid''', {"aid": aid})
        cancelled = one('''SELECT COUNT(DISTINCT o.id) AS orders, COALESCE(SUM(CASE WHEN o.cancelled=1 OR s.cancelled=1 THEN s.ordered_qty ELSE COALESCE(c.qty,0) END),0) AS qty FROM orders o JOIN parties p ON p.id=o.party_id LEFT JOIN order_items i ON i.order_id=o.id LEFT JOIN order_item_sizes s ON s.order_item_id=i.id LEFT JOIN order_size_cancellations c ON c.order_size_id=s.id WHERE p.agent_id=:aid AND (o.cancelled=1 OR s.cancelled=1 OR c.id IS NOT NULL)''', {"aid": aid})
        cols=st.columns(5)
        metrics=[("Total Parties",summary.get("parties",0)),("Pending Orders",pending.get("orders",0)),("Pending Pieces",pending.get("qty",0)),("Total Dispatched Orders",dispatched.get("orders",0)),("Total Cancle Orders",cancelled.get("orders",0))]
        for col,(label,value) in zip(cols,metrics):
            with col: st.markdown(f"<div class='metric-card'><div class='metric-label'>{label}</div><div class='metric-value'>{int(value or 0)}</div></div>", unsafe_allow_html=True)
        st.subheader("My Parties")
        st.caption("આ list માં ફક્ત તમારા Agent account સાથે જોડાયેલી Parties છે. આ પેજ read-only છે.")
        if parties.empty: st.info("આ Agent સાથે કોઈ Party જોડાયેલી નથી.")
        else: st.dataframe(parties.fillna(""), use_container_width=True, hide_index=True)
        return

    party_rows = q("SELECT id,party_name FROM parties WHERE agent_id=:aid ORDER BY party_name", {"aid": aid})
    if party_rows.empty:
        st.info("આ Agent સાથે કોઈ Party જોડાયેલી નથી.")
        return
    if view == "pending":
        title = "Total Pending Orders"
        st.title(f"{title} — {agent_name}")
        options = [(None, "All My Party Pending Orders")] + [(int(r.id), str(r.party_name)) for r in party_rows.itertuples()]
        selected_party = st.selectbox("Select Party", options, format_func=lambda x: x[1], key="agent_portal_pending_party")[0]
        qty_expr = "CASE WHEN s.ordered_qty-COALESCE((SELECT SUM(d.qty) FROM order_dispatches d WHERE d.order_size_id=s.id),0)-COALESCE((SELECT SUM(c.qty) FROM order_size_cancellations c WHERE c.order_size_id=s.id),0)>0 THEN s.ordered_qty-COALESCE((SELECT SUM(d.qty) FROM order_dispatches d WHERE d.order_size_id=s.id),0)-COALESCE((SELECT SUM(c.qty) FROM order_size_cancellations c WHERE c.order_size_id=s.id),0) ELSE 0 END"
        raw = q(f'''SELECT o.id AS order_id,o.order_no AS "Order No.",o.order_date AS "Order Date",p.id AS party_id,p.party_name AS "Party Name",i.particulars AS "SKU Code",s.size_code AS Size,{qty_expr} AS Qty,i.discount AS Discount,i.piece_rate AS Rate
            FROM orders o JOIN parties p ON p.id=o.party_id JOIN order_items i ON i.order_id=o.id JOIN order_item_sizes s ON s.order_item_id=i.id
            WHERE p.agent_id=:aid AND o.cancelled=0 AND s.cancelled=0 AND {qty_expr}>0 ORDER BY o.order_no DESC,p.party_name,i.particulars''', {"aid": aid})
        filename = "shubhvastra_agent_pending_orders.pdf"
    elif view == "dispatched":
        title = "Total Dispatched Orders"
        st.title(f"{title} — {agent_name}")
        options = [(None, "All My Party Dispatched Orders")] + [(int(r.id), str(r.party_name)) for r in party_rows.itertuples()]
        selected_party = st.selectbox("Select Party", options, format_func=lambda x: x[1], key="agent_portal_dispatched_party")[0]
        raw = q('''SELECT o.id AS order_id,o.order_no AS "Order No.",o.order_date AS "Order Date",p.id AS party_id,p.party_name AS "Party Name",COALESCE(a.agent_name,'') AS "Agent Name",i.particulars AS "SKU Code",d.dispatched_size AS Size,d.qty AS Qty,i.discount AS Discount,i.piece_rate AS Rate,d.invoice_number AS "Invoice Number",d.dispatch_date AS "Dispatched Date",d.details AS "Dispatched Details"
            FROM order_dispatches d JOIN order_item_sizes s ON s.id=d.order_size_id JOIN order_items i ON i.id=s.order_item_id JOIN orders o ON o.id=i.order_id JOIN parties p ON p.id=o.party_id LEFT JOIN agents a ON a.id=p.agent_id
            WHERE p.agent_id=:aid ORDER BY d.dispatch_date DESC,o.order_no DESC,p.party_name,i.particulars''', {"aid": aid})
        filename = "shubhvastra_agent_dispatched_orders.pdf"
    else:
        title = "Total Cancle Orders"
        st.title(f"{title} — {agent_name}")
        options = [(None, "All My Party Cancelled Orders")] + [(int(r.id), str(r.party_name)) for r in party_rows.itertuples()]
        selected_party = st.selectbox("Select Party", options, format_func=lambda x: x[1], key="agent_portal_cancelled_party")[0]
        raw = q('''SELECT o.id AS order_id,o.order_no AS "Order No.",o.order_date AS "Order Date",p.id AS party_id,p.party_name AS "Party Name",i.particulars AS "SKU Code",s.size_code AS Size,
            CASE WHEN o.cancelled=1 OR s.cancelled=1 THEN s.ordered_qty ELSE COALESCE(c.qty,0) END AS Qty,
            i.discount AS Discount,i.piece_rate AS Rate
            FROM orders o JOIN parties p ON p.id=o.party_id JOIN order_items i ON i.order_id=o.id JOIN order_item_sizes s ON s.order_item_id=i.id LEFT JOIN order_size_cancellations c ON c.order_size_id=s.id
            WHERE p.agent_id=:aid AND (o.cancelled=1 OR s.cancelled=1 OR c.id IS NOT NULL) ORDER BY o.order_no DESC,p.party_name,i.particulars''', {"aid": aid})
        filename = "shubhvastra_agent_cancelled_orders.pdf"

    if selected_party is not None:
        raw = raw[raw["party_id"] == int(selected_party)].copy()
    dispatch_view = view == "dispatched"
    base_columns = ["Order No.", "Order Date", "Party Name", "SKU Code", "M", "L", "XL", "XXL", "Qty", "Discount", "Amount"]
    dispatch_columns = ["Agent Name", "Order No.", "Order Date", "Party Name", "SKU Code", "M", "L", "XL", "XXL", "Qty", "Discount", "Amount", "Invoice Number", "Dispatched Date", "Dispatched Details"]
    if not raw.empty:
        for date_col in ["Order Date"] + (["Dispatched Date"] if dispatch_view else []):
            raw[date_col] = pd.to_datetime(raw[date_col], errors="coerce").dt.strftime("%d-%m-%Y").fillna("")
        raw["Qty"] = pd.to_numeric(raw["Qty"], errors="coerce").fillna(0)
        raw["Discount"] = pd.to_numeric(raw["Discount"], errors="coerce").fillna(0)
        raw["Rate"] = pd.to_numeric(raw["Rate"], errors="coerce").fillna(0)
        # Normalize historic size labels (e.g. 'M (38)', 'm', ' XL ') to the four report columns.
        def _size_key(value):
            v = str(value or "").strip().upper()
            for candidate in SIZES:
                if v == candidate or v.startswith(candidate + " ") or v.startswith(candidate + "(") or v.startswith(candidate + "-"):
                    return candidate
            return v
        raw["Size"] = raw["Size"].map(_size_key)
        if dispatch_view:
            idx = ["order_id", "Order No.", "Order Date", "party_id", "Party Name", "Agent Name", "SKU Code", "Discount", "Rate", "Invoice Number", "Dispatched Date", "Dispatched Details"]
        else:
            idx = ["order_id", "Order No.", "Order Date", "party_id", "Party Name", "SKU Code", "Discount", "Rate"]
        pivot = raw.pivot_table(index=idx, columns="Size", values="Qty", aggfunc="sum", fill_value=0, dropna=False).reset_index()
        pivot.columns.name = None
        for size in SIZES:
            if size not in pivot.columns: pivot[size] = 0
        pivot["Qty"] = pivot[SIZES].sum(axis=1)
        pivot["Amount"] = pivot["Qty"] * pivot["Rate"] - pivot["Discount"]
        if dispatch_view:
            df = pivot[["Agent Name", "Order No.", "Order Date", "Party Name", "SKU Code", "M", "L", "XL", "XXL", "Qty", "Discount", "Amount", "Invoice Number", "Dispatched Date", "Dispatched Details"]].copy()
        else:
            df = pivot[base_columns].copy()
        for c in ["M", "L", "XL", "XXL", "Qty"]: df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
        for c in ["Discount", "Amount"]: df[c] = df[c].map(lambda x: f"₹{float(x or 0):,.2f}")
        sort_cols = [c for c in (["Order No.", "Party Name", "SKU Code"] if not dispatch_view else ["Dispatched Date", "Order No.", "Party Name", "SKU Code"]) if c in df.columns]
        df = df.sort_values(sort_cols, ascending=[False] + [True] * (len(sort_cols)-1)).reset_index(drop=True)
    else:
        df = pd.DataFrame(columns=dispatch_columns if dispatch_view else base_columns)
    if df.empty: st.info("પસંદ કરેલી Party માટે records મળ્યા નથી.")
    else: st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button("Download PDF", pending_report_pdf_bytes(title, df), file_name=filename, mime="application/pdf", key=f"agent_portal_{view}_pdf", use_container_width=True)

def page_dashboard():
    st.title("Dashboard")
    stats = [
      ("Total Parties", "SELECT COUNT(*) n FROM parties"),
      ("Total Agents", "SELECT COUNT(*) n FROM agents"),
      ("Total SKU", "SELECT COUNT(*) n FROM sku_master"),
      ("Total Orders", "SELECT COUNT(*) n FROM orders"),
      ("Pending Orders", "SELECT COUNT(DISTINCT o.id) n FROM orders o JOIN order_items i ON i.order_id=o.id JOIN order_item_sizes s ON s.order_item_id=i.id WHERE o.cancelled=0 AND s.cancelled=0 AND s.ordered_qty>(SELECT COALESCE(SUM(d.qty),0) FROM order_dispatches d WHERE d.order_size_id=s.id)+(SELECT COALESCE(SUM(c.qty),0) FROM order_size_cancellations c WHERE c.order_size_id=s.id)")]
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
    st.caption("શરૂઆતમાં 5 rows દેખાશે. છેલ્લી row માં SKU અથવા quantity ભરશો એટલે આગળની row આપમેળે ઉમેરાશે (મહત્તમ 999).")
    sku_options=[""]+skus.sku_number.tolist()
    rows=[]
    header=st.columns([.5,3,1,1,1,1,1.2,1.3,1.2])
    for col,label in zip(header,["Sr.","Particulars / SKU","M","L","XL","XXL","Discount","WSP Rate (₹)","Qty"]): col.markdown(f"**{label}**")
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
        sku_rate=float(skus.loc[skus.sku_number==sku,"sale_rate"].iloc[0]) if not skus.empty and sku in skus.sku_number.tolist() else 0.0
        rate_default=float(old.piece_rate) if old is not None else sku_rate
        rkey=f"ord_rate_{ix}"
        if edit_id:
            if rkey not in st.session_state: st.session_state[rkey]=rate_default
            rate=float(st.session_state.get(rkey,rate_default) or 0)
        else:
            rate=sku_rate
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
        c[7].number_input("WSP Rate (₹)",min_value=0.0,value=float(rate),step=1.0,format="%.2f",key=f"ord_rate_visible_{ix}_{edit_id or 'new'}",disabled=True,label_visibility="collapsed")
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
    delivery_default=str(existing.get("delivery_date") or date.today().isoformat())[:10] if existing else date.today().isoformat()
    delivery_date=st.date_input("Delivery Date *", value=date.fromisoformat(delivery_default), key=f"ord_delivery_date_{edit_id or 'new'}", disabled=bool(edit_id))
    narration=st.text_area("Additional Order Details",value=str(existing["narration"] or "") if existing else "",key=f"ord_narration_{edit_id or 'new'}",disabled=bool(edit_id))
    buttons=st.columns(2)
    save=buttons[0].button("Save Order" if not edit_id else "Save Item Changes",type="primary",use_container_width=True)
    clean=buttons[1].button("Clean Form",use_container_width=True)
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
                    conn.execute(text("UPDATE orders SET order_date=:d,delivery_date=:dd,party_id=:p,packaging=:pack,gst_type=:gst,narration=:n WHERE id=:id"),{"d":od,"dd":delivery_date,"p":int(party_id),"pack":json.dumps(packaging),"gst":gst,"n":narration.strip(),"id":int(edit_id)})
                    conn.execute(text("DELETE FROM order_items WHERE order_id=:id"),{"id":int(edit_id)}); oid=int(edit_id)
                    order_no=int(existing["order_no"])
                else:
                    if engine.dialect.name == "postgresql": conn.execute(text("LOCK TABLE orders IN EXCLUSIVE MODE"))
                    order_no=int(conn.execute(text("SELECT COALESCE(MAX(order_no),1100)+1 FROM orders")).scalar_one())
                    oid=conn.execute(text("INSERT INTO orders(order_no,order_date,delivery_date,party_id,packaging,gst_type,narration) VALUES(:no,:d,:dd,:p,:pack,:gst,:n) RETURNING id"),{"no":order_no,"d":od,"dd":delivery_date,"p":int(party_id),"pack":json.dumps(packaging),"gst":gst,"n":narration.strip()}).scalar_one()
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
        oid=int(st.session_state["last_saved_order_id"])
        odf=q("SELECT o.*,p.party_name,p.phone_number,p.address,p.city,p.state,p.gst_number,p.transport_details,p.transport_gst_number,COALESCE(a.agent_name,'') agent_name FROM orders o JOIN parties p ON p.id=o.party_id LEFT JOIN agents a ON a.id=p.agent_id WHERE o.id=:id",{"id":oid}).iloc[0].to_dict()
        try: odf["packaging"]=", ".join(json.loads(odf.get("packaging") or "[]"))
        except Exception: pass
        it=q('SELECT i.sr_no AS Sr,i.particulars AS Particulars,i.piece_rate AS "WSP Rate",i.discount AS Discount,s.size_code AS Size,s.ordered_qty AS Qty,(SELECT COALESCE(SUM(d.qty),0) FROM order_dispatches d WHERE d.order_size_id=s.id) AS Dispatched FROM order_items i JOIN order_item_sizes s ON s.order_item_id=i.id WHERE i.order_id=:id ORDER BY i.sr_no,s.size_code',{"id":oid})
        pdf_data=order_pdf_bytes(odf,it)
        def finish_after_pdf_download():
            for k in list(st.session_state.keys()):
                if k.startswith(("ord_sku_","ord_rate_","ord_disc_","ord_qty_","ord_last_sku_","ord_pack_","ord_gst_","ord_narration_","ord_party_","ord_date_","ord_delivery_date_")):
                    st.session_state.pop(k,None)
            st.session_state["new_order_row_count"]=5
            st.session_state.pop("show_pdf_prompt",None)
            st.session_state.pop("last_saved_order_id",None)
            st.session_state.pop("edit_order_id",None)
            st.session_state.pop("confirm_clean_order_form",None)
            st.session_state["pending_page"]="New Order"
        st.download_button("Yes — Download PDF & Open New Order",pdf_data,file_name=f"shubhvastra_order_{odf['order_no']}.pdf",mime="application/pdf",type="primary",on_click=finish_after_pdf_download,use_container_width=True)
        if st.button("No — Continue Without PDF",use_container_width=True):
            finish_after_pdf_download()
            st.rerun()


def page_orders():
    st.title("Order List")
    search=st.text_input("Search Order Number / Party", key="order_history_search", placeholder="Type order number or party name…")
    # Streamlit reruns on each text change, so the results filter immediately without Enter.
    df=q("""SELECT o.id AS ID,o.order_no AS "Order Number",o.order_date AS "Order Date",
             p.party_name AS "Party Name",COALESCE(SUM(s.ordered_qty),0) AS Qty,
             COALESCE(SUM(s.ordered_qty * i.piece_rate),0) AS Amount,
             COALESCE(a.agent_name,'') AS "Agent Name",o.cancelled AS Cancelled
             FROM orders o JOIN parties p ON p.id=o.party_id LEFT JOIN agents a ON a.id=p.agent_id
             LEFT JOIN order_items i ON i.order_id=o.id LEFT JOIN order_item_sizes s ON s.order_item_id=i.id
             WHERE (:s='' OR CAST(o.order_no AS VARCHAR) LIKE :likeq OR LOWER(p.party_name) LIKE LOWER(:likeq))
             GROUP BY o.id,o.order_no,o.order_date,p.party_name,a.agent_name,o.cancelled
             ORDER BY o.order_no DESC LIMIT 1000""",{"s":search.strip(),"likeq":f"%{search.strip()}%"})
    if df.empty:
        st.info("કોઈ Order મળ્યો નથી." if search.strip() else "હજુ કોઈ Order નથી.")
        return
    st.caption(f"કુલ {len(df)} orders")
    h=st.columns([1.0,1.1,1.8,.65,1.0,1.25,.75,.95,.85])
    for c, label in zip(h,["Order No.","Order Date","Party Name","Qty","Amount","Agent Name","Edit","PDF","Delete"]):
        c.markdown(f"**{label}**")
    # Compact row layout with the requested fields and actions on the same row.
    for _, row in df.iterrows():
        oid=int(row["ID"])
        with st.container(border=True):
            cols=st.columns([1.0,1.1,1.8,.65,1.0,1.25,.75,.95,.85])
            cols[0].markdown(f"**#{int(row['Order Number'])}**")
            cols[1].write(str(row["Order Date"])[:10])
            cols[2].write(str(row["Party Name"]))
            cols[3].write(int(row["Qty"]))
            cols[4].write(f"₹{float(row['Amount'] or 0):,.2f}")
            cols[5].write(str(row["Agent Name"] or "—"))
            if str(current_user().get("role", "staff")).lower() in ("admin", "member"):
                if cols[6].button("Edit",key=f"history_edit_{oid}",use_container_width=True):
                    st.session_state["edit_order_id"]=oid; st.session_state["pending_page"]="New Order"; st.rerun()
            else:
                cols[6].write("—")
            pdfrow=one("SELECT o.*,p.party_name,p.phone_number,p.address,p.city,p.state,p.gst_number,p.transport_details,p.transport_gst_number,COALESCE(a.agent_name,'') agent_name FROM orders o JOIN parties p ON p.id=o.party_id LEFT JOIN agents a ON a.id=p.agent_id WHERE o.id=:id",{"id":oid})
            if pdfrow:
                pdfrow["packaging"] = ", ".join(json.loads(pdfrow.get("packaging") or "[]")) if str(pdfrow.get("packaging") or "").startswith("[") else str(pdfrow.get("packaging") or "")
                pdfitems=q('SELECT i.sr_no AS Sr,i.particulars AS Particulars,i.piece_rate AS "WSP Rate",i.discount AS Discount,s.size_code AS Size,s.ordered_qty AS Qty,(SELECT COALESCE(SUM(d.qty),0) FROM order_dispatches d WHERE d.order_size_id=s.id) AS Dispatched FROM order_items i JOIN order_item_sizes s ON s.order_item_id=i.id WHERE i.order_id=:id ORDER BY i.sr_no,s.size_code',{"id":oid})
                cols[7].download_button("PDF",order_pdf_bytes(pdfrow,pdfitems),file_name=f"shubhvastra_order_{pdfrow['order_no']}.pdf",mime="application/pdf",key=f"history_pdf_{oid}",use_container_width=True)
            if is_admin():
                if cols[8].button("Delete",key=f"history_delete_{oid}",use_container_width=True):
                    st.session_state["confirm_delete_order_id"]=oid
            else:
                cols[8].write("")
    # Delete is intentionally restricted to Admin; members and staff do not see this control.
    del_id=st.session_state.get("confirm_delete_order_id")
    if is_admin() and del_id and not df.empty and del_id in df.ID.astype(int).tolist():
        target=df.loc[df.ID.astype(int)==int(del_id)].iloc[0]
        st.warning(f"Order #{int(target['Order Number'])} delete કરવો છે? આ action પાછું ફેરવી શકાતું નથી.")
        yes,no=st.columns(2)
        if yes.button("Confirm Delete",type="primary",key="history_confirm_delete"):
            dispatched=one("SELECT d.id FROM order_dispatches d JOIN order_item_sizes s ON s.id=d.order_size_id JOIN order_items i ON i.id=s.order_item_id WHERE i.order_id=:id LIMIT 1",{"id":int(del_id)})
            if dispatched:
                st.error("Dispatch record ધરાવતો order delete કરી શકાતો નથી.")
            else:
                run("DELETE FROM order_items WHERE order_id=:id",{"id":int(del_id)})
                run("DELETE FROM orders WHERE id=:id",{"id":int(del_id)})
                st.session_state.pop("confirm_delete_order_id",None); st.success("Order delete થયો."); st.rerun()
        if no.button("Cancel",key="history_cancel_delete"):
            st.session_state.pop("confirm_delete_order_id",None); st.rerun()


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


def pending_report_pdf_bytes(title, df):
    buff = io.BytesIO()
    doc = SimpleDocTemplate(buff, pagesize=landscape(A4), rightMargin=8*mm, leftMargin=8*mm, topMargin=8*mm, bottomMargin=8*mm)
    styles = getSampleStyleSheet()
    story = [Paragraph(title, ParagraphStyle("PendingReportTitle", parent=styles["Title"], alignment=TA_CENTER, fontSize=14)), Spacer(1, 5*mm)]
    if df is None or df.empty:
        story.append(Paragraph("No pending orders found.", styles["BodyText"]))
    else:
        view = df.copy().fillna("")
        headers=list(map(str, view.columns))
        data = [headers] + view.astype(str).values.tolist()
        available=landscape(A4)[0]-16*mm
        weights=[]
        for h in headers:
            hl=h.lower()
            if 'party name' in hl: weights.append(1.55)
            elif 'agent name' in hl: weights.append(1.0)
            elif 'sku' in hl or 'description' in hl or 'details' in hl: weights.append(1.65 if 'details' in hl else 1.35)
            elif 'order date' in hl: weights.append(.95)
            elif 'order no' in hl: weights.append(.8)
            elif hl in ('m','l','xl','xxl'): weights.append(.45)
            else: weights.append(.8)
        total=sum(weights) or 1
        widths=[available*w/total for w in weights]
        wrapped=[]
        for ri,row in enumerate(data):
            wrapped.append([Paragraph(str(v).replace('&','&amp;').replace('<','&lt;').replace('>','&gt;'), ParagraphStyle(f'pdfcell{ri}', parent=styles['BodyText'], fontName='Helvetica-Bold' if ri==0 else 'Helvetica', fontSize=7, leading=8, textColor=colors.black, wordWrap='CJK')) for v in row])
        tbl = Table(wrapped, repeatRows=1, colWidths=widths)
        tbl.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor("#F7F4EA")),("TEXTCOLOR",(0,0),(-1,0),colors.black),("FONTNAME",(0,0),(-1,0),"Helvetica-Bold"),("FONTSIZE",(0,0),(-1,-1),7),("GRID",(0,0),(-1,-1),0.35,colors.HexColor("#B7C3D0")),("VALIGN",(0,0),(-1,-1),"TOP"),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#F2F5F9")])]))
        story.append(tbl)
    doc.build(story)
    return buff.getvalue()


def _pending_raw():
    df=q("""SELECT p.party_name AS "Party Name",COALESCE(a.agent_name,'—') AS "Agent Name",
      o.order_no AS "Order No.",o.order_date AS "Order Date",i.particulars AS "SKU Code",
      s.size_code AS "Size",s.ordered_qty AS "Order Qty",i.piece_rate AS Rate,
      i.discount AS "Discount",o.narration AS Details,
      COALESCE((SELECT SUM(d.qty) FROM order_dispatches d WHERE d.order_size_id=s.id),0) AS Dispatched,
      COALESCE((SELECT SUM(c.qty) FROM order_size_cancellations c WHERE c.order_size_id=s.id),0) AS "Cancelled Qty"
      FROM orders o JOIN parties p ON p.id=o.party_id LEFT JOIN agents a ON a.id=p.agent_id
      JOIN order_items i ON i.order_id=o.id JOIN order_item_sizes s ON s.order_item_id=i.id
      WHERE o.cancelled=0 AND s.cancelled=0 ORDER BY p.party_name,o.order_no DESC,i.sr_no,s.size_code""")
    if not df.empty:
        for col in ('Order Qty','Dispatched','Cancelled Qty','Rate','Discount'):
            df[col]=pd.to_numeric(df[col],errors='coerce').fillna(0)
        df['Pending']=(df['Order Qty']-df['Dispatched']-df['Cancelled Qty']).clip(lower=0).astype(int)
        df=df[df['Pending']>0].copy()
    return df


def _pending_report_rows(raw, show_party=False):
    columns=(['Party Name'] if show_party else [])+['Order No.','Order Date','SKU Code','M','L','XL','XXL','Qty','Discount','Amount','Details']
    if raw.empty: return pd.DataFrame(columns=columns)
    work=raw.copy()
    work['Size']=work['Size'].astype(str).str.upper().str.strip()
    work['Amount']=((work['Rate']*work['Pending'])*(1-work['Discount']/100)).round(2)
    work['Order Date']=pd.to_datetime(work['Order Date'],errors='coerce').dt.strftime('%d-%m-%Y').fillna('')
    idx=['Party Name','Order No.','Order Date','SKU Code','Discount','Details']
    grouped=work.groupby(idx,dropna=False,sort=False)
    rows=[]
    for key,g in grouped:
        row=dict(zip(idx,key))
        for sz in ('M','L','XL','XXL'):
            row[sz]=int(g.loc[g['Size']==sz,'Pending'].sum())
        other=g.loc[~g['Size'].isin(['M','L','XL','XXL'])]
        if not other.empty:
            row['Details']=str(row['Details'] or '')+' | '+', '.join(f"{r['Size']}: {int(r['Pending'])}" for _,r in other.iterrows())
        row['Qty']=int(g['Pending'].sum())
        row['Amount']=round(float(g['Amount'].sum()),2)
        rows.append(row)
    return pd.DataFrame(rows).reindex(columns=columns).sort_values(['Order No.'],ascending=False).reset_index(drop=True)


def page_dispatch(view='dispatch'):
    labels={'dispatch':'Pending to Dispatch Order','party':'Party Wise Pending Report',
            'agent':'Agent Wise Pending Report','sku':'SKU Wise Pending Report'}
    st.title(labels.get(view,'Pending to Dispatch Order'))
    if view=='dispatch':
        parties=q("""SELECT DISTINCT p.id,p.party_name,p.city,COALESCE(a.agent_name,'') agent_name
          FROM parties p LEFT JOIN agents a ON a.id=p.agent_id JOIN orders o ON o.party_id=p.id
          JOIN order_items i ON i.order_id=o.id JOIN order_item_sizes s ON s.order_item_id=i.id
          WHERE o.cancelled=0 AND s.cancelled=0 AND s.ordered_qty >
          COALESCE((SELECT SUM(d.qty) FROM order_dispatches d WHERE d.order_size_id=s.id),0)+
          COALESCE((SELECT SUM(c.qty) FROM order_size_cancellations c WHERE c.order_size_id=s.id),0)
          ORDER BY p.party_name""")
        if parties.empty:
            st.success('હાલ કોઈ Party નો Order dispatch માટે pending નથી.')
            return
        options=parties.id.astype(int).tolist()
        pid=st.selectbox('Select Party',options,index=None,placeholder='Select Party',format_func=lambda v: str(parties.loc[parties.id.astype(int)==v,'party_name'].iloc[0]),key='dispatch_party_select')
        if pid is None:
            st.info('Please select a Party to view its pending orders.')
            return
        party=parties.loc[parties.id.astype(int)==pid].iloc[0]
        st.caption(f"Agent: {party['agent_name'] or '—'} · City: {party['city'] or '—'}")
        df=q("""SELECT o.order_no AS "Order No.",o.order_date AS "Order Date",
           i.particulars AS "SKU Code",s.size_code AS "Size",s.id AS size_id,
           s.ordered_qty AS "Order Qty",o.narration AS Details,
           COALESCE((SELECT SUM(d.qty) FROM order_dispatches d WHERE d.order_size_id=s.id),0) AS dispatched,
           COALESCE((SELECT SUM(c.qty) FROM order_size_cancellations c WHERE c.order_size_id=s.id),0) AS cancelled_qty
           FROM orders o JOIN order_items i ON i.order_id=o.id JOIN order_item_sizes s ON s.order_item_id=i.id
           WHERE o.party_id=:pid AND o.cancelled=0 AND s.cancelled=0
           ORDER BY o.order_no DESC,i.sr_no,s.size_code""",{'pid':int(pid)})
        df['Pending Qty']=(df['Order Qty'].astype(int)-df['dispatched'].astype(int)-df['cancelled_qty'].astype(int)).clip(lower=0)
        df=df[df['Pending Qty']>0]
        header=st.columns([1.1,1,1.2,.55,.7,.8,.8,1.8,.7])
        for col,label in zip(header,['Order No.','Order Date','SKU Code','Size','Dispatch','Order Qty','Pending Qty','Details','Cancel']):
            col.markdown(f'**{label}**')
        selected=[]
        for _,r in df.iterrows():
            size_id=int(r['size_id']); pending=int(r['Pending Qty'])
            for piece in range(pending):
                token=f'{pid}_{size_id}_{piece}'
                dispatch_key=f'piece_dispatch_{token}'; cancel_key=f'piece_cancel_{token}'
                dispatch_checked=bool(st.session_state.get(dispatch_key,False))
                cancel_checked=bool(st.session_state.get(cancel_key,False))
                with st.container(border=True):
                    c=st.columns([1.1,1,1.2,.55,.7,.8,.8,1.8,.7],vertical_alignment='center')
                    c[0].write(str(r['Order No.']))
                    c[1].write(pd.to_datetime(r['Order Date']).strftime('%d-%m-%Y'))
                    c[2].write(str(r['SKU Code']))
                    c[3].write(str(r['Size']))
                    if not cancel_checked:
                        dispatch_checked=c[4].checkbox('Dispatch',key=dispatch_key,label_visibility='collapsed')
                    else: c[4].write('—')
                    c[5].write(int(r['Order Qty']))
                    c[6].write(1)
                    details=c[7].text_input('Details',value=str(r['Details'] or ''),key=f'piece_details_{token}',label_visibility='collapsed')
                    if not dispatch_checked:
                        cancel_checked=c[8].checkbox('Cancel',key=cancel_key,label_visibility='collapsed')
                    else: c[8].write('—')
                    if dispatch_checked or cancel_checked:
                        selected.append((size_id,str(r['Size']),details,'dispatch' if dispatch_checked else 'cancel',token))
        if st.button('Save to Dispatched',type='primary',use_container_width=True,key='save_to_dispatched'):
            if not selected:
                st.info('પહેલાં Dispatch અથવા Cancel checkbox પસંદ કરો.')
            else:
                try:
                    with engine.begin() as conn:
                        counts={}
                        for size_id,sz,details,action,token in selected:
                            counts[size_id]=counts.get(size_id,0)+1
                        for size_id,count in counts.items():
                            # PostgreSQL locks the size row during this transaction.
                            lock=' FOR UPDATE' if engine.dialect.name=='postgresql' else ''
                            record=conn.execute(text('SELECT ordered_qty,cancelled FROM order_item_sizes WHERE id=:id'+lock),{'id':size_id}).mappings().first()
                            if not record or int(record['cancelled']): raise ValueError('આ Order size હવે pending નથી.')
                            sent=conn.execute(text('SELECT COALESCE(SUM(qty),0) FROM order_dispatches WHERE order_size_id=:id'),{'id':size_id}).scalar()
                            cancelled=conn.execute(text('SELECT COALESCE(SUM(qty),0) FROM order_size_cancellations WHERE order_size_id=:id'),{'id':size_id}).scalar()
                            if count>int(record['ordered_qty'])-int(sent)-int(cancelled):
                                raise ValueError('Pending Qty બદલાઈ ગઈ છે. Refresh કરીને ફરીથી પસંદ કરો.')
                        for size_id,sz,details,action,token in selected:
                            if action=='dispatch':
                                conn.execute(text("INSERT INTO order_dispatches(order_size_id,dispatched_size,qty,dispatch_date,details,invoice_number) VALUES(:id,:size,1,:date,:details,'')"),{'id':size_id,'size':sz,'date':date.today(),'details':details})
                            else:
                                conn.execute(text('INSERT INTO order_size_cancellations(order_size_id,qty,details) VALUES(:id,1,:details)'),{'id':size_id,'details':details})
                    for key in list(st.session_state):
                        if key.startswith(('piece_dispatch_','piece_cancel_','piece_details_')): st.session_state.pop(key,None)
                    st.session_state.pop('dispatch_party_select',None)
                    st.success('Selected pieces Dispatched / Cancelled માં save થયા.')
                    st.rerun()
                except Exception as exc:
                    st.error(f'Save ન થયું: {exc}')
        return

    raw=_pending_raw()
    if view=='party':
        parties=q('SELECT party_name FROM parties ORDER BY party_name')
        options=['All Parties']+parties['party_name'].dropna().unique().tolist()
        chosen=st.selectbox('Select Party',options,key='party_pending_report_filter')
        if chosen!='All Parties': raw=raw[raw['Party Name']==chosen]
        show_party=chosen=='All Parties'
        filename='shubhvastra_party_pending_report.pdf'
    elif view=='agent':
        agents=q('SELECT agent_name FROM agents ORDER BY agent_name')
        agent_options=agents['agent_name'].dropna().unique().tolist() if not agents.empty else []
        if not agent_options:
            st.info('Agent Master માં કોઈ Agent ઉપલબ્ધ નથી.')
            return
        chosen_agent=st.selectbox('Select Agent',agent_options,key='agent_pending_report_filter')
        raw=raw[raw['Agent Name']==chosen_agent].copy()
        pending_parties=sorted(raw['Party Name'].dropna().astype(str).unique().tolist()) if not raw.empty else []
        party_options=[f'All {chosen_agent} Parties']+pending_parties
        chosen_party=st.selectbox('Select Party',party_options,key='agent_pending_party_filter')
        if chosen_party!=f'All {chosen_agent} Parties':
            raw=raw[raw['Party Name']==chosen_party]
        show_party=True
        filename='shubhvastra_agent_pending_report.pdf'
    else:
        skus=sorted(raw['SKU Code'].dropna().astype(str).unique().tolist()) if not raw.empty else []
        chosen=st.multiselect('Select Pending SKU Codes',skus,default=[],placeholder='All Pending SKUs',key='sku_pending_report_filter')
        if chosen: raw=raw[raw['SKU Code'].astype(str).isin(chosen)]
        show_party=True
        filename='shubhvastra_sku_pending_report.pdf'
    shown=_pending_report_rows(raw,show_party=show_party)
    if shown.empty:
        st.info('No pending orders found for the selected filter.')
    else:
        st.dataframe(shown,use_container_width=True,hide_index=True)
        st.caption(f'Total pending pieces: {int(shown["Qty"].sum())} · Amount: ₹{shown["Amount"].sum():,.2f}')
        st.download_button('Download PDF',pending_report_pdf_bytes(labels[view],shown),file_name=filename,mime='application/pdf',key=f'{view}_pending_pdf',use_container_width=True)


def page_dispatched_details(view='party'):
    """Show saved dispatch transactions by party or agent, with PDF export."""
    title = 'Party Wise Dispatched History' if view == 'party' else 'Agent Wise Dispatched History'
    st.title(title)
    base = q("""SELECT p.party_name AS "Party Name",COALESCE(a.agent_name,'—') AS "Agent Name",
        o.order_no AS "Order No.",o.order_date AS "Order Date",d.dispatch_date AS "Dispatch Date",
        i.particulars AS "SKU Code",d.dispatched_size AS "Size",d.qty AS "Dispatched Qty",
        d.invoice_number AS "Invoice No.",d.details AS "Dispatch Details"
        FROM order_dispatches d
        JOIN order_item_sizes s ON s.id=d.order_size_id
        JOIN order_items i ON i.id=s.order_item_id
        JOIN orders o ON o.id=i.order_id
        JOIN parties p ON p.id=o.party_id
        LEFT JOIN agents a ON a.id=p.agent_id
        ORDER BY d.dispatch_date DESC,o.order_no DESC,p.party_name,i.particulars,d.dispatched_size""")
    if base.empty:
        st.info('હજુ સુધી કોઈ dispatched history ઉપલબ્ધ નથી.')
        return
    for col in ('Order Date','Dispatch Date'):
        base[col] = pd.to_datetime(base[col], errors='coerce').dt.strftime('%d-%m-%Y').fillna('')
    if view == 'party':
        parties = sorted(base['Party Name'].dropna().astype(str).unique().tolist())
        chosen = st.selectbox('Select Party', parties, key='dispatched_history_party')
        shown = base[base['Party Name'] == chosen].copy()
        filename = 'shubhvastra_party_dispatched_history.pdf'
    else:
        agents = sorted(base.loc[base['Agent Name'] != '—', 'Agent Name'].dropna().astype(str).unique().tolist())
        if not agents:
            st.info('Dispatched history માટે કોઈ Agent જોડાયેલો નથી.')
            return
        chosen = st.selectbox('Select Agent', agents, key='dispatched_history_agent')
        shown = base[base['Agent Name'] == chosen].copy()
        filename = 'shubhvastra_agent_dispatched_history.pdf'
        party_options = ['All Parties'] + sorted(shown['Party Name'].dropna().astype(str).unique().tolist())
        chosen_party = st.selectbox('Select Party', party_options, key='dispatched_history_agent_party')
        if chosen_party != 'All Parties':
            shown = shown[shown['Party Name'] == chosen_party].copy()
            filename = 'shubhvastra_agent_party_dispatched_history.pdf'
    st.dataframe(shown, use_container_width=True, hide_index=True)
    st.caption(f"Dispatched pieces: {int(pd.to_numeric(shown['Dispatched Qty'], errors='coerce').fillna(0).sum())}")
    if shown.empty:
        st.info('પસંદ કરેલા filter માટે dispatched history મળી નથી.')
    st.download_button('Download PDF', pending_report_pdf_bytes(title, shown), file_name=filename,
                       mime='application/pdf', key=f'{view}_dispatched_history_pdf', use_container_width=True)


def page_cancelled_orders():
    st.title('Cancelled Orders')
    cancelled=q("""SELECT p.party_name AS \"Party Name\",COALESCE(a.agent_name,'—') AS \"Agent Name\",o.order_no AS \"Order No.\",o.order_date AS \"Order Date\",i.particulars AS \"SKU Code\",s.size_code AS Size,s.ordered_qty AS \"Order Qty\",s.cancelled AS Cancelled FROM orders o JOIN parties p ON p.id=o.party_id LEFT JOIN agents a ON a.id=p.agent_id JOIN order_items i ON i.order_id=o.id JOIN order_item_sizes s ON s.order_item_id=i.id WHERE o.cancelled=1 OR s.cancelled=1 OR EXISTS(SELECT 1 FROM order_size_cancellations c WHERE c.order_size_id=s.id) ORDER BY o.order_no DESC""")
    if cancelled.empty: st.info('Cancelled orders નથી.')
    else: st.dataframe(cancelled,use_container_width=True,hide_index=True)
    st.download_button('Download Cancelled PDF',pending_report_pdf_bytes('Cancelled Orders',cancelled),file_name='shubhvastra_cancelled_orders.pdf',mime='application/pdf',key='utilities_cancelled_pdf')

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
    st.caption("Agent user ફક્ત તેની સાથે જોડાયેલી Parties અને તેમના pending, dispatched તથા cancelled reports જોઈ શકશે. Agent કોઈ record edit કરી શકશે નહીં.")
    agent_df = q("SELECT id, agent_name FROM agents ORDER BY agent_name")
    agent_ids = agent_df["id"].astype(int).tolist() if not agent_df.empty else []
    agent_names = agent_df["agent_name"].astype(str).tolist() if not agent_df.empty else []
    with st.expander("Create New User", expanded=True):
        with st.form("new_user"):
            role = st.selectbox("Role", ["admin", "member", "staff", "agent"], format_func=lambda x: x.title(), key="create_role")
            agent_id = None
            if role == "agent":
                if not agent_ids:
                    st.warning("Agent role user બનાવવા પહેલાં Agent Master માં Agent ઉમેરો.")
                selected_agent = st.selectbox("Select Agent", agent_ids, format_func=lambda x: agent_df.loc[agent_df.id.astype(int)==x, "agent_name"].iloc[0], key="create_agent_id") if agent_ids else None
                agent_id = int(selected_agent) if selected_agent is not None else None
                username = st.text_input("Username (Agent Name)", value=(agent_df.loc[agent_df.id.astype(int)==agent_id, "agent_name"].iloc[0] if agent_id is not None else ""), disabled=True, key="create_agent_username")
            else:
                username = st.text_input("Username", key="create_username")
            password = st.text_input("Password (minimum 10 characters)", type="password", key="create_password")
            if st.form_submit_button("Create User", type="primary"):
                if role == "agent" and agent_id is None:
                    st.error("Agent પસંદ કરો.")
                elif not username.strip() or len(password) < 10:
                    st.error("Username અને ઓછામાં ઓછો 10-character password જરૂરી છે.")
                elif one("SELECT id FROM users WHERE LOWER(username)=LOWER(:u)", {"u":username.strip()}):
                    st.error("આ username પહેલેથી છે. આ Agent માટે બીજું account હોય તો પહેલું account બદલો.")
                elif role == "agent" and one("SELECT id FROM users WHERE role='agent' AND agent_id=:aid AND active=1", {"aid":agent_id}):
                    st.error("આ Agent માટે પહેલેથી active login user છે.")
                else:
                    run("INSERT INTO users(username,password_hash,role,active,agent_id) VALUES(:u,:p,:r,1,:aid)", {"u":username.strip(), "p":generate_password_hash(password), "r":role, "aid":agent_id})
                    st.success("User create થયો.")
                    st.rerun()
    df=q('SELECT id AS ID,username AS Username,role AS Role,active AS Active,created_at AS "Created At" FROM users ORDER BY username')
    st.subheader("Existing Users")
    if not df.empty:
        view_df=df.copy()
        agent_map={int(r.id):str(r.agent_name) for r in agent_df.itertuples()} if not agent_df.empty else {}
        details=q("SELECT id,agent_id FROM users")
        detail_map={int(r.id):agent_map.get(int(r.agent_id), "") for r in details.itertuples() if pd.notna(r.agent_id)}
        view_df["Agent"] = view_df["ID"].map(detail_map).fillna("")
    else:
        view_df=df
    st.dataframe(view_df.drop(columns=["ID"], errors="ignore"),use_container_width=True,hide_index=True)
    if not df.empty:
        uid=st.selectbox("Select User",df.ID.tolist(),format_func=lambda x:df.loc[df.ID==x,"Username"].iloc[0],key="admin_selected_user")
        selected=one("SELECT id,username,role,active,agent_id FROM users WHERE id=:id",{"id":int(uid)})
        with st.form("edit_user_credentials"):
            st.write(f"Selected user: **{selected['username']}**")
            new_role=st.selectbox("Role",["staff","member","admin","agent"],index=["staff","member","admin","agent"].index(selected["role"]) if selected["role"] in ["staff","member","admin","agent"] else 0)
            new_agent_id = None
            if new_role == "agent":
                if agent_ids:
                    current_index=agent_ids.index(int(selected["agent_id"])) if selected.get("agent_id") is not None and int(selected["agent_id"]) in agent_ids else 0
                    new_agent_id=st.selectbox("Select Agent",agent_ids,index=current_index,format_func=lambda x:agent_df.loc[agent_df.id.astype(int)==x,"agent_name"].iloc[0],key="edit_agent_id")
                    new_username=str(agent_df.loc[agent_df.id.astype(int)==int(new_agent_id),"agent_name"].iloc[0])
                    st.text_input("Username (Agent Name)",value=new_username,disabled=True)
                else:
                    st.warning("Agent Master માં કોઈ Agent નથી.")
                    new_username=selected["username"]
            else:
                new_username=st.text_input("Change Username",value=selected["username"])
            new_password=st.text_input("Set New Password (leave blank to keep current)",type="password")
            active=st.checkbox("User can login",value=bool(selected["active"]))
            save=st.form_submit_button("Save User Settings",type="primary")
        if save:
            if not new_username.strip():
                st.error("Username ખાલી ન રાખો.")
            elif new_role == "agent" and new_agent_id is None:
                st.error("Agent પસંદ કરો.")
            elif len(new_password)>0 and len(new_password)<10:
                st.error("નવો password ઓછામાં ઓછો 10 characters નો હોવો જોઈએ.")
            elif one("SELECT id FROM users WHERE LOWER(username)=LOWER(:u) AND id<>:id",{"u":new_username.strip(),"id":int(uid)}):
                st.error("આ username બીજા user દ્વારા વપરાય છે.")
            elif new_role == "agent" and one("SELECT id FROM users WHERE role='agent' AND agent_id=:aid AND id<>:id AND active=1",{"aid":int(new_agent_id),"id":int(uid)}):
                st.error("આ Agent માટે બીજું active account પહેલેથી છે.")
            elif int(uid)==int(current_user()["id"]) and not active:
                st.error("તમારા પોતાના logged-in admin account ને disable કરી શકતા નથી.")
            else:
                run("UPDATE users SET username=:u,role=:r,active=:a,agent_id=:aid WHERE id=:id",{"u":new_username.strip(),"r":new_role,"a":1 if active else 0,"aid":int(new_agent_id) if new_role=="agent" and new_agent_id is not None else None,"id":int(uid)})
                if new_password:
                    run("UPDATE users SET password_hash=:p WHERE id=:id",{"p":generate_password_hash(new_password),"id":int(uid)})
                if int(uid)==int(current_user()["id"]):
                    st.session_state["authenticated_user"].update({"username":new_username.strip(),"role":new_role,"agent_id":int(new_agent_id) if new_role=="agent" and new_agent_id is not None else None})
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
    menu=["Dashboard","Party Master","Agent Master","New Order","Pending to Dispatched","Dispatched Details","Order Reports","Utilities"]
elif role_name == "member":
    menu=["Dashboard","Party Master","Agent Master","New Order","Pending to Dispatched","Dispatched Details","Order Reports","Utilities"]
elif role_name == "agent":
    menu=["My Dashboard","My Party Pending Orders","Total Dispatched Orders","Total Cancle Orders"]
else:
    menu=["Dashboard","Pending to Dispatched","Dispatched Details","Order Reports","Utilities"]
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
    # The navigation options depend on the logged-in role. A previous session may
    # leave a page name such as "Dashboard" selected, which is not valid for Agent.
    default=st.session_state.get("page", menu[0])
    if default not in menu:
        default=menu[0]
    # Keep the radio widget's stored value aligned with the role-specific menu.
    if st.session_state.get("main_navigation") not in menu:
        st.session_state["main_navigation"] = default
    page=st.radio("Navigation",menu,index=menu.index(default),key="main_navigation")
    if page == "Pending to Dispatched":
        dispatch_options = ["Pending to Dispatch Order", "Party Wise Pending Report", "Agent Wise Pending Report", "SKU Wise Pending Report"]
        dispatch_choice = st.selectbox("Pending to Dispatched", dispatch_options, key="pending_dispatch_submenu")
    else:
        dispatch_choice = ""
    if page == "Utilities":
        util_options = ["Order History / Order List", "Cancelled Orders"]
        if role_name in ("admin", "member"):
            util_options.insert(0, "Item Master")
        if is_admin():
            util_options.append("Admin Panel / Backup & Restore")
        util_choice = st.selectbox("Utilities", util_options, key="utilities_submenu")
    elif page == "Dispatched Details":
        dispatched_options = ["Party Wise Dispatched History", "Agent Wise Dispatched History"]
        dispatched_choice = st.selectbox("Dispatched Details", dispatched_options, key="dispatched_details_submenu")
    else:
        util_choice = ""
        dispatched_choice = ""
    st.session_state["page"]=page
if role_name == "agent":
    if page == "My Dashboard": page_agent_portal("dashboard")
    elif page == "My Party Pending Orders": page_agent_portal("pending")
    elif page == "Total Dispatched Orders": page_agent_portal("dispatched")
    elif page == "Total Cancle Orders": page_agent_portal("cancelled")
elif page=="Dashboard": page_dashboard()
elif page=="Party Master": page_parties()
elif page=="Agent Master": page_agents()
elif page=="New Order":
    if str(user.get("role", "staff")).lower() == "staff": st.error("આ વિભાગ માટે પરવાનગી નથી.")
    else: page_order_form(st.session_state.get("edit_order_id"))
elif page=="Utilities" and util_choice == "Item Master" and role_name in ("admin", "member"): page_sku()
elif page=="Utilities" and util_choice == "Order History / Order List": page_orders()
elif page=="Utilities" and util_choice == "Cancelled Orders": page_cancelled_orders()
elif page=="Dispatched Details": page_dispatched_details("party" if dispatched_choice == "Party Wise Dispatched History" else "agent")
elif page=="Utilities" and util_choice == "Admin Panel / Backup & Restore" and is_admin(): page_settings()
elif page=="Pending to Dispatched":
    page_dispatch({"Pending to Dispatch Order":"dispatch", "Party Wise Pending Report":"party", "Agent Wise Pending Report":"agent", "SKU Wise Pending Report":"sku"}.get(dispatch_choice,"dispatch"))
elif page=="Order Reports": page_reports()


st.markdown(f"<div style='text-align:center;color:#8b98a9;font-size:11px;padding:20px'>SHUBHVASTRA · Secure Login · {user['role'].title()}</div>",unsafe_allow_html=True)
