"""Flask entry point + route registration, where the app is created and static files and CORS are configured
and the games api bp is plugged in. 
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, send_from_directory
from flask_cors import CORS

from routes.game import bp as games_bp

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")

_CLIENT_DIR = Path(__file__).resolve().parent.parent / "client"


app = Flask(__name__, static_folder=str(_CLIENT_DIR), static_url_path="")
CORS(app)
app.register_blueprint(games_bp, url_prefix="/api/games")


@app.get("/")
def index():
    return send_from_directory(app.static_folder, "index.html") # sending static file to the client 


if __name__ == "__main__":
    import os
    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1", port=5000)
