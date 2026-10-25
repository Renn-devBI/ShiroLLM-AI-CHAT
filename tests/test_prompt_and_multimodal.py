# -*- coding: utf-8 -*-
import unittest
from unittest.mock import MagicMock, patch

from shiro.persona import build_system_prompt
from shiro.llm.cleaner import clean_response
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

    def test_custom_persona_overrides_default_roleplay(self):
        # When user sets custom persona (e.g. Megumin), it overrides the default Shiro brocon roleplay
        prompt = build_system_prompt(
            assistant_name="Megumin",
            custom_persona="Gadis penyihir berumur 14 tahun yang pemalu tapi sangat terobsesi dengan sihir ledakan (Explosion).",
            user_name="Kazuma"
        )
        self.assertIn("Kamu adalah Megumin", prompt)
        self.assertIn("Kazuma", prompt)
        self.assertIn("Gadis penyihir berumur 14 tahun yang pemalu", prompt)
        # Default brocon sister persona is replaced
        self.assertNotIn("adik perempuan berumur 14 tahun yang sangat menyayangi", prompt)
        self.assertNotIn("Brocon", prompt)

    def test_revert_to_default_when_custom_persona_empty(self):
        # When user clears/empties custom persona, it automatically falls back to default Shiro
        prompt = build_system_prompt(
            assistant_name="Shiro",
            custom_persona="",
            user_name="Kakak"
        )
        self.assertIn("Kamu adalah Shiro", prompt)
        self.assertIn("Brocon", prompt)
        self.assertIn("Kakak", prompt)

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

    def test_image_attachment_in_native_multimodal_inference(self):
        mock_llm = MagicMock()
        mock_llm.model_path = "model/Qwen2.5-VL-7B-Instruct-Q4_K_M.gguf"
        mock_llm.chat_handler = MagicMock()
        mock_llm.create_chat_completion.return_value = {
            "choices": [{
                "message": {"content": "*menatap gambar* Aku melihat kucing lucu di gambar ini!"},
                "finish_reason": "stop"
            }],
            "usage": {}
        }

        with patch.object(state, 'llm', mock_llm), patch.object(state, 'vision_chat_handler', mock_llm.chat_handler):
            reply, trace = get_shiro_reply(
                "shiro tau dia siapa?",
                image_base64="data:image/jpeg;base64,/9j/4AAQSkZJRg==",
                return_trace=True
            )
            self.assertIn("kucing lucu", reply)
            call_args = mock_llm.create_chat_completion.call_args[1]
            msgs = call_args["messages"]
            # Multimodal user turn content has image_url and text directly for Qwen2.5-VL
            user_msg = msgs[-1]["content"]
            self.assertIsInstance(user_msg, list)
            self.assertEqual(user_msg[0]["type"], "image_url")
            self.assertIn("data:image/jpeg;base64,", user_msg[0]["image_url"]["url"])
            self.assertEqual(user_msg[1]["type"], "text")
            self.assertIn("shiro tau dia siapa?", user_msg[1]["text"])

    def test_image_attachment_in_text_model_inference(self):
        mock_llm = MagicMock()
        mock_llm.model_path = "model/Qwen3.8-27B-Uncensored-Q4_K_M.gguf"
        mock_llm.chat_handler = None
        mock_llm.create_chat_completion.return_value = {
            "choices": [{
                "message": {"content": "*membaca teks di gambar* Gambar ini adalah Project Shiro AI v2!"},
                "finish_reason": "stop"
            }],
            "usage": {}
        }

        with patch.object(state, 'llm', mock_llm), patch.object(state, 'vision_chat_handler', None):
            with patch('shiro.vision.bridge.extract_local_image_text_and_info', return_value="- Gambar (PNG, 1280x720 px):\n  [Teks terbaca pada gambar]: \"PROJECT SHIRO AI v2\""):
                reply, trace = get_shiro_reply(
                    "shiro coba lihat gambar ini",
                    image_base64="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
                    return_trace=True
                )
                self.assertIn("Project Shiro AI v2", reply)
                call_args = mock_llm.create_chat_completion.call_args[1]
                msgs = call_args["messages"]
                # Text model receives OCR and clear prompt instruction
                user_msg = msgs[-1]["content"]
                self.assertIsInstance(user_msg, str)
                self.assertIn("OBSERVASI VISUAL GAMBAR YANG DILAMPIRKAN KAKAK", user_msg)
                self.assertIn("PROJECT SHIRO AI v2", user_msg)
                self.assertIn("shiro coba lihat gambar ini", user_msg)
                # System prompt has visual guidance
                sys_msg = next(m["content"] for m in msgs if m["role"] == "system")
                self.assertIn("PANDUAN PENGAMATAN GAMBAR BARU", sys_msg)

    def test_optimal_tokens_scaling_for_27b_32b(self):
        from shiro.models import get_optimal_model_tokens
        with patch('shiro.models.get_gpu_layers', return_value=33):
            n_ctx, max_out = get_optimal_model_tokens("model/Qwen3.8-27B-Uncensored-Q4_K_M.gguf")
            self.assertEqual(n_ctx, 32768)
            self.assertEqual(max_out, 16384)

    def test_inference_preserves_reasoning_when_inside_think_block(self):
        mock_llm = MagicMock()
        mock_llm.model_path = "model/Qwen3.8-27B-Uncensored-Q4_K_M.gguf"
        # The model generated output solely within <think>...</think>
        mock_llm.create_chat_completion.return_value = {
            "choices": [{
                "message": {"content": "<think>def rewrite_program():\n    return 'sukses'</think>"},
                "finish_reason": "stop"
            }],
            "usage": {}
        }
        with patch.object(state, 'llm', mock_llm):
            reply = get_shiro_reply("coba kamu buat ulang progam semua nya")
            # Should NOT be fake canned greeting!
            self.assertNotIn("Iya Kak? Shiro siap mendengarkan", reply)
            self.assertIn("def rewrite_program():", reply)

if __name__ == "__main__":
    unittest.main()
