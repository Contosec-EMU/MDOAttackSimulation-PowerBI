# Gateway VM - Quick Reference Card

## Deployment Commands

### PowerShell (Windows)
```powershell
cd C:\repos\MDOAttackSimulation_PowerBI
az login
az account set --subscription ea321fd5-c995-4231-bebd-5d3fa7fff0fd
.\scripts\deploy-gateway-vm.ps1
```

### Bash (macOS/Linux/WSL)
```bash
cd /mnt/c/repos/MDOAttackSimulation_PowerBI
az login
az account set --subscription ea321fd5-c995-4231-bebd-5d3fa7fff0fd
./scripts/deploy-gateway-vm.sh
```

## Resource Names

| Resource | Name |
|----------|------|
| VM | `mdoast-gateway-vm` |
| Bastion | `mdoast-bastion-sswuqpmzpslng` |
| VM Subnet | `snet-gateway` (10.0.2.0/24) |
| Bastion Subnet | `AzureBastionSubnet` (10.0.3.0/26) |
| Storage Account | `mdoastdlsswuqpmzpslng` |
| Resource Group | `rg-mdo-attack-simulation` |

## VM Credentials

- **Username**: `azureuser`
- **Password**: (set during deployment)
- **RDP Access**: Via Azure Bastion only (no public IP)

## Connection Steps

1. **Open Azure Portal**: https://portal.azure.com
2. **Search**: `mdoast-gateway-vm`
3. **Click**: Connect → Bastion
4. **Login**: Username + Password
5. **Browser RDP opens**

## Gateway Installation

1. **Download**: https://go.microsoft.com/fwlink/?linkid=2235690
2. **Run as Administrator**
3. **Sign in** with Power BI account
4. **Name**: `MDO-AttackSim-Gateway`
5. **Save recovery key** securely

## Storage Configuration

- **URL**: `https://mdoastdlsswuqpmzpslng.dfs.core.windows.net/`
- **Container**: `curated`
- **Authentication**: OAuth2 or Service Principal
- **Required Role**: Storage Blob Data Reader

## Common Commands

### Start VM
```bash
az vm start -g rg-mdo-attack-simulation -n mdoast-gateway-vm
```

### Stop VM (saves compute cost)
```bash
az vm deallocate -g rg-mdo-attack-simulation -n mdoast-gateway-vm
```

### Check VM Status
```bash
az vm get-instance-view -g rg-mdo-attack-simulation -n mdoast-gateway-vm \
  --query instanceView.statuses[1].displayStatus -o tsv
```

### Check Gateway from VM
```powershell
# Test storage connectivity
Test-NetConnection -ComputerName mdoastdlsswuqpmzpslng.dfs.core.windows.net -Port 443

# Check gateway service
Get-Service -Name "On-premises data gateway service"

# Restart gateway service
Restart-Service -Name "On-premises data gateway service"
```

### View Costs
```bash
# Open Cost Analysis
https://portal.azure.com/#view/Microsoft_Azure_CostManagement/Menu/~/costanalysis

# CLI cost query (requires Microsoft.CostManagement extension)
az costmanagement query \
  --type Usage \
  --dataset-filter "{\"and\":[{\"dimensions\":{\"name\":\"ResourceGroup\",\"operator\":\"In\",\"values\":[\"rg-mdo-attack-simulation\"]}}]}" \
  --timeframe MonthToDate
```

## Cost Breakdown

| Resource | SKU | Monthly Cost |
|----------|-----|--------------|
| Azure Bastion | Basic | ~$140 |
| VM (running) | B2s | ~$36 |
| VM (with auto-shutdown) | B2s | ~$24 |
| Storage | 127GB HDD | ~$2 |
| **TOTAL** | | **~$166-178** |

## Cost Optimization

### Option 1: Stop VM when not needed
```bash
# Stop (deallocate) to stop billing
az vm deallocate -g rg-mdo-attack-simulation -n mdoast-gateway-vm

# Start when needed
az vm start -g rg-mdo-attack-simulation -n mdoast-gateway-vm
```
**Savings**: ~$24/month if stopped 16 hrs/day

### Option 2: Delete Bastion after setup
```bash
az network bastion delete -g rg-mdo-attack-simulation -n mdoast-bastion-sswuqpmzpslng
```
**Savings**: ~$140/month (but no remote access without VPN)

### Option 3: Downgrade VM to B1s
```bash
az vm deallocate -g rg-mdo-attack-simulation -n mdoast-gateway-vm
az vm resize -g rg-mdo-attack-simulation -n mdoast-gateway-vm --size Standard_B1s
az vm start -g rg-mdo-attack-simulation -n mdoast-gateway-vm
```
**Savings**: ~$12/month (may impact gateway performance)

## Troubleshooting

### Gateway Offline
```powershell
# On VM via Bastion
Get-Service "On-premises data gateway service" | Restart-Service
```

### Storage Connection Failed
```bash
# Verify firewall rule
az storage account show -n mdoastdlsswuqpmzpslng -g rg-mdo-attack-simulation \
  --query "networkRuleSet.virtualNetworkRules[].virtualNetworkResourceId" -o table
```

### Bastion Connection Failed
```bash
# Check Bastion status
az network bastion show -g rg-mdo-attack-simulation -n mdoast-bastion-sswuqpmzpslng \
  --query provisioningState -o tsv

# Check VM is running
az vm get-instance-view -g rg-mdo-attack-simulation -n mdoast-gateway-vm \
  --query instanceView.statuses[1].displayStatus -o tsv
```

## Power BI Configuration

### Add Data Source in Power BI Service
1. **Gateways**: https://app.powerbi.com (Settings → Manage gateways)
2. **Select**: `MDO-AttackSim-Gateway`
3. **New data source**: Azure Data Lake Storage Gen2
4. **URL**: `https://mdoastdlsswuqpmzpslng.dfs.core.windows.net/`
5. **Auth**: OAuth2
6. **Test**: Connection should succeed

### Power BI Desktop Connection
1. **Get Data** → Azure → ADLS Gen2
2. **URL**: `https://mdoastdlsswuqpmzpslng.dfs.core.windows.net/curated/`
3. **Gateway**: Select `MDO-AttackSim-Gateway`
4. **Browse**: Select Parquet files
5. **Load**: Import or DirectQuery

## File Paths on VM

| Item | Path |
|------|------|
| Gateway App | `C:\Program Files\On-premises data gateway\` |
| Gateway Logs | `C:\Users\azureuser\AppData\Local\Microsoft\On-premises data gateway\` |
| Gateway Config | `C:\ProgramData\Microsoft\On-premises data gateway\` |

## Useful URLs

- **Azure Portal**: https://portal.azure.com
- **Power BI Service**: https://app.powerbi.com
- **Gateway Download**: https://go.microsoft.com/fwlink/?linkid=2235690
- **Cost Management**: https://portal.azure.com/#view/Microsoft_Azure_CostManagement/Menu/~/overview
- **Full Documentation**: `C:\repos\MDOAttackSimulation_PowerBI\docs\GATEWAY_VM_SETUP.md`

## Auto-Shutdown Schedule

- **Time**: 7:00 PM Pacific (2:00 AM UTC next day)
- **Timezone**: Pacific Standard Time
- **Status**: Enabled by default

### Disable Auto-Shutdown
```bash
az vm auto-shutdown -g rg-mdo-attack-simulation -n mdoast-gateway-vm --off
```

### Change Shutdown Time
```bash
# Example: 10 PM Pacific (6 AM UTC next day)
az vm auto-shutdown \
  -g rg-mdo-attack-simulation \
  -n mdoast-gateway-vm \
  --time 0600
```

## Complete Cleanup

### Delete All Gateway Resources
```bash
# VM and NIC
az vm delete -g rg-mdo-attack-simulation -n mdoast-gateway-vm --yes
az network nic delete -g rg-mdo-attack-simulation -n mdoast-gateway-nic-sswuqpmzpslng

# Bastion and Public IP
az network bastion delete -g rg-mdo-attack-simulation -n mdoast-bastion-sswuqpmzpslng
az network public-ip delete -g rg-mdo-attack-simulation -n mdoast-bastion-pip-sswuqpmzpslng

# Subnets (do last)
az network vnet subnet delete -g rg-mdo-attack-simulation --vnet-name mdoast-vnet-sswuqpmzpslng -n AzureBastionSubnet
az network vnet subnet delete -g rg-mdo-attack-simulation --vnet-name mdoast-vnet-sswuqpmzpslng -n snet-gateway
```

## Support Contacts

- **Azure Support**: https://portal.azure.com/#blade/Microsoft_Azure_Support/HelpAndSupportBlade
- **Power BI Support**: https://support.powerbi.com
- **Full Guide**: `C:\repos\MDOAttackSimulation_PowerBI\docs\GATEWAY_VM_SETUP.md`
