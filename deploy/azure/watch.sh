#!/usr/bin/env bash
set -euo pipefail
cd /opt/broadcast
id="$(docker compose -p broadcast -f compose.azure.yaml ps -q broadcast)"
if [[ -z "$id" ]]; then
    echo 'Application container is missing.' >&2
    exit 1
fi
health="$(docker inspect --format='{{.State.Health.Status}}' "$id")"
if [[ "$health" == unhealthy ]]; then
    echo 'Readiness failed repeatedly; restarting application container.' >&2
    docker compose -p broadcast -f compose.azure.yaml restart broadcast
fi
used="$(df -P /var/lib/docker | awk 'NR==2 {gsub(/%/,"",$5); print $5}')"
if (( used >= 85 )); then
    echo 'Disk usage is at least 85%; inspect before it fills.' >&2
fi
hostname="$(awk -F= '$1=="APP_HOSTNAME" {print $2; exit}' .env)"
if ! curl --fail --silent --show-error --max-time 15 \
    --resolve "$hostname:443:127.0.0.1" "https://$hostname/health/live" >/dev/null; then
    echo 'Local HTTPS health check failed. Review proxy and certificate logs.' >&2
    exit 1
fi
