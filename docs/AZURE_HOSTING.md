# Azure judge-demo hosting

Prepared October 25, 2026 for West US 3, supplied by the user. Nothing in this guide has created Azure resources. The subscription, quota, trial expiry and credit spending limit have not been inspected. This is a reviewed deployment package; a live Azure rollout remains to be done.

## Architecture and cost

One Ubuntu 24.04 Linux VM (proposed `Standard_B2s`, 2 vCPU/4 GiB) runs the existing application container and Caddy. The app has one worker and uses SQLite on the VM's persistent managed OS disk. Docker volumes and certificates survive process/container/VM restarts. They do not survive deleting their disk/volume. Do not put them on Azure temporary storage or a network file share.

The Azure public IP supplies a hostname such as `YOUR-LABEL.westus3.cloudapp.azure.com`. Caddy obtains and renews its HTTPS certificate; no custom domain purchase is needed. Judges see one HTTPS URL, with no login or installation. A dedicated resource group keeps the demo separate from the existing Foundry deployment. The current app can continue using that existing model endpoint.

Public Linux retail prices retrieved from Microsoft's [Retail Prices API](https://learn.microsoft.com/en-us/rest/api/cost-management/retail-prices/azure-retail-prices) on October 25:

| Item | Rate | Approximate 408-hour cost |
| --- | --- | --- |
| B2s Linux VM, West US 3 | $0.0416/hour | $16.98 |
| Standard static IPv4 | $0.005/hour | $2.04 |
| 32 GiB E4 Standard SSD managed OS disk | $2.40/month, prorated using 730 hours | $1.35 |
| Base total | | About $21 |

Allow $25 credit for hosting through the end of judging, plus model calls, disk operations/mount meters and any excess data transfer. See `deploy/azure/PRICE_ESTIMATE.json` for the recorded assumptions. This is not an invoice or a hard dollar cap. No free allowances or discounts are assumed. VM availability and quota in this subscription still need checking; reprice any replacement size before provisioning. Ongoing base cost is roughly $37/month, before variable charges. Do not enable Bastion, premium disks, NAT Gateway, paid monitoring or paid support as incidental defaults.

Before creating billable resources, verify the user-reported $180 credit, its expiry through November 10, 2026 at 11:59 pm Pacific, and the subscription's spending-limit status. Budget alerts are notifications, not hard stops. A pay-as-you-go subscription does not provide the same trial spending-limit protection. No promise of $0 out-of-pocket can be made from a public price estimate alone.

## Preparation on this computer

```powershell
pnpm build
.\.venv\Scripts\python.exe -m scripts.smoke_deployment --public
.\.venv\Scripts\python.exe -m scripts.package_hosting
```

The source archive is `runtime/release/broadcast-hosting.tar.gz`, with a SHA256 sidecar. It uses an explicit allowlist: no .env, database, browser workspace, node_modules, logs, private SSH key or Git history is included. It contains synthetic match data and the source needed to build on the VM. The Docker build context separately excludes credentials. The Azure demo starts with a fresh editorial database; local producer history is not uploaded.

For SSH, use a dedicated key whose public half can be uploaded to Cloud Shell. Keep the private half on the administrator's computer. Do not put keys in chat or source control. Only the administrator's single public IPv4 /32 is allowed on SSH; ports 80 and 443 are public. No port 8000/8080 is opened in the Azure network security group. This is infrastructure administration access, not a producer login.

## Azure Cloud Shell: preview before applying

The local computer currently has neither Azure CLI nor Docker. Use Azure Portal's Bash Cloud Shell, which supplies an authenticated Azure CLI, to inspect the account and preview the infrastructure. Cloud Shell can involve its own backing-storage charges; use an ephemeral/no-storage session where offered and keep your files locally. Do not enable extra services casually.

Upload the release archive and the PUBLIC SSH `.pub` key to Cloud Shell, then:

```bash
mkdir -p broadcast-hosting
tar -xzf broadcast-hosting.tar.gz -C broadcast-hosting
cd broadcast-hosting
az account show --query '{subscription:name,id:id}' -o table
# If necessary, select the intended existing subscription first:
# az account set --subscription YOUR-SUBSCRIPTION-ID

export AZURE_RESOURCE_GROUP='broadcast-copilot-demo'
export DNS_LABEL='YOUR-UNIQUE-LOWERCASE-LABEL'
export ADMIN_SOURCE_CIDR='YOUR-ADMINISTRATOR-PUBLIC-IP/32'
export SSH_PUBLIC_KEY_FILE="$HOME/YOUR-UPLOADED-KEY.pub"

# Create only an empty dedicated resource group after checking the account.
az group create --name "$AZURE_RESOURCE_GROUP" --location westus3
bash deploy/azure/provision.sh plan
```

The plan lists B2s restrictions and runs Azure's resource-group what-if. It does not deploy the VM. Inspect the selected subscription, restrictions, VM/disk size, IP, network rules and changes. Bicep compilation checks syntax/types but not subscription capacity. An empty resource group itself has no compute attached. Use a unique DNS label; the output hostname is authoritative.

Once the cost/credit checks and what-if are acceptable, this explicit command creates billable resources:

```bash
export CREDIT_AND_COST_CHECKED=yes
bash deploy/azure/provision.sh apply
```

Record the output hostname, IP and VM name. Never upload the Foundry key to Bicep, deployment parameters or cloud-init. The template carries no model secrets. Default OS disk deletion follows VM deletion; backups must be downloaded before cleanup. The normal teardown is deleting the dedicated demo resource group after judging, not merely shutting down the VM: disks and IPs can keep billing after deallocation. Do not delete the separate Foundry resource group.

## Upload and start the application

Wait for the VM to finish provisioning, then use SSH from the administrator computer. The script user is `bcadmin`. Keep normal SSH host-key verification enabled; verify its fingerprint through a trusted Azure channel before accepting the first connection.

```powershell
# Replace HOSTNAME and PRIVATE-KEY-PATH with your actual values.
scp -i PRIVATE-KEY-PATH runtime/release/broadcast-hosting.tar.gz bcadmin@HOSTNAME:/opt/broadcast/
ssh -i PRIVATE-KEY-PATH bcadmin@HOSTNAME
```

On the VM:

```bash
sudo cloud-init status --wait
cd /opt/broadcast
tar -xzf broadcast-hosting.tar.gz
# Create .env privately using an editor; do not put secrets in shell history.
umask 077
nano .env
```

The server-only file needs:

```dotenv
APP_HOSTNAME=YOUR-OUTPUT-HOSTNAME
FOUNDRY_BASE_URL=https://YOUR-RESOURCE.openai.azure.com/openai/v1/
FOUNDRY_API_KEY=YOUR-KEY
FOUNDRY_MODEL=YOUR-EXISTING-DEPLOYMENT-NAME
```

Use actual values from the existing local configuration; never paste them into chat or commit them. Check file permissions, then build and start:

```bash
chmod 600 .env
sudo docker compose -p broadcast -f compose.azure.yaml config --quiet
sudo docker compose -p broadcast -f compose.azure.yaml build
sudo docker compose -p broadcast -f compose.azure.yaml up -d
sudo docker compose -p broadcast -f compose.azure.yaml ps
curl --fail http://127.0.0.1:8080/health/ready
```

Do not print `docker compose config` without `--quiet`: resolved configuration can contain credentials. Allow time for DNS and HTTPS issuance, then open the HTTPS hostname from a different device/network. If cloud-init fails, inspect its status and logs before retrying installation. Do not use root containers or open additional ports as a workaround.

## Enable reboot startup, backup and local watchdog

On the VM after the first successful start:

```bash
sudo install -m 0644 deploy/azure/broadcast*.service deploy/azure/broadcast*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now broadcast.service broadcast-backup.timer broadcast-watch.timer
sudo systemctl start broadcast-backup.service
sudo systemctl list-timers 'broadcast-*'
```

The daily timer uses SQLite's online backup and puts restricted backup copies under `/opt/broadcast/backups` (and in the app volume). No retention deletion is automatic. Download backups regularly to a separate machine; same-VM backups do not protect against losing the VM/disk. The minute timer checks container health, restarts an unhealthy app, warns when Docker's disk reaches 85%, and checks the local HTTPS endpoint. Container restart policies also recover an exited process. Timer output is available via `journalctl -u broadcast-watch.service` / `broadcast-backup.service`. The watchdog cannot detect a dead VM from outside or email anyone; external uptime alerts remain a separate step and are not provisioned here.

## Public demo behavior and limits

The Azure compose file forces `PUBLIC_DEMO_MODE=1`. There is no producer login, as requested. Every browser gets a random workspace ID; those IDs separate work but are not authentication. Only synthetic demo material should be present. Someone with a workspace ID can access/change that workspace. This is a public demonstration of the enterprise workflow, not an enterprise access-control system.

Foundry connection probing, operations metrics and API schema/docs are blocked in both public app mode and the HTTPS proxy. Health checks do not call the model. Setup diagnostics are hidden in the public UI. Audit/history remain available for the browser workspace, and body size is limited at the proxy. HTTPS and these controls do not make the app resistant to all abuse or denial of service.

Public-mode model generation reserves a slot in SQLite before sending a request. Limits are 100 calls per rolling 24 hours and 500 total across the database, plus the existing 10-per-workspace/30-process calls per 10 minutes. Failed/provider-rejected calls consume a slot conservatively. Cache hits and calculated substitute cards do not. Restarting or changing fixture versions does not reset durable counts. Hitting the allowance returns HTTP 429 without calling the provider; saved work and calculated cards remain available. This is a call ceiling, not a dollar cap. Restoring an older backup also restores its older allowance count, so check that before enabling generation again. Do not discard the database or disable this mode to bypass a limit on a public site.

## Acceptance before submitting the link

- From a separate device/network, load the HTTPS URL and verify the certificate, replay, suggested moments, draft generation and approval.
- Verify a real Foundry-backed draft and its chart; the local smoke test deliberately uses calculated cards and proves no cloud inference connectivity.
- Confirm `/api/ops`, `/api/foundry/probe`, `/docs` and `/openapi.json` cannot be used publicly; the probe must be tested with POST as well as GET.
- Confirm saved edits/history survive container restart, stale graphics expire, and a private backup can be restored to a separate path without touching the active database.
- Test two browser workspaces, check health/logs and verify the watchdog and backup timers actually execute on Ubuntu.
- Check credit consumption and leave the service available through November 10, 2026 at 11:59 pm Pacific. Keep the public repository and under-two-minute video as separate submission artifacts.

Validated locally: Bicep compiles, Caddy configuration validates, backend/frontend checks and public-mode HTTP/restart/backup rehearsal. Not yet validated: Azure resource deployment, Linux container build/runtime, real certificate issuance, timers on Ubuntu, regional quota and live judge access. The recorded price estimate is public pricing, not an account billing inspection.
