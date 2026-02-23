"""
Vercel serverless: POST /api/analyze — GPT daily analysis, stores entry in Supabase.
Requires: OPENAI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""
import json
import os
from http.server import BaseHTTPRequestHandler

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_ANON_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")


def get_supabase():
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    from supabase import create_client
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def check_missing_answer(transcript: str, sleep_hours: float, sleep_quality: int, energy: int, deep_work: int) -> str | None:
    """If a critical performance question is unanswered, return it. Otherwise return None."""
    t = (transcript or "").strip()
    if not t or len(t) < 10:
        return None
    # Short reflections (< 80 chars) always need more — skip GPT, prompt directly
    if len(t) < 80:
        t_lower = t.lower()
        has_energy = any(w in t_lower for w in ["energy", "tired", "drained", "focused", "focus", "productive", "work", "deep work"])
        if not has_energy:
            return "How was your energy and focus today?"
    if not OPENAI_KEY:
        return None
    try:
        import openai
        client = openai.OpenAI(api_key=OPENAI_KEY)
        prompt = f"""You are Signal, a performance pattern detection engine. Anchors: sleep {sleep_hours}h, quality {sleep_quality}/5, energy {energy}/5, deep work {deep_work}.

Reflection: {transcript[:800]}

Is there ONE critical performance question (sleep, energy, focus, work output) that would significantly improve the analysis if the user answered it? Focus on PERFORMANCE only.
- If reflection is very short or only mentions sleep, ask about energy or focus (e.g. "How was your energy and focus today?")
- If reflection is detailed enough, return: NONE

If yes, return exactly one short question ending with ?
If no, return: NONE"""
        r = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], temperature=0.2, max_tokens=80)
        full = (r.choices[0].message.content or "").strip()
        if not full or full.upper() == "NONE":
            return None
        if full.endswith("?"):
            return full
        return None
    except Exception:
        return None


def analyze_with_gpt(transcript: str, sleep_hours: float, sleep_quality: int, energy: int, deep_work: int) -> dict:
    """Call GPT to generate structured output. Returns dict with reflection_summary, likely_drivers, predicted_impact, experiment_for_tomorrow."""
    if not OPENAI_KEY:
        return {
            "reflection_summary": transcript[:200] + ("..." if len(transcript) > 200 else ""),
            "likely_drivers": ["Sleep debt", "Cognitive load"],
            "predicted_impact": "Reduced focus for 24h",
            "experiment_for_tomorrow": "25 min deep work before any meetings",
        }
    try:
        import openai
        client = openai.OpenAI(api_key=OPENAI_KEY)
        prompt = f"""You are Signal, a performance pattern detection engine. You analyze daily reflections and detect factors impacting productivity. You do NOT provide therapy advice. You focus strictly on performance drivers.

Anchors: sleep {sleep_hours}h, quality {sleep_quality}/5, energy {energy}/5, deep work blocks {deep_work}.

Reflection: {transcript[:1500]}

Return JSON only. Focus on performance drivers (sleep, energy, focus, blockers), not emotional or relationship advice:
{{"reflection_summary": "1-2 sentence summary of performance-relevant factors", "likely_drivers": ["driver1", "driver2"], "predicted_impact": "impact on next 24-48h performance", "experiment_for_tomorrow": "one small performance experiment"}}"""
        r = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], temperature=0.3)
        text = r.choices[0].message.content.strip()
        if text.startswith("```"): text = text.split("```")[1].replace("json", "").strip()
        return json.loads(text)
    except Exception as e:
        return {
            "reflection_summary": transcript[:200] or "No reflection provided.",
            "likely_drivers": ["Analysis pending"],
            "predicted_impact": "—",
            "experiment_for_tomorrow": "—",
        }


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(content_len).decode("utf-8") if content_len else "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            self._send(400, {"error": "Invalid JSON"})
            return

        user_id = data.get("user_id")
        if not user_id:
            self._send(400, {"error": "user_id required"})
            return

        supabase = get_supabase()
        if not supabase:
            self._send(503, {"error": "Server not configured"})
            return

        transcript = data.get("transcript", "") or ""
        sleep_hours = float(data.get("sleep_hours", 0))
        sleep_quality = int(data.get("sleep_quality", 3))
        energy = int(data.get("energy", 3))
        deep_work = int(data.get("deep_work_blocks", 0))

        if not data.get("skip_missing_check") and not data.get("overwrite"):
            missing = check_missing_answer(transcript, sleep_hours, sleep_quality, energy, deep_work)
            if missing:
                self._send(200, {"needs_answer": missing})
                return

        result = analyze_with_gpt(transcript, sleep_hours, sleep_quality, energy, deep_work)

        row = {
            "user_id": user_id,
            "date": data.get("date"),
            "sleep_hours": data.get("sleep_hours"),
            "sleep_quality": data.get("sleep_quality"),
            "energy": data.get("energy"),
            "deep_work_blocks": data.get("deep_work_blocks"),
            "transcript": data.get("transcript"),
            "reflection_summary": result.get("reflection_summary"),
            "likely_drivers": result.get("likely_drivers", []),
            "predicted_impact": result.get("predicted_impact"),
            "experiment_for_tomorrow": result.get("experiment_for_tomorrow"),
        }

        overwrite = data.get("overwrite") is True
        existing = supabase.table("entries").select("id").eq("user_id", user_id).eq("date", row["date"]).limit(1).execute()

        if existing.data and len(existing.data) > 0:
            if overwrite:
                entry_id = existing.data[0]["id"]
                update_row = {k: v for k, v in row.items() if k not in ("user_id", "date")}
                supabase.table("entries").update(update_row).eq("id", entry_id).execute()
                self._send(200, {"entry_id": str(entry_id)})
            else:
                self._send(400, {"error": "Entry for this date already exists", "entry_id": str(existing.data[0]["id"])})
            return

        try:
            r = supabase.table("entries").insert(row).execute()
            entry_id = r.data[0]["id"] if r.data else None
            self._send(200, {"entry_id": str(entry_id)})
        except Exception as e:
            self._send(500, {"error": str(e)})

    def _send(self, status, body):
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))
