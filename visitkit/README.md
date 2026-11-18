# visitkit — Starful content-site visit log

Anonymous visitor flow for HQ「이용자 보기」(no survey).

## What it stores
- Cookie `sf_vid` (random, 180 days)
- Events: `pv`, `click`, `cta`, `outbound`, `affiliate`, optional `search`
- Path · referrer host · lang · UTM when present
- Not stored: IP · accounts · form bodies

## Wire a site
1. Copy this package into the site repo as `visitkit/` (see okpy).
2. Copy `static/visit_track.js` → site static JS; include before `</body>` (Flask footer, FastAPI `base.html`, or HTML inject).
3. Register:
   - Flask: `from visitkit.flask_api import register_visitlog`
   - FastAPI (campus): `from visitkit.fastapi_api import register_visitlog`
   - `register_visitlog(app, site_id="…", db_path=…)`
4. Set `VISITLOG_SECRET` (or `SESSION_SECRET`) on Cloud Run (`cloudbuild` `--set-secrets`).
5. Production with multiple instances: `STORE_BACKEND=firestore` + `FIRESTORE_COLLECTION=<site>`.
6. In `/opt/work/sites.yaml` set `hq.visitlog: true`.
7. HQ Secret Manager: same `VISITLOG_SECRET` (derives per-site HMAC).

Rolled to: okpy · jpcampus · krcampus · okcaddie · okonsen · okramen · jpfun · companydb.

## Endpoints
- `POST /events` — beacon from `visit_track.js`
- `GET /hq/api/users?days=7|30|90` — Bearer HQ token
