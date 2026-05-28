import geopandas as gpd
import pandas as pd
import fiona
import os
import warnings
warnings.filterwarnings("ignore")

DAMS_PATH = r"C:\Users\annam\PyCharmMiscProject\SARADI\data\dams_with_flood_zones.csv"

NHD_PATHS = [
    r"C:\Users\annam\PyCharmMiscProject\SARADI\data\raw\NHD\NHD_H_0208_HU4_GDB.gdb",
    r"C:\Users\annam\PyCharmMiscProject\SARADI\data\raw\NHD\NHD_H_0207_HU4_GDB\NHD_H_0207_HU4_GDB.gdb",
    r"C:\Users\annam\PyCharmMiscProject\SARADI\data\raw\NHD\NHD_H_0206_HU4_GDB\NHD_H_0206_HU4_GDB.gdb",
    r"C:\Users\annam\PyCharmMiscProject\SARADI\data\raw\NHD\NHD_H_0501_HU4_GDB\NHD_H_0501_HU4_GDB.gdb",
    r"C:\Users\annam\PyCharmMiscProject\SARADI\data\raw\NHD\NHD_H_0301_HU4_GDB\NHD_H_0301_HU4_GDB.gdb",
    r"C:\Users\annam\PyCharmMiscProject\SARADI\data\raw\NHD\NHD_H_0302_HU4_GDB\NHD_H_0302_HU4_GDB.gdb",
]

WBD_PATHS = [
    r"C:\Users\annam\PyCharmMiscProject\SARADI\data\raw\WBD\WBD_02_HU2_GDB\WBD_02_HU2_GDB.gdb",
    r"C:\Users\annam\PyCharmMiscProject\SARADI\data\raw\WBD\WBD_03_HU2_GDB\WBD_03_HU2_GDB.gdb",
    r"C:\Users\annam\PyCharmMiscProject\SARADI\data\raw\WBD\WBD_05_HU2_GDB\WBD_05_HU2_GDB.gdb",
]

OUTPUT = r"C:\Users\annam\PyCharmMiscProject\SARADI\data\dams_with_nhd_wbd.csv"

print("Loading dams_with_flood_zones.csv...")
dams = pd.read_csv(DAMS_PATH).reset_index(drop=True)
dams["dam_row_id"] = dams.index
print(f"Loaded {len(dams)} dams")

dams_gdf = gpd.GeoDataFrame(
    dams,
    geometry=gpd.points_from_xy(dams["Longitude"], dams["Latitude"]),
    crs="EPSG:4326"
)

def find_col(df, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None

RIVER_NAME_CANDIDATES = ["gnis_name", "GNIS_Name", "GNIS_NAME", "Name", "NAME"]
COMID_CANDIDATES      = ["permanent_identifier", "NHDPlusID", "NHDPLUSID", "ComID", "COMID"]

print("\nLoading NHD flowlines + waterbodies...")
flow_parts  = []
water_parts = []

for path in NHD_PATHS:
    if not os.path.exists(path):
        print(f"  Missing: {path}")
        continue
    flow = gpd.read_file(path, layer="NHDFlowline")
    flow = flow[flow.geometry.notna() & flow.geometry.is_valid]
    flow_parts.append(flow)
    available_layers = fiona.listlayers(path)
    if "NHDWaterbody" in available_layers:
        water = gpd.read_file(path, layer="NHDWaterbody")
        water = water[water.geometry.notna() & water.geometry.is_valid]
        water_parts.append(water)
        print(f"  {os.path.basename(path)}: {len(flow):,} flowlines, {len(water):,} waterbodies")
    else:
        print(f"  {os.path.basename(path)}: {len(flow):,} flowlines, NHDWaterbody not found")

if not flow_parts:
    raise ValueError("No NHD flowlines loaded. Check paths.")

flow_parts_fixed = []
for g in flow_parts:
    if g.crs is None:
        g = g.set_crs("EPSG:4326")
    elif g.crs.to_epsg() != 4326:
        g = g.to_crs("EPSG:4326")
    flow_parts_fixed.append(g)
flow = gpd.GeoDataFrame(pd.concat(flow_parts_fixed, ignore_index=True), crs="EPSG:4326")
print(f"Total flowlines:   {len(flow):,}")

if water_parts:
    water_parts_fixed = []
    for g in water_parts:
        if g.crs is None:
            g = g.set_crs("EPSG:4326")
        elif g.crs.to_epsg() != 4326:
            g = g.to_crs("EPSG:4326")
        water_parts_fixed.append(g)
    water = gpd.GeoDataFrame(pd.concat(water_parts_fixed, ignore_index=True), crs="EPSG:4326")
    print(f"Total waterbodies: {len(water):,}")
else:
    water = gpd.GeoDataFrame(columns=["geometry"], crs="EPSG:4326")
    print("No waterbodies loaded - will snap to flowlines only")

river_col      = find_col(flow,  RIVER_NAME_CANDIDATES)
water_name_col = find_col(water, RIVER_NAME_CANDIDATES) if len(water) > 0 else None
comid_col      = find_col(flow,  COMID_CANDIDATES)
print(f"Flowline name col:  {river_col}")
print(f"Waterbody name col: {water_name_col}")
print(f"Permanent ID col:   {comid_col}")
print("Stream order: Not available in this NHD version - excluded from output")

print("\nSnapping to flowlines and waterbodies...")
dams_proj = dams_gdf.to_crs("EPSG:3857")
flow_proj = flow.to_crs("EPSG:3857")
snap_flow = gpd.sjoin_nearest(dams_proj, flow_proj, how="left", distance_col="dist_flow")

if len(water) > 0:
    water_proj = water.to_crs("EPSG:3857")
    snap_water = gpd.sjoin_nearest(dams_proj, water_proj, how="left", distance_col="dist_water")
else:
    snap_water = None

print("Choosing best match...")
snap_flow = snap_flow.sort_values("dist_flow").groupby("dam_row_id").first()
combined  = snap_flow.copy()
combined["Snap_Distance_m"] = snap_flow["dist_flow"]
combined["NHD_Snap_Source"] = "FLOWLINE"

if snap_water is not None:
    snap_water = snap_water.sort_values("dist_water").groupby("dam_row_id").first()
    use_water = (
        snap_water["dist_water"].notna() &
        (
            snap_flow["dist_flow"].isna() |
            (snap_water["dist_water"] < snap_flow["dist_flow"])
        )
    )
    combined.loc[use_water, "Snap_Distance_m"] = snap_water.loc[use_water, "dist_water"]
    combined.loc[use_water, "NHD_Snap_Source"] = "WATERBODY"
    if water_name_col and water_name_col in snap_water.columns:
        combined.loc[use_water, "NHD_River_Name"] = snap_water.loc[use_water, water_name_col]
    if comid_col and comid_col in snap_water.columns:
        combined.loc[use_water, comid_col] = snap_water.loc[use_water, comid_col]

if "NHD_River_Name" not in combined.columns:
    combined["NHD_River_Name"] = None
if river_col and river_col in combined.columns:
    mask = combined["NHD_River_Name"].isna()
    combined.loc[mask, "NHD_River_Name"] = combined.loc[mask, river_col]

if comid_col and comid_col in combined.columns:
    combined = combined.rename(columns={comid_col: "NHD_Permanent_ID"})

def snap_flag(d):
    if pd.isna(d): return "NO_MATCH"
    if d <= 100:   return "OK"
    if d <= 500:   return "REVIEW"
    return "FAR"

combined["NHD_Snap_Flag"] = combined["Snap_Distance_m"].apply(snap_flag)
combined = combined.reset_index()

print("Snap source breakdown:")
print(combined["NHD_Snap_Source"].value_counts())
print("Snap flag breakdown:")
print(combined["NHD_Snap_Flag"].value_counts())
print("Snap distance stats (meters):")
print(combined["Snap_Distance_m"].describe())

print("\nLoading WBD watersheds from 3 HU2 regions...")

def load_wbd_layer(gdb_path, level):
    if not os.path.exists(gdb_path):
        print(f"  Path not found: {gdb_path}")
        return None
    layers = fiona.listlayers(gdb_path)
    match = [l for l in layers if f"HU{level}" in l.upper() or f"WBDHU{level}" in l.upper()]
    if not match:
        return None
    gdf = gpd.read_file(gdb_path, layer=match[0])
    code_col = find_col(gdf, [f"huc{level}", f"HUC{level}", f"HUC_{level}"])
    name_col = find_col(gdf, ["name", "Name", "NAME"])
    if not code_col:
        code_col = next((c for c in gdf.columns if str(level) in c.lower()), None)
    if not name_col:
        name_col = next((c for c in gdf.columns if "name" in c.lower()), None)
    if not code_col or not name_col:
        return None
    print(f"  HUC{level}: {len(gdf)} polygons from {os.path.basename(gdb_path)}")
    gdf = gdf[[code_col, name_col, "geometry"]].copy()
    gdf = gdf.rename(columns={code_col: f"HUC{level}_Code", name_col: f"HUC{level}_Name"})
    return gdf.to_crs("EPSG:4326")

huc8_parts  = []
huc12_parts = []
for wbd_path in WBD_PATHS:
    h8  = load_wbd_layer(wbd_path, 8)
    h12 = load_wbd_layer(wbd_path, 12)
    if h8  is not None: huc8_parts.append(h8)
    if h12 is not None: huc12_parts.append(h12)

dams_wbd = dams_gdf[["dam_row_id", "geometry"]].copy()

if huc8_parts:
    huc8_all = gpd.GeoDataFrame(pd.concat(huc8_parts, ignore_index=True), crs="EPSG:4326")
    j8 = gpd.sjoin(dams_wbd, huc8_all, how="left", predicate="within")
    j8 = j8.groupby("dam_row_id").first().reset_index()
    print(f"HUC8 assigned: {j8['HUC8_Code'].notna().sum()} / {len(dams)}")
else:
    j8 = pd.DataFrame({"dam_row_id": dams["dam_row_id"], "HUC8_Code": None, "HUC8_Name": None})

if huc12_parts:
    huc12_all = gpd.GeoDataFrame(pd.concat(huc12_parts, ignore_index=True), crs="EPSG:4326")
    j12 = gpd.sjoin(dams_wbd, huc12_all, how="left", predicate="within")
    j12 = j12.groupby("dam_row_id").first().reset_index()
    print(f"HUC12 assigned: {j12['HUC12_Code'].notna().sum()} / {len(dams)}")
else:
    j12 = pd.DataFrame({"dam_row_id": dams["dam_row_id"], "HUC12_Code": None, "HUC12_Name": None})

print("\nMerging all results...")
nhd_cols = ["dam_row_id", "Snap_Distance_m", "NHD_Snap_Flag", "NHD_Snap_Source"]
for c in ["NHD_River_Name", "NHD_Permanent_ID"]:
    if c in combined.columns:
        nhd_cols.append(c)

result = dams.copy()
result = result.merge(combined[nhd_cols], on="dam_row_id", how="left")
result = result.merge(j8[["dam_row_id",  "HUC8_Code",  "HUC8_Name"]],  on="dam_row_id", how="left")
result = result.merge(j12[["dam_row_id", "HUC12_Code", "HUC12_Name"]], on="dam_row_id", how="left")
result = result.drop(columns=["dam_row_id"])

# Hard cutoff - snaps over 10km are not meaningful
result.loc[result["Snap_Distance_m"] > 10000, "NHD_Snap_Flag"]    = "INVALID"
result.loc[result["Snap_Distance_m"] > 10000, "NHD_Snap_Source"]  = "NONE"
result.loc[result["Snap_Distance_m"] > 10000, "NHD_River_Name"]   = None
result.loc[result["Snap_Distance_m"] > 10000, "NHD_Permanent_ID"] = None
result["Valid_Snap"] = result["Snap_Distance_m"] <= 10000

result.to_csv(OUTPUT, index=False)

# Final validation
print("\n=== FINAL VALIDATION ===")
print("--- BASIC ---")
print(f"Shape: {result.shape}")
print("--- SNAP SOURCE ---")
print(result["NHD_Snap_Source"].value_counts())
print("--- SNAP FLAG ---")
print(result["NHD_Snap_Flag"].value_counts())
print("--- DISTANCE ---")
print(result["Snap_Distance_m"].describe())
print("--- HUC COVERAGE ---")
print(f"HUC8:  {result['HUC8_Code'].notna().sum()} / {len(result)}")
print(f"HUC12: {result['HUC12_Code'].notna().sum()} / {len(result)}")
print("--- FEMA ---")
print(result["Flood_Risk_Category"].value_counts())
print("--- INVALID SNAPS (>10km) ---")
print((result["Snap_Distance_m"] > 10000).sum())
print("--- VALID SNAP ---")
print(result["Valid_Snap"].value_counts())
print(f"\nRiver names filled: {result['NHD_River_Name'].notna().sum()} / {len(result)}")