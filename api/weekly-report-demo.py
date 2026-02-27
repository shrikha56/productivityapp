"""
Vercel serverless: POST /api/weekly-report-demo — Demo weekly report (no auth).
Returns GPT-generated report from 7 days of test reflections.
Requires: OPENAI_API_KEY
"""
import importlib.util
import json
import os
from http.server import BaseHTTPRequestHandler

# Load weekly-report module (filename has hyphen)
_mod_path = os.path.join(os.path.dirname(__file__), "weekly-report.py")
_spec = importlib.util.spec_from_file_location("weekly_report", _mod_path)
_weekly_report = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_weekly_report)
generate_weekly_report = _weekly_report.generate_weekly_report

DEMO_ENTRIES = [
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


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        report = generate_weekly_report(DEMO_ENTRIES, api_key=None)
        if report.get("error") and not report.get("week_narrative"):
            self._send(503, report)
            return
        report["entries"] = DEMO_ENTRIES
        self._send(200, report)

    def _send(self, status, body):
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))
