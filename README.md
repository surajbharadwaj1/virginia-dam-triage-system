# SARRDI — Situational Awareness of Risks Related to Dam Infrastructure

> **GMU DAEN 690 Capstone | Spring 2026**
> George Mason University × Appalachia Recovery Coalition × GMU STAR-TIDES

---

## Table of Contents
- [Overview](#overview)
- [Project Objective](#project-objective)
- [Stakeholders](#stakeholders)
- [Problem Statement](#problem-statement)
- [System Architecture](#system-architecture)
- [Data Sources](#data-sources)
- [Data Pipeline](#data-pipeline)
- [Triage Scoring Model](#triage-scoring-model)
- [Key Findings](#key-findings)
- [Power BI Dashboard](#power-bi-dashboard)
- [Repository Structure](#repository-structure)
- [Technologies Used](#technologies-used)
- [Testing and Validation](#testing-and-validation)
- [Business Impact](#business-impact)
- [Getting Started](#getting-started)
- [About](#about)

---

## Overview

SARRDI is a data-driven decision support system that analyzes all **2,712 dams in Virginia** and assigns each a **0–100 triage score** based on five weighted risk dimensions. Results are delivered through an interactive Power BI dashboard to help agencies prioritize inspections, Emergency Action Plans (EAPs), and mitigation efforts.

The project directly addresses a critical gap in Virginia's dam safety infrastructure: over half of all dams lack formal hazard classification, dozens have no emergency plans, and inspection data is fragmented across multiple agencies. SARRDI consolidates these disparate datasets into a single, reproducible pipeline.

---

## Project Objective

> **Which dams should be inspected or addressed first?**

SARRDI answers this question by producing two actionable outputs:

1. **Inspection Priority List** — Dams ranked by triage score urgency
2. **Classification Campaign List** — Dams missing hazard classifications that require immediate categorization

---

## Stakeholders

| Role | Organization | Contact |
|------|-------------|---------|
| Client | Appalachia Recovery Coalition (ARC) | Velma Anne Ruth |
| Research Partner | GMU STAR-TIDES Program | Dr. Linton Wells II |
| Academic Advisor | George Mason University | Dr. Isaac Gang |

---

## Problem Statement

Virginia's dam portfolio contains significant information gaps that impede effective risk management:

| Metric | Count |
|--------|-------|
| Total dams in Virginia | 2,712 |
| Dams without a formal safety rating | 1,402 (51.6%) |
| Critical dams with no Emergency Action Plan | 74 |
| Dams flagged for urgent inspection | 170 |

Without a standardized prioritization method, inspection and remediation resources cannot be effectively targeted.

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         DATA SOURCES                             │
│  ┌──────────┐  ┌─────────┐  ┌──────────┐  ┌──────┐  ┌────────┐ │
│  │USACE NID │  │  VA DCR │  │ CDC SVI  │  │  NHD │  │ Fathom │ │
│  └────┬─────┘  └────┬────┘  └────┬─────┘  └──┬───┘  └───┬────┘ │
└───────┼─────────────┼────────────┼────────────┼──────────┼──────┘
        │             │            │            │          │
        ▼             ▼            ▼            ▼          ▼
┌──────────────────────────────────────────────────────────────────┐
│                       PYTHON PIPELINE                            │
│                                                                  │
│  [Step 1] dams_dcr_new.py           — Base dam data extraction   │
│      ↓                                                           │
│  [Step 2] add_census_to_dams.py     — Inspection dates + SVI     │
│      ↓                                                           │
│  [Step 3] Nhd integration .py       — River name spatial join    │
│      ↓                                                           │
│  [Step 4] extract_nfhl.py           — FEMA flood zone extraction │
│           fema_lookup.py            — Flood zone classification  │
│           Fathom.py                 — Fathom flood integration   │
│      ↓                                                           │
│  [Step 5] Triagescoring.py          — Score + priority band      │
└───────────────────────────┬──────────────────────────────────────┘
                            │
                            ▼
              dams_triage_scored.csv
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────┐
│                     POWER BI DASHBOARD                           │
│    Interactive Map | KPI Cards | Charts | Slicers | Filters      │
└──────────────────────────────────────────────────────────────────┘
```

---

## Data Sources

### 1. USACE — National Inventory of Dams (NID)
- NID ID, dam height, storage capacity, hazard classification, EAP status
- Source: https://nid.usace.army.mil/

### 2. Virginia Department of Conservation and Recreation (DCR)
- Dam point locations, watersheds, inundation zones, inspection dates
- Source: https://www.dcr.virginia.gov/

### 3. CDC Social Vulnerability Index (SVI) 2022
- Population metrics and community vulnerability indicators
- Source: https://www.atsdr.cdc.gov/placeandhealth/svi/

### 4. USGS National Hydrography Dataset (NHD)
- River and stream names for spatial context
- Source: https://www.usgs.gov/national-hydrography/national-hydrography-dataset

### 5. Fathom Flood Data *(Licensed)*
- 100-year and 500-year flood exposure per dam location

---

## Data Pipeline

The system processes data through five sequential stages.

### Step 1 — Base Extraction
**Script:** `dams_dcr_new.py`

Extracts foundational dam records from the National Inventory of Dams and Virginia DCR. Establishes the 2,712-record base that all subsequent stages join against.

### Step 2 — DCR + SVI Integration
**Script:** `add_census_to_dams.py`

Adds Virginia DCR inspection dates, DCR hazard classifications, and CDC Social Vulnerability Index metrics by joining on dam location and county FIPS codes.

### Step 3 — NHD River Integration
**Script:** `Nhd integration .py`

Performs a spatial join between dam point locations and USGS NHD flowline geometries to attach the nearest river or stream name to each dam record.

### Step 4 — Flood Zone Integration
**Scripts:** `extract_nfhl.py`, `fema_lookup.py`, `Fathom.py`

Extracts FEMA National Flood Hazard Layer geometries and Fathom flood data to determine whether each dam falls within a 100-year or 500-year flood zone.

### Step 5 — Triage Score Calculation
**Script:** `Triagescoring.py`

Calculates the final composite triage score and assigns a priority band (Critical, High, Moderate, Low) based on the weighted scoring formula.

### Intermediate Output Files

| Stage | Output File | Description |
|-------|-------------|-------------|
| Step 1 | `dams.csv` | Base dam dataset |
| Step 2 | `dams_with_nhd_wbd_census.csv` | With SVI metrics |
| Step 3 | `dams_with_nhd_wbd.csv` | With river/stream names |
| Step 4 | `dams_with_flood_zones.csv` | With flood zone flags |
| Step 5 | `dams_triage_scored.csv` | Final scored dataset |

---

## Triage Scoring Model

Each dam is scored across five risk dimensions and assigned a composite triage score from 0–100. Higher scores indicate greater urgency.

| Dimension | Description | Weight |
|-----------|-------------|--------|
| D1 | Hazard Classification | 25% |
| D2 | Flood Zone Exposure | 20% |
| D3 | Watershed & Cascade Risk | 25% |
| D4 | Downstream Human Impact | 20% |
| D5 | Data Quality & Inspection Gap | 10% |

**Formula:**

```
Triage Score = (0.25 × D1) + (0.20 × D2) + (0.25 × D3) + (0.20 × D4) + (0.10 × D5)
```

### Dimension Descriptions

**D1 — Hazard Classification (25%)**
Scores based on USACE/DCR hazard class. High-hazard dams (where failure is likely to cause loss of life) receive maximum scores. Unclassified dams receive a penalty score reflecting unknown risk.

**D2 — Flood Zone Exposure (20%)**
Graduated scoring based on intersection with FEMA 100-year and 500-year flood zones. Dams within both zones receive the highest exposure scores.

**D3 — Watershed & Cascade Risk (25%)**
Accounts for upstream/downstream dam density and watershed drainage area. Dams in cascade-failure-prone watersheds score higher.

**D4 — Downstream Human Impact (20%)**
Derived from CDC SVI metrics. Reflects population size, density, and social vulnerability within the potential inundation zone.

**D5 — Data Quality & Inspection Gap (10%)**
Penalizes dams with missing inspection records, outdated assessments, or absent Emergency Action Plans.

### Priority Bands

| Band | Score Range | Meaning |
|------|-------------|---------|
| 🔴 Critical | 70–100 | Immediate action required |
| 🟠 High | 50–69 | Inspect soon |
| 🟡 Moderate | 30–49 | Monitor and schedule |
| 🟢 Low | 0–29 | Routine oversight |
| ⚪ Not Inspected | — | Missing recent inspection data |

---

## Key Findings

- **170 Critical Priority Dams** identified statewide
- **Highest Triage Score:** 83.71
- **74 Critical Dams** with no Emergency Action Plan on file
- **1,402 Dams** without formal hazard classification
- **Top-ranked dam:** Lancaster Roller Mill Dam

### High-Concentration Counties

- Caroline County
- Amherst County
- Frederick County
- Powhatan County
- Greensville County

---

## Power BI Dashboard

The interactive dashboard (`Dashboard.pbip`) provides:

### Interactive Map
- All 2,712 Virginia dams plotted and color-coded by priority band
- Tooltip shows: Dam name, County, Hazard classification, EAP status, Inspection status, Triage score

### Executive KPIs
- Total dams | Dams without safety ratings | Urgent inspections needed

### Analytical Visuals
- Inspection recency for critical dams
- Priority band distribution
- Flood exposure distribution
- Top critical dams ranked by triage score
- Critical dams by county

### Filters
- Priority band | Dam name | River name | County | Hazard class

> **To open:** Download `Dashboard.pbip` and open with Power BI Desktop (free): https://powerbi.microsoft.com/desktop/

---

## Repository Structure

```
virginia-dam-triage-system/
│
├── Dashboard.Report/               # Power BI report definition files
├── Dashboard.SemanticModel/        # Power BI semantic model
├── Dashboard.pbip                  # Power BI project file
│
├── dams.csv                        # Base dam dataset
├── dams_triage_scored.csv          # Final scored dataset
├── dams_with_flood_zones.csv       # After flood zone integration
├── dams_with_nhd_wbd.csv           # After NHD integration
├── dams_with_nhd_wbd_census.csv    # After census/SVI integration
│
├── Triagescoring.py                # Step 5: Triage score calculation
├── Fathom.py                       # Step 4: Fathom flood integration
├── dams_dcr_new.py                 # Step 1: Base dam extraction
├── dams_dcr_svi_integrated_final.py        # DCR + SVI pipeline
├── dams_dcr_svi_integrated_final_nhd.py    # Full integration script
├── add_census_to_dams.py           # Step 2: SVI/census integration
├── extract_nfhl.py                 # Step 4: FEMA flood extraction
├── fema_lookup.py                  # Step 4: FEMA flood lookup
├── Nhd integration .py             # Step 3: NHD spatial join
│
├── requirements.txt                # Python dependencies
├── .gitignore                      # Git ignore rules
├── LICENSE                         # MIT License
└── README.md                       # This file
```

---

## Technologies Used

| Category | Tools |
|----------|-------|
| Data Processing | Python 3.8+, Pandas, NumPy |
| Spatial Analysis | GeoPandas, Shapely, Fiona, PyProj |
| Visualization | Power BI, DAX, Bing Maps |
| Data Sources | USACE NID, VA DCR, CDC SVI, USGS NHD, Fathom (Licensed) |
| Version Control | Git, GitHub |

---

## Testing and Validation

### Data Quality
- Record counts verified across all five pipeline stages (expected: 2,712 at each stage)
- NID ID uniqueness confirmed — no duplicate dam records at any stage
- Missing values flagged and handled with documented imputation logic
- Coordinate validity checked for all spatial join operations

### Dashboard Validation
- Row counts matched against final scored dataset
- All filters and slicers tested against underlying data
- Visuals cross-checked with Python-generated outputs
- Priority band counts verified against triage score output

### Client Acceptance
- Reviewed and approved by ARC project stakeholders
- Priority logic validated against expert domain knowledge
- Delivered with no outstanding change requests

---

## Business Impact

SARRDI transforms fragmented infrastructure data into operational intelligence for emergency management and policy decision-making.

**Use Cases:**
- **Inspection resource allocation** — Direct limited budgets to highest-risk dams first
- **Emergency response planning** — Pre-identify cascade failure risk zones before disasters occur
- **EAP development campaigns** — Target the 74 critical dams currently lacking emergency action plans
- **Legislative and budget reporting** — Evidence-based justification for dam safety funding requests
- **Classification campaigns** — Systematic outreach to owners of the 1,402 unclassified dams

---

## Getting Started

### Prerequisites
- Python 3.8+
- Power BI Desktop: https://powerbi.microsoft.com/desktop/
- Git

### 1. Clone the Repository

```bash
git clone https://github.com/surajbharadwaj1/virginia-dam-triage-system.git
cd virginia-dam-triage-system
```

### 2. Set Up Environment

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Run the Pipeline

```bash
python dams_dcr_new.py
python add_census_to_dams.py
python "Nhd integration .py"
python extract_nfhl.py
python fema_lookup.py
python Fathom.py
python Triagescoring.py
```

### 4. Open the Dashboard

Open `Dashboard.pbip` in Power BI Desktop. The dashboard reads from `dams_triage_scored.csv`.

---

## About

| | |
|--|--|
| **Course** | DAEN 690 — Data Analytics Engineering Capstone |
| **Program** | George Mason University, College of Engineering and Computing |
| **Semester** | Spring 2026 |
| **Partner** | Appalachia Recovery Coalition (ARC) |
| **Research Sponsor** | GMU STAR-TIDES Program |
| **License** | MIT |

*For questions about the GMU DAEN Program: https://analyticsengineering.gmu.edu/*