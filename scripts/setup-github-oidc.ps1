#Requires -Version 7.0
<#
.SYNOPSIS
    Setup Azure OIDC Federation with GitHub Actions

.DESCRIPTION
    This script configures Azure Entra ID to trust GitHub's OIDC provider,
    eliminating the need for long-lived secrets in GitHub Actions.

.PARAMETER GitHubOrg
    GitHub organization name

.PARAMETER GitHubRepo
    GitHub repository name

.PARAMETER ResourceGroup
    Azure resource group name (default: rg-mdo-attack-simulation)

.PARAMETER Location
    Azure region (default: westus2)

.EXAMPLE
    .\scripts\setup-github-oidc.ps1 -GitHubOrg "myorg" -GitHubRepo "MDOAttackSimulation_PowerBI"

.NOTES
    Prerequisites:
    - Azure CLI installed and authenticated (az login)
    - GitHub repository created (can be empty)
    - Permissions: Entra ID Application Administrator + Subscription Owner/User Access Administrator
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$GitHubOrg,

    [Parameter(Mandatory = $true)]
    [string]$GitHubRepo,

    [Parameter(Mandatory = $false)]
    [string]$ResourceGroup = "rg-mdo-attack-simulation",

    [Parameter(Mandatory = $false)]
    [string]$Location = "westus2"
)

$ErrorActionPreference = "Stop"

# ============================================================================
# Helper Functions
# ============================================================================

function Write-Info { Write-Host "ℹ $args" -ForegroundColor Blue }
function Write-Success { Write-Host "✅ $args" -ForegroundColor Green }
function Write-Warning { Write-Host "⚠️ $args" -ForegroundColor Yellow }
function Write-ErrorMsg { Write-Host "❌ $args" -ForegroundColor Red; exit 1 }

# ============================================================================
# Validate Environment
# ============================================================================

Write-Info "GitHub Repository: $GitHubOrg/$GitHubRepo"
Write-Info "Azure Resource Group: $ResourceGroup"
Write-Info "Azure Region: $Location"

# Check Azure CLI
Write-Info "Checking Azure CLI authentication..."
try {
    $account = az account show --output json 2>&1 | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) {
        throw "Not authenticated"
    }
}
catch {
    Write-ErrorMsg "Not logged into Azure CLI. Run: az login"
}

$subscriptionId = $account.id
$tenantId = $account.tenantId
$subscriptionName = $account.name

Write-Success "Authenticated to Azure"
Write-Info "  Subscription: $subscriptionName"
Write-Info "  Subscription ID: $subscriptionId"
Write-Info "  Tenant ID: $tenantId"

# ============================================================================
# Create or Update App Registration
# ============================================================================

$appName = "gh-oidc-$GitHubRepo"

Write-Info "Creating/updating Entra ID App Registration: $appName"

# Check if app exists
$existingApp = az ad app list --display-name $appName --output json 2>&1 | ConvertFrom-Json

if ($existingApp -and $existingApp.Count -gt 0) {
    $appId = $existingApp[0].appId
    Write-Warning "App registration already exists: $appId"
}
else {
    Write-Info "Creating new app registration: $appName"
    $appId = az ad app create --display-name $appName --query appId --output tsv
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "Failed to create app registration"
    }
    Write-Success "App registration created: $appId"
}

# Get app object ID
$appObjectId = az ad app show --id $appId --query id --output tsv

# ============================================================================
# Configure OIDC Federated Credentials
# ============================================================================

Write-Info "Configuring federated credentials for GitHub OIDC..."

$credNameMain = "github-$GitHubOrg-$GitHubRepo-main"
$subjectMain = "repo:$GitHubOrg/$($GitHubRepo):ref:refs/heads/main"

# Check if credential exists
$existingCred = az ad app federated-credential show `
    --id $appId `
    --federated-credential-id $credNameMain `
    --output json 2>&1

if ($LASTEXITCODE -eq 0) {
    Write-Warning "Federated credential already exists: $credNameMain"
}
else {
    # Create federated credential
    $credParams = @{
        name        = $credNameMain
        issuer      = "https://token.actions.githubusercontent.com"
        subject     = $subjectMain
        audiences   = @("api://AzureADTokenExchange")
        description = "GitHub Actions OIDC for $GitHubOrg/$GitHubRepo main branch"
    } | ConvertTo-Json -Compress

    az ad app federated-credential create `
        --id $appId `
        --parameters $credParams `
        --output none

    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "Failed to create federated credential"
    }

    Write-Success "Federated credential created: $credNameMain"
}

# ============================================================================
# Create Service Principal
# ============================================================================

Write-Info "Creating/updating Service Principal..."

$existingSp = az ad sp list --filter "appId eq '$appId'" --output json 2>&1 | ConvertFrom-Json

if ($existingSp -and $existingSp.Count -gt 0) {
    $spId = $existingSp[0].id
    Write-Warning "Service principal already exists: $spId"
}
else {
    Write-Info "Creating service principal..."
    $spId = az ad sp create --id $appId --query id --output tsv
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "Failed to create service principal"
    }
    Write-Success "Service principal created: $spId"
}

# ============================================================================
# Create Resource Group
# ============================================================================

Write-Info "Ensuring resource group exists: $ResourceGroup"

$existingRg = az group exists --name $ResourceGroup
if ($existingRg -eq "true") {
    Write-Warning "Resource group already exists: $ResourceGroup"
}
else {
    az group create `
        --name $ResourceGroup `
        --location $Location `
        --tags project=MDOAttackSimulation environment=production deployment=github-actions `
        --output none

    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "Failed to create resource group"
    }
    Write-Success "Resource group created: $ResourceGroup"
}

# ============================================================================
# Assign RBAC Roles
# ============================================================================

Write-Info "Assigning RBAC roles to service principal..."

$rgScope = "/subscriptions/$subscriptionId/resourceGroups/$ResourceGroup"

# Contributor role
$contributorAssignment = az role assignment list `
    --assignee $appId `
    --role "Contributor" `
    --scope $rgScope `
    --output json 2>&1 | ConvertFrom-Json

if ($contributorAssignment -and $contributorAssignment.Count -gt 0) {
    Write-Warning "Contributor role already assigned"
}
else {
    az role assignment create `
        --assignee $appId `
        --role "Contributor" `
        --scope $rgScope `
        --output none

    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "Failed to assign Contributor role"
    }
    Write-Success "Assigned 'Contributor' role on resource group"
}

# User Access Administrator role
$uaaAssignment = az role assignment list `
    --assignee $appId `
    --role "User Access Administrator" `
    --scope $rgScope `
    --output json 2>&1 | ConvertFrom-Json

if ($uaaAssignment -and $uaaAssignment.Count -gt 0) {
    Write-Warning "User Access Administrator role already assigned"
}
else {
    az role assignment create `
        --assignee $appId `
        --role "User Access Administrator" `
        --scope $rgScope `
        --output none

    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "Failed to assign User Access Administrator role"
    }
    Write-Success "Assigned 'User Access Administrator' role on resource group"
}

# ============================================================================
# Summary
# ============================================================================

Write-Host ""
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Success "Azure OIDC setup complete!"
Write-Host "========================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Info "Next steps:"
Write-Host ""
Write-Host "1. Add these secrets to your GitHub repository:" -ForegroundColor White
Write-Host "   Repository Settings > Secrets and variables > Actions > New repository secret" -ForegroundColor Gray
Write-Host ""
Write-Host "   AZURE_CLIENT_ID:       $appId" -ForegroundColor Yellow
Write-Host "   AZURE_TENANT_ID:       $tenantId" -ForegroundColor Yellow
Write-Host "   AZURE_SUBSCRIPTION_ID: $subscriptionId" -ForegroundColor Yellow
Write-Host ""
Write-Host "2. Store your Graph API client secret in Azure Key Vault:" -ForegroundColor White
Write-Host "   (After infrastructure is deployed)" -ForegroundColor Gray
Write-Host ""
Write-Host "   az keyvault secret set \\" -ForegroundColor Gray
Write-Host "     --vault-name <keyvault-name> \\" -ForegroundColor Gray
Write-Host "     --name `"graph-client-secret`" \\" -ForegroundColor Gray
Write-Host "     --value `"<your-graph-api-secret>`"" -ForegroundColor Gray
Write-Host ""
Write-Host "3. Push code to main branch to trigger deployment:" -ForegroundColor White
Write-Host ""
Write-Host "   git add ." -ForegroundColor Gray
Write-Host "   git commit -m `"Initial commit with GitHub Actions`"" -ForegroundColor Gray
Write-Host "   git push origin main" -ForegroundColor Gray
Write-Host ""
Write-Info "GitHub Actions workflow will automatically deploy on push to main"
Write-Host ""
