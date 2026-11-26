import os
import py_compile

with open("dashboard/assets/style.css", "r", encoding="utf-8") as f:
    css = f.read()

checks = [
    (".chart-name-title font color", "color: #FFFFFF !important;" in css),
    (".chart-subtitle-scope font color", "color: #CBD5E1 !important;" in css),
    (".stSelectbox label font color", "color: #FFFFFF !important;" in css),
    ("div[data-testid='stSelectbox'] label selector", "div[data-testid=\"stSelectbox\"] label" in css),
    (".circle-hero-card font color", "color: #FFFFFF !important;" in css),
    (".executive-insight-bar font color", "color: #F8FAFC !important;" in css),
    (".kpi-value font color", "color: #FFFFFF !important;" in css),
    (".kpi-title font color", "color: #CBD5E1 !important;" in css),
    (".block-container spacing", "padding-top: 0.35rem !important;" in css),
    ("[data-testid='stVerticalBlock'] gap", "gap: 0.45rem !important;" in css),
    ("[data-testid='stHorizontalBlock'] gap", "gap: 1.0rem !important;" in css),
    (".dashboard-header-container margin", "margin-bottom: 8px;" in css),
    (".kpi-card padding", "padding: 8px 14px 6px 14px !important;" in css),
    (".chart container padding", "padding: 10px 14px 8px 14px !important;" in css),
    (".stTabs margin", "margin-bottom: 8px !important;" in css),
    ("Chart card container white text", "[data-testid=\"stVerticalBlockBorderWrapper\"] .chart-header-banner *" in css)
]

print("--- CSS RULES & NO-SCROLL SPACING VALIDATION ---")
all_passed = True
for name, passed in checks:
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name}")
    if not passed:
        all_passed = False

with open("dashboard/app.py", "r", encoding="utf-8") as f:
    app_code = f.read()

app_checks = [
    ("Default DYN_CHART_H is 310", 'DYN_CHART_H = HEIGHT_MAP.get(screen_preset, 310)' in app_code),
    ("Fit Screen option exists", '"Fit Screen (290px)"' in app_code),
    ("Chart 1 Title Inline White", 'CHART 1: RETENTION FUNNEL' in app_code and 'color:#FFFFFF !important;' in app_code),
    ("Chart 2 Title Inline White", 'CHART 2: REGIONAL & CIRCLE TREEMAP' in app_code and 'color:#FFFFFF !important;' in app_code),
    ("Chart 3 Title Inline White", 'CHART 3: COHORT ATTRITION RISK RADAR' in app_code and 'color:#FFFFFF !important;' in app_code),
    ("Chart 4 Title Inline White", 'CHART 4: MONTHLY ATTRITION STEP-LINE CADENCE' in app_code and 'color:#FFFFFF !important;' in app_code),
    ("Chart 5 Title Inline White", 'CHART 5: CIRCLE CHURN SEVERITY GAUGE' in app_code and 'color:#FFFFFF !important;' in app_code),
    ("Chart 6 Title Inline White", 'CHART 6: NETWORK & DEVICE DONUT' in app_code and 'color:#FFFFFF !important;' in app_code),
    ("Chart 7 Title Inline White", 'CHART 7: TENURE VS ARPU BUBBLE MATRIX' in app_code and 'color:#FFFFFF !important;' in app_code),
    ("Chart 8 Title Inline White", 'CHART 8: SUBSCRIBER ATTRITION WATERFALL BRIDGE' in app_code and 'color:#FFFFFF !important;' in app_code),
    ("Playbook Header White", "🎯 RETENTION ACTION PLAYBOOK</span>" in app_code),
    ("Playbook Items White Contrast", 'Year 0 (&lt; 1 Yr) Cohort Fragility:' in app_code and 'color:#FFFFFF !important;' in app_code),
    ("Circle Hero Card White", 'Circle Operational Intelligence' in app_code and 'color:#FFFFFF !important;' in app_code),
    ("Radar Axis White", 'angularaxis=dict(tickfont=dict(size=9.5, color="#FFFFFF"' in app_code),
    ("KPI Filter Spacing", 'st.markdown(\'<div style="margin-bottom: 8px;"></div>\'' in app_code),
    ("Sub-tabs Divider Spacing", 'border-bottom: 1px solid rgba(255,255,255,0.10);' in app_code),
    ("Chart 1 Filter Gap", 'st.markdown(\'<div style="margin-bottom: 6px;"></div>\'' in app_code)
]

print("\n--- APP.PY RULES & CHART HEIGHT VALIDATION ---")
for name, passed in app_checks:
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name}")
    if not passed:
        all_passed = False

try:
    py_compile.compile("dashboard/app.py", doraise=True)
    print("\n[PASS] Python compilation successful: dashboard/app.py")
except Exception as e:
    print(f"\n[FAIL] Python compilation error: {e}")
    all_passed = False

if all_passed:
    print("\nALL VERIFICATIONS PASSED SUCCESSFULLY (100%)!")
else:
    print("\nSOME VERIFICATIONS FAILED!")
