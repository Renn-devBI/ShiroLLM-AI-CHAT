# -*- coding: utf-8 -*-
import unittest
import os
import json
import tempfile
from shiro.memory.manager import AdvancedMemoryManager

class TestMemoryManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mem_file = os.path.join(self.temp_dir.name, "test_memory.json")
        self.world_file = os.path.join(self.temp_dir.name, "test_world.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_memory_initialization(self):
        mm = AdvancedMemoryManager(memory_file=self.mem_file, world_file=self.world_file)
        self.assertEqual(mm.system_metadata["total_turns"], 0)
        self.assertEqual(len(mm.short_term_history), 0)

    def test_add_fact_and_save(self):
        mm = AdvancedMemoryManager(memory_file=self.mem_file, world_file=self.world_file)
        mm.add_fact(subject="Kakak", predicate="suka", obj="Shiro", confidence=1.0)
        mm.save_memory()
        
        self.assertTrue(os.path.exists(self.mem_file))
        with open(self.mem_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertGreaterEqual(len(data.get("knowledge_base", {}).get("facts", [])), 1)

    def test_visual_exemplars_filtered_for_visual_queries(self):
        mm = AdvancedMemoryManager(memory_file=self.mem_file, world_file=self.world_file)
        # Rekam pola respon gambar lama (seperti poster)
        mm.record_learned_pattern(
            "[Gambar/Kamera Dikirim] Kakak memperlihatkan gambar poster anime.",
            "Wah poster anime yang keren banget Kakak!",
            image_path="images/poster.jpg"
        )
        # Rekam pola obrolan teks biasa
        mm.record_learned_pattern(
            "Shiro suka sarapan apa?",
            "Shiro suka sarapan roti panggang buatan Kakak!"
        )

        # Ketika user mengirim gambar visual baru, jangan berikan exemplar gambar lama
        visual_exemplars = mm.get_relevant_exemplars("[Gambar/Kamera Dikirim] Kakak memperlihatkan gambar kucing.")
        for ex in visual_exemplars:
            self.assertNotIn("poster", ex.get("assistant", "").lower())
            self.assertFalse(ex.get("image"))

    def test_learned_patterns_deduplication(self):
        # Buat file json dengan pola ganda
        dummy_data = {
            "system_metadata": {"version": "2.0"},
            "knowledge_base": {"facts": []},
            "learned_patterns": [
                {"user": "halo 1", "assistant": "Wah poster tersebut bagus!"},
                {"user": "halo 2", "assistant": "Wah poster tersebut bagus!"}
            ]
        }
        with open(self.mem_file, "w", encoding="utf-8") as f:
            json.dump(dummy_data, f)

        mm = AdvancedMemoryManager(memory_file=self.mem_file, world_file=self.world_file)
        # Harus ter-deduplikasi menjadi 1
        self.assertEqual(len(mm.learned_patterns), 1)

if __name__ == "__main__":
    unittest.main()

