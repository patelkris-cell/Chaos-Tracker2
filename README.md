# Chaos Tracker

This folder has everything for the project:

```
chaos-tracker/
  frontend/
    chaos-tracker-live.html   <- wired to the real backend below (open with VS Code Live Server)
    design-mockup.html        <- the original static design mockup (no backend needed, click around freely)
  backend/
    app/                      <- FastAPI source
    requirements.txt
    .env.example
    README.md                 <- full backend setup guide (Supabase, seeding, running, /chat endpoint)
```

## Quick start

1. **Backend** — open `backend/` in VS Code, then in its integrated terminal:

   ```bash
   cd backend
   python3 -m venv venv
   source venv/bin/activate        # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   cp .env.example .env
   ```

   Edit `.env`: set `SECRET_KEY` (generate one with
   `python -c "import secrets; print(secrets.token_hex(32))"`), and set
   `DATABASE_URL` (the default SQLite works with zero setup, or point it at
   your Supabase Postgres connection string — see `backend/README.md`).

   Then:

   ```bash
   python -m app.seed        # creates tables + demo data (kris@example.com / password123)
   uvicorn app.main:app --reload --port 8000
   ```

   Leave that running. Swagger docs: http://127.0.0.1:8000/docs

2. **Frontend** — right-click `frontend/chaos-tracker-live.html` in VS Code and
   choose "Open with Live Server" (install the Live Server extension if you
   don't have it). It should come up on `http://127.0.0.1:5500`, which matches
   the CORS allowlist already set in `backend/.env.example`.

   If your backend runs somewhere other than `127.0.0.1:8000`, add this
   before the closing `</body>` tag of the HTML file (or just edit the
   `API_BASE` constant near the top of the `<script>`):

   ```html
   <script>window.CHAOS_API_BASE = "http://your-host:port";</script>
   ```

3. `frontend/design-mockup.html` doesn't need the backend at all — it's the
   original clickable prototype with sample data baked in, useful for design
   review or showing someone the concept without spinning up the server.

See `backend/README.md` for the full endpoint list, what's real vs. still
mocked (phone verification, Census migration data, photo uploads), and the
"Next steps" list for what to build next.
