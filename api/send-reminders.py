"""
Vercel serverless cron: GET /api/send-reminders
Runs daily via Vercel Cron to email users who haven't checked in today.
Requires: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, RESEND_API_KEY, CRON_SECRET
"""
import json
import os
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler


def get_supabase():
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not url or not key:
        return None
    from supabase import create_client
    return create_client(url, key)


def send_email(to_email, subject, html_body):
    import urllib.request
    import urllib.error
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        raise RuntimeError("RESEND_API_KEY not set")
    from_addr = os.environ.get("EMAIL_FROM", "Signal <noreply@signal-au.com>")
    payload = json.dumps({
        "from": from_addr,
        "to": [to_email],
        "subject": subject,
        "html": html_body,
    }).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Resend {e.code}: {body}")


def build_reminder_html(day_number, user_name=""):
    greeting = f"Hey{' ' + user_name if user_name else ''}"
    app_url = os.environ.get("APP_URL", "https://signal-au.com")

    encouragement = {
        1: "You signed up — now let's make it count. Your first check-in takes 2 minutes and sets the baseline for everything Signal does for you.",
        2: "Day 2 — patterns start forming. Keep building the data.",
        3: "You're almost halfway. The more data, the sharper the insights.",
        4: "Day 4! Consistency is where Signal gets powerful.",
        5: "Over the halfway mark. Your weekly report is taking shape.",
        6: "One more day until your full weekly report unlocks.",
        7: "Final day of the trial! Complete today to unlock your weekly pattern report.",
    }
    msg = encouragement.get(day_number, "Keep the streak going — your data is building something useful.")

    cta_text = "Start your first check-in" if day_number == 1 else "Log today's check-in"
    subject_line = "Welcome to Signal — start your first check-in" if day_number == 1 else None

    what_to_expect = ""
    if day_number == 1:
        what_to_expect = """
      <div style="margin:20px 0 0 0;padding:16px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);border-radius:10px;">
        <p style="color:#a3a3a3;font-size:12px;line-height:1.6;margin:0;">
          <span style="color:#e5e5e5;font-weight:500;">Here's how it works:</span><br>
          Log 3 things daily — sleep, energy, and a quick reflection.<br>
          Signal spots patterns you can't see yourself.<br>
          After 7 days, you unlock your full weekly performance report.
        </p>
      </div>"""

    return f"""
<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#050505;font-family:'Inter',system-ui,-apple-system,sans-serif;">
  <div style="max-width:480px;margin:0 auto;padding:40px 24px;">
    <div style="text-align:center;margin-bottom:32px;">
      <div style="display:inline-block;width:32px;height:32px;background:white;border-radius:50%;line-height:32px;">
        <div style="display:inline-block;width:10px;height:10px;background:black;border-radius:50%;vertical-align:middle;"></div>
      </div>
      <span style="color:white;font-size:13px;font-weight:500;letter-spacing:-0.01em;margin-left:8px;vertical-align:middle;">SIGNAL</span>
    </div>

    <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:16px;padding:32px 24px;">
      <p style="color:#e5e5e5;font-size:15px;margin:0 0 6px 0;">{greeting},</p>
      <p style="color:#a3a3a3;font-size:14px;line-height:1.6;margin:0 0 20px 0;">
        {msg}
      </p>{what_to_expect}
      <p style="color:#737373;font-size:12px;margin:0 0 24px 0;">
        Day {day_number} of 7 &nbsp;·&nbsp; {'🟢' * min(day_number - 1, 7)}{'⚫' * max(0, 7 - day_number + 1)}
      </p>
      <div style="text-align:center;">
        <a href="{app_url}/checkin" style="display:inline-block;background:white;color:black;font-size:13px;font-weight:500;padding:10px 28px;border-radius:999px;text-decoration:none;">
          {cta_text}
        </a>
      </div>
    </div>

    <p style="color:#525252;font-size:11px;text-align:center;margin-top:24px;">
      You're receiving this because you signed up for Signal's 7-day trial.
    </p>
  </div>
</body>
</html>
"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        cron_secret = os.environ.get("CRON_SECRET", "")
        auth = self.headers.get("Authorization", "")
        if cron_secret and auth != f"Bearer {cron_secret}":
            self._send(401, {"error": "Unauthorized"})
            return

        supabase = get_supabase()
        if not supabase:
            self._send(503, {"error": "Server not configured"})
            return

        if not os.environ.get("RESEND_API_KEY"):
            self._send(503, {"error": "RESEND_API_KEY not set"})
            return

        today = date.today().isoformat()

        try:
            users_resp = supabase.auth.admin.list_users()
            users = users_resp if isinstance(users_resp, list) else getattr(users_resp, 'users', [])
        except Exception as e:
            self._send(500, {"error": f"Failed to list users: {e}"})
            return

        sent = 0
        skipped = 0
        errors = []

        for user in users:
            user_id = user.id if hasattr(user, 'id') else user.get('id')
            email = user.email if hasattr(user, 'email') else user.get('email')
            if not user_id or not email:
                continue

            created_at = user.created_at if hasattr(user, 'created_at') else user.get('created_at', '')
            created_str = str(created_at)[:10] if created_at else ''

            try:
                result = supabase.table("entries").select("id, date").eq(
                    "user_id", user_id
                ).order("date", desc=True).limit(30).execute()
                entries = result.data or []
            except Exception:
                entries = []

            already_today = any(e.get("date") == today for e in entries)
            if already_today:
                skipped += 1
                continue

            unique_dates = set(e.get("date") for e in entries if e.get("date"))
            day_number = len(unique_dates) + 1

            if day_number > 7:
                skipped += 1
                continue

            user_name = ""
            meta = user.user_metadata if hasattr(user, 'user_metadata') else user.get('user_metadata', {})
            if meta:
                user_name = meta.get("full_name", "") or meta.get("name", "")
                if user_name:
                    user_name = user_name.split()[0]

            try:
                if day_number == 1:
                    subject = "Welcome to Signal — start your first check-in"
                else:
                    subject = f"Day {day_number}/7 — Time for your check-in"
                html = build_reminder_html(day_number, user_name)
                send_email(email, subject, html)
                sent += 1
            except Exception as e:
                errors.append(f"{email}: {e}")

        self._send(200, {
            "ok": True,
            "sent": sent,
            "skipped": skipped,
            "errors": errors[:10],
        })

    def _send(self, status, body):
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))
