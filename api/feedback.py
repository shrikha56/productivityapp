"""
Vercel serverless: POST /api/feedback — stores user feedback after viewing reports.
Requires: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""
import json
import os
from http.server import BaseHTTPRequestHandler


def get_supabase():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY", "")
    if not url or not key:
        return None
    from supabase import create_client
    return create_client(url, key)


def get_user_id(headers):
    from api.security import get_user_id as _get_user_id
    return _get_user_id(headers.get("Authorization", ""))


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        user_id = get_user_id(self.headers)
        if not user_id:
            self._send(401, {"error": "Authentication required"})
            return

        content_len = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(content_len).decode("utf-8") if content_len else "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            self._send(400, {"error": "Invalid JSON"})
            return

        rating = data.get("rating")
        comment = (data.get("comment") or "").strip()[:1000]
        report_type = (data.get("report_type") or "").strip()[:50]

        if not rating or rating not in [1, 2, 3, 4, 5]:
            try:
                rating = int(rating)
                if rating < 1 or rating > 5:
                    raise ValueError
            except (TypeError, ValueError):
                self._send(400, {"error": "Rating must be 1-5"})
                return

        supabase = get_supabase()
        if not supabase:
            self._send(503, {"error": "Server not configured"})
            return

        row = {
            "user_id": user_id,
            "rating": rating,
            "comment": comment,
            "report_type": report_type,
        }

        try:
            supabase.table("feedback").insert(row).execute()
            self._send(200, {"ok": True, "message": "Thanks for your feedback!"})
        except Exception as e:
            self._send(500, {"error": f"Failed to save: {e}"})

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def _send(self, status, body):
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))
