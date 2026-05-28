import pandas as pd
import geopandas as gpd
import os
import warnings
warnings.filterwarnings('ignore')

BASE          = r"C:\Users\annam\PyCharmMiscProject\SARADI\data"
INPUT         = os.path.join(BASE, "dams_dcr_svi_integrated_v3.csv")
DAMPOINTS_SHP = os.path.join(BASE, "raw", "DamPoints", "DamPoints.shp")
OUTPUT        = os.path.join(BASE, "dams_dcr_svi_integrated_v4.csv")

# ── Load base file ────────────────────────────────────────────────────────────
print("Loading v3...")
df = pd.read_csv(INPUT, low_memory=False)
print(f"  Loaded: {df.shape}")

# ── Add DCR_EP_Status from DamPoints via damid ────────────────────────────────
print("\nAdding DCR_EP_Status from DamPoints...")
dp = gpd.read_file(DAMPOINTS_SHP)

if 'EP_Status' in dp.columns and 'damid' in dp.columns:
    ep = dp[['damid', 'EP_Status']].copy()
    ep = ep.rename(columns={'EP_Status': 'DCR_EP_Status'})
    ep['damid'] = pd.to_numeric(ep['damid'], errors='coerce')
    ep = ep.drop_duplicates(subset=['damid'], keep='first')
    df['damid'] = pd.to_numeric(df['damid'], errors='coerce')
    df = df.merge(ep, on='damid', how='left')
    print(f"  DCR_EP_Status non-null: {df['DCR_EP_Status'].notna().sum()} / {len(df)}")
    print(f"  Values:")
    for k, v in df['DCR_EP_Status'].value_counts(dropna=False).items():
        print(f"    {str(k):25s} {v}")
else:
    print("  WARNING: EP_Status or damid not found — skipping")
    df['DCR_EP_Status'] = None

# ── Helpers ───────────────────────────────────────────────────────────────────
NOT_VALID = ['', '<null>', 'nan', 'none']
NOT_RATED = ['not rated', 'not available', '<null>', 'nan', 'none', '',
             'undetermined', 'unknown']

def is_valid(val):
    return pd.notna(val) and str(val).strip().lower() not in NOT_VALID

def is_rated(val):
    return pd.notna(val) and str(val).strip().lower() not in NOT_RATED

# ── Inspection_Date_Final ─────────────────────────────────────────────────────
print("\nCreating Inspection_Date_Final...")

def unify_date(row):
    dcr = row['DCR_LastInspDa']
    nid = row['Last Inspection Date']
    if is_valid(dcr):
        return str(dcr)
    elif is_valid(nid):
        return str(nid)
    else:
        return None

df['Inspection_Date_Final'] = df.apply(unify_date, axis=1)
print(f"  Non-null:        {df['Inspection_Date_Final'].notna().sum()} / {len(df)}")
print(f"  Never inspected: {df['Inspection_Date_Final'].isna().sum()}")

# ── Condition_Final ───────────────────────────────────────────────────────────
print("\nCreating Condition_Final...")

def unify_condition(row):
    dcr = row['DCR_LastInspCo']
    nid = row['Condition Assessment']
    if is_rated(dcr):
        return str(dcr)
    elif is_rated(nid):
        return str(nid)
    else:
        return 'Not Rated'

df['Condition_Final'] = df.apply(unify_condition, axis=1)
print(f"  Breakdown:")
for k, v in df['Condition_Final'].value_counts().items():
    print(f"    {k:25s} {v}")

# ── Hazard_Final ──────────────────────────────────────────────────────────────
print("\nCreating Hazard_Final...")

def unify_hazard(row):
    dcr = row['DCR_HazardClas']
    nid = row['Hazard Potential Classification']
    if is_rated(dcr):
        return str(dcr)
    elif is_rated(nid):
        return str(nid)
    else:
        return 'Unknown'

df['Hazard_Final'] = df.apply(unify_hazard, axis=1)
print(f"  Breakdown:")
for k, v in df['Hazard_Final'].value_counts().items():
    print(f"    {k:25s} {v}")

# ── Drop redundant columns ────────────────────────────────────────────────────
print("\nDropping redundant columns...")
drop_cols = [
    'Last Inspection Date',
    'Condition Assessment',
    'Condition Assessment Date',
    'Hazard Potential Classification',
    'DCR_LastInspCo',
    'DCR_LastInspDa',
    'DCR_HazardClas',
]
drop_cols = [c for c in drop_cols if c in df.columns]
df.drop(columns=drop_cols, inplace=True)
print(f"  Dropped {len(drop_cols)} columns: {drop_cols}")

# ── Save ──────────────────────────────────────────────────────────────────────
df.to_csv(OUTPUT, index=False)
print(f"\nSaved: {OUTPUT}")
print(f"Final shape: {df.shape}")
print(f"\nFinal columns ({len(df.columns)}):")
for c in df.columns:
    print(f"  {c}")
print("\nDone.")