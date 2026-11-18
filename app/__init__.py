"""CompanyDB web app — static pages + reactions API."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, send_from_directory

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)

    from app.analytics_status import analytics_status_bp
    from app.reactions import reactions_bp
    from app.recent_updates import recent_updates_bp

    app.register_blueprint(reactions_bp)
    app.register_blueprint(analytics_status_bp)
    app.register_blueprint(recent_updates_bp)

    @app.get("/")
    @app.get("/index.html")
    def index():
        return send_from_directory(OUTPUT, "index.html")

    @app.get("/compare.html")
    def compare():
        return send_from_directory(OUTPUT, "compare.html")

    @app.get("/about.html")
    def about():
        return send_from_directory(OUTPUT, "about.html")

    @app.get("/contact.html")
    def contact():
        return send_from_directory(OUTPUT, "contact.html")

    @app.get("/privacy.html")
    def privacy():
        return send_from_directory(OUTPUT, "privacy.html")

    @app.get("/favicon.ico")
    def favicon():
        return send_from_directory(OUTPUT / "assets", "favicon.ico")

    @app.get("/robots.txt")
    def robots():
        # Pin the mimetype explicitly — a host with an incomplete mimetypes
        # registry would otherwise fall back to application/octet-stream,
        # which crawlers may refuse to read as robots.txt / sitemap.xml.
        return send_from_directory(OUTPUT, "robots.txt", mimetype="text/plain")

    @app.get("/sitemap.xml")
    def sitemap():
        return send_from_directory(OUTPUT, "sitemap.xml", mimetype="application/xml")

    @app.get("/assets/<path:filename>")
    def assets(filename: str):
        return send_from_directory(OUTPUT / "assets", filename)

    @app.get("/companies/<path:filename>")
    def companies(filename: str):
        return send_from_directory(OUTPUT / "companies", filename)

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "service": "companydb"}


    # Anonymous visit log for Starful HQ「이용자 보기」
    from pathlib import Path as _VisitPath
    try:
        from visitkit.flask_api import register_visitlog as _register_visitlog
    except ImportError:
        import sys as _sys
        _sys.path.insert(0, str(ROOT))
        from visitkit.flask_api import register_visitlog as _register_visitlog
    _register_visitlog(app, site_id="companydb", db_path=ROOT / "data" / "visitlog.sqlite3")

    @app.after_request
    def _inject_visit_track(resp):
        ctype = (resp.content_type or "")
        if "text/html" not in ctype:
            return resp
        try:
            body = resp.get_data(as_text=True)
        except Exception:
            return resp
        if "visit_track.js" in body or "</body>" not in body.lower():
            return resp
        low = body.lower()
        idx = low.rfind("</body>")
        if idx < 0:
            return resp
        snippet = '<script src="/assets/visit_track.js" defer></script>'
        body = body[:idx] + snippet + body[idx:]
        resp.set_data(body)
        return resp

    return app
