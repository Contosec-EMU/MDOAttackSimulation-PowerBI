# On-Premises Data Gateway VM Setup Guide

This guide walks you through deploying a Windows VM with Azure Bastion to host the On-Premises Data Gateway for Power BI access to the MDO Attack Simulation data in ADLS Gen2.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Quick Start](#quick-start)
- [Step-by-Step Deployment](#step-by-step-deployment)
- [Post-Deployment Configuration](#post-deployment-configuration)
- [Connecting to Power BI](#connecting-to-power-bi)
- [Cost Optimization](#cost-optimization)
- [Troubleshooting](#troubleshooting)

## Overview

### Why This Solution?

**Problem**: Your organization's Azure Policy blocks VMs from having public IPs, but you need to access a Windows VM from home to configure the On-Premises Data Gateway for Power BI.

**Solution**: Azure Bastion provides secure, browser-based RDP access without requiring a public IP on the VM. The gateway VM can then access ADLS Gen2 through VNet integration.

### What Gets Deployed

1. **VM Subnet** (`snet-gateway`): 10.0.2.0/24 - Hosts the gateway VM
2. **Bastion Subnet** (`AzureBastionSubnet`): 10.0.3.0/26 - Dedicated Bastion subnet (required)
3. **Azure Bastion** (Basic tier): Secure RDP access from anywhere via Azure Portal
4. **Windows VM** (B2s, Windows Server 2022): Runs the On-Premises Data Gateway
5. **Storage Firewall Rule**: Allows gateway subnet to access ADLS Gen2
6. **Auto-Shutdown Schedule**: Turns off VM at 7 PM Pacific to save costs

### Estimated Costs

| Resource | SKU | Monthly Cost |
|----------|-----|--------------|
| Azure Bastion | Basic | ~$140 |
| Windows VM | B2s (2 vCPU, 4GB RAM) | ~$36 |
| Managed Disk | 127GB Standard HDD | ~$2 |
| **TOTAL** | | **~$178/month** |

**Cost Optimization**: Auto-shutdown saves ~$12/month on VM costs. See [Cost Optimization](#cost-optimization) for more options.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ Azure Virtual Network (mdoast-vnet-sswuqpmzpslng)          │
│ Address Space: 10.0.0.0/16                                  │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ snet-functions (10.0.1.0/24)                           │ │
│  │ - Azure Function App                                   │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ snet-gateway (10.0.2.0/24)                    [NEW]    │ │
│  │ - Gateway VM (NO PUBLIC IP)                            │ │
│  │ - VNet Service Endpoint to Storage                     │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │ AzureBastionSubnet (10.0.3.0/26)             [NEW]    │ │
│  │ - Azure Bastion (has public IP)                        │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                          │
                          │ VNet Integration
                          ▼
         ┌──────────────────────────────────────┐
         │ Storage Account Firewall             │
         │ - Allow: snet-functions              │
         │ - Allow: snet-gateway     [UPDATED]  │
         │ - Allow: Azure Services              │
         │ - Default: Deny                      │
         └──────────────────────────────────────┘

User at Home ──HTTPS──> Azure Portal ──Bastion──> Gateway VM
                                                       │
                                                       │ VNet
                                                       ▼
                                                   ADLS Gen2
```

### Security Highlights

- **No Public IP on VM**: Complies with corporate policy
- **Bastion-Only Access**: RDP traffic never exposed to internet
- **Storage Firewall**: Only allows traffic from approved subnets
- **Managed Identity**: VM uses Azure AD for resource authentication
- **Auto-Updates**: Windows updates applied automatically

## Prerequisites

### Azure Permissions

- **Subscription**: `ea321fd5-c995-4231-bebd-5d3fa7fff0fd`
- **Resource Group**: `rg-mdo-attack-simulation`
- **Required Roles**: Contributor (or Network Contributor + Virtual Machine Contributor)

### Local Tools

- **Azure CLI**: [Install](https://aka.ms/installazurecli)
- **PowerShell 7+** (for PowerShell script): [Install](https://aka.ms/install-powershell)
- **Bash** (for bash script): Git Bash, WSL2, or macOS/Linux terminal

### Power BI Requirements

- **Power BI Pro or Premium license**
- **Power BI account** with permissions to create gateways
- **ADLS Gen2 permissions**: Storage Blob Data Reader on `mdoastdlsswuqpmzpslng`

## Quick Start

### Option 1: PowerShell (Windows)

```powershell
# Navigate to repo
cd C:\repos\MDOAttackSimulation_PowerBI

# Login to Azure
az login
az account set --subscription ea321fd5-c995-4231-bebd-5d3fa7fff0fd

# Run deployment script (will prompt for password)
.\scripts\deploy-gateway-vm.ps1
```

### Option 2: Bash (macOS/Linux/WSL)

```bash
# Navigate to repo
cd /mnt/c/repos/MDOAttackSimulation_PowerBI

# Login to Azure
az login
az account set --subscription ea321fd5-c995-4231-bebd-5d3fa7fff0fd

# Run deployment script (will prompt for password)
./scripts/deploy-gateway-vm.sh
```

### Option 3: Manual Azure CLI

```bash
# Set variables
SUBSCRIPTION_ID="ea321fd5-c995-4231-bebd-5d3fa7fff0fd"
RESOURCE_GROUP="rg-mdo-attack-simulation"

# Prompt for password (or set directly)
read -s -p "Enter VM admin password: " ADMIN_PASSWORD
echo ""

# Deploy
az deployment group create \
  --subscription "$SUBSCRIPTION_ID" \
  --resource-group "$RESOURCE_GROUP" \
  --template-file infra/gateway-vm.bicep \
  --parameters infra/gateway-vm.bicepparam \
  --parameters adminPassword="$ADMIN_PASSWORD" \
  --name "gateway-vm-$(date +%Y%m%d-%H%M%S)"
```

**Deployment Time**: 10-15 minutes

## Step-by-Step Deployment

### 1. Review Configuration

Edit `C:\repos\MDOAttackSimulation_PowerBI\infra\gateway-vm.bicepparam` if you want to change:

- **VM Size**: `Standard_B2s` (recommended) or `Standard_B1s` (cheaper but slower)
- **Auto-Shutdown**: Time and timezone (default: 7 PM Pacific)
- **Subnet Ranges**: VM subnet and Bastion subnet CIDR blocks

### 2. Prepare Password

Create a strong password for the VM admin account:

**Requirements**:
- Length: 12-72 characters
- Must contain 3 of: lowercase, uppercase, digit, special character
- Cannot contain username (`azureuser`)

**Example**: `MyGateway2026!Secure`

### 3. Run Deployment Script

**PowerShell**:
```powershell
.\scripts\deploy-gateway-vm.ps1
```

**Bash**:
```bash
./scripts/deploy-gateway-vm.sh
```

The script will:
1. Check prerequisites (Azure CLI, files)
2. Prompt for VM admin password (twice)
3. Show estimated costs and ask for confirmation
4. Deploy resources in this order:
   - Create `snet-gateway` subnet
   - Create `AzureBastionSubnet`
   - Update storage account firewall
   - Create Bastion public IP
   - Deploy Azure Bastion
   - Create VM NIC
   - Deploy Windows VM
   - Configure auto-shutdown schedule
5. Display deployment outputs and next steps

### 4. Verify Deployment

Check that all resources were created:

```bash
# List resources in resource group
az resource list -g rg-mdo-attack-simulation -o table

# Check VM status
az vm show -g rg-mdo-attack-simulation -n mdoast-gateway-vm --query "{name:name, powerState:instanceView.statuses[1].displayStatus}" -o table

# Check Bastion status
az network bastion show -g rg-mdo-attack-simulation -n mdoast-bastion-sswuqpmzpslng --query "{name:name, state:provisioningState}" -o table

# Verify storage firewall includes new subnet
az storage account show -n mdoastdlsswuqpmzpslng -g rg-mdo-attack-simulation --query "networkRuleSet.virtualNetworkRules[].virtualNetworkResourceId" -o table
```

## Post-Deployment Configuration

### Step 1: Connect to VM via Bastion

1. **Open Azure Portal**: [https://portal.azure.com](https://portal.azure.com)

2. **Navigate to VM**:
   - Search for `mdoast-gateway-vm`
   - Click on the VM

3. **Connect via Bastion**:
   - Click **Connect** button
   - Select **Bastion** tab
   - Enter credentials:
     - **Username**: `azureuser`
     - **Password**: (the password you created during deployment)
   - Click **Connect**

4. **Browser RDP Session Opens**: A new browser tab opens with the VM desktop

### Step 2: Install On-Premises Data Gateway

**On the VM (via Bastion session)**:

1. **Open Browser** (Edge is pre-installed)

2. **Download Gateway Installer**:
   - URL: [https://go.microsoft.com/fwlink/?linkid=2235690](https://go.microsoft.com/fwlink/?linkid=2235690)
   - Save to Desktop

3. **Run Installer**:
   - Right-click installer
   - Select **Run as Administrator**
   - Accept UAC prompt

4. **Installation Wizard**:
   - Accept license terms
   - Keep default installation path
   - Click **Install**

5. **Gateway Configuration**:
   - Select **Register a new gateway on this computer**
   - Click **Sign in**
   - Sign in with your **Power BI account** (work/school account)
   - Enter a **gateway name**: `MDO-AttackSim-Gateway`
   - Enter a **recovery key** (save this securely!)
   - Click **Configure**

6. **Verify Gateway**:
   - Gateway status should show **Online**
   - Note the gateway name for Power BI configuration

### Step 3: Test Connectivity to ADLS Gen2

**On the VM (via Bastion session)**:

1. **Open PowerShell as Administrator**

2. **Install Azure PowerShell** (if not already installed):
   ```powershell
   Install-Module -Name Az -Repository PSGallery -Force -AllowClobber
   ```

3. **Test Storage Connectivity**:
   ```powershell
   # Test DNS resolution
   nslookup mdoastdlsswuqpmzpslng.dfs.core.windows.net

   # Test HTTPS connectivity
   Test-NetConnection -ComputerName mdoastdlsswuqpmzpslng.dfs.core.windows.net -Port 443

   # Login to Azure
   Connect-AzAccount

   # Test access to storage account
   Get-AzStorageAccount -ResourceGroupName rg-mdo-attack-simulation -Name mdoastdlsswuqpmzpslng
   ```

4. **Expected Results**:
   - DNS resolves to private IP (if using private endpoint) or public IP
   - Port 443 is reachable
   - No firewall errors

## Connecting to Power BI

### Configure Data Source in Power BI Service

1. **Open Power BI Service**: [https://app.powerbi.com](https://app.powerbi.com)

2. **Navigate to Gateway Settings**:
   - Click gear icon (Settings) → **Manage connections and gateways**
   - Select **Gateways** tab
   - You should see `MDO-AttackSim-Gateway` with status **Online**

3. **Add Data Source**:
   - Click on your gateway
   - Click **New** (New data source)
   - Configure:
     - **Data Source Name**: `MDO Attack Simulation ADLS Gen2`
     - **Data Source Type**: `Azure Data Lake Storage Gen2`
     - **Account Name or URL**: `https://mdoastdlsswuqpmzpslng.dfs.core.windows.net/`
     - **Authentication Method**: `OAuth2` (recommended) or `Service Principal`

4. **OAuth2 Authentication** (Recommended):
   - Click **Sign in**
   - Sign in with account that has Storage Blob Data Reader role
   - Click **Create**

5. **Service Principal Authentication** (Alternative):
   - **Tenant ID**: `cfb30b1b-1cbf-41ea-9453-7546e858dddd`
   - **Client ID**: (your service principal client ID)
   - **Client Secret**: (your service principal secret)
   - Click **Create**

6. **Test Connection**:
   - Click **Test connection**
   - Should show **Connection successful**

### Create Power BI Report

1. **Open Power BI Desktop** (on your local machine)

2. **Get Data**:
   - Click **Get Data** → **More**
   - Search for `Azure Data Lake Storage Gen2`
   - Click **Connect**

3. **Configure Connection**:
   - **URL**: `https://mdoastdlsswuqpmzpslng.dfs.core.windows.net/curated/`
   - **Data Connectivity Mode**: `DirectQuery` or `Import`
   - Click **OK**

4. **Sign In**:
   - Choose authentication method (same as gateway)
   - Sign in
   - Click **Connect**

5. **Navigate to Data**:
   - Navigate: `curated` → `repeatOffenders` (or other API folder) → date folder
   - Select Parquet file
   - Click **Load**

6. **Publish Report**:
   - Create your visualizations
   - Click **Publish**
   - Select workspace
   - In Power BI Service, configure dataset to use gateway

### Configure Scheduled Refresh

1. **In Power BI Service**:
   - Navigate to your dataset
   - Click **Settings** → **Data source credentials**
   - Ensure gateway connection is configured

2. **Set Refresh Schedule**:
   - Click **Scheduled refresh**
   - Enable **Keep your data up to date**
   - Set frequency: Daily at 3 AM (after function runs at 2 AM)
   - Click **Apply**

## Cost Optimization

### Current Costs (~$178/month)

- **Azure Bastion (Basic)**: ~$140/month (24/7)
- **VM B2s**: ~$36/month → ~$24/month with auto-shutdown
- **Storage**: ~$2/month

### Optimization Strategies

#### 1. Use Smaller VM (if gateway performance is acceptable)

Change VM size to B1s (1 vCPU, 1GB RAM):

```bash
# Stop VM
az vm deallocate -g rg-mdo-attack-simulation -n mdoast-gateway-vm

# Resize
az vm resize -g rg-mdo-attack-simulation -n mdoast-gateway-vm --size Standard_B1s

# Start VM
az vm start -g rg-mdo-attack-simulation -n mdoast-gateway-vm
```

**Savings**: ~$12/month (total: ~$166/month)

#### 2. Manual Start/Stop VM

Turn off VM when not actively configuring gateway:

```bash
# Stop VM
az vm stop -g rg-mdo-attack-simulation -n mdoast-gateway-vm

# Deallocate (releases compute, stops billing)
az vm deallocate -g rg-mdo-attack-simulation -n mdoast-gateway-vm

# Start when needed
az vm start -g rg-mdo-attack-simulation -n mdoast-gateway-vm
```

**Gateway Behavior**: Gateway will appear offline in Power BI when VM is stopped. Scheduled refreshes will fail. You must start VM before refreshes run.

**Savings**: If VM only runs 8 hours/day: ~$24/month (total: ~$166/month)

#### 3. Disable Auto-Shutdown (if gateway needs 24/7 availability)

```bash
az vm auto-shutdown -g rg-mdo-attack-simulation -n mdoast-gateway-vm --off
```

#### 4. Consider Alternatives to Bastion

**For long-term use**, consider these alternatives:

- **VPN Gateway** (Point-to-Site): ~$30/month, allows direct RDP from home
- **Azure AD Application Proxy**: Free, but requires Azure AD P1 license (~$6/user/month)
- **Delete Bastion after initial setup**: If you don't need ongoing remote access

**To delete Bastion** (saves $140/month):

```bash
az network bastion delete -g rg-mdo-attack-simulation -n mdoast-bastion-sswuqpmzpslng
```

**Warning**: You won't be able to RDP to VM after deleting Bastion unless you set up VPN.

### Recommended Cost-Optimized Configuration

**Initial Setup** (Month 1): Use Bastion for configuration (~$178/month)
**Ongoing** (Month 2+):
- Delete Bastion after setup (~$38/month for VM + storage)
- Or keep Bastion but stop VM except during maintenance windows (~$142/month)

## Troubleshooting

### Cannot Connect via Bastion

**Symptom**: "Unable to connect" error in Azure Portal

**Solutions**:
1. Verify Bastion provisioning state:
   ```bash
   az network bastion show -g rg-mdo-attack-simulation -n mdoast-bastion-sswuqpmzpslng --query provisioningState
   ```
   Should be `Succeeded`

2. Check VM is running:
   ```bash
   az vm get-instance-view -g rg-mdo-attack-simulation -n mdoast-gateway-vm --query instanceView.statuses[1].displayStatus
   ```
   Should be `VM running`

3. Verify Bastion subnet exists:
   ```bash
   az network vnet subnet show -g rg-mdo-attack-simulation --vnet-name mdoast-vnet-sswuqpmzpslng -n AzureBastionSubnet
   ```

4. Check NSG rules (if NSGs are attached to subnets)

### Gateway Not Appearing in Power BI

**Symptom**: Gateway shows offline or doesn't appear in gateway list

**Solutions**:
1. **Check Gateway Service**:
   - On VM, open Services (services.msc)
   - Find "On-premises data gateway service"
   - Verify it's Running
   - If stopped, start it

2. **Check Internet Connectivity**:
   ```powershell
   Test-NetConnection -ComputerName powerbi.microsoft.com -Port 443
   Test-NetConnection -ComputerName login.microsoftonline.com -Port 443
   ```

3. **Verify Gateway Registration**:
   - On VM, open "On-premises data gateway" app
   - Click "Service Settings"
   - Verify status is "Online"
   - If offline, try "Restart now"

4. **Check Gateway Logs**:
   - On VM: `C:\Users\azureuser\AppData\Local\Microsoft\On-premises data gateway\GatewayInfo.log`
   - Look for errors

### Cannot Access Storage from VM

**Symptom**: Storage connection fails from VM

**Solutions**:
1. **Verify Firewall Rules**:
   ```bash
   az storage account show -n mdoastdlsswuqpmzpslng -g rg-mdo-attack-simulation --query networkRuleSet.virtualNetworkRules -o table
   ```
   Should include `snet-gateway`

2. **Check Service Endpoint**:
   ```bash
   az network vnet subnet show -g rg-mdo-attack-simulation --vnet-name mdoast-vnet-sswuqpmzpslng -n snet-gateway --query serviceEndpoints -o table
   ```
   Should include `Microsoft.Storage`

3. **Test from VM PowerShell**:
   ```powershell
   # Test DNS
   nslookup mdoastdlsswuqpmzpslng.dfs.core.windows.net

   # Test port
   Test-NetConnection -ComputerName mdoastdlsswuqpmzpslng.dfs.core.windows.net -Port 443
   ```

4. **Add IP to Storage Firewall** (temporary debugging):
   ```bash
   # Get VM's public IP if Bastion is used (won't work for storage)
   # Better: Get VM's outbound public IP
   OUTBOUND_IP=$(curl -s ifconfig.me)  # Run from VM
   az storage account network-rule add -g rg-mdo-attack-simulation --account-name mdoastdlsswuqpmzpslng --ip-address $OUTBOUND_IP
   ```

### Power BI Refresh Fails

**Symptom**: Scheduled refresh shows error in Power BI

**Solutions**:
1. **Check Gateway Status**:
   - Power BI Service → Manage gateways
   - Gateway should be "Online"
   - If offline, start VM

2. **Test Connection**:
   - Click on data source
   - Click "Test connection"
   - View error message

3. **Verify Credentials**:
   - Ensure OAuth token hasn't expired
   - Re-authenticate if needed

4. **Check Gateway Permissions**:
   - Ensure Power BI service principal has Storage Blob Data Reader
   ```bash
   az role assignment list --scope /subscriptions/ea321fd5-c995-4231-bebd-5d3fa7fff0fd/resourceGroups/rg-mdo-attack-simulation/providers/Microsoft.Storage/storageAccounts/mdoastdlsswuqpmzpslng --query "[?principalName=='Power BI Service']" -o table
   ```

### Auto-Shutdown Not Working

**Symptom**: VM doesn't shut down at scheduled time

**Solutions**:
1. **Check Schedule Exists**:
   ```bash
   az vm show -g rg-mdo-attack-simulation -n mdoast-gateway-vm --query "tags.AutoShutdownSchedule"
   ```

2. **View Schedule Details**:
   ```bash
   az resource show --ids "/subscriptions/ea321fd5-c995-4231-bebd-5d3fa7fff0fd/resourceGroups/rg-mdo-attack-simulation/providers/Microsoft.DevTestLab/schedules/shutdown-computevm-mdoast-gateway-vm" -o json
   ```

3. **Manually Trigger Shutdown**:
   ```bash
   az vm stop -g rg-mdo-attack-simulation -n mdoast-gateway-vm
   ```

4. **Disable Schedule**:
   ```bash
   az vm auto-shutdown -g rg-mdo-attack-simulation -n mdoast-gateway-vm --off
   ```

### High Costs

**Symptom**: Azure bill higher than expected

**Solutions**:
1. **Check What's Running**:
   ```bash
   # List all resources and their types
   az resource list -g rg-mdo-attack-simulation --query "[].{name:name, type:type, location:location}" -o table

   # Check VM power state
   az vm list -g rg-mdo-attack-simulation --show-details --query "[].{name:name, powerState:powerState}" -o table
   ```

2. **View Cost Analysis**:
   - Azure Portal → Cost Management + Billing → Cost analysis
   - Filter by resource group: `rg-mdo-attack-simulation`
   - Group by: Resource

3. **Implement Cost Optimizations**:
   - See [Cost Optimization](#cost-optimization) section above
   - Consider deleting Bastion after initial setup
   - Use auto-shutdown or manual stop/start

## Advanced Configuration

### Use Private Endpoint for Storage

For enhanced security, configure private endpoint for ADLS Gen2:

```bash
# Create private endpoint subnet
az network vnet subnet create \
  -g rg-mdo-attack-simulation \
  --vnet-name mdoast-vnet-sswuqpmzpslng \
  -n snet-storage-private-endpoints \
  --address-prefixes 10.0.4.0/24

# Create private endpoint
az network private-endpoint create \
  -g rg-mdo-attack-simulation \
  -n pe-mdoastdlsswuqpmzpslng \
  --vnet-name mdoast-vnet-sswuqpmzpslng \
  --subnet snet-storage-private-endpoints \
  --private-connection-resource-id "/subscriptions/ea321fd5-c995-4231-bebd-5d3fa7fff0fd/resourceGroups/rg-mdo-attack-simulation/providers/Microsoft.Storage/storageAccounts/mdoastdlsswuqpmzpslng" \
  --group-id dfs \
  --connection-name pe-mdoastdlsswuqpmzpslng-connection
```

### Configure Managed Identity for Gateway

Assign managed identity of VM to access storage:

```bash
# Get VM managed identity
IDENTITY=$(az vm show -g rg-mdo-attack-simulation -n mdoast-gateway-vm --query identity.principalId -o tsv)

# Grant Storage Blob Data Reader
az role assignment create \
  --assignee $IDENTITY \
  --role "Storage Blob Data Reader" \
  --scope /subscriptions/ea321fd5-c995-4231-bebd-5d3fa7fff0fd/resourceGroups/rg-mdo-attack-simulation/providers/Microsoft.Storage/storageAccounts/mdoastdlsswuqpmzpslng
```

### Install Additional Tools on VM

Useful tools for gateway management:

```powershell
# Azure PowerShell
Install-Module -Name Az -Repository PSGallery -Force

# Azure Storage Explorer
winget install -e --id Microsoft.AzureStorageExplorer

# PowerShell 7
winget install -e --id Microsoft.PowerShell
```

## Cleanup

### Delete All Gateway Resources

**Warning**: This will delete the VM, Bastion, and subnets. Gateway will stop working.

```bash
# Delete VM
az vm delete -g rg-mdo-attack-simulation -n mdoast-gateway-vm --yes

# Delete NIC
az network nic delete -g rg-mdo-attack-simulation -n mdoast-gateway-nic-sswuqpmzpslng

# Delete Bastion
az network bastion delete -g rg-mdo-attack-simulation -n mdoast-bastion-sswuqpmzpslng

# Delete Bastion Public IP
az network public-ip delete -g rg-mdo-attack-simulation -n mdoast-bastion-pip-sswuqpmzpslng

# Delete subnets (requires no resources attached)
az network vnet subnet delete -g rg-mdo-attack-simulation --vnet-name mdoast-vnet-sswuqpmzpslng -n AzureBastionSubnet
az network vnet subnet delete -g rg-mdo-attack-simulation --vnet-name mdoast-vnet-sswuqpmzpslng -n snet-gateway

# Remove storage firewall rule
az storage account network-rule remove \
  -g rg-mdo-attack-simulation \
  --account-name mdoastdlsswuqpmzpslng \
  --subnet snet-gateway \
  --vnet-name mdoast-vnet-sswuqpmzpslng
```

### Delete Only Bastion (Keep VM)

If you want to keep the VM but stop paying for Bastion:

```bash
az network bastion delete -g rg-mdo-attack-simulation -n mdoast-bastion-sswuqpmzpslng
az network public-ip delete -g rg-mdo-attack-simulation -n mdoast-bastion-pip-sswuqpmzpslng
az network vnet subnet delete -g rg-mdo-attack-simulation --vnet-name mdoast-vnet-sswuqpmzpslng -n AzureBastionSubnet
```

**Note**: You won't be able to access the VM remotely after this unless you set up VPN or Azure AD Application Proxy.

## Resources

- [Azure Bastion Documentation](https://docs.microsoft.com/azure/bastion/)
- [On-Premises Data Gateway Documentation](https://docs.microsoft.com/data-integration/gateway/service-gateway-onprem)
- [Power BI ADLS Gen2 Connector](https://docs.microsoft.com/power-bi/connect-data/service-azure-data-lake-storage-gen2)
- [Azure VM Sizes and Pricing](https://azure.microsoft.com/pricing/details/virtual-machines/windows/)
- [Azure Bastion Pricing](https://azure.microsoft.com/pricing/details/azure-bastion/)

## Support

For issues specific to this deployment:
1. Check [Troubleshooting](#troubleshooting) section
2. Review deployment logs in Azure Portal
3. Check Application Insights for function errors

For Power BI gateway issues:
- [Power BI Gateway Troubleshooting](https://docs.microsoft.com/power-bi/connect-data/service-gateway-onprem-tshoot)
