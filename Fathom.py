"""
fathom_integration.py
SARRDI Project — Step 4: Fathom Flood Zone Integration
Logic:
  1. Load Fathom 100yr flood extent shapefile
  2. Load Fathom 500yr flood extent shapefile
  3. Spatial join each dam point to both flood extents
  4. Add binary flags: In_Fathom_100yr_Flood_Zone, In_Fathom_500yr_Flood_Zone
  5. Save to dams_dcr_svi_integrated_v5.csv

These flags feed directly into the Flood Zone Exposure dimension (20% weight).
Scoring:
  - In 100yr zone → Flood Exposure Score = 100
  - In 500yr zone only → Flood Exposure Score = 50
  - In neither zone → Flood Exposure Score = 0
"""

import warnings
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point

warnings.filterwarnings("ignore")

# ── Config ─────────────────────────────────────────────────────────────────────
FATHOM_100_SHP = r"C:\Users\annam\PyCharmMiscProject\SARADI\data\raw\FATHOM-20260410T194928Z-3-001\FATHOM\2020-50_M_Ex_100_VA\2020-50_M_Ex_100_VA.shp"
FATHOM_500_SHP = r"C:\Users\annam\PyCharmMiscProject\SARADI\data\raw\FATHOM-20260410T194928Z-3-001\FATHOM\2020-50_M_Ex_500_VA\2020-50_M_Ex_500_VA.shp"
INPUT_CSV      = r"C:\Users\annam\PyCharmMiscProject\SARADI\data\dams_dcr_svi_integrated_v4.csv"
OUTPUT_CSV     = r"C:\Users\annam\PyCharmMiscProject\SARADI\data\dams_dcr_svi_integrated_v5.csv"


# ── Step 1: Load dams ─────────────────────────────────────────────────────────
print("Loading dam data...")
dams     = pd.read_csv(INPUT_CSV, low_memory=False)
dams_geo = dams.dropna(subset=["Latitude", "Longitude"]).copy()
dams_geo["geometry"] = dams_geo.apply(
    lambda r: Point(r["Longitude"], r["Latitude"]), axis=1
)
dams_gdf = gpd.GeoDataFrame(dams_geo, geometry="geometry", crs="EPSG:4326")
print(f"  {len(dams_gdf)} dams with valid coordinates")


# ── Helper: spatial join dam points to flood polygons ─────────────────────────
def flag_dams_in_flood_zone(dams_gdf, shp_path, label):
    """
    Returns a Series of 1/0 indicating whether each dam falls
    inside any flood polygon in the shapefile.
    """
    print(f"\nLoading {label} flood shapefile (large file, may take a moment)...")
    flood = gpd.read_file(shp_path)
    print(f"  {len(flood)} flood polygons loaded")
    print(f"  CRS: {flood.crs}")

    # Ensure both are in same CRS
    if flood.crs != dams_gdf.crs:
        flood = flood.to_crs(dams_gdf.crs)

    # Keep only geometry — we just need the flood footprint
    flood = flood[["geometry"]].copy()
    flood["_in_zone"] = 1

    print(f"  Joining dams to {label} flood zone...")
    joined = gpd.sjoin(
        dams_gdf[["NID ID", "geometry"]],
        flood,
        how="left",
        predicate="intersects"
    )

    # Drop duplicates — a dam touching multiple polygons counts once
    joined = joined.drop_duplicates(subset=["NID ID"], keep="first")

    # Binary flag: 1 if in zone, 0 if not
    flag = joined.set_index("NID ID")["_in_zone"].fillna(0).astype(int)
    in_zone = flag.sum()
    print(f"  Dams in {label} flood zone: {in_zone}/{len(dams_gdf)} ({100*in_zone/len(dams_gdf):.1f}%)")
    return flag


# ── Step 2: Flag 100yr flood zone ─────────────────────────────────────────────
flag_100 = flag_dams_in_flood_zone(dams_gdf, FATHOM_100_SHP, "100yr")

# ── Step 3: Flag 500yr flood zone ─────────────────────────────────────────────
flag_500 = flag_dams_in_flood_zone(dams_gdf, FATHOM_500_SHP, "500yr")


# ── Step 4: Merge flags back to dams dataframe ────────────────────────────────
print("\nMerging flood zone flags into dam dataset...")

flag_df = pd.DataFrame({
    "NID ID": flag_100.index,
    "In Fathom 100yr Flood Zone": flag_100.values,
    "In Fathom 500yr Flood Zone": flag_500.reindex(flag_100.index).fillna(0).astype(int).values,
})

dams_merged = dams.merge(flag_df, on="NID ID", how="left")

# Fill NaN for dams that had no coordinates
dams_merged["In Fathom 100yr Flood Zone"] = dams_merged["In Fathom 100yr Flood Zone"].fillna(0).astype(int)
dams_merged["In Fathom 500yr Flood Zone"] = dams_merged["In Fathom 500yr Flood Zone"].fillna(0).astype(int)


# ── Step 5: Save ──────────────────────────────────────────────────────────────
dams_merged.to_csv(OUTPUT_CSV, index=False)
print(f"\nSaved: {OUTPUT_CSV}")
print(f"Final shape: {dams_merged.shape[0]} rows x {dams_merged.shape[1]} columns")

# ── Step 6: Summary ───────────────────────────────────────────────────────────
print("\n--- Flood Zone Summary ---")
print(f"In 100yr flood zone: {dams_merged['In Fathom 100yr Flood Zone'].sum()} dams")
print(f"In 500yr flood zone: {dams_merged['In Fathom 500yr Flood Zone'].sum()} dams")
print(f"In neither zone:     {((dams_merged['In Fathom 100yr Flood Zone']==0) & (dams_merged['In Fathom 500yr Flood Zone']==0)).sum()} dams")

print("\n--- Sample dams in 100yr flood zone ---")
sample = dams_merged[dams_merged["In Fathom 100yr Flood Zone"] == 1][
    ["NID ID", "Dam Name", "In Fathom 100yr Flood Zone", "In Fathom 500yr Flood Zone"]
].head(10)
print(sample.to_string(index=False))