"""CompanyDB web app — static pages + reactions API."""

from __future__ import annotations

from pathlib import Path

from flask import Flask, send_from_directory

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "output"


def create_app() -> Flask:
    app = Flask(__name__, static_folder=None)

    from app.reactions import reactions_bp

    app.register_blueprint(reactions_bp)

    @app.get("/")
    @app.get("/index.html")
    def index():
        return send_from_directory(OUTPUT, "index.html")

    @app.get("/compare.html")
    def compare():
        return send_from_directory(OUTPUT, "compare.html")

    @app.get("/favicon.ico")
    def favicon():
        return send_from_directory(OUTPUT / "assets", "favicon.ico")

    @app.get("/assets/<path:filename>")
    def assets(filename: str):
        return send_from_directory(OUTPUT / "assets", filename)

    @app.get("/companies/<path:filename>")
    def companies(filename: str):
        return send_from_directory(OUTPUT / "companies", filename)

    @app.get("/healthz")
    def healthz():
        return {"ok": True, "service": "companydb"}

    return app
