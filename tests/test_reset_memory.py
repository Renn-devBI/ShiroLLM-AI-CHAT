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

    def test_clean_training_directory(self):
        from shiro.memory.drive_sync import clean_training_directory, count_training_samples
        train_folder = os.path.join(self.test_dir, "test_train")
        os.makedirs(os.path.join(train_folder, "chat"), exist_ok=True)
        os.makedirs(os.path.join(train_folder, "vision", "images"), exist_ok=True)

        alpaca_file = os.path.join(train_folder, "chat", "shiro_alpaca_train.json")
        with open(alpaca_file, "w", encoding="utf-8") as f:
            json.dump([{"instruction": "hi", "output": "halo"}], f)

        img_file = os.path.join(train_folder, "vision", "images", "sample.jpg")
        with open(img_file, "w", encoding="utf-8") as f:
            f.write("fake_img_bytes")

        gitkeep_file = os.path.join(train_folder, ".gitkeep")
        with open(gitkeep_file, "w", encoding="utf-8") as f:
            f.write("")

        self.assertEqual(count_training_samples(train_folder), 1)

        cleaned = clean_training_directory(train_folder)
        self.assertTrue(cleaned >= 2)

        # Verify json is now empty list []
        with open(alpaca_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data, [])

        # Verify image was deleted
        self.assertFalse(os.path.exists(img_file))

        # Verify .gitkeep was preserved
        self.assertTrue(os.path.exists(gitkeep_file))
        self.assertEqual(count_training_samples(train_folder), 0)

    def test_reset_drive_memory_cleans_training_by_default(self):
        # Create mock drive training data
        drive_train = os.path.join(self.mock_drive, "training_data")
        os.makedirs(drive_train, exist_ok=True)
        drive_alpaca = os.path.join(drive_train, "shiro_alpaca_train.json")
        with open(drive_alpaca, "w", encoding="utf-8") as f:
            json.dump([{"instruction": "q1", "output": "a1"}, {"instruction": "q2", "output": "a2"}], f)

        # Create local training data
        os.makedirs("training_data", exist_ok=True)
        local_alpaca = os.path.join("training_data", "shiro_alpaca_train.json")
        with open(local_alpaca, "w", encoding="utf-8") as f:
            json.dump([{"instruction": "local_q", "output": "local_a"}], f)

        res = reset_drive_memory(
            drive_dir=self.mock_drive,
            backup=True,
            clean_training=True,
            notify_server=False
        )

        self.assertTrue(res["success"])
        self.assertTrue(res["training_cleaned"])
        self.assertGreaterEqual(res["training_samples_cleared"], 2)

        # Verify drive training file is emptied to []
        with open(drive_alpaca, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f), [])

        # Verify local training file is emptied to []
        with open(local_alpaca, "r", encoding="utf-8") as f:
            self.assertEqual(json.load(f), [])

        # Verify backup of training data exists
        backup_files = res["backup_info"]["backup_files"]
        has_train_backup = any("training_data_backup" in b for b in backup_files)
        self.assertTrue(has_train_backup)

if __name__ == "__main__":
    unittest.main()

