import pandas as pd
import geopandas as gpd
from rapidfuzz import process, fuzz
import fiona
import os
import warnings
warnings.filterwarnings('ignore')

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE = r"C:\Users\annam\PyCharmMiscProject\SARADI\data"
RAW  = os.path.join(BASE, "raw")

DAMS_CLEANED         = os.path.join(BASE, "dams_cleaned.csv")
DAMPOINTS_SHP     = os.path.join(RAW, "DamPoints", "DamPoints.shp")
DAMWATERSHEDS_SHP = os.path.join(RAW, "DamWatersheds", "DamWatersheds.shp")
INUNDATION_SHP    = os.path.join(RAW, "InundationZones", "inundation_zones_dslv.shp")
SVI_GDB           = os.path.join(RAW, "SVI", "SVI2022_VIRGINIA_tract.gdb")
OUTPUT_CSV        = os.path.join(BASE, "dams_dcr_svi_integrated_v3.csv")

FUZZY_THRESHOLD = 85

# ── Helper functions ──────────────────────────────────────────────────────────
def norm_name(s):
    return str(s).upper().strip() if pd.notna(s) else ""

def norm_county(s):
    return str(s).upper().strip().replace(" COUNTY", "") if pd.notna(s) else ""

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Load dams.csv — preserve ALL original columns
# ══════════════════════════════════════════════════════════════════════════════
print("=" * 60)
print("STEP 1: Loading dams.csv")
print("=" * 60)
dams = pd.read_csv(DAMS_CLEANED, low_memory=False)
original_cols = list(dams.columns)
print(f"  Loaded: {len(dams)} dams, {len(dams.columns)} columns")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Join DCR DamPoints
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("STEP 2: Joining DCR DamPoints")
print("=" * 60)

dp = gpd.read_file(DAMPOINTS_SHP)
print(f"  Loaded: {len(dp)} DCR dam points")

# Select only useful columns
wanted_dp = [
    'DamName', 'County', 'damid', 'LegacyNumb', 'HazardClas',
    'LastInspCo', 'EP_Type', 'EP_Status', 'EP_Expirat',
    'CertStatus', 'CertType', 'Regulated', 'TopHeight',
    'TopCapacit', 'StructureC', 'LastInspDa', 'StudyType',
    'DSRegion', 'IS_Status'
]
wanted_dp = [c for c in wanted_dp if c in dp.columns]
dp = dp[wanted_dp].copy()

# Rename DCR columns with prefix
rename_dp = {c: f"DCR_{c}" for c in wanted_dp
             if c not in ['DamName', 'County', 'damid', 'LegacyNumb']}
dp.rename(columns=rename_dp, inplace=True)

# Normalize names and counties
dams['_name_norm']   = dams['Dam Name'].apply(norm_name)
dams['_county_norm'] = dams['County'].apply(norm_county)
dp['_name_norm']     = dp['DamName'].apply(norm_name)
dp['_county_norm']   = dp['County'].apply(norm_county)

# -- Exact match --
print("\n  Exact matching on name + county...")
exact = dams.merge(dp, on=['_name_norm', '_county_norm'], how='left', suffixes=('', '_dcr'))

# Fix: deduplicate — keep first match per NID ID to avoid extra rows
exact = exact.drop_duplicates(subset=['NID ID'], keep='first')

exact_matched = exact['damid'].notna()
matched_df    = exact[exact_matched].copy()
matched_df['DCR_match_type'] = 'exact'

unmatched_df  = dams[~dams['NID ID'].isin(matched_df['NID ID'])].copy()
print(f"  Exact matches:   {len(matched_df)} / {len(dams)}")
print(f"  Unmatched:       {len(unmatched_df)}")

# Add blank DCR columns to unmatched
dcr_cols = [c for c in matched_df.columns
            if c not in dams.columns and c not in ['DCR_match_type', '_name_norm', '_county_norm']]
for c in dcr_cols:
    unmatched_df[c] = None
unmatched_df['DCR_match_type'] = 'no_match'

# -- Fuzzy match --
print(f"\n  Fuzzy matching {len(unmatched_df)} unmatched dams (threshold >= {FUZZY_THRESHOLD})...")
dp_by_county = dp.groupby('_county_norm')
fuzzy_rows   = []

for _, row in unmatched_df.iterrows():
    county     = row['_county_norm']
    name       = row['_name_norm']
    result_row = row.copy()
    result_row['DCR_match_type']    = 'no_match'
    result_row['DCR_fuzzy_score']   = None
    result_row['DCR_fuzzy_matched'] = None

    if county in dp_by_county.groups:
        candidates_df   = dp_by_county.get_group(county)
        candidate_names = candidates_df['_name_norm'].tolist()
        match = process.extractOne(name, candidate_names, scorer=fuzz.token_sort_ratio)

        if match and match[1] >= FUZZY_THRESHOLD:
            dcr_row = candidates_df[candidates_df['_name_norm'] == match[0]].iloc[0]
            for col in dcr_cols:
                if col in dcr_row.index:
                    result_row[col] = dcr_row[col]
            result_row['DCR_match_type']    = 'fuzzy_review'
            result_row['DCR_fuzzy_score']   = round(match[1], 1)
            result_row['DCR_fuzzy_matched'] = dcr_row['DamName']

    fuzzy_rows.append(result_row)

fuzzy_df        = pd.DataFrame(fuzzy_rows)
fuzzy_matched   = fuzzy_df[fuzzy_df['DCR_match_type'] == 'fuzzy_review']
fuzzy_unmatched = fuzzy_df[fuzzy_df['DCR_match_type'] == 'no_match']
print(f"  Fuzzy matches:   {len(fuzzy_matched)}")
print(f"  No match:        {len(fuzzy_unmatched)}")

# Add fuzzy audit columns to matched_df
for col in ['DCR_fuzzy_score', 'DCR_fuzzy_matched']:
    if col not in matched_df.columns:
        matched_df[col] = None

# Combine all three groups
combined = pd.concat([matched_df, fuzzy_matched, fuzzy_unmatched], ignore_index=True)

# Clean up temp columns
combined.drop(columns=['_name_norm', '_county_norm', 'DamName_dcr', 'County_dcr'],
              inplace=True, errors='ignore')

# Verify row count
print(f"\n  Final row count: {len(combined)} (should be {len(dams)})")
print(f"    exact:         {(combined['DCR_match_type']=='exact').sum()}")
print(f"    fuzzy_review:  {(combined['DCR_match_type']=='fuzzy_review').sum()}")
print(f"    no_match:      {(combined['DCR_match_type']=='no_match').sum()}")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 3: Join DCR DamWatersheds via LegacyNumber
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("STEP 3: Joining DCR DamWatersheds")
print("=" * 60)

ws = gpd.read_file(DAMWATERSHEDS_SHP)
print(f"  Loaded: {len(ws)} watershed features")

legacy_col = [c for c in ws.columns if 'legacy' in c.lower()]
if legacy_col:
    lc = legacy_col[0]
    ws_slim = ws[[lc, 'SqMi']].copy()
    ws_slim = ws_slim.rename(columns={lc: '_ws_legacy', 'SqMi': 'DCR_Watershed_SqMi'})
    ws_slim['_ws_legacy'] = ws_slim['_ws_legacy'].astype(str).str.strip().str.lstrip('0')

    legacy_dcr = [c for c in combined.columns if 'legacynumb' in c.lower()]
    if legacy_dcr:
        ldc = legacy_dcr[0]
        combined['_legacy_norm'] = combined[ldc].astype(str).str.strip().str.lstrip('0')
        combined = combined.merge(ws_slim, left_on='_legacy_norm', right_on='_ws_legacy', how='left')
        combined.drop(columns=['_legacy_norm', '_ws_legacy'], inplace=True, errors='ignore')
        print(f"  Watersheds joined: {combined['DCR_Watershed_SqMi'].notna().sum()} dams")
    else:
        print("  WARNING: No LegacyNumb column found — skipping")
        combined['DCR_Watershed_SqMi'] = None
else:
    print("  WARNING: No legacy column in DamWatersheds — skipping")
    combined['DCR_Watershed_SqMi'] = None

# ══════════════════════════════════════════════════════════════════════════════
# STEP 4: Spatial overlay — InundationZones x SVI (geometry only, no Inund_ attributes)
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("STEP 4: Spatial overlay InundationZones x SVI")
print("=" * 60)

# Load inundation zones (geometry + damid only)
inund = gpd.read_file(INUNDATION_SHP)
print(f"  Loaded: {len(inund)} inundation zone features")

damid_col = [c for c in inund.columns if 'damid' in c.lower()]
if not damid_col:
    print("  ERROR: No damid column in InundationZones — cannot do SVI overlay")
else:
    dc = damid_col[0]
    # Keep only damid + geometry for the overlay
    inund_geo = inund[[dc, 'geometry']].copy()

    # Load SVI GDB
    layers    = fiona.listlayers(SVI_GDB)
    svi_layer = [l for l in layers if 'tract' in l.lower()]
    svi_layer = svi_layer[0] if svi_layer else layers[0]
    print(f"  SVI layer: {svi_layer}")

    svi = gpd.read_file(SVI_GDB, layer=svi_layer)
    print(f"  Loaded: {len(svi)} SVI tracts")

    # Keep only needed SVI columns
    svi_keep = ['FIPS', 'E_TOTPOP', 'RPL_THEMES', 'RPL_THEME1', 'RPL_THEME2',
                'RPL_THEME3', 'RPL_THEME4', 'E_POV150', 'E_AGE65',
                'E_DISABL', 'E_NOVEH', 'geometry']
    svi_keep = [c for c in svi_keep if c in svi.columns]
    svi      = svi[svi_keep].copy()

    # Match CRS
    if inund_geo.crs != svi.crs:
        print(f"  Reprojecting SVI from {svi.crs} to {inund_geo.crs}")
        svi = svi.to_crs(inund_geo.crs)

    # Use projected CRS for area calculation
    projected_crs = "EPSG:32618"  # UTM Zone 18N — correct for Virginia
    inund_proj    = inund_geo.to_crs(projected_crs)
    svi_proj      = svi.to_crs(projected_crs)

    # Spatial overlay
    print("  Running spatial overlay (this may take 1-2 minutes)...")
    overlay = gpd.overlay(inund_proj, svi_proj, how='intersection')
    overlay['intersect_area'] = overlay.geometry.area
    print(f"  Overlay produced {len(overlay)} intersection features")

    # Filter out -999 SVI values (CDC uses -999 for missing data)
    for col in ['RPL_THEMES', 'RPL_THEME1', 'RPL_THEME2', 'RPL_THEME3', 'RPL_THEME4']:
        if col in overlay.columns:
            overlay[col] = overlay[col].where(overlay[col] >= 0, other=None)

    # Aggregate per dam
    print("  Aggregating SVI stats per dam...")

    def agg_svi(g):
        total_area = g['intersect_area'].sum()
        result     = {}

        result['SVI_TotalPop_InZone'] = int(g['E_TOTPOP'].sum()) if 'E_TOTPOP' in g else None

        for col, out in [('RPL_THEMES', 'SVI_Avg_RPL_THEMES'),
                         ('RPL_THEME1', 'SVI_Avg_RPL_THEME1'),
                         ('RPL_THEME2', 'SVI_Avg_RPL_THEME2'),
                         ('RPL_THEME3', 'SVI_Avg_RPL_THEME3'),
                         ('RPL_THEME4', 'SVI_Avg_RPL_THEME4')]:
            if col in g.columns:
                valid = g[g[col].notna()]
                if len(valid) > 0 and valid['intersect_area'].sum() > 0:
                    result[out] = round(
                        (valid[col] * valid['intersect_area']).sum() /
                        valid['intersect_area'].sum(), 4)
                else:
                    result[out] = None
            else:
                result[out] = None

        for col, out in [('E_POV150', 'SVI_Pop_POV150'),
                         ('E_AGE65',  'SVI_Pop_AGE65'),
                         ('E_DISABL', 'SVI_Pop_DISABL'),
                         ('E_NOVEH',  'SVI_Pop_NOVEH')]:
            result[out] = int(g[col].sum()) if col in g.columns else None

        return pd.Series(result)

    agg = overlay.groupby(dc).apply(agg_svi).reset_index()
    print(f"  SVI aggregated for {len(agg)} dams")
    print(f"  SVI_Avg_RPL_THEMES non-null: {agg['SVI_Avg_RPL_THEMES'].notna().sum()}")

    # Join to combined
    combined['damid']  = pd.to_numeric(combined['damid'], errors='coerce')
    agg[dc]            = pd.to_numeric(agg[dc], errors='coerce')
    combined           = combined.merge(agg, left_on='damid', right_on=dc, how='left')
    if dc != 'damid':
        combined.drop(columns=[dc], inplace=True, errors='ignore')

    print(f"  SVI joined: {combined['SVI_TotalPop_InZone'].notna().sum()} dams")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 5: Final cleanup
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("STEP 5: Final cleanup")
print("=" * 60)

# Drop all Inund_ columns — redundant
inund_cols = [c for c in combined.columns if c.startswith('Inund_')]
combined.drop(columns=inund_cols, inplace=True, errors='ignore')
print(f"  Dropped {len(inund_cols)} redundant Inund_ columns")

# Verify all original columns are present
missing_orig = [c for c in original_cols if c not in combined.columns]
if missing_orig:
    print(f"  WARNING: These original columns are missing: {missing_orig}")
else:
    print(f"  All {len(original_cols)} original columns preserved")

# Final row count check
print(f"  Final rows: {len(combined)} (original: {len(dams)})")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 6: Save output
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("STEP 6: Saving output")
print("=" * 60)

combined.to_csv(OUTPUT_CSV, index=False)
print(f"  Saved: {OUTPUT_CSV}")
print(f"  Final shape: {combined.shape}")

# Summary of new columns
new_cols = [c for c in combined.columns if c not in original_cols]
print(f"\n  New columns added ({len(new_cols)}):")
for c in new_cols:
    non_null = combined[c].notna().sum()
    print(f"    {c:40s} {non_null} / {len(combined)} non-null")

print("\nDone.")