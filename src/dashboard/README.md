# Streamlit Executive Dashboard

Browser-based executive dashboard for MDO Attack Simulation Training data — a lightweight alternative to the Power BI reports.

> **Note:** This is a **starter dashboard** — the authors are security engineers, not data visualization designers. You are encouraged to customize the visuals, layout, and styling to match your organization's reporting standards.

## Features

- **5 Dashboard Pages** — Executive Dashboard, Simulation Analysis, User Risk Profile, Training Compliance, Payload Effectiveness
- **No Licenses Required** — Just a browser and a URL
- **Azure AD Authentication** — Secured via App Service EasyAuth
- **Same Data** — Reads Parquet files from the same ADLS Gen2 storage the Function writes to
- **Fluent Design** — Microsoft-inspired styling with Segoe UI, blue accents, card-based layout

## Local Development

### Prerequisites

- Python 3.11+
- Azure CLI (logged in with `az login`)
- Access to the ADLS Gen2 storage account (Storage Blob Data Reader role)

### Setup

```bash
cd src/dashboard
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # macOS/Linux

pip install -r requirements.txt
```

### Configure

Set environment variables:

```bash
export STORAGE_ACCOUNT_URL="https://<your-account>.dfs.core.windows.net"
export CONTAINER_NAME="curated"
```

Or on Windows PowerShell:

```powershell
$env:STORAGE_ACCOUNT_URL = "https://<your-account>.dfs.core.windows.net"
$env:CONTAINER_NAME = "curated"
```

### Run

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`.

## Deployment

See [Dashboard Setup Guide](../../docs/DASHBOARD_SETUP.md) for Azure deployment instructions, or use the quick deploy scripts:

```powershell
# PowerShell
.\scripts\deploy-dashboard.ps1 -ResourceGroup "rg-mdo-attack-simulation" -DashboardClientId "<client-id>"

# Bash
./scripts/deploy-dashboard.sh -g "rg-mdo-attack-simulation" -c "<client-id>"
```

## Project Structure

```
src/dashboard/
├── app.py                      # Main entry point
├── requirements.txt            # Python dependencies
├── startup.sh                  # Azure App Service startup
├── .streamlit/config.toml      # Streamlit theme configuration
├── data/
│   └── loader.py               # ADLS Gen2 Parquet reader (cached)
├── pages/
│   ├── 1_Executive_Dashboard.py
│   ├── 2_Simulation_Analysis.py
│   ├── 3_User_Risk_Profile.py
│   ├── 4_Training_Compliance.py
│   └── 5_Payload_Effectiveness.py
├── components/
│   ├── metrics.py              # KPI card components
│   ├── charts.py               # Plotly chart wrappers
│   ├── filters.py              # Sidebar filter components
│   └── layout.py               # Page layout helpers
└── theme/
    └── style.css               # Fluent Design CSS
```
