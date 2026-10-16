import unittest
import os
import json
from unittest.mock import patch, MagicMock
from flask import Flask
from shiro.routes.chat import chat_bp
from shiro.routes.sessions import sessions_bp
from shiro.memory.manager import AdvancedMemoryManager

class TestChatStreamAndSessions(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        self.app.register_blueprint(chat_bp)
        self.app.register_blueprint(sessions_bp)
        self.client = self.app.test_client()

    @patch("shiro.routes.chat.stream_shiro_reply")
    def test_chat_sse_streaming(self, mock_stream):
        # Mock streaming tokens
        def dummy_stream(*args, **kwargs):
            yield {"type": "ping"}
            yield {"type": "token", "token": "Halo "}
            yield {"type": "token", "token": "Kakak!"}
            yield {"type": "done", "reply": "Halo Kakak!", "trace": {}}

        mock_stream.side_effect = dummy_stream

        resp = self.client.post("/api/chat", json={
            "message": "Halo Shiro",
            "stream": True
        })

        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/event-stream", resp.headers.get("Content-Type", ""))

        data_str = resp.get_data(as_text=True)
        self.assertIn(": ping", data_str)
        self.assertIn('"type": "init"', data_str)
        self.assertIn('"type": "token"', data_str)
        self.assertIn('"type": "done"', data_str)
        self.assertIn("Halo Kakak!", data_str)

    def test_sessions_endpoint_returns_messages(self):
        resp = self.client.get("/api/sessions")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("sessions", data)
        self.assertIn("active_session_id", data)
        self.assertIn("messages", data)
        self.assertIsInstance(data["messages"], list)

if __name__ == "__main__":
    unittest.main()
