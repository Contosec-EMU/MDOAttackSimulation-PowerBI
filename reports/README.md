# Power BI Report Templates

Pre-built Power BI report templates for Microsoft Defender for Office 365 Attack Simulation Training data. These templates use the **PBIR (Power BI Enhanced Report Format)** — a JSON-based, source-control friendly format.

> **Note:** These report templates are provided as **functional starting points**, not polished dashboards. The authors are security engineers, not data visualization designers — the layouts, visuals, and formatting are intentionally basic. You are encouraged to customize the reports to match your organization's branding, reporting standards, and analytical needs.

## Requirements

- **Power BI Desktop** (March 2024 or later) with Developer Mode enabled
- Data already ingested into your ADLS Gen2 storage account (see main [README](../README.md))
- **Storage Blob Data Reader** role on your ADLS Gen2 account

## Quick Start

### 1. Enable Developer Mode in Power BI Desktop

1. Open Power BI Desktop
2. Go to **File > Options and settings > Options**
3. Under **Preview features**, check **Power BI Project (.pbip) save format**
4. Under **Preview features**, check **Store reports using enhanced metadata format (PBIR)**
5. Restart Power BI Desktop

### 2. Open the Project

1. In **File Explorer**, navigate to the `reports/` folder and **double-click** `MDOAttackSimulation.pbip`

> **Tip:** If double-clicking doesn't work (or the file opens in a text editor), open Power BI Desktop first, then go to **File > Open report > Browse reports** and select the `.pbip` file.

### 3. Configure Your Storage Connection

When prompted (or via **Transform data > Edit parameters**):

| Parameter | Value | Example |
|-----------|-------|---------|
| **StorageAccountUrl** | Your ADLS Gen2 **DFS** endpoint URL | `https://mdoastdlxyz.dfs.core.windows.net` |
| **ContainerName** | Container with curated Parquet files | `curated` |

> ⚠️ **Important:** Use the **DFS** endpoint (`.dfs.core.windows.net`), **not** the Blob endpoint (`.blob.core.windows.net`). The Blob endpoint will return a 400 error.

Click **OK**, then **Apply Changes**.

### 4. Authenticate

When the Azure Data Lake Storage Gen2 credential prompt appears:

1. Select **Organizational account** on the left
2. Click **Sign in** and authenticate with your Azure AD credentials
3. In the **"Select which level to apply these settings to"** dropdown, choose the **root storage account URL** (e.g., `https://mdoastdlxyz.dfs.core.windows.net/`) — this avoids being prompted for each table
4. Click **Connect**

### 5. Refresh Data

Click **Home > Refresh** to load data from your storage account.

> **Note:** If some tables (e.g., `repeatOffenders`, `payloads`) don't have data yet, they will load as empty tables without blocking the rest of the report. They will populate automatically on the next refresh after the Azure Function produces data for those endpoints.

## Report Pages

| Page | Description | Key Visuals |
|------|-------------|-------------|
| **Executive Dashboard** | High-level KPIs for security leadership | Compromise Rate, Training Completion, Repeat Offenders, Monthly Trend |
| **Simulation Analysis** | Per-simulation performance metrics | Simulation details table, compromise rates by campaign, user outcomes |
| **User Risk Profile** | Identify high-risk users and departments | Department risk scores, user scatter plot, compromise timeline |
| **Training Compliance** | Training assignment and completion tracking | Completion rate, status by department, overdue users |
| **Payload Effectiveness** | Attack technique and payload analysis | Predicted vs actual rates, payload treemap, complexity scatter |

## Interactive Filters

Every page includes interactive slicers for filtering:

- **Date range** — filter by simulation launch date or event date
- **Attack type / technique** — focus on specific campaign types
- **Department** — drill into organizational units
- **Cross-filtering** — click any visual to filter all others on the page

## Data Model

The semantic model connects to 9 Parquet tables in your ADLS Gen2 `curated` container:

```
                    ┌──────────┐
                    │  users   │
                    └────┬─────┘
         ┌───────────────┼───────────────┐
         │               │               │
┌────────▼───────┐ ┌─────▼─────┐ ┌───────▼──────────┐
│repeatOffenders │ │simulation │ │trainingUser      │
│                │ │UserCoverage│ │Coverage          │
└────────────────┘ └───────────┘ └──────────────────┘

┌────────────┐     ┌────────────────┐     ┌──────────┐
│simulations │◄────│simulationUsers │────►│  users   │
└──────┬─────┘     └───────┬────────┘     └──────────┘
       │                   │
┌──────▼─────┐     ┌───────▼────────────┐
│  payloads  │     │simulationUserEvents│
└────────────┘     └────────────────────┘

┌────────────┐
│  trainings │  (standalone reference)
└────────────┘
```

## DAX Measures (12 included)

| Measure | Description |
|---------|-------------|
| Compromise Rate | % of users compromised across simulations |
| Training Completion Rate | % of assigned trainings completed |
| Avg Training Duration | Average training duration in minutes |
| Repeat Offender Count | Users compromised more than once |
| Active Simulations | Simulations with succeeded status |
| Simulation Count | Total number of simulations |
| Monthly Compromised Users | Month-to-date compromised count |
| Phish Report Rate | % of users who reported phishing |
| Department Risk Score | Compromise rate by department (0-100) |
| Actual vs Predicted Variance | Difference between actual and predicted compromise rates |
| Click Rate | % of users who clicked the phishing link |
| Total Users Targeted | Sum of all users targeted across simulations |

## Customizing

Since PBIR is JSON-based, you can:

- **Edit visuals** directly in Power BI Desktop
- **Modify DAX measures** in the TMDL files under `MDOAttackSimulation.SemanticModel/definition/tables/_Measures.tmdl`
- **Add relationships** in `relationships.tmdl`
- **Add tables** by creating new `.tmdl` files in the `tables/` folder
- **Version control** all changes with Git (every visual is a separate JSON file)

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Cannot find parameter" error | Ensure Developer Mode and PBIR preview features are enabled |
| Authentication failure | Verify you have Storage Blob Data Reader role on the ADLS Gen2 account |
| Empty tables | Confirm the function has run at least once and data exists in `curated/` container |
| "Cannot connect to data source" | Check that `StorageAccountUrl` is the DFS endpoint (`.dfs.core.windows.net`) |
| Firewall error | Add your IP to the storage account network rules temporarily |

## File Structure

```
reports/
├── MDOAttackSimulation.pbip                    # Open this file in Power BI Desktop
├── MDOAttackSimulation.Report/
│   ├── definition.pbir                         # Report → Semantic Model link
│   └── definition/
│       ├── report.json                         # Theme and report settings
│       ├── version.json                        # Format version
│       └── pages/                              # 5 report pages with visuals
│           ├── pages.json                      # Page order
│           ├── {pageId}/page.json              # Page definition
│           └── {pageId}/visuals/{id}/visual.json
├── MDOAttackSimulation.SemanticModel/
│   ├── definition.pbism                        # Semantic model manifest
│   └── definition/
│       ├── database.tmdl                       # Compatibility level
│       ├── model.tmdl                          # Model configuration
│       ├── expressions.tmdl                    # StorageAccountUrl parameter
│       ├── relationships.tmdl                  # 7 table relationships
│       └── tables/                             # 9 data tables + _Measures
└── README.md                                   # This file
```
