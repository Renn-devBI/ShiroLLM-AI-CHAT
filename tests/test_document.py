import unittest
import os
import tempfile
from shiro.document.reader import (
    extract_text_from_file,
    extract_text_from_folder,
    detect_document_intent,
    build_document_prompt,
    SUPPORTED_EXTENSIONS
)
from shiro.memory.optimization import (
    estimate_tokens,
    calculate_messages_tokens,
    trim_text_to_token_budget
)

class TestDocumentReader(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_extract_text_file(self):
        sample_path = os.path.join(self.temp_dir.name, "catatan.txt")
        with open(sample_path, "w", encoding="utf-8") as f:
            f.write("Halo Shiro! Ini catatan penting tentang proyek.")

        res = extract_text_from_file(sample_path)
        self.assertTrue(res["success"])
        self.assertEqual(res["file_type"], "txt")
        self.assertIn("catatan penting", res["text"])

    def test_extract_csv_file(self):
        sample_path = os.path.join(self.temp_dir.name, "data.csv")
        with open(sample_path, "w", encoding="utf-8") as f:
            f.write("Nama,Nilai\nShiro,100\nKakak,100")

        res = extract_text_from_file(sample_path)
        self.assertTrue(res["success"])
        self.assertEqual(res["file_type"], "csv")
        self.assertIn("Shiro,100", res["text"])

    def test_extract_non_existent(self):
        res = extract_text_from_file(os.path.join(self.temp_dir.name, "tidak_ada.txt"))
        self.assertFalse(res["success"])
        self.assertEqual(res["text"], "")

    def test_detect_document_intent(self):
        self.assertEqual(detect_document_intent("Shiro tolong rangkum artikel ini"), "summarize")
        self.assertEqual(detect_document_intent("Bisa ringkas poin penting dokumen ini?"), "summarize")
        self.assertEqual(detect_document_intent("Tolong perbaiki tata bahasa file ini"), "proofread")
        self.assertEqual(detect_document_intent("Cek salah ketik atau typo di teks ini"), "proofread")
        self.assertEqual(detect_document_intent("Siapa penulis dokumen ini?"), "qa")

    def test_build_document_prompt(self):
        doc_info = {
            "filename": "laporan.txt",
            "text": "Konten laporan kuartal pertama."
        }
        prompt_sum = build_document_prompt(doc_info, "Tolong rangkum ya")
        self.assertIn("PANDUAN MERANGKUM", prompt_sum)
        self.assertIn("laporan.txt", prompt_sum)

        prompt_fix = build_document_prompt(doc_info, "Tolong perbaiki kata-katanya")
        self.assertIn("PANDUAN MEMPERBAIKI", prompt_fix)

    def test_extract_text_from_folder(self):
        sub_folder = os.path.join(self.temp_dir.name, "sub_docs")
        os.makedirs(sub_folder, exist_ok=True)
        with open(os.path.join(sub_folder, "doc1.txt"), "w", encoding="utf-8") as f:
            f.write("Dokumen pertama.")
        with open(os.path.join(sub_folder, "doc2.md"), "w", encoding="utf-8") as f:
            f.write("# Dokumen Kedua")

        res = extract_text_from_folder(sub_folder)
        self.assertTrue(res["success"])
        self.assertEqual(res["file_count"], 2)
        self.assertIn("Dokumen pertama", res["text"])
        self.assertIn("Dokumen Kedua", res["text"])

    def test_document_max_chars_truncation(self):
        sample_path = os.path.join(self.temp_dir.name, "long_doc.txt")
        long_text = "Kata ini berulang. " * 500  # ~9500 chars
        with open(sample_path, "w", encoding="utf-8") as f:
            f.write(long_text)

        res = extract_text_from_file(sample_path, max_chars=1000)
        self.assertTrue(res["success"])
        self.assertTrue(res["truncated"])
        self.assertTrue(len(res["text"]) < 1200)
        self.assertIn("dipotong", res["text"])

    def test_token_estimation_and_budget_trimming(self):
        sample_text = "Shiro adalah adik yang cerdas dan setia menemani Kakak bermain game di akhir pekan."
        tokens = estimate_tokens(sample_text)
        self.assertGreater(tokens, 10)
        self.assertLess(tokens, 100)

        very_long_text = "Ini adalah paragraf cerita yang panjang sekali untuk pengujian memori AI. " * 100
        trimmed = trim_text_to_token_budget(very_long_text, max_tokens=150)
        self.assertLess(estimate_tokens(trimmed), 170)
        self.assertIn("dipotong", trimmed)

    def test_calculate_messages_tokens(self):
        msgs = [
            {"role": "system", "content": "Kamu adalah Shiro."},
            {"role": "user", "content": "Halo Shiro!"},
            {"role": "assistant", "content": "Halo juga Kakak tersayang!"}
        ]
        total_tokens = calculate_messages_tokens(msgs)
        self.assertGreater(total_tokens, 15)
        self.assertLess(total_tokens, 100)

if __name__ == '__main__':
    unittest.main()
