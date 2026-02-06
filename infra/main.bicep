// main.bicep - MDO Attack Simulation Training Data Ingestion Infrastructure
// Deploys: Storage (ADLS Gen2), Function App, Key Vault, App Insights

targetScope = 'resourceGroup'

@description('Naming prefix for all resources')
param prefix string = 'mdoast'

@description('Azure region for deployment')
param location string = resourceGroup().location

@description('Entra ID Tenant ID for Graph API authentication')
param tenantId string

@description('Entra ID App Registration Client ID')
param graphClientId string

@description('Timer schedule (CRON) - default daily at 2:00 AM UTC')
param timerSchedule string = '0 0 2 * * *'

@description('Sync mode: full (default) or incremental (7-day lookback)')
@allowed([
  'full'
  'incremental'
])
param syncMode string = 'full'

@description('Whether to sync simulation details (extended endpoint)')
param syncSimulations bool = true

@description('Allow all Power BI workspaces in the tenant to access ADLS Gen2')
param enablePowerBiAccess bool = true

@description('Tags for all resources')
param tags object = {
  project: 'MDOAttackSimulation'
  environment: 'production'
}

// Generate unique suffix for globally unique names
var uniqueSuffix = uniqueString(resourceGroup().id)
var funcStorageAccountName = '${prefix}fn${uniqueSuffix}'
var dataLakeAccountName = '${prefix}dl${uniqueSuffix}'
var functionAppName = '${prefix}-func-${uniqueSuffix}'
var appServicePlanName = '${prefix}-asp-${uniqueSuffix}'
var keyVaultName = '${prefix}-kv2-${uniqueSuffix}'
var appInsightsName = '${prefix}-appi-${uniqueSuffix}'
var logAnalyticsName = '${prefix}-law-${uniqueSuffix}'
var vnetName = '${prefix}-vnet-${uniqueSuffix}'
var functionSubnetName = 'snet-functions'

// ============================================================================
// Log Analytics Workspace (for App Insights)
// ============================================================================
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2022-10-01' = {
  name: logAnalyticsName
  location: location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 90
  }
}

// ============================================================================
// Virtual Network (for Function App to access firewall-protected storage)
// ============================================================================
resource vnet 'Microsoft.Network/virtualNetworks@2023-05-01' = {
  name: vnetName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.0.0.0/16'
      ]
    }
    subnets: [
      {
        name: functionSubnetName
        properties: {
          addressPrefix: '10.0.1.0/24'
          // Delegate subnet to Azure Functions
          delegations: [
            {
              name: 'delegation'
              properties: {
                serviceName: 'Microsoft.Web/serverFarms'
              }
            }
          ]
          // Service endpoint allows subnet to access storage directly
          serviceEndpoints: [
            {
              service: 'Microsoft.Storage'
            }
            {
              service: 'Microsoft.KeyVault'
            }
          ]
        }
      }
    ]
  }
}

// Reference to the function subnet
resource functionSubnet 'Microsoft.Network/virtualNetworks/subnets@2023-05-01' existing = {
  parent: vnet
  name: functionSubnetName
}

// ============================================================================
// Application Insights
// ============================================================================
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// ============================================================================
// Storage Account for Function App (standard, no HNS)
// ============================================================================
resource funcStorageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: funcStorageAccountName
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false  // Use identity-based auth instead of account keys
    accessTier: 'Hot'
  }
}

// ============================================================================
// Storage Account for Data Lake (ADLS Gen2 with HNS)
// ============================================================================
resource dataLakeAccount 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: dataLakeAccountName
  location: location
  tags: tags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    isHnsEnabled: true // Enable hierarchical namespace for ADLS Gen2
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    accessTier: 'Hot'
    networkAcls: {
      defaultAction: 'Deny'
      bypass: 'AzureServices,Logging,Metrics'
      // Allow Function App subnet to access storage via service endpoint
      virtualNetworkRules: [
        {
          id: functionSubnet.id
          action: 'Allow'
        }
      ]
      // Resource instance rules allow Power BI Service to access storage
      // even with defaultAction: Deny. Power BI connects as a trusted resource.
      resourceAccessRules: enablePowerBiAccess ? [
        {
          // Allow Power BI workspaces in this tenant to access storage
          tenantId: tenantId
          resourceId: '/subscriptions/${subscription().subscriptionId}/providers/Microsoft.PowerBI/workspaces'
        }
      ] : []
    }
  }
}

// Blob service for Data Lake
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-01-01' = {
  parent: dataLakeAccount
  name: 'default'
}

// Container: raw (optional JSON storage)
resource rawContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: 'raw'
  properties: {
    publicAccess: 'None'
  }
}

// Container: curated (Parquet for Power BI)
resource curatedContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-01-01' = {
  parent: blobService
  name: 'curated'
  properties: {
    publicAccess: 'None'
  }
}

// ============================================================================
// Key Vault
// ============================================================================
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: tags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
      // Allow Function App subnet to access Key Vault via service endpoint
      virtualNetworkRules: [
        {
          id: functionSubnet.id
        }
      ]
    }
  }
}

// ============================================================================
// App Service Plan (Basic B1 - more reliable than Consumption for this region)
// ============================================================================
resource appServicePlan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: appServicePlanName
  location: location
  tags: tags
  sku: {
    name: 'B1'
    tier: 'Basic'
  }
  properties: {
    reserved: true // Required for Linux
  }
}

// ============================================================================
// Function App
// ============================================================================
resource functionApp 'Microsoft.Web/sites@2023-01-01' = {
  name: functionAppName
  location: location
  tags: tags
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    publicNetworkAccess: 'Enabled'
    // VNet integration allows Function to access firewall-protected resources
    virtualNetworkSubnetId: functionSubnet.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      pythonVersion: '3.11'
      appSettings: [
        // Identity-based connection for AzureWebJobsStorage (no account keys)
        {
          name: 'AzureWebJobsStorage__accountName'
          value: funcStorageAccount.name
        }
        {
          name: 'AzureWebJobsStorage__blobServiceUri'
          value: 'https://${funcStorageAccount.name}.blob.${environment().suffixes.storage}'
        }
        {
          name: 'AzureWebJobsStorage__queueServiceUri'
          value: 'https://${funcStorageAccount.name}.queue.${environment().suffixes.storage}'
        }
        {
          name: 'AzureWebJobsStorage__tableServiceUri'
          value: 'https://${funcStorageAccount.name}.table.${environment().suffixes.storage}'
        }
        {
          name: 'FUNCTIONS_EXTENSION_VERSION'
          value: '~4'
        }
        {
          name: 'FUNCTIONS_WORKER_RUNTIME'
          value: 'python'
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsights.properties.ConnectionString
        }
        {
          name: 'APPINSIGHTS_INSTRUMENTATIONKEY'
          value: appInsights.properties.InstrumentationKey
        }
        // Custom app settings for Graph ingestion
        {
          name: 'TENANT_ID'
          value: tenantId
        }
        {
          name: 'GRAPH_CLIENT_ID'
          value: graphClientId
        }
        {
          name: 'KEY_VAULT_URL'
          value: keyVault.properties.vaultUri
        }
        {
          name: 'STORAGE_ACCOUNT_URL'
          value: 'https://${dataLakeAccount.name}.dfs.${environment().suffixes.storage}'
        }
        {
          name: 'TIMER_SCHEDULE'
          value: timerSchedule
        }
        // Sync mode configuration (ASTSync-inspired improvements)
        {
          name: 'SYNC_MODE'
          value: syncMode
        }
        {
          name: 'SYNC_SIMULATIONS'
          value: syncSimulations ? 'true' : 'false'
        }
      ]
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      // Route all outbound traffic through VNet for firewall-protected resources
      vnetRouteAllEnabled: true
    }
  }
}

// ============================================================================
// RBAC Assignments
// ============================================================================

// RBAC roles for Function App on Function Storage Account (for AzureWebJobsStorage)
// These roles are required for identity-based connections to work

// Storage Blob Data Contributor - allows Function to read/write blobs in function storage
resource funcStorageBlobDataContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(funcStorageAccount.id, functionApp.id, 'Storage Blob Data Contributor')
  scope: funcStorageAccount
  properties: {
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  }
}

// Storage Queue Data Contributor - allows Function to manage queue messages
resource funcStorageQueueDataContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(funcStorageAccount.id, functionApp.id, 'Storage Queue Data Contributor')
  scope: funcStorageAccount
  properties: {
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '974c5e8b-45b9-4653-ba55-5f855dd0fb88')
  }
}

// Storage Table Data Contributor - allows Function to read/write table data
resource funcStorageTableDataContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(funcStorageAccount.id, functionApp.id, 'Storage Table Data Contributor')
  scope: funcStorageAccount
  properties: {
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3')
  }
}

// Storage Blob Data Contributor for Function App on Data Lake
resource storageBlobContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(dataLakeAccount.id, functionApp.id, 'Storage Blob Data Contributor')
  scope: dataLakeAccount
  properties: {
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  }
}

// Key Vault Secrets User for Function App
resource keyVaultSecretsUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, functionApp.id, 'Key Vault Secrets User')
  scope: keyVault
  properties: {
    principalId: functionApp.identity.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}

// ============================================================================
// Outputs
// ============================================================================
output funcStorageAccountName string = funcStorageAccount.name
output dataLakeAccountName string = dataLakeAccount.name
output dataLakeAccountId string = dataLakeAccount.id
output functionAppName string = functionApp.name
output functionAppPrincipalId string = functionApp.identity.principalId
output keyVaultName string = keyVault.name
output keyVaultUri string = keyVault.properties.vaultUri
output appInsightsName string = appInsights.name
output resourceGroupName string = resourceGroup().name

// Connection info for Power BI
output adlsGen2Endpoint string = 'https://${dataLakeAccount.name}.dfs.${environment().suffixes.storage}'
output curatedContainerPath string = 'https://${dataLakeAccount.name}.dfs.${environment().suffixes.storage}/curated'
output powerBiAccessEnabled bool = enablePowerBiAccess
output vnetName string = vnet.name
output functionSubnetId string = functionSubnet.id
