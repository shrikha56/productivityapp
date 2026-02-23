"""
Signal local dev server: serves all pages + API routes.
Set env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_ANON_KEY), OPENAI_API_KEY (optional).
Run: python server.py  →  http://127.0.0.1:5000/
"""
import json
import os
import re
import tempfile

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from flask import Flask, request, jsonify, send_from_directory, Response

# Import API logic from Vercel functions
from api.analyze import get_supabase, analyze_with_gpt

app = Flask(__name__, static_folder=".", static_url_path="")

SUPABASE_URL = os.environ.get("SUPABASE_URL") or os.environ.get("EXPO_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_ANON_KEY")
    or os.environ.get("EXPO_PUBLIC_SUPABASE_KEY", "")
)
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")


# --- Page routes ---

@app.route("/")
def index():
    return send_from_directory(".", "index.html")


@app.route("/signup")
def signup():
    return send_from_directory(".", "signup.html")


@app.route("/login")
def login():
    return send_from_directory(".", "login.html")


@app.route("/checkin")
def checkin():
    return send_from_directory(".", "checkin.html")


@app.route("/entry")
def entry():
    return send_from_directory(".", "entry.html")


@app.route("/history")
def history():
    return send_from_directory(".", "history.html")


@app.route("/report/weekly")
def report():
    return send_from_directory(".", "report.html")


@app.route("/auth/callback")
def auth_callback():
    return send_from_directory(".", "auth-callback.html")


@app.route("/auth-callback")
def auth_callback_alt():
    """Alias for OAuth configs that use /auth-callback."""
    return send_from_directory(".", "auth-callback.html")


@app.route("/report")
def report_page():
    return send_from_directory(".", "report.html")


# --- API routes ---

@app.route("/api/join", methods=["POST"])
def join():
    data = request.get_json(force=True, silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "Valid email required"}), 400

    supabase = get_supabase()
    if not supabase:
        return jsonify({"ok": False, "error": "Server not configured"}), 503

    try:
        supabase.table("signups").insert({"email": email}).execute()
        return jsonify({"ok": True, "message": "You're on the list. We'll be in touch."})
    except Exception as e:
        err = str(e).lower()
        if "duplicate" in err or "unique" in err or "already" in err:
            return jsonify({"ok": True, "message": "You're already on the list."})
        print("[api/join error]", type(e).__name__, str(e))
        return jsonify({"ok": False, "error": "Something went wrong"}), 500


@app.route("/api/analyze", methods=["POST"])
def analyze():
    data = request.get_json(force=True, silent=True) or {}
    user_id = data.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id required"}), 400

    supabase = get_supabase()
    if not supabase:
        return jsonify({"error": "Server not configured"}), 503

    transcript = data.get("transcript", "") or ""
    sleep_hours = float(data.get("sleep_hours", 0))
    sleep_quality = int(data.get("sleep_quality", 3))
    energy = int(data.get("energy", 3))
    deep_work = int(data.get("deep_work_blocks", 0))

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
            return jsonify({"entry_id": str(entry_id)})
        return jsonify({"error": "Entry for this date already exists", "entry_id": str(existing.data[0]["id"])}), 400

    try:
        r = supabase.table("entries").insert(row).execute()
        entry_id = r.data[0]["id"] if r.data else None
        return jsonify({"entry_id": str(entry_id)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


def _fallback_clarify(text: str) -> list:
    """Return simple clarifying questions when GPT is not available."""
    t = text.lower()
    questions = []
    if any(w in t for w in ["tired", "exhausted", "drained", "low energy"]):
        questions.append("How did you sleep last night?")
    if any(w in t for w in ["blue", "down", "bothered", "sad", "don't feel", "dont feel"]):
        questions.append("How did that affect your energy for work today?")
    if any(w in t for w in ["unproductive", "unfocused", "wasted", "sat the whole day"]):
        questions.append("What got in the way of feeling productive today?")
    if any(w in t for w in ["unsure", "confused", "bored", "unmotivated", "not sure"]):
        questions.append("What did you attempt today that mattered to you?")
    if any(w in t for w in ["fight", "argument", "conflict", "bf", "boyfriend", "girlfriend"]):
        questions.append("How did that affect your energy for work today?")
    if any(w in t for w in ["stress", "anxious", "overwhelmed", "stuck"]):
        questions.append("What got in the way of your focus?")
    if any(w in t for w in ["sleep", "slept", "rest", "enough sleep"]):
        questions.append("What might have affected your sleep quality?")
    if not questions:
        questions.append("What got in the way of your best work today?")
    return questions[:2]  # Max 2


@app.route("/api/check-topics", methods=["POST", "OPTIONS"])
def check_topics():
    if request.method == "OPTIONS":
        r = Response("", 204)
        r.headers["Access-Control-Allow-Origin"] = "*"
        r.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        r.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return r
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("text") or "").strip()
    if len(text) < 5:
        return jsonify({"missing": ["How did you sleep?", "What are you feeling?", "What did you attempt?"]})
    if not OPENAI_KEY:
        return jsonify({"missing": _fallback_check_topics(text)})
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
        return jsonify({"missing": missing})
    except Exception as e:
        print("[check-topics] GPT error:", type(e).__name__, str(e))
        return jsonify({"missing": _fallback_check_topics(text)})


def _fallback_check_topics(text: str) -> list:
    """Keyword fallback when GPT unavailable."""
    t = text.lower()
    missing = []
    if not re.search(r"\b(sleep|slept|rest|woke|nap|bed|insomnia|alright|well|hours?|asleep|restorative|restless)\b", t):
        missing.append("How did you sleep?")
    if not re.search(r"\b(feel|felt|feeling|energy|mood|stressed|anxious|happy|sad|tired|exhausted|drained|bothered|down|low|great|calm|relaxed|motivated|restless|groggy|heavy)\b", t) and not re.search(r"(feel|i'm|im)\s+(okay|fine|good|bad)", t):
        missing.append("What are you feeling?")
    if not re.search(r"\b(work|worked|attempt|tried|did|task|project|focus|study|meeting|class|productive|unproductive|nothing|read|exercise|chilled)\b", t):
        missing.append("What did you attempt?")
    return missing


@app.route("/api/test-gpt")
def test_gpt():
    """Quick check: is OpenAI key set and responding?"""
    if not OPENAI_KEY:
        return jsonify({"ok": False, "error": "OPENAI_API_KEY not set in .env"})
    try:
        import openai
        r = openai.OpenAI(api_key=OPENAI_KEY).chat.completions.create(
            model="gpt-4o-mini", messages=[{"role": "user", "content": "Reply with exactly: OK"}], max_tokens=5
        )
        reply = (r.choices[0].message.content or "").strip()
        return jsonify({"ok": True, "reply": reply})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/api/clarify", methods=["POST", "OPTIONS"])
def clarify():
    if request.method == "OPTIONS":
        r = Response("", 204)
        r.headers["Access-Control-Allow-Origin"] = "*"
        r.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
        r.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return r
    data = request.get_json(force=True, silent=True) or {}
    text = (data.get("text") or "").strip()
    if len(text) < 15:
        return jsonify({"questions": [], "source": "none"})
    if not OPENAI_KEY:
        return jsonify({"questions": _fallback_clarify(text), "source": "fallback", "error": "OPENAI_API_KEY not set"})
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
        questions = out if isinstance(out, list) else []
        return jsonify({"questions": questions, "source": "gpt"})
    except Exception as e:
        print("[clarify] GPT error:", type(e).__name__, str(e))
        return jsonify({"questions": _fallback_clarify(text), "source": "fallback", "error": str(e)})


@app.route("/api/transcribe", methods=["POST"])
def transcribe():
    file = request.files.get("audio") or request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "No audio file in request"}), 400

    if not OPENAI_KEY:
        return jsonify({"transcript": "[Add OPENAI_API_KEY for voice transcription]"})

    try:
        import openai
        with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
            file.save(tmp.name)
            with open(tmp.name, "rb") as f:
                r = openai.OpenAI(api_key=OPENAI_KEY).audio.transcriptions.create(
                    model="whisper-1", file=f, language="en"
                )
        os.unlink(tmp.name)
        return jsonify({"transcript": r.text})
    except Exception as e:
        return jsonify({"error": str(e), "transcript": ""}), 500


@app.route("/<path:path>")
def serve_static(path):
    """Serve static files (css, js, etc.) that exist on disk."""
    if ".." in path:
        return "Not Found", 404
    full = os.path.join(".", path)
    if os.path.isfile(full):
        return send_from_directory(".", path)
    return "Not Found", 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"Signal running at http://127.0.0.1:{port}/")
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
