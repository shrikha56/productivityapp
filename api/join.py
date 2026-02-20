"""
Vercel serverless function: POST /api/join — stores beta signups in Supabase.
"""
import json
import os

from http.server import BaseHTTPRequestHandler


def get_supabase():
    url = os.environ.get("SUPABASE_URL") or os.environ.get("EXPO_PUBLIC_SUPABASE_URL", "")
    key = (
        os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
        or os.environ.get("SUPABASE_ANON_KEY")
        or os.environ.get("EXPO_PUBLIC_SUPABASE_KEY", "")
    )
    if not url or not key:
        return None
    from supabase import create_client
    return create_client(url, key)


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(content_len).decode("utf-8") if content_len else "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            self._send(400, {"ok": False, "error": "Invalid JSON"})
            return

        email = (data.get("email") or "").strip().lower()
        if not email or "@" not in email:
            self._send(400, {"ok": False, "error": "Valid email required"})
            return

        supabase = get_supabase()
        if not supabase:
            self._send(503, {"ok": False, "error": "Server not configured"})
            return

        try:
            supabase.table("signups").insert({"email": email}).execute()
            self._send(200, {"ok": True, "message": "You're on the list. We'll be in touch."})
        except Exception as e:
            err = str(e).lower()
            if "duplicate" in err or "unique" in err or "already" in err:
                self._send(200, {"ok": True, "message": "You're already on the list."})
            else:
                self._send(500, {"ok": False, "error": "Something went wrong"})

    def _send(self, status, body):
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))
