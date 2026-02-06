// ============================================================================
// Azure VM + Bastion for On-Premises Data Gateway
// ============================================================================
// Purpose: Deploy a Windows VM accessible via Azure Bastion to host the
//          On-Premises Data Gateway for Power BI connectivity to ADLS Gen2
//
// Requirements:
// - No public IP on VM (policy restriction)
// - Secure RDP via Azure Bastion
// - VM must access storage account through VNet integration
// - Minimal cost (Basic Bastion + B2s VM)
// ============================================================================

@description('Azure region for all resources')
param location string = resourceGroup().location

@description('Existing VNet name')
param vnetName string = 'mdoast-vnet-sswuqpmzpslng'

@description('VM subnet address prefix')
param vmSubnetPrefix string = '10.0.2.0/24'

@description('Azure Bastion subnet address prefix (must be /26 or larger)')
param bastionSubnetPrefix string = '10.0.3.0/26'

@description('Storage account name to grant access from VM subnet')
param storageAccountName string = 'mdoastdlsswuqpmzpslng'

@description('VM size')
@allowed([
  'Standard_B1s'       // 1 vCPU, 1 GB RAM
  'Standard_B2s'       // 2 vCPU, 4 GB RAM
  'Standard_D2as_v7'   // 2 vCPU, 8 GB RAM (available in westus2)
])
param vmSize string = 'Standard_D2as_v7'

@description('VM administrator username')
param adminUsername string = 'azureuser'

@description('VM administrator password (min 12 chars, must meet complexity requirements)')
@secure()
param adminPassword string

@description('Name prefix for resources')
param namePrefix string = 'mdoast'

@description('Unique suffix from storage account name')
param uniqueSuffix string = 'sswuqpmzpslng'

@description('Enable auto-shutdown at 7 PM Pacific to save costs')
param enableAutoShutdown bool = true

@description('Auto-shutdown time in 24h format (default: 7 PM Pacific = 02:00 UTC)')
param autoShutdownTime string = '0200'

@description('Timezone for auto-shutdown (Pacific Standard Time)')
param autoShutdownTimeZone string = 'Pacific Standard Time'

// ============================================================================
// Existing Resources
// ============================================================================

resource existingVnet 'Microsoft.Network/virtualNetworks@2023-05-01' existing = {
  name: vnetName
}

resource existingStorageAccount 'Microsoft.Storage/storageAccounts@2023-01-01' existing = {
  name: storageAccountName
}

// ============================================================================
// Network: Subnets
// ============================================================================

resource vmSubnet 'Microsoft.Network/virtualNetworks/subnets@2023-05-01' = {
  parent: existingVnet
  name: 'snet-gateway'
  properties: {
    addressPrefix: vmSubnetPrefix
    serviceEndpoints: [
      {
        service: 'Microsoft.Storage'
        locations: [location]
      }
    ]
    privateEndpointNetworkPolicies: 'Disabled'
  }
}

resource bastionSubnet 'Microsoft.Network/virtualNetworks/subnets@2023-05-01' = {
  parent: existingVnet
  name: 'AzureBastionSubnet'  // MUST be this exact name
  dependsOn: [vmSubnet]  // Serial deployment to avoid vnet lock conflicts
  properties: {
    addressPrefix: bastionSubnetPrefix
  }
}

// ============================================================================
// Storage Account: Add VM Subnet to Firewall
// ============================================================================

resource storageAccountNetworkRules 'Microsoft.Storage/storageAccounts@2023-01-01' = {
  name: storageAccountName
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  dependsOn: [vmSubnet]
  properties: {
    isHnsEnabled: true  // ADLS Gen2
    networkAcls: {
      bypass: 'Logging, Metrics, AzureServices'
      defaultAction: 'Deny'
      virtualNetworkRules: [
        // Keep existing function subnet rule
        {
          id: '${existingVnet.id}/subnets/snet-functions'
          action: 'Allow'
        }
        // Add new gateway subnet rule
        {
          id: vmSubnet.id
          action: 'Allow'
        }
      ]
      ipRules: []
    }
  }
}

// ============================================================================
// Azure Bastion (Basic Tier)
// ============================================================================

resource bastionPublicIp 'Microsoft.Network/publicIPAddresses@2023-05-01' = {
  name: '${namePrefix}-bastion-pip-${uniqueSuffix}'
  location: location
  sku: {
    name: 'Standard'  // Required for Bastion
  }
  properties: {
    publicIPAllocationMethod: 'Static'
    publicIPAddressVersion: 'IPv4'
  }
}

resource bastion 'Microsoft.Network/bastionHosts@2023-05-01' = {
  name: '${namePrefix}-bastion-${uniqueSuffix}'
  location: location
  dependsOn: [bastionSubnet]
  sku: {
    name: 'Basic'  // ~$140/month (cheapest option)
  }
  properties: {
    ipConfigurations: [
      {
        name: 'bastionIpConfig'
        properties: {
          subnet: {
            id: bastionSubnet.id
          }
          publicIPAddress: {
            id: bastionPublicIp.id
          }
        }
      }
    ]
  }
}

// ============================================================================
// Windows VM for On-Premises Data Gateway
// ============================================================================

resource vmNic 'Microsoft.Network/networkInterfaces@2023-05-01' = {
  name: '${namePrefix}-gateway-nic-${uniqueSuffix}'
  location: location
  dependsOn: [vmSubnet]
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          subnet: {
            id: vmSubnet.id
          }
          privateIPAllocationMethod: 'Dynamic'
        }
      }
    ]
  }
}

resource gatewayVM 'Microsoft.Compute/virtualMachines@2023-03-01' = {
  name: '${namePrefix}-gateway-vm'
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    hardwareProfile: {
      vmSize: vmSize
    }
    osProfile: {
      computerName: 'gateway-vm'
      adminUsername: adminUsername
      adminPassword: adminPassword
      windowsConfiguration: {
        enableAutomaticUpdates: true
        patchSettings: {
          patchMode: 'AutomaticByOS'
        }
      }
    }
    storageProfile: {
      imageReference: {
        publisher: 'MicrosoftWindowsServer'
        offer: 'WindowsServer'
        sku: '2022-datacenter-azure-edition'
        version: 'latest'
      }
      osDisk: {
        createOption: 'FromImage'
        managedDisk: {
          storageAccountType: 'Standard_LRS'  // Standard HDD (cheapest)
        }
        diskSizeGB: 127
      }
    }
    networkProfile: {
      networkInterfaces: [
        {
          id: vmNic.id
        }
      ]
    }
  }
}

// ============================================================================
// VM Auto-Shutdown Schedule (Cost Optimization)
// ============================================================================

resource vmAutoShutdown 'Microsoft.DevTestLab/schedules@2018-09-15' = if (enableAutoShutdown) {
  name: 'shutdown-computevm-${gatewayVM.name}'
  location: location
  properties: {
    status: 'Enabled'
    taskType: 'ComputeVmShutdownTask'
    dailyRecurrence: {
      time: autoShutdownTime
    }
    timeZoneId: autoShutdownTimeZone
    notificationSettings: {
      status: 'Disabled'
    }
    targetResourceId: gatewayVM.id
  }
}

// ============================================================================
// Outputs
// ============================================================================

output vmName string = gatewayVM.name
output vmPrivateIp string = vmNic.properties.ipConfigurations[0].properties.privateIPAddress
output bastionName string = bastion.name
output vmSubnetName string = vmSubnet.name
output vmResourceId string = gatewayVM.id
output adminUsername string = adminUsername
output vmSize string = vmSize
output bastionPublicIp string = bastionPublicIp.properties.ipAddress
