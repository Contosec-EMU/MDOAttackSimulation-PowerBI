<#
.SYNOPSIS
    Deploy the Streamlit Executive Dashboard to Azure.

.DESCRIPTION
    Deploys the dashboard.bicep module and publishes the Streamlit app
    to the Azure Web App on the existing B1 App Service Plan.
    Automatically creates an Entra ID app registration for EasyAuth
    if a DashboardClientId is not provided.

.PARAMETER ResourceGroup
    Name of the resource group containing the existing infrastructure.

.PARAMETER DashboardClientId
    (Optional) Entra ID App Registration Client ID for the dashboard.
    If not provided, a new app registration is created automatically.

.EXAMPLE
    .\deploy-dashboard.ps1 -ResourceGroup "rg-mdo-attack-simulation"

.EXAMPLE
    .\deploy-dashboard.ps1 -ResourceGroup "rg-mdo-attack-simulation" -DashboardClientId "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$ResourceGroup,

    [Parameter(Mandatory=$false)]
    [string]$DashboardClientId
)

$ErrorActionPreference = "Stop"

Write-Host "=== MDO Attack Simulation — Dashboard Deployment ===" -ForegroundColor Cyan

# Verify resource group exists
Write-Host "`n1. Reading existing infrastructure..." -ForegroundColor Yellow
$rgExists = az group exists --name $ResourceGroup -o tsv
if ($rgExists -ne "true") {
    Write-Host "ERROR: Resource group '$ResourceGroup' not found. Deploy the main infrastructure first." -ForegroundColor Red
    exit 1
}

# Find the main deployment outputs (try common deployment names)
$MAIN_OUTPUTS = $null
foreach ($deployName in @("main", "azure-deploy", $ResourceGroup)) {
    $MAIN_OUTPUTS = az deployment group show `
        --resource-group $ResourceGroup `
        --name $deployName `
        --query "properties.outputs" -o json 2>$null | ConvertFrom-Json
    if ($MAIN_OUTPUTS) {
        Write-Host "  Found deployment: $deployName"
        break
    }
}

if (-not $MAIN_OUTPUTS) {
    Write-Host "ERROR: Could not find the main Bicep deployment in resource group '$ResourceGroup'." -ForegroundColor Red
    Write-Host "  Expected a deployment named 'main'. List deployments with:" -ForegroundColor Yellow
    Write-Host "    az deployment group list --resource-group $ResourceGroup --query ""[].name"" -o tsv" -ForegroundColor Yellow
    exit 1
}

$APP_SERVICE_PLAN_NAME = az appservice plan list `
    --resource-group $ResourceGroup `
    --query "[0].id" -o tsv

if (-not $APP_SERVICE_PLAN_NAME) {
    Write-Host "ERROR: No App Service Plan found in resource group '$ResourceGroup'." -ForegroundColor Red
    exit 1
}

$DATA_LAKE_NAME = $MAIN_OUTPUTS.dataLakeAccountName.value
$STORAGE_URL = $MAIN_OUTPUTS.adlsGen2Endpoint.value
$SUBNET_ID = $MAIN_OUTPUTS.functionSubnetId.value

if (-not $DATA_LAKE_NAME -or -not $STORAGE_URL -or -not $SUBNET_ID) {
    Write-Host "ERROR: Missing expected outputs from main deployment (dataLakeAccountName, adlsGen2Endpoint, functionSubnetId)." -ForegroundColor Red
    Write-Host "  The main infrastructure may need to be redeployed." -ForegroundColor Yellow
    exit 1
}

$APP_INSIGHTS_CS = az monitor app-insights component show `
    --resource-group $ResourceGroup `
    --query "[0].connectionString" -o tsv
$TENANT_ID = az account show --query tenantId -o tsv

Write-Host "  Data Lake: $DATA_LAKE_NAME"
Write-Host "  Storage URL: $STORAGE_URL"

# Create app registration if not provided
if (-not $DashboardClientId) {
    Write-Host "`n2. Creating Entra ID app registration..." -ForegroundColor Yellow
    $APP_DISPLAY_NAME = "MDOAttackSimulation-Dashboard"
    # Check if app registration already exists
    $existingAppId = az ad app list --display-name $APP_DISPLAY_NAME --query "[0].appId" -o tsv 2>$null
    if ($existingAppId) {
        $DashboardClientId = $existingAppId
        Write-Host "  Found existing app registration: $APP_DISPLAY_NAME ($DashboardClientId)"
    } else {
        $APP_JSON = az ad app create `
            --display-name $APP_DISPLAY_NAME `
            --sign-in-audience AzureADMyOrg `
            --query "{appId:appId, id:id}" -o json | ConvertFrom-Json
        $DashboardClientId = $APP_JSON.appId
        if (-not $DashboardClientId) {
            Write-Host "ERROR: Failed to create app registration. Check your Entra ID permissions." -ForegroundColor Red
            exit 1
        }
        az ad sp create --id $DashboardClientId | Out-Null
        Write-Host "  Created app registration: $APP_DISPLAY_NAME ($DashboardClientId)"
    }
} else {
    Write-Host "`n2. Using existing app registration: $DashboardClientId" -ForegroundColor Yellow
}

# Deploy Bicep
Write-Host "`n3. Deploying dashboard infrastructure..." -ForegroundColor Yellow
$DEPLOY_OUTPUT = az deployment group create `
    --resource-group $ResourceGroup `
    --template-file infra/dashboard.bicep `
    --parameters `
        appServicePlanId=$APP_SERVICE_PLAN_NAME `
        dataLakeAccountName=$DATA_LAKE_NAME `
        storageAccountUrl=$STORAGE_URL `
        tenantId=$TENANT_ID `
        dashboardClientId=$DashboardClientId `
        appInsightsConnectionString=$APP_INSIGHTS_CS `
        subnetId=$SUBNET_ID `
    | ConvertFrom-Json

$DASHBOARD_NAME = $DEPLOY_OUTPUT.properties.outputs.dashboardAppName.value
$DASHBOARD_URL = $DEPLOY_OUTPUT.properties.outputs.dashboardUrl.value

Write-Host "  Dashboard App: $DASHBOARD_NAME"
Write-Host "  Dashboard URL: $DASHBOARD_URL"

# Update app registration redirect URI with the actual URL
Write-Host "`n4. Updating app registration redirect URI..." -ForegroundColor Yellow
$REDIRECT_URI = "$DASHBOARD_URL/.auth/login/aad/callback"
az ad app update --id $DashboardClientId --web-redirect-uris $REDIRECT_URI
Write-Host "  Redirect URI: $REDIRECT_URI"

# Deploy code — source only, startup.sh installs deps on first boot
Write-Host "`n5. Publishing Streamlit app..." -ForegroundColor Yellow
Write-Host "  Packaging source code (dependencies install on first app boot via startup.sh)..." -ForegroundColor Gray

Push-Location src/dashboard
$zipFile = [System.IO.Path]::GetTempFileName() + ".zip"
Compress-Archive -Path * -DestinationPath $zipFile -Force

Write-Host "  Deploying to Azure..." -ForegroundColor Gray
az webapp deploy `
    --resource-group $ResourceGroup `
    --name $DASHBOARD_NAME `
    --src-path $zipFile `
    --type zip 2>&1

$deployExitCode = $LASTEXITCODE

Remove-Item $zipFile
Pop-Location

if ($deployExitCode -ne 0) {
    Write-Host "`n=== Deployment Failed ===" -ForegroundColor Red
    Write-Host "The code deployment failed." -ForegroundColor Red
    Write-Host ""
    Write-Host "To retry just the code deployment, re-run this script." -ForegroundColor Cyan
    Write-Host "The infrastructure and auth configuration are already deployed." -ForegroundColor Yellow
    exit 1
}

Write-Host "`n=== Deployment Complete ===" -ForegroundColor Green
Write-Host "Dashboard URL: $DASHBOARD_URL"
Write-Host "Client ID:     $DashboardClientId"
Write-Host ""
Write-Host "Note: The first load takes 3-5 minutes while dependencies install."
Write-Host "      Subsequent restarts are fast (packages persist in /home storage)."
