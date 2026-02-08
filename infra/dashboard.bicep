// dashboard.bicep - Streamlit Executive Dashboard Web App
// Deploys on the existing B1 App Service Plan with Entra ID authentication

targetScope = 'resourceGroup'

@description('Existing App Service Plan resource ID')
param appServicePlanId string

@description('Azure region for deployment')
param location string = resourceGroup().location

@description('ADLS Gen2 storage account name (for RBAC and env vars)')
param dataLakeAccountName string

@description('ADLS Gen2 DFS endpoint URL')
param storageAccountUrl string

@description('Container name for curated Parquet files')
param containerName string = 'curated'

@description('Entra ID Tenant ID for EasyAuth')
param tenantId string

@description('Entra ID App Registration Client ID for the dashboard')
param dashboardClientId string

@description('Application Insights connection string')
param appInsightsConnectionString string

@description('Existing VNet subnet resource ID for VNet integration')
param subnetId string

@description('Naming prefix for resources')
param prefix string = 'mdoast'

@description('Tags for all resources')
param tags object = {
  project: 'MDOAttackSimulation'
  environment: 'production'
}

var uniqueSuffix = uniqueString(resourceGroup().id)
var dashboardAppName = '${prefix}-dash-${uniqueSuffix}'

// ============================================================================
// Dashboard Web App
// ============================================================================
resource dashboardApp 'Microsoft.Web/sites@2023-01-01' = {
  name: dashboardAppName
  location: location
  tags: tags
  kind: 'app,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: appServicePlanId
    httpsOnly: true
    publicNetworkAccess: 'Enabled'
    virtualNetworkSubnetId: subnetId
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.11'
      appCommandLine: 'startup.sh'
      alwaysOn: true
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appSettings: [
        {
          name: 'STORAGE_ACCOUNT_URL'
          value: storageAccountUrl
        }
        {
          name: 'CONTAINER_NAME'
          value: containerName
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: appInsightsConnectionString
        }
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'false'
        }
        {
          name: 'WEBSITE_RUN_FROM_PACKAGE'
          value: '0'
        }
        {
          name: 'WEBSITES_CONTAINER_START_TIME_LIMIT'
          value: '600'
        }
      ]
    }
  }
}

// ============================================================================
// Entra ID Authentication (EasyAuth)
// ============================================================================
resource authSettings 'Microsoft.Web/sites/config@2023-01-01' = {
  parent: dashboardApp
  name: 'authsettingsV2'
  properties: {
    globalValidation: {
      requireAuthentication: true
      unauthenticatedClientAction: 'RedirectToLoginPage'
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: dashboardClientId
          openIdIssuer: 'https://sts.windows.net/${tenantId}/v2.0'
        }
        validation: {
          allowedAudiences: [
            'api://${dashboardClientId}'
          ]
        }
      }
    }
    login: {
      tokenStore: {
        enabled: true
      }
    }
  }
}

// ============================================================================
// RBAC: Storage Blob Data Reader for the dashboard managed identity
// ============================================================================
resource dataLakeAccount 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: dataLakeAccountName
}

// Storage Blob Data Reader role
var storageBlobDataReaderRoleId = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'

resource dashboardStorageRbac 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(dataLakeAccount.id, dashboardApp.id, storageBlobDataReaderRoleId)
  scope: dataLakeAccount
  properties: {
    principalId: dashboardApp.identity.principalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataReaderRoleId)
    principalType: 'ServicePrincipal'
  }
}

// ============================================================================
// Outputs
// ============================================================================
output dashboardAppName string = dashboardApp.name
output dashboardUrl string = 'https://${dashboardApp.properties.defaultHostName}'
output dashboardPrincipalId string = dashboardApp.identity.principalId
