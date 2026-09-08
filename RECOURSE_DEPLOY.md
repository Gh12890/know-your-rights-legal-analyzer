# Deploying Recourse

The public app is **`recourse_app.py`** (the single-flow UI). The older
multi-mode `app.py` stays in the repo but is not deployed.

## What the deploy needs

| | |
|---|---|
| Entry | `recourse_app.py` |
| Python | 3.13 (`.python-version`, `runtime.txt`) |
| Install | `pip install -r requirements.txt` (now UTF-8, full freeze) |
| Start | `streamlit run recourse_app.py --server.port $PORT --server.address 0.0.0.0 --server.headless true --server.enableCORS false` |
| Data at runtime | `embeddings/corpus_embeddings.json` (~38 MB, committed) + `chunks/*.json` |
| Secrets | `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY` (Indian Kanoon key is **not** needed by `recourse_app.py` — it does no live IK fetch) |

`railway.json` and `Procfile` both carry the start command; `.railwayignore` /
`.slugignore` trim `raw_pdfs/`, sample PDFs, eval output and `venv/` from the build.

## Railway steps

1. **New Project → Deploy from GitHub repo** → pick this repo, branch `submission`
   (or `main` after merge).
2. Railway auto-detects Nixpacks + Python and reads `railway.json`. If it picks
   the wrong Python, the `.python-version` pin (3.13) should hold.
3. **Variables** (Settings → Variables): add
   - `ANTHROPIC_API_KEY = sk-ant-...`
   - `VOYAGE_API_KEY = ...`
   Railway injects these as real env vars — the code reads `os.environ` first, so
   no `st.secrets` juggling is needed here (unlike Streamlit Community Cloud).
4. **Networking → check the health check** is `/_stcore/health` (railway.json sets it).
5. Deploy. First boot loads the 38 MB embeddings inside `@st.cache_resource` at
   startup (`_warm()` in `recourse_app.py`), so it happens while the container
   boots, not on the first user's click.

## Making the URL not say "railway"  ← required

Railway's generated domain is `*.up.railway.app` and always contains "railway".
The only way to remove it is a **custom domain you own**.

1. **Register a domain.** Options, in order of fit:
   - `recourse.law` (~$40–90/yr; `.law` is verified/regulated but fits perfectly)
   - `recourse.in` or `recourse.org.in` (cheap, India signal)
   - `getrecourse.com` / `recourse.app` / `tryrecourse.com` (if `.law`/`.in` taken)
   Registrars: Cloudflare Registrar (at-cost, no markup), Namecheap, Google Domains
   successor (Squarespace).
2. In Railway: **service → Settings → Networking → Custom Domain →** enter the
   domain (e.g. `recourse.law` or `app.recourse.law`). Railway shows a target.
3. At the registrar's DNS:
   - apex (`recourse.law`): add the ALIAS/ANAME/flattened-CNAME Railway gives you
     (Cloudflare supports CNAME flattening on the apex; most registrars need a
     subdomain instead).
   - subdomain (`app.recourse.law`): add a **CNAME** → the `*.up.railway.app`
     target Railway shows.
4. Wait for DNS + Railway's automatic TLS cert (usually minutes, up to ~1 hour).
5. Set the custom domain as the primary; keep the `*.up.railway.app` one working
   as a fallback but don't show it.

**Do this on Day 4, not demo day** — DNS propagation is the one step you can't rush.

## Protect the wallet (public link + paid keys)

- Anthropic console: set a **hard monthly spend cap** on the key before sharing.
- Voyage console: check the usage cap.
- `recourse_app.py` makes **one Haiku call per submission** (the router) and no
  other model calls on the hot path — the rights, cases, document and badges are
  all pure Python. A junk flood costs ~one cheap Haiku call each; `OUT_OF_SCOPE`
  short-circuits the rest.
- If you want a belt-and-braces limit, add a per-session counter in
  `st.session_state` (e.g. 15 checks/session).

## Backup URL

Also deploy `recourse_app.py` to **Streamlit Community Cloud** (free, ~10 min) as
a secondary link. On Cloud, the two keys go in **Manage app → Settings → Secrets**
(TOML), because Cloud's Secrets and `os.environ` are separate stores — the code
already checks `st.secrets` for `ANTHROPIC_API_KEY`; confirm `VOYAGE_API_KEY` too.

## Keep-warm (optional)

Railway Hobby doesn't sleep, but a restart leaves the container cold until the
first hit. Point a free **UptimeRobot** or **cron-job.org** monitor at the health
URL every 5 minutes.
