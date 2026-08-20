import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    # Debug off by default — the Werkzeug debugger is an RCE if exposed.
    # Enable locally with: FLASK_DEBUG=1 python run.py
    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host="0.0.0.0", port=5000, debug=debug)
