"""
Vercel serverless: POST /api/analyze — GPT daily analysis, stores entry in Supabase.
Requires: OPENAI_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""
import json
import os
import re
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


def analyze_with_gpt(transcript: str, sleep_hours: float, sleep_quality: int, energy: int, deep_work: int, api_key: str = None) -> dict:
    """Call GPT to generate structured output. Returns dict with reflection_summary, likely_drivers, predicted_impact, experiment_for_tomorrow."""
    key = (api_key or OPENAI_KEY or "").strip()
    if not key:
        return {
            "reflection_summary": transcript[:200] + ("..." if len(transcript) > 200 else ""),
            "likely_drivers": ["Analysis pending"],
            "predicted_impact": "—",
            "experiment_for_tomorrow": "—",
            "_error": "OPENAI_API_KEY not set in .env",
        }
    try:
        import openai
        client = openai.OpenAI(api_key=key)
        prompt = f"""You are "Signal", a cognitive performance analysis engine. Your job is to generate a daily reflection grounded in behavioral science, cognitive psychology, and neuroscience.

INPUTS:
- Sleep hours: {sleep_hours}
- Sleep quality (1–5): {sleep_quality}
- Energy (1–5): {energy}
- Deep work blocks completed: {deep_work}
- Optional notes: {transcript[:2000]}

RULES:
1. Use evidence-based mechanisms only. Allowed domains: sleep restriction & executive function, working memory limits, cognitive load theory, attentional residue (Leroy, 2009), implementation intentions (Gollwitzer), habit loops (cue–routine–reward), dopamine & task initiation, stress arousal (Yerkes–Dodson), decision fatigue research, task switching costs.
2. DO NOT invent study titles, journals, or specific years unless highly certain. Prefer "Research on sleep restriction shows...", "Cognitive load theory suggests...".
3. Every section MUST reference at least one observable behavioral signal from today (e.g., delayed start, resistance before deep work, choice of admin tasks over deep work). If no behavioral evidence is present in the inputs, state "Insufficient data" for that section instead of guessing.
4. BAN single-word drivers. Each driver MUST include a mechanism explanation (2-3 sentences). Never output drivers like "Sleep" or "Stress" alone.
5. Write like a diagnostic performance report, not a self-help blog.
6. Tone: Analytical. Precise. Non-emotional. No hype. No moralising. No fluff.

Return valid JSON only. No markdown. Structure:
{{
  "reflection_summary": "100-150 words. Must cite observable behaviors from today. If no behavioral evidence: 'Insufficient data'.",
  "core_bottleneck": "One sentence citing today's behavioral signal. If no evidence: 'Insufficient data'.",
  "likely_drivers": ["Each driver: full mechanism explanation (2-3 sentences) + why it applies to today's observable behavior. No single-word drivers. If no evidence: return ['Insufficient data']."],
  "predicted_impact": "How today's observed pattern affects focus, task initiation, mood stability, avoidance risk. Cite behavioral evidence. If none: 'Insufficient data'.",
  "experiment_for_tomorrow": "ONE experiment tied to today's behavioral signal. Include: Trigger, Protocol, Measurement, Mechanism, Failure mode. If no behavioral evidence: 'Insufficient data'.",
  "micro_interventions": ["Up to 3 tiny 2-5 min actions that support the main experiment. If insufficient data: []"]
}}"""
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2500,
        )
        text = (r.choices[0].message.content or "").strip()
        if not text:
            raise ValueError("Empty response from GPT")
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.lower().startswith("json"):
                text = text[4:]
            text = text.strip()
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            text = text[start:end]
        # Fix common JSON issues: trailing commas
        text = re.sub(r",\s*}", "}", text)
        text = re.sub(r",\s*]", "]", text)
        data = json.loads(text)
        # Ensure required keys exist
        data.setdefault("reflection_summary", "")
        data.setdefault("likely_drivers", [])
        data.setdefault("predicted_impact", "")
        data.setdefault("experiment_for_tomorrow", "")

        # Normalize fields that GPT may return as dicts instead of strings
        for str_field in ("reflection_summary", "predicted_impact", "experiment_for_tomorrow", "core_bottleneck"):
            val = data.get(str_field)
            if isinstance(val, dict):
                data[str_field] = "\n".join(f"{k}: {v}" for k, v in val.items())

        # Normalize likely_drivers: GPT may return list of dicts instead of strings
        drivers = data.get("likely_drivers", [])
        if isinstance(drivers, list):
            normalized = []
            for d in drivers:
                if isinstance(d, dict):
                    normalized.append(" — ".join(f"{k}: {v}" for k, v in d.items()))
                else:
                    normalized.append(str(d))
            data["likely_drivers"] = normalized

        # Merge core_bottleneck into reflection_summary for display
        core = data.get("core_bottleneck", "")
        summary = data.get("reflection_summary", "")
        if core:
            data["reflection_summary"] = f"Core bottleneck: {core}\n\n{summary}"

        # Append micro_interventions to experiment
        micro = data.get("micro_interventions") or []
        if isinstance(micro, list):
            micro = [str(m) if not isinstance(m, str) else m for m in micro]
        exp = data.get("experiment_for_tomorrow", "")
        if micro:
            exp += "\n\nMicro-interventions:\n" + "\n".join(f"• {m}" for m in micro[:3])
            data["experiment_for_tomorrow"] = exp
        return data
    except Exception as e:
        import sys
        err_msg = f"{type(e).__name__}: {str(e)}"
        print("[analyze] GPT failed:", err_msg, file=sys.stderr)
        # Retry with minimal prompt (create fresh client in case first failed early)
        try:
            import openai as _openai
            _client = _openai.OpenAI(api_key=key)
            simple_prompt = f"""Based on: Sleep {sleep_hours}h, quality {sleep_quality}/5, energy {energy}/5, deep work {deep_work} blocks. Notes: {transcript[:500]}

Return JSON only:
{{"reflection_summary": "2-3 sentence summary of performance factors", "core_bottleneck": "one sentence", "likely_drivers": ["driver 1", "driver 2"], "predicted_impact": "1-2 sentences", "experiment_for_tomorrow": "one concrete experiment", "micro_interventions": []}}"""
            r2 = _client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": simple_prompt}], temperature=0.2, max_tokens=800)
            text = (r2.choices[0].message.content or "").strip()
            start, end = text.find("{"), text.rfind("}") + 1
            if start >= 0 and end > start:
                text = text[start:end]
            text = re.sub(r",\s*}", "}", re.sub(r",\s*]", "]", text))
            data = json.loads(text)
            data.setdefault("reflection_summary", "")
            data.setdefault("likely_drivers", [])
            data.setdefault("predicted_impact", "")
            data.setdefault("experiment_for_tomorrow", "")
            core = data.get("core_bottleneck", "")
            if core:
                data["reflection_summary"] = f"Core bottleneck: {core}\n\n{data.get('reflection_summary', '')}"
            return data
        except Exception as e2:
            print("[analyze] Retry also failed:", str(e2), file=sys.stderr)
        return {
            "reflection_summary": transcript[:200] or "No reflection provided.",
            "likely_drivers": ["Analysis pending"],
            "predicted_impact": "—",
            "experiment_for_tomorrow": "—",
            "_error": err_msg,
        }


class handler(BaseHTTPRequestHandler):
    def _get_user_id(self):
        from api.security import get_user_id
        return get_user_id(self.headers.get("Authorization", ""))

    def do_POST(self):
        user_id = self._get_user_id()
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

        supabase = get_supabase()
        if not supabase:
            self._send(503, {"error": "Server not configured"})
            return

        from api.security import sanitize_text, clamp_float, clamp_int, validate_date, encrypt

        transcript = sanitize_text(data.get("transcript", "") or "", max_length=5000)
        sleep_hours = clamp_float(data.get("sleep_hours", 0), 0, 24, default=0)
        sleep_quality = clamp_int(data.get("sleep_quality", 3), 1, 5, default=3)
        energy = clamp_int(data.get("energy", 3), 1, 5, default=3)
        deep_work = clamp_int(data.get("deep_work_blocks", 0), 0, 5, default=0)
        entry_date = validate_date(data.get("date", ""))
        if not entry_date:
            self._send(400, {"error": "Valid date required (YYYY-MM-DD)"})
            return

        if not data.get("skip_missing_check") and not data.get("overwrite"):
            missing = check_missing_answer(transcript, sleep_hours, sleep_quality, energy, deep_work)
            if missing:
                self._send(200, {"needs_answer": missing})
                return

        result = analyze_with_gpt(transcript, sleep_hours, sleep_quality, energy, deep_work)

        if result.get("likely_drivers") == ["Analysis pending"]:
            self._send(503, {"error": "Analysis failed. Add OPENAI_API_KEY to Vercel Environment Variables (Settings → Environment Variables) and redeploy."})
            return

        is_follow_up = data.get("is_follow_up") is True
        existing = supabase.table("entries").select("id, entry_number, sleep_hours, sleep_quality, energy, deep_work_blocks").eq(
            "user_id", user_id).eq("date", entry_date).order("entry_number", desc=True).execute()
        existing_entries = existing.data or []
        next_number = (existing_entries[0]["entry_number"] + 1) if existing_entries else 1

        if is_follow_up and existing_entries:
            first = existing_entries[-1]
            sleep_hours = first.get("sleep_hours") or sleep_hours
            sleep_quality = first.get("sleep_quality") or sleep_quality
            energy = first.get("energy") or energy
            deep_work = first.get("deep_work_blocks") or deep_work

        row = {
            "user_id": user_id,
            "date": entry_date,
            "entry_number": next_number,
            "is_follow_up": is_follow_up and next_number > 1,
            "sleep_hours": sleep_hours,
            "sleep_quality": sleep_quality,
            "energy": energy,
            "deep_work_blocks": deep_work,
            "transcript": encrypt(transcript),
            "reflection_summary": encrypt(result.get("reflection_summary", "")),
            "likely_drivers": result.get("likely_drivers", []),
            "predicted_impact": result.get("predicted_impact", ""),
            "experiment_for_tomorrow": result.get("experiment_for_tomorrow", ""),
        }

        try:
            r = supabase.table("entries").insert(row).execute()
            entry_id = r.data[0]["id"] if r.data else None
            self._send(200, {"entry_id": str(entry_id), "entry_number": next_number})
        except Exception as e:
            self._send(500, {"error": str(e)})

    def _send(self, status, body):
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))
