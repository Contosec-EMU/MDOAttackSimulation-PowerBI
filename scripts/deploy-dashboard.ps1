<#
.SYNOPSIS
    Deploy the Streamlit Executive Dashboard to Azure.

.DESCRIPTION
    Deploys the dashboard.bicep module and publishes the Streamlit app
    to the Azure Web App on the existing B1 App Service Plan.

.PARAMETER ResourceGroup
    Name of the resource group containing the existing infrastructure.

.PARAMETER DashboardClientId
    Entra ID App Registration Client ID for the dashboard (EasyAuth).

.EXAMPLE
    .\deploy-dashboard.ps1 -ResourceGroup "rg-mdo-attack-simulation" -DashboardClientId "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
#>

param(
    [Parameter(Mandatory=$true)]
    [string]$ResourceGroup,

    [Parameter(Mandatory=$true)]
    [string]$DashboardClientId
)

$ErrorActionPreference = "Stop"

Write-Host "=== MDO Attack Simulation — Dashboard Deployment ===" -ForegroundColor Cyan

# Get existing infrastructure outputs
Write-Host "`n1. Reading existing infrastructure..." -ForegroundColor Yellow
$MAIN_OUTPUTS = az deployment group show `
    --resource-group $ResourceGroup `
    --name main `
    --query "properties.outputs" -o json | ConvertFrom-Json

$APP_SERVICE_PLAN_NAME = az appservice plan list `
    --resource-group $ResourceGroup `
    --query "[0].id" -o tsv

$DATA_LAKE_NAME = $MAIN_OUTPUTS.dataLakeAccountName.value
$STORAGE_URL = $MAIN_OUTPUTS.adlsGen2Endpoint.value
$APP_INSIGHTS_CS = az monitor app-insights component show `
    --resource-group $ResourceGroup `
    --query "[0].connectionString" -o tsv
$TENANT_ID = az account show --query tenantId -o tsv
$SUBNET_ID = $MAIN_OUTPUTS.functionSubnetId.value

Write-Host "  Data Lake: $DATA_LAKE_NAME"
Write-Host "  Storage URL: $STORAGE_URL"

# Deploy Bicep
Write-Host "`n2. Deploying dashboard infrastructure..." -ForegroundColor Yellow
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

# Deploy code
Write-Host "`n3. Publishing Streamlit app..." -ForegroundColor Yellow
Push-Location src/dashboard
$zipFile = [System.IO.Path]::GetTempFileName() + ".zip"
Compress-Archive -Path * -DestinationPath $zipFile -Force
az webapp deployment source config-zip `
    --resource-group $ResourceGroup `
    --name $DASHBOARD_NAME `
    --src $zipFile
Remove-Item $zipFile
Pop-Location

Write-Host "`n=== Deployment Complete ===" -ForegroundColor Green
Write-Host "Dashboard URL: $DASHBOARD_URL"
Write-Host "`nNote: It may take 1-2 minutes for the app to start after deployment."
