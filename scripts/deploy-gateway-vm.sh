#!/usr/bin/env bash
# ============================================================================
# Deploy On-Premises Data Gateway VM with Azure Bastion
# ============================================================================
# Purpose: Deploy Windows VM accessible via Azure Bastion for Power BI gateway
# Requirements: Azure CLI, bash, jq, Contributor access to resource group
# Usage: ./scripts/deploy-gateway-vm.sh
# ============================================================================

set -euo pipefail

# ============================================================================
# Configuration
# ============================================================================

readonly SUBSCRIPTION_ID="ea321fd5-c995-4231-bebd-5d3fa7fff0fd"
readonly RESOURCE_GROUP="rg-mdo-attack-simulation"
readonly LOCATION="westus2"
readonly TEMPLATE_FILE="infra/gateway-vm.bicep"
readonly PARAMETERS_FILE="infra/gateway-vm.bicepparam"

# Colors
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m' # No Color

# ============================================================================
# Helper Functions
# ============================================================================

log() {
    echo -e "${GREEN}[INFO]${NC} $*"
}

warn() {
    echo -e "${YELLOW}[WARN]${NC} $*"
}

error() {
    echo -e "${RED}[ERROR]${NC} $*" >&2
}

section() {
    echo ""
    echo -e "${CYAN}============================================================================${NC}"
    echo -e "${CYAN}$*${NC}"
    echo -e "${CYAN}============================================================================${NC}"
    echo ""
}

# ============================================================================
# Prerequisites Check
# ============================================================================

check_prerequisites() {
    section "Checking Prerequisites"

    # Check Azure CLI
    if ! command -v az &> /dev/null; then
        error "Azure CLI is not installed. Install from https://aka.ms/installazurecli"
        exit 1
    fi

    AZ_VERSION=$(az version --query '"azure-cli"' -o tsv)
    log "Azure CLI version: $AZ_VERSION"

    # Check jq
    if ! command -v jq &> /dev/null; then
        error "jq is not installed. Install: apt-get install jq (Ubuntu) or brew install jq (macOS)"
        exit 1
    fi

    # Check if logged in
    if ! az account show &> /dev/null; then
        error "Not logged into Azure. Run 'az login' first."
        exit 1
    fi

    CURRENT_SUB=$(az account show --query id -o tsv)
    log "Current subscription: $CURRENT_SUB"

    # Check files exist
    if [[ ! -f "$TEMPLATE_FILE" ]]; then
        error "Bicep template not found: $TEMPLATE_FILE"
        exit 1
    fi

    if [[ ! -f "$PARAMETERS_FILE" ]]; then
        error "Parameters file not found: $PARAMETERS_FILE"
        exit 1
    fi

    log "Prerequisites check passed!"
}

# ============================================================================
# Get Password
# ============================================================================

get_secure_password() {
    section "VM Administrator Password"

    warn "Password requirements:"
    echo "  - Length: 12-72 characters"
    echo "  - Must contain 3 of: lowercase, uppercase, digit, special character"
    echo "  - Cannot contain username"
    echo ""

    while true; do
        read -s -p "Enter VM admin password: " PASSWORD
        echo ""
        read -s -p "Confirm password: " PASSWORD_CONFIRM
        echo ""

        if [[ "$PASSWORD" != "$PASSWORD_CONFIRM" ]]; then
            error "Passwords do not match!"
            continue
        fi

        PASSWORD_LENGTH=${#PASSWORD}
        if [[ $PASSWORD_LENGTH -lt 12 || $PASSWORD_LENGTH -gt 72 ]]; then
            error "Password must be 12-72 characters!"
            continue
        fi

        # Basic complexity check (at least 3 types)
        COMPLEXITY=0
        [[ "$PASSWORD" =~ [a-z] ]] && ((COMPLEXITY++))
        [[ "$PASSWORD" =~ [A-Z] ]] && ((COMPLEXITY++))
        [[ "$PASSWORD" =~ [0-9] ]] && ((COMPLEXITY++))
        [[ "$PASSWORD" =~ [^a-zA-Z0-9] ]] && ((COMPLEXITY++))

        if [[ $COMPLEXITY -lt 3 ]]; then
            error "Password must contain at least 3 character types!"
            continue
        fi

        break
    done

    echo "$PASSWORD"
}

# ============================================================================
# Deploy Resources
# ============================================================================

deploy_infrastructure() {
    local admin_password="$1"

    section "Deploying Gateway VM + Azure Bastion"

    log "Subscription: $SUBSCRIPTION_ID"
    log "Resource Group: $RESOURCE_GROUP"
    log "Location: $LOCATION"
    log "Template: $TEMPLATE_FILE"
    echo ""

    warn "Estimated monthly costs:"
    echo "  - Azure Bastion (Basic): ~\$140/month"
    echo "  - VM B2s (2 vCPU, 4GB): ~\$36/month"
    echo "  - Storage (127GB HDD): ~\$2/month"
    echo "  - TOTAL: ~\$178/month"
    echo ""

    read -p "Proceed with deployment? (yes/no): " CONFIRM
    if [[ "$CONFIRM" != "yes" ]]; then
        warn "Deployment cancelled."
        exit 0
    fi

    log "Starting deployment (this will take 10-15 minutes)..."
    log "Progress: Creating subnets -> Bastion -> VM -> Storage firewall rules"
    echo ""

    DEPLOYMENT_NAME="gateway-vm-$(date +%Y%m%d-%H%M%S)"

    DEPLOYMENT_OUTPUT=$(az deployment group create \
        --subscription "$SUBSCRIPTION_ID" \
        --resource-group "$RESOURCE_GROUP" \
        --template-file "$TEMPLATE_FILE" \
        --parameters "$PARAMETERS_FILE" \
        --parameters adminPassword="$admin_password" \
        --name "$DEPLOYMENT_NAME" \
        --output json)

    if [[ $? -ne 0 ]]; then
        error "Deployment failed!"
        error "Check Azure Portal for details:"
        error "https://portal.azure.com/#view/HubsExtension/DeploymentDetailsBlade/~/overview/id/%2Fsubscriptions%2F${SUBSCRIPTION_ID}%2FresourceGroups%2F${RESOURCE_GROUP}%2Fproviders%2FMicrosoft.Resources%2Fdeployments%2F${DEPLOYMENT_NAME}"
        exit 1
    fi

    echo "$DEPLOYMENT_OUTPUT"
}

# ============================================================================
# Post-Deployment Instructions
# ============================================================================

show_post_deployment_info() {
    local deployment_output="$1"

    section "Deployment Successful!"

    VM_NAME=$(echo "$deployment_output" | jq -r '.properties.outputs.vmName.value')
    VM_PRIVATE_IP=$(echo "$deployment_output" | jq -r '.properties.outputs.vmPrivateIp.value')
    ADMIN_USERNAME=$(echo "$deployment_output" | jq -r '.properties.outputs.adminUsername.value')
    VM_SIZE=$(echo "$deployment_output" | jq -r '.properties.outputs.vmSize.value')
    BASTION_NAME=$(echo "$deployment_output" | jq -r '.properties.outputs.bastionName.value')
    BASTION_PUBLIC_IP=$(echo "$deployment_output" | jq -r '.properties.outputs.bastionPublicIp.value')

    log "VM Information:"
    echo "  Name: $VM_NAME"
    echo "  Private IP: $VM_PRIVATE_IP"
    echo "  Admin Username: $ADMIN_USERNAME"
    echo "  Size: $VM_SIZE"
    echo ""

    log "Azure Bastion:"
    echo "  Name: $BASTION_NAME"
    echo "  Public IP: $BASTION_PUBLIC_IP"
    echo ""

    log "Cost Optimization:"
    echo "  Auto-shutdown: Enabled (7 PM Pacific)"
    echo "  To disable: az vm auto-shutdown -g $RESOURCE_GROUP -n $VM_NAME --off"
    echo ""

    section "Next Steps"

    echo -e "${CYAN}1. Connect to VM via Azure Bastion:${NC}"
    echo "   a. Open Azure Portal: https://portal.azure.com"
    echo "   b. Navigate to VM: $VM_NAME"
    echo "   c. Click 'Connect' -> 'Bastion'"
    echo "   d. Enter credentials and click 'Connect'"
    echo ""

    echo -e "${CYAN}2. Install On-Premises Data Gateway on VM:${NC}"
    echo "   a. Download: https://go.microsoft.com/fwlink/?linkid=2235690"
    echo "   b. Run installer as Administrator"
    echo "   c. Sign in with your Power BI account"
    echo "   d. Register gateway with a unique name"
    echo ""

    echo -e "${CYAN}3. Configure Power BI Connection:${NC}"
    echo "   a. In Power BI: Settings -> Manage connections and gateways"
    echo "   b. Select your gateway"
    echo "   c. Add data source: Azure Data Lake Storage Gen2"
    echo "   d. URL: https://mdoastdlsswuqpmzpslng.dfs.core.windows.net/"
    echo "   e. Authentication: OAuth 2.0 or Service Principal"
    echo ""

    echo -e "${CYAN}4. Test Connection:${NC}"
    echo "   a. In Power BI Desktop: Get Data -> Azure -> ADLS Gen2"
    echo "   b. Use gateway for connection"
    echo "   c. Browse to 'curated' container"
    echo "   d. Load Parquet files"
    echo ""

    section "Important Notes"

    warn "Security:"
    echo "  - VM has NO public IP (only accessible via Bastion)"
    echo "  - Storage firewall allows traffic from gateway subnet"
    echo "  - Managed Identity assigned to VM for Azure resource access"
    echo ""

    warn "Costs:"
    echo "  - Bastion runs 24/7 (~\$140/month)"
    echo "  - VM auto-shuts down at 7 PM Pacific (saves ~\$12/month)"
    echo "  - To reduce costs further, consider Developer tier Bastion when available"
    echo ""

    warn "Troubleshooting:"
    echo "  - Cannot connect to storage from VM?"
    echo "    Check VNet integration: az storage account show -n mdoastdlsswuqpmzpslng -g $RESOURCE_GROUP --query networkRuleSet"
    echo "  - Gateway not appearing in Power BI?"
    echo "    Verify internet connectivity from VM and gateway service is running"
    echo ""

    log "Deployment Complete! You can now connect to the VM via Bastion."
}

# ============================================================================
# Main Execution
# ============================================================================

main() {
    section "Gateway VM + Bastion Deployment Script"

    # Run checks
    check_prerequisites

    # Get password
    ADMIN_PASSWORD=$(get_secure_password)

    # Deploy
    DEPLOYMENT_OUTPUT=$(deploy_infrastructure "$ADMIN_PASSWORD")

    # Show next steps
    show_post_deployment_info "$DEPLOYMENT_OUTPUT"
}

# Trap errors
trap 'error "Script failed at line $LINENO"' ERR

main "$@"
