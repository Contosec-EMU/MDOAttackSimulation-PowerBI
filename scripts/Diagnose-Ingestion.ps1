<#
.SYNOPSIS
    Diagnoses data ingestion issues for the MDO Attack Simulation pipeline.

.DESCRIPTION
    Checks Function App health, storage access, Key Vault access, recent
    invocations, and latest data files in ADLS Gen2. Requires Azure CLI
    and appropriate permissions.

.PARAMETER ResourceGroupName
    Resource group name (auto-detected from main.bicepparam if omitted)

.PARAMETER SubscriptionId
    Azure subscription ID (auto-detected from main.bicepparam or current context)

.EXAMPLE
    .\Diagnose-Ingestion.ps1
    .\Diagnose-Ingestion.ps1 -ResourceGroupName "rg-mdo-attack-simulation"
#>

param(
    [Parameter(Mandatory=$false)]
    [string]$ResourceGroupName,

    [Parameter(Mandatory=$false)]
    [string]$SubscriptionId
)

$ErrorActionPreference = "Continue"

function Write-Check {
    param([string]$Label, [string]$Status, [string]$Detail = "")
    $color = switch ($Status) {
        "OK"      { "Green" }
        "WARN"    { "Yellow" }
        "FAIL"    { "Red" }
        "INFO"    { "Cyan" }
        default   { "White" }
    }
    Write-Host "  [$Status] " -ForegroundColor $color -NoNewline
    Write-Host "$Label" -NoNewline
    if ($Detail) { Write-Host " - $Detail" -ForegroundColor DarkGray } else { Write-Host "" }
}

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  MDO Ingestion Diagnostics" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""

# --- Auto-detect parameters from bicepparam file ---
$paramsFile = "$PSScriptRoot\..\infra\main.bicepparam"
if (Test-Path $paramsFile) {
    $paramsContent = Get-Content $paramsFile -Raw
    if (-not $SubscriptionId) {
        if ($paramsContent -match "// subscriptionId = '([^']+)'") {
            $candidate = $Matches[1]
            if ($candidate -ne '<YOUR_SUBSCRIPTION_ID>') {
                $SubscriptionId = $candidate
            }
        }
    }
    if (-not $ResourceGroupName) {
        if ($paramsContent -match "// resourceGroupName = '([^']+)'") {
            $candidate = $Matches[1]
            if ($candidate -ne '<YOUR_RG_NAME>') {
                $ResourceGroupName = $candidate
            }
        }
    }
}

# Fall back to defaults
if (-not $SubscriptionId) {
    $SubscriptionId = (az account show --query id -o tsv 2>$null)
}
if (-not $ResourceGroupName) {
    $ResourceGroupName = "rg-mdo-attack-simulation"
}

Write-Host "Subscription: $SubscriptionId"
Write-Host "Resource Group: $ResourceGroupName"
Write-Host ""

# Set subscription
az account set --subscription $SubscriptionId 2>$null

# --- Discover resource names ---
Write-Host "[1/7] Discovering resources..." -ForegroundColor Cyan

$funcApp = az functionapp list -g $ResourceGroupName --query "[0].name" -o tsv 2>$null
$funcStorageName = az storage account list -g $ResourceGroupName --query "[?contains(name,'fn')].name | [0]" -o tsv 2>$null
$adlsStorageName = az storage account list -g $ResourceGroupName --query "[?contains(name,'dl')].name | [0]" -o tsv 2>$null
$kvName = az keyvault list -g $ResourceGroupName --query "[0].name" -o tsv 2>$null
$appInsightsName = az monitor app-insights component show -g $ResourceGroupName --query "[0].name" -o tsv 2>$null

if (-not $funcApp) {
    Write-Check "Function App" "FAIL" "Not found in resource group $ResourceGroupName"
    Write-Host "`nCannot continue without Function App. Check resource group name." -ForegroundColor Red
    exit 1
}

Write-Check "Function App" "OK" $funcApp
Write-Check "Function Storage" $(if ($funcStorageName) { "OK" } else { "FAIL" }) $funcStorageName
Write-Check "ADLS Storage" $(if ($adlsStorageName) { "OK" } else { "FAIL" }) $adlsStorageName
Write-Check "Key Vault" $(if ($kvName) { "OK" } else { "FAIL" }) $kvName
Write-Check "App Insights" $(if ($appInsightsName) { "OK" } else { "WARN" }) $(if ($appInsightsName) { $appInsightsName } else { "Not found (optional)" })
Write-Host ""

# --- Check Function App state ---
Write-Host "[2/7] Checking Function App state..." -ForegroundColor Cyan

$funcState = az functionapp show -n $funcApp -g $ResourceGroupName --query "state" -o tsv 2>$null
$funcAvailability = az functionapp show -n $funcApp -g $ResourceGroupName --query "availabilityState" -o tsv 2>$null

if ($funcState -eq "Running") {
    Write-Check "Function App state" "OK" "Running"
} else {
    Write-Check "Function App state" "FAIL" "$funcState (expected: Running)"
}

if ($funcAvailability -eq "Normal") {
    Write-Check "Availability" "OK" "Normal"
} else {
    Write-Check "Availability" "WARN" "$funcAvailability"
}

# Check timer schedule
$timerSchedule = az functionapp config appsettings list -n $funcApp -g $ResourceGroupName --query "[?name=='TIMER_SCHEDULE'].value | [0]" -o tsv 2>$null
Write-Check "Timer schedule" "INFO" $(if ($timerSchedule) { $timerSchedule } else { "Not set (using code default)" })

# Check sync config
$syncMode = az functionapp config appsettings list -n $funcApp -g $ResourceGroupName --query "[?name=='SYNC_MODE'].value | [0]" -o tsv 2>$null
$syncSims = az functionapp config appsettings list -n $funcApp -g $ResourceGroupName --query "[?name=='SYNC_SIMULATIONS'].value | [0]" -o tsv 2>$null
Write-Check "Sync mode" "INFO" $(if ($syncMode) { $syncMode } else { "full (default)" })
Write-Check "Sync simulations" "INFO" $(if ($syncSims) { $syncSims } else { "true (default)" })
Write-Host ""

# --- Check network access ---
Write-Host "[3/7] Checking network access..." -ForegroundColor Cyan

if ($funcStorageName) {
    $funcStoragePublic = az storage account show -n $funcStorageName --query "publicNetworkAccess" -o tsv 2>$null
    if ($funcStoragePublic -eq "Enabled") {
        Write-Check "Function storage public access" "OK" "Enabled"
    } else {
        Write-Check "Function storage public access" "FAIL" "$funcStoragePublic - Timer trigger will NOT fire!"
    }
}

if ($adlsStorageName) {
    $adlsPublic = az storage account show -n $adlsStorageName --query "publicNetworkAccess" -o tsv 2>$null
    $adlsDefault = az storage account show -n $adlsStorageName --query "networkRuleSet.defaultAction" -o tsv 2>$null
    $adlsVnetRules = az storage account show -n $adlsStorageName --query "networkRuleSet.virtualNetworkRules | length(@)" -o tsv 2>$null
    if ($adlsPublic -eq "Enabled") {
        Write-Check "ADLS public access" "OK" "Enabled (defaultAction: $adlsDefault, VNet rules: $adlsVnetRules)"
    } elseif ($adlsPublic -eq "Disabled") {
        Write-Check "ADLS public access" "FAIL" "Disabled - Function cannot write data even with VNet integration!"
    } else {
        Write-Check "ADLS public access" "WARN" "$adlsPublic (defaultAction: $adlsDefault)"
    }
}

if ($kvName) {
    $kvPublic = az keyvault show -n $kvName --query "properties.publicNetworkAccess" -o tsv 2>$null
    if ($kvPublic -eq "Enabled") {
        Write-Check "Key Vault public access" "OK" "Enabled"
    } else {
        Write-Check "Key Vault public access" "FAIL" "$kvPublic - Function cannot get Graph API client secret!"
    }
}
Write-Host ""

# --- Check VNet integration ---
Write-Host "[4/7] Checking VNet integration..." -ForegroundColor Cyan

$vnetSubnetId = az functionapp show -n $funcApp -g $ResourceGroupName --query "virtualNetworkSubnetId" -o tsv 2>$null
if ($vnetSubnetId) {
    Write-Check "VNet integration" "OK" "Connected to subnet"
} else {
    Write-Check "VNet integration" "WARN" "Not configured - storage firewall rules may block access"
}

$vnetRouteAll = az functionapp show -n $funcApp -g $ResourceGroupName --query "siteConfig.vnetRouteAllEnabled" -o tsv 2>$null
if ($vnetRouteAll -eq "True") {
    Write-Check "VNet route all" "OK" "Enabled (all outbound via VNet)"
} else {
    Write-Check "VNet route all" "WARN" "Disabled - storage service endpoints may not be used"
}
Write-Host ""

# --- Check recent invocations via App Insights ---
Write-Host "[5/7] Checking recent function invocations..." -ForegroundColor Cyan

if ($appInsightsName) {
    # Recent invocations by day
    $invocations = az monitor app-insights query -a $appInsightsName -g $ResourceGroupName `
        --analytics-query "requests | where timestamp > ago(14d) | where name contains 'mdo_attack_simulation_ingest' or name contains 'test_run' | summarize count() by bin(timestamp, 1d) | order by timestamp desc" `
        -o json 2>$null

    if ($invocations) {
        $parsed = $invocations | ConvertFrom-Json
        $tables = $parsed.tables
        if ($tables -and $tables[0].rows -and $tables[0].rows.Count -gt 0) {
            Write-Check "Invocations (last 14d)" "INFO" "$($tables[0].rows.Count) days with activity:"
            foreach ($row in $tables[0].rows | Select-Object -First 7) {
                $date = ([datetime]$row[0]).ToString("yyyy-MM-dd")
                $count = $row[1]
                Write-Host "    $date : $count invocations" -ForegroundColor DarkGray
            }
        } else {
            Write-Check "Invocations (last 14d)" "FAIL" "No invocations found! Timer trigger is not firing."
        }
    } else {
        Write-Check "Invocations" "WARN" "Could not query App Insights"
    }

    # Recent errors
    Write-Host ""
    Write-Host "[6/7] Checking recent errors..." -ForegroundColor Cyan

    $errors = az monitor app-insights query -a $appInsightsName -g $ResourceGroupName `
        --analytics-query "exceptions | where timestamp > ago(14d) | project timestamp, outerMessage, problemId | order by timestamp desc | take 10" `
        -o json 2>$null

    if ($errors) {
        $parsed = $errors | ConvertFrom-Json
        $tables = $parsed.tables
        if ($tables -and $tables[0].rows -and $tables[0].rows.Count -gt 0) {
            Write-Check "Recent errors" "WARN" "$($tables[0].rows.Count) errors found:"
            foreach ($row in $tables[0].rows | Select-Object -First 5) {
                $ts = ([datetime]$row[0]).ToString("yyyy-MM-dd HH:mm")
                $msg = if ($row[1].Length -gt 100) { $row[1].Substring(0, 100) + "..." } else { $row[1] }
                Write-Host "    $ts : $msg" -ForegroundColor DarkGray
            }
        } else {
            Write-Check "Recent errors" "OK" "No exceptions in last 14 days"
        }
    } else {
        Write-Check "Errors" "WARN" "Could not query App Insights"
    }
} else {
    Write-Check "App Insights" "WARN" "Not found - cannot check invocation history"
    Write-Host ""
    Write-Host "[6/7] Skipping error check (no App Insights)..." -ForegroundColor Yellow
}
Write-Host ""

# --- Check latest files in ADLS ---
Write-Host "[7/7] Checking latest data files in ADLS..." -ForegroundColor Cyan

if ($adlsStorageName) {
    $tables = @("repeatOffenders", "simulationUserCoverage", "trainingUserCoverage", "simulations", "trainings", "payloads", "simulationUsers", "simulationUserEvents", "users")

    foreach ($table in $tables) {
        $latestFolder = az storage fs directory list `
            -f "curated" `
            --path $table `
            --account-name $adlsStorageName `
            --auth-mode login `
            --query "[-1].name" -o tsv 2>$null

        if ($latestFolder) {
            $datePart = $latestFolder -replace "^$table/", ""
            Write-Check $table "INFO" "Latest: $datePart"
        } else {
            Write-Check $table "WARN" "No data found"
        }
    }
} else {
    Write-Check "ADLS files" "FAIL" "Storage account not found"
}

Write-Host ""
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host "  Diagnostics Complete" -ForegroundColor Cyan
Write-Host "=========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Common fixes:" -ForegroundColor Yellow
Write-Host "  1. If public access is Disabled on any resource:" -ForegroundColor DarkGray
Write-Host "     az storage account update -n <name> --public-network-access Enabled" -ForegroundColor DarkGray
Write-Host "     az keyvault update -n <name> --public-network-access Enabled" -ForegroundColor DarkGray
Write-Host "  2. If Function App is not running:" -ForegroundColor DarkGray
Write-Host "     az functionapp start -n <name> -g $ResourceGroupName" -ForegroundColor DarkGray
Write-Host "  3. To manually trigger a test run:" -ForegroundColor DarkGray
Write-Host "     az functionapp function invoke -n <funcapp> -g $ResourceGroupName --name test_run --method POST" -ForegroundColor DarkGray
Write-Host "  4. To redeploy the latest code:" -ForegroundColor DarkGray
Write-Host "     cd scripts && .\deploy.ps1" -ForegroundColor DarkGray
Write-Host ""
