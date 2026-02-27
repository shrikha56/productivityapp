"""
Vercel serverless: GET /api/entries/<id> — fetch single entry.
Requires: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""
import json
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse

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


def validate_uuid(s):
    if not s or not isinstance(s, str):
        return False
    return bool(re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", s.strip().lower()))


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        parts = path.rstrip("/").split("/")
        entry_id = parts[-1] if parts else ""

        if not validate_uuid(entry_id):
            self._send(400, {"error": "Invalid entry ID"})
            return

        user_id = get_user_id(self.headers)
        if not user_id:
            self._send(401, {"error": "Authentication required"})
            return

        supabase = get_supabase()
        if not supabase:
            self._send(503, {"error": "Server not configured"})
            return

        try:
            result = supabase.table("entries").select("*").eq("id", entry_id).eq("user_id", user_id).single().execute()
            entry = result.data
            if not entry:
                self._send(404, {"error": "Entry not found"})
                return
            from api.security import decrypt
            def safe_decrypt(val):
                s = decrypt(val or "")
                return "" if (s and s.startswith("gAAAAA")) else (s or "")

            entry["transcript"] = safe_decrypt(entry.get("transcript"))
            entry["reflection_summary"] = safe_decrypt(entry.get("reflection_summary"))
            entry["predicted_impact"] = safe_decrypt(entry.get("predicted_impact"))
            entry["experiment_for_tomorrow"] = safe_decrypt(entry.get("experiment_for_tomorrow"))
            entry["likely_drivers"] = [safe_decrypt(d) for d in (entry.get("likely_drivers") or [])]
            entry_date = entry.get("date")
            entry_num = entry.get("entry_number") or 1
            try:
                same_day = supabase.table("entries").select("entry_number").eq("user_id", user_id).eq("date", entry_date).execute()
                nums = [r.get("entry_number") or 1 for r in (same_day.data or [])]
                max_num = max(nums) if nums else 1
                entry["is_final_for_day"] = (entry_num == max_num) or (len(nums) == 1)
            except Exception:
                entry["is_final_for_day"] = True
            self._send(200, {"data": entry})
        except Exception as e:
            err = str(e).lower()
            if "single" in err or "0 rows" in err or "not found" in err:
                self._send(404, {"error": "Entry not found"})
            else:
                self._send(500, {"error": str(e)})

    def _send(self, status, body):
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))
