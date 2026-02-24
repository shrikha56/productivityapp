"""
Vercel serverless: GET /api/entries — list user's entries for history/analysis.
Requires: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""
import json
from http.server import BaseHTTPRequestHandler

SUPABASE_URL = __import__("os").environ.get("SUPABASE_URL", "")
SUPABASE_KEY = __import__("os").environ.get("SUPABASE_SERVICE_ROLE_KEY") or __import__("os").environ.get("SUPABASE_ANON_KEY", "")


def get_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def get_user_id(headers):
    from api.security import get_user_id as _get_user_id
    return _get_user_id(headers.get("Authorization", ""))


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        user_id = get_user_id(self.headers)
        if not user_id:
            self._send(401, {"error": "Authentication required"})
            return

        supabase = get_supabase()
        if not supabase:
            self._send(503, {"error": "Server not configured"})
            return

        try:
            result = supabase.table("entries").select(
                "id, date, sleep_hours, sleep_quality, energy, deep_work_blocks, reflection_summary, entry_number, is_follow_up"
            ).eq("user_id", user_id).order("date", desc=True).limit(90).execute()
        except Exception:
            result = supabase.table("entries").select(
                "id, date, sleep_hours, sleep_quality, energy, deep_work_blocks, reflection_summary"
            ).eq("user_id", user_id).order("date", desc=True).limit(90).execute()

        entries = result.data or []
        from api.security import decrypt
        for e in entries:
            e["reflection_summary"] = decrypt(e.get("reflection_summary") or "")

        self._send(200, {"data": entries})

    def _send(self, status, body):
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))
