#!/usr/bin/env pwsh
# ============================================================================
# Deploy On-Premises Data Gateway VM with Azure Bastion
# ============================================================================
# Purpose: Deploy Windows VM accessible via Azure Bastion for Power BI gateway
# Requirements: Azure CLI, PowerShell 7+, Contributor access to resource group
# Usage: .\scripts\deploy-gateway-vm.ps1
# ============================================================================

#Requires -Version 7.0

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ============================================================================
# Configuration
# ============================================================================

$SUBSCRIPTION_ID = "ea321fd5-c995-4231-bebd-5d3fa7fff0fd"
$RESOURCE_GROUP = "rg-mdo-attack-simulation"
$LOCATION = "westus2"
$TEMPLATE_FILE = "infra/gateway-vm.bicep"
$PARAMETERS_FILE = "infra/gateway-vm.bicepparam"

# ============================================================================
# Helper Functions
# ============================================================================

function Write-ColorOutput {
    param(
        [string]$Message,
        [string]$Color = "White"
    )
    Write-Host $Message -ForegroundColor $Color
}

function Write-Section {
    param([string]$Title)
    Write-Host "`n============================================================================" -ForegroundColor Cyan
    Write-Host $Title -ForegroundColor Cyan
    Write-Host "============================================================================`n" -ForegroundColor Cyan
}

function Test-Prerequisites {
    Write-Section "Checking Prerequisites"

    # Check Azure CLI
    if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
        Write-ColorOutput "ERROR: Azure CLI is not installed. Download from https://aka.ms/installazurecliwindows" -Color Red
        exit 1
    }

    $azVersion = az version --query '\"azure-cli\"' -o tsv
    Write-ColorOutput "Azure CLI version: $azVersion" -Color Green

    # Check if logged in
    $account = az account show 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-ColorOutput "ERROR: Not logged into Azure. Run 'az login' first." -Color Red
        exit 1
    }

    $currentSub = az account show --query id -o tsv
    Write-ColorOutput "Current subscription: $currentSub" -Color Green

    # Check files exist
    if (-not (Test-Path $TEMPLATE_FILE)) {
        Write-ColorOutput "ERROR: Bicep template not found: $TEMPLATE_FILE" -Color Red
        exit 1
    }

    if (-not (Test-Path $PARAMETERS_FILE)) {
        Write-ColorOutput "ERROR: Parameters file not found: $PARAMETERS_FILE" -Color Red
        exit 1
    }

    Write-ColorOutput "Prerequisites check passed!" -Color Green
}

function Get-SecurePassword {
    Write-Section "VM Administrator Password"

    Write-ColorOutput "Password requirements:" -Color Yellow
    Write-ColorOutput "  - Length: 12-72 characters" -Color Yellow
    Write-ColorOutput "  - Must contain 3 of: lowercase, uppercase, digit, special character" -Color Yellow
    Write-ColorOutput "  - Cannot contain username" -Color Yellow
    Write-Host ""

    $password = Read-Host "Enter VM admin password" -AsSecureString
    $confirmPassword = Read-Host "Confirm password" -AsSecureString

    # Convert to plain text for comparison
    $pwd1 = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($password))
    $pwd2 = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($confirmPassword))

    if ($pwd1 -ne $pwd2) {
        Write-ColorOutput "ERROR: Passwords do not match!" -Color Red
        exit 1
    }

    if ($pwd1.Length -lt 12 -or $pwd1.Length -gt 72) {
        Write-ColorOutput "ERROR: Password must be 12-72 characters!" -Color Red
        exit 1
    }

    return $pwd1
}

function Invoke-Deployment {
    param([string]$AdminPassword)

    Write-Section "Deploying Gateway VM + Azure Bastion"

    Write-ColorOutput "Subscription: $SUBSCRIPTION_ID" -Color Cyan
    Write-ColorOutput "Resource Group: $RESOURCE_GROUP" -Color Cyan
    Write-ColorOutput "Location: $LOCATION" -Color Cyan
    Write-ColorOutput "Template: $TEMPLATE_FILE" -Color Cyan
    Write-Host ""

    Write-ColorOutput "Estimated monthly costs:" -Color Yellow
    Write-ColorOutput "  - Azure Bastion (Basic): ~$140/month" -Color Yellow
    Write-ColorOutput "  - VM B2s (2 vCPU, 4GB): ~$36/month" -Color Yellow
    Write-ColorOutput "  - Storage (127GB HDD): ~$2/month" -Color Yellow
    Write-ColorOutput "  - TOTAL: ~$178/month" -Color Yellow
    Write-Host ""

    $confirm = Read-Host "Proceed with deployment? (yes/no)"
    if ($confirm -ne "yes") {
        Write-ColorOutput "Deployment cancelled." -Color Yellow
        exit 0
    }

    Write-ColorOutput "`nStarting deployment (this will take 10-15 minutes)..." -Color Green
    Write-ColorOutput "Progress: Creating subnets -> Bastion -> VM -> Storage firewall rules`n" -Color Cyan

    $deploymentName = "gateway-vm-$(Get-Date -Format 'yyyyMMdd-HHmmss')"

    az deployment group create `
        --subscription $SUBSCRIPTION_ID `
        --resource-group $RESOURCE_GROUP `
        --template-file $TEMPLATE_FILE `
        --parameters $PARAMETERS_FILE `
        --parameters adminPassword=$AdminPassword `
        --name $deploymentName `
        --output json | ConvertFrom-Json | Tee-Object -Variable deploymentOutput

    if ($LASTEXITCODE -ne 0) {
        Write-ColorOutput "`nERROR: Deployment failed!" -Color Red
        Write-ColorOutput "Check Azure Portal for details: https://portal.azure.com/#view/HubsExtension/DeploymentDetailsBlade/~/overview/id/%2Fsubscriptions%2F$SUBSCRIPTION_ID%2FresourceGroups%2F$RESOURCE_GROUP%2Fproviders%2FMicrosoft.Resources%2Fdeployments%2F$deploymentName" -Color Red
        exit 1
    }

    return $deploymentOutput
}

function Show-PostDeploymentInfo {
    param($DeploymentOutput)

    Write-Section "Deployment Successful!"

    $outputs = $DeploymentOutput.properties.outputs

    Write-ColorOutput "VM Information:" -Color Green
    Write-ColorOutput "  Name: $($outputs.vmName.value)" -Color White
    Write-ColorOutput "  Private IP: $($outputs.vmPrivateIp.value)" -Color White
    Write-ColorOutput "  Admin Username: $($outputs.adminUsername.value)" -Color White
    Write-ColorOutput "  Size: $($outputs.vmSize.value)" -Color White
    Write-Host ""

    Write-ColorOutput "Azure Bastion:" -Color Green
    Write-ColorOutput "  Name: $($outputs.bastionName.value)" -Color White
    Write-ColorOutput "  Public IP: $($outputs.bastionPublicIp.value)" -Color White
    Write-Host ""

    Write-ColorOutput "Cost Optimization:" -Color Green
    Write-ColorOutput "  Auto-shutdown: Enabled (7 PM Pacific)" -Color White
    Write-ColorOutput "  To disable: az vm auto-shutdown -g $RESOURCE_GROUP -n $($outputs.vmName.value) --off" -Color Yellow
    Write-Host ""

    Write-Section "Next Steps"

    Write-ColorOutput "1. Connect to VM via Azure Bastion:" -Color Cyan
    Write-ColorOutput "   a. Open Azure Portal: https://portal.azure.com" -Color White
    Write-ColorOutput "   b. Navigate to VM: $($outputs.vmName.value)" -Color White
    Write-ColorOutput "   c. Click 'Connect' -> 'Bastion'" -Color White
    Write-ColorOutput "   d. Enter credentials and click 'Connect'" -Color White
    Write-Host ""

    Write-ColorOutput "2. Install On-Premises Data Gateway on VM:" -Color Cyan
    Write-ColorOutput "   a. Download: https://go.microsoft.com/fwlink/?linkid=2235690" -Color White
    Write-ColorOutput "   b. Run installer as Administrator" -Color White
    Write-ColorOutput "   c. Sign in with your Power BI account" -Color White
    Write-ColorOutput "   d. Register gateway with a unique name" -Color White
    Write-Host ""

    Write-ColorOutput "3. Configure Power BI Connection:" -Color Cyan
    Write-ColorOutput "   a. In Power BI: Settings -> Manage connections and gateways" -Color White
    Write-ColorOutput "   b. Select your gateway" -Color White
    Write-ColorOutput "   c. Add data source: Azure Data Lake Storage Gen2" -Color White
    Write-ColorOutput "   d. URL: https://mdoastdlsswuqpmzpslng.dfs.core.windows.net/" -Color White
    Write-ColorOutput "   e. Authentication: OAuth 2.0 or Service Principal" -Color White
    Write-Host ""

    Write-ColorOutput "4. Test Connection:" -Color Cyan
    Write-ColorOutput "   a. In Power BI Desktop: Get Data -> Azure -> ADLS Gen2" -Color White
    Write-ColorOutput "   b. Use gateway for connection" -Color White
    Write-ColorOutput "   c. Browse to 'curated' container" -Color White
    Write-ColorOutput "   d. Load Parquet files" -Color White
    Write-Host ""

    Write-Section "Important Notes"

    Write-ColorOutput "Security:" -Color Yellow
    Write-ColorOutput "  - VM has NO public IP (only accessible via Bastion)" -Color White
    Write-ColorOutput "  - Storage firewall allows traffic from gateway subnet" -Color White
    Write-ColorOutput "  - Managed Identity assigned to VM for Azure resource access" -Color White
    Write-Host ""

    Write-ColorOutput "Costs:" -Color Yellow
    Write-ColorOutput "  - Bastion runs 24/7 (~$140/month)" -Color White
    Write-ColorOutput "  - VM auto-shuts down at 7 PM Pacific (saves ~$12/month)" -Color White
    Write-ColorOutput "  - To reduce costs further, consider Developer tier Bastion when available" -Color White
    Write-Host ""

    Write-ColorOutput "Troubleshooting:" -Color Yellow
    Write-ColorOutput "  - Cannot connect to storage from VM?" -Color White
    Write-ColorOutput "    Check VNet integration: az storage account show -n mdoastdlsswuqpmzpslng -g $RESOURCE_GROUP --query networkRuleSet" -Color White
    Write-ColorOutput "  - Gateway not appearing in Power BI?" -Color White
    Write-ColorOutput "    Verify internet connectivity from VM and gateway service is running" -Color White
    Write-Host ""

    Write-ColorOutput "Deployment Complete! You can now connect to the VM via Bastion." -Color Green
}

# ============================================================================
# Main Execution
# ============================================================================

try {
    Write-Section "Gateway VM + Bastion Deployment Script"

    # Run checks
    Test-Prerequisites

    # Get password
    $adminPassword = Get-SecurePassword

    # Deploy
    $deploymentOutput = Invoke-Deployment -AdminPassword $adminPassword

    # Show next steps
    Show-PostDeploymentInfo -DeploymentOutput $deploymentOutput

} catch {
    Write-ColorOutput "`nERROR: $_" -Color Red
    Write-ColorOutput $_.ScriptStackTrace -Color Red
    exit 1
}
