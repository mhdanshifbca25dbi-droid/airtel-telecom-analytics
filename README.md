# Airtel Telecom Analytics — Enterprise Retention Intelligence
### BCA Data Science & Telecom Analytics · Domain A: Customer Retention Intelligence Dashboard

[![Python](https://img.shields.io/badge/Python-3.13-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.67.0-FF4B4B.svg)](https://streamlit.io/)
[![Plotly](https://img.shields.io/badge/Plotly-7.1.0-3F4F75.svg)](https://plotly.com/)
[![SQLite](https://img.shields.io/badge/SQLite-airtel.db-003B57.svg)](https://www.sqlite.org/)

---

## 1. Executive Problem Statement
Bharti Airtel faces an ongoing challenge in customer retention: losing nearly one subscriber in four (**23.75% national baseline churn rate** across 22,000 audited subscribers). The goal of this intelligence platform is to enable the **Head of Retention** to:
1. Identify high-risk subscriber segments before they abandon the network or port out (MNP).
2. Quantify behavioral churn drivers (recharge frequency decay, customer service ticket escalation, prepaid vulnerability).
3. Validate operational interventions using rigorous statistical hypothesis testing (Welch's t-test, Two-proportion Z-test).

---

## 2. Advanced Retention Dashboard Architecture

The dashboard is built with **Streamlit**, **Plotly**, and **SQLite**, structured into two complementary intelligence tiers:

### Tab 1: OVERVIEW — Executive Macro View
- **Executive KPI Cards (1 Row):**
  - **Total Subscribers:** Validated fixed base of 22,000 subscribers (16,774 Retained / 5,226 Churned; 23.75% National Baseline).
  - **T4 Statistical Validation:** Welch's independent-samples t-test on active rechargers ($t = -42.32, p < 0.001$, two-tailed, Reject $H_0$, difference = -₹1,407.87 active revenue).
  - **Filtered Churn:** Executive scope metric tracking churn rate, leaver count ($k$), subscriber denominator ($N$), and variance vs the 23.75% benchmark.
- **Independent Visualisations:**
  - **Chart 1 — Churn by Tenure (Lollipop Chart):** Custom stem-and-marker visualization showing churn decay across tenure bands (Year 0 to Year 3) with independent Region, Connection, and Tenure filters.
  - **Chart 2 — Prepaid vs Postpaid Churn (Vertical Column Chart):** Comparing Prepaid (25.90% churn) against Postpaid (16.18% churn) with independent Region and Age Band filters.
  - **Chart 3 — Churn by Circle Ranking (Horizontal Ranked Bar Chart):** Dynamic ranking of all 22 circles against the 23.75% benchmark with independent Region, Connection, and Sort Order filters.

### Tab 2: DETAIL — Circle Explorer & Cohort Drilldown
- **Circle Selector Bar:** Interactive target circle dropdown (e.g. *Maharashtra*, *Himachal Pradesh*, *Delhi*) with real-time KPI card highlighting subscriber base, ARPU, leavers, and local churn delta.
- **Deep-Dive Analytical Charts:**
  - **Chart 4 — Open Ticket Analysis:** Evaluating customer service ticket resolution impact (Open tickets carry 27.5% - 38.3% churn risk) with independent Ticket Status and Connection filters.
  - **Chart 5 — Monthly Leavers Trend:** Area-filled time-series visualization tracking attrition cadence (Jan–Jun 2025) with Quarter and Connection filters.
  - **Chart 6 — Tenure Cohort Churn within Circle:** Discrete tenure band risk breakdown for the selected circle.
  - **Chart 7 — Cross-Cohort Churn Heatmap:** 2D matrix mapping Customer Tenure Years against Age Bands to identify hyper-vulnerable demographic cohorts.

---

## 3. Critical Filter Independence Rule

Each chart is engineered with **separate, independent Streamlit filters and unique widget keys**:
- Changing Chart 1 filters (`c1_tenure_region`, `c1_tenure_conn`) modifies **only Chart 1**.
- Changing Chart 2 filters (`c2_pre_post_region`, `c2_pre_post_age`) modifies **only Chart 2**.
- Changing Chart 3 filters (`c3_circle_region`, `c3_circle_conn`) modifies **only Chart 3**.
- Every chart dynamically updates its header title with its active filter state.
- All filters query actual database values and leverage parameterized SQL queries to prevent SQL injection.

---

## 4. Database Setup & SQL Architecture

The platform operates directly against the master SQLite database:
- **Database Location:** `data/raw/airtel.db` (123.7 MB, ~408k recharges, 22k customer profiles)
- **Primary Analysis Table:** `customer_features` (41 validated attributes per subscriber)
- **National Benchmark:** `23.75%` (5,226 churned / 22,000 total subscribers)

---

## 5. How to Run the Dashboard

### Prerequisites
Ensure Python 3.10+ is installed with project dependencies:
```bash
pip install -r requirements.txt
```

### Launch Command
Run the Streamlit application from the project root:
```bash
streamlit run dashboard/app.py
```
Open your browser at `http://localhost:8501`.

---

## 6. Project Directory Structure

```text
airtel-telecom-analytics/
├── data/
│   ├── raw/
│   │   └── airtel.db             # Master SQLite relational database
│   ├── processed/
│   └── practice/
├── dashboard/
│   ├── app.py                    # Main Streamlit dashboard application
│   └── assets/
│       ├── style.css             # Airtel custom CSS & animations
│       └── telecom_bg.svg        # Abstract telecom network background
├── notebooks/
│   ├── 00_verify_handover.ipynb
│   ├── 01_sql_toolkit.ipynb
│   ├── 02_understanding.ipynb
│   ├── 04_preparation.ipynb
│   ├── 05_analysis.ipynb
│   ├── 06_validation.ipynb
│   └── 07_Validation.ipynb       # Assignment 07 Statistical Validation
├── reports/
│   ├── figures/                  # Publication-quality charts (PNG)
│   ├── 07_Validation_Summary.xlsx # Comprehensive statistical test matrix
│   └── 07_Validation_Conclusion.pdf # Executive business conclusion report
├── requirements.txt              # Environment dependencies
└── README.md                     # Project documentation
```

---

## 7. Version Control & Submission

To commit and preserve dashboard deliverables:
```bash
git add dashboard/ requirements.txt README.md
git commit -m "Add premium retention intelligence dashboard with independent filters"
```
*(Do not push to remote without instructor guidance).*
