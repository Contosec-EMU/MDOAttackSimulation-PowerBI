<#
.SYNOPSIS
    Deploys the MDO Attack Simulation Training data pipeline to Azure.

.DESCRIPTION
    This script automates the deployment of:
    - Azure infrastructure via Bicep
    - Key Vault secret configuration
    - Function App code deployment

.PARAMETER SubscriptionId
    Azure subscription ID

.PARAMETER ResourceGroupName
    Name for the resource group

.PARAMETER Location
    Azure region (default: eastus)

.PARAMETER TenantId
    Entra ID tenant ID for Graph API

.PARAMETER GraphClientId
    App registration client ID

.PARAMETER GraphClientSecret
    App registration client secret (will be stored in Key Vault)

.EXAMPLE
    .\deploy.ps1 -SubscriptionId "xxx" -TenantId "xxx" -GraphClientId "xxx" -GraphClientSecret "xxx"
#>

param(
    [Parameter(Mandatory=$false)]
    [string]$SubscriptionId,

    [Parameter(Mandatory=$false)]
    [string]$ResourceGroupName = "rg-mdo-attack-simulation",

    [Parameter(Mandatory=$false)]
    [string]$Location = "eastus",

    [Parameter(Mandatory=$false)]
    [string]$TenantId,

    [Parameter(Mandatory=$false)]
    [string]$GraphClientId,

    [Parameter(Mandatory=$false)]
    [string]$GraphClientSecret
)

$ErrorActionPreference = "Stop"

Write-Host "=== MDO Attack Simulation Pipeline Deployment ===" -ForegroundColor Cyan

# Prompt for secret if not provided
if (-not $GraphClientSecret) {
    $GraphClientSecret = Read-Host -Prompt "Enter Graph Client Secret"
}

$PlainSecret = $GraphClientSecret

# Read all values from parameters file
$paramsFile = "$PSScriptRoot\..\infra\main.bicepparam"
if (-not (Test-Path $paramsFile)) {
    throw "Parameters file not found: $paramsFile"
}
$paramsContent = Get-Content $paramsFile -Raw

# Parse subscriptionId (from comment line in params file)
if (-not $SubscriptionId) {
    if ($paramsContent -match "// subscriptionId = '([^']+)'") {
        $SubscriptionId = $Matches[1]
        if ($SubscriptionId -eq '<YOUR_SUBSCRIPTION_ID>') {
            throw "SubscriptionId not set in main.bicepparam. Run 'az account list -o table' and update the file."
        }
        Write-Host "Using subscriptionId from parameters file" -ForegroundColor Cyan
    } else {
        # Fall back to current subscription
        $SubscriptionId = az account show --query "id" -o tsv
        Write-Host "Using current Azure CLI subscription: $SubscriptionId" -ForegroundColor Cyan
    }
}

# Parse tenantId
if (-not $TenantId) {
    if ($paramsContent -match "param tenantId = '([^']+)'") {
        $TenantId = $Matches[1]
        if ($TenantId -eq '<YOUR_TENANT_ID>') {
            throw "TenantId not set in main.bicepparam"
        }
        Write-Host "Using tenantId from parameters file" -ForegroundColor Cyan
    } else {
        throw "TenantId not found in main.bicepparam"
    }
}

# Parse graphClientId
if (-not $GraphClientId) {
    if ($paramsContent -match "param graphClientId = '([^']+)'") {
        $GraphClientId = $Matches[1]
        if ($GraphClientId -eq '<YOUR_APP_REGISTRATION_CLIENT_ID>') {
            throw "GraphClientId not set in main.bicepparam"
        }
        Write-Host "Using graphClientId from parameters file" -ForegroundColor Cyan
    } else {
        throw "GraphClientId not found in main.bicepparam"
    }
}

# Parse location
if (-not $Location -or $Location -eq "eastus") {
    if ($paramsContent -match "param location = '([^']+)'") {
        $Location = $Matches[1]
    }
}

# Parse prefix for resource group naming
$Prefix = "mdoast"
if ($paramsContent -match "param prefix = '([^']+)'") {
    $Prefix = $Matches[1]
}
if (-not $ResourceGroupName -or $ResourceGroupName -eq "rg-mdo-attack-simulation") {
    $ResourceGroupName = "rg-$Prefix-attack-simulation"
}

Write-Host "`nConfiguration from parameters file:" -ForegroundColor Green
Write-Host "  Subscription: $SubscriptionId"
Write-Host "  Tenant:       $TenantId"
Write-Host "  Client ID:    $GraphClientId"
Write-Host "  Location:     $Location"
Write-Host "  RG Name:      $ResourceGroupName"

# Step 1: Set subscription
Write-Host "`n[1/5] Setting Azure subscription..." -ForegroundColor Yellow
az account set --subscription $SubscriptionId
if ($LASTEXITCODE -ne 0) { throw "Failed to set subscription" }

# Step 2: Create resource group
Write-Host "`n[2/5] Creating resource group: $ResourceGroupName..." -ForegroundColor Yellow
az group create --name $ResourceGroupName --location $Location --output none
if ($LASTEXITCODE -ne 0) { throw "Failed to create resource group" }

# Step 3: Deploy Bicep
Write-Host "`n[3/5] Deploying infrastructure (Bicep)..." -ForegroundColor Yellow
$deploymentOutput = az deployment group create `
    --resource-group $ResourceGroupName `
    --template-file "$PSScriptRoot\..\infra\main.bicep" `
    --parameters prefix=mdoast location=$Location tenantId=$TenantId graphClientId=$GraphClientId `
    --query "properties.outputs" `
    --output json | ConvertFrom-Json

if ($LASTEXITCODE -ne 0) { throw "Bicep deployment failed" }

$keyVaultName = $deploymentOutput.keyVaultName.value
$functionAppName = $deploymentOutput.functionAppName.value
$dataLakeAccountName = $deploymentOutput.dataLakeAccountName.value

Write-Host "  Key Vault: $keyVaultName" -ForegroundColor Green
Write-Host "  Function App: $functionAppName" -ForegroundColor Green
Write-Host "  Data Lake Storage: $dataLakeAccountName" -ForegroundColor Green

# Step 4: Store secret in Key Vault
Write-Host "`n[4/5] Storing Graph client secret in Key Vault..." -ForegroundColor Yellow
az keyvault secret set `
    --vault-name $keyVaultName `
    --name "graph-client-secret" `
    --value $PlainSecret `
    --output none
if ($LASTEXITCODE -ne 0) { throw "Failed to store secret in Key Vault" }

# Step 5: Deploy Function code
Write-Host "`n[5/5] Deploying Function App code..." -ForegroundColor Yellow
Push-Location "$PSScriptRoot\..\src\function_app"
try {
    func azure functionapp publish $functionAppName --python
    if ($LASTEXITCODE -ne 0) { throw "Function deployment failed" }
} finally {
    Pop-Location
}

# Summary
Write-Host "`n=== Deployment Complete ===" -ForegroundColor Green
Write-Host @"

Resources Created:
  Resource Group:    $ResourceGroupName
  Data Lake Storage: $dataLakeAccountName
  Function App:      $functionAppName
  Key Vault:         $keyVaultName

Next Steps:
  1. Verify deployment: az functionapp show -g $ResourceGroupName -n $functionAppName
  2. Test function manually via Azure Portal or CLI
  3. Configure Power BI to connect to: https://$dataLakeAccountName.dfs.core.windows.net/curated

Power BI Connection:
  Storage URL: https://$dataLakeAccountName.dfs.core.windows.net/
  Container:   curated
  Format:      Parquet (partitioned by date)

"@ -ForegroundColor Cyan
