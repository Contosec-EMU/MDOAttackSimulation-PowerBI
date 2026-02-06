# Manual Azure Portal Deployment Guide

Deploy the MDO Attack Simulation Training data pipeline entirely through the Azure Portal — no CLI, no terminal, no code editors required.

This guide walks through every click, every field, and every setting needed to go from zero to a fully working data pipeline that ingests Microsoft Defender for Office 365 Attack Simulation Training data into Azure Data Lake Storage Gen2 as Parquet files for Power BI.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Step 1: Create Resource Group](#step-1-create-resource-group)
- [Step 2: Create Virtual Network](#step-2-create-virtual-network)
- [Step 3: Create Log Analytics Workspace](#step-3-create-log-analytics-workspace)
- [Step 4: Create Application Insights](#step-4-create-application-insights)
- [Step 5: Create Function Storage Account](#step-5-create-function-storage-account)
- [Step 6: Create Data Lake Storage Account (ADLS Gen2)](#step-6-create-data-lake-storage-account-adls-gen2)
- [Step 7: Create Key Vault](#step-7-create-key-vault)
- [Step 8: Create App Service Plan](#step-8-create-app-service-plan)
- [Step 9: Create Function App](#step-9-create-function-app)
- [Step 10: Enable Managed Identity](#step-10-enable-managed-identity)
- [Step 11: Configure RBAC Role Assignments](#step-11-configure-rbac-role-assignments)
- [Step 12: Create Entra ID App Registration](#step-12-create-entra-id-app-registration)
- [Step 13: Store Client Secret in Key Vault](#step-13-store-client-secret-in-key-vault)
- [Step 14: Configure Function App Settings](#step-14-configure-function-app-settings)
- [Step 15: Deploy Function Code](#step-15-deploy-function-code)
- [Step 16: Verify Deployment](#step-16-verify-deployment)
- [Troubleshooting](#troubleshooting)
- [Appendix: Resource Naming Reference](#appendix-resource-naming-reference)

---

## Prerequisites

Before you begin, ensure you have:

| Requirement | Details |
|---|---|
| **Azure Subscription** | Active subscription with billing configured |
| **Subscription Roles** | `Contributor` + `User Access Administrator` on the subscription (or target resource group) |
| **Entra ID Permissions** | Permission to create App Registrations and grant admin consent (Global Administrator, Application Administrator, or Cloud Application Administrator) |
| **Browser** | Modern browser (Edge, Chrome, Firefox) — the Azure Portal does not support Internet Explorer |

> **Tip:** To check your subscription roles, navigate to **Subscriptions → (your subscription) → Access control (IAM) → View my access**.

---

## Step 1: Create Resource Group

A resource group is a logical container for all the Azure resources in this solution.

### Navigation

1. Go to [https://portal.azure.com](https://portal.azure.com)
2. In the top search bar, type **Resource groups** and select it
3. Click **➕ Create**

### Configuration

| Tab | Field | Value |
|-----|-------|-------|
| **Basics** | Subscription | *(select your subscription)* |
| | Resource group | `rg-mdo-attack-simulation` |
| | Region | `West US 2` |
| **Tags** | Name / Value | `project` = `MDOAttackSimulation` |
| | Name / Value | `environment` = `production` |
| | Name / Value | `costCenter` = `security` |

### Steps

1. On the **Basics** tab, select your subscription from the dropdown
2. Enter `rg-mdo-attack-simulation` in the **Resource group** field
3. Select **West US 2** from the Region dropdown
4. Click **Next: Tags**
5. Add three tags:
   - **Name:** `project` → **Value:** `MDOAttackSimulation`
   - **Name:** `environment` → **Value:** `production`
   - **Name:** `costCenter` → **Value:** `security`
6. Click **Review + create**
7. Verify all settings are correct, then click **Create**

<!-- Screenshot: Resource Group creation page with Basics tab filled in -->

> **Checkpoint:** You should now see `rg-mdo-attack-simulation` listed under Resource Groups.

---

## Step 2: Create Virtual Network

The Virtual Network (VNet) provides network isolation so the Function App can securely access firewall-protected storage and Key Vault via service endpoints.

### Navigation

1. In the portal search bar, type **Virtual networks** and select it
2. Click **➕ Create**

### Configuration

| Tab | Field | Value |
|-----|-------|-------|
| **Basics** | Subscription | *(select your subscription)* |
| | Resource group | `rg-mdo-attack-simulation` |
| | Virtual network name | `mdoast-vnet` |
| | Region | `West US 2` |
| **IP addresses** | Address space | `10.0.0.0/16` |
| | Subnet name | `snet-functions` |
| | Subnet address range | `10.0.1.0/24` |
| **Tags** | Name / Value | `project` = `MDOAttackSimulation` |
| | Name / Value | `environment` = `production` |

### Steps

1. On the **Basics** tab, select your subscription and resource group `rg-mdo-attack-simulation`
2. Enter `mdoast-vnet` as the name
3. Confirm region is **West US 2**
4. Click **Next: Security** — leave defaults (no Bastion, no Firewall, no DDoS protection needed)
5. Click **Next: IP addresses**
6. Verify the address space is `10.0.0.0/16` (edit if needed)
7. If a `default` subnet exists, click the **🗑 delete** icon to remove it
8. Click **➕ Add a subnet**:
   - **Subnet name:** `snet-functions`
   - **Starting address:** `10.0.1.0`
   - **Subnet size:** `/24 (256 addresses)`
   - Under **Services**, check: `Microsoft.KeyVault` and `Microsoft.Storage`
   - Under **Subnet delegation**, select: `Microsoft.Web/serverFarms`
9. Click **Add**
10. Click **Next: Tags**, add the project/environment tags
11. Click **Review + create**, then **Create**

<!-- Screenshot: Virtual Network IP addresses tab with snet-functions subnet configured -->

> **Checkpoint:** Navigate to the VNet resource → **Subnets** to verify `snet-functions` exists with service endpoints for `Microsoft.Storage` and `Microsoft.KeyVault`, and delegation to `Microsoft.Web/serverFarms`.

---

## Step 3: Create Log Analytics Workspace

Log Analytics is the backend data store for Application Insights. It stores diagnostic logs and enables querying.

### Navigation

1. In the portal search bar, type **Log Analytics workspaces** and select it
2. Click **➕ Create**

### Configuration

| Tab | Field | Value |
|-----|-------|-------|
| **Basics** | Subscription | *(select your subscription)* |
| | Resource group | `rg-mdo-attack-simulation` |
| | Name | `mdoast-law` |
| | Region | `West US 2` |
| **Pricing tier** | Pricing tier | `Pay-as-you-go (Per GB 2018)` *(default)* |
| **Tags** | Name / Value | `project` = `MDOAttackSimulation` |
| | Name / Value | `environment` = `production` |

### Steps

1. Select your subscription and resource group `rg-mdo-attack-simulation`
2. Enter `mdoast-law` as the name
3. Set region to **West US 2**
4. Click **Next: Pricing tier** — leave as **Pay-as-you-go** (default)
5. Click **Next: Tags**, add the project/environment tags
6. Click **Review + create**, then **Create**
7. After creation, navigate to the workspace → **Usage and estimated costs** → **Data Retention**
8. Set retention to **90 days** and click **OK**

<!-- Screenshot: Log Analytics Workspace creation page -->

> **Checkpoint:** Log Analytics workspace `mdoast-law` exists with 90-day retention.

---

## Step 4: Create Application Insights

Application Insights provides monitoring, live metrics, and alerting for the Function App.

### Navigation

1. In the portal search bar, type **Application Insights** and select it
2. Click **➕ Create**

### Configuration

| Tab | Field | Value |
|-----|-------|-------|
| **Basics** | Subscription | *(select your subscription)* |
| | Resource group | `rg-mdo-attack-simulation` |
| | Name | `mdoast-appi` |
| | Region | `West US 2` |
| | Resource Mode | `Workspace-based` *(default)* |
| | Log Analytics Workspace | `mdoast-law` *(created in Step 3)* |
| **Tags** | Name / Value | `project` = `MDOAttackSimulation` |
| | Name / Value | `environment` = `production` |

### Steps

1. Select your subscription and resource group `rg-mdo-attack-simulation`
2. Enter `mdoast-appi` as the name
3. Set region to **West US 2**
4. Ensure **Resource Mode** is set to `Workspace-based`
5. In the **Log Analytics Workspace** dropdown, select `mdoast-law`
6. Click **Next: Tags**, add the project/environment tags
7. Click **Review + create**, then **Create**
8. After creation, open the resource and **copy the Connection String** from the **Overview** page — you will need this in Step 14

<!-- Screenshot: Application Insights creation with workspace-based mode -->

> **Save this value:**
> - **Connection String:** `InstrumentationKey=xxxxxxxx-xxxx-...` (from the Overview page, Properties section)

---

## Step 5: Create Function Storage Account

This is a **separate** storage account used internally by Azure Functions for triggers, bindings, and runtime state. It is **not** the Data Lake.

### Navigation

1. In the portal search bar, type **Storage accounts** and select it
2. Click **➕ Create**

### Configuration

| Tab | Field | Value |
|-----|-------|-------|
| **Basics** | Subscription | *(select your subscription)* |
| | Resource group | `rg-mdo-attack-simulation` |
| | Storage account name | `mdoastfn` + *unique suffix* (e.g., `mdoastfn2024prod`) |
| | Region | `West US 2` |
| | Performance | `Standard` |
| | Redundancy | `Locally-redundant storage (LRS)` |
| **Advanced** | Require secure transfer | ✅ Enabled *(default)* |
| | Allow enabling anonymous access on containers | ❌ Disabled |
| | Enable storage account key access | ❌ **Disabled** |
| | Minimum TLS version | `Version 1.2` |
| | Access tier | `Hot` |
| | Enable hierarchical namespace | ❌ **Disabled** (this is NOT the data lake) |
| **Tags** | Name / Value | `project` = `MDOAttackSimulation` |
| | Name / Value | `environment` = `production` |

> ⚠️ **Important:** Storage account names must be globally unique, 3–24 characters, lowercase letters and numbers only. Pick a unique name like `mdoastfn2024prod` or `mdoastfnXXXXX` where `XXXXX` is a random string.

### Steps

1. Select your subscription and resource group `rg-mdo-attack-simulation`
2. Enter a globally unique name (e.g., `mdoastfn2024prod`)
3. Set region to **West US 2**, performance to **Standard**, redundancy to **LRS**
4. Click **Next: Advanced**
5. **Disable** "Allow enabling anonymous access on individual containers"
6. **Disable** "Enable storage account key access" (we use identity-based auth)
7. Set minimum TLS version to **1.2**
8. Set access tier to **Hot**
9. Ensure **Enable hierarchical namespace** is **unchecked** (this is the function storage, not the data lake)
10. Click **Next: Networking** — leave defaults
11. Click **Next: Data protection** — leave defaults
12. Click **Next: Encryption** — leave defaults
13. Click **Next: Tags**, add the project/environment tags
14. Click **Review + create**, then **Create**

<!-- Screenshot: Function storage account Advanced tab showing key access disabled -->

> **Save this value:**
> - **Function Storage Account name:** e.g., `mdoastfn2024prod`

---

## Step 6: Create Data Lake Storage Account (ADLS Gen2)

This is the primary data store. Parquet files (for Power BI) and raw JSON archives are written here. **Hierarchical namespace must be enabled** — this is what makes it an ADLS Gen2 account.

### Navigation

1. In the portal search bar, type **Storage accounts** and select it
2. Click **➕ Create**

### Configuration

| Tab | Field | Value |
|-----|-------|-------|
| **Basics** | Subscription | *(select your subscription)* |
| | Resource group | `rg-mdo-attack-simulation` |
| | Storage account name | `mdoastdl` + *unique suffix* (e.g., `mdoastdl2024prod`) |
| | Region | `West US 2` |
| | Performance | `Standard` |
| | Redundancy | `Locally-redundant storage (LRS)` |
| **Advanced** | Require secure transfer | ✅ Enabled |
| | Allow enabling anonymous access on containers | ❌ Disabled |
| | Minimum TLS version | `Version 1.2` |
| | Access tier | `Hot` |
| | **Enable hierarchical namespace** | ✅ **YES — REQUIRED** |
| **Networking** | Network access | `Disable public access and use private access` |
| | | **OR** `Enable public access from selected virtual networks and IP addresses` |
| | Virtual networks | ➕ Add existing virtual network: `mdoast-vnet` / `snet-functions` |
| | Exceptions | ✅ Allow Azure services on the trusted services list to access this storage account |
| **Tags** | Name / Value | `project` = `MDOAttackSimulation` |
| | Name / Value | `environment` = `production` |

> ⚠️ **CRITICAL:** Enabling hierarchical namespace is a **one-time, irreversible** setting. If you forget to enable it during creation, you must delete the storage account and start over.

### Steps

1. Select your subscription and resource group `rg-mdo-attack-simulation`
2. Enter a globally unique name (e.g., `mdoastdl2024prod`)
3. Set region to **West US 2**, performance to **Standard**, redundancy to **LRS**
4. Click **Next: Advanced**
5. **Disable** "Allow enabling anonymous access on individual containers"
6. Set minimum TLS version to **1.2**
7. Set access tier to **Hot**
8. ✅ **Check "Enable hierarchical namespace"** — this is the most critical setting
9. Click **Next: Networking**
10. Select **Enable public access from selected virtual networks and IP addresses**
11. Under **Virtual networks**, click **➕ Add existing virtual network**
    - **Subscription:** *(your subscription)*
    - **Virtual networks:** `mdoast-vnet`
    - **Subnets:** `snet-functions`
    - Click **Add**
12. Under **Exceptions**, check ✅ **Allow Azure services on the trusted services list to access this storage account**
13. Click **Next: Data protection** — leave defaults
14. Click **Next: Encryption** — leave defaults
15. Click **Next: Tags**, add the project/environment tags
16. Click **Review + create**, then **Create**

<!-- Screenshot: Data Lake storage account Advanced tab showing hierarchical namespace enabled -->

### Create Containers

After the storage account is created:

1. Navigate to the storage account → **Containers** (under Data storage in the left menu)
2. Click **➕ Container**
   - **Name:** `curated`
   - **Public access level:** `Private (no anonymous access)`
   - Click **Create**
3. Click **➕ Container** again
   - **Name:** `raw`
   - **Public access level:** `Private (no anonymous access)`
   - Click **Create**
4. Click **➕ Container** again
   - **Name:** `state`
   - **Public access level:** `Private (no anonymous access)`
   - Click **Create**

<!-- Screenshot: Storage account Containers page showing curated, raw, and state containers -->

> **Save these values:**
> - **Data Lake Storage Account name:** e.g., `mdoastdl2024prod`
> - **DFS endpoint:** `https://mdoastdl2024prod.dfs.core.windows.net` (visible on the storage account's **Endpoints** page under **Data Lake Storage**)

> **Checkpoint:** The storage account **Overview** page should show **Hierarchical namespace: Enabled**. Three containers (`curated`, `raw`, `state`) should be visible under **Containers**.

---

## Step 7: Create Key Vault

Key Vault securely stores the Graph API client secret. The Function App retrieves it at runtime using its managed identity.

### Navigation

1. In the portal search bar, type **Key vaults** and select it
2. Click **➕ Create**

### Configuration

| Tab | Field | Value |
|-----|-------|-------|
| **Basics** | Subscription | *(select your subscription)* |
| | Resource group | `rg-mdo-attack-simulation` |
| | Key vault name | `mdoast-kv` + *unique suffix* (e.g., `mdoast-kv-2024prod`) |
| | Region | `West US 2` |
| | Pricing tier | `Standard` |
| | Days to retain deleted vaults | `90` |
| | Purge protection | `Disable purge protection` *(can enable later if needed)* |
| **Access configuration** | Permission model | ✅ **Azure role-based access control (recommended)** |
| **Networking** | Network access | `Allow public access from specific virtual networks and IP addresses` |
| | Virtual networks | ➕ Add: `mdoast-vnet` / `snet-functions` |
| | Exception | ✅ Allow trusted Microsoft services to bypass this firewall |
| **Tags** | Name / Value | `project` = `MDOAttackSimulation` |
| | Name / Value | `environment` = `production` |

> ⚠️ **Key vault names** must be globally unique, 3–24 characters, and can contain only alphanumeric characters and hyphens.

### Steps

1. Select your subscription and resource group `rg-mdo-attack-simulation`
2. Enter a unique name (e.g., `mdoast-kv-2024prod`)
3. Set region to **West US 2**
4. Set pricing tier to **Standard**
5. Set soft-delete retention to **90 days**
6. Click **Next: Access configuration**
7. Select ✅ **Azure role-based access control** as the permission model
8. Click **Next: Networking**
9. Select **Allow public access from specific virtual networks and IP addresses**
10. Click **➕ Add a virtual network** → select `mdoast-vnet` / `snet-functions` → **Add**
11. Under **Exception**, check ✅ **Allow trusted Microsoft services to bypass this firewall**
12. Click **Next: Tags**, add the project/environment tags
13. Click **Review + create**, then **Create**

<!-- Screenshot: Key Vault Access configuration tab showing RBAC selected -->
<!-- Screenshot: Key Vault Networking tab showing VNet rule and trusted services bypass -->

> **Save this value:**
> - **Key Vault URI:** `https://mdoast-kv-2024prod.vault.azure.net/` (visible on the Key Vault's **Overview** page)

---

## Step 8: Create App Service Plan

The App Service Plan defines the compute resources for the Function App. We use a Basic B1 Linux plan.

### Navigation

1. In the portal search bar, type **App Service plans** and select it
2. Click **➕ Create**

### Configuration

| Tab | Field | Value |
|-----|-------|-------|
| **Basics** | Subscription | *(select your subscription)* |
| | Resource group | `rg-mdo-attack-simulation` |
| | Name | `mdoast-asp` |
| | Operating System | **Linux** |
| | Region | `West US 2` |
| **Pricing plan** | Pricing tier | **Basic B1** |
| **Tags** | Name / Value | `project` = `MDOAttackSimulation` |
| | Name / Value | `environment` = `production` |

### Steps

1. Select your subscription and resource group `rg-mdo-attack-simulation`
2. Enter `mdoast-asp` as the name
3. Select **Linux** as the operating system
4. Set region to **West US 2**
5. Under **Pricing plan**, click **Explore pricing plans**
6. Select the **Dev / Test** tab
7. Select **B1** (Basic — 1 core, 1.75 GB RAM, ~$13/month)
8. Click **Select**
9. Click **Next: Tags**, add the project/environment tags
10. Click **Review + create**, then **Create**

<!-- Screenshot: App Service Plan creation with B1 Linux selected -->

> **Checkpoint:** The plan should show SKU `B1`, OS `Linux`, Region `West US 2`.

---

## Step 9: Create Function App

The Function App hosts the Python code that ingests data from Microsoft Graph.

### Navigation

1. In the portal search bar, type **Function App** and select it
2. Click **➕ Create**
3. Select **Consumption** or switch to **App Service plan** *(we'll select our existing plan)*

### Configuration

| Tab | Field | Value |
|-----|-------|-------|
| **Basics** | Subscription | *(select your subscription)* |
| | Resource group | `rg-mdo-attack-simulation` |
| | Function App name | `mdoast-func` + *unique suffix* (e.g., `mdoast-func-2024prod`) |
| | Runtime stack | **Python** |
| | Version | **3.11** |
| | Region | `West US 2` |
| | Operating System | **Linux** |
| | Hosting options and plans | Select **App Service plan** |
| | Plan | `mdoast-asp` *(created in Step 8)* |
| **Storage** | Storage account | Select the **function** storage account (e.g., `mdoastfn2024prod`) — **NOT the data lake** |
| **Networking** | Enable public access | **On** |
| | Enable network injection | ✅ **On** |
| | Virtual network | `mdoast-vnet` |
| | Inbound access – Enable private endpoints | Off |
| | Outbound access – VNet integration subnet | `snet-functions` |
| **Monitoring** | Enable Application Insights | ✅ **Yes** |
| | Application Insights | `mdoast-appi` *(created in Step 4)* |
| **Tags** | Name / Value | `project` = `MDOAttackSimulation` |
| | Name / Value | `environment` = `production` |

> ⚠️ **Function App names** must be globally unique and will become part of the URL: `https://mdoast-func-2024prod.azurewebsites.net`.

### Steps

1. Select your subscription and resource group `rg-mdo-attack-simulation`
2. Enter a globally unique name (e.g., `mdoast-func-2024prod`)
3. Set **Runtime stack** to **Python**, version **3.11**
4. Set region to **West US 2**
5. Under **Operating system**, select **Linux**
6. Under **Hosting options and plans**, select **App Service plan**
7. In the **Plan** dropdown, select `mdoast-asp` (the plan from Step 8)
8. Click **Next: Storage**
9. Select the **function** storage account (`mdoastfn2024prod`) — do **NOT** select the data lake account
10. Click **Next: Networking**
11. Set **Enable public access** to **On**
12. Set **Enable network injection** to **On**
13. Select virtual network `mdoast-vnet`
14. Leave inbound private endpoints **Off**
15. For **Outbound access**, select VNet integration subnet `snet-functions`
16. Click **Next: Monitoring**
17. Set **Enable Application Insights** to **Yes**
18. Select `mdoast-appi` from the dropdown
19. Click **Next: Deployment** — leave defaults (can configure later)
20. Click **Next: Tags**, add the project/environment tags
21. Click **Review + create**, then **Create**

<!-- Screenshot: Function App Basics tab with Python 3.11 and Linux -->
<!-- Screenshot: Function App Networking tab with VNet integration configured -->

> **Save this value:**
> - **Function App name:** e.g., `mdoast-func-2024prod`

---

## Step 10: Enable Managed Identity

The system-assigned managed identity allows the Function App to authenticate to Key Vault and Storage without storing any credentials.

### Navigation

1. Navigate to **Function App** → select your function app (e.g., `mdoast-func-2024prod`)
2. In the left menu, scroll down to **Settings** → **Identity**

### Steps

1. On the **System assigned** tab, set **Status** to **On**
2. Click **Save**
3. A confirmation dialog appears: "Enable system assigned managed identity?" — Click **Yes**
4. Wait for the identity to be created (takes a few seconds)
5. **Copy the Object (principal) ID** — you will need this for RBAC assignments

<!-- Screenshot: Function App Identity page showing System assigned = On with Object ID -->

> **Save this value:**
> - **Managed Identity Object ID:** `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`

> **Note:** If the identity was already created during Function App creation (Step 9), you may see it already enabled here. Still copy the Object ID.

---

## Step 11: Configure RBAC Role Assignments

The Function App's managed identity needs permissions to read/write to both storage accounts and read secrets from Key Vault.

### 11a: Function Storage Account — Storage Blob Data Contributor

1. Navigate to **Storage accounts** → select the **function** storage account (e.g., `mdoastfn2024prod`)
2. In the left menu, click **Access Control (IAM)**
3. Click **➕ Add** → **Add role assignment**
4. **Role** tab: Search for and select `Storage Blob Data Contributor` → click **Next**
5. **Members** tab:
   - **Assign access to:** `Managed identity`
   - Click **➕ Select members**
   - **Managed identity:** `Function App`
   - Select your function app (e.g., `mdoast-func-2024prod`)
   - Click **Select**
6. Click **Review + assign**, then **Review + assign** again

<!-- Screenshot: RBAC role assignment for Storage Blob Data Contributor -->

### 11b: Function Storage Account — Storage Queue Data Contributor

Repeat the same process on the **function** storage account:

1. **Access Control (IAM)** → **➕ Add** → **Add role assignment**
2. Search for and select `Storage Queue Data Contributor`
3. Assign to the same Function App managed identity
4. **Review + assign**

### 11c: Function Storage Account — Storage Table Data Contributor

Repeat again on the **function** storage account:

1. **Access Control (IAM)** → **➕ Add** → **Add role assignment**
2. Search for and select `Storage Table Data Contributor`
3. Assign to the same Function App managed identity
4. **Review + assign**

### 11d: Data Lake Storage Account — Storage Blob Data Contributor

1. Navigate to **Storage accounts** → select the **data lake** storage account (e.g., `mdoastdl2024prod`)
2. In the left menu, click **Access Control (IAM)**
3. Click **➕ Add** → **Add role assignment**
4. **Role** tab: Search for and select `Storage Blob Data Contributor` → click **Next**
5. **Members** tab:
   - **Assign access to:** `Managed identity`
   - Click **➕ Select members**
   - Select your function app (e.g., `mdoast-func-2024prod`)
   - Click **Select**
6. Click **Review + assign**, then **Review + assign** again

<!-- Screenshot: Data Lake IAM role assignment page -->

### 11e: Key Vault — Key Vault Secrets User

1. Navigate to **Key vaults** → select your key vault (e.g., `mdoast-kv-2024prod`)
2. In the left menu, click **Access Control (IAM)**
3. Click **➕ Add** → **Add role assignment**
4. **Role** tab: Search for and select `Key Vault Secrets User` → click **Next**
5. **Members** tab:
   - **Assign access to:** `Managed identity`
   - Click **➕ Select members**
   - Select your function app (e.g., `mdoast-func-2024prod`)
   - Click **Select**
6. Click **Review + assign**, then **Review + assign** again

<!-- Screenshot: Key Vault IAM role assignment for Key Vault Secrets User -->

> **Checkpoint — Summary of RBAC Assignments:**
>
> | Resource | Role | Assignee |
> |----------|------|----------|
> | Function Storage Account | Storage Blob Data Contributor | Function App MI |
> | Function Storage Account | Storage Queue Data Contributor | Function App MI |
> | Function Storage Account | Storage Table Data Contributor | Function App MI |
> | Data Lake Storage Account | Storage Blob Data Contributor | Function App MI |
> | Key Vault | Key Vault Secrets User | Function App MI |

---

## Step 12: Create Entra ID App Registration

The App Registration provides the identity that the Function App uses to call Microsoft Graph APIs.

### Navigation

1. In the portal search bar, type **Microsoft Entra ID** and select it (or navigate to [https://entra.microsoft.com](https://entra.microsoft.com))
2. In the left menu, click **App registrations**
3. Click **➕ New registration**

### Create the Registration

| Field | Value |
|-------|-------|
| Name | `MDOAttackSimulation-GraphAPI` |
| Supported account types | `Accounts in this organizational directory only (Single tenant)` |
| Redirect URI | *(leave blank)* |

1. Enter the name `MDOAttackSimulation-GraphAPI`
2. Select **Accounts in this organizational directory only**
3. Leave Redirect URI blank
4. Click **Register**

<!-- Screenshot: App registration creation page -->

### Copy IDs

After creation, you'll be on the app's **Overview** page. Copy these values:

> **Save these values:**
> - **Application (client) ID:** `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
> - **Directory (tenant) ID:** `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`

### Add API Permissions

1. In the left menu, click **API permissions**
2. Click **➕ Add a permission**
3. Select **Microsoft Graph**
4. Select **Application permissions** (not Delegated)
5. Search for and check:
   - ✅ `AttackSimulation.Read.All`
   - ✅ `User.Read.All`
6. Click **Add permissions**
7. Back on the API permissions page, click **✅ Grant admin consent for [Your Organization]**
8. Confirm by clicking **Yes**

<!-- Screenshot: API permissions page with AttackSimulation.Read.All and User.Read.All granted -->

> ⚠️ **Admin consent** requires Global Administrator, Privileged Role Administrator, or Cloud Application Administrator. If you don't have this role, ask your admin to grant consent.

### Verify Permissions

After granting consent, you should see:

| Permission | Type | Status |
|---|---|---|
| AttackSimulation.Read.All | Application | ✅ Granted for [Your Organization] |
| User.Read.All | Application | ✅ Granted for [Your Organization] |

### Create Client Secret

1. In the left menu, click **Certificates & secrets**
2. Click the **Client secrets** tab
3. Click **➕ New client secret**
4. **Description:** `MDO Attack Simulation Function App`
5. **Expires:** `24 months` (recommended) or your organization's policy
6. Click **Add**
7. **IMMEDIATELY copy the secret Value** (the `Value` column, not the `Secret ID`)

<!-- Screenshot: Client secrets page with newly created secret -->

> ⚠️ **CRITICAL:** The secret value is only displayed **once**. If you navigate away without copying it, you must create a new one. The `Value` looks like: `aBc~dEf1G2h3I4j5K6l7M8n9...`

> **Save this value:**
> - **Client Secret Value:** `aBc~dEf1G2h3...` (copy the full value)

---

## Step 13: Store Client Secret in Key Vault

Store the Graph API client secret securely in Key Vault where the Function App can retrieve it using managed identity.

### Navigation

1. Navigate to **Key vaults** → select your key vault (e.g., `mdoast-kv-2024prod`)
2. In the left menu under **Objects**, click **Secrets**
3. Click **➕ Generate/Import**

### Configuration

| Field | Value |
|-------|-------|
| Upload options | `Manual` |
| Name | `graph-client-secret` |
| Secret value | *(paste the client secret from Step 12)* |
| Content type | *(leave blank)* |
| Set activation date | *(leave unchecked)* |
| Set expiration date | *(optionally set to match the secret's expiry)* |
| Enabled | `Yes` |

### Steps

1. Set upload options to **Manual**
2. Enter `graph-client-secret` as the **Name** (this exact name is expected by the function code)
3. Paste the client secret value from Step 12 into the **Secret value** field
4. Leave Content type blank
5. Click **Create**

<!-- Screenshot: Key Vault secret creation page -->

> ⚠️ **The secret name MUST be exactly `graph-client-secret`** — the function code looks for this specific name.

> **Checkpoint:** Navigate to Key Vault → Secrets. You should see `graph-client-secret` listed with status **Enabled**.

---

## Step 14: Configure Function App Settings

Application settings are environment variables that the Function App reads at runtime. These must be configured exactly for the function to work.

### Navigation

1. Navigate to **Function App** → select your function app (e.g., `mdoast-func-2024prod`)
2. In the left menu under **Settings**, click **Environment variables**
3. You should see the **App settings** tab

### Required Application Settings

Add or verify each of the following settings. Click **➕ Add** for each new setting:

| Name | Value | Notes |
|------|-------|-------|
| `TENANT_ID` | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` | Your Entra ID Directory (tenant) ID from Step 12 |
| `GRAPH_CLIENT_ID` | `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` | App Registration Application (client) ID from Step 12 |
| `KEY_VAULT_URL` | `https://mdoast-kv-2024prod.vault.azure.net/` | Key Vault URI from Step 7 (must start with `https://`) |
| `STORAGE_ACCOUNT_URL` | `https://mdoastdl2024prod.dfs.core.windows.net` | Data Lake DFS endpoint from Step 6 (must start with `https://`, use `.dfs.` not `.blob.`) |
| `TIMER_SCHEDULE` | `0 0 2 * * *` | CRON schedule: daily at 2:00 AM UTC |
| `SYNC_MODE` | `full` | `full` = fetch all data each run; `incremental` = 7-day lookback |
| `SYNC_SIMULATIONS` | `true` | `true` = sync simulation details (extended endpoints); `false` = core only |
| `FUNCTIONS_EXTENSION_VERSION` | `~4` | Should already exist; verify it's `~4` |
| `FUNCTIONS_WORKER_RUNTIME` | `python` | Should already exist |
| `AzureWebJobsStorage__accountName` | `mdoastfn2024prod` | Function storage account name (identity-based auth) |
| `AzureWebJobsStorage__blobServiceUri` | `https://mdoastfn2024prod.blob.core.windows.net` | Function storage blob endpoint |
| `AzureWebJobsStorage__queueServiceUri` | `https://mdoastfn2024prod.queue.core.windows.net` | Function storage queue endpoint |
| `AzureWebJobsStorage__tableServiceUri` | `https://mdoastfn2024prod.table.core.windows.net` | Function storage table endpoint |

> ⚠️ **Identity-based storage connection:** The `AzureWebJobsStorage__*` settings replace the traditional connection string approach. They tell Azure Functions to use the managed identity (configured in Step 10) instead of account keys.

> ⚠️ **If you see `AzureWebJobsStorage` (without suffix):** Delete the old `AzureWebJobsStorage` setting that contains a connection string, and replace it with the four `AzureWebJobsStorage__*` settings above.

### Steps

1. For each setting in the table above, click **➕ Add**
2. Enter the **Name** exactly as shown (case-sensitive)
3. Enter the **Value** with your actual resource names/IDs
4. Click **Apply** (or **OK**) after each entry
5. After adding all settings, click **Apply** at the bottom of the page
6. A confirmation dialog appears — click **Confirm**
7. The Function App will restart to apply the new settings

<!-- Screenshot: Function App Environment variables page with all settings configured -->

### Verify Settings

After the restart, scroll through the settings list and verify:
- `TENANT_ID` and `GRAPH_CLIENT_ID` match your Entra ID app registration
- `KEY_VAULT_URL` starts with `https://` and ends with `.vault.azure.net/`
- `STORAGE_ACCOUNT_URL` uses `.dfs.core.windows.net` (not `.blob.`)
- `FUNCTIONS_EXTENSION_VERSION` is `~4`

### CRON Schedule Reference

The `TIMER_SCHEDULE` uses Azure Functions CRON format: `{second} {minute} {hour} {day} {month} {day-of-week}`

| Schedule | CRON Expression |
|----------|----------------|
| Daily at 2:00 AM UTC | `0 0 2 * * *` |
| Every 6 hours | `0 0 */6 * * *` |
| Weekdays at 9:30 AM UTC | `0 30 9 * * 1-5` |
| First day of each month | `0 0 0 1 * *` |

---

## Step 15: Deploy Function Code

There are two ways to deploy the function code through the portal: **GitHub deployment** (recommended) or **ZIP deploy via Kudu**.

### Option A: Deploy from GitHub (Recommended)

This sets up continuous deployment — every push to your repository triggers a new deployment.

#### Steps

1. Navigate to **Function App** → select your function app
2. In the left menu under **Deployment**, click **Deployment Center**
3. Under **Source**, select **GitHub**
4. Click **Authorize** and sign in to your GitHub account
5. Configure:
   - **Organization:** *(your GitHub org or username)*
   - **Repository:** `MDOAttackSimulation_PowerBI`
   - **Branch:** `main`
6. Under **Build provider**, select **GitHub Actions**
7. Under **Runtime stack**, verify **Python** and **3.11**
8. Click **Save**

The portal will create a GitHub Actions workflow file (`.github/workflows/`) in your repository and trigger the first deployment.

<!-- Screenshot: Deployment Center configured with GitHub source -->

#### Monitor Deployment

1. In the **Deployment Center**, click the **Logs** tab
2. Wait for the deployment to show **Status: Success (Active)**
3. You can also check the GitHub Actions tab in your GitHub repository

### Option B: ZIP Deploy via Kudu (Advanced Tools)

Use this if your code is not in GitHub, or you prefer a manual one-time deployment.

#### Prepare the ZIP File

On your local machine, create a ZIP file containing the contents of `src/function_app/`:

```
function_app.zip
├── function_app.py
├── config.py
├── host.json
├── requirements.txt
├── clients/
│   ├── __init__.py
│   ├── graph_api.py
│   └── adls_writer.py
├── processors/
│   ├── __init__.py
│   └── transformers.py
├── services/
│   ├── __init__.py
│   └── sync_state.py
└── utils/
    ├── __init__.py
    └── security.py
```

> ⚠️ **Important:** The ZIP must contain the files at the **root level** — do **not** include the `function_app/` directory itself. When you open the ZIP, you should see `function_app.py` directly, not a folder containing it.

#### Deploy via Kudu

1. Navigate to **Function App** → select your function app
2. In the left menu under **Development Tools**, click **Advanced Tools**
3. Click **Go →** (this opens the Kudu portal in a new tab)
4. In Kudu, navigate to **Tools** → **Zip Push Deploy**
5. Drag and drop your `function_app.zip` file onto the page
6. Wait for the deployment to complete (the page will show progress)

<!-- Screenshot: Kudu Zip Push Deploy page -->

#### Alternative: Deploy via Deployment Center (Local Git)

1. Navigate to **Deployment Center** → select **Local Git** as the source
2. Copy the **Git Clone URI** shown
3. On your local machine, add it as a remote and push:
   ```
   git remote add azure <Git Clone URI>
   git push azure main
   ```

---

## Step 16: Verify Deployment

### 16a: Check Functions Are Loaded

1. Navigate to **Function App** → select your function app
2. In the left menu, click **Functions**
3. You should see the following functions listed:

| Function Name | Trigger Type |
|---|---|
| `mdo_attack_simulation_ingest` | Timer trigger |
| `health` | HTTP (GET) |
| `test_run` | HTTP (POST) |
| `sync_status` | HTTP (GET) |
| `reset_sync_state` | HTTP (POST) |

<!-- Screenshot: Function App Functions list showing all 5 functions -->

> ⚠️ If no functions appear, wait 2–3 minutes for the deployment to complete. If they still don't appear, check the deployment logs (Deployment Center → Logs) for errors.

### 16b: Test the Health Endpoint

1. Click on the `health` function
2. Click **Get function URL** and copy it
3. Open a new browser tab and paste the URL — you should see a response like:
   ```json
   {"status": "healthy", "timestamp": "2024-01-15T10:30:00Z"}
   ```

Alternatively:

1. Click on the `health` function
2. Click **Code + Test** in the left menu
3. Click **Test/Run** at the top
4. Set **HTTP method** to **GET**
5. Click **Run**
6. Verify the response shows status **200** with a healthy status

<!-- Screenshot: Health endpoint returning 200 OK -->

### 16c: Trigger a Test Run

1. Navigate back to **Functions** → click on `test_run`
2. Click **Code + Test**
3. Click **Test/Run**
4. Set **HTTP method** to **POST**
5. Leave the body empty or add `{}`
6. Click **Run**
7. The response should show status **200** (or **202** accepted) — the ingestion process has started

> ⏱ **Note:** The test run may take 2–10 minutes to complete depending on data volume. Check Application Insights for progress.

### 16d: Verify Data in Storage

1. Navigate to **Storage accounts** → select the **data lake** storage account
2. Click **Containers** in the left menu
3. Click on the `curated` container
4. You should see folders for each data source, e.g.:
   ```
   curated/
   ├── repeatOffenders/
   │   └── 2024-01-15/
   │       └── repeatOffenders.parquet
   ├── simulationUserCoverage/
   │   └── 2024-01-15/
   │       └── simulationUserCoverage.parquet
   └── trainingUserCoverage/
       └── 2024-01-15/
           └── trainingUserCoverage.parquet
   ```
5. Click on the `raw` container — verify similar folder structure with `_raw.json` files

<!-- Screenshot: Curated container showing Parquet files organized by date -->

### 16e: Check Application Insights Logs

1. Navigate to **Application Insights** → `mdoast-appi`
2. In the left menu, click **Logs**
3. Close the default queries dialog
4. Enter this query and click **Run**:
   ```kusto
   traces
   | where timestamp > ago(1h)
   | order by timestamp desc
   | take 50
   ```
5. You should see log entries from the ingestion process

<!-- Screenshot: Application Insights Logs query showing ingestion traces -->

---

## Troubleshooting

### Functions Not Appearing

| Symptom | Cause | Fix |
|---------|-------|-----|
| Functions list is empty | Deployment failed or in progress | Check **Deployment Center → Logs** for errors |
| Functions list is empty | Missing `host.json` | Ensure `host.json` is in the root of the deployed ZIP |
| Functions list is empty | Wrong Python version | Verify **Configuration → General settings → Python version** is 3.11 |

### 401 Unauthorized from Graph API

| Symptom | Cause | Fix |
|---------|-------|-----|
| 401 in logs | Admin consent not granted | Go to **Entra ID → App registrations → API permissions** → Grant admin consent |
| 401 in logs | Wrong `TENANT_ID` or `GRAPH_CLIENT_ID` | Verify values match the app registration |
| 401 in logs | Client secret expired | Create a new secret in **Certificates & secrets** and update Key Vault |

### 403 Forbidden on Storage

| Symptom | Cause | Fix |
|---------|-------|-----|
| 403 writing to storage | Missing RBAC role | Verify **Storage Blob Data Contributor** role on the data lake account (Step 11d) |
| 403 writing to storage | VNet not configured | Verify Function App has VNet integration to `snet-functions` and the storage account allows that subnet |
| 403 writing to storage | Wrong storage URL | Verify `STORAGE_ACCOUNT_URL` uses `.dfs.core.windows.net` (not `.blob.`) |

### 403 Forbidden on Key Vault

| Symptom | Cause | Fix |
|---------|-------|-----|
| 403 reading secret | Missing RBAC role | Verify **Key Vault Secrets User** role (Step 11e) |
| 403 reading secret | Access policy instead of RBAC | Ensure Key Vault uses **Azure RBAC** permission model, not Vault access policy |
| 403 reading secret | Firewall blocking | Verify Key Vault networking allows the `snet-functions` subnet and trusted Microsoft services |

### Function Timing Out

| Symptom | Cause | Fix |
|---------|-------|-----|
| Function exceeds timeout | Large data volume | The default timeout is 15 minutes (`host.json`). Consider switching `SYNC_MODE` to `incremental` |
| Function exceeds timeout | API rate limiting | Check for 429 responses in logs; the function has built-in retry with exponential backoff |

### Application Insights Shows No Data

| Symptom | Cause | Fix |
|---------|-------|-----|
| No traces/logs | Missing connection string | Verify `APPLICATIONINSIGHTS_CONNECTION_STRING` in app settings |
| No traces/logs | Wrong App Insights resource | Ensure the connection string matches `mdoast-appi` |

### Common App Setting Mistakes

| Mistake | Impact | Fix |
|---------|--------|-----|
| `STORAGE_ACCOUNT_URL` uses `.blob.` instead of `.dfs.` | Data writes fail | Change to `https://<name>.dfs.core.windows.net` |
| `KEY_VAULT_URL` missing trailing `/` | May work but inconsistent | Use `https://<name>.vault.azure.net/` |
| `AzureWebJobsStorage` has connection string | Conflicts with identity-based auth | Remove and replace with the four `AzureWebJobsStorage__*` settings |
| `TIMER_SCHEDULE` in wrong CRON format | Timer trigger won't fire | Use 6-part format: `{second} {minute} {hour} {day} {month} {day-of-week}` |

---

## Appendix: Resource Naming Reference

Summary of all resources created in this guide. Replace the unique suffixes with your actual values.

| Resource | Type | Name (Example) |
|----------|------|-----------------|
| Resource Group | Resource Group | `rg-mdo-attack-simulation` |
| Virtual Network | Virtual Network | `mdoast-vnet` |
| Subnet | Subnet | `snet-functions` |
| Log Analytics | Log Analytics Workspace | `mdoast-law` |
| Application Insights | Application Insights | `mdoast-appi` |
| Function Storage | Storage Account | `mdoastfn2024prod` |
| Data Lake (ADLS Gen2) | Storage Account (HNS) | `mdoastdl2024prod` |
| Key Vault | Key Vault | `mdoast-kv-2024prod` |
| App Service Plan | App Service Plan | `mdoast-asp` |
| Function App | Function App | `mdoast-func-2024prod` |
| App Registration | Entra ID App | `MDOAttackSimulation-GraphAPI` |
| Key Vault Secret | Secret | `graph-client-secret` |

### Resource Relationships

```
rg-mdo-attack-simulation
├── mdoast-vnet
│   └── snet-functions (subnet, delegated to Microsoft.Web/serverFarms)
├── mdoast-law (Log Analytics)
├── mdoast-appi (Application Insights → mdoast-law)
├── mdoastfn2024prod (Function Storage)
├── mdoastdl2024prod (Data Lake, HNS enabled)
│   ├── curated/ (Parquet files for Power BI)
│   ├── raw/ (JSON archives)
│   └── state/ (sync state tracking)
├── mdoast-kv-2024prod (Key Vault, RBAC mode)
│   └── graph-client-secret
├── mdoast-asp (App Service Plan, B1 Linux)
└── mdoast-func-2024prod (Function App, Python 3.11)
    └── System-assigned Managed Identity
        ├── → Storage Blob Data Contributor on mdoastfn2024prod
        ├── → Storage Queue Data Contributor on mdoastfn2024prod
        ├── → Storage Table Data Contributor on mdoastfn2024prod
        ├── → Storage Blob Data Contributor on mdoastdl2024prod
        └── → Key Vault Secrets User on mdoast-kv-2024prod
```

### Estimated Monthly Cost

| Resource | SKU | Estimated Cost |
|----------|-----|---------------|
| App Service Plan (B1) | Basic | ~$13/month |
| Storage Account (Function) | Standard LRS | ~$1/month |
| Storage Account (Data Lake) | Standard LRS | ~$1–5/month |
| Key Vault | Standard | ~$0.03/secret/month |
| Application Insights | Pay-as-you-go | ~$2–5/month |
| Log Analytics | Per GB | ~$2–5/month |
| Virtual Network | — | Free |
| **Total** | | **~$20–30/month** |

> Costs vary by region and usage. Use the [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) for precise estimates.
