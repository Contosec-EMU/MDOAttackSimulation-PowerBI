<#
.SYNOPSIS
    Creates the Entra ID App Registration for Graph API access.

.DESCRIPTION
    Creates an app registration with AttackSimulation.Read.All and User.Read.All permissions
    and grants admin consent.

.PARAMETER AppName
    Display name for the app registration

.EXAMPLE
    .\create-app-registration.ps1 -AppName "MDOAttackSimulation-GraphAPI"
#>

param(
    [Parameter(Mandatory=$false)]
    [string]$AppName = "MDOAttackSimulation-GraphAPI"
)

$ErrorActionPreference = "Stop"

Write-Host "=== Creating Entra ID App Registration ===" -ForegroundColor Cyan

# Check if logged in
$account = az account show 2>$null | ConvertFrom-Json
if (-not $account) {
    Write-Host "Not logged in. Running 'az login'..." -ForegroundColor Yellow
    az login
}

$tenantId = $account.tenantId
Write-Host "Tenant ID: $tenantId" -ForegroundColor Green

# Create app registration
Write-Host "`nCreating app registration: $AppName..." -ForegroundColor Yellow
$app = az ad app create --display-name $AppName --query "{appId:appId, id:id}" -o json | ConvertFrom-Json

if (-not $app) {
    throw "Failed to create app registration"
}

Write-Host "App (Client) ID: $($app.appId)" -ForegroundColor Green

# Create service principal
Write-Host "`nCreating service principal..." -ForegroundColor Yellow
az ad sp create --id $app.appId --output none 2>$null
# Ignore error if SP already exists

# Add API permission: AttackSimulation.Read.All (Application)
# Microsoft Graph App ID: 00000003-0000-0000-c000-000000000000
# AttackSimulation.Read.All permission ID: 93283d0a-6322-4fa8-966b-8c121624760d
Write-Host "`nAdding AttackSimulation.Read.All permission..." -ForegroundColor Yellow
az ad app permission add `
    --id $app.appId `
    --api "00000003-0000-0000-c000-000000000000" `
    --api-permissions "93283d0a-6322-4fa8-966b-8c121624760d=Role"

# Add API permission: User.Read.All (Application)
# User.Read.All permission ID: df021288-bdef-4463-88db-98f22de89214
Write-Host "`nAdding User.Read.All permission..." -ForegroundColor Yellow
az ad app permission add `
    --id $app.appId `
    --api "00000003-0000-0000-c000-000000000000" `
    --api-permissions "df021288-bdef-4463-88db-98f22de89214=Role"

# Grant admin consent
Write-Host "`nGranting admin consent (requires Global Admin or Privileged Role Admin)..." -ForegroundColor Yellow
try {
    az ad app permission admin-consent --id $app.appId
    Write-Host "Admin consent granted successfully" -ForegroundColor Green
} catch {
    Write-Host "Warning: Could not grant admin consent automatically." -ForegroundColor Yellow
    Write-Host "Please grant consent manually in Azure Portal:" -ForegroundColor Yellow
    Write-Host "  1. Go to Entra ID > App registrations > $AppName" -ForegroundColor Yellow
    Write-Host "  2. API permissions > Grant admin consent" -ForegroundColor Yellow
}

# Create client secret
Write-Host "`nCreating client secret..." -ForegroundColor Yellow
$secretResult = az ad app credential reset --id $app.appId --append --query "{password:password, endDate:endDateTime}" -o json | ConvertFrom-Json

# Save secret to file
$secretFile = "app-registration-secret.txt"
@"
=== MDO Attack Simulation - App Registration Credentials ===
Created: $(Get-Date -Format "yyyy-MM-dd HH:mm:ss")

Tenant ID:        $tenantId
App (Client) ID:  $($app.appId)
Client Secret:    $($secretResult.password)
Secret Expires:   $($secretResult.endDate)

IMPORTANT: Delete this file after securely storing the credentials!
"@ | Out-File -FilePath $secretFile -Encoding UTF8

# Output summary
Write-Host "`n=== App Registration Created ===" -ForegroundColor Green
Write-Host @"

Save these values securely:

  Tenant ID:        $tenantId
  App (Client) ID:  $($app.appId)
  Client Secret:    [SAVED TO FILE: $secretFile]
  Secret Expires:   $($secretResult.endDate)

Required Permissions:
  AttackSimulation.Read.All (Application) - Admin consent required
  User.Read.All (Application) - Admin consent required

Next Steps:
  1. Verify admin consent is granted in Azure Portal
  2. Retrieve the client secret from: $secretFile
  3. Use these values in the deployment:
     - TENANT_ID = $tenantId
     - GRAPH_CLIENT_ID = $($app.appId)
     - GRAPH_CLIENT_SECRET = (from the file above)
  4. Delete $secretFile after storing the secret securely (e.g., in Key Vault)

"@ -ForegroundColor Cyan

Write-Host "⚠️  IMPORTANT: Client secret saved to $secretFile - store it securely and delete the file!" -ForegroundColor Red
