import geopandas as gpd
import pandas as pd
import os
import warnings

warnings.filterwarnings("ignore")

DAMS_PATH = r"C:\Users\annam\PyCharmMiscProject\SARADI\data\dams.csv"
NFHL_DIR  = r"C:\Users\annam\PyCharmMiscProject\SARADI\data\raw\NFHL"
OUTPUT    = r"C:\Users\annam\PyCharmMiscProject\SARADI\data\dams_with_flood_zones.csv"

print("Loading dams.csv...")
dams = pd.read_csv(DAMS_PATH).reset_index(drop=True)
dams["dam_row_id"] = dams.index
print(f"Loaded {len(dams)} dams")

# Build dam points
dams_gdf = gpd.GeoDataFrame(
    dams,
    geometry=gpd.points_from_xy(dams["Longitude"], dams["Latitude"]),
    crs="EPSG:4326"
)

print(f"\nScanning NFHL folders in {NFHL_DIR}...")
print("This will take a few minutes...\n")

all_flood_zones = []

# Find all FEMA flood hazard shapefiles
shp_files = []
for root, dirs, files in os.walk(NFHL_DIR):
    for f in files:
        if f.lower() == "s_fld_haz_ar.shp":
            shp_files.append(os.path.join(root, f))

shp_files = sorted(shp_files)
print(f"Found {len(shp_files)} S_FLD_HAZ_AR shapefiles")

if not shp_files:
    raise ValueError(
        "No S_FLD_HAZ_AR.shp files found. Make sure the FEMA zip files are extracted."
    )

# Load each county FEMA layer
for i, shp_path in enumerate(shp_files):
    folder = os.path.basename(os.path.dirname(shp_path))
    try:
        gdf = gpd.read_file(shp_path)

        # Keep only needed columns if present
        keep_cols = [c for c in ["FLD_ZONE", "ZONE_SUBTY", "SFHA_TF"] if c in gdf.columns]
        keep_cols.append("geometry")
        gdf = gdf[keep_cols].copy()

        # Drop bad geometries
        gdf = gdf[gdf.geometry.notna() & gdf.geometry.is_valid]

        # Reproject if needed
        if gdf.crs and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs("EPSG:4326")

        all_flood_zones.append(gdf)
        print(f"  [{i+1}/{len(shp_files)}] {folder} - {len(gdf)} polygons loaded")

    except Exception as e:
        print(f"  [{i+1}/{len(shp_files)}] {folder} - error: {e}")

if not all_flood_zones:
    raise ValueError("No FEMA flood zones loaded. Check shapefile contents.")

print(f"\nSuccessfully loaded {len(all_flood_zones)} county layers")

# Merge all FEMA polygons
print("\nMerging all flood zone layers...")
nfhl_all = gpd.GeoDataFrame(
    pd.concat(all_flood_zones, ignore_index=True),
    crs="EPSG:4326"
)
print(f"Total flood zone polygons: {len(nfhl_all):,}")

# Spatial join
print("\nRunning spatial join...")
joined = gpd.sjoin(dams_gdf, nfhl_all, how="left", predicate="intersects")

# Keep the most restrictive zone for each original dam row
ZONE_PRIORITY = {
    "VE": 1, "V": 1,
    "AE": 1,
    "AO": 2, "AH": 2, "AR": 2, "A": 2, "A99": 2,
    "X500": 3,
    "X": 4,
    "D": 5
}

joined["_priority"] = joined["FLD_ZONE"].map(ZONE_PRIORITY).fillna(6)
joined = joined.sort_values("_priority")
joined = joined.groupby("dam_row_id").first().reset_index()

assert len(joined) == len(dams), f"Row count mismatch: {len(joined)} vs {len(dams)}"
print(f"Row count verified: {len(joined)}")

# Build final FEMA columns
joined["FEMA_Flood_Zone"] = joined["FLD_ZONE"].fillna("No Data")

if "ZONE_SUBTY" in joined.columns:
    joined["FEMA_Zone_Subtype"] = joined["ZONE_SUBTY"].fillna("")
else:
    joined["FEMA_Zone_Subtype"] = ""

if "SFHA_TF" in joined.columns:
    joined["FEMA_In_SFHA"] = joined["SFHA_TF"].fillna("F").eq("T")
    print("Using FEMA's own SFHA_TF flag")
else:
    SFHA_ZONES = {"A", "AE", "AO", "AH", "VE", "V", "AR", "A99"}
    joined["FEMA_In_SFHA"] = joined["FEMA_Flood_Zone"].isin(SFHA_ZONES)
    print("SFHA_TF not found - deriving SFHA from zone code")

def risk_cat(zone, sfha):
    if sfha:
        return "High"
    if zone == "X500":
        return "Moderate"
    if zone == "No Data":
        return "Unknown"
    return "Low"

joined["Flood_Risk_Category"] = joined.apply(
    lambda x: risk_cat(x["FEMA_Flood_Zone"], x["FEMA_In_SFHA"]),
    axis=1
)

# Diagnostics
print("\nUnique matched zones:")
print(joined["FEMA_Flood_Zone"].value_counts(dropna=False).head(20))
print("SFHA count:", joined["FEMA_In_SFHA"].sum())
print("Unknown count:", (joined["Flood_Risk_Category"] == "Unknown").sum())

# Merge back using unique row id
fema_cols = joined[
    [
        "dam_row_id",
        "FEMA_Flood_Zone",
        "FEMA_Zone_Subtype",
        "FEMA_In_SFHA",
        "Flood_Risk_Category"
    ]
]

result = dams.merge(fema_cols, on="dam_row_id", how="left")
result = result.drop(columns=["dam_row_id"])

# Save output
result.to_csv(OUTPUT, index=False)

print(f"\nDONE - saved to {OUTPUT}")
print(f"Shape: {result.shape}")

print("\nRisk category breakdown:")
print(result["Flood_Risk_Category"].value_counts())

print(f"\nIn SFHA (High Risk): {result['FEMA_In_SFHA'].sum()}")
print(f"No Data (unmapped): {(result['FEMA_Flood_Zone'] == 'No Data').sum()}")

if "Last Inspection Date" in result.columns:
    print(
        f"Never inspected + In SFHA: "
        f"{((result['FEMA_In_SFHA']) & (result['Last Inspection Date'].isna())).sum()}"
    )