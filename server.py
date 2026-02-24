"""
Signal landing page backend: stores beta signups in Supabase.
Set env: SUPABASE_URL and either SUPABASE_SERVICE_ROLE_KEY or SUPABASE_ANON_KEY.
Run: python server.py  →  http://127.0.0.1:5000/
"""
import os

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, jsonify, send_from_directory

app = Flask(__name__, static_folder=".", static_url_path="")

SUPABASE_URL = os.environ.get("SUPABASE_URL") or os.environ.get("EXPO_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_ANON_KEY")
    or os.environ.get("EXPO_PUBLIC_SUPABASE_KEY", "")
)
supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    from supabase import create_client
    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/checkin")
def checkin():
    return send_from_directory(".", "checkin.html")


@app.route("/analysis")
def analysis():
    return send_from_directory(".", "analysis.html")


@app.route("/report/weekly")
def report_weekly():
    return send_from_directory(".", "report.html")


@app.route("/history")
def history():
    return send_from_directory(".", "history.html")


@app.route("/api/join", methods=["POST"])
def join():
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "Valid email required"}), 400

    if not supabase:
        return jsonify({"ok": False, "error": "Server not configured"}), 503

    try:
        supabase.table("signups").insert({"email": email}).execute()
        return jsonify({"ok": True, "message": "You're on the list. We'll be in touch."})
    except Exception as e:
        err = str(e).lower()
        if "duplicate" in err or "unique" in err or "already" in err:
            return jsonify({"ok": True, "message": "You're already on the list."})
        # Log the real error (shows in terminal) for debugging
        print("[api/join error]", type(e).__name__, str(e))
        return jsonify({"ok": False, "error": "Something went wrong"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
