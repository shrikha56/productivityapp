"""
Vercel serverless: POST /api/transcribe — Whisper speech-to-text.
Requires: OPENAI_API_KEY
"""
import json
import os
import tempfile
from http.server import BaseHTTPRequestHandler

OPENAI_KEY = (os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_KEY") or "").strip()


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            self._send(400, {"error": "Expected multipart form with audio file"})
            return

        content_len = int(self.headers.get("Content-Length", 0))
        if content_len == 0:
            self._send(400, {"error": "No body"})
            return

        raw = self.rfile.read(content_len)
        boundary = content_type.split("boundary=")[-1].strip().strip('"')
        parts = raw.split(b"--" + boundary.encode())
        audio_data = None
        for p in parts:
            if b"audio" in p and b"filename=" in p:
                idx = p.find(b"\r\n\r\n")
                if idx >= 0:
                    audio_data = p[idx + 4 :].rstrip(b"\r\n")
                    break

        if not audio_data:
            self._send(400, {"error": "No audio file in request"})
            return

        if not OPENAI_KEY:
            self._send(503, {"error": "OPENAI_API_KEY not configured. Add it in Vercel: Settings → Environment Variables.", "transcript": ""})
            return

        try:
            import openai
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as f:
                f.write(audio_data)
                path = f.name
            with open(path, "rb") as f:
                r = openai.OpenAI(api_key=OPENAI_KEY).audio.transcriptions.create(model="whisper-1", file=f, language="en")
            os.unlink(path)
            self._send(200, {"transcript": r.text})
        except Exception as e:
            self._send(500, {"error": str(e), "transcript": ""})

    def _send(self, status, body):
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode("utf-8"))
