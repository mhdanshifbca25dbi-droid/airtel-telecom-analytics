import os
import gzip
import shutil
import base64
import sqlite3
import threading
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ==============================================================================
# 1. STREAMLIT CONFIGURATION & ASSETS RESOLUTION
# ==============================================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))

def resolve_asset_path(filename: str) -> str:
    """
    Resolves asset paths using BASE_DIR and relative paths reliably
    across Windows local development and Streamlit Community Cloud (Linux).
    """
    candidates = [
        os.path.join(BASE_DIR, "assets", filename),
        os.path.join(PROJECT_ROOT, "dashboard", "assets", filename),
        os.path.join("dashboard", "assets", filename),
        os.path.join("assets", filename)
    ]
    for p in candidates:
        if os.path.exists(p):
            return os.path.abspath(p)
    return os.path.abspath(os.path.join(BASE_DIR, "assets", filename))

LOGO_IMAGE_PATH = resolve_asset_path("airtel_logo.png")
BG_IMAGE_PATH = resolve_asset_path("airtel_cyber_bg.jpg")
if not os.path.exists(BG_IMAGE_PATH):
    BG_IMAGE_PATH = resolve_asset_path("telecom_bg.png")
CSS_PATH = resolve_asset_path("style.css")

st.set_page_config(
    page_title="Airtel Telecom Analytics | Retention Intelligence",
    page_icon=LOGO_IMAGE_PATH if os.path.exists(LOGO_IMAGE_PATH) else "📶",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Core Airtel Color Palette
AIRTEL_RED = "#ED1C24"
AIRTEL_RED_DARK = "#C40000"
AIRTEL_RED_SOFT = "#FFF1F2"
NAVY_DARK = "#0B132B"
NAVY_SURFACE = "#14213D"
NAVY_LIGHT = "#1E293B"
SLATE_GRAY = "#CBD5E1"
LIGHT_BG = "#F8FAFC"
BORDER_GRAY = "rgba(255, 255, 255, 0.20)"
NATIONAL_BENCHMARK = 23.75  # Audited National Churn Benchmark (5,226 / 22,000 = 23.75%)

# Base64 encode the user's official Airtel logo
logo_b64 = ""
if os.path.exists(LOGO_IMAGE_PATH):
    try:
        with open(LOGO_IMAGE_PATH, "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        logo_b64 = ""

# Base64 encode the telecom background image
bg_b64 = ""
if os.path.exists(BG_IMAGE_PATH):
    try:
        with open(BG_IMAGE_PATH, "rb") as f:
            bg_b64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        bg_b64 = ""

# Inject Custom CSS and Dynamic Background Image
css_content = ""
if os.path.exists(CSS_PATH):
    try:
        with open(CSS_PATH, "r", encoding="utf-8") as f:
            css_content = f.read()
    except Exception:
        css_content = ""

bg_injection_css = ""
if bg_b64:
    bg_injection_css = f"""
    .stApp {{
        background: transparent !important;
        position: relative !important;
    }}
    .stApp::before {{
        content: '' !important;
        position: fixed !important;
        top: -6% !important;
        left: -6% !important;
        width: 112% !important;
        height: 112% !important;
        z-index: -2 !important;
        background-image: url("data:image/jpeg;base64,{bg_b64}") !important;
        background-position: center center !important;
        background-size: cover !important;
        background-repeat: no-repeat !important;
        animation: cyberBgMove 24s ease-in-out infinite alternate, cyberCircuitGlow 6s ease-in-out infinite alternate !important;
        pointer-events: none !important;
        transform-origin: center center !important;
        will-change: transform, filter !important;
        opacity: 0.46 !important;
        filter: brightness(0.72) contrast(1.22) saturate(1.30) !important;
    }}
    .stApp::after {{
        content: '' !important;
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        width: 100% !important;
        height: 100% !important;
        z-index: -1 !important;
        background: radial-gradient(circle at 50% 25%, rgba(11, 19, 43, 0.62) 0%, rgba(15, 7, 20, 0.76) 55%, rgba(8, 12, 24, 0.88) 100%) !important;
        pointer-events: none !important;
        animation: ambientCyberPulse 8s ease-in-out infinite alternate !important;
    }}
    [data-testid="stSidebar"] {{
        background: linear-gradient(180deg, rgba(8, 14, 32, 0.96) 0%, rgba(15, 7, 10, 0.96) 50%, rgba(8, 14, 32, 0.98) 100%),
                    url("data:image/jpeg;base64,{bg_b64}") center center / cover no-repeat fixed !important;
        border-right: 2px solid rgba(237, 28, 36, 0.45) !important;
        box-shadow: 6px 0 25px rgba(237, 28, 36, 0.25) !important;
    }}
    [data-testid="stSidebar"] > div {{
        background: transparent !important;
    }}
    """

st.markdown(f"<style>{css_content}\n{bg_injection_css}</style>", unsafe_allow_html=True)

# ==============================================================================
# 2. DATABASE RESOLUTION & REUSABLE SQL HELPER
# ==============================================================================
_db_lock = threading.Lock()

def is_valid_database(path: str) -> bool:
    """
    Verifies that an uncompressed SQLite file exists, has full size (~118 MB),
    and passes integrity check without corruption.
    """
    if not os.path.exists(path):
        return False
    # Full database is ~117.96 MB (123,686,912 bytes). Must be >= 110 MB.
    try:
        if os.path.getsize(path) < 110 * 1024 * 1024:
            return False
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5.0)
        cursor = conn.cursor()
        cursor.execute("PRAGMA quick_check;")
        res = cursor.fetchone()
        if not res or res[0] != "ok":
            conn.close()
            return False
        cursor.execute("SELECT COUNT(*) FROM customer_features;")
        count = cursor.fetchone()[0]
        conn.close()
        return count == 22000
    except Exception:
        return False

def get_db_path() -> str:
    """
    Resolves the SQLite database path using BASE_DIR and relative paths.
    Automatically and atomically extracts 'airtel.db.gz' into 'data/raw/airtel.db'
    when the uncompressed database is missing or malformed (e.g. on Streamlit Cloud).
    Preserves valid existing local databases without modification.
    """
    candidates = [
        os.path.join(BASE_DIR, "..", "data", "raw", "airtel.db"),
        os.path.join(PROJECT_ROOT, "data", "raw", "airtel.db"),
        os.path.join("data", "raw", "airtel.db")
    ]
    
    # 1. If uncompressed database already exists and is 100% valid, use it directly
    for p in candidates:
        if is_valid_database(p):
            return os.path.abspath(p)
            
    # Target extraction destination
    target_db_path = os.path.abspath(candidates[0])
    target_dir = os.path.dirname(target_db_path)
    os.makedirs(target_dir, exist_ok=True)
    
    # 2. Check candidate paths for compressed archive
    gz_candidates = [
        os.path.join(BASE_DIR, "..", "data", "raw", "airtel.db.gz"),
        os.path.join(PROJECT_ROOT, "data", "raw", "airtel.db.gz"),
        os.path.join("data", "raw", "airtel.db.gz"),
        target_db_path + ".gz"
    ]
    gz_path = None
    for gz in gz_candidates:
        if os.path.exists(gz) and os.path.getsize(gz) > 10 * 1024 * 1024:
            gz_path = os.path.abspath(gz)
            break
            
    # Show clear error if archive is missing
    if not gz_path:
        st.error(
            f"❌ Database archive not found in '{target_dir}'. "
            "Please ensure 'data/raw/airtel.db.gz' is committed and pushed to your GitHub repository."
        )
        return target_db_path

    # 3. Thread-safe atomic extraction with integrity verification
    with _db_lock:
        # Double-check after acquiring lock in case another thread just completed extraction
        if is_valid_database(target_db_path):
            return target_db_path

        # If an incomplete or corrupt target file exists, remove it cleanly
        if os.path.exists(target_db_path):
            try:
                os.remove(target_db_path)
            except Exception:
                pass

        tmp_path = target_db_path + f".tmp_{os.getpid()}"
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

        try:
            with st.spinner("📦 Initializing enterprise database archive on Streamlit Cloud (extracting ~118 MB)..."):
                with gzip.open(gz_path, "rb") as f_in:
                    with open(tmp_path, "wb") as f_out:
                        shutil.copyfileobj(f_in, f_out, length=1024 * 1024)

            # Validate the extracted temp file before making it live
            if not is_valid_database(tmp_path):
                raise RuntimeError("Extracted database failed integrity verification.")

            # Atomic replacement: rename verified tmp file to live database file
            os.replace(tmp_path, target_db_path)

            # Clear any previously cached Streamlit errors or empty results
            try:
                st.cache_data.clear()
            except Exception:
                pass

        except Exception as e:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            st.error(f"❌ Failed to extract database from '{gz_path}': {e}")
            return target_db_path
        
    return target_db_path

DB_PATH = get_db_path()

def get_db_connection():
    """Creates a single managed connection to SQLite with timeout and thread safety."""
    return sqlite3.connect(DB_PATH, timeout=30.0, check_same_thread=False)

@st.cache_data(ttl=600, show_spinner=False)
def q(sql: str, params: tuple = ()) -> pd.DataFrame:
    """
    Executes a parameterized SQL query on the SQLite database.
    Uses the verified extracted database path, safely manages connection lifecycle, and avoids duplicate connections.
    """
    if not os.path.exists(DB_PATH):
        return pd.DataFrame()
    conn = get_db_connection()
    try:
        df = pd.read_sql_query(sql, conn, params=params)
    except Exception as e:
        st.error(f"SQL execution error: {e}")
        df = pd.DataFrame()
    finally:
        conn.close()
    return df

@st.cache_data(ttl=3600, show_spinner=False)
def get_filter_options():
    regions_df = q("SELECT DISTINCT region FROM customer_features WHERE region IS NOT NULL AND region != '' ORDER BY region")
    regions = ['All'] + (regions_df['region'].tolist() if not regions_df.empty else ['East', 'North', 'South', 'West'])
    
    conns_df = q("SELECT DISTINCT connection_type FROM customer_features WHERE connection_type IS NOT NULL AND connection_type != '' ORDER BY connection_type")
    conn_types = ['All'] + (conns_df['connection_type'].tolist() if not conns_df.empty else ['Postpaid', 'Prepaid'])
    
    circles_df = q("SELECT DISTINCT circle_name FROM customer_features WHERE circle_name IS NOT NULL AND circle_name != '' ORDER BY circle_name")
    circles = circles_df['circle_name'].tolist() if not circles_df.empty else ['Maharashtra', 'Delhi', 'Karnataka', 'Tamil Nadu', 'Gujarat']
    
    ages_df = q("SELECT DISTINCT age_band FROM customer_features WHERE age_band IS NOT NULL AND age_band != '' ORDER BY age_band")
    age_bands = ['All'] + (ages_df['age_band'].tolist() if not ages_df.empty else ['18-25', '26-35', '36-50', '50+'])
    
    devs_df = q("SELECT DISTINCT device_type FROM customer_features WHERE device_type IS NOT NULL AND device_type != '' ORDER BY device_type")
    devices = ['All'] + (devs_df['device_type'].tolist() if not devs_df.empty else ['4G Smartphone', '5G Smartphone', 'Basic Phone'])
    
    return regions, conn_types, circles, age_bands, devices

OPT_REGIONS, OPT_CONNS, OPT_CIRCLES, OPT_AGES, OPT_DEVICES = get_filter_options()
TENURE_OPTIONS = ['All Tenures', '0 Years (< 1 yr)', '1 Year (1-2 yrs)', '2 Years (2-3 yrs)', '3 Years (3+ yrs)']

# ==============================================================================
# 3. SIDEBAR CONTROL PANEL & QUICK PRESET ACTIONS
# ==============================================================================
sidebar_logo_tag = f'<img src="data:image/png;base64,{logo_b64}" class="sidebar-logo-img" alt="Airtel Logo" />' if logo_b64 else '📶'
st.sidebar.markdown(f"""
<div class="sidebar-brand-box">
  {sidebar_logo_tag}
  <div style="font-size:1.05rem; font-weight:800; color:#FFFFFF; letter-spacing:0.5px;">
    AIRTEL INTELLIGENCE
  </div>
  <div style="font-size:0.75rem; color:#E2E8F0; margin-top:2px;">
    Enterprise Retention Center
  </div>
  <div style="font-size:0.70rem; color:#10B981; margin-top:6px; font-weight:700;">
    <span class="pulse-indicator"></span>Active Base: 22,000 Subs
  </div>
</div>
""", unsafe_allow_html=True)

# Quick Presets for Bulk Setting (Updates Session State for all charts safely)
st.sidebar.markdown("### ⚡ Strategic Presets")
st.sidebar.caption("Calibrate all dashboard charts with 1 click:")

if st.sidebar.button("🚨 Focus: High-Risk (Prepaid)", use_container_width=True, help="Set all chart connection filters to Prepaid"):
    st.session_state["c1_filter_conn"] = "Prepaid"
    st.session_state["c2_filter_conn"] = "Prepaid"
    st.session_state["c3_filter_conn"] = "Prepaid"
    st.session_state["c4_filter_conn"] = "Prepaid"
    st.session_state["c5_filter_conn"] = "Prepaid"
    st.session_state["c6_filter_conn"] = "Prepaid"
    st.session_state["c7_filter_conn"] = "Prepaid"
    st.session_state["c8_filter_conn"] = "Prepaid"
    st.session_state["kpi_conn_filter"] = "Prepaid"
    st.session_state["sb_explore_conn"] = "Prepaid"
    st.rerun()

if st.sidebar.button("💼 Focus: Postpaid Core Base", use_container_width=True, help="Set all chart connection filters to Postpaid"):
    st.session_state["c1_filter_conn"] = "Postpaid"
    st.session_state["c2_filter_conn"] = "Postpaid"
    st.session_state["c3_filter_conn"] = "Postpaid"
    st.session_state["c4_filter_conn"] = "Postpaid"
    st.session_state["c5_filter_conn"] = "Postpaid"
    st.session_state["c6_filter_conn"] = "Postpaid"
    st.session_state["c7_filter_conn"] = "Postpaid"
    st.session_state["c8_filter_conn"] = "Postpaid"
    st.session_state["kpi_conn_filter"] = "Postpaid"
    st.session_state["sb_explore_conn"] = "Postpaid"
    st.rerun()

if st.sidebar.button("🔄 Reset All Filters to 'All'", use_container_width=True, help="Reset every individual chart filter to default"):
    defaults = {
        "c1_filter_region": "All",
        "c1_filter_conn": "All",
        "c2_filter_conn": "All",
        "c2_filter_min": "All (>=0)",
        "c3_filter_reg": "All",
        "c3_filter_conn": "All",
        "c4_filter_window": "All 6 Months (Jan-Jun 2025)",
        "c4_filter_conn": "All",
        "c5_filter_conn": "All",
        "c5_filter_dev": "All",
        "c6_filter_conn": "All",
        "c6_filter_dev": "All Devices",
        "c7_filter_age": "All",
        "c7_filter_conn": "All",
        "c8_filter_conn": "All",
        "c8_filter_dev": "All",
        "kpi_reg_filter": "All",
        "kpi_conn_filter": "All",
        "detail_selected_circle": "Maharashtra" if "Maharashtra" in OPT_CIRCLES else (OPT_CIRCLES[0] if OPT_CIRCLES else "Maharashtra"),
        "sb_explore_region": "All",
        "sb_explore_conn": "All",
        "sb_explore_tenure": "All Tenures",
        "dyn_screen_preset": "Standard 1080p (420px)"
    }
    for k, v in defaults.items():
        st.session_state[k] = v
    st.rerun()

st.sidebar.markdown("---")

# Dynamic Screen Height & Layout Control (No-Scroll Viewport Optimization)
st.sidebar.markdown("### 🖥️ Display Scale & Resolution")
screen_preset = st.sidebar.select_slider(
    "Vertical Chart Height",
    options=["Fit Screen (290px)", "Standard (310px)", "Expanded (350px)", "Large (400px)"],
    value="Standard (310px)",
    key="dyn_screen_preset",
    help="Adjust chart size to fit your monitor without scrolling."
)
HEIGHT_MAP = {
    "Fit Screen (290px)": 290,
    "Standard (310px)": 310,
    "Expanded (350px)": 350,
    "Large (400px)": 400
}
DYN_CHART_H = HEIGHT_MAP.get(screen_preset, 310)

st.sidebar.markdown("---")

# Sidebar Independent Exploration Sandbox
st.sidebar.markdown("### 🔬 Sidebar Cohort Explorer")
st.sidebar.caption("Use this sandbox to probe any custom segment independently from the main charts.")

sb_region = st.sidebar.selectbox("Sidebar Region Scope", OPT_REGIONS, key="sb_explore_region")
sb_conn = st.sidebar.selectbox("Sidebar Connection Scope", OPT_CONNS, key="sb_explore_conn")
sb_tenure = st.sidebar.selectbox("Sidebar Tenure Scope", TENURE_OPTIONS, key="sb_explore_tenure")

sb_ten_val = -1
if '0' in sb_tenure: sb_ten_val = 0
elif '1' in sb_tenure: sb_ten_val = 1
elif '2' in sb_tenure: sb_ten_val = 2
elif '3' in sb_tenure: sb_ten_val = 3

sql_sb = """
SELECT 
    COUNT(DISTINCT customer_id) AS total_subs,
    COUNT(DISTINCT CASE WHEN is_churned = 1 THEN customer_id END) AS churned_subs,
    COALESCE(ROUND(AVG(is_churned) * 100, 2), 0.0) AS churn_rate
FROM customer_features
WHERE (? = 'All' OR region = ?)
  AND (? = 'All' OR connection_type = ?)
  AND (? = -1 OR tenure_years = ?)
"""
df_sb = q(sql_sb, (sb_region, sb_region, sb_conn, sb_conn, sb_ten_val, sb_ten_val))
sb_tot = int(df_sb['total_subs'].iloc[0]) if not df_sb.empty and pd.notna(df_sb['total_subs'].iloc[0]) else 0
sb_chr = int(df_sb['churned_subs'].iloc[0]) if not df_sb.empty and pd.notna(df_sb['churned_subs'].iloc[0]) else 0
sb_rt = float(df_sb['churn_rate'].iloc[0]) if not df_sb.empty and pd.notna(df_sb['churn_rate'].iloc[0]) else 0.0
sb_diff = sb_rt - NATIONAL_BENCHMARK
sb_sign = "+" if sb_diff > 0 else ""
sb_col = "#FF6B6B" if sb_diff > 0 else "#10B981"

st.sidebar.markdown(f"""
<div class="sidebar-telemetry-card">
  <div style="font-size:0.72rem; color:#CBD5E1; text-transform:uppercase; font-weight:800; letter-spacing:0.8px;">
    <span class="pulse-indicator"></span>Sandbox Telemetry
  </div>
  <div style="font-size:1.50rem; font-weight:900; color:#FFFFFF; margin-top:4px;">
    {sb_rt:.2f}% <span style="font-size:0.78rem; font-weight:800; color:{sb_col};">({sb_sign}{sb_diff:.2f}% pts)</span>
  </div>
  <div style="font-size:0.77rem; color:#E2E8F0; margin-top:6px; line-height:1.4;">
    <b>Base:</b> {sb_tot:,} subs | <b>Leavers:</b> {sb_chr:,}<br>
    <b>National Ref:</b> 23.75% Benchmark
  </div>
</div>
""", unsafe_allow_html=True)

# ==============================================================================
# 4. ANIMATED AIRTEL HEADER WITH OFFICIAL LOGO & TELEMETRY
# ==============================================================================
logo_img_tag = f'<img src="data:image/png;base64,{logo_b64}" class="airtel-main-logo" alt="Airtel Logo" />' if logo_b64 else ''

st.markdown(f"""
<div class="dashboard-header-container">
  <div class="header-left">
    {logo_img_tag}
    <div class="header-text-block">
      <div class="header-title-text">
        AIRTEL TELECOM ANALYTICS | GROUP 1
        <span class="header-badge">● Retention Command Center</span>
      </div>
      <div class="header-subtitle">
        Retention & Circle Analysis Intelligence Dashboard
      </div>
      <div class="header-statement">
        <b>For the Head of Retention:</b> Identify high-churn cohorts and prioritize retention efforts across circles.
      </div>
    </div>
  </div>
  <div class="header-right-telemetry">
    <div style="font-size:0.75rem; color:#E2E8F0; text-transform:uppercase; letter-spacing:0.8px; font-weight:700;">
      <span class="pulse-indicator"></span>Audited Base: 22,000 Subs
    </div>
    <div style="font-size:1.15rem; color:#FFFFFF; font-weight:800; margin-top:2px;">
      National Ref: <span style="color:#FF6B6B;">23.75%</span>
    </div>
    <div style="font-size:0.70rem; color:#94A3B8; margin-top:2px;">
      Period: 1 Jan 2025 – 30 Jun 2025
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ==============================================================================
# 5. PRIMARY TABS: OVERVIEW & DETAIL
# ==============================================================================
tab_overview, tab_detail = st.tabs([
    "📊  OVERVIEW — EXECUTIVE MACRO VIEW", 
    "🔍  DETAIL — CIRCLE EXPLORER & COHORT DRILLDOWN"
])

# ==============================================================================
# TAB 1: OVERVIEW TAB
# ==============================================================================
with tab_overview:
    # --------------------------------------------------------------------------
    # Separate Executive Scope Controls for KPI Card 3
    # --------------------------------------------------------------------------
    kpi_f1, kpi_f2, kpi_info = st.columns([1.1, 1.1, 3.8])
    with kpi_f1:
        kpi_reg_val = st.selectbox("🌐 Card 3 Region", OPT_REGIONS, key="kpi_reg_filter")
    with kpi_f2:
        kpi_conn_val = st.selectbox("📶 Card 3 Conn", OPT_CONNS, key="kpi_conn_filter")
    with kpi_info:
        st.markdown('<div style="padding-top:16px; font-size:0.72rem; color:#F8FAFC !important;">💡 <b style="color:#FFFFFF !important;">Scope Calibration:</b> <span style="color:#CBD5E1 !important;">Controls Card 3 (Filtered Churn). Cards 1 & 2 are fixed audited benchmarks.</span></div>', unsafe_allow_html=True)

    st.markdown('<div style="margin-bottom: 8px;"></div>', unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # Exactly THREE Animated KPI Cards in One Row (Compact Fit-Screen)
    # --------------------------------------------------------------------------
    sql_kpi_filtered = """
    SELECT 
        COUNT(DISTINCT customer_id) AS total_subs,
        COUNT(DISTINCT CASE WHEN is_churned = 1 THEN customer_id END) AS churned_subs,
        COALESCE(ROUND(AVG(is_churned) * 100, 2), 0.0) AS churn_rate
    FROM customer_features
    WHERE (? = 'All' OR region = ?)
      AND (? = 'All' OR connection_type = ?)
    """
    df_kpi_filtered = q(sql_kpi_filtered, (kpi_reg_val, kpi_reg_val, kpi_conn_val, kpi_conn_val))
    filtered_subs = int(df_kpi_filtered['total_subs'].iloc[0]) if not df_kpi_filtered.empty and pd.notna(df_kpi_filtered['total_subs'].iloc[0]) else 0
    filtered_churn = int(df_kpi_filtered['churned_subs'].iloc[0]) if not df_kpi_filtered.empty and pd.notna(df_kpi_filtered['churned_subs'].iloc[0]) else 0
    filtered_rate = float(df_kpi_filtered['churn_rate'].iloc[0]) if not df_kpi_filtered.empty and pd.notna(df_kpi_filtered['churn_rate'].iloc[0]) else 0.0

    kpi1_col, kpi2_col, kpi3_col = st.columns(3)

    # CARD 1: TOTAL SUBSCRIBERS
    with kpi1_col:
        st.markdown("""
        <div class="kpi-card kpi-card-1">
          <div>
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <span class="kpi-badge kpi-badge-blue">Audited Base</span>
              <span style="font-size:0.65rem; color:#CBD5E1; font-weight:700;">22 Circles</span>
            </div>
            <div class="kpi-title">Total Subscribers (H1 2025)</div>
            <div class="kpi-value">22,000</div>
            <div class="kpi-tag-row">
              <span class="kpi-stat-tag kpi-stat-green">✓ 16,774 Retained (76.25%)</span>
              <span class="kpi-stat-tag kpi-stat-red">✗ 5,226 Churned (23.75%)</span>
            </div>
          </div>
          <p class="kpi-subtext">
            <b>Audited Baseline:</b> 23.75% national benchmark across 22 telecom circles.
          </p>
        </div>
        """, unsafe_allow_html=True)

    # CARD 2: T4 STATISTICAL VALIDATION
    with kpi2_col:
        st.markdown("""
        <div class="kpi-card kpi-card-2">
          <div>
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <span class="kpi-badge kpi-badge-purple">T4 Statistical Validation</span>
              <span style="font-size:0.65rem; color:#7C3AED; font-weight:700;">p &lt; 0.001</span>
            </div>
            <div class="kpi-title">Welch's t-Test (Active Base)</div>
            <div class="kpi-value">t = -42.32</div>
            <div class="kpi-tag-row">
              <span class="kpi-stat-tag kpi-stat-purple">Two-tailed (α = 0.05)</span>
              <span class="kpi-stat-tag kpi-stat-red">Diff: -₹1,407.87 (-51.0%)</span>
            </div>
          </div>
          <p class="kpi-subtext">
            <b>Welch's t-test:</b> Reject H₀ (N = 18,289 active | d = -0.57 large effect).
          </p>
        </div>
        """, unsafe_allow_html=True)

    # CARD 3: FILTERED CHURN
    with kpi3_col:
        rate_diff = filtered_rate - NATIONAL_BENCHMARK
        diff_color = "#ED1C24" if rate_diff > 0 else "#10B981"
        diff_sign = "+" if rate_diff > 0 else ""
        st.markdown(f"""
        <div class="kpi-card kpi-card-3">
          <div>
            <div style="display:flex; justify-content:space-between; align-items:center;">
              <span class="kpi-badge kpi-badge-red">Executive Cohort Churn</span>
              <span style="font-size:0.65rem; color:{diff_color}; font-weight:800;">{diff_sign}{rate_diff:.2f}% pts vs Ref</span>
            </div>
            <div class="kpi-title">Filtered Churn Rate</div>
            <div class="kpi-value" style="color:#ED1C24;">{filtered_rate:.2f}%</div>
            <div class="kpi-tag-row">
              <span class="kpi-stat-tag kpi-stat-green">Retained: {100.0 - filtered_rate:.2f}%</span>
              <span class="kpi-stat-tag kpi-stat-red">Leavers: {filtered_churn:,} / {filtered_subs:,}</span>
            </div>
          </div>
          <p class="kpi-subtext">
            <b>Scope:</b> {kpi_reg_val} / {kpi_conn_val} | <b>Ref (23.75%):</b> <span style="color:{diff_color}; font-weight:800;">{diff_sign}{rate_diff:.2f}% pts</span>
          </p>
        </div>
        """, unsafe_allow_html=True)

    # --------------------------------------------------------------------------
    # OVERVIEW CHARTS ORGANIZED INTO 2 SPACIOUS VIEWS (ELIMINATES CONGESTION)
    # --------------------------------------------------------------------------
    st.markdown('<div style="margin-top: 8px; margin-bottom: 4px; border-bottom: 1px solid rgba(255,255,255,0.10);"></div>', unsafe_allow_html=True)
    tab1_pipeline, tab1_behavior = st.tabs([
        "📊  CONVERSION PIPELINE & REGIONAL TREEMAP (CHARTS 1 & 2)",
        "🎯  COHORT ATTRITION RISK RADAR & STRATEGIC PLAYBOOK (CHART 3)"
    ])

    # ==========================================================================
    # TAB 1 - VIEW A: FUNNEL & REGIONAL TREEMAP (2 EXPANDED COLUMNS)
    # ==========================================================================
    with tab1_pipeline:
        c1_col, c2_col = st.columns(2)

        # ----------------------------------------------------------------------
        # CHART 1 — SUBSCRIBER RETENTION FUNNEL (Funnel Plot)
        # ----------------------------------------------------------------------
        with c1_col:
            with st.container(border=True):
                st.markdown("""
                <div class="chart-header-banner">
                  <div>
                    <div class="chart-name-title" style="color:#FFFFFF !important;">
                      <span style="color:#FFFFFF !important; font-size:0.86rem; font-weight:800; letter-spacing:0.2px; text-shadow:0 1px 3px rgba(0,0,0,0.8);">CHART 1: RETENTION FUNNEL</span>
                    </div>
                    <div class="chart-subtitle-scope" style="color:#CBD5E1 !important; font-size:0.72rem; font-weight:600; text-shadow:0 1px 2px rgba(0,0,0,0.6);">
                      Attrition Pipeline · Conversion & dropout
                    </div>
                  </div>
                  <span class="chart-type-tag">FUNNEL</span>
                </div>
                """, unsafe_allow_html=True)

                f_c1, f_c2 = st.columns(2)
                with f_c1:
                    c1_region = st.selectbox("🌐 Region (C1)", OPT_REGIONS, key="c1_filter_region")
                with f_c2:
                    c1_conn = st.selectbox("📶 Conn (C1)", OPT_CONNS, key="c1_filter_conn")

                st.markdown('<div style="margin-bottom: 6px;"></div>', unsafe_allow_html=True)

                sql_c1 = """
                SELECT 
                    COUNT(DISTINCT customer_id) AS total_subs,
                    COUNT(DISTINCT CASE WHEN recharge_total_6m > 0 THEN customer_id END) AS active_rechargers,
                    COUNT(DISTINCT CASE WHEN is_churned = 0 THEN customer_id END) AS retained_subs,
                    COUNT(DISTINCT CASE WHEN unresolved_count > 0 THEN customer_id END) AS at_risk_tickets,
                    COUNT(DISTINCT CASE WHEN is_churned = 1 THEN customer_id END) AS churned_subs
                FROM customer_features
                WHERE (? = 'All' OR region = ?)
                  AND (? = 'All' OR connection_type = ?)
                """
                df_c1 = q(sql_c1, (c1_region, c1_region, c1_conn, c1_conn))

                if not df_c1.empty and df_c1['total_subs'].iloc[0] > 0:
                    r = df_c1.iloc[0]
                    stages = ["1. Total Base", "2. Active Rechargers", "3. Retained Base", "4. At-Risk (Tickets)", "5. Lost Leavers"]
                    values = [int(r['total_subs']), int(r['active_rechargers']), int(r['retained_subs']), int(r['at_risk_tickets']), int(r['churned_subs'])]

                    fig_c1 = go.Figure(go.Funnel(
                        y=stages,
                        x=values,
                        texttemplate="<b>%{value:,}</b> (%{percentInitial:.1%})",
                        textposition="auto",
                        insidetextfont=dict(size=12, color="#FFFFFF", family="Arial Black"),
                        outsidetextfont=dict(size=11, color="#0F172A", family="Arial Black"),
                        marker=dict(
                            color=["#0B132B", "#1E293B", "#0284C7", "#D97706", "#ED1C24"],
                            line=dict(color="#FFFFFF", width=2)
                        ),
                        connector=dict(line=dict(color="rgba(100, 116, 139, 0.40)", width=2))
                    ))

                    fig_c1.update_layout(
                        title=dict(text=f"<b>Scope:</b> {c1_region} | {c1_conn}", font=dict(size=10, color=SLATE_GRAY)),
                        yaxis=dict(tickfont=dict(size=10.5, color="#0F172A", family="Arial Black"), automargin=True),
                        height=DYN_CHART_H,
                        margin=dict(l=135, r=20, t=20, b=15),
                        plot_bgcolor="#FFFFFF",
                        paper_bgcolor="#FFFFFF",
                        transition={'duration': 500, 'easing': 'cubic-in-out'},
                        hoverlabel=dict(bgcolor="#0B132B", font_size=11.5)
                    )
                    st.plotly_chart(fig_c1, use_container_width=True)
                else:
                    st.info("No subscriber records match.")

    # --------------------------------------------------------------------------
    # CHART 2 — REGIONAL & CIRCLE CHURN TREEMAP (Hierarchical Treemap)
    # --------------------------------------------------------------------------
    with c2_col:
        with st.container(border=True):
            st.markdown("""
            <div class="chart-header-banner">
              <div>
                <div class="chart-name-title" style="color:#FFFFFF !important;">
                  <span style="color:#FFFFFF !important; font-size:0.86rem; font-weight:800; letter-spacing:0.2px; text-shadow:0 1px 3px rgba(0,0,0,0.8);">CHART 2: REGIONAL & CIRCLE TREEMAP</span>
                </div>
                <div class="chart-subtitle-scope" style="color:#CBD5E1 !important; font-size:0.72rem; font-weight:600; text-shadow:0 1px 2px rgba(0,0,0,0.6);">
                  Hierarchical Sizing & Heat · Geographic attrition density
                </div>
              </div>
              <span class="chart-type-tag">TREEMAP</span>
            </div>
            """, unsafe_allow_html=True)

            c2_f1, c2_f2 = st.columns(2)
            with c2_f1:
                c2_conn = st.selectbox("📶 Conn (C2)", OPT_CONNS, key="c2_filter_conn")
            with c2_f2:
                c2_min_subs = st.selectbox("👥 Scale (C2)", ["All (>=0)", ">=500 subs", ">=1000 subs"], key="c2_filter_min")

            st.markdown('<div style="margin-bottom: 6px;"></div>', unsafe_allow_html=True)

            min_val = 0
            if "500" in c2_min_subs: min_val = 500
            elif "1000" in c2_min_subs: min_val = 1000

            sql_c2 = """
            SELECT 
                region,
                circle_name,
                COUNT(DISTINCT customer_id) AS total_subs,
                COUNT(DISTINCT CASE WHEN is_churned = 1 THEN customer_id END) AS churned_subs,
                COALESCE(ROUND(AVG(is_churned) * 100, 2), 0.0) AS churn_rate
            FROM customer_features
            WHERE (? = 'All' OR connection_type = ?)
            GROUP BY region, circle_name
            HAVING COUNT(DISTINCT customer_id) >= ?
            ORDER BY region, churn_rate DESC
            """
            df_c2 = q(sql_c2, (c2_conn, c2_conn, min_val))

            if not df_c2.empty:
                fig_c2 = px.treemap(
                    df_c2,
                    path=["region", "circle_name"],
                    values="total_subs",
                    color="churn_rate",
                    color_continuous_scale=[[0.0, "#F87171"], [0.35, "#EF4444"], [0.7, "#DC2626"], [1.0, "#7F1D1D"]],
                    range_color=[16, 35],
                    custom_data=["churn_rate", "total_subs", "churned_subs"]
                )
                fig_c2.update_traces(
                    texttemplate="<b>%{label}</b><br>%{value:,} (<b>%{color:.1f}%</b>)",
                    textfont=dict(size=11, family="Arial Black", color="#FFFFFF"),
                    marker=dict(pad=dict(t=16, l=3, r=3, b=3), line=dict(color="#FFFFFF", width=1.5)),
                    tiling=dict(packing="squarify", pad=2),
                    hovertemplate="<b>%{label}</b><br>Subscribers: %{customdata[1]:,}<br>Churn Rate: <b>%{customdata[0]:.2f}%</b><br>Leavers: %{customdata[2]:,}<extra></extra>"
                )
                fig_c2.update_layout(
                    title=dict(text=f"<b>Scope:</b> {c2_conn} | {c2_min_subs}", font=dict(size=9.5, color=SLATE_GRAY)),
                    height=DYN_CHART_H,
                    margin=dict(l=6, r=6, t=20, b=22),
                    coloraxis_colorbar=dict(title=dict(text="Churn %", font=dict(size=8, color=SLATE_GRAY)), orientation="h", y=-0.14, x=0.5, xanchor="center", len=0.65, thickness=6, tickfont=dict(size=7.5), ticksuffix="%"),
                    transition={'duration': 350, 'easing': 'cubic-in-out'},
                    hoverlabel=dict(bgcolor="#0B132B", font_size=11)
                )
                st.plotly_chart(fig_c2, use_container_width=True)
            else:
                st.info("No records match.")

    # ==========================================================================
    # TAB 1 - VIEW B: COHORT ATTRITION RADAR & STRATEGIC PLAYBOOK
    # ==========================================================================
    with tab1_behavior:
        c3_col, c3_playbook = st.columns([1.15, 0.85])

        # ----------------------------------------------------------------------
        # CHART 3 — COHORT ATTRITION RISK RADAR (Polar Radar Chart)
        # ----------------------------------------------------------------------
        with c3_col:
            with st.container(border=True):
                st.markdown("""
                <div class="chart-header-banner">
                  <div>
                    <div class="chart-name-title" style="color:#FFFFFF !important;">
                      <span style="color:#FFFFFF !important; font-size:0.86rem; font-weight:800; letter-spacing:0.2px; text-shadow:0 1px 3px rgba(0,0,0,0.8);">CHART 3: COHORT ATTRITION RISK RADAR</span>
                    </div>
                    <div class="chart-subtitle-scope" style="color:#CBD5E1 !important; font-size:0.72rem; font-weight:600; text-shadow:0 1px 2px rgba(0,0,0,0.6);">
                      Behavioral Spider Profile · Retained vs Churned footprint across 5 risk dimensions
                    </div>
                  </div>
                  <span class="chart-type-tag">POLAR RADAR</span>
                </div>
                """, unsafe_allow_html=True)

                c3_f1, c3_f2 = st.columns(2)
                with c3_f1:
                    c3_region = st.selectbox("🌐 Scope Region (C3)", OPT_REGIONS, key="c3_filter_reg")
                with c3_f2:
                    c3_conn = st.selectbox("📶 Scope Conn (C3)", OPT_CONNS, key="c3_filter_conn")

                st.markdown('<div style="margin-bottom: 6px;"></div>', unsafe_allow_html=True)

                sql_c3 = """
                SELECT 
                    is_churned,
                    ROUND(AVG(CASE WHEN complaint_count > 0 THEN 1.0 ELSE 0.0 END) * 100, 1) AS pct_complaint,
                    ROUND(AVG(CASE WHEN recharge_total_6m < 1500 THEN 1.0 ELSE 0.0 END) * 100, 1) AS pct_low_recharge,
                    ROUND(AVG(CASE WHEN tenure_years = 0 THEN 1.0 ELSE 0.0 END) * 100, 1) AS pct_yr0_tenure,
                    ROUND(AVG(CASE WHEN connection_type = 'Prepaid' THEN 1.0 ELSE 0.0 END) * 100, 1) AS pct_prepaid,
                    ROUND(AVG(CASE WHEN stated_arpu < 200 THEN 1.0 ELSE 0.0 END) * 100, 1) AS pct_low_arpu
                FROM customer_features
                WHERE (? = 'All' OR region = ?)
                  AND (? = 'All' OR connection_type = ?)
                GROUP BY is_churned
                """
                df_c3 = q(sql_c3, (c3_region, c3_region, c3_conn, c3_conn))

                if not df_c3.empty and len(df_c3) == 2:
                    categories = ['Complaints<br>(>0)', 'Low Spend<br>(<₹1.5k)', 'Tenure<br>(<1 Yr)', 'Prepaid<br>Segment', 'Low ARPU<br>(<₹200)']
                    df_ret = df_c3[df_c3['is_churned'] == 0].iloc[0]
                    df_chr = df_c3[df_c3['is_churned'] == 1].iloc[0]

                    r_ret = [float(df_ret['pct_complaint']), float(df_ret['pct_low_recharge']), float(df_ret['pct_yr0_tenure']), float(df_ret['pct_prepaid']), float(df_ret['pct_low_arpu'])]
                    r_chr = [float(df_chr['pct_complaint']), float(df_chr['pct_low_recharge']), float(df_chr['pct_yr0_tenure']), float(df_chr['pct_prepaid']), float(df_chr['pct_low_arpu'])]

                    fig_c3 = go.Figure()
                    fig_c3.add_trace(go.Scatterpolar(
                        r=r_ret + [r_ret[0]],
                        theta=categories + [categories[0]],
                        fill='toself',
                        name='Retained Base (76.3%)',
                        mode='lines+markers+text',
                        text=[f"{v:.0f}%" for v in r_ret] + [""],
                        textposition="top center",
                        textfont=dict(size=10.5, color="#0284C7", family="Arial Black"),
                        line=dict(color='#0284C7', width=3),
                        marker=dict(size=9, color='#0284C7', symbol='circle'),
                        fillcolor='rgba(2, 132, 199, 0.20)',
                        hovertemplate="<b>%{theta}</b><br>Retained: <b>%{r:.1f}%</b><extra></extra>"
                    ))
                    fig_c3.add_trace(go.Scatterpolar(
                        r=r_chr + [r_chr[0]],
                        theta=categories + [categories[0]],
                        fill='toself',
                        name='Lost Churned (23.8%)',
                        mode='lines+markers+text',
                        text=[f"{v:.0f}%" for v in r_chr] + [""],
                        textposition="bottom center",
                        textfont=dict(size=10.5, color="#ED1C24", family="Arial Black"),
                        line=dict(color=AIRTEL_RED, width=3.5),
                        marker=dict(size=10, color=AIRTEL_RED, symbol='diamond'),
                        fillcolor='rgba(237, 28, 36, 0.35)',
                        hovertemplate="<b>%{theta}</b><br>Churned: <b>%{r:.1f}%</b><extra></extra>"
                    ))

                    fig_c3.update_layout(
                        polar=dict(
                            radialaxis=dict(visible=True, range=[0, 100], ticksuffix="%", tickfont=dict(size=8.5, color="#CBD5E1"), gridcolor="rgba(255,255,255,0.25)", tickvals=[20, 40, 60, 80, 100]),
                            angularaxis=dict(tickfont=dict(size=9.5, color="#FFFFFF", family="Arial Black"), rotation=90, direction="clockwise", linecolor="rgba(255,255,255,0.25)"),
                            bgcolor="#FFFFFF"
                        ),
                        title=dict(text=f"<b>Scope:</b> {c3_region} | {c3_conn}", font=dict(size=10, color=SLATE_GRAY)),
                        height=DYN_CHART_H,
                        margin=dict(l=30, r=30, t=30, b=20),
                        legend=dict(orientation="h", yanchor="bottom", y=1.06, xanchor="center", x=0.5, font=dict(size=9.5, family="Arial Black", color="#FFFFFF")),
                        transition={'duration': 500, 'easing': 'cubic-in-out'},
                        hoverlabel=dict(bgcolor="#0B132B", font_size=11.5)
                    )
                    st.plotly_chart(fig_c3, use_container_width=True)
                else:
                    st.info("No cohort records match.")

        # ----------------------------------------------------------------------
        # EXECUTIVE COHORT PLAYBOOK & KEY TAKEAWAYS CARD
        # ----------------------------------------------------------------------
        with c3_playbook:
            with st.container(border=True):
                st.markdown("""
                <div class="chart-header-banner">
                  <div>
                    <div class="chart-name-title" style="color:#FFFFFF !important;">
                      <span style="color:#FFFFFF !important; font-size:0.86rem; font-weight:800; letter-spacing:0.2px; text-shadow:0 1px 3px rgba(0,0,0,0.8);">🎯 RETENTION ACTION PLAYBOOK</span>
                    </div>
                    <div class="chart-subtitle-scope" style="color:#CBD5E1 !important; font-size:0.72rem; font-weight:600; text-shadow:0 1px 2px rgba(0,0,0,0.6);">
                      Priority Interventions Derived from Cohort Footprint
                    </div>
                  </div>
                  <span class="chart-type-tag" style="background:rgba(16,185,129,0.22); color:#34D399; border:1px solid rgba(52,211,153,0.5);">PRIORITY MATRIX</span>
                </div>
                <div style="font-size:0.73rem; line-height:1.45; color:#FFFFFF !important; padding-top:4px;">
                  <div style="display:flex; align-items:flex-start; gap:8px; margin-bottom:6px; background:rgba(255,255,255,0.08); padding:8px 12px; border-radius:8px; border:1px solid rgba(255,255,255,0.20); border-left:4px solid #ED1C24;">
                    <span style="background:#ED1C24; color:#FFFFFF !important; font-weight:900; font-size:0.70rem; min-width:20px; height:20px; border-radius:50%; display:inline-flex; align-items:center; justify-content:center; box-shadow:0 2px 6px rgba(237,28,36,0.6); flex-shrink:0;">1</span>
                    <div style="color:#FFFFFF !important;">
                      <b style="color:#FFFFFF !important; font-size:0.80rem;">Year 0 (&lt; 1 Yr) Cohort Fragility:</b> <span style="color:#F1F5F9 !important;">New subscribers exhibit peak attrition rate of <b style="color:#FF6B6B !important; font-weight:800;">32.1%</b>. Immediate 30-day onboarding check-ins and recharge rewards mitigate early fallout.</span>
                    </div>
                  </div>
                  <div style="display:flex; align-items:flex-start; gap:8px; margin-bottom:6px; background:rgba(255,255,255,0.08); padding:8px 12px; border-radius:8px; border:1px solid rgba(255,255,255,0.20); border-left:4px solid #ED1C24;">
                    <span style="background:#ED1C24; color:#FFFFFF !important; font-weight:900; font-size:0.70rem; min-width:20px; height:20px; border-radius:50%; display:inline-flex; align-items:center; justify-content:center; box-shadow:0 2px 6px rgba(237,28,36,0.6); flex-shrink:0;">2</span>
                    <div style="color:#FFFFFF !important;">
                      <b style="color:#FFFFFF !important; font-size:0.80rem;">Prepaid Vulnerability Gap:</b> <span style="color:#F1F5F9 !important;">Prepaid users churn <b style="color:#FF6B6B !important; font-weight:800;">7.6 percentage points</b> higher than postpaid (25.1% vs 17.5%). Multi-month bundle incentives stabilize recurring renewals.</span>
                    </div>
                  </div>
                  <div style="display:flex; align-items:flex-start; gap:8px; margin-bottom:6px; background:rgba(255,255,255,0.08); padding:8px 12px; border-radius:8px; border:1px solid rgba(255,255,255,0.20); border-left:4px solid #ED1C24;">
                    <span style="background:#ED1C24; color:#FFFFFF !important; font-weight:900; font-size:0.70rem; min-width:20px; height:20px; border-radius:50%; display:inline-flex; align-items:center; justify-content:center; box-shadow:0 2px 6px rgba(237,28,36,0.6); flex-shrink:0;">3</span>
                    <div style="color:#FFFFFF !important;">
                      <b style="color:#FFFFFF !important; font-size:0.80rem;">Unresolved Complaint Escalations:</b> <span style="color:#F1F5F9 !important;">Subscribers with open support tickets churn at <b style="color:#FF6B6B !important; font-weight:800;">2.8x</b> baseline rate. Priority SLA escalation routing prevents preventable departures.</span>
                    </div>
                  </div>
                  <div style="display:flex; align-items:flex-start; gap:8px; background:rgba(255,255,255,0.08); padding:8px 12px; border-radius:8px; border:1px solid rgba(255,255,255,0.20); border-left:4px solid #ED1C24;">
                    <span style="background:#ED1C24; color:#FFFFFF !important; font-weight:900; font-size:0.70rem; min-width:20px; height:20px; border-radius:50%; display:inline-flex; align-items:center; justify-content:center; box-shadow:0 2px 6px rgba(237,28,36,0.6); flex-shrink:0;">4</span>
                    <div style="color:#FFFFFF !important;">
                      <b style="color:#FFFFFF !important; font-size:0.80rem;">Low Spend (&lt; ₹1.5k) Concentration:</b> <span style="color:#F1F5F9 !important;">Accounts with 6-month recharge &lt; ₹1,500 constitute <b style="color:#FF6B6B !important; font-weight:800;">80.6%</b> of all leavers (4,210 subs). Targeted micro-recharge top-ups preserve base tenure.</span>
                    </div>
                  </div>
                </div>
                """, unsafe_allow_html=True)

    st.markdown('<div style="margin-top: 6px;"></div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="executive-insight-bar">
      <span class="insight-pill">EXECUTIVE INSIGHT</span>
      <span><b>Key Retention Takeaway:</b> Year 0 (&lt; 1 yr) cohorts exhibit peak attrition vulnerability (32.1%) with prepaid users churning 7.6% pts higher than postpaid. Onboarding interventions in Maharashtra and geographic outliers drive optimal retention impact.</span>
    </div>
    """, unsafe_allow_html=True)


# ==============================================================================
# TAB 2: DETAIL TAB — CIRCLE EXPLORER
# ==============================================================================
with tab_detail:
    # Target Circle Selector & Compact Operational Summary Hero Card
    d_c1, d_c2 = st.columns([1.5, 3.5])
    with d_c1:
        default_circle_idx = OPT_CIRCLES.index("Maharashtra") if "Maharashtra" in OPT_CIRCLES else 0
        selected_circle = st.selectbox(
            "Target Circle for Deep Investigation", 
            OPT_CIRCLES, 
            index=default_circle_idx, 
            key="detail_selected_circle"
        )
    
    # Query Circle Summary Metrics using Distinct Subscribers for Open Tickets
    sql_circle_kpi = """
    SELECT 
        circle_name,
        region,
        COUNT(DISTINCT customer_id) AS total_subs,
        COUNT(DISTINCT CASE WHEN is_churned = 1 THEN customer_id END) AS churned_subs,
        COALESCE(ROUND(AVG(is_churned) * 100, 2), 0.0) AS churn_rate,
        COUNT(DISTINCT CASE WHEN unresolved_count > 0 THEN customer_id END) AS open_ticket_subs,
        COALESCE(ROUND(COUNT(DISTINCT CASE WHEN unresolved_count > 0 THEN customer_id END) * 100.0 / COUNT(DISTINCT customer_id), 2), 0.0) AS open_ticket_pct,
        COALESCE(ROUND(AVG(stated_arpu), 2), 0.0) AS avg_arpu,
        COALESCE(ROUND(AVG(recharge_total_6m), 2), 0.0) AS avg_spend,
        COALESCE(SUM(complaint_count), 0) AS total_complaints,
        COALESCE(SUM(unresolved_count), 0) AS total_open_tickets
    FROM customer_features
    WHERE circle_name = ?
    GROUP BY circle_name, region
    """
    df_circle_kpi = q(sql_circle_kpi, (selected_circle,))
    
    if not df_circle_kpi.empty:
        c_info = df_circle_kpi.iloc[0]
        c_name = c_info['circle_name']
        c_reg = c_info['region']
        c_tot = int(c_info['total_subs'])
        c_chr = int(c_info['churned_subs'])
        c_rate = float(c_info['churn_rate'])
        c_open_subs = int(c_info['open_ticket_subs'])
        c_open_pct = float(c_info['open_ticket_pct'])
        c_open_tickets = int(c_info['total_open_tickets'])
        c_arpu = float(c_info['avg_arpu'])
    else:
        c_name = selected_circle
        c_reg = "N/A"
        c_tot = 0
        c_chr = 0
        c_rate = 0.0
        c_open_subs = 0
        c_open_pct = 0.0
        c_open_tickets = 0
        c_arpu = 0.0

    with d_c2:
        diff_nat = c_rate - NATIONAL_BENCHMARK
        c_status = f"+{diff_nat:.2f}% pts Above Ref" if diff_nat > 0 else f"{diff_nat:.2f}% pts Below Ref"
        c_badge_color = "#ED1C24" if diff_nat > 0 else "#10B981"
        st.markdown(f"""
        <div class="circle-hero-card">
          <div style="font-size:0.95rem; font-weight:800; color:#FFFFFF !important;">
            {c_name} ({c_reg} Region) — Circle Operational Intelligence
            <span style="float:right; font-size:0.75rem; color:{c_badge_color} !important; font-weight:700;">● {c_status}</span>
          </div>
          <div style="font-size:0.76rem; color:#CBD5E1 !important; margin-top:2px;">
            <b style="color:#FFFFFF !important;">Total Subs:</b> <span style="color:#FFFFFF !important;">{c_tot:,}</span> | <b style="color:#FFFFFF !important;">Leavers:</b> <span style="color:#FFFFFF !important;">{c_chr:,}</span> | 
            <b style="color:#FFFFFF !important;">Circle Churn:</b> <span style="color:{c_badge_color} !important; font-weight:800;">{c_rate:.2f}%</span> | 
            <b style="color:#FFFFFF !important;">Open-Ticket Subs:</b> <span style="color:#FF6B6B !important; font-weight:800;">{c_open_subs:,}</span> ({c_open_pct:.2f}%) | 
            <b style="color:#FFFFFF !important;">Open Tickets:</b> <span style="color:#FFFFFF !important;">{c_open_tickets:,}</span> | <b style="color:#FFFFFF !important;">ARPU:</b> <span style="color:#FFFFFF !important;">₹{c_arpu:.2f}</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

    # Sub-tabs for Detail Tab to fit screen perfectly without scrolling
    det_tab_ops, det_tab_matrix, det_tab_waterfall = st.tabs([
        "📈  CADENCE TREND & CIRCLE SEVERITY GAUGE (CHARTS 4 & 5)",
        "📱  DEVICE ECOSYSTEM & ARPU RISK MATRIX (CHARTS 6 & 7)",
        "🌊  SUBSCRIBER ATTRITION WATERFALL BRIDGE (CHART 8)"
    ])

    # --------------------------------------------------------------------------
    # SUB-TAB 1: CHART 4 & CHART 5 (SIDE-BY-SIDE IN 2 COLUMNS)
    # --------------------------------------------------------------------------
    with det_tab_ops:
        det_col1, det_col2 = st.columns(2)

        # --------------------------------------------------------------------------
        # CHART 4 — MONTHLY ATTRITION STEP-LINE CADENCE (Step-Line Plot)
        # --------------------------------------------------------------------------
        with det_col1:
            with st.container(border=True):
                st.markdown(f"""
                <div class="chart-header-banner">
                  <div>
                    <div class="chart-name-title" style="color:#FFFFFF !important;">
                      <span style="color:#FFFFFF !important; font-size:0.86rem; font-weight:800; letter-spacing:0.2px; text-shadow:0 1px 3px rgba(0,0,0,0.8);">CHART 4: MONTHLY ATTRITION STEP-LINE CADENCE</span>
                    </div>
                    <div class="chart-subtitle-scope" style="color:#CBD5E1 !important; font-size:0.72rem; font-weight:600; text-shadow:0 1px 2px rgba(0,0,0,0.6);">
                      Step-Line Trend · Discrete attrition trajectory in {selected_circle}
                    </div>
                  </div>
                  <span class="chart-type-tag">STEP-LINE</span>
                </div>
                """, unsafe_allow_html=True)

                c4_f1, c4_f2 = st.columns(2)
                with c4_f1:
                    c4_window = st.selectbox(
                        "📅 Time Window (C4)", 
                        ["All 6 Months (Jan-Jun 2025)", "Q1 2025 (Jan-Mar)", "Q2 2025 (Apr-Jun)"], 
                        key="c4_filter_window"
                    )
                with c4_f2:
                    c4_conn = st.selectbox("📶 Conn Type (C4)", OPT_CONNS, key="c4_filter_conn")

                sql_c4 = """
                SELECT 
                    strftime('%Y-%m', churn_date) AS churn_month,
                    COUNT(DISTINCT customer_id) AS monthly_leavers,
                    COALESCE(ROUND(COUNT(DISTINCT customer_id) * 100.0 / (SELECT COUNT(DISTINCT customer_id) FROM customer_features WHERE circle_name = ?), 2), 0.0) AS monthly_churn_rate
                FROM customer_features
                WHERE circle_name = ?
                  AND is_churned = 1
                  AND churn_date IS NOT NULL
                  AND (? = 'All' OR connection_type = ?)
                  AND (
                      (? = 'All 6 Months (Jan-Jun 2025)' AND churn_date >= '2025-01-01' AND churn_date < '2025-07-01')
                      OR (? = 'Q1 2025 (Jan-Mar)' AND churn_date >= '2025-01-01' AND churn_date < '2025-04-01')
                      OR (? = 'Q2 2025 (Apr-Jun)' AND churn_date >= '2025-04-01' AND churn_date < '2025-07-01')
                  )
                GROUP BY churn_month
                ORDER BY churn_month
                """
                df_c4 = q(sql_c4, (selected_circle, selected_circle, c4_conn, c4_conn, c4_window, c4_window, c4_window))

                if not df_c4.empty:
                    fig_c4 = go.Figure()
                    fig_c4.add_hline(
                        y=round(NATIONAL_BENCHMARK / 6.0, 2), line_dash="dash", line_color=AIRTEL_RED, line_width=1.5,
                        annotation_text="Monthly Benchmark (~3.96%)", annotation_position="top right",
                        annotation_font_size=10, annotation_font_color=AIRTEL_RED, annotation_font_family="Arial Black"
                    )

                    fig_c4.add_trace(go.Scatter(
                        x=df_c4['churn_month'],
                        y=df_c4['monthly_churn_rate'],
                        mode="lines+markers+text",
                        line_shape="hv",
                        line=dict(color=AIRTEL_RED, width=3.5),
                        marker=dict(size=10, color=NAVY_DARK, line=dict(color="#FFFFFF", width=2.5)),
                        fill="tozeroy",
                        fillcolor="rgba(237, 28, 36, 0.10)",
                        text=[f"<b>{v:.2f}%</b>" for v in df_c4['monthly_churn_rate']],
                        textposition="top center",
                        textfont=dict(size=11, color="#0F172A", family="Arial Black"),
                        customdata=df_c4['monthly_leavers'],
                        hovertemplate="Month: <b>%{x}</b><br>Monthly Churn Rate: <b>%{y:.2f}%</b><br>Leavers: <b>%{customdata:,}</b> subs<extra></extra>"
                    ))

                    c4_max = df_c4['monthly_churn_rate'].max() if not df_c4.empty else None
                    c4_upper = max(8.0, float(c4_max * 1.35) if pd.notna(c4_max) else 8.0)

                    fig_c4.update_layout(
                        title=dict(text=f"<b>Scope:</b> {c4_window} | {c4_conn}", font=dict(size=10, color=SLATE_GRAY)),
                        xaxis=dict(title=dict(text="<b>Churn Month</b>", font=dict(size=10, color="#0F172A", family="Arial Black")), tickfont=dict(size=9.5, family="Arial Black", color="#0F172A")),
                        yaxis=dict(title=dict(text="<b>Monthly Churn Rate (%)</b>", font=dict(size=10, color="#0F172A", family="Arial Black")), range=[0, c4_upper], ticksuffix="%", tickfont=dict(size=9.5, family="Arial Black", color="#0F172A")),
                        height=DYN_CHART_H,
                        margin=dict(l=55, r=20, t=25, b=40),
                        plot_bgcolor="#FFFFFF",
                        paper_bgcolor="#FFFFFF",
                        transition={'duration': 500, 'easing': 'cubic-in-out'},
                        hoverlabel=dict(bgcolor="#0B132B", font_size=11.5)
                    )
                    st.plotly_chart(fig_c4, use_container_width=True)
                else:
                    st.info(f"No records found for {selected_circle}.")

        # --------------------------------------------------------------------------
        # CHART 5 — CIRCLE CHURN SEVERITY GAUGE (Dial Indicator)
        # --------------------------------------------------------------------------
        with det_col2:
            with st.container(border=True):
                st.markdown(f"""
                <div class="chart-header-banner">
                  <div>
                    <div class="chart-name-title" style="color:#FFFFFF !important;">
                      <span style="color:#FFFFFF !important; font-size:0.86rem; font-weight:800; letter-spacing:0.2px; text-shadow:0 1px 3px rgba(0,0,0,0.8);">CHART 5: CIRCLE CHURN SEVERITY GAUGE</span>
                    </div>
                    <div class="chart-subtitle-scope" style="color:#CBD5E1 !important; font-size:0.72rem; font-weight:600; text-shadow:0 1px 2px rgba(0,0,0,0.6);">
                      Dial Indicator · Churn severity vs 23.75% benchmark in {selected_circle}
                    </div>
                  </div>
                  <span class="chart-type-tag">DIAL GAUGE</span>
                </div>
                """, unsafe_allow_html=True)

                c5_f1, c5_f2 = st.columns(2)
                with c5_f1:
                    c5_conn = st.selectbox("📶 Conn Type (C5)", OPT_CONNS, key="c5_filter_conn")
                with c5_f2:
                    c5_device = st.selectbox("📱 Device Scope (C5)", OPT_DEVICES, key="c5_filter_dev")

                sql_c5 = """
                SELECT 
                    circle_name,
                    COUNT(DISTINCT customer_id) AS total_subs,
                    COUNT(DISTINCT CASE WHEN is_churned = 1 THEN customer_id END) AS churned_subs,
                    COALESCE(ROUND(AVG(is_churned) * 100, 2), 0.0) AS churn_rate
                FROM customer_features
                WHERE circle_name = ?
                  AND (? = 'All' OR connection_type = ?)
                  AND (? = 'All' OR device_type = ?)
                GROUP BY circle_name
                """
                df_c5 = q(sql_c5, (selected_circle, c5_conn, c5_conn, c5_device, c5_device))

                if not df_c5.empty:
                    c5_rate = float(df_c5['churn_rate'].iloc[0])
                    c5_subs = int(df_c5['total_subs'].iloc[0])
                    c5_leavers = int(df_c5['churned_subs'].iloc[0])

                    fig_c5 = go.Figure(go.Indicator(
                        mode="gauge+number+delta",
                        value=c5_rate,
                        delta={'reference': NATIONAL_BENCHMARK, 'valueformat': '.2f', 'suffix': '% pts vs Ref', 'font': {'size': 13, 'family': 'Arial Black', 'color': AIRTEL_RED if c5_rate > NATIONAL_BENCHMARK else '#10B981'}},
                        number={'suffix': '%', 'font': {'size': 36, 'color': AIRTEL_RED if c5_rate > NATIONAL_BENCHMARK else '#10B981', 'family': 'Arial Black'}},
                        gauge={
                            'axis': {'range': [0, 50], 'ticksuffix': '%', 'tickfont': {'size': 11, 'family': 'Arial Black', 'color': '#0F172A'}},
                            'bar': {'color': AIRTEL_RED if c5_rate > NATIONAL_BENCHMARK else NAVY_DARK, 'thickness': 0.30},
                            'bgcolor': "white",
                            'borderwidth': 1,
                            'bordercolor': BORDER_GRAY,
                            'steps': [
                                {'range': [0, 20], 'color': '#ECFDF5'},
                                {'range': [20, 25], 'color': '#FFFBEB'},
                                {'range': [25, 50], 'color': '#FEF2F2'}
                            ],
                            'threshold': {
                                'line': {'color': '#0F172A', 'width': 3.5},
                                'thickness': 0.82,
                                'value': NATIONAL_BENCHMARK
                            }
                        }
                    ))

                    fig_c5.update_layout(
                        title=dict(text=f"<b>Scope:</b> {c5_conn} | {c5_device} | Base: {c5_subs:,} (Leavers: {c5_leavers:,})", font=dict(size=10, color=SLATE_GRAY)),
                        height=DYN_CHART_H,
                        margin=dict(l=25, r=25, t=30, b=18),
                        paper_bgcolor="#FFFFFF",
                        transition={'duration': 500, 'easing': 'cubic-in-out'}
                    )
                    st.plotly_chart(fig_c5, use_container_width=True)
                else:
                    st.info(f"No records found.")

    # --------------------------------------------------------------------------
    # SUB-TAB 2: CHART 6 & CHART 7 (SIDE-BY-SIDE IN 2 COLUMNS)
    # --------------------------------------------------------------------------
    with det_tab_matrix:
        det_c1, det_c2 = st.columns(2)

        # --------------------------------------------------------------------------
        # CHART 6 — NETWORK & DEVICE ECOSYSTEM DONUT (Donut Ring Chart)
        # --------------------------------------------------------------------------
        with det_c1:
            with st.container(border=True):
                st.markdown(f"""
                <div class="chart-header-banner">
                  <div>
                    <div class="chart-name-title" style="color:#FFFFFF !important;">
                      <span style="color:#FFFFFF !important; font-size:0.86rem; font-weight:800; letter-spacing:0.2px; text-shadow:0 1px 3px rgba(0,0,0,0.8);">CHART 6: NETWORK & DEVICE DONUT</span>
                    </div>
                    <div class="chart-subtitle-scope" style="color:#CBD5E1 !important; font-size:0.72rem; font-weight:600; text-shadow:0 1px 2px rgba(0,0,0,0.6);">
                      Donut Ring · Device share & attrition breakdown in {selected_circle}
                    </div>
                  </div>
                  <span class="chart-type-tag">DONUT RING</span>
                </div>
                """, unsafe_allow_html=True)

                c6_f1, c6_f2 = st.columns(2)
                with c6_f1:
                    c6_conn = st.selectbox("📶 Conn (C6)", OPT_CONNS, key="c6_filter_conn")
                with c6_f2:
                    c6_device = st.selectbox("📱 Scope Device (C6)", ['All Devices'] + OPT_DEVICES, key="c6_filter_dev")

                sql_c6 = """
                SELECT 
                    COALESCE(device_type, 'Other') AS device_type,
                    COUNT(DISTINCT customer_id) AS total_subs,
                    COUNT(DISTINCT CASE WHEN is_churned = 1 THEN customer_id END) AS churned_subs,
                    COALESCE(ROUND(AVG(is_churned) * 100, 2), 0.0) AS churn_rate
                FROM customer_features
                WHERE circle_name = ?
                  AND (? = 'All' OR connection_type = ?)
                  AND (? = 'All Devices' OR device_type = ?)
                GROUP BY device_type
                ORDER BY total_subs DESC
                """
                df_c6 = q(sql_c6, (selected_circle, c6_conn, c6_conn, c6_device, c6_device))

                if not df_c6.empty:
                    fig_c6 = go.Figure(go.Pie(
                        labels=df_c6['device_type'],
                        values=df_c6['total_subs'],
                        hole=0.55,
                        textinfo="label+percent",
                        insidetextfont=dict(size=12, color="#FFFFFF", family="Arial Black"),
                        outsidetextfont=dict(size=11, color="#0F172A", family="Arial Black"),
                        marker=dict(colors=[NAVY_DARK, AIRTEL_RED, "#0284C7", "#F97316"], line=dict(color="#FFFFFF", width=2)),
                        customdata=df_c6[['churn_rate', 'churned_subs']],
                        hovertemplate="<b>%{label}</b><br>Subscribers: %{value:,} (%{percent})<br>Churn Rate: <b>%{customdata[0]:.2f}%</b><br>Leavers: %{customdata[1]:,}<extra></extra>"
                    ))

                    fig_c6.update_layout(
                        title=dict(text=f"<b>Scope:</b> {c6_conn} | {c6_device}", font=dict(size=10, color=SLATE_GRAY)),
                        height=DYN_CHART_H,
                        margin=dict(l=15, r=15, t=25, b=35),
                        plot_bgcolor="#FFFFFF",
                        paper_bgcolor="#FFFFFF",
                        legend=dict(orientation="h", yanchor="bottom", y=-0.12, xanchor="center", x=0.5, font=dict(size=9.5, family="Arial Black")),
                        transition={'duration': 500, 'easing': 'cubic-in-out'},
                        hoverlabel=dict(bgcolor="#0B132B", font_size=11.5)
                    )
                    st.plotly_chart(fig_c6, use_container_width=True)
                else:
                    st.info("No records match.")

        # --------------------------------------------------------------------------
        # CHART 7 — TENURE VS ARPU RISK BUBBLE MATRIX (Bubble Plot)
        # --------------------------------------------------------------------------
        with det_c2:
            with st.container(border=True):
                st.markdown(f"""
                <div class="chart-header-banner">
                  <div>
                    <div class="chart-name-title" style="color:#FFFFFF !important;">
                      <span style="color:#FFFFFF !important; font-size:0.86rem; font-weight:800; letter-spacing:0.2px; text-shadow:0 1px 3px rgba(0,0,0,0.8);">CHART 7: TENURE VS ARPU BUBBLE MATRIX</span>
                    </div>
                    <div class="chart-subtitle-scope" style="color:#CBD5E1 !important; font-size:0.72rem; font-weight:600; text-shadow:0 1px 2px rgba(0,0,0,0.6);">
                      Bubble Matrix · Size=Subscribers, Y=Churn % in {selected_circle}
                    </div>
                  </div>
                  <span class="chart-type-tag">BUBBLE MATRIX</span>
                </div>
                """, unsafe_allow_html=True)

                c7_f1, c7_f2 = st.columns(2)
                with c7_f1:
                    c7_age = st.selectbox("🎂 Age Band (C7)", OPT_AGES, key="c7_filter_age")
                with c7_f2:
                    c7_conn = st.selectbox("📶 Conn (C7)", OPT_CONNS, key="c7_filter_conn")

                sql_c7 = """
                SELECT 
                    tenure_years,
                    COUNT(DISTINCT customer_id) AS total_subs,
                    COUNT(DISTINCT CASE WHEN is_churned = 1 THEN customer_id END) AS churned_subs,
                    COALESCE(ROUND(AVG(is_churned) * 100, 2), 0.0) AS churn_rate,
                    COALESCE(ROUND(AVG(stated_arpu), 1), 0.0) AS avg_arpu,
                    COALESCE(ROUND(AVG(recharge_total_6m), 1), 0.0) AS avg_spend
                FROM customer_features
                WHERE circle_name = ?
                  AND (? = 'All' OR age_band = ?)
                  AND (? = 'All' OR connection_type = ?)
                GROUP BY tenure_years
                ORDER BY tenure_years
                """
                df_c7 = q(sql_c7, (selected_circle, c7_age, c7_age, c7_conn, c7_conn))

                if not df_c7.empty:
                    max_subs = df_c7['total_subs'].max() if not df_c7.empty else 1
                    sizes = [max(16, int((s / max_subs) * 38)) for s in df_c7['total_subs']]

                    fig_c7 = go.Figure()
                    fig_c7.add_hline(
                        y=NATIONAL_BENCHMARK, line_dash="dash", line_color=AIRTEL_RED, line_width=1.5,
                        annotation_text="National Ref: 23.75%", annotation_position="top right",
                        annotation_font_size=10, annotation_font_color=AIRTEL_RED, annotation_font_family="Arial Black"
                    )

                    fig_c7.add_trace(go.Scatter(
                        x=df_c7['avg_arpu'],
                        y=df_c7['churn_rate'],
                        mode="markers+text",
                        text=[f"<b>Yr {int(y)}</b><br>{float(r):.1f}%" for y, r in zip(df_c7['tenure_years'], df_c7['churn_rate'])],
                        textposition="top center",
                        textfont=dict(size=10.5, color="#0F172A", family="Arial Black"),
                        marker=dict(
                            size=sizes,
                            color=df_c7['churn_rate'],
                            colorscale="Reds",
                            cmin=15,
                            cmax=40,
                            showscale=False,
                            line=dict(color=NAVY_DARK, width=2)
                        ),
                        customdata=df_c7[['total_subs', 'churned_subs']],
                        hovertemplate="<b>Tenure: Year %{text}</b><br>Average ARPU: ₹%{x:.1f}<br>Churn Rate: <b>%{y:.2f}%</b><br>Subscribers: %{customdata[0]:,}<br>Leavers: %{customdata[1]:,}<extra></extra>"
                    ))

                    c7_max = df_c7['churn_rate'].max() if not df_c7.empty else None
                    c7_upper = max(42.0, float(c7_max * 1.30) if pd.notna(c7_max) else 42.0)

                    fig_c7.update_layout(
                        title=dict(text=f"<b>Scope:</b> {c7_age} | {c7_conn}", font=dict(size=10, color=SLATE_GRAY)),
                        xaxis=dict(title=dict(text="<b>Average ARPU (₹)</b>", font=dict(size=10, color="#0F172A", family="Arial Black")), tickfont=dict(size=9.5, family="Arial Black", color="#0F172A")),
                        yaxis=dict(title=dict(text="<b>Churn Rate (%)</b>", font=dict(size=10, color="#0F172A", family="Arial Black")), range=[0, c7_upper], ticksuffix="%", tickfont=dict(size=9.5, family="Arial Black", color="#0F172A")),
                        height=DYN_CHART_H,
                        margin=dict(l=55, r=20, t=25, b=45),
                        plot_bgcolor="#FFFFFF",
                        paper_bgcolor="#FFFFFF",
                        transition={'duration': 500, 'easing': 'cubic-in-out'},
                        hoverlabel=dict(bgcolor="#0B132B", font_size=11.5)
                    )
                    st.plotly_chart(fig_c7, use_container_width=True)
                else:
                    st.info("No records match.")

    # --------------------------------------------------------------------------
    # SUB-TAB 3: CHART 8 — SUBSCRIBER ATTRITION WATERFALL BRIDGE
    # --------------------------------------------------------------------------
    with det_tab_waterfall:
        with st.container(border=True):
            st.markdown(f"""
            <div class="chart-header-banner">
              <div>
                <div class="chart-name-title" style="color:#FFFFFF !important;">
                  <span style="color:#FFFFFF !important; font-size:0.86rem; font-weight:800; letter-spacing:0.2px; text-shadow:0 1px 3px rgba(0,0,0,0.8);">CHART 8: SUBSCRIBER ATTRITION WATERFALL BRIDGE</span>
                </div>
                <div class="chart-subtitle-scope" style="color:#CBD5E1 !important; font-size:0.72rem; font-weight:600; text-shadow:0 1px 2px rgba(0,0,0,0.6);">
                  Waterfall Bridge · Base to leaver attrition step flow in {selected_circle}
                </div>
              </div>
              <span class="chart-type-tag">WATERFALL BRIDGE</span>
            </div>
            """, unsafe_allow_html=True)

            c8_f1, c8_f2 = st.columns(2)
            with c8_f1:
                c8_conn = st.selectbox("📶 Connection Scope (C8)", OPT_CONNS, key="c8_filter_conn")
            with c8_f2:
                c8_device = st.selectbox("📱 Device Type Scope (C8)", OPT_DEVICES, key="c8_filter_dev")

            sql_c8 = """
            SELECT 
                tenure_years,
                COUNT(DISTINCT customer_id) AS total_subs,
                COUNT(DISTINCT CASE WHEN is_churned = 1 THEN customer_id END) AS leavers
            FROM customer_features
            WHERE circle_name = ?
              AND (? = 'All' OR connection_type = ?)
              AND (? = 'All' OR device_type = ?)
            GROUP BY tenure_years
            ORDER BY tenure_years
            """
            df_c8 = q(sql_c8, (selected_circle, c8_conn, c8_conn, c8_device, c8_device))

            if not df_c8.empty:
                tot_circle_subs = int(df_c8['total_subs'].sum())
                total_leavers = int(df_c8['leavers'].sum())
                retained_base = tot_circle_subs - total_leavers

                measures = ["absolute"] + ["relative"] * len(df_c8) + ["total"]
                x_labels = ["Base Base"] + [f"Yr {int(y)} Loss" for y in df_c8['tenure_years']] + ["Retained Base"]
                y_values = [tot_circle_subs] + [-int(v) for v in df_c8['leavers']] + [0]
                text_values = [f"<b>{tot_circle_subs:,}</b>"] + [f"<b>-{int(v):,}</b>" for v in df_c8['leavers']] + [f"<b>{retained_base:,}</b>"]

                fig_c8 = go.Figure(go.Waterfall(
                    name="Attrition Waterfall",
                    orientation="v",
                    measure=measures,
                    x=x_labels,
                    y=y_values,
                    text=text_values,
                    textposition="outside",
                    textfont=dict(size=11, family="Arial Black", color="#0F172A"),
                    connector={"line": {"color": SLATE_GRAY, "width": 1.5}},
                    decreasing={"marker": {"color": AIRTEL_RED}},
                    increasing={"marker": {"color": "#10B981"}},
                    totals={"marker": {"color": NAVY_DARK}}
                ))

                fig_c8.update_layout(
                    title=dict(text=f"<b>Scope:</b> {c8_conn} | {c8_device}", font=dict(size=10, color=SLATE_GRAY)),
                    xaxis=dict(tickfont=dict(size=10, family="Arial Black", color="#0F172A")),
                    yaxis=dict(title=dict(text="<b>Subscriber Count</b>", font=dict(size=10.5, color="#0F172A", family="Arial Black")), tickfont=dict(size=9.5, family="Arial Black", color="#0F172A")),
                    height=DYN_CHART_H,
                    margin=dict(l=65, r=20, t=25, b=45),
                    plot_bgcolor="#FFFFFF",
                    paper_bgcolor="#FFFFFF",
                    transition={'duration': 500, 'easing': 'cubic-in-out'},
                    hoverlabel=dict(bgcolor="#0B132B", font_size=11.5)
                )
                st.plotly_chart(fig_c8, use_container_width=True)
            else:
                st.info("No records match.")

    st.markdown(f"""
    <div class="executive-insight-bar">
      <span class="insight-pill">CIRCLE INSIGHT</span>
      <span><b>Operational Diagnostic for {selected_circle}:</b> Unresolved customer service tickets strongly correlate with attrition ({c_open_pct:.1f}% affected subscribers). Expediting service escalation resolution remains the immediate operational lever.</span>
    </div>
    """, unsafe_allow_html=True)

# ==============================================================================
# 6. FOOTER & ACADEMIC AUDIT SIGN-OFF (COMPACT 1-LINE)
# ==============================================================================
st.caption("Bharti Airtel Enterprise Analytics | Group 1 · Audited Base: `airtel.db` (22,000 subscribers, 408,089 records) · National Churn Benchmark: 23.75%")
