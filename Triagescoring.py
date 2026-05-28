"""
triage_score.py
SARRDI Project — Step 6: Triage Score 0-100
Final version with 3 fixes applied:
  Fix 1: D2 flood score capped at 75 (graduated, not binary)
  Fix 2: D3 watershed uses percentile normalization (not log min-max)
  Fix 3: Unknown hazard stays at 50 but adds Needs_Hazard_Classification flag

5 dimensions:
  D1 — Hazard Classification        25%
       Hazard_Final + NID Height + NID Storage
  D2 — Flood Zone Exposure          20%
       Fathom 100yr (75pts) + 500yr (40pts) — capped at 75
  D3 — Cascade / Watershed Risk     25%
       Percentile-normalized watershed size
  D4 — Downstream Human Impact      20%
       SVI pop + poverty + elderly + disabled + no vehicle
  D5 — Data Quality & Inspection    10%
       Condition + Inspection gap + EAP + Operational Status + Maps

Input:  dams_dcr_svi_integrated_v5.csv
Output: dams_triage_scored.csv
"""

import warnings
import pandas as pd
import numpy as np
from datetime import datetime

warnings.filterwarnings("ignore")

# ── Config ─────────────────────────────────────────────────────────────────────
INPUT_CSV  = r"C:\Users\annam\PyCharmMiscProject\SARADI\data\dams_dcr_svi_integrated_v5.csv"
OUTPUT_CSV = r"C:\Users\annam\PyCharmMiscProject\SARADI\data\dams_triage_scored.csv"
TODAY      = datetime(2026, 4, 10)


# ── Helpers ────────────────────────────────────────────────────────────────────
def normalize_log(series, fill=50):
    """Log-scale min-max normalize to 0-100."""
    s = pd.to_numeric(series, errors="coerce")
    log_s = np.log1p(s.clip(lower=0))
    mn, mx = log_s.min(), log_s.max()
    if mx == mn:
        return pd.Series(fill, index=series.index)
    return ((log_s - mn) / (mx - mn) * 100).fillna(fill)

def normalize_percentile(series, fill=50):
    """
    FIX 2: Percentile-based normalization.
    Ranks each dam relative to all other dams — dam at 90th percentile
    gets score 90. Robust against outliers unlike log min-max.
    """
    s = pd.to_numeric(series, errors="coerce")
    result = s.rank(pct=True) * 100
    return result.fillna(fill)


# ── Load data ──────────────────────────────────────────────────────────────────
print("Loading data...")
df = pd.read_csv(INPUT_CSV, low_memory=False)
print(f"  {df.shape[0]} rows x {df.shape[1]} columns")


# ══════════════════════════════════════════════════════════════════════════════
# DIMENSION 1 — Hazard Classification (25%)
# Components:
#   A. Hazard_Final        (60%) — official hazard class
#   B. NID Height (Ft)     (25%) — taller dam = more energy = worse failure
#   C. NID Storage (Acre-Ft)(15%) — more water = bigger flood
#
# FIX 3: Unknown hazard = 50 (neutral, not penalized)
#         + Needs_Hazard_Classification flag added separately
# ══════════════════════════════════════════════════════════════════════════════
def score_hazard_class(val):
    if pd.isna(val):
        return 50
    v = str(val).strip().lower()
    if "high" in v:
        return 100
    elif "significant" in v:
        return 67
    elif "low" in v:
        return 33
    else:
        return 50  # Unknown — neutral score, flagged separately

hazard_class  = df["Hazard_Final"].apply(score_hazard_class)
height_score  = normalize_log(df["NID Height (Ft)"], fill=25)
storage_score = normalize_log(df["NID Storage (Acre-Ft)"], fill=25)

df["D1_Hazard_Score"] = (
    0.60 * hazard_class +
    0.25 * height_score +
    0.15 * storage_score
).round(2)

# FIX 3: Flag unclassified dams separately
df["Needs_Hazard_Classification"] = df["Hazard_Final"].apply(
    lambda v: 1 if pd.isna(v) or str(v).strip().lower() in ["unknown", ""] else 0
)

n_unclassified = df["Needs_Hazard_Classification"].sum()
print(f"\nD1 Hazard     — mean: {df['D1_Hazard_Score'].mean():.1f} | "
      f"min: {df['D1_Hazard_Score'].min():.1f} | max: {df['D1_Hazard_Score'].max():.1f}")
print(f"  Unclassified dams flagged: {n_unclassified} ({100*n_unclassified/len(df):.1f}%)")


# ══════════════════════════════════════════════════════════════════════════════
# DIMENSION 2 — Flood Zone Exposure (20%)
# FIX 1: Graduated scale, capped at 75.
#   In 100yr zone = 75 (was 100) — flood zone alone cannot reach Critical
#   In 500yr only = 40 (was 50)
#   Neither       =  0
# This prevents D2 from single-handedly pushing a dam to Critical band.
# ══════════════════════════════════════════════════════════════════════════════
def score_flood(row):
    in_100 = row.get("In Fathom 100yr Flood Zone", 0)
    in_500 = row.get("In Fathom 500yr Flood Zone", 0)
    if in_100 == 1:
        return 75   # FIX 1: was 100
    elif in_500 == 1:
        return 40   # FIX 1: was 50
    else:
        return 0

df["D2_Flood_Score"] = df.apply(score_flood, axis=1)
print(f"D2 Flood      — mean: {df['D2_Flood_Score'].mean():.1f} | "
      f"min: {df['D2_Flood_Score'].min():.1f} | max: {df['D2_Flood_Score'].max():.1f}")


# ══════════════════════════════════════════════════════════════════════════════
# DIMENSION 3 — Cascade / Watershed Risk (25%)
# FIX 2: Percentile normalization instead of log min-max.
#   Ranks each dam relative to all Virginia dams by watershed size.
#   Mean will be ~50 (by definition of percentile rank).
#   No longer crushed by outlier large dams.
# Use DCR_Watershed_SqMi as primary, Drainage Area as fallback.
# ══════════════════════════════════════════════════════════════════════════════
watershed = pd.to_numeric(df["DCR_Watershed_SqMi"], errors="coerce")
drainage  = pd.to_numeric(df["Drainage Area (Sq Miles)"], errors="coerce")
combined_watershed = watershed.fillna(drainage)

df["D3_Watershed_Score"] = normalize_percentile(combined_watershed, fill=50).round(2)
print(f"D3 Watershed  — mean: {df['D3_Watershed_Score'].mean():.1f} | "
      f"min: {df['D3_Watershed_Score'].min():.1f} | max: {df['D3_Watershed_Score'].max():.1f}")


# ══════════════════════════════════════════════════════════════════════════════
# DIMENSION 4 — Downstream Human Impact (20%)
# Components:
#   A. SVI_TotalPop_InZone  (35%) — total population in zone
#   B. SVI_Pop_POV150       (20%) — population in poverty
#   C. SVI_Pop_AGE65        (15%) — elderly population
#   D. SVI_Pop_DISABL       (15%) — disabled population
#   E. SVI_Pop_NOVEH        (15%) — no vehicle (cannot evacuate)
# ══════════════════════════════════════════════════════════════════════════════
df["D4_Impact_Score"] = (
    0.35 * normalize_log(df["SVI_TotalPop_InZone"], fill=0) +
    0.20 * normalize_log(df["SVI_Pop_POV150"],      fill=0) +
    0.15 * normalize_log(df["SVI_Pop_AGE65"],       fill=0) +
    0.15 * normalize_log(df["SVI_Pop_DISABL"],      fill=0) +
    0.15 * normalize_log(df["SVI_Pop_NOVEH"],       fill=0)
).fillna(0).round(2)

print(f"D4 Impact     — mean: {df['D4_Impact_Score'].mean():.1f} | "
      f"min: {df['D4_Impact_Score'].min():.1f} | max: {df['D4_Impact_Score'].max():.1f}")


# ══════════════════════════════════════════════════════════════════════════════
# DIMENSION 5 — Data Quality & Inspection Gap (10%)
# Components:
#   A. Condition_Final        (25%) — structural condition
#   B. Inspection_Date_Final  (25%) — inspection recency
#   C. EAP Prepared           (20%) — emergency action plan exists
#   D. EAP Last Revision Date (15%) — EAP currency
#   E. Operational Status     (10%) — remediation / enforcement flag
#   F. Inundation Maps in NID  (5%) — flood mapping documented
# ══════════════════════════════════════════════════════════════════════════════
def score_condition(val):
    if pd.isna(val): return 75
    v = str(val).strip().lower()
    return {"unsatisfactory":100,"poor":80,"fair":50,
            "satisfactory":20,"not rated":75}.get(v, 75)

def score_inspection_gap(val):
    if pd.isna(val) or str(val).strip() == "": return 100
    try:
        dt = pd.to_datetime(val, errors="coerce")
        if pd.isna(dt): return 100
        years_ago = (TODAY - dt).days / 365.25
        if years_ago >= 10: return 100
        elif years_ago >= 5: return 70
        elif years_ago >= 2: return 40
        else: return 10
    except: return 100

def score_eap_prepared(val):
    if pd.isna(val): return 100
    v = str(val).strip().lower()
    if v == "yes": return 0
    elif v == "not required": return 20
    elif v == "no": return 100
    else: return 80

def score_eap_revision(val):
    if pd.isna(val) or str(val).strip() == "": return 100
    try:
        dt = pd.to_datetime(val, errors="coerce")
        if pd.isna(dt): return 100
        years_ago = (TODAY - dt).days / 365.25
        if years_ago >= 10: return 100
        elif years_ago >= 5: return 60
        elif years_ago >= 2: return 30
        else: return 0
    except: return 100

def score_operational_status(val):
    if pd.isna(val): return 50
    v = str(val).strip().lower()
    if "under remediation" in v: return 100
    elif "enforcement" in v: return 100
    elif "investigation" in v or "planning" in v: return 80
    elif "normal operations" in v: return 0
    else: return 30

def score_inundation_maps(val):
    if pd.isna(val): return 50
    return 0 if str(val).strip().lower() == "yes" else 50

df["D5_DataQuality_Score"] = (
    0.25 * df["Condition_Final"].apply(score_condition) +
    0.25 * df["Inspection_Date_Final"].apply(score_inspection_gap) +
    0.20 * df["EAP Prepared"].apply(score_eap_prepared) +
    0.15 * df["EAP Last Revision Date"].apply(score_eap_revision) +
    0.10 * df["Operational Status"].apply(score_operational_status) +
    0.05 * df["Inundation Maps Added to NID?"].apply(score_inundation_maps)
).round(2)

print(f"D5 DataQuality— mean: {df['D5_DataQuality_Score'].mean():.1f} | "
      f"min: {df['D5_DataQuality_Score'].min():.1f} | max: {df['D5_DataQuality_Score'].max():.1f}")


# ══════════════════════════════════════════════════════════════════════════════
# FINAL TRIAGE SCORE
# ══════════════════════════════════════════════════════════════════════════════
df["Triage_Score"] = (
    0.25 * df["D1_Hazard_Score"] +
    0.20 * df["D2_Flood_Score"] +
    0.25 * df["D3_Watershed_Score"] +
    0.20 * df["D4_Impact_Score"] +
    0.10 * df["D5_DataQuality_Score"]
).round(2)

print(f"\nTriage Score  — mean: {df['Triage_Score'].mean():.1f} | "
      f"min: {df['Triage_Score'].min():.1f} | max: {df['Triage_Score'].max():.1f}")


# ══════════════════════════════════════════════════════════════════════════════
# PRIORITY BAND
# ══════════════════════════════════════════════════════════════════════════════
def assign_band(score):
    if score >= 75:   return "Critical"
    elif score >= 50: return "High"
    elif score >= 25: return "Moderate"
    else:             return "Low"

df["Priority_Band"] = df["Triage_Score"].apply(assign_band)

print("\n--- Priority Band Distribution ---")
print(df["Priority_Band"].value_counts().to_string())

print(f"\n--- Unclassified dams needing hazard assessment: "
      f"{df['Needs_Hazard_Classification'].sum()} ---")


# ══════════════════════════════════════════════════════════════════════════════
# SAVE
# ══════════════════════════════════════════════════════════════════════════════
df.to_csv(OUTPUT_CSV, index=False)
print(f"\nSaved: {OUTPUT_CSV}")
print(f"Final shape: {df.shape[0]} rows x {df.shape[1]} columns")


# ══════════════════════════════════════════════════════════════════════════════
# TOP 20 HIGHEST PRIORITY DAMS
# ══════════════════════════════════════════════════════════════════════════════
print("\n--- Top 20 Highest Priority Dams ---")
top20 = df.nlargest(20, "Triage_Score")[
    ["NID ID", "Dam Name", "County", "Hazard_Final",
     "Triage_Score", "Priority_Band", "Needs_Hazard_Classification",
     "D1_Hazard_Score", "D2_Flood_Score", "D3_Watershed_Score",
     "D4_Impact_Score", "D5_DataQuality_Score"]
]
print(top20.to_string(index=False))


# ══════════════════════════════════════════════════════════════════════════════
# UNCLASSIFIED DAMS NEEDING HAZARD ASSESSMENT
# ══════════════════════════════════════════════════════════════════════════════
print("\n--- Top 20 Unclassified Dams (Needs Hazard Classification) ---")
unclassified = df[df["Needs_Hazard_Classification"] == 1].nlargest(20, "Triage_Score")[
    ["NID ID", "Dam Name", "County", "Triage_Score", "Priority_Band",
     "D2_Flood_Score", "D3_Watershed_Score", "D4_Impact_Score"]
]
print(unclassified.to_string(index=False))