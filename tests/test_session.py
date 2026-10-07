import unittest
import os
import tempfile
import json
from shiro.memory.manager import AdvancedMemoryManager
from shiro.training.exporter import export_data

class TestMultiSessionMemory(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.mem_file = os.path.join(self.temp_dir.name, "test_mem.json")
        self.world_file = os.path.join(self.temp_dir.name, "test_world.json")
        os.environ["SHIRO_TRAINING_DIR"] = os.path.join(self.temp_dir.name, "training_data")
        self.memory = AdvancedMemoryManager(memory_file=self.mem_file, world_file=self.world_file)

    def tearDown(self):
        os.environ.pop("SHIRO_TRAINING_DIR", None)
        self.temp_dir.cleanup()

    def test_session_creation_and_switching(self):
        # Initial session is 'default'
        self.assertEqual(self.memory.active_session_id, "default")
        self.memory.add_message("user", "Pesan di sesi default")
        self.memory.add_message("assistant", "Balasan di sesi default")

        # Create new session
        sess2_id = self.memory.create_new_session("Diskusi Proyek AI")
        self.assertEqual(self.memory.active_session_id, sess2_id)
        self.assertEqual(len(self.memory.short_term_history), 0)

        # Add message to session 2
        self.memory.add_message("user", "Pesan di sesi 2")
        self.memory.add_message("assistant", "Balasan di sesi 2")
        self.assertEqual(len(self.memory.short_term_history), 2)

        # Switch back to default session
        ok = self.memory.switch_session("default")
        self.assertTrue(ok)
        self.assertEqual(self.memory.active_session_id, "default")
        self.assertEqual(len(self.memory.short_term_history), 2)
        self.assertEqual(self.memory.short_term_history[0]["content"], "Pesan di sesi default")

    def test_global_memory_retention_across_sessions(self):
        # Facts and learned patterns should stay global
        self.memory.add_fact(subject="Kakak", predicate="suka", obj="teh hijau hangat")
        sess2_id = self.memory.create_new_session("Obrolan Santai")
        
        # In new session, fact should still be present in knowledge base
        facts_text = " ".join([json.dumps(f) for f in self.memory.knowledge_base["facts"]])
        self.assertIn("teh hijau hangat", facts_text)

    def test_cross_session_recall(self):
        # Session 1: Talk about robotika
        self.memory.add_message("user", "Shiro, kita mau rancang sasis robotika")
        self.memory.add_message("assistant", "Siap Kakak! Shiro bantu rancang sasis aluminium ya.")
        
        # Create Session 2
        sess2 = self.memory.create_new_session("Chat Kedua")
        self.memory.add_message("user", "Halo Shiro di hari baru")
        
        # In Session 2, query referring to earlier chat
        ctx = self.memory.get_cross_session_context("Di chat 1 tadi kita bahas sasis apa ya?")
        self.assertTrue(len(ctx) > 0)
        self.assertIn("sasis", ctx.lower())

    def test_dataset_export_preserves_all_sessions(self):
        # Add messages in session 1
        self.memory.add_message("user", "Pertanyaan di sesi 1")
        self.memory.add_message("assistant", "Jawaban di sesi 1 yang bagus dan panjang")

        # Create session 2 and add messages
        self.memory.create_new_session("Sesi Kedua")
        self.memory.add_message("user", "Pertanyaan di sesi 2")
        self.memory.add_message("assistant", "Jawaban di sesi 2 yang bagus dan panjang")
        self.memory.save_memory()

        # Export dataset using export_data
        output_dir = os.path.join(self.temp_dir.name, "training_export")
        export_data(memory_path=self.mem_file, base_output_dir=output_dir)

        chat_out = os.path.join(output_dir, "chat", "shiro_chatml_train.jsonl")
        self.assertTrue(os.path.exists(chat_out))

        with open(chat_out, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        texts = " ".join([json.dumps(l) for l in lines])
        self.assertIn("Pertanyaan di sesi 1", texts)
        self.assertIn("Pertanyaan di sesi 2", texts)

    def test_delete_session_preserves_training_data_and_facts(self):
        # Create a session and add conversation turn
        sess_id = self.memory.create_new_session("Diskusi Game")
        self.memory.add_message("user", "Kakak sangat suka main game Genshin")
        self.memory.add_message("assistant", "*tersenyum manis* Wah seru banget Kak! Shiro temani ya~")
        self.memory.save_memory()

        # Delete the session
        ok = self.memory.delete_session(sess_id)
        self.assertTrue(ok)
        self.assertNotIn(sess_id, [s["id"] for s in self.memory.get_sessions_list()])

        # Verify archived_training_history preserved the conversation
        archived = getattr(self.memory, "archived_training_history", [])
        self.assertTrue(any("Genshin" in item.get("user", "") for item in archived))

        # Verify learned_patterns preserved the dialogue
        patterns = getattr(self.memory, "learned_patterns", [])
        self.assertTrue(any("Genshin" in p.get("user", "") for p in patterns))

        # Verify export_data exports the deleted session into training dataset
        output_dir = os.path.join(self.temp_dir.name, "training_export_del")
        export_data(memory_path=self.mem_file, base_output_dir=output_dir)
        chat_out = os.path.join(output_dir, "chat", "shiro_chatml_train.jsonl")
        with open(chat_out, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("Genshin", content)

if __name__ == '__main__':
    unittest.main()
