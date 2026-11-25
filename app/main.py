import os
from pathlib import Path

from flask import Flask, jsonify, render_template
from werkzeug.exceptions import RequestEntityTooLarge

from app.catalog import SPEC
from app.config import MAX_FILE, ROOT
from app.errors import DomainIssue, error_response
from app.quota.routes import quota_api
from app.quota.store import QuotaStore
from app.review.store import Store
from app.routes import api


def _quota_path(database):
    override = os.getenv("WORKBENCH_QUOTA_DB")
    if override:
        return override
    base = database or os.getenv("WORKBENCH_DB")
    if base:
        return str(Path(base).with_name("quota.sqlite3"))
    return str(ROOT / "instance" / "quota.sqlite3")


def create_app(database=None):
    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = MAX_FILE + 64 * 1024
    runs_path = database or os.getenv("WORKBENCH_DB", str(ROOT / "instance" / "workbench.sqlite3"))
    app.extensions["runs"] = Store(runs_path)
    app.extensions["quota"] = QuotaStore(_quota_path(database))
    app.register_error_handler(DomainIssue, error_response)
    app.register_error_handler(RequestEntityTooLarge, lambda _: error_response(DomainIssue("FILE_TOO_LARGE", 413)))
    app.register_blueprint(api)
    app.register_blueprint(quota_api)

    @app.get("/")
    def home():
        return render_template("index.html", p=SPEC)

    @app.get("/healthz")
    def health():
        return jsonify(status="ok")

    return app


app = create_app()
