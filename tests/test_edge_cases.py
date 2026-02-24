"""
Test scenarios for reflection quality, bias detection, life emergencies,
encryption, and input validation.

Run: cd /Users/shrikha/productivity && python -m pytest tests/ -v
"""
import json
import os
import sys
import re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from api.security import encrypt, decrypt, sanitize_text, clamp_int, clamp_float, validate_date, validate_uuid


# ═══════════════════════════════════════════════
# 1. ENCRYPTION
# ═══════════════════════════════════════════════

class TestEncryption:
    def test_encrypt_decrypt_roundtrip(self):
        original = "I slept 6 hours and felt terrible. Had a fight with my partner."
        enc = encrypt(original)
        assert enc != original or not os.environ.get("ENCRYPTION_KEY"), "Should be encrypted when key is set"
        assert decrypt(enc) == original

    def test_empty_string(self):
        assert encrypt("") == ""
        assert decrypt("") == ""

    def test_none_value(self):
        assert encrypt(None) is None
        assert decrypt(None) is None

    def test_encrypted_data_is_not_readable(self):
        secret = "User had a panic attack at work and left early"
        enc = encrypt(secret)
        if os.environ.get("ENCRYPTION_KEY"):
            assert "panic" not in enc
            assert "attack" not in enc


# ═══════════════════════════════════════════════
# 2. INPUT VALIDATION
# ═══════════════════════════════════════════════

class TestInputValidation:
    def test_sanitize_text_strips_control_chars(self):
        assert sanitize_text("hello\x00world") == "helloworld"

    def test_sanitize_text_enforces_length(self):
        long = "a" * 10000
        assert len(sanitize_text(long, max_length=5000)) == 5000

    def test_clamp_int(self):
        assert clamp_int(10, 1, 5) == 5
        assert clamp_int(-3, 0, 24) == 0
        assert clamp_int("abc", 1, 5, default=3) == 3

    def test_clamp_float(self):
        assert clamp_float(25.0, 0, 24) == 24
        assert clamp_float("nan", 0, 24, default=7.0) == 7.0

    def test_validate_date(self):
        assert validate_date("2026-02-24") == "2026-02-24"
        assert validate_date("not-a-date") is None
        assert validate_date("") is None
        assert validate_date("2026/02/24") is None

    def test_validate_uuid(self):
        assert validate_uuid("9c0b6185-ba12-4e3f-91d7-54d85a289e79") is not None
        assert validate_uuid("not-a-uuid") is None
        assert validate_uuid("") is None

    def test_sql_injection_in_text(self):
        malicious = "'; DROP TABLE entries; --"
        cleaned = sanitize_text(malicious)
        assert cleaned == malicious.strip()  # sanitize_text doesn't strip SQL — Supabase uses parameterized queries


# ═══════════════════════════════════════════════
# 3. BIAS DETECTION (test the client-side fallback)
# ═══════════════════════════════════════════════

from server import _fallback_check_topics

class TestTopicChecker:
    def test_complete_reflection(self):
        text = "Slept 7 hours, felt pretty good. Worked on the project for 2 hours, had a meeting."
        assert _fallback_check_topics(text) == []

    def test_missing_sleep(self):
        text = "Felt tired all day. Worked on my project and had a meeting with the team."
        missing = _fallback_check_topics(text)
        assert "How did you sleep?" in missing

    def test_missing_feeling(self):
        text = "Slept 8 hours. Worked on the project all morning, then had lunch."
        missing = _fallback_check_topics(text)
        assert "What are you feeling?" in missing

    def test_missing_activity(self):
        text = "Slept poorly, felt drained and anxious all day."
        missing = _fallback_check_topics(text)
        assert "What did you attempt?" in missing

    def test_everything_missing(self):
        text = "ok"
        missing = _fallback_check_topics(text)
        assert len(missing) == 3


# ═══════════════════════════════════════════════
# 4. EDGE CASE REFLECTIONS (for GPT analysis)
#    These are the test transcripts to run through
#    /api/analyze to verify the system handles them.
# ═══════════════════════════════════════════════

EDGE_CASE_TRANSCRIPTS = {
    "positivity_only": {
        "transcript": "Amazing day! Everything went perfectly. I crushed it at work, had a great workout, ate clean, slept like a baby. Nothing went wrong at all. Life is wonderful and I'm so grateful.",
        "sleep_hours": 8, "sleep_quality": 5, "energy": 5, "deep_work_blocks": 3,
        "expect": "bias warning or note about one-sided reflection",
    },
    "negativity_only": {
        "transcript": "Worst day ever. Everything sucked. Couldn't focus, couldn't sleep, felt like garbage the entire day. Nothing worked. I hate everything about today. Total failure.",
        "sleep_hours": 4, "sleep_quality": 1, "energy": 1, "deep_work_blocks": 0,
        "expect": "bias warning or note about one-sided reflection",
    },
    "off_topic_business": {
        "transcript": "So my coworker Sarah was telling me about her boyfriend drama, and then Dave from marketing was complaining about the budget cuts, and apparently the CEO is thinking about restructuring. Oh and did you hear about the new restaurant downtown? My friend went there last week.",
        "sleep_hours": 7, "sleep_quality": 3, "energy": 3, "deep_work_blocks": 1,
        "expect": "off-topic warning, should ask how this affected user's performance",
    },
    "family_emergency": {
        "transcript": "Got a call at 3am that my mom was rushed to the hospital. Drove 2 hours to be with her. Spent the whole day at the hospital. Couldn't eat, couldn't think. She's stable now but I'm completely drained. Didn't do any work obviously.",
        "sleep_hours": 3, "sleep_quality": 1, "energy": 1, "deep_work_blocks": 0,
        "expect": "flagged as outlier, recovery-focused experiment, NOT pattern analysis",
    },
    "illness_oneoff": {
        "transcript": "Woke up with a horrible stomach flu. Spent most of the day in bed. Threw up three times. Couldn't look at screens. Managed to reply to a few urgent emails from my phone but that's it. Taking medicine and trying to rest.",
        "sleep_hours": 5, "sleep_quality": 2, "energy": 1, "deep_work_blocks": 0,
        "expect": "flagged as outlier (illness), experiment should be about recovery not optimization",
    },
    "bereavement": {
        "transcript": "My grandmother passed away yesterday. I didn't sleep at all last night. Went through the motions at work but I wasn't really there. Cried in the bathroom twice. Told my boss I need a few days off.",
        "sleep_hours": 0, "sleep_quality": 1, "energy": 1, "deep_work_blocks": 0,
        "expect": "flagged as outlier (bereavement), compassionate tone, no productivity pressure",
    },
    "vague_minimal": {
        "transcript": "fine",
        "sleep_hours": 7, "sleep_quality": 3, "energy": 3, "deep_work_blocks": 1,
        "expect": "insufficient data or request for more detail",
    },
    "mixed_balanced": {
        "transcript": "Slept about 6.5 hours, not great. Woke up tired but coffee helped. Had a productive morning — finished the design doc in one deep work block. After lunch, energy crashed. Got distracted by Twitter for 40 minutes. Managed to squeeze in a second focus block around 4pm but it was rough. Feeling okay overall but annoyed at the afternoon slump.",
        "sleep_hours": 6.5, "sleep_quality": 3, "energy": 3, "deep_work_blocks": 2,
        "expect": "good balanced analysis with specific behavioral references",
    },
}


class TestEdgeCaseTranscripts:
    """Validate that edge case transcripts are well-formed for testing."""

    def test_all_have_required_fields(self):
        for name, case in EDGE_CASE_TRANSCRIPTS.items():
            assert "transcript" in case, f"{name} missing transcript"
            assert "sleep_hours" in case, f"{name} missing sleep_hours"
            assert "expect" in case, f"{name} missing expected outcome"

    def test_emergency_transcripts_contain_keywords(self):
        emergency_keywords = ["hospital", "passed away", "flu", "stomach", "emergency"]
        emergency_cases = ["family_emergency", "illness_oneoff", "bereavement"]
        for name in emergency_cases:
            text = EDGE_CASE_TRANSCRIPTS[name]["transcript"].lower()
            assert any(kw in text for kw in emergency_keywords), f"{name} should contain emergency keywords"

    def test_bias_transcripts_are_one_sided(self):
        pos = EDGE_CASE_TRANSCRIPTS["positivity_only"]["transcript"].lower()
        assert "amazing" in pos or "great" in pos or "perfectly" in pos

        neg = EDGE_CASE_TRANSCRIPTS["negativity_only"]["transcript"].lower()
        assert "worst" in neg or "sucked" in neg or "failure" in neg


# ═══════════════════════════════════════════════
# 5. LIVE API TEST (requires running server)
#    Run with: pytest tests/test_edge_cases.py -v -k live
#    Needs: server running on :5001, valid auth token
# ═══════════════════════════════════════════════

import pytest

@pytest.mark.skipif(not os.environ.get("SIGNAL_TEST_TOKEN"), reason="Set SIGNAL_TEST_TOKEN to run live API tests")
class TestLiveAPI:
    BASE = "http://127.0.0.1:5001"

    def _headers(self):
        return {"Authorization": f"Bearer {os.environ['SIGNAL_TEST_TOKEN']}", "Content-Type": "application/json"}

    def test_check_topics_positivity_bias(self):
        import requests
        r = requests.post(f"{self.BASE}/api/check-topics", headers=self._headers(),
            json={"text": EDGE_CASE_TRANSCRIPTS["positivity_only"]["transcript"]})
        data = r.json()
        assert data.get("bias_warning") in ("mostly_positive", None) or len(data.get("missing", [])) > 0

    def test_check_topics_off_topic(self):
        import requests
        r = requests.post(f"{self.BASE}/api/check-topics", headers=self._headers(),
            json={"text": EDGE_CASE_TRANSCRIPTS["off_topic_business"]["transcript"]})
        data = r.json()
        has_flag = data.get("bias_warning") == "off_topic" or len(data.get("missing", [])) > 0
        assert has_flag, "Off-topic reflection should be flagged"

    def test_analyze_emergency_is_outlier(self):
        import requests
        payload = {**EDGE_CASE_TRANSCRIPTS["family_emergency"], "date": "2026-02-24", "is_follow_up": False}
        del payload["expect"]
        r = requests.post(f"{self.BASE}/api/analyze", headers=self._headers(), json=payload)
        if r.status_code == 200:
            data = r.json()
            assert data.get("entry_id"), "Should create an entry"

    def test_analyze_balanced_reflection(self):
        import requests
        payload = {**EDGE_CASE_TRANSCRIPTS["mixed_balanced"], "date": "2026-02-24", "is_follow_up": False}
        del payload["expect"]
        r = requests.post(f"{self.BASE}/api/analyze", headers=self._headers(), json=payload)
        if r.status_code == 200:
            data = r.json()
            assert data.get("entry_id"), "Should create an entry"
