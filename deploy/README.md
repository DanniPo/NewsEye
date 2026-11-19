# Deploying Newseye on a server

One server runs everything, with Docker Compose (`docker-compose.yml` at the
repository root):

| Service | What it does |
|---|---|
| `db` | PostgreSQL 18 with pgvector. Reachable from the server itself only. |
| `pipeline` | Brings the schema up to date, creates the API's read-only account, then runs `backend.pipeline` every 2 hours (collect, group, compare, people pages). |
| `api` | The read-only web API, logged in with the read-only account. |
| `web` | Caddy: the React pages, `/api` passed to the API, HTTPS certificates obtained and renewed by itself, and a login prompt while the site is private. |
| `backup` | A `pg_dump` of the database once a day into `./backups`, the last 7 kept. |

Every model is inside the `app` image, built from `deploy/Dockerfile`, so a
server never downloads one in the middle of a run. Nothing needs a graphics
card.

## What the server needs

- **Ubuntu 24.04 LTS, 4 vCPUs, 8 GB of memory, 40 GB of disk.** Measured
  in Docker on the development laptop, with no graphics card: during a full
  pipeline run the five services together peaked at 4.0 GiB (the pipeline
  3.45 GiB, the API 0.48 GiB), because each stage loads only its own models
  and exits. 8 GB leaves room for busier runs. The images take about 10 GB
  of disk; the database grows by roughly 6 MB per 1,000 articles.
- **A domain name** whose A record points at the server's IP address. Caddy
  needs it to get the HTTPS certificate.
- **No paid service** besides the server and the domain. Student offers (the
  GitHub Student Developer Pack, Azure for Students) may cover both; check
  their current terms.

## First deployment

1. **Point the domain at the server** (an A record) and wait until
   `ping your-domain` answers from the server's address.

2. **Install Docker and open the firewall** (on the server, as a user with
   `sudo`):

   ```bash
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker $USER        # then log out and in again
   sudo ufw allow OpenSSH && sudo ufw allow 80,443/tcp && sudo ufw allow 443/udp
   sudo ufw enable
   ```

3. **Get the code**, at the version to deploy:

   ```bash
   git clone https://github.com/DanniPo/NEWSEYE.git newseye
   cd newseye
   git checkout main
   ```

   A private repository needs a deploy key or a token on the server.

4. **Write the settings.** Copy the template and fill it in:

   ```bash
   cp deploy/env.example .env
   openssl rand -base64 24      # run twice: DB_PASSWORD, NEWSEYE_API_DB_PASSWORD
   docker run --rm caddy:2 caddy hash-password --plaintext 'a login password'
   nano .env
   ```

   Put the hash, not the password, in `NEWSEYE_LOGIN_HASH`, inside the single
   quotes. Give the login password to the people who will try the site.
   `.env` holds the secrets: it is in `.gitignore`; never commit it.

5. **Build and start:**

   ```bash
   docker compose up -d --build
   ```

   The first build downloads about 3 GB (Python packages and models), so it
   can take half an hour or more on a slow connection; later builds reuse
   what was downloaded.

6. **Check that it works:**

   ```bash
   docker compose ps                       # all five services up; api "healthy"
   curl -u reviewer:'the login password' https://your-domain/api/health
   docker compose logs -f pipeline         # the first run, live
   ```

   Then open `https://your-domain` in a browser and log in. The database
   starts empty: the first run collects the feeds' current entries and groups
   them, and stories read "not compared yet" until the comparison stage
   reaches them (see Operating limits). The page refreshes itself after each
   run.

## Updating, and going back

```bash
git pull                       # or: git checkout <the commit to deploy>
docker compose up -d --build
```

To go back to an earlier version, check out its commit and run the same
command. The migrations add tables, columns and indexes and drop nothing but a
duplicate index (columns of retired features go only with `--drop-retired`,
which the server never runs). If an older version still fails on the newer
schema, restore the backup taken before the update.

## Backups and restoring

`backup` writes `backups/newseye-<date>.dump` once a day, with the first
when it starts, and keeps the last 7 (`NEWSEYE_BACKUPS_KEPT`). The dumps stay
on the server: copy them elsewhere regularly, for example from your own
computer:

```bash
scp 'user@your-server:newseye/backups/*.dump' .
```

They hold the outlets' headlines and snippets, so keep them private.

To restore one, replacing the current database:

```bash
docker compose stop pipeline api
docker compose exec db dropdb -U postgres newseye
docker compose exec db createdb -U postgres newseye
docker compose exec -T db pg_restore -U postgres -d newseye < backups/newseye-<date>.dump
docker compose up -d
```

The pipeline service re-grants the API's account when it starts, and the next
run carries on from the restored state. This procedure was tested: a database
of 209 articles and 42 stories was dropped, recreated and restored, and the
API reported the same counts afterwards.

## Operating limits

- **Time per run.** Without a graphics card the models run 3 to 7 times
  slower than on the laptop's. The first run of this deployment, in Docker on
  the laptop's CPU (8 threads), took 498 s: 237 s to collect 209 articles and
  group them, 211 s to compare 21 stories (median 5.0 s, slowest 38.1 s, over
  the 30 s measured with a graphics card) and 51 s for the people pages. A
  4-vCPU server will be slower, but well inside the 2-hour interval.
- **Freshness.** New stories appear after each run, every 2 hours, and read
  "not compared yet" until the comparison stage reaches them. A run that
  outlasts the interval is followed by the next one a minute later; two runs
  never overlap.
- **Outlets.** Some sites block automated reading (People Daily's Cloudflare
  check) or are sometimes unreachable (Kenya News). Their headlines are still
  collected, and the site says when an article could not be read.
- **The API** allows 120 requests a minute per reader (30 searches), counted
  by the reader's address, which Caddy passes on.

## Before going public

`NEWSEYE_ACCESS=public` removes the login. Before that:

- **Logins and roles.** The MVP scope requires them, and who logs in is still
  to be agreed with the supervisor.
- **The outlets.** Check each site's terms of use and robots.txt, and give
  outlets a way to ask to be left out.
- **A privacy notice.** The site keeps no reader data, but say so, and say who
  runs it.

## The database alone, on a laptop

`docker compose up -d db` starts only PostgreSQL with pgvector, on
`127.0.0.1:5433`, with `DB_PASSWORD` from your shell or a `.env` file. See
the Setup section of the main README for running the Python code against it.
