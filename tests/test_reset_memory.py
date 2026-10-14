# -*- coding: utf-8 -*-
"""
Unit tests for Shiro Drive memory reset and backup features
"""

import os
import sys
import json
import shutil
import tempfile
import unittest

from shiro.memory.drive_sync import (
    get_pristine_memory_data,
    get_pristine_world_data,
    create_memory_backup,
    reset_drive_memory,
    get_drive_memory_status
)

class TestResetDriveMemory(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="shiro_test_reset_")
        self.mock_drive = os.path.join(self.test_dir, "mock_drive")
        os.makedirs(self.mock_drive, exist_ok=True)
        self.orig_cwd = os.getcwd()
        os.chdir(self.test_dir)

    def tearDown(self):
        os.chdir(self.orig_cwd)
        if os.path.exists(self.test_dir):
            try:
                shutil.rmtree(self.test_dir)
            except Exception:
                pass

    def test_get_pristine_memory_data(self):
        data = get_pristine_memory_data(user_name="Kakak")
        self.assertEqual(data["system_metadata"]["total_turns"], 0)
        self.assertEqual(len(data["knowledge_base"]["facts"]), 0)
        self.assertEqual(len(data["short_term_history"]), 0)
        self.assertEqual(data["user_profile"]["name"], "Kakak")
        self.assertIn("default", data["sessions_store"])

    def test_get_pristine_memory_keep_profile(self):
        existing = {
            "user_profile": {
                "name": "Kakak Senior",
                "preferences": {"favorite_food": "Ramen"}
            },
            "knowledge_base": {"facts": [{"subject": "A", "predicate": "is", "object": "B"}]}
        }
        data = get_pristine_memory_data(user_name="Kakak", keep_profile=True, existing_data=existing)
        self.assertEqual(data["user_profile"]["name"], "Kakak Senior")
        self.assertEqual(data["user_profile"]["preferences"]["favorite_food"], "Ramen")
        self.assertEqual(len(data["knowledge_base"]["facts"]), 0)

    def test_create_memory_backup(self):
        old_memory = {
            "system_metadata": {"total_turns": 42},
            "knowledge_base": {"facts": [{"subject": "Old", "predicate": "fact", "object": "hallucination"}]}
        }
        drive_file = os.path.join(self.mock_drive, "ingatan_shiro.json")
        with open(drive_file, "w", encoding="utf-8") as f:
            json.dump(old_memory, f)

        res = create_memory_backup(drive_dir=self.mock_drive, include_world=False)
        self.assertTrue(res["success"])
        self.assertTrue(len(res["backup_files"]) > 0)
        backup_path = res["backup_files"][0]
        self.assertTrue(os.path.exists(backup_path))
        with open(backup_path, "r", encoding="utf-8") as f:
            backed_data = json.load(f)
        self.assertEqual(backed_data["system_metadata"]["total_turns"], 42)

    def test_reset_drive_memory_flow(self):
        # Setup existing memory with 3 facts in mock drive
        old_memory = {
            "system_metadata": {"total_turns": 15, "user_name": "Kakak"},
            "knowledge_base": {"facts": [
                {"subject": "A", "predicate": "B", "object": "C"},
                {"subject": "D", "predicate": "E", "object": "F"},
                {"subject": "G", "predicate": "H", "object": "I"}
            ]},
            "short_term_history": [{"role": "user", "content": "hi"}]
        }
        drive_mem_file = os.path.join(self.mock_drive, "ingatan_shiro.json")
        with open(drive_mem_file, "w", encoding="utf-8") as f:
            json.dump(old_memory, f)

        res = reset_drive_memory(
            drive_dir=self.mock_drive,
            backup=True,
            reset_world=True,
            notify_server=False
        )

        self.assertTrue(res["success"])
        self.assertEqual(res["facts_cleared"], 3)
        self.assertEqual(res["turns_cleared"], 15)
        self.assertTrue(res["drive_reset"])
        self.assertTrue(res["local_reset"])
        self.assertTrue(res["world_reset"])

        # Check drive file is now clean
        with open(drive_mem_file, "r", encoding="utf-8") as f:
            clean_drive = json.load(f)
        self.assertEqual(len(clean_drive["knowledge_base"]["facts"]), 0)
        self.assertEqual(clean_drive["system_metadata"]["total_turns"], 0)

        # Check local file is also clean
        self.assertTrue(os.path.exists("ingatan_shiro.json"))
        with open("ingatan_shiro.json", "r", encoding="utf-8") as f:
            clean_local = json.load(f)
        self.assertEqual(len(clean_local["knowledge_base"]["facts"]), 0)

        # Check backup file exists
        self.assertTrue(len(res["backup_info"]["backup_files"]) > 0)

    def test_get_drive_memory_status(self):
        mem = {
            "system_metadata": {"total_turns": 5, "user_name": "Kakak Test"},
            "knowledge_base": {"facts": [{"subject": "X", "predicate": "Y", "object": "Z"}]}
        }
        drive_mem_file = os.path.join(self.mock_drive, "ingatan_shiro.json")
        with open(drive_mem_file, "w", encoding="utf-8") as f:
            json.dump(mem, f)

        status = get_drive_memory_status(drive_dir=self.mock_drive)
        self.assertTrue(status["drive_connected"])
        self.assertEqual(status["drive_stats"]["facts"], 1)
        self.assertEqual(status["drive_stats"]["turns"], 5)
        self.assertEqual(status["drive_stats"]["user_name"], "Kakak Test")

if __name__ == "__main__":
    unittest.main()
