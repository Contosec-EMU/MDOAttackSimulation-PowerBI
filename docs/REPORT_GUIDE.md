# MDO Attack Simulation — Power BI Report Guide

This guide documents the **MDO Attack Simulation Training** Power BI report — its pages, visuals, data sources, and the Graph API endpoints that feed each section.

---

## Data Architecture Overview

```
Microsoft Graph API  →  Azure Function (Python)  →  ADLS Gen2 (Parquet)  →  Power BI
```

| ADLS Table | Graph API Endpoint | Scope |
|---|---|---|
| `simulations` | `beta/security/attackSimulation/simulations` | Extended (SYNC_SIMULATIONS=true) |
| `simulationUsers` | `beta/…/simulations/{id}/report/simulationUsers` | Per-simulation detail |
| `simulationUserEvents` | `beta/…/simulations/{id}/report/simulationUsers` (events array) | Per-simulation detail |
| `simulationUserCoverage` | `v1.0/…/getAttackSimulationSimulationUserCoverage` | Core (always) |
| `trainingUserCoverage` | `v1.0/…/getAttackSimulationTrainingUserCoverage` | Core (always) |
| `repeatOffenders` | `v1.0/…/getAttackSimulationRepeatOffenders` | Core (always) |
| `payloads` | `beta/security/attackSimulation/payloads` | Extended |
| `trainings` | `beta/security/attackSimulation/trainings` | Extended |
| `users` | `v1.0/users/{id}?$select=id,displayName,…,department,…` | Per-user enrichment |

---

## Page 1: Organization Overview

**Purpose**: High-level snapshot of the organization's overall phishing simulation performance.

### Visuals

| Visual | Type | Measure / Data | Source Table | API |
|---|---|---|---|---|
| Simulation Count | Card | `COUNTROWS(simulations)` | simulations | beta simulations |
| Total Users Targeted | Card | `SUM(simulations[reportTotalUserCount])` with fallback to `COUNTROWS(simulationUsers)` | simulations / simulationUsers | beta simulations |
| Training Completion Rate | Card | `completedTrainingsCount / assignedTrainingsCount` with CROSSFILTER | trainingUserCoverage | v1.0 trainingUserCoverage |
| Compromise Rate | Card (red) | `compromised users / total` from simulationUsers | simulationUsers | beta simulationUsers |
| Phish Report Rate | Card (green) | Dual-path: simulation-level `reportReportedCount` then user-level `reportedPhishDateTime` | simulations + simulationUsers | beta simulations |
| User Response Distribution | Donut | User Compromised Count / Reported User Count / No Action Count | simulationUsers | beta simulationUsers |
| Performance Over Time | Area Chart | Compromise Rate + Phish Report Rate over `simulations.launchDateTime` | simulations + simulationUsers | beta simulations |

**Key insight**: The donut chart and cards all use `simulationUsers` data consistently (one row per user per simulation). Compromise Rate (red) is a negative indicator; Phish Report Rate (green) is positive. The three donut slices — compromised, reported, and no action — should sum to the total simulation participation count.

---

## Page 2: Department Overview

**Purpose**: Break down simulation performance by organizational department.

### Visuals

| Visual | Type | Measure / Data | Source Table | API |
|---|---|---|---|---|
| Department slicer | Slicer | `users[department]` | users | v1.0 users (Entra ID) |
| Dept Simulated User Count | Card | `DISTINCTCOUNT(simulationUsers[userId])` — unique users, not user-simulation pairs | simulationUsers | beta simulationUsers |
| Dept Simulation Count | Card | `DISTINCTCOUNT(simulationUsers[simulationId])` | simulationUsers | beta simulationUsers |
| Dept Training Completion | Card | `completedTrainingsCount / assignedTrainingsCount` with `CROSSFILTER(trainingUserCoverage[userId], users[userId], Both)` | trainingUserCoverage | v1.0 trainingUserCoverage |
| Department Performance Summary | Table | Department × Risk Score × Compromise Rate | simulationUsers + users | beta + Entra |
| Department Risk Score | Card | `(compromised / total) × 100` per department using `USERELATIONSHIP` | simulationUsers + users | beta + Entra |
| Dept Trends | Area Chart | Dept Compromise Rate + Dept Reported Rate over time | simulationUsers | beta simulationUsers |

**Key insight**: Department data comes from Entra ID user enrichment (`users.department`). The Graph API call uses explicit `$select` to request department, city, country, and other profile fields. The `CROSSFILTER` on `Dept Training Completion` enables the department slicer to filter training data through the `users` dimension table, which is necessary because `trainingUserCoverage` has no direct relationship to `simulations`.

**Blank department row**: Users with blank department are either (a) Entra system accounts without a department (e.g., BreakGlass, DirSync), or (b) user IDs referenced by simulation data that no longer exist in Entra ID (deleted users, synthetic accounts from the attack simulation platform). The function creates fallback records for 404 responses with null profile fields.

---

## Page 3: Improving Submissions

**Purpose**: Analyze how users interact with simulated phishing emails — reads, deletes, and reporting behavior.

### Visuals

| Visual | Type | Measure / Data | Source Table | API |
|---|---|---|---|---|
| User Sim Count | Card | `COUNTROWS(simulationUsers)` — total user-simulation participations | simulationUsers | beta simulationUsers |
| Email Read Count | Card | Events where `eventName = "EmailRead"` | simulationUserEvents | beta simulationUsers (events array) |
| Email Deleted Count | Card | Events where `eventName = "EmailDeleted"` | simulationUserEvents | beta simulationUsers (events array) |
| Email Deleted % | Card | Deleted event count / total user participations | simulationUserEvents + simulationUsers | beta |
| Submission behavior over time | Chart | Email events over time | simulationUserEvents | beta simulationUsers (events array) |

**Key insight**: This page tracks email handling behavior. High email deletion without reporting suggests users recognize suspicious emails but don't follow the proper reporting procedure. The `simulationUserEvents` table captures granular event types: `EmailLinkClicked`, `EmailRead`, `EmailDeleted`, `CredentialHarvested`, `AttachmentOpened`, etc.

---

## Page 4: Executive Dashboard

**Purpose**: C-level summary with key KPIs, date-filterable trends, and cross-table metrics.

### Visuals

| Visual | Type | Measure / Data | Source Table | API |
|---|---|---|---|---|
| Date slicer | Slicer | `simulations[launchDateTime]` | simulations | beta simulations |
| Simulation Count | Card | `COUNTROWS(simulations)` | simulations | beta simulations |
| Total Users Targeted | Card | Report-level or user-level count | simulations | beta simulations |
| Compromise Rate | Card | % of users compromised | simulationUsers | beta simulationUsers |
| Completed Simulations | Card | Simulations with `status = "succeeded"` and non-blank launch date | simulations | beta simulations |
| Training Completion Rate | Card | `completedTrainingsCount / assignedTrainingsCount` with `CROSSFILTER(simulationUsers[userId], users[userId], Both)` | trainingUserCoverage | v1.0 trainingUserCoverage |
| Repeat Offender Count | Card | `COUNTROWS(repeatOffenders)` with `CROSSFILTER(simulationUsers[userId], users[userId], Both)` | repeatOffenders | v1.0 repeatOffenders |
| Monthly Compromised Users | Chart | Compromised user trend over time | simulationUsers | beta simulationUsers |

**Key insight**: The date slicer filters `simulations` by `launchDateTime`. The `CROSSFILTER(simulationUsers[userId], users[userId], Both)` on Training Completion Rate and Repeat Offender Count enables the date filter to propagate: `simulations → simulationUsers → users (bidirectional) → trainingUserCoverage / repeatOffenders`. Without this, these measures would be unaffected by the date slicer since they have no direct relationship to `simulations`.

---

## Page 5: Simulation Analysis

**Purpose**: Detailed per-simulation breakdown showing individual campaign performance.

### Visuals

| Visual | Type | Measure / Data | Source Table | API |
|---|---|---|---|---|
| Simulation table | Table | Name, launch date, status, user counts | simulations | beta simulations |
| Click Rate | Card | `reportClickCount / reportTotalUserCount` | simulations | beta simulations |
| Compromise Rate (per sim) | Card | Per-simulation compromise percentage | simulationUsers | beta simulationUsers |
| Simulation timeline | Chart | Simulations over time with performance metrics | simulations | beta simulations |

**Key insight**: This page uses `simulations`-level aggregated report fields (`reportClickCount`, `reportCompromisedCount`, `reportTotalUserCount`) which are pre-computed by the Graph API in each simulation's embedded `report.overview` object.

---

## Page 6: User Risk Profile

**Purpose**: Individual user-level risk analysis showing which users are most vulnerable across simulations.

### Visuals

| Visual | Type | Measure / Data | Source Table | API |
|---|---|---|---|---|
| User table | Table | User details with compromise and reporting status | simulationUsers + users | beta + Entra |
| User event timeline | Line Chart | Events over time per user | simulationUserEvents | beta events |
| Compromise Rate | Card | User-level compromise percentage | simulationUsers | beta simulationUsers |
| User Reported Rate | Card | % of users who reported phishing | simulationUsers | beta simulationUsers |

**Key insight**: User event data comes from `simulationUserEvents`, which contains granular events with timestamps. The `users` table provides Entra ID profile data (department, city, country, job title) for user identification and filtering.

**Known limitation**: The line chart x-axis (`simulationUserEvents.eventDateTime`) has limited cross-filter capability to `simulationUsers`-based measures due to single-directional relationships. Event-level trend analysis works best with event-sourced measures.

---

## Page 7: Training Compliance

**Purpose**: Track training assignment completion across the organization.

### Visuals

| Visual | Type | Measure / Data | Source Table | API |
|---|---|---|---|---|
| Training Completion Rate | Card | Completed / assigned trainings | trainingUserCoverage | v1.0 trainingUserCoverage |
| User Training Completed | Card | `SUM(completedTrainingsCount)` | trainingUserCoverage | v1.0 trainingUserCoverage |
| Avg Training Duration | Card | `AVERAGE(trainings[durationInMinutes])` | trainings | beta trainings |
| Training list | Table | Training names, durations, types | trainings | beta trainings |
| Completion trend | Chart | Training completion over time | trainingUserCoverage | v1.0 trainingUserCoverage |

**Key insight**: `trainingUserCoverage` is a core endpoint (v1.0, always synced) providing per-user training status with `completedTrainingsCount`, `assignedTrainingsCount`, and `inProgressTrainingsCount`. The `trainings` table (beta, extended) provides training catalog metadata like names, durations, and types.

---

## Page 8: Payload Effectiveness

**Purpose**: Analyze which phishing payload types and techniques are most effective at compromising users.

### Visuals

| Visual | Type | Measure / Data | Source Table | API |
|---|---|---|---|---|
| Payload table | Table | Payload names, types, predicted compromise rates | payloads | beta payloads |
| Actual vs Predicted Variance | Card | Actual compromise rate − `predictedCompromiseRate` | simulations + payloads | beta |
| Predicted Compromise Rate | Chart | Distribution of predicted rates across payloads | payloads | beta payloads |
| Payload type breakdown | Chart | Performance by technique/theme | payloads + simulations | beta |

**Key insight**: `payloads.predictedCompromiseRate` is a `double` (0.0–1.0) representing Microsoft's predicted compromise rate based on payload characteristics. Comparing actual vs. predicted reveals whether your organization is more or less susceptible than average. Payloads connect to simulations via `payloadId`.

---

## Data Model Relationships

```
simulations (one) ← simulationUsers (many)       [simulationId]
users (one) ← simulationUsers (many)             [userId]
simulationUsers (one) ← simulationUserEvents      [SimUserKey]
payloads (one) ← simulations (many)               [payloadId]
users (one) ← simulationUserCoverage (many)       [userId]
users (one) ← trainingUserCoverage (many)         [userId]
users (one) ← repeatOffenders (many)              [userId]
trainings — ISOLATED (no direct relationships)
```

All relationships are single-directional (one → many) by default. `CROSSFILTER(..., Both)` is used in specific measures to enable bidirectional filtering when a slicer on one fact table needs to filter another fact table through a shared dimension (`users`).

### Cross-Filter Pattern

When a date slicer on `simulations.launchDateTime` needs to affect measures from `trainingUserCoverage` or `repeatOffenders`:
1. Date slicer → filters `simulations`
2. `simulations` → `simulationUsers` (default direction)
3. `simulationUsers` → `users` (requires `CROSSFILTER(..., Both)`)
4. `users` → `trainingUserCoverage` / `repeatOffenders` (default direction)

---

## Graph API Permissions Required

| Permission | Type | Purpose |
|---|---|---|
| `AttackSimulation.Read.All` | Application | Read all simulation, payload, and training data |
| `User.Read.All` | Application | Read Entra ID user profiles (department, city, country, etc.) |

---

## Refresh Cadence

The Azure Function runs on an hourly timer trigger (`:00` each hour). Data is written to ADLS Gen2 in Parquet format with date-partitioned paths (`curated/{table}/YYYY/MM/DD/`). Power BI connects to the ADLS storage account to read the latest Parquet files.
