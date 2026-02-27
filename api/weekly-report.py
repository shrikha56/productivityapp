"""
Vercel serverless: POST /api/weekly-report — GPT weekly synthesis from 7+ entries.
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


def build_entries_digest(entries: list) -> str:
    lines = []
    for e in entries:
        drivers = e.get("likely_drivers") or []
        if isinstance(drivers, list):
            drivers = "; ".join(str(d) for d in drivers)
        lines.append(
            f"Date: {e.get('date')} | Sleep: {e.get('sleep_hours')}h (quality {e.get('sleep_quality')}/5) | "
            f"Energy: {e.get('energy')}/5 | Deep work: {e.get('deep_work_blocks')} blocks\n"
            f"Summary: {(e.get('reflection_summary') or '—')[:300]}\n"
            f"Drivers: {drivers[:200]}\n"
            f"Experiment: {(e.get('experiment_for_tomorrow') or '—')[:150]}"
        )
    return "\n---\n".join(lines)


def generate_weekly_report(entries: list, api_key: str = None) -> dict:
    key = (api_key or OPENAI_KEY or "").strip()
    if not key:
        return {"error": "OPENAI_API_KEY not set"}

    digest = build_entries_digest(entries)
    n = len(entries)
    avg_sleep = round(sum(e.get("sleep_hours", 0) or 0 for e in entries) / n, 1)
    avg_quality = round(sum(e.get("sleep_quality", 3) or 3 for e in entries) / n, 1)
    avg_energy = round(sum(e.get("energy", 3) or 3 for e in entries) / n, 1)
    total_blocks = sum(e.get("deep_work_blocks", 0) or 0 for e in entries)

    prompt = f"""You are "Signal", a cognitive performance analysis engine. Synthesize {n} daily reflections into a weekly performance report.

WEEKLY DATA:
- Entries: {n} days
- Avg sleep: {avg_sleep}h | Avg quality: {avg_quality}/5 | Avg energy: {avg_energy}/5
- Total deep work blocks: {total_blocks}

DAILY ENTRIES:
{digest[:6000]}

RULES:
1. QUANTIFY everything. Never say "sleep impacted productivity." Instead: "When sleep quality was ≥4/5, deep work output doubled (2 blocks vs 0–1 on low-sleep days)." Cite exact numbers and thresholds.
2. Identify RECURRING themes — what appeared 2+ times. Cite specific dates (e.g., Feb 19, 22).
3. Avoid obvious statements. Go beyond "sleep affects energy." Show the causal chain with numbers.
4. Tone: Analytical, precise, non-emotional. Signal must feel like insight, not generic advice.
5. For each pattern, assign confidence: Strong correlation (clear cause→effect across 3+ days), Moderate (2 days or partial), Emerging (1–2 instances, worth watching).

Return valid JSON only. No markdown. Structure:
{{
  "week_narrative": "3-5 sentence overview. Cite specific dates and inflection points. Include recovery lag if visible (e.g., 'Sleep deprivation showed a 24-hour recovery window before output normalized').",
  "metrics": {{
    "avg_sleep": {avg_sleep},
    "avg_sleep_quality": {avg_quality},
    "avg_energy": {avg_energy},
    "total_deep_work": {total_blocks},
    "entries_count": {n}
  }},
  "recurring_patterns": [
    "[Strong correlation] When sleep quality ≥4/5, deep work doubled (2 blocks vs 0–1). Feb 19, 22.",
    "[Moderate correlation] Phone restriction → output. Evidence: Feb 19, 22.",
    "[Emerging] Post-lunch crashes on Feb 18, 20 — worth tracking."
  ],
  "recovery_lag": "Optional: How long did poor sleep/stress affect output? e.g., '24-hour recovery window' or '48-hour lag before energy normalized'. Omit if not discernible.",
  "top_derailers": [
    "Derailer with numbers: e.g., 'Sleep <6h on Feb 17, 20 → 0 deep work blocks both days vs 2 blocks when ≥7h'",
    "Second derailer with specific days and quantified impact"
  ],
  "bright_spots": [
    "Quantified: e.g., 'Feb 22: 7.5h sleep, 4/5 quality → 2 deep work blocks, highest energy day'"
  ],
  "weekly_experiment": {{
    "focus": "The ONE thing to focus on based on strongest quantified pattern",
    "protocol": "Specific daily action with timing and measurement",
    "mechanism": "Why this targets the root cause",
    "success_metric": "Quantified: e.g., '4/5 sleep quality on 5 of 7 days' or '2+ deep work blocks on 4 days'"
  }},
  "micro_shifts": [
    "2-3 small daily adjustments that support the main experiment"
  ]
}}"""

    try:
        import openai
        client = openai.OpenAI(api_key=key)
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=3000,
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
        text = re.sub(r",\s*}", "}", text)
        text = re.sub(r",\s*]", "]", text)
        data = json.loads(text)

        # Normalize any dict fields to strings
        for field in ("week_narrative",):
            if isinstance(data.get(field), dict):
                data[field] = "\n".join(f"{k}: {v}" for k, v in data[field].items())

        for list_field in ("recurring_patterns", "top_derailers", "bright_spots", "micro_shifts"):
            items = data.get(list_field, [])
            if isinstance(items, list):
                data[list_field] = [
                    " — ".join(f"{k}: {v}" for k, v in d.items()) if isinstance(d, dict) else str(d)
                    for d in items
                ]

        exp = data.get("weekly_experiment")
        if isinstance(exp, dict):
            data["weekly_experiment"] = exp
        elif isinstance(exp, str):
            data["weekly_experiment"] = {"focus": exp, "protocol": "", "mechanism": "", "success_metric": ""}

        data.setdefault("metrics", {
            "avg_sleep": avg_sleep,
            "avg_sleep_quality": avg_quality,
            "avg_energy": avg_energy,
            "total_deep_work": total_blocks,
            "entries_count": n,
        })

        return data
    except Exception as e:
        import sys
        print(f"[weekly-report] GPT failed: {type(e).__name__}: {e}", file=sys.stderr)
        return {
            "error": f"Report generation failed: {type(e).__name__}: {e}",
            "metrics": {
                "avg_sleep": avg_sleep,
                "avg_sleep_quality": avg_quality,
                "avg_energy": avg_energy,
                "total_deep_work": total_blocks,
                "entries_count": n,
            },
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

        result = supabase.table("entries").select("*").eq("user_id", user_id).order("date", desc=True).limit(30).execute()
        entries = result.data or []

        from api.security import decrypt
        for entry in entries:
            entry["transcript"] = decrypt(entry.get("transcript") or "")
            entry["reflection_summary"] = decrypt(entry.get("reflection_summary") or "")
            entry["predicted_impact"] = decrypt(entry.get("predicted_impact") or "")
            entry["experiment_for_tomorrow"] = decrypt(entry.get("experiment_for_tomorrow") or "")
            entry["likely_drivers"] = [decrypt(d) for d in (entry.get("likely_drivers") or [])]

        unique_dates = set(e.get("date") for e in entries if e.get("date"))
        entries_count = len(unique_dates)
        if entries_count < 7:
            self._send(200, {"locked": True, "entries_count": entries_count, "needed": 7})
            return

        report = generate_weekly_report(entries[:14], api_key=OPENAI_KEY)
        if report.get("error") and not report.get("week_narrative"):
            self._send(503, report)
            return

        by_date = {}
        for e in entries[:14]:
            d = e.get("date")
            if d and (d not in by_date or e.get("entry_number") == 1):
                by_date[d] = e
        report["entries"] = [by_date[d] for d in sorted(by_date.keys())]
        self._send(200, report)

    def _send(self, status, body):
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))
