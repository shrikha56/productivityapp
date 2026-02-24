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
from functools import wraps

# Import API logic from Vercel functions
from api.analyze import get_supabase, analyze_with_gpt
from api.security import (
    get_user_id, encrypt, decrypt,
    sanitize_text, clamp_int, clamp_float, validate_date, validate_uuid,
)
import importlib
weekly_report_mod = importlib.import_module("api.weekly-report")

app = Flask(__name__, static_folder=".", static_url_path="")


# ── Security headers ──

@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), geolocation=(), payment=()"
    return response


# ── Rate limiting (simple in-memory) ──

from collections import defaultdict
import time

_rate_limits = defaultdict(list)
RATE_LIMIT_WINDOW = 60
RATE_LIMIT_MAX = 30

def check_rate_limit(key: str) -> bool:
    now = time.time()
    _rate_limits[key] = [t for t in _rate_limits[key] if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_limits[key]) >= RATE_LIMIT_MAX:
        return False
    _rate_limits[key].append(now)
    return True


# ── Auth decorator ──

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = get_user_id(request.headers.get("Authorization", ""))
        if not user_id:
            return jsonify({"error": "Authentication required"}), 401
        request.authenticated_user_id = user_id
        if not check_rate_limit(user_id):
            return jsonify({"error": "Too many requests. Try again shortly."}), 429
        return f(*args, **kwargs)
    return decorated

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


@app.route("/analysis")
def analysis():
    return send_from_directory(".", "analysis.html")


# --- API routes ---

@app.route("/api/entries", methods=["GET"])
@require_auth
def list_entries():
    """Fetch user's entries with decrypted fields."""
    user_id = request.authenticated_user_id
    supabase = get_supabase()
    if not supabase:
        return jsonify({"error": "Server not configured"}), 503
    try:
        try:
            result = supabase.table("entries").select(
                "id, date, sleep_hours, sleep_quality, energy, deep_work_blocks, reflection_summary, entry_number, is_follow_up"
            ).eq("user_id", user_id).order("date", desc=True).limit(90).execute()
        except Exception:
            result = supabase.table("entries").select(
                "id, date, sleep_hours, sleep_quality, energy, deep_work_blocks, reflection_summary"
            ).eq("user_id", user_id).order("date", desc=True).limit(90).execute()
        entries = result.data or []
        for e in entries:
            e["reflection_summary"] = decrypt(e.get("reflection_summary") or "")
        return jsonify({"data": entries})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/entries/today", methods=["GET"])
@require_auth
def today_entries():
    """Check how many entries the user has for today and total unique days logged."""
    user_id = request.authenticated_user_id
    today = __import__("datetime").date.today().isoformat()
    supabase = get_supabase()
    if not supabase:
        return jsonify({"error": "Server not configured"}), 503
    try:
        try:
            result = supabase.table("entries").select("id, entry_number, is_follow_up").eq(
                "user_id", user_id
            ).eq("date", today).order("entry_number", desc=False).execute()
        except Exception:
            result = supabase.table("entries").select("id").eq(
                "user_id", user_id
            ).eq("date", today).execute()
        entries = result.data or []
        today_count = len(entries)

        result_all = supabase.table("entries").select("date").eq("user_id", user_id).order("date", desc=True).limit(100).execute()
        all_dates = result_all.data or []
        unique_days = len(set(r.get("date") for r in all_dates if r.get("date")))

        return jsonify({"count": today_count, "entries": entries, "unique_days": unique_days})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/entries/<entry_id>", methods=["GET"])
@require_auth
def get_entry(entry_id):
    """Fetch a single entry with decrypted fields, verifying ownership."""
    user_id = request.authenticated_user_id
    if not validate_uuid(entry_id):
        return jsonify({"error": "Invalid entry ID"}), 400
    supabase = get_supabase()
    if not supabase:
        return jsonify({"error": "Server not configured"}), 503
    try:
        result = supabase.table("entries").select("*").eq("id", entry_id).eq("user_id", user_id).single().execute()
        entry = result.data
        if not entry:
            return jsonify({"error": "Entry not found"}), 404
        entry["transcript"] = decrypt(entry.get("transcript") or "")
        entry["reflection_summary"] = decrypt(entry.get("reflection_summary") or "")
        return jsonify({"data": entry})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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


def _pending_analysis_result():
    return {
        "reflection_summary": "",
        "likely_drivers": ["Analysis pending"],
        "predicted_impact": "—",
        "experiment_for_tomorrow": "—",
    }


@app.route("/api/analyze", methods=["POST"])
@require_auth
def analyze():
    data = request.get_json(force=True, silent=True) or {}
    user_id = request.authenticated_user_id

    supabase = get_supabase()
    if not supabase:
        return jsonify({"error": "Server not configured"}), 503

    transcript = sanitize_text(data.get("transcript", "") or "", max_length=5000)
    sleep_hours = clamp_float(data.get("sleep_hours", 0), 0, 24, default=0)
    sleep_quality = clamp_int(data.get("sleep_quality", 3), 1, 5, default=3)
    energy = clamp_int(data.get("energy", 3), 1, 5, default=3)
    deep_work = clamp_int(data.get("deep_work_blocks", 0), 0, 5, default=0)
    entry_date = validate_date(data.get("date", ""))
    if not entry_date:
        return jsonify({"error": "Valid date required (YYYY-MM-DD)"}), 400

    is_follow_up = data.get("is_follow_up") is True
    plan_more_reflections = data.get("plan_more_reflections") in (True, "true", 1)
    is_last_reflection = data.get("is_last_reflection") in (True, "true", 1)

    has_multi_entry_cols = True
    try:
        existing = supabase.table("entries").select("id, entry_number, sleep_hours, sleep_quality, energy, deep_work_blocks, transcript").eq("user_id", user_id).eq("date", entry_date).order("entry_number", desc=False).execute()
        existing_entries = existing.data or []
        next_number = (existing_entries[-1]["entry_number"] + 1) if existing_entries else 1
    except Exception:
        has_multi_entry_cols = False
        existing = supabase.table("entries").select("id, sleep_hours, sleep_quality, energy, deep_work_blocks, transcript").eq("user_id", user_id).eq("date", entry_date).execute()
        existing_entries = existing.data or []
        next_number = len(existing_entries) + 1

    if is_follow_up and existing_entries:
        first = existing_entries[0]
        sleep_hours = first.get("sleep_hours") or sleep_hours
        sleep_quality = first.get("sleep_quality") or sleep_quality
        energy = first.get("energy") or energy
        deep_work = first.get("deep_work_blocks") or deep_work

    skip_analysis = False
    if is_follow_up:
        skip_analysis = not is_last_reflection
    else:
        skip_analysis = plan_more_reflections

    if skip_analysis:
        result = _pending_analysis_result()
    elif is_follow_up and is_last_reflection and existing_entries:
        parts = []
        for i, e in enumerate(existing_entries):
            raw = decrypt(e.get("transcript") or "")
            if raw.strip():
                label = f"Reflection {i + 1}:" if len(existing_entries) > 1 else ""
                parts.append((label + " " + raw.strip()).strip())
        if transcript.strip():
            parts.append(f"Reflection {len(existing_entries) + 1}: " + transcript.strip())
        combined = "\n\n".join(parts) if parts else transcript
        result = analyze_with_gpt(combined, sleep_hours, sleep_quality, energy, deep_work, api_key=OPENAI_KEY)
        if result.get("likely_drivers") == ["Analysis pending"]:
            err = result.get("_error", "Unknown error")
            return jsonify({"error": f"Analysis failed: {err}"}), 503
    else:
        result = analyze_with_gpt(transcript, sleep_hours, sleep_quality, energy, deep_work, api_key=OPENAI_KEY)
        if result.get("likely_drivers") == ["Analysis pending"]:
            err = result.get("_error", "Unknown error")
            return jsonify({"error": f"Analysis failed: {err}"}), 503

    row = {
        "user_id": user_id,
        "date": entry_date,
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
    if has_multi_entry_cols:
        row["entry_number"] = next_number
        row["is_follow_up"] = is_follow_up and next_number > 1

    try:
        r = supabase.table("entries").insert(row).execute()
        entry_id = r.data[0]["id"] if r.data else None

        if is_follow_up and is_last_reflection and existing_entries and not skip_analysis:
            update_data = {
                "reflection_summary": encrypt(result.get("reflection_summary", "")),
                "likely_drivers": result.get("likely_drivers", []),
                "predicted_impact": result.get("predicted_impact", ""),
                "experiment_for_tomorrow": result.get("experiment_for_tomorrow", ""),
            }
            for e in existing_entries:
                supabase.table("entries").update(update_data).eq("id", e["id"]).execute()

        out = {"entry_id": str(entry_id), "entry_number": next_number}
        if skip_analysis:
            out["skipped_analysis"] = True
        return jsonify(out)
    except Exception as e:
        err = str(e)
        if "duplicate" in err.lower() or "unique" in err.lower() or "23505" in err:
            if not has_multi_entry_cols and existing_entries:
                entry_id = existing_entries[0]["id"]
                update_row = {k: v for k, v in row.items() if k not in ("user_id", "date")}
                supabase.table("entries").update(update_row).eq("id", entry_id).execute()
                return jsonify({"entry_id": str(entry_id), "entry_number": 1, "overwritten": True})
            return jsonify({"error": "Run supabase-multi-entries.sql in Supabase SQL Editor to enable multiple entries per day."}), 400
        return jsonify({"error": err}), 500


@app.route("/api/weekly-report", methods=["POST"])
@require_auth
def weekly_report():
    data = request.get_json(force=True, silent=True) or {}
    user_id = request.authenticated_user_id

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

    supabase = get_supabase()
    if not supabase:
        return jsonify({"error": "Server not configured"}), 503

    try:
        result = supabase.table("entries").select("*").eq("user_id", user_id).order("date", desc=True).limit(30).execute()
        entries = result.data or []
    except Exception as e:
        return jsonify({"error": f"Failed to fetch entries: {e}"}), 500

    for entry in entries:
        entry["transcript"] = decrypt(entry.get("transcript") or "")
        entry["reflection_summary"] = decrypt(entry.get("reflection_summary") or "")

    unique_dates = sorted(set(e.get("date") for e in entries if e.get("date")), reverse=True)
    entries_count = len(unique_dates)
    if entries_count < 7:
        return jsonify({"locked": True, "entries_count": entries_count, "needed": 7})

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
        r.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return r
    data = request.get_json(force=True, silent=True) or {}
    text = sanitize_text((data.get("text") or ""), max_length=2000)
    if len(text) < 5:
        return jsonify({"missing": ["How did you sleep?", "What are you feeling?", "What did you attempt?"]})
    if not OPENAI_KEY:
        return jsonify({"missing": _fallback_check_topics(text)})
    try:
        import openai
        client = openai.OpenAI(api_key=OPENAI_KEY)
        prompt = f"""A user recorded a daily voice reflection for a cognitive performance tool. Analyze it for completeness AND quality.

STEP 1 — Check if 3 core topics are covered. Be lenient — any mention counts.
  TOPIC 1 — "How did you sleep?" (sleep, waking, tiredness from sleep, hours, etc.)
  TOPIC 2 — "What are you feeling?" (ANY emotion, energy, physical state)
  TOPIC 3 — "What did you attempt?" (ANY activity, work, or lack thereof)

STEP 2 — Check for reflection quality issues:
  BIAS CHECK: Is the reflection heavily one-sided?
    - Only positive ("everything was great, amazing day, no issues") with no specific behaviors → flag
    - Only negative ("everything sucked, worst day ever") with no specific behaviors → flag
    - Off-topic: mostly about other people's business, gossip, unrelated stories with no connection to the user's own performance → flag
  If biased or off-topic, add a gentle guiding question to "missing".

Reflection: "{text[:1200]}"

Return JSON only:
{{
  "missing": ["exact topic questions from above OR a guiding question for bias/off-topic"],
  "bias_warning": null or a short string like "mostly_positive", "mostly_negative", "off_topic" if detected
}}
Return {{"missing": [], "bias_warning": null}} if complete and balanced."""
        r = client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}], temperature=0.1, max_tokens=100)
        raw = (r.choices[0].message.content or "").strip()
        if raw.startswith("```"): raw = raw.split("```")[1].replace("json", "").strip()
        start = raw.find("{"); end = raw.rfind("}") + 1
        if start >= 0 and end > start: raw = raw[start:end]
        out = json.loads(raw)
        missing = out.get("missing", []) if isinstance(out, dict) else out
        if isinstance(missing, list):
            missing = [q for q in missing if isinstance(q, str)]
        else:
            missing = []
        bias = out.get("bias_warning") if isinstance(out, dict) else None
        return jsonify({"missing": missing, "bias_warning": bias})
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
        r.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return r
    data = request.get_json(force=True, silent=True) or {}
    text = sanitize_text((data.get("text") or ""), max_length=2000)
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
@require_auth
def transcribe():
    file = request.files.get("audio") or request.files.get("file")
    if not file or not file.filename:
        return jsonify({"error": "No audio file in request"}), 400

    if file.content_length and file.content_length > 25 * 1024 * 1024:
        return jsonify({"error": "Audio file too large (max 25MB)"}), 400

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


ALLOWED_STATIC_EXTENSIONS = {'.html', '.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.webp', '.woff', '.woff2', '.ttf'}

@app.route("/<path:path>")
def serve_static(path):
    """Serve static files (css, js, etc.) that exist on disk."""
    if ".." in path or path.startswith("/"):
        return "Not Found", 404
    resolved = os.path.realpath(os.path.join(".", path))
    root = os.path.realpath(".")
    if not resolved.startswith(root):
        return "Not Found", 404
    ext = os.path.splitext(path)[1].lower()
    if ext not in ALLOWED_STATIC_EXTENSIONS:
        return "Not Found", 404
    if os.path.isfile(resolved):
        return send_from_directory(".", path)
    return "Not Found", 404


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"Signal running at http://127.0.0.1:{port}/")
    if not OPENAI_KEY:
        print("WARNING: OPENAI_API_KEY not set in .env — analysis and voice transcription will fail.")
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
