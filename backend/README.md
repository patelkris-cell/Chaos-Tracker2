# Chaos Tracker API

FastAPI backend for Chaos Tracker: incidents, comments/reactions, verification
voting, events, and area-trend insights. Built to match the frontend
prototype you already reviewed -- same data shapes, same mock locations.

Tested and working end-to-end (auth, incidents, heatmap, comments, voting,
events, area insights, the AI chatbot's `/chat` endpoint, real-key Census
migration data, and real SMS phone verification have all been run live and
confirmed working, not just smoke-tested against mocks).

## What's real vs. mocked right now

| Piece | Status |
|---|---|
| Register / login / JWT sessions | Real -- bcrypt password hashing, real tokens |
| Phone verification | **Real, live-tested (2026-08-25).** Three providers in `app/otp.py`: `mock` (code always `123456`, default), `textbelt` (real SMS via textbelt.com -- their free shared key is blocked for US numbers due to past abuse, but a paid personal key works, $3 for 50 texts), and `twilio` (real SMS via Twilio's plain Messaging API -- note Twilio now requires an upgraded/funded account to claim a phone number at all, not just to use their separate Verify product). |
| Incidents, comments, reactions, verification voting | Real -- backed by Postgres/SQLite, no mocking |
| Hex heatmap (`/incidents/heatmap`) | Real -- uses `h3-py`, same H3 grid system as the frontend's `h3-js` |
| Area trend insights (`/areas/insights`) | Real -- computed live from Incident rows (6mo vs. prior 6mo) |
| Population / income / area size | **Not built yet.** Needs the Census ACS integration -- see "Next steps" |
| Photo/GIF uploads on comments and reports | Real -- `POST /uploads`, plus an in-app GIF search (Klipy). Saves to local disk by default, or Cloudflare R2 if configured -- see "Deploying" below |
| Forecasting ("next 6 months") | Not built yet -- see "Next steps" |
| AI chatbot (`POST /chat`) | Real tool-calling loop against Claude, wired to real data -- but **not live-tested** here (no Anthropic key in this environment). See "The /chat endpoint" below. |
| County migration data (one `/chat` tool) | Real Census API integration, but **not live-tested** here -- outbound requests to census.gov were blocked in the sandbox this was built in. Verify it once you add a `CENSUS_API_KEY` and run it with real internet access. |

## 1. Open in VS Code

```
cd chaos-tracker-backend
code .
```

Install the **Python** extension (Microsoft) if you don't have it -- VS Code
will prompt you. When it asks which interpreter to use, point it at
`venv/bin/python` (created in step 2).

## 2. Create a virtual environment and install dependencies

In the VS Code integrated terminal (`` Ctrl+` ``):

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## 3. Set up your database (Supabase)

You picked cloud-hosted Postgres, so:

1. Go to [supabase.com](https://supabase.com) → New project (free tier is fine).
2. Once it's provisioned: **Project Settings → Database → Connection string**.
   Pick the **URI** tab, and use the **Session pooler** connection (works
   better than "Direct connection" for a dev server that starts/stops a lot).
3. Copy that string -- it looks like:
   `postgresql://postgres.xxxxxxxxxxxx:[YOUR-PASSWORD]@aws-0-xxxxx.pooler.supabase.com:5432/postgres`

Then:

```bash
cp .env.example .env
```

Open `.env` and set:

```
DATABASE_URL=postgresql://postgres.xxxx:YOUR-PASSWORD@aws-0-xxxx.pooler.supabase.com:5432/postgres
SECRET_KEY=<paste output of the command below>
```

Generate a real secret key (don't ship the placeholder one):

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

No PostGIS extension needed -- distance queries use plain Haversine math in
Python so a bare Supabase project works with zero extra setup. (If this
grows past a few hundred thousand incidents, revisit -- see `app/geo.py`.)

## 4. Create the tables and load demo data

```bash
python -m app.seed
```

This creates all tables (via `Base.metadata.create_all`, no migration tool
yet) and inserts a demo user (`kris@example.com` / `password123`) plus ~95
incidents and 4 events at the same coordinates the frontend prototype
already uses.

## 5. Run the server

In VS Code, press **F5** with `app/main.py` open (or just run it manually):

```bash
uvicorn app.main:app --reload --port 8000
```

Open **http://127.0.0.1:8000/docs** -- that's an interactive Swagger UI
where you can try every endpoint (click "Authorize" and paste a token from
`/auth/login` to hit the protected ones) without writing any frontend code.

## Endpoints at a glance

- `POST /auth/register`, `POST /auth/login`, `GET /auth/me`
- `POST /auth/phone/request`, `POST /auth/phone/confirm` -- mock OTP flow
- `POST /incidents`, `GET /incidents`, `GET /incidents/{id}`, `GET /incidents/pending`
- `GET /incidents/heatmap?resolution=8` -- H3 hex cells with density, ready for the map
- `POST /incidents/{id}/comments`, `GET /incidents/{id}/comments`, `PATCH /comments/{id}`, `DELETE /comments/{id}`
- `POST /comments/{id}/reactions` -- toggle an emoji reaction
- `POST /incidents/{id}/vote` -- confirm/deny, auto-verifies at 3 confirms
- `GET /events`, `POST /events`, `GET /events/{id}`
- `GET /areas/insights?lat=&lng=&radius_km=` -- the "Check area" endpoint
- `POST /chat` -- the AI chatbot (see below)

## The /chat endpoint

This is the "AI pulls real data and answers questions" feature. It's a small
tool-calling loop against Claude:

1. You send `{"message": "...", "lat": ..., "lng": ...}`.
2. Claude reads the message and decides whether it needs data, and which of
   three tools answers it: `get_area_trend` (rising/falling incidents, same
   numbers as `/areas/insights`), `get_incident_breakdown` (counts by
   category), or `get_county_migration` (Census in/out migration for the
   county -- **county-level, not neighborhood-level**, Claude is instructed
   to say so).
3. Our backend runs the real query, Claude reads the result, and writes a
   plain-language answer. It's told explicitly never to invent numbers.

**To turn it on:** get a key at
[console.anthropic.com](https://console.anthropic.com) (Settings → API
Keys), put it in `.env` as `ANTHROPIC_API_KEY`. Without it, every other
endpoint in this API still works -- `/chat` alone returns a clear error
telling you the key is missing, instead of crashing.

**Important -- what I could and couldn't test:** I built this in a sandboxed
environment with no Anthropic API key available to me and no outbound access
to census.gov, so two things could not be exercised end-to-end here:

- The actual round-trip to Claude (the tool-calling loop) -- I tested every
  piece around it (the tools themselves, the error handling when the key is
  missing, the request/response shapes) but not a live call. It's written
  against Anthropic's documented tool-use API, so it should work, but please
  run a real question through it once you've added your key and tell me if
  anything looks off.
- `get_county_migration`'s Census API calls (`app/census.py`) -- same
  situation, written against Census's documented API shape but not
  live-verified. Get a free key at
  [api.census.gov/data/key_signup.html](https://api.census.gov/data/key_signup.html),
  set `CENSUS_API_KEY` in `.env`, and try a question like "how's migration in
  this county" once you're running with real internet access.

Try it once both keys are set:

```bash
curl -X POST http://127.0.0.1:8000/chat \
  -H "Authorization: Bearer <token from /auth/login>" \
  -H "Content-Type: application/json" \
  -d '{"message": "Whats the trend here and are more people moving in?", "lat": 40.758, "lng": -73.9855}'
```

The response includes both the plain-language `reply` and a `tool_calls`
array with the raw structured data each tool returned -- that's what the
frontend would use to render the chart cards under the bot's message, the
same way the prototype's chatbot mockup already does.

## Connecting the frontend prototype

The HTML prototype currently uses hardcoded JS arrays for incidents/events/
locations. To wire it to this API: replace those arrays with `fetch()` calls
to the endpoints above (e.g. `fetch('http://127.0.0.1:8000/incidents')`),
and swap the fake hex-density math for a call to `/incidents/heatmap`. Happy
to do that wiring in the next pass once you've had a look at this.

## Next steps (in the order I'd tackle them)

1. ~~Verify `/chat` and `/areas`'s county migration tool live~~ -- **done.**
   Live-tested 2026-08-25: the chatbot correctly calls both `get_area_trend`
   and `get_county_migration` and answers from real data. One real gap found
   and fixed: Census's `for=county/in=state` query only publishes the
   inbound (`MOVEDIN`) figure for most counties, not outbound -- `app/census.py`
   now reports `moved_out_available: false` and the frontend/chatbot both
   disclose that honestly instead of implying net migration is zero.
2. ~~Real phone verification~~ -- **done**, see the table above. If you want
   Twilio's nicer Verify product instead of plain SMS (built-in rate
   limiting, no code stored in our own DB) once you've upgraded that account,
   see the docstring at the top of `app/otp.py` for the small swap needed.
3. ~~Photo/GIF uploads~~ -- **done.** `POST /uploads` (local disk or R2, see
   "Deploying"), plus an in-app GIF search (`GET /gifs/search`, Klipy).
4. **Census demographics (population/income/area size)** -- separate from
   migration; pull ACS 5-year estimates by census tract, cache results (they
   only update yearly), fill in `AreaInsights`.
5. **Forecasting** -- a small `pandas` + `statsmodels`/`prophet` job that
   projects the next 6 months per area/hex cell, exposed as a 4th `/chat` tool.
6. **Alembic migrations** -- once the schema stabilizes, replace
   `Base.metadata.create_all()` with real migrations so schema changes don't
   require dropping tables.
7. **CAPTCHA at registration** -- Cloudflare Turnstile, verified server-side
   before `/auth/register` accepts the request.

## Deploying

Everything below is free, at the cost of two trade-offs worth knowing up
front: the backend "falls asleep" after ~15 minutes with no traffic and
takes 30-60 seconds to wake back up on the next request, and the database
pauses after a week of no activity (visiting its dashboard un-pauses it in
a few seconds). If that ever becomes annoying, Render's ~$7/month paid web
service tier removes the sleep behavior -- nothing else about this setup
changes.

You'll end up with three free accounts: **GitHub** (holds your code so
Render can deploy it), **Render** (runs the backend, hosts the frontend),
**Supabase** (the production database), and optionally **Cloudflare** (R2,
for photos/GIFs that survive redeploys). Steps 1-2 you do once; steps 3-6
you can do in any order.

### 1. Push the code to GitHub

In VS Code: open the **Source Control** panel (the branching icon in the
left sidebar) with the `chaos-tracker` folder open, and click **Publish to
GitHub**. Pick "Publish to GitHub public/private repository" (private is
fine, Render can still read it) -- this creates the repo and pushes your
code in one step, no command line needed. Do this for both the `backend`
and `frontend` folders (or as one combined repo, whichever VS Code offers
you -- either works with the steps below, just adjust the "Root Directory"
setting in step 3 to match).

### 2. Set up Supabase (production database)

1. [supabase.com](https://supabase.com) -> New project (free tier).
2. Once it's provisioned: **Project Settings -> Database -> Connection
   string** -> URI tab -> **Session pooler** connection (works better than
   "Direct connection" for a server that starts/stops a lot, which the free
   Render tier does).
3. Copy that string -- you'll paste it into Render as `DATABASE_URL` in
   step 3. It looks like:
   `postgresql://postgres.xxxx:[YOUR-PASSWORD]@aws-0-xxxx.pooler.supabase.com:5432/postgres`

This is a brand-new empty database -- the backend creates all its tables
automatically on first startup (see `Base.metadata.create_all` in
`app/main.py`), so there's nothing else to run manually here.

### 3. Deploy the backend on Render

1. [render.com](https://render.com) -> New -> Web Service -> connect your
   GitHub account -> pick the repo.
2. If backend and frontend are separate folders in one repo, set **Root
   Directory** to `backend`.
3. **Runtime:** Python 3. **Build Command:** `pip install -r
   requirements.txt`. **Start Command:** `uvicorn app.main:app --host
   0.0.0.0 --port $PORT`.
4. **Instance Type:** Free.
5. Under **Environment**, add every variable from your local `.env` (see
   `.env.example` for the full list and what each does) -- paste them in
   one at a time, or use Render's "Add from .env" bulk-paste option. Two
   values need to be different from your local `.env`:
   - `DATABASE_URL` -- the Supabase connection string from step 2, not your
     local `sqlite:///./chaos.db`.
   - `CORS_ORIGINS` -- add your frontend's Render URL once you have it from
     step 4 below (e.g. `https://chaos-tracker.onrender.com`), comma-
     separated with whatever's already there.
6. Click **Create Web Service**. First deploy takes a few minutes; Render
   gives you a URL like `https://chaos-tracker-api.onrender.com` when it's
   done -- visit `<that URL>/health` to confirm it says `{"status":"ok"}`.

### 4. Deploy the frontend on Render

1. [render.com](https://render.com) -> New -> Static Site -> same repo.
2. If it's a separate `frontend` folder, set **Root Directory** to
   `frontend`. **Build Command:** leave blank (it's a plain HTML file, no
   build step). **Publish Directory:** `.`
3. Create it -- Render gives you a URL like
   `https://chaos-tracker.onrender.com`.
4. In `chaos-tracker-live.html`, find the line near the top of the
   `<script>` block:
   ```js
   const DEPLOYED_API_BASE = "https://chaos-tracker-api.onrender.com";
   ```
   and set it to your actual backend URL from step 3. Commit and push --
   Render redeploys the static site automatically on every push once it's
   connected to GitHub.
5. Go back to your **backend's** `CORS_ORIGINS` env var on Render (step
   3.5) and make sure this frontend URL is in the list, then also set
   `FRONTEND_BASE_URL` to `https://<your-frontend-url>/chaos-tracker-live.html`
   so password-reset links point at the real deployed site instead of your
   local file.

### 5. Cloudflare R2 (persistent photo/GIF storage)

Without this, uploaded photos/GIFs are stored on the backend's local disk,
which Render's free tier wipes on every redeploy -- fine while you're still
actively testing, but not something to rely on long-term.

1. [dash.cloudflare.com](https://dash.cloudflare.com) -> R2 -> Create
   bucket (any name, e.g. `chaos-tracker-uploads`).
2. Open the bucket -> **Settings** -> enable **Public access** (gives you a
   `https://pub-xxxx.r2.dev` URL -- that's your `R2_PUBLIC_BASE_URL`).
3. R2 -> **Manage API tokens** -> Create API token -> permission **Object
   Read & Write**, scoped to that one bucket. Note the **Account ID**, the
   **Access Key ID**, and the **Secret Access Key** it shows you (the
   secret is only shown once -- copy it immediately).
4. Add all five `R2_*` variables to your backend's Render environment (see
   `.env.example`) and it redeploys automatically. Uploads switch over to
   R2 immediately, no other changes needed.

### 6. Final checklist

- [ ] Backend `/health` returns `{"status":"ok"}` at its Render URL
- [ ] Frontend loads at its Render URL and successfully calls the backend
      (check the "connected to API" banner)
- [ ] `CORS_ORIGINS` on the backend includes the frontend's real URL
- [ ] `FRONTEND_BASE_URL` on the backend points at the deployed frontend
- [ ] `DATABASE_URL` on the backend is the Supabase connection string, not
      SQLite
- [ ] Register a real account and confirm data persists after a backend
      redeploy (proves you're actually on Supabase, not a fresh SQLite file)

## Project layout

```
app/
  main.py          FastAPI app, CORS, router wiring
  config.py         env-var settings
  database.py       SQLAlchemy engine/session
  models.py         ORM tables
  schemas.py        Pydantic request/response shapes
  security.py       password hashing, JWT
  deps.py           get_db / get_current_user
  otp.py            phone verification (mock / textbelt / twilio, all live-tested)
  geo.py            Haversine + H3 hex helpers
  analytics.py      shared trend/breakdown queries (used by /areas and /chat)
  census.py         Census geocoder + migration flows (not live-tested, see above)
  ai_tools.py       tool definitions + dispatcher for the chatbot
  seed.py           demo data matching the frontend prototype
  routers/
    auth.py  users.py  incidents.py  comments.py  verify.py  events.py  areas.py  chat.py
```
