#!/usr/bin/env bash
# Run in Azure Cloud Shell (Bash), not on the Windows development machine.
# Default is a read-only what-if. apply is an explicit, billable deployment.
set -euo pipefail
mode="${1:-plan}"
location="${AZURE_LOCATION:-westus3}"
vm_size="${VM_SIZE:-Standard_B2s}"
architecture="${CPU_ARCHITECTURE:-x64}"
if [[ "$mode" != plan && "$mode" != apply ]]; then echo 'Use plan or apply.' >&2; exit 2; fi
: "${AZURE_RESOURCE_GROUP:?Choose a dedicated demo resource group}"
: "${DNS_LABEL:?Choose a unique lowercase hostname label}"
: "${ADMIN_SOURCE_CIDR:?Set your public IPv4 address followed by /32}"
: "${SSH_PUBLIC_KEY_FILE:?Set the path to your uploaded PUBLIC .pub key}"
python3 - "$ADMIN_SOURCE_CIDR" "$DNS_LABEL" "$SSH_PUBLIC_KEY_FILE" <<'PY'
import ipaddress,re,sys
from pathlib import Path
network=ipaddress.ip_network(sys.argv[1],strict=False)
if network.version!=4 or network.prefixlen!=32 or not network.network_address.is_global:
    raise SystemExit('Use one administrator public IPv4 /32, not a broad SSH network.')
if not re.fullmatch(r'[a-z][a-z0-9-]{2,61}[a-z0-9]',sys.argv[2]):
    raise SystemExit('DNS label must be 4–63 lowercase letters, digits or hyphens.')
if not Path(sys.argv[3]).read_text().startswith(('ssh-ed25519 ','ssh-rsa ')):
    raise SystemExit('Supply a PUBLIC SSH key, never a private key.')
PY
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
az account show --query '{subscription:name,id:id}' -o table
if [[ "$(az group exists --name "$AZURE_RESOURCE_GROUP")" != true ]]; then
    echo 'Create the dedicated resource group first, then re-run. No VM has been created.' >&2
    exit 2
fi
az vm list-skus --location "$location" --size "$vm_size" --all \
  --query '[].{size:name,restrictions:restrictions}' -o json
params=(location="$location" vmSize="$vm_size" cpuArchitecture="$architecture" dnsLabel="$DNS_LABEL" adminSourceCidr="$ADMIN_SOURCE_CIDR" "sshPublicKey=$(cat -- "$SSH_PUBLIC_KEY_FILE")")
if [[ "$mode" == plan ]]; then
    az deployment group what-if --resource-group "$AZURE_RESOURCE_GROUP" \
      --template-file "$script_dir/main.bicep" --parameters "${params[@]}"
else
    : "${CREDIT_AND_COST_CHECKED:?Set to yes only after verifying trial expiry, spending limit and the estimate}"
    if [[ "$CREDIT_AND_COST_CHECKED" != yes ]]; then exit 2; fi
    az deployment group create --name broadcast-hosting --resource-group "$AZURE_RESOURCE_GROUP" \
      --template-file "$script_dir/main.bicep" --parameters "${params[@]}" \
      --query properties.outputs -o json
fi
