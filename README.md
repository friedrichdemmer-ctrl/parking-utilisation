# Parking Garage Utilisation

Historical and live occupancy data for German parking garages, browsable via a
small web app: query & CSV download, a year-long heatmap, and multi-garage
daily comparisons. Data comes from the [defgsus/parking-data](https://github.com/defgsus/parking-data)
archive (2020-present) plus a live 30-minute poll of [api.parkendd.de](https://api.parkendd.de).

## Run it locally

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
./venv/bin/python collector.py          # one live snapshot
./venv/bin/python import_historical.py  # clones the archive + bulk-imports it (~1 min)
./venv/bin/python recluster.py          # reorders the table for fast per-garage queries (~1-10 min)
./venv/bin/python app.py                # http://127.0.0.1:5151
```

## Deploy publicly

The app needs a **persistent disk** (the database is ~14GB) and a **long-running
process** for the background collector, so it doesn't fit a serverless host like
Vercel. [Fly.io](https://fly.io) fits both requirements with a Docker deploy and
a mounted volume; the same Dockerfile works on Railway or any VPS.

You'll need to do the account/billing steps yourself — I can't create accounts
or enter payment details on your behalf.

### 1. Push the code to GitHub

```bash
gh repo create parking-utilisation --public --source=. --remote=origin
git add -A
git commit -m "Initial commit"
git push -u origin main
```

(No `gh`? Create the repo at github.com/new instead, then `git remote add origin <url>` and push.)
The `.gitignore` already excludes the local database, the cloned archive, and logs —
none of that gets pushed; the deployed instance rebuilds its own copy on first boot.

### 2. Deploy to Fly.io

```bash
# install the CLI (macOS)
curl -L https://fly.io/install.sh | sh

fly auth signup   # or `fly auth login` if you already have an account
fly launch --no-deploy   # edit fly.toml's `app` name when prompted, keep the Dockerfile it detects
fly volumes create parking_data --region fra --size 25   # 25GB: fits the ~14GB db plus headroom
fly deploy
```

First boot takes roughly 10-20 minutes: the container clones the historical
archive, imports ~88M rows, and reorders the table for fast queries, all onto
the mounted volume. Every boot after that starts instantly since the database
persists on the volume. Watch it with `fly logs`.

### Notes

- `RECLUSTER_CACHE_KB` / `RECLUSTER_TEMP_STORE=MEMORY` env vars can speed up
  that first-boot reorder step on a machine with more RAM (it defaults to a
  disk-backed sort that fits a 1GB instance; an in-memory sort used ~7.6GB
  locally but finishes in under a minute instead of several).
- Bump `[[vm]] memory` in `fly.toml` if you raise `RECLUSTER_CACHE_KB`.
- The collector runs as a background loop inside the same container
  (`collector_daemon.py`), not gunicorn workers, so it doesn't duplicate
  across the 2 web workers.
