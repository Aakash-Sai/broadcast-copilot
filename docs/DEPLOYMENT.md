# Local deployment and operations

This milestone is a local deployment rehearsal, not an Azure deployment. No Azure resources or hosting charges were created. The native production entry point serves the built React UI and FastAPI API together on port 8080. The separate Vite development server remains available on port 5173.

For the subsequently prepared West US 3 rollout, see [Azure judge-demo hosting](AZURE_HOSTING.md). Its public-demo mode and durable call ceilings are tested locally; Azure deployment and Linux container runtime remain unverified.

## Run the production preview

Install the locked dependencies as described in README.md, then:

```powershell
pnpm build
.\start-production.ps1
```

Open http://127.0.0.1:8080. Stop with Ctrl+C and run the launcher again: saved drafts, decisions and still-valid publications return. Browser storage retains this workspace's ID, timeline and selected player/team; playback resumes paused. Use Save draft before refreshing to retain edits in the selected audience wording and chart style. Text that has only been typed locally is not saved automatically. Expired graphics remain in history and cannot be republished without a fresh eligible snapshot. Seeking backwards still invalidates graphics by design.

The default database is `runtime/editorial.sqlite3`, excluded from Git and image builds. `EDITORIAL_DB_PATH` overrides it. Both development and production previews use that default; run only one of them at a time against a given database. The current design supports exactly one process/worker and one app instance, with a persistent local filesystem. Do not place the active SQLite file on a network filesystem or synchronize it across machines. For long-term hosting, put it outside OneDrive/sync folders and use the environment override. Changing either fixture/history content creates an isolated workflow namespace; old records remain in the database.

The UI's collapsed Saved work and history section shows the latest 50 drafts. Download recent audit history exports up to 1,000 newest entries for the browser workspace. Events include UTC timestamp, sequence ID, match snapshot, sources, saved draft versions and approved publication wording. Generated, reused, saved, approved, dismissed, superseded, expired and cleared decisions are recorded. Identical polling is not audited. The app offers no audit-edit or audit-delete endpoint. This is not a tamper-proof compliance archive: an administrator with database access can alter it. Browser workspace IDs are not verified operator identities or authentication.

## Container package

If Docker Desktop with Compose is available:

```powershell
docker compose up --build -d
docker compose ps
docker compose logs --tail 50 broadcast
```

The image runs as a non-root user, serves one origin, installs locked dependencies and has a readiness health check. The compose port binds to localhost, logs rotate at 10 MB with three files, and a named volume preserves SQLite across container replacement. Runtime credentials come from .env; the allowlisted build context excludes credentials and runtime data. Ensure .env exists (copy .env.example if needed). `docker compose down` retains the volume; `down -v` deletes saved work and must not be used as routine shutdown. Restart policy restarts an exited process; a failed health check alone does not restart it.

Docker is not installed in the current environment, so the container image and Compose startup have not been executed here. Native production startup and HTTP/restart/backup checks are the verified deployment path for this milestone.

## Monitoring

| Endpoint | Meaning |
| --- | --- |
| `/health/live` | Process responds; no storage/model check |
| `/health/ready` | SQLite accepts a write transaction, fixture/history load and required frontend build exists; 503 on failure |
| `/api/health` | Model configuration is present; not proof of connectivity |
| `/api/ops` | In-process request counts by method/route/status, mean latency and uptime (reset on restart), plus durable draft-source/status and audit-event totals for this fixture |

Health polling does not call or bill Foundry. Missing model configuration is explicitly reported but does not make readiness fail: factual/calculated drafts are supported. Use the existing Check Foundry connection button separately for a real, potentially billable inference test.

Requests produce JSON logs containing server-generated request ID, UTC time, route template, status and elapsed milliseconds. Responses include X-Request-ID. Query strings, request/response bodies, session IDs and model credentials are not logged by this request logger. Expected storage errors return a generic 503; approval/save memory changes roll back if persistence fails. Unexpected exceptions may also appear in server error output, so treat operational logs as private.

For the local rehearsal, inspect `/health/ready` and `/api/ops`, and review logs when reproducing a problem. No external alerting service or dashboard is provisioned. On a hosted server, configure uptime polling (30–60 seconds), alert on repeated readiness failures or sustained 5xx responses, collect rotating logs and monitor volume free space. Also review factual-fallback frequency in audit exports. These are hosting steps still to implement, not automatic alerts supplied by this package. Mean API latency includes cache and non-model routes; it is not a model-only performance measure.

## Backup and recovery

Use SQLite's online backup API; do not copy only the live .sqlite3 file while WAL writes may be active.

```powershell
.\.venv\Scripts\python.exe -m scripts.backup_editorial backups/editorial-backup.sqlite3
```

For a container, back up into the mounted volume with `docker compose exec broadcast python -m scripts.backup_editorial /var/lib/broadcast/editorial-backup.sqlite3`, then copy the backup to a separate host/location using `docker compose cp`. A backup left only on the same disk is not disaster recovery. Restrict access: backups contain editorial content and workspace IDs. No automatic retention/deletion policy is enabled. Schedule backups when hosting and periodically test restoring them.

To restore: stop the app; retain the damaged database and any WAL/SHM files for investigation; choose a new empty directory outside the active database location, place the verified backup there, and point `EDITORIAL_DB_PATH` to it. Starting from a fresh path avoids combining a backup with stale WAL/SHM files. Start exactly one instance, verify readiness, open the same browser workspace and confirm history/publication at its original snapshot. SQLite backup preserves audit history, not the in-memory model cache or process counters. Model request limits are still process-local and reset on restart; they are not a permanent spending cap.

For releases: back up, build/test a new image or frontend/backend release, stop the old instance and start the new one using the same data path/volume. Keep the previous release available for rollback. The application checks schema version 1 and refuses unknown versions. This release adds the first durable schema; future schema changes need an explicit migration and backup strategy. Rollback must use a compatible schema.

## Access boundary

Login was deliberately excluded at the user's request. This milestone binds to localhost and should remain on a trusted machine/private network. Session separation does not restrict a person who knows a workspace ID; there are no verified producer roles. Do not treat the current application as a secure, unrestricted internet service. Azure deployment, TLS, external monitoring/alerts and any perimeter access arrangement remain later work before public judging access. No live cloud deployment or independent production-readiness certification is implied.
