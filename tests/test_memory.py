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

if __name__ == "__main__":
    unittest.main()
