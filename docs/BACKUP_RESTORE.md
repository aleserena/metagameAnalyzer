# Backup and restore

Two safety nets, for two kinds of accident:

| What went wrong | Use | Where |
|---|---|---|
| One event was deleted, merged, overwritten or badly edited | **Event snapshot** | Settings page → Event snapshots → Restore |
| The database is lost or broadly damaged (bad migration, runaway script, deleted volume) | **Point-in-time recovery** | Railway, steps below |

Event snapshots are taken automatically before an event is deleted or merged, before a Hadouken import, before "clear decks", and before a re-scrape of an event that already exists. They live *inside* the database, so they do not protect against losing the database itself. That is what point-in-time recovery is for.

## Point-in-time recovery (PITR)

Railway continuously archives the Postgres write log to a Railway storage bucket, with a full backup every week and a differential every day. The database can be restored to any moment in roughly the last **four weeks**. The window starts at the first backup after PITR was enabled; it is not retroactive.

- Enabled on **staging** and **production** on 2026-11-12 (`postgres` service in each environment).
- Cost: bucket storage ($0.015 per GB-month) plus network egress for the uploads ($0.05 per GB). Restores are free. For a database of a few hundred MB this is cents per month. Check the bucket size in the Railway dashboard after the first weeks.
- On-demand backups and backup schedules (`railway postgres pitr backup …`, `… schedule …`) need a Pro workspace and are **not** available on the current plan. PITR itself is.
- Enabling or disabling PITR **redeploys the database service**: the database is down until the new container starts and the site reports "database unavailable" meanwhile. On 2026-11-12 that took under a minute on staging and about **six minutes** on production (the deployment sat in "Deploying" after mounting the volume, then started normally). Do it when no scrape or MTGJSON sync is running, and wait before retrying.

### Check that it is healthy

```
railway postgres pitr status -s postgres -e production
railway postgres pitr status -s postgres -e staging
```

Expected: `Status: enabled` and `Bucket wired: yes`. Check after any change to the database service, and once a month.

### Restore

A restore never touches the running database. It creates a **new** Postgres service in the same environment, holding the data as it was at the moment you name.

1. Decide the moment to go back to: just before the accident. Times are UTC in RFC 3339 form, or a relative offset back from now (`30m`, `2h`, `1d`). Railway's clock is the reference; if an absolute time is rejected as "in the future", use a relative offset.
2. Start the restore:
   ```
   railway postgres pitr restore --at "2026-11-12T23:08:00Z" --new-service-name postgres-restored -y -s postgres -e production
   ```
   It runs in the background; the new service appears in the dashboard and takes a few minutes to deploy.
3. Check the restored copy before using it:
   ```
   railway run -s postgres-restored -e production -- sh -c 'psql "$DATABASE_PUBLIC_URL" -Atc "select count(*) from decks; select count(*) from matchups; select count(*) from events"'
   ```
   (`psql` must be installed locally. `railway run` injects the connection string without printing it.)
4. Then either:
   - **Take back the whole database:** in the app service's variables, point `DATABASE_URL` at the restored service (use Railway's reference to that service's `DATABASE_URL`), and redeploy the app. Everything written after the restore moment is gone. Keep the old database service until you are sure, then remove it and enable PITR on the new one (`railway postgres pitr enable -s postgres-restored -e production`).
   - **Take back only some rows:** copy what you need from the restored copy into the live database (`pg_dump -t <table>` from the copy, or `psql` with a `COPY`), then delete the restored service.
5. Delete the restored service in the Railway dashboard when you are done. It costs resources while it runs.

### Restore drill — 2026-11-12, staging

- Before: 241 decks on staging (from `GET /api/v1/decks?limit=1`).
- `railway postgres pitr restore --at 2m --new-service-name postgres-restore-drill -y -s postgres -e staging`, started about seven minutes after PITR was enabled.
- The restored service answered queries about four minutes after the command. It held **241 decks, 131 matchups, 24 events**, and was out of recovery mode. The app was not repointed.
- Lessons: an absolute `--at` a few seconds old was rejected as "in the future" (the local clock was ahead of Railway's), so relative offsets are safer; the first restore point is a few minutes after enabling.

Repeat the drill after any change of Postgres major version or Railway plan.
