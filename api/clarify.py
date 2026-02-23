"""
Vercel serverless: POST /api/clarify — GPT clarifying questions as user types.
Requires: OPENAI_API_KEY
"""
import json
import os
from http.server import BaseHTTPRequestHandler

OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")


def clarify_with_gpt(text: str) -> list:
    """Return 1-2 short clarifying questions based on partial reflection."""
    if not text or len(text.strip()) < 15:
        return []
    if not OPENAI_KEY:
        return []
    try:
        import openai
        client = openai.OpenAI(api_key=OPENAI_KEY)
        prompt = f"""You are Signal, a performance pattern detection engine. You detect factors impacting productivity. You do NOT provide therapy. NEVER ask about feelings, emotions, relationships, or personal life.

User's reflection so far:

"{text[:500]}"

Generate 1-2 clarifying questions about PERFORMANCE ONLY. Ask ONLY about: sleep, energy, focus, work output, what blocked them.

BAD (therapeutic - never do this): "What's causing you to feel blue?", "Can you share more about your relationship?", "What do you think is missing?"
GOOD (performance): "How did that affect your energy for work today?", "What got in the way of your focus?", "How did your sleep factor in?"

Return JSON array only: ["question1?", "question2?"]."""
        r = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], temperature=0.4)
        raw = r.choices[0].message.content.strip()
        if raw.startswith("```"): raw = raw.split("```")[1].replace("json", "").strip()
        out = json.loads(raw)
        return out if isinstance(out, list) else []
    except Exception:
        return []


def _fallback_clarify(text: str) -> list:
    t = text.lower()
    questions = []
    if any(w in t for w in ["blue", "down", "bothered", "sad", "don't feel", "dont feel"]):
        questions.append("How did that affect your energy for work today?")
    if any(w in t for w in ["unproductive", "unfocused", "wasted", "sat the whole day"]):
        questions.append("What got in the way of feeling productive today?")
    if any(w in t for w in ["tired", "exhausted", "drained"]):
        questions.append("How did you sleep last night?")
    if any(w in t for w in ["unsure", "confused", "bored", "unmotivated", "not sure"]):
        questions.append("What did you attempt today that mattered to you?")
    if any(w in t for w in ["fight", "argument", "conflict", "bf", "boyfriend", "girlfriend"]):
        questions.append("How did that affect your energy for work today?")
    if any(w in t for w in ["stress", "anxious", "overwhelmed", "stuck"]):
        questions.append("What got in the way of your focus?")
    if any(w in t for w in ["sleep", "slept", "rest", "woke", "wake"]):
        questions.append("What might have affected your sleep quality?")
    if not questions:
        questions.append("What got in the way of your best work today?")
    return questions[:2]


def _clarify_response(text: str) -> tuple:
    """Return (questions, source, error)."""
    if len(text) < 15:
        return [], "none", None
    if not OPENAI_KEY:
        return _fallback_clarify(text), "fallback", "OPENAI_API_KEY not set"
    try:
        q = clarify_with_gpt(text)
        return (q, "gpt", None) if q else (_fallback_clarify(text), "fallback", None)
    except Exception as e:
        return _fallback_clarify(text), "fallback", str(e)


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
            self._send(400, {"questions": []})
            return
        text = (data.get("text") or "").strip()
        questions, source, err = _clarify_response(text)
        self._send(200, {"questions": questions, "source": source, "error": err or None})

    def _send(self, status, body):
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))
