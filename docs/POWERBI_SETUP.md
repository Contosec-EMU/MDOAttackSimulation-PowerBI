# Power BI Setup Guide — MDO Attack Simulation Training

Connect Power BI to Azure Data Lake Storage Gen2 (ADLS Gen2) Parquet files ingested by the MDO Attack Simulation Training pipeline.

> **Data Pipeline**: Azure Function (daily at 2:00 AM UTC) → Microsoft Graph API → ADLS Gen2 Parquet → **Power BI**

---

## Table of Contents

- [1. Prerequisites](#1-prerequisites)
- [2. Connecting to Data](#2-connecting-to-data)
- [3. Data Model](#3-data-model)
- [4. Recommended DAX Measures](#4-recommended-dax-measures)
- [5. Suggested Report Pages](#5-suggested-report-pages)
- [6. Scheduled Refresh](#6-scheduled-refresh)
- [7. Troubleshooting](#7-troubleshooting)

---

## 1. Prerequisites

| Requirement | Details |
|---|---|
| **Power BI Desktop** | [Latest version](https://powerbi.microsoft.com/desktop/) (October 2023+ recommended for Parquet support) |
| **ADLS Gen2 Storage Account** | The storage account deployed by this project (e.g., `mdoastdl<suffix>`) |
| **Entra ID Account** | Organizational account with **Storage Blob Data Reader** role on the storage account or `curated` container |
| **Power BI Pro or Premium** | Required for scheduled refresh in Power BI Service |
| **On-Premises Data Gateway** | Required only if the storage account has network restrictions **and** you are using Power BI Pro (not Premium). See [Gateway Setup](GATEWAY_VM_SETUP.md) |

### Verify Storage Access

Before opening Power BI, confirm you can access the storage account:

```
Storage Account URL:  https://<storageAccountName>.dfs.core.windows.net/
Container:            curated
```

> **Important:** Each user who needs to access the data from Power BI must have the **Storage Blob Data Reader** role on the ADLS Gen2 storage account. This is not granted automatically — an administrator must assign it.
>
> To grant access via Azure CLI:
>
> ```powershell
> # Grant a user Storage Blob Data Reader on the data lake
> $USER_ID = az ad user show --id "user@yourorg.com" --query id -o tsv
> $STORAGE_ID = az storage account show --name "<storageAccountName>" --query id -o tsv
> az role assignment create --role "Storage Blob Data Reader" --assignee $USER_ID --scope $STORAGE_ID
> ```
>
> Or via **Azure Portal → Storage account → Access Control (IAM) → Add role assignment → Storage Blob Data Reader**.

---

## 2. Connecting to Data

> 💡 **Recommended: Use the Pre-Built Report Template**
>
> The easiest way to connect is using the included `.pbip` project file, which has all 9 tables, relationships, and DAX measures pre-configured. See the [reports README](../reports/README.md) for quick start instructions.
>
> The manual steps below are for users who want to build their own report from scratch.

### Step 1: Open Power BI Desktop and Connect

1. Open **Power BI Desktop**
2. Click **Get Data** → **Azure** → **Azure Data Lake Storage Gen2**
3. Click **Connect**

<!-- Screenshot: Get Data dialog with Azure Data Lake Storage Gen2 selected -->

### Step 2: Enter the Storage URL

1. In the **URL** field, enter your **DFS endpoint** (not the Blob endpoint):
   ```
   https://<storageAccountName>.dfs.core.windows.net/
   ```
   > ⚠️ **Important:** Use `.dfs.core.windows.net` — the `.blob.core.windows.net` endpoint will return errors with ADLS Gen2.
2. Click **OK**

<!-- Screenshot: ADLS Gen2 connection dialog with URL field -->

### Step 3: Authenticate

1. Select the **Organizational account** tab
2. Click **Sign in** and authenticate with your Entra ID credentials
3. In the **"Select which level to apply these settings to"** dropdown, choose the **root storage account URL** (e.g., `https://<storageAccountName>.dfs.core.windows.net/`) — this avoids being prompted again for each table subfolder
4. Click **Connect**

<!-- Screenshot: Authentication dialog showing Organizational account tab -->

### Step 4: Navigate to Data

The Navigator pane displays the storage account containers. Expand the **curated** container to see the 9 table folders:

```
curated/
├── repeatOffenders/
├── simulationUserCoverage/
├── trainingUserCoverage/
├── simulations/
├── simulationUsers/
├── simulationUserEvents/
├── trainings/
├── payloads/
└── users/
```

### Step 5: Load Tables Using Power Query

For each table, create a query that combines all date-partitioned Parquet files into a single table. Click **Transform Data** to open Power Query Editor, then create a new **Blank Query** for each table.

#### Power Query (M) — Generic Template

Replace `<tableName>` with each of the 9 table names:

```powerquery
let
    Source = AzureStorage.DataLake("https://<storageAccountName>.dfs.core.windows.net/curated/<tableName>"),
    #"Filtered to Parquet" = Table.SelectRows(Source, each Text.EndsWith([Name], ".parquet")),
    #"Combined Files" = Table.Combine(
        Table.TransformColumns(#"Filtered to Parquet", {{"Content", each Parquet.Document(_)}})
    )
in
    #"Combined Files"
```

#### Power Query (M) — All 9 Tables

Create one query per table (replace `<storageAccountName>` with your actual account name):

<details>
<summary><strong>repeatOffenders</strong></summary>

```powerquery
let
    Source = AzureStorage.DataLake("https://<storageAccountName>.dfs.core.windows.net/curated/repeatOffenders"),
    #"Filtered to Parquet" = Table.SelectRows(Source, each Text.EndsWith([Name], ".parquet")),
    #"Combined Files" = Table.Combine(
        Table.TransformColumns(#"Filtered to Parquet", {{"Content", each Parquet.Document(_)}})
    )
in
    #"Combined Files"
```
</details>

<details>
<summary><strong>simulationUserCoverage</strong></summary>

```powerquery
let
    Source = AzureStorage.DataLake("https://<storageAccountName>.dfs.core.windows.net/curated/simulationUserCoverage"),
    #"Filtered to Parquet" = Table.SelectRows(Source, each Text.EndsWith([Name], ".parquet")),
    #"Combined Files" = Table.Combine(
        Table.TransformColumns(#"Filtered to Parquet", {{"Content", each Parquet.Document(_)}})
    )
in
    #"Combined Files"
```
</details>

<details>
<summary><strong>trainingUserCoverage</strong></summary>

```powerquery
let
    Source = AzureStorage.DataLake("https://<storageAccountName>.dfs.core.windows.net/curated/trainingUserCoverage"),
    #"Filtered to Parquet" = Table.SelectRows(Source, each Text.EndsWith([Name], ".parquet")),
    #"Combined Files" = Table.Combine(
        Table.TransformColumns(#"Filtered to Parquet", {{"Content", each Parquet.Document(_)}})
    )
in
    #"Combined Files"
```
</details>

<details>
<summary><strong>simulations</strong></summary>

```powerquery
let
    Source = AzureStorage.DataLake("https://<storageAccountName>.dfs.core.windows.net/curated/simulations"),
    #"Filtered to Parquet" = Table.SelectRows(Source, each Text.EndsWith([Name], ".parquet")),
    #"Combined Files" = Table.Combine(
        Table.TransformColumns(#"Filtered to Parquet", {{"Content", each Parquet.Document(_)}})
    )
in
    #"Combined Files"
```
</details>

<details>
<summary><strong>simulationUsers</strong></summary>

```powerquery
let
    Source = AzureStorage.DataLake("https://<storageAccountName>.dfs.core.windows.net/curated/simulationUsers"),
    #"Filtered to Parquet" = Table.SelectRows(Source, each Text.EndsWith([Name], ".parquet")),
    #"Combined Files" = Table.Combine(
        Table.TransformColumns(#"Filtered to Parquet", {{"Content", each Parquet.Document(_)}})
    )
in
    #"Combined Files"
```
</details>

<details>
<summary><strong>simulationUserEvents</strong></summary>

```powerquery
let
    Source = AzureStorage.DataLake("https://<storageAccountName>.dfs.core.windows.net/curated/simulationUserEvents"),
    #"Filtered to Parquet" = Table.SelectRows(Source, each Text.EndsWith([Name], ".parquet")),
    #"Combined Files" = Table.Combine(
        Table.TransformColumns(#"Filtered to Parquet", {{"Content", each Parquet.Document(_)}})
    )
in
    #"Combined Files"
```
</details>

<details>
<summary><strong>trainings</strong></summary>

```powerquery
let
    Source = AzureStorage.DataLake("https://<storageAccountName>.dfs.core.windows.net/curated/trainings"),
    #"Filtered to Parquet" = Table.SelectRows(Source, each Text.EndsWith([Name], ".parquet")),
    #"Combined Files" = Table.Combine(
        Table.TransformColumns(#"Filtered to Parquet", {{"Content", each Parquet.Document(_)}})
    )
in
    #"Combined Files"
```
</details>

<details>
<summary><strong>payloads</strong></summary>

```powerquery
let
    Source = AzureStorage.DataLake("https://<storageAccountName>.dfs.core.windows.net/curated/payloads"),
    #"Filtered to Parquet" = Table.SelectRows(Source, each Text.EndsWith([Name], ".parquet")),
    #"Combined Files" = Table.Combine(
        Table.TransformColumns(#"Filtered to Parquet", {{"Content", each Parquet.Document(_)}})
    )
in
    #"Combined Files"
```
</details>

<details>
<summary><strong>users</strong></summary>

```powerquery
let
    Source = AzureStorage.DataLake("https://<storageAccountName>.dfs.core.windows.net/curated/users"),
    #"Filtered to Parquet" = Table.SelectRows(Source, each Text.EndsWith([Name], ".parquet")),
    #"Combined Files" = Table.Combine(
        Table.TransformColumns(#"Filtered to Parquet", {{"Content", each Parquet.Document(_)}})
    )
in
    #"Combined Files"
```
</details>

### Step 6: Load Only the Latest Snapshot (Optional)

If you only want the most recent day's data instead of all historical snapshots, add a filter step to keep only the latest `snapshotDateUtc`:

```powerquery
let
    Source = AzureStorage.DataLake("https://<storageAccountName>.dfs.core.windows.net/curated/<tableName>"),
    #"Filtered to Parquet" = Table.SelectRows(Source, each Text.EndsWith([Name], ".parquet")),
    #"Combined Files" = Table.Combine(
        Table.TransformColumns(#"Filtered to Parquet", {{"Content", each Parquet.Document(_)}})
    ),
    #"Max Date" = List.Max(#"Combined Files"[snapshotDateUtc]),
    #"Latest Only" = Table.SelectRows(#"Combined Files", each [snapshotDateUtc] = #"Max Date")
in
    #"Latest Only"
```

### Step 7: Set Column Data Types

After loading, verify that Power BI detected the correct types. The Parquet schema should auto-map, but confirm:

| Power BI Type | Columns |
|---|---|
| **Date/Time** | `snapshotDateUtc`, `createdDateTime`, `launchDateTime`, `completionDateTime`, `lastModifiedDateTime`, `compromisedDateTime`, `reportedPhishDateTime`, `latestSimulationDateTime`, `eventDateTime` |
| **True/False** | `isAutomated`, `isCompromised`, `accountEnabled`, `hasEvaluation`, `isCurrentEvent`, `isControversial` |
| **Whole Number** | `repeatOffenceCount`, `simulationCount`, `clickCount`, `compromisedCount`, `assignedTrainingsCount`, `completedTrainingsCount`, `inProgressTrainingsCount`, `notStartedTrainingsCount`, `durationInDays`, `durationInMinutes`, `reportTotalUserCount`, `reportCompromisedCount`, `reportClickCount`, `reportReportedCount` |
| **Decimal Number** | `predictedCompromiseRate` |
| **Text** | All other columns (IDs, names, emails, descriptions, etc.) |

---

## 3. Data Model

### Table Schemas

#### Core Tables (Always Populated)

**repeatOffenders** — Users who have been compromised in multiple simulations

| Column | Type | Description |
|---|---|---|
| snapshotDateUtc | datetime | Date this data was captured |
| userId | string | Entra ID user identifier |
| displayName | string | User's display name |
| email | string | User's email address |
| repeatOffenceCount | int32 | Number of times compromised |

**simulationUserCoverage** — Aggregated simulation exposure per user

| Column | Type | Description |
|---|---|---|
| snapshotDateUtc | datetime | Date this data was captured |
| userId | string | Entra ID user identifier |
| displayName | string | User's display name |
| email | string | User's email address |
| simulationCount | int32 | Total simulations targeting this user |
| latestSimulationDateTime | datetime | Most recent simulation date |
| clickCount | int32 | Total phishing link clicks |
| compromisedCount | int32 | Total times compromised |

**trainingUserCoverage** — Training assignment and completion per user

| Column | Type | Description |
|---|---|---|
| snapshotDateUtc | datetime | Date this data was captured |
| userId | string | Entra ID user identifier |
| displayName | string | User's display name |
| email | string | User's email address |
| assignedTrainingsCount | int32 | Trainings assigned |
| completedTrainingsCount | int32 | Trainings completed |
| inProgressTrainingsCount | int32 | Trainings in progress |
| notStartedTrainingsCount | int32 | Trainings not started |

#### Extended Tables (Requires `SYNC_SIMULATIONS=true`)

**simulations** — Attack simulation campaign details

| Column | Type | Description |
|---|---|---|
| snapshotDateUtc | datetime | Date this data was captured |
| simulationId | string | Unique simulation identifier |
| displayName | string | Simulation campaign name |
| description | string | Simulation description |
| status | string | Current status (e.g., succeeded, draft) |
| attackType | string | Attack type (e.g., phish, malware) |
| attackTechnique | string | Technique used (e.g., credentialHarvest) |
| createdDateTime | datetime | When the simulation was created |
| launchDateTime | datetime | When the simulation was launched |
| completionDateTime | datetime | When the simulation completed |
| lastModifiedDateTime | datetime | Last modification timestamp |
| isAutomated | bool | Whether this is an automated simulation |
| automationId | string | Automation rule identifier |
| durationInDays | int32 | Simulation duration |
| payloadId | string | Associated payload identifier |
| payloadDisplayName | string | Payload display name |
| reportTotalUserCount | int32 | Total targeted users |
| reportCompromisedCount | int32 | Users who were compromised |
| reportClickCount | int32 | Users who clicked the link |
| reportReportedCount | int32 | Users who reported the phish |
| createdById | string | Creator user ID |
| createdByDisplayName | string | Creator display name |
| createdByEmail | string | Creator email |
| lastModifiedById | string | Last modifier user ID |
| lastModifiedByDisplayName | string | Last modifier display name |
| lastModifiedByEmail | string | Last modifier email |

**simulationUsers** — Per-user results within each simulation

| Column | Type | Description |
|---|---|---|
| snapshotDateUtc | datetime | Date this data was captured |
| simulationId | string | Parent simulation identifier |
| userId | string | Entra ID user identifier |
| email | string | User's email address |
| displayName | string | User's display name |
| compromisedDateTime | datetime | When the user was compromised (null if not) |
| reportedPhishDateTime | datetime | When the user reported the phish (null if not) |
| assignedTrainingsCount | int32 | Remediation trainings assigned |
| completedTrainingsCount | int32 | Remediation trainings completed |
| inProgressTrainingsCount | int32 | Remediation trainings in progress |
| isCompromised | bool | Whether the user was compromised |

**simulationUserEvents** — Granular user interaction events

| Column | Type | Description |
|---|---|---|
| snapshotDateUtc | datetime | Date this data was captured |
| simulationId | string | Parent simulation identifier |
| userId | string | Entra ID user identifier |
| eventName | string | Event type (e.g., linkClicked, credentialSupplied) |
| eventDateTime | datetime | When the event occurred |
| browser | string | Browser used |
| ipAddress | string | Source IP address |
| osPlatformDeviceDetails | string | OS and device information |

**trainings** — Training content catalog

| Column | Type | Description |
|---|---|---|
| snapshotDateUtc | datetime | Date this data was captured |
| trainingId | string | Unique training identifier |
| displayName | string | Training name |
| description | string | Training description |
| durationInMinutes | int32 | Training duration |
| source | string | Content source (e.g., microsoft, custom) |
| type | string | Training type |
| availabilityStatus | string | Availability status |
| hasEvaluation | bool | Whether training has an evaluation |
| lastModifiedDateTime | datetime | Last modification timestamp |
| createdById | string | Creator user ID |
| createdByDisplayName | string | Creator display name |
| createdByEmail | string | Creator email |
| lastModifiedById | string | Last modifier user ID |
| lastModifiedByDisplayName | string | Last modifier display name |
| lastModifiedByEmail | string | Last modifier email |

**payloads** — Phishing payload definitions

| Column | Type | Description |
|---|---|---|
| snapshotDateUtc | datetime | Date this data was captured |
| payloadId | string | Unique payload identifier |
| displayName | string | Payload name |
| description | string | Payload description |
| simulationAttackType | string | Attack type |
| platform | string | Target platform (e.g., email) |
| status | string | Payload status |
| source | string | Content source |
| predictedCompromiseRate | float64 | Microsoft's predicted compromise rate (0.0–1.0) |
| complexity | string | Payload complexity level |
| technique | string | Attack technique |
| theme | string | Payload theme |
| brand | string | Impersonated brand |
| industry | string | Target industry |
| isCurrentEvent | bool | Based on a current real-world event |
| isControversial | bool | Flagged as controversial |
| lastModifiedDateTime | datetime | Last modification timestamp |
| createdById | string | Creator user ID |
| createdByDisplayName | string | Creator display name |
| createdByEmail | string | Creator email |
| lastModifiedById | string | Last modifier user ID |
| lastModifiedByDisplayName | string | Last modifier display name |
| lastModifiedByEmail | string | Last modifier email |

**users** — Entra ID user directory information

| Column | Type | Description |
|---|---|---|
| snapshotDateUtc | datetime | Date this data was captured |
| userId | string | Entra ID user identifier |
| displayName | string | User's display name |
| givenName | string | First name |
| surname | string | Last name |
| mail | string | Email address |
| department | string | Department |
| companyName | string | Company name |
| city | string | City |
| country | string | Country |
| jobTitle | string | Job title |
| accountEnabled | bool | Whether account is active |

### Relationships (Star Schema)

```
                              ┌──────────────────────┐
                              │       payloads       │
                              │                      │
                              │  payloadId (PK)      │
                              │  displayName         │
                              │  simulationAttackType│
                              │  predictedCompromise │
                              │  technique           │
                              └──────────┬───────────┘
                                         │ payloadId
                                         │
┌───────────────────┐         ┌──────────┴───────────┐         ┌───────────────────────┐
│  repeatOffenders  │         │     simulations      │         │      trainings        │
│                   │         │       (FACT)          │         │                       │
│  userId           │         │  simulationId (PK)   │         │  trainingId (PK)      │
│  email            │         │  payloadId (FK)      │         │  displayName          │
│  repeatOffence    │         │  attackType          │         │  durationInMinutes    │
│  Count            │         │  status              │         │  source               │
└────────┬──────────┘         │  reportCompromised   │         └───────────┬───────────┘
         │                    │  Count               │                     │
         │ userId             └──────────┬───────────┘                     │
         │                               │ simulationId                    │
         │                               │                                 │
         │                    ┌──────────┴───────────┐                     │
         │                    │  simulationUsers     │                     │
         │                    │      (FACT)          │                     │
         │                    │                      │                     │
         │                    │  simulationId (FK)   │                     │
         │                    │  userId (FK)         │                     │
         │                    │  isCompromised       │                     │
         │                    │  assignedTrainings   │                     │
         │                    │  Count               │                     │
         │                    └──────────┬───────────┘                     │
         │                               │                                 │
         │              simulationId     │    userId                       │
         │              + userId         │                                 │
         │                               │                                 │
         │          ┌────────────────────┤                                 │
         │          │                    │                                 │
         │   ┌──────┴──────────────┐  ┌──┴──────────────────┐             │
         │   │ simulationUser      │  │       users         │             │
         │   │ Events              │  │     (DIMENSION)     │             │
         │   │                     │  │                     │             │
         │   │ simulationId (FK)   │  │  userId (PK)        │◄────────────┘
         │   │ userId (FK)         │  │  displayName        │   (via user
         │   │ eventName           │  │  mail               │    assignments)
         │   │ eventDateTime       │  │  department         │
         └───┤ browser             │  │  jobTitle           │
   (via      └────────────────────┘  │  country            │
    userId)                           └──────────┬──────────┘
                                                 │ userId / mail
                                    ┌────────────┼────────────┐
                                    │            │            │
                              ┌─────┴──────┐  ┌─┴──────────┐ │
                              │simulation  │  │training     │ │
                              │UserCoverage│  │UserCoverage │ │
                              │            │  │             │ │
                              │userId (FK) │  │userId (FK)  │ │
                              │simulation  │  │assigned     │ │
                              │Count       │  │Trainings    │ │
                              │clickCount  │  │Count        │ │
                              │compromised │  │completed    │ │
                              │Count       │  │Trainings    │ │
                              └────────────┘  │Count        │ │
                                              └─────────────┘ │
                                                              │
                                              ┌───────────────┘
                                              │
                                    ┌─────────┴──────────┐
                                    │  repeatOffenders   │
                                    │                    │
                                    │  userId (FK)       │
                                    │  repeatOffence     │
                                    │  Count             │
                                    └────────────────────┘
```

### Configuring Relationships in Power BI

In Power BI Desktop, go to **Model** view and create these relationships:

| From Table | From Column | To Table | To Column | Cardinality | Cross-Filter |
|---|---|---|---|---|---|
| simulationUsers | simulationId | simulations | simulationId | Many-to-One | Single |
| simulationUsers | userId | users | userId | Many-to-One | Single |
| simulationUserEvents | simulationId, userId | simulationUsers | simulationId, userId | Many-to-One | Single |
| simulations | payloadId | payloads | payloadId | Many-to-One | Single |
| simulationUserCoverage | userId | users | userId | Many-to-One | Single |
| trainingUserCoverage | userId | users | userId | Many-to-One | Single |
| repeatOffenders | userId | users | userId | Many-to-One | Single |

> ⚠️ **Note on composite keys**: Power BI does not natively support multi-column relationships. For `simulationUserEvents → simulationUsers`, create a calculated column in both tables:
> ```dax
> SimUserKey = simulationUserEvents[simulationId] & "|" & simulationUserEvents[userId]
> ```
> Then create the relationship on the `SimUserKey` column.

> ⚠️ **Note on `snapshotDateUtc`**: If loading multiple snapshots, filter all tables to the same `snapshotDateUtc` to ensure consistency. Alternatively, load only the latest snapshot (see [Step 6](#step-6-load-only-the-latest-snapshot-optional)).

<!-- Screenshot: Power BI Model view showing all relationships configured -->

---

## 4. Recommended DAX Measures

Create a dedicated measures table in Power BI for organization: **Modeling** → **New Table** → `_Measures = ROW("Value", 0)`.

> ⚠️ **Note:** Do not use `Measures` as the table name — it is a reserved word in TMDL/PBIR format and will cause errors when saving as a `.pbip` project. Use `_Measures` instead.

### Compromise Rate

Percentage of targeted users who were compromised across all simulations.

```dax
Compromise Rate =
DIVIDE(
    COUNTROWS(FILTER(simulationUsers, simulationUsers[isCompromised] = TRUE())),
    COUNTROWS(simulationUsers),
    0
)
```

### Training Completion Rate

Percentage of assigned trainings that have been completed.

```dax
Training Completion Rate =
DIVIDE(
    SUM(trainingUserCoverage[completedTrainingsCount]),
    SUM(trainingUserCoverage[assignedTrainingsCount]),
    0
)
```

### Average Training Duration (Minutes)

Average duration of trainings in the catalog.

```dax
Avg Training Duration =
AVERAGE(trainings[durationInMinutes])
```

### Repeat Offender Count

Total number of users who have been compromised more than once.

```dax
Repeat Offender Count =
COUNTROWS(
    FILTER(repeatOffenders, repeatOffenders[repeatOffenceCount] > 1)
)
```

### Active Simulations Count

Number of simulations that have launched and are not yet completed.

```dax
Active Simulations =
COUNTROWS(
    FILTER(
        simulations,
        simulations[status] = "succeeded"
            && NOT(ISBLANK(simulations[launchDateTime]))
    )
)
```

### Simulations by Attack Type

Count of simulations grouped by attack type (use with a bar chart on `attackType`).

```dax
Simulation Count by Attack Type =
COUNTROWS(simulations)
```

### Monthly Compromise Trend

Compromised users by month for trend analysis.

```dax
Monthly Compromised Users =
CALCULATE(
    COUNTROWS(FILTER(simulationUsers, simulationUsers[isCompromised] = TRUE())),
    DATESMTD(simulationUsers[compromisedDateTime])
)
```

### Phish Report Rate

Percentage of users who correctly reported the phishing simulation.

```dax
Phish Report Rate =
DIVIDE(
    SUM(simulations[reportReportedCount]),
    SUM(simulations[reportTotalUserCount]),
    0
)
```

### Department Risk Score

Risk score per department — higher score means more compromises relative to simulation exposure.

```dax
Department Risk Score =
VAR _compromised =
    CALCULATE(
        COUNTROWS(FILTER(simulationUsers, simulationUsers[isCompromised] = TRUE())),
        USERELATIONSHIP(simulationUsers[userId], users[userId])
    )
VAR _total =
    CALCULATE(
        COUNTROWS(simulationUsers),
        USERELATIONSHIP(simulationUsers[userId], users[userId])
    )
RETURN
    DIVIDE(_compromised, _total, 0) * 100
```

### Predicted vs Actual Compromise Rate

Compare payload predicted compromise rates with actual results.

```dax
Actual vs Predicted Variance =
VAR _actual =
    DIVIDE(
        SUM(simulations[reportCompromisedCount]),
        SUM(simulations[reportTotalUserCount]),
        0
    )
VAR _predicted = AVERAGE(payloads[predictedCompromiseRate])
RETURN
    _actual - _predicted
```

---

## 5. Suggested Report Pages

### Page 1: Executive Dashboard

**Purpose**: High-level KPIs for security leadership.

| Visual | Measure/Data | Position |
|---|---|---|
| **KPI Card** — Compromise Rate | `[Compromise Rate]` formatted as % | Top row |
| **KPI Card** — Training Completion | `[Training Completion Rate]` formatted as % | Top row |
| **KPI Card** — Repeat Offenders | `[Repeat Offender Count]` | Top row |
| **KPI Card** — Active Simulations | `[Active Simulations]` | Top row |
| **Line Chart** — Monthly Trend | X: Month, Y: `[Monthly Compromised Users]` | Middle |
| **Donut Chart** — Attack Types | Legend: `attackType`, Values: `[Simulation Count by Attack Type]` | Middle right |
| **Table** — Top 10 Repeat Offenders | `repeatOffenders[displayName]`, `repeatOffenders[email]`, `repeatOffenders[repeatOffenceCount]`, sorted desc | Bottom |

<!-- Screenshot: Executive Dashboard layout with KPI cards across top, trend chart in middle, table at bottom -->

### Page 2: Simulation Analysis

**Purpose**: Detailed per-simulation performance metrics.

| Visual | Measure/Data | Position |
|---|---|---|
| **Slicer** — Attack Type | `simulations[attackType]` | Top filter bar |
| **Slicer** — Date Range | `simulations[launchDateTime]` | Top filter bar |
| **Table** — Simulation Details | `displayName`, `attackType`, `attackTechnique`, `launchDateTime`, `reportTotalUserCount`, `reportCompromisedCount`, `reportClickCount`, `reportReportedCount` | Main area |
| **Clustered Bar Chart** — Compromise Rate by Simulation | X: `displayName`, Y: compromise rate per simulation | Middle |
| **Stacked Bar Chart** — User Outcomes | X: simulation, Y: stacked counts (compromised, clicked, reported, no action) | Bottom |
| **Card** — Phish Report Rate | `[Phish Report Rate]` | Sidebar |

<!-- Screenshot: Simulation Analysis page with filters at top, detail table, and bar charts -->

### Page 3: User Risk Profile

**Purpose**: Identify high-risk users and departments.

| Visual | Measure/Data | Position |
|---|---|---|
| **Slicer** — Department | `users[department]` | Top filter bar |
| **Bar Chart** — Department Risk Score | X: `department`, Y: `[Department Risk Score]`, sorted desc | Left |
| **Scatter Plot** — User Risk | X: `simulationUserCoverage[simulationCount]`, Y: `simulationUserCoverage[compromisedCount]`, Size: `repeatOffenders[repeatOffenceCount]` | Center |
| **Table** — High Risk Users | Users with `compromisedCount > 0`, showing `displayName`, `department`, `simulationCount`, `compromisedCount`, `repeatOffenceCount` | Right |
| **Timeline** — Compromise Events | `simulationUserEvents` filtered to compromise events, by `eventDateTime` | Bottom |

<!-- Screenshot: User Risk Profile with department bar chart on left, scatter plot center, user table right -->

### Page 4: Training Compliance

**Purpose**: Track training assignment and completion across the organization.

| Visual | Measure/Data | Position |
|---|---|---|
| **KPI Card** — Overall Completion Rate | `[Training Completion Rate]` | Top |
| **Gauge** — Assigned vs Completed | Target: `SUM(assignedTrainingsCount)`, Value: `SUM(completedTrainingsCount)` | Top |
| **Stacked Bar** — Training Status by Department | Department on axis, stacked: completed, in progress, not started | Middle |
| **Table** — Users with Overdue Trainings | Filter `notStartedTrainingsCount > 0`, show `displayName`, `department`, `assignedTrainingsCount`, `notStartedTrainingsCount` | Bottom left |
| **Scatter Plot** — Training vs Compromise Correlation | X: `completedTrainingsCount`, Y: `compromisedCount` per user | Bottom right |

<!-- Screenshot: Training Compliance page with gauge at top, department stacked bars, and overdue table -->

### Page 5: Payload Effectiveness

**Purpose**: Analyze which attack techniques and payloads are most effective.

| Visual | Measure/Data | Position |
|---|---|---|
| **Slicer** — Attack Technique | `payloads[technique]` | Top filter bar |
| **Bar Chart** — Predicted vs Actual | Payload name on axis, paired bars for `predictedCompromiseRate` vs actual rate | Main area |
| **Treemap** — Payloads by Theme | Size: simulation count using this payload, Color: compromise rate | Middle left |
| **Table** — Payload Details | `displayName`, `technique`, `theme`, `brand`, `complexity`, `predictedCompromiseRate` | Middle right |
| **Card** — Actual vs Predicted Variance | `[Actual vs Predicted Variance]` | Sidebar |
| **Scatter Plot** — Complexity vs Effectiveness | X: `complexity`, Y: actual compromise rate | Bottom |

<!-- Screenshot: Payload Effectiveness page with paired bar chart, treemap, and payload table -->

---

## 6. Scheduled Refresh

### Publishing to Power BI Service

1. In Power BI Desktop, click **Publish** → select your workspace
2. Open the report in [Power BI Service](https://app.powerbi.com)

### Configure Data Source Credentials

1. Go to **Settings** (gear icon) → **Manage connections and gateways**
2. Find your ADLS Gen2 connection
3. Under **Authentication method**, select **OAuth2**
4. Click **Sign in** with your Entra ID account (must have Storage Blob Data Reader)
5. Click **Apply**

<!-- Screenshot: Power BI Service dataset settings showing OAuth2 credential configuration -->

### Set Up Scheduled Refresh

1. Go to your **Semantic model** → **Settings** → **Refresh**
2. Turn on **Keep your data up to date**
3. Set **Refresh frequency**: Daily
4. Set **Time**: **3:00 AM UTC** (1 hour after the Azure Function runs at 2:00 AM UTC)
5. Configure a secondary time slot if desired (e.g., 12:00 PM UTC for mid-day refresh)
6. Add your email to **Send refresh failure notifications to**
7. Click **Apply**

<!-- Screenshot: Scheduled refresh configuration showing daily at 3:00 AM UTC -->

> **Why 3:00 AM?** The Azure Function ingests data at 2:00 AM UTC. Adding a 1-hour buffer ensures all Parquet files are fully written before Power BI reads them.

### On-Premises Data Gateway

A gateway is required if **any** of these apply:

| Condition | Gateway Required? |
|---|---|
| Power BI Pro (no Premium capacity) accessing ADLS Gen2 | **Yes** |
| Storage account has network ACLs restricting public access | **Yes** |
| Power BI Premium with `enablePowerBiAccess=true` in Bicep | **No** |
| Storage account allows public network access | **No** |

#### Gateway Setup (If Required)

1. **Install the gateway** on a VM with network access to the storage account — see [Microsoft: On-Premises Data Gateway](https://learn.microsoft.com/en-us/power-bi/connect-data/service-gateway-onprem)
2. **Register the gateway** in Power BI Service under **Settings** → **Manage connections and gateways**
3. **Add the data source**:
   - **Type**: Azure Data Lake Storage Gen2
   - **URL**: `https://<storageAccountName>.dfs.core.windows.net/`
   - **Authentication**: OAuth2
4. **Map the dataset** to use the gateway in your semantic model settings

---

## 7. Troubleshooting

### Authentication Errors

| Error | Cause | Fix |
|---|---|---|
| "Access to the resource is forbidden" | Missing RBAC role | Assign **Storage Blob Data Reader** on the storage account or `curated` container via Azure Portal → Access Control (IAM) |
| "AADSTS50076: Multi-factor authentication required" | Conditional Access policy | Complete MFA prompt, or use a service principal for unattended refresh |
| "Token expired" in Power BI Service | OAuth2 token not refreshed | Go to dataset settings → re-enter credentials under Data source credentials |
| "Invalid credentials" | Wrong account type selected | Ensure you select **Organizational account** (not Key, SAS, or Anonymous) |

### Missing Data

| Symptom | Cause | Fix |
|---|---|---|
| Only 3 tables have data | `SYNC_SIMULATIONS` not enabled | Set `SYNC_SIMULATIONS=true` in the Azure Function app settings to enable the 6 extended tables |
| Table loads but is empty | Function hasn't run yet | Check function logs in Application Insights, or trigger manually via `/api/test-run` |
| Data is stale (old date) | Function timer not firing | Check timer schedule in Azure Portal → Function App → Configuration (`TIMER_SCHEDULE`) |
| Some columns are null | Graph API returned no data | Normal — not all fields are populated for every record (e.g., `automationId` is null for manual simulations) |

### Refresh Failures

| Error | Cause | Fix |
|---|---|---|
| "Data source error: Unable to connect" | Network restrictions blocking Power BI | Set `enablePowerBiAccess=true` in Bicep, or configure an On-Premises Data Gateway |
| "The gateway is offline" | Gateway VM is stopped or service is down | Start the gateway VM and verify the gateway service is running |
| "Timeout expired" | Large dataset or slow network | Reduce data volume by loading only the latest snapshot, or increase the timeout in gateway settings |
| "The content of the request is not valid" | Corrupted Parquet file | Check function logs for write errors; re-trigger ingestion via `/api/test-run` |

### Power Query Errors

| Error | Cause | Fix |
|---|---|---|
| "Expression.Error: The key didn't match any rows" | Table folder doesn't exist yet | Ensure the function has run at least once for that endpoint |
| "DataFormat.Error: Parquet error" | Power BI version too old | Update to the latest Power BI Desktop version |
| "Access to the resource is forbidden" inside Power Query | Cached credentials expired | Go to **File** → **Options** → **Data source settings** → clear permissions for the ADLS endpoint, then re-authenticate |

### Performance Tips

- **Load only the latest snapshot** unless you need historical trend analysis (see [Step 6](#step-6-load-only-the-latest-snapshot-optional))
- **Disable Auto Date/Time** in Power BI options to reduce model size: **File** → **Options** → **Data Load** → uncheck **Auto date/time**
- **Use Import mode** (not DirectQuery) for best performance with Parquet files
- **Enable query folding** by keeping filter operations early in the Power Query steps

---

## Additional Resources

- [README — Power BI Setup section](../README.md#power-bi-setup)
- [Microsoft: Connect to ADLS Gen2 from Power BI](https://learn.microsoft.com/en-us/power-bi/connect-data/service-azure-and-power-bi)
- [Microsoft: On-Premises Data Gateway](https://learn.microsoft.com/en-us/power-bi/connect-data/service-gateway-onprem)
- [Microsoft: DAX Reference](https://learn.microsoft.com/en-us/dax/)
