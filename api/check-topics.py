"""
Vercel serverless: POST /api/check-topics — GPT checks which reflection questions are missing.
Requires: OPENAI_API_KEY
"""
import json
import os
import re
from http.server import BaseHTTPRequestHandler

OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")


def _fallback_check_topics(text: str) -> list:
    t = text.lower()
    missing = []
    if not re.search(r"\b(sleep|slept|rest|woke|nap|bed|insomnia|alright|well|hours?|asleep|restorative|restless)\b", t):
        missing.append("How did you sleep?")
    if not re.search(r"\b(feel|felt|feeling|energy|mood|stressed|anxious|happy|sad|tired|exhausted|drained|bothered|down|low|great|calm|relaxed|motivated|restless|groggy|heavy)\b", t) and not re.search(r"(feel|i'm|im)\s+(okay|fine|good|bad)", t):
        missing.append("What are you feeling?")
    if not re.search(r"\b(work|worked|attempt|tried|did|task|project|focus|study|meeting|class|productive|unproductive|nothing|read|exercise|chilled)\b", t):
        missing.append("What did you attempt?")
    return missing


def check_topics_with_gpt(text: str) -> list:
    if not OPENAI_KEY or len(text.strip()) < 5:
        return ["How did you sleep?", "What are you feeling?", "What did you attempt?"] if len(text.strip()) < 5 else []
    try:
        import openai
        client = openai.OpenAI(api_key=OPENAI_KEY)
        prompt = f"""A user's daily reflection must meaningfully address 3 topics. A vague mention is NOT enough — they need to provide real detail.

TOPIC 1 — "How did you sleep?"
ADDRESSED: they give AT LEAST TWO specifics: duration, quality description, disruptions, bedtime, or how they woke up.
"slept 7 hours, woke up twice" → ADDRESSED (duration + disruption)
"went to bed at 11, woke up groggy" → ADDRESSED (bedtime + wake quality)
"slept okay" → NOT ADDRESSED (only one vague word)
"slept fine today" → NOT ADDRESSED (no real detail)
"i slept alright" → NOT ADDRESSED (too vague)

TOPIC 2 — "What are you feeling?"
ADDRESSED: they describe their current emotional state, mood, or energy level for the day.
"I feel low today", "my energy is drained", "I'm stressed" → ADDRESSED
"felt groggy waking up", "felt restless at night" → NOT ADDRESSED (describes sleep, not current feeling)
"okay" or "fine" without context → NOT ADDRESSED (too vague)

TOPIC 3 — "What did you attempt?"
ADDRESSED: they describe what they worked on, tried, or did during the day (or said they did nothing).
"worked on my project", "did nothing today", "went to class" → ADDRESSED
No mention of any activity → NOT ADDRESSED

Reflection: "{text[:1200]}"

Return JSON array of MISSING topics. Use exact strings:
["How did you sleep?", "What are you feeling?", "What did you attempt?"]
Return [] only if ALL three are meaningfully addressed with detail."""
        r = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], temperature=0.1, max_tokens=100)
        raw = (r.choices[0].message.content or "").strip()
        if raw.startswith("```"): raw = raw.split("```")[1].replace("json", "").strip()
        out = json.loads(raw)
        missing = [q for q in out if isinstance(q, str) and q in ("How did you sleep?", "What are you feeling?", "What did you attempt?")]
        return missing
    except Exception:
        return _fallback_check_topics(text)


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(content_len).decode("utf-8") if content_len else "{}"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            self._send(400, {"missing": ["How did you sleep?", "What are you feeling?", "What did you attempt?"]})
            return
        text = (data.get("text") or "").strip()
        missing = check_topics_with_gpt(text)
        self._send(200, {"missing": missing})

    def _send(self, status, body):
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))
