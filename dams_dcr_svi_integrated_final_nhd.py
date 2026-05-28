import pandas as pd
import geopandas as gpd
import numpy as np
import os
import warnings
warnings.filterwarnings('ignore')

BASE   = r"C:\Users\annam\PyCharmMiscProject\SARADI\data"
NHD    = os.path.join(BASE, "raw", "NHD")
INPUT  = os.path.join(BASE, "dams_dcr_svi_integrated_v4.csv")
OUTPUT = os.path.join(BASE, "dams_dcr_svi_integrated_v4.csv")

NHD_GDBS = [
    os.path.join(NHD, "NHD_H_0206_HU4_GDB", "NHD_H_0206_HU4_GDB.gdb"),
    os.path.join(NHD, "NHD_H_0207_HU4_GDB", "NHD_H_0207_HU4_GDB.gdb"),
    os.path.join(NHD, "NHD_H_0208_HU4_GDB.gdb"),
    os.path.join(NHD, "NHD_H_0301_HU4_GDB", "NHD_H_0301_HU4_GDB.gdb"),
    os.path.join(NHD, "NHD_H_0302_HU4_GDB", "NHD_H_0302_HU4_GDB.gdb"),
    os.path.join(NHD, "NHD_H_0501_HU4_GDB", "NHD_H_0501_HU4_GDB.gdb"),
]
for p in NHD_GDBS:
    print(f"Exists: {os.path.exists(p)} — {p}")

# ── Load base file ─────────────────────────────────────────────────────────────
print("Loading v4...")
df = pd.read_csv(INPUT, low_memory=False)
print(f"  Loaded: {df.shape}")
print(f"  River or Stream Name missing: {df['River or Stream Name'].isna().sum()}")
print(f"  City missing:                 {df['City'].isna().sum()}")
print(f"  Distance missing:             {df['Distance to Nearest City (Miles)'].isna().sum()}")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 1: Fill River or Stream Name from NHD Flowlines
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("STEP 1: Filling River or Stream Name from NHD")
print("=" * 60)

flowline_gdfs = []
for gdb_path in NHD_GDBS:
    if not os.path.exists(gdb_path):
        print(f"  WARNING: Not found — {gdb_path}")
        continue
    try:
        # Hardcode 'NHDFlowline' — fiona was picking NHDFlowlineVAA which has no gnis_name
        gdf = gpd.read_file(gdb_path, layer='NHDFlowline')
        gdf = gdf[gdf['gnis_name'].notna() & (gdf['gnis_name'].str.strip() != '')]
        flowline_gdfs.append(gdf[['gnis_name', 'geometry']])
        print(f"  Loaded {len(gdf)} named flowlines from {os.path.basename(gdb_path)}")
    except Exception as e:
        print(f"  ERROR loading {os.path.basename(gdb_path)}: {e}")

if flowline_gdfs:
    all_flowlines = gpd.GeoDataFrame(
        pd.concat(flowline_gdfs, ignore_index=True),
        geometry='geometry'
    ).to_crs("EPSG:32618")

    print(f"\n  Total named flowlines: {len(all_flowlines)}")

    missing_river = df[df['River or Stream Name'].isna()].copy()
    print(f"  Dams missing river name: {len(missing_river)}")

    if len(missing_river) > 0:
        dam_gdf = gpd.GeoDataFrame(
            missing_river[['NID ID', 'Latitude', 'Longitude']],
            geometry=gpd.points_from_xy(
                missing_river['Longitude'], missing_river['Latitude']),
            crs="EPSG:4326"
        ).to_crs("EPSG:32618")

        print("  Running nearest flowline join (may take 2-3 minutes)...")
        joined = gpd.sjoin_nearest(
            dam_gdf[['NID ID', 'geometry']],
            all_flowlines,
            how='left',
            max_distance=5000  # within 5km
        )

        river_map = joined.set_index('NID ID')['gnis_name'].to_dict()
        filled = 0
        for idx, row in df.iterrows():
            if pd.isna(row['River or Stream Name']):
                val = river_map.get(row['NID ID'])
                if val and pd.notna(val):
                    df.at[idx, 'River or Stream Name'] = val
                    filled += 1

        print(f"  Filled:        {filled} river names")
        print(f"  Now have:      {df['River or Stream Name'].notna().sum()} / {len(df)}")
        print(f"  Still missing: {df['River or Stream Name'].isna().sum()}")
else:
    print("  No flowlines loaded — skipping")

# ══════════════════════════════════════════════════════════════════════════════
# STEP 2: Fill City and Distance using Virginia cities
# ══════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("STEP 2: Filling City and Distance to Nearest City")
print("=" * 60)

va_cities = [
    ('Richmond',        37.5407, -77.4360), ('Virginia Beach', 36.8529, -75.9780),
    ('Norfolk',         36.8508, -76.2859), ('Chesapeake',     36.7682, -76.2875),
    ('Arlington',       38.8799, -77.1067), ('Alexandria',     38.8048, -77.0469),
    ('Hampton',         37.0299, -76.3452), ('Newport News',   37.0871, -76.4730),
    ('Roanoke',         37.2710, -79.9414), ('Lynchburg',      37.4138, -79.1422),
    ('Charlottesville', 38.0293, -78.4767), ('Portsmouth',     36.8354, -76.2983),
    ('Fredericksburg',  38.3032, -77.4605), ('Harrisonburg',   38.4496, -78.8689),
    ('Leesburg',        39.1154, -77.5636), ('Winchester',     39.1857, -78.1633),
    ('Staunton',        38.1496, -79.0717), ('Danville',       36.5860, -79.3950),
    ('Suffolk',         36.7282, -76.5836), ('Manassas',       38.7509, -77.4753),
    ('Petersburg',      37.2279, -77.4019), ('Blacksburg',     37.2296, -80.4139),
    ('Bristol',         36.5959, -82.1888), ('Martinsville',   36.6918, -79.8728),
    ('Waynesboro',      38.0685, -78.8895), ('Radford',        37.1318, -80.5765),
    ('Salem',           37.2932, -80.0548), ('Covington',      37.7934, -79.9942),
    ('Lexington',       37.7843, -79.4428), ('Wytheville',     36.9487, -81.0848),
    ('Abingdon',        36.7098, -81.9774), ('Culpeper',       38.4732, -77.9961),
    ('Front Royal',     38.9176, -78.1941), ('Warrenton',      38.7215, -77.7961),
    ('Luray',           38.6651, -78.4567), ('Pulaski',        37.0579, -80.7762),
    ('Galax',           36.6612, -80.9237), ('Emporia',        36.6860, -77.5422),
    ('Hopewell',        37.3043, -77.2875), ('Williamsburg',   37.2707, -76.7075),
    ('Farmville',       37.3057, -78.3978), ('South Boston',   36.6979, -78.9011),
    ('Tazewell',        37.1148, -81.5196), ('Big Stone Gap',  36.8687, -82.7749),
    ('Norton',          36.9334, -82.6296), ('Grundy',         37.2693, -82.0974),
    ('Woodstock',       38.8818, -78.5083), ('Tappahannock',   37.9243, -76.8558),
    ('Louisa',          38.0221, -77.9997), ('Appomattox',     37.3565, -78.8139),
    ('Rocky Mount',     36.9968, -79.8917), ('Stuart',         36.6418, -80.2742),
    ('Hillsville',      36.7626, -80.7326), ('Lebanon',        36.8990, -82.0760),
    ('Gate City',       36.6337, -82.5760), ('Wise',           36.9765, -82.5760),
    ('Orange',          38.2454, -78.1094), ('Gordonsville',   38.1382, -78.1861),
    ('Buckingham',      37.5493, -78.5564), ('Clarksville',    36.6243, -78.5597),
]

cities_df = pd.DataFrame(va_cities, columns=['city_name', 'city_lat', 'city_lon'])

def haversine_miles(lat1, lon1, lat2, lon2):
    R = 3958.8
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1)*np.cos(lat2)*np.sin(dlon/2)**2
    return R * 2 * np.arcsin(np.sqrt(a))

def find_nearest_city(lat, lon):
    if pd.isna(lat) or pd.isna(lon):
        return None, None
    dists = cities_df.apply(
        lambda r: haversine_miles(lat, lon, r['city_lat'], r['city_lon']), axis=1)
    idx = dists.idxmin()
    return cities_df.loc[idx, 'city_name'], round(dists[idx], 1)

before_city = df['City'].notna().sum()
before_dist = df['Distance to Nearest City (Miles)'].notna().sum()

print(f"  Processing {len(df)} dams...")
for idx, row in df.iterrows():
    city_missing = pd.isna(row['City']) or str(row['City']).strip() == ''
    dist_missing = pd.isna(row['Distance to Nearest City (Miles)'])
    if city_missing or dist_missing:
        city, dist = find_nearest_city(row['Latitude'], row['Longitude'])
        if city_missing and city:
            df.at[idx, 'City'] = city
        if dist_missing and dist:
            df.at[idx, 'Distance to Nearest City (Miles)'] = dist

after_city = df['City'].notna().sum()
after_dist = df['Distance to Nearest City (Miles)'].notna().sum()
print(f"  City — Before: {before_city}, After: {after_city}, Filled: {after_city - before_city}")
print(f"  Dist — Before: {before_dist}, After: {after_dist}, Filled: {after_dist - before_dist}")

# ── Save ───────────────────────────────────────────────────────────────────────
df.to_csv(OUTPUT, index=False)
print(f"\nSaved: {OUTPUT}")
print(f"Final shape: {df.shape}")
print("\nDone.")