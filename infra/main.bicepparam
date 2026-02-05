using 'main.bicep'

// ============================================================================
// MDO Attack Simulation - Deployment Parameters
// ============================================================================
// Update these values before deployment

// Azure Subscription (REQUIRED - used by deploy script, not Bicep)
// Run: az account list --query "[].{Name:name, Id:id}" -o table
// subscriptionId = 'ea321fd5-c995-4231-bebd-5d3fa7fff0fd'

param prefix = 'mdoast'
param location = 'westus2'

// Entra ID Configuration (REQUIRED - update these)
param tenantId = 'cfb30b1b-1cbf-41ea-9453-7546e858dddd'
param graphClientId = 'd46d827f-8a75-4274-ae77-5c9c06b97be4'

// Timer schedule: CRON expression (default: daily at 2:00 AM UTC)
// Format: {second} {minute} {hour} {day} {month} {day-of-week}
param timerSchedule = '0 0 2 * * *'

// Power BI Access: Enable resource instance rules to allow Power BI Service
// to access ADLS Gen2 even with public access denied
param enablePowerBiAccess = true

param tags = {
  project: 'MDOAttackSimulation'
  environment: 'production'
  costCenter: 'security'
}
