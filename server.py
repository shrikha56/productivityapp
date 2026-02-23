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
    import pathlib
    env_path = pathlib.Path(__file__).resolve().parent / ".env"
    load_dotenv(dotenv_path=env_path)
except ImportError:
    pass

from flask import Flask, request, jsonify, send_from_directory, Response

# Import API logic from Vercel functions
from api.analyze import get_supabase, analyze_with_gpt
import importlib
weekly_report_mod = importlib.import_module("api.weekly-report")

app = Flask(__name__, static_folder=".", static_url_path="")

SUPABASE_URL = os.environ.get("SUPABASE_URL") or os.environ.get("EXPO_PUBLIC_SUPABASE_URL", "")
SUPABASE_KEY = (
    os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    or os.environ.get("SUPABASE_ANON_KEY")
    or os.environ.get("EXPO_PUBLIC_SUPABASE_KEY", "")
)
OPENAI_KEY = (os.environ.get("OPENAI_API_KEY") or "").strip()


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

    result = analyze_with_gpt(transcript, sleep_hours, sleep_quality, energy, deep_work, api_key=OPENAI_KEY)

    # If GPT failed (fallback), don't save — return error so user can retry
    if result.get("likely_drivers") == ["Analysis pending"]:
        err = result.get("_error", "Unknown error")
        return jsonify({"error": f"Analysis failed: {err}"}), 503

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


@app.route("/api/weekly-report", methods=["POST"])
def weekly_report():
    data = request.get_json(force=True, silent=True) or {}

    # Demo mode: use test data + real GPT
    if data.get("demo"):
        test_entries = [
            {"date": "2026-02-17", "sleep_hours": 6, "sleep_quality": 2, "energy": 2, "deep_work_blocks": 0,
             "reflection_summary": "Stayed up until 2am scrolling. Woke up groggy at 8. Had a lecture at 10 but couldn't focus. Spent most of the day on admin tasks. Felt scattered and unmotivated. Skipped the gym.",
             "likely_drivers": ["Late-night phone use disrupted melatonin production", "Sleep debt reduced executive function"], "experiment_for_tomorrow": "Phone in another room by 11pm"},
            {"date": "2026-02-18", "sleep_hours": 7.5, "sleep_quality": 3, "energy": 3, "deep_work_blocks": 1,
             "reflection_summary": "Better sleep but still felt residual tiredness. Got one deep work block on my assignment in the morning. After lunch energy crashed hard. Ate too much pasta. Spent afternoon in meetings that could have been emails.",
             "likely_drivers": ["Post-lunch glucose crash", "Residual sleep debt from previous night"], "experiment_for_tomorrow": "Light lunch, walk after eating"},
            {"date": "2026-02-19", "sleep_hours": 7, "sleep_quality": 4, "energy": 4, "deep_work_blocks": 2,
             "reflection_summary": "Slept well. Woke up at 7:30 naturally. Got two solid deep work blocks before noon. Felt locked in. Phone was in another room which helped. Had a great conversation with a classmate about the project. Energy dipped slightly around 3pm but recovered.",
             "likely_drivers": ["Phone removal reduced attentional residue", "Morning deep work leveraged peak cortisol"], "experiment_for_tomorrow": "Repeat morning routine"},
            {"date": "2026-02-20", "sleep_hours": 5.5, "sleep_quality": 2, "energy": 2, "deep_work_blocks": 0,
             "reflection_summary": "Deadline stress kept me up. Worked until 1am on the assignment. Woke up at 6:30 feeling terrible. Couldn't concentrate in any lecture. Had 3 coffees by noon. Felt jittery and anxious. No deep work happened. The work I did last night was probably low quality anyway.",
             "likely_drivers": ["Acute sleep restriction impaired prefrontal cortex", "Caffeine-induced anxiety", "Decision fatigue from deadline pressure"], "experiment_for_tomorrow": "Set hard stop at 11pm regardless of deadline"},
            {"date": "2026-02-21", "sleep_hours": 8, "sleep_quality": 4, "energy": 3, "deep_work_blocks": 1,
             "reflection_summary": "Crashed early at 9pm, slept 8 hours. Body needed recovery. Morning was slow to start, felt like I was coming out of a fog. By afternoon managed one focused session. Submitted the assignment. Felt relief but also drained. Went for a walk which helped clear my head.",
             "likely_drivers": ["Recovery sleep restored some executive function", "Post-deadline relief reduced cognitive load"], "experiment_for_tomorrow": "Morning walk before any screens"},
            {"date": "2026-02-22", "sleep_hours": 7.5, "sleep_quality": 4, "energy": 4, "deep_work_blocks": 2,
             "reflection_summary": "Good sleep again. Started with a 20min walk, then straight into deep work. Got two blocks done on the new project. Lunch was light — salad and protein. Afternoon energy stayed high. Didn't touch phone until 2pm. This felt like my best day this week.",
             "likely_drivers": ["Consistent sleep restored working memory", "Morning walk elevated baseline arousal", "Delayed phone use prevented attentional residue"], "experiment_for_tomorrow": "Replicate: walk → deep work → light lunch"},
            {"date": "2026-02-23", "sleep_hours": 7, "sleep_quality": 3, "energy": 3, "deep_work_blocks": 1,
             "reflection_summary": "Decent sleep but woke up once around 3am — might have been the late dinner. Started slower today. One deep work block in the morning. Got distracted by social media after lunch. Had a productive conversation about my project with my boss. Feeling okay overall, not great not terrible.",
             "likely_drivers": ["Late dinner disrupted sleep continuity", "Social media broke afternoon focus momentum"], "experiment_for_tomorrow": "Dinner before 8pm, block social media until 4pm"},
        ]
        report = weekly_report_mod.generate_weekly_report(test_entries, api_key=OPENAI_KEY)
        if report.get("error") and not report.get("week_narrative"):
            return jsonify(report), 503
        return jsonify(report)

    user_id = data.get("user_id")
    if not user_id:
        return jsonify({"error": "user_id required"}), 400

    supabase = get_supabase()
    if not supabase:
        return jsonify({"error": "Server not configured"}), 503

    try:
        result = supabase.table("entries").select("*").eq("user_id", user_id).order("date", desc=True).limit(30).execute()
        entries = result.data or []
    except Exception as e:
        return jsonify({"error": f"Failed to fetch entries: {e}"}), 500

    if len(entries) < 7:
        return jsonify({"locked": True, "entries_count": len(entries), "needed": 7})

    report = weekly_report_mod.generate_weekly_report(entries[:14], api_key=OPENAI_KEY)
    if report.get("error") and not report.get("week_narrative"):
        return jsonify(report), 503

    return jsonify(report)


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
        prompt = f"""A user recorded a daily voice reflection. Check if 3 topics are covered. This is informal speech — look for ANY mention, even brief or indirect. Be lenient. When in doubt, mark as ADDRESSED.

TOPIC 1 — "How did you sleep?"
ADDRESSED if they mention sleep at all: waking up, sleep time, sleep quality, tiredness from sleep, wanting to sleep more, etc.
Examples: "woke up at 7", "slept well", "didn't sleep enough", "wanted to sleep in" → all ADDRESSED

TOPIC 2 — "What are you feeling?"
ADDRESSED if they describe ANY emotion, energy state, or physical feeling during the day.
Examples: "felt tired", "was energetic", "felt unproductive", "I'm sick", "was lethargic", "felt overwhelmed" → all ADDRESSED

TOPIC 3 — "What did you attempt?"
ADDRESSED if they mention ANY activity, work, or what they did (or didn't do).
Examples: "went to work", "had a meeting", "worked on my app", "did nothing", "went to class" → all ADDRESSED

Reflection: "{text[:1200]}"

Return JSON array of ONLY truly missing topics (topics with ZERO mention). Use exact strings:
["How did you sleep?", "What are you feeling?", "What did you attempt?"]
Return [] if all three are mentioned even briefly."""
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
        return jsonify({"error": "OPENAI_API_KEY not configured. Add it to .env for local dev, or Vercel Environment Variables for production.", "transcript": ""}), 503

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
    if not OPENAI_KEY:
        print("WARNING: OPENAI_API_KEY not set in .env — analysis and voice transcription will fail.")
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
