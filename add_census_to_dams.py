import pandas as pd
import json

# -------------------------
# Paths
# -------------------------
DAMS_PATH = r"C:\Users\annam\PyCharmMiscProject\SARADI\data\dams_with_nhd_wbd.csv"
CENSUS_PATH = r"C:\Users\annam\PyCharmMiscProject\SARADI\data\raw\Census\census_population.json"
OUTPUT = r"C:\Users\annam\PyCharmMiscProject\SARADI\data\dams_with_nhd_wbd_census.csv"

# -------------------------
# Load dams
# -------------------------
print("Loading dams_with_nhd_wbd.csv...")
dams = pd.read_csv(DAMS_PATH)
print(f"Loaded {len(dams)} dam rows")

# -------------------------
# Load Census JSON
# -------------------------
print("\nLoading census_population.json...")
with open(CENSUS_PATH, "r", encoding="utf-8") as f:
    census_raw = json.load(f)

print("Census JSON type:", type(census_raw))

# Raw table-like JSON
census = pd.DataFrame(census_raw)

print("Raw Census shape:", census.shape)
print("\nRaw first 5 rows:")
print(census.head())

# -------------------------
# First row is header
# -------------------------
census.columns = census.iloc[0]
census = census.iloc[1:].reset_index(drop=True)

print("\nFixed columns:")
print(census.columns.tolist())
print("\nFirst 5 rows after header fix:")
print(census.head())

# -------------------------
# Clean and aggregate tract → county
# -------------------------
census["NAME"] = census["NAME"].astype(str)
census["B01003_001E"] = pd.to_numeric(census["B01003_001E"], errors="coerce")

# Example NAME:
# Census Tract 901.01; Accomack County; Virginia
name_parts = census["NAME"].str.split(";", expand=True)

census["County_raw"] = name_parts[1].str.strip()
census["State_raw"] = name_parts[2].str.strip()

census["County_join"] = (
    census["County_raw"]
    .str.upper()
    .str.replace(" COUNTY", "", regex=False)
    .str.replace(" CITY", "", regex=False)
    .str.strip()
)

state_map = {
    "VIRGINIA": "VA"
}
census["State_join"] = census["State_raw"].str.upper().map(state_map)

county_pop = (
    census.groupby(["County_join", "State_join"], as_index=False)["B01003_001E"]
    .sum()
    .rename(columns={"B01003_001E": "County_Population"})
)

print("\nCounty population rows:", len(county_pop))
print(county_pop.head())

# -------------------------
# Clean dams join fields
# -------------------------
dams["County_join"] = (
    dams["County"]
    .astype(str)
    .str.upper()
    .str.replace(" COUNTY", "", regex=False)
    .str.replace(" CITY", "", regex=False)
    .str.strip()
)

dams["State_join"] = (
    dams["State"]
    .astype(str)
    .str.upper()
    .str.strip()
    .replace(state_map)
)

# -------------------------
# Debug checks
# -------------------------
print("\nUnique dams State_join:")
print(dams["State_join"].dropna().unique()[:10])

print("\nUnique census State_join:")
print(county_pop["State_join"].dropna().unique()[:10])

print("\nSample dams County_join:")
print(dams[["County", "County_join", "State_join"]].head(10))

print("\nSample census County_join:")
print(county_pop.head(10))

# -------------------------
# Merge Census onto dams
# -------------------------
print("\nMerging Census population onto dams...")
result = dams.merge(
    county_pop,
    on=["County_join", "State_join"],
    how="left"
)

print("Rows after merge:", len(result))
print("Population matched:", result["County_Population"].notna().sum(), "/", len(result))
print("Population missing:", result["County_Population"].isna().sum())

print("\nSample rows:")
print(result[["Dam Name", "County", "State", "County_Population"]].head(10))

# -------------------------
# Save
# -------------------------
result = result.drop(columns=["County_join", "State_join"])
result.to_csv(OUTPUT, index=False)

print(f"\nDONE - saved to:\n{OUTPUT}")