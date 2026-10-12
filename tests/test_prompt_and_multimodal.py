# -*- coding: utf-8 -*-
import unittest
from unittest.mock import MagicMock, patch

from shiro.persona import build_system_prompt
from shiro.llm.cleaner import clean_response
from shiro.vision.bridge import analyze_visual_bridge, get_gemini_api_key
from shiro.pipeline.inference import get_shiro_reply
from shiro.server_state import state

class TestPromptAndMultimodal(unittest.TestCase):
    def test_slimmed_system_prompt(self):
        prompt = build_system_prompt(
            conversation_summary="FAKTA: Kakak suka kopi\n",
            facts_summary="TRAITS: Ceria\n"
        )
        self.assertIn("Kamu adalah Shiro", prompt)
        self.assertIn("PEDOMAN KARAKTER", prompt)
        self.assertIn("Fakta & Anti-Halusinasi", prompt)
        # Verify negative bloat is removed
        self.assertNotIn("DILARANG KERAS MENGGUNAKAN BAHASA INGGRIS", prompt)
        self.assertNotIn("KEMAMPUAN REKAYASA PERANGKAT LUNAK, CODING & DEBUGGING: Shiro adalah programmer jenius", prompt)
        self.assertNotIn("AGENTIC PLANNING & PENGGUNAAN TOOLS", prompt)

    def test_cleaner_preserves_shiro_actions(self):
        # Previously *Shiro tersenyum* was wiped completely; now it should normalize to *tersenyum*
        text = "*Shiro tersenyum manis* Halo Kakak! Shiro senang melihat Kakak."
        cleaned = clean_response(text)
        self.assertIn("*tersenyum manis*", cleaned)
        self.assertIn("Halo Kakak!", cleaned)

    def test_cleaner_preserves_markdown_headers_and_code(self):
        text = "### Ringkasan Dokumen\nBerikut adalah poin penting:\n```python\nprint('hello')\n```"
        cleaned = clean_response(text)
        self.assertIn("### Ringkasan Dokumen", cleaned)
        self.assertIn("```python\nprint('hello')\n```", cleaned)

    def test_document_prompt_integration_in_inference(self):
        mock_llm = MagicMock()
        mock_llm.model_path = "model/Qwen3.8-27B-Uncensored-Q4_K_M.gguf"
        mock_llm.create_chat_completion.return_value = {
            "choices": [{
                "message": {"content": "*tersenyum membaca dokumen* Dokumen ini membahas arsitektur AI Shiro."},
                "finish_reason": "stop"
            }],
            "usage": {}
        }

        with patch.object(state, 'llm', mock_llm):
            doc_info = {
                "filename": "laporan_proyek.txt",
                "text": "Proyek Shiro berjalan lancar dengan sistem neural canggih."
            }
            reply, trace = get_shiro_reply(
                "Tolong rangkum dokumen ini ya!",
                document_info=doc_info,
                return_trace=True
            )
            self.assertIn("arsitektur AI Shiro", reply)
            # Verify the messages sent to LLM included the document
            call_args = mock_llm.create_chat_completion.call_args[1]
            msgs = call_args["messages"]
            # System prompt contains document
            sys_msg = next(m["content"] for m in msgs if m["role"] == "system")
            self.assertIn("laporan_proyek.txt", sys_msg)
            self.assertIn("Proyek Shiro berjalan lancar", sys_msg)
            # User turn message has attached doc indicator
            user_msg = msgs[-1]["content"]
            self.assertIn("[Melampirkan Dokumen: laporan_proyek.txt]", user_msg)
            self.assertIn("Tolong rangkum dokumen ini ya!", user_msg)

    def test_image_attachment_in_text_only_inference(self):
        mock_llm = MagicMock()
        mock_llm.model_path = "model/Qwen3.8-27B-Uncensored-Q4_K_M.gguf"
        mock_llm.chat_handler = None
        mock_llm.create_chat_completion.return_value = {
            "choices": [{
                "message": {"content": "*menatap layar* Uwah, Kakak kirim foto ya? Shiro belum bisa lihat gambarnya langsung nih!"},
                "finish_reason": "stop"
            }],
            "usage": {}
        }

        with patch.object(state, 'llm', mock_llm), patch.object(state, 'vision_chat_handler', None):
            with patch('shiro.vision.bridge.get_gemini_api_key', return_value=None):
                reply, trace = get_shiro_reply(
                    "shiro tau dia siapa?",
                    image_base64="data:image/jpeg;base64,/9j/4AAQSkZJRg==",
                    return_trace=True
                )
                self.assertIn("Kakak kirim foto ya", reply)
                call_args = mock_llm.create_chat_completion.call_args[1]
                msgs = call_args["messages"]
                # System prompt has clear guidance when vision is inactive
                sys_msg = next(m["content"] for m in msgs if m["role"] == "system")
                self.assertIn("CATATAN SISTEM VISUAL", sys_msg)
                # User turn explicitly states image is attached
                user_msg = msgs[-1]["content"]
                self.assertIn("[Melampirkan Gambar Visual]", user_msg)
                self.assertIn("shiro tau dia siapa?", user_msg)

if __name__ == "__main__":
    unittest.main()
