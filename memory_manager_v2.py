# -*- coding: utf-8 -*-
"""
Advanced Memory System v2.0
Sophisticated memory tracking for Shiro LLMA

Features:
- User profile extraction
- Agent emotional state tracking
- RDF-like knowledge base
- Episodic memory (session summaries)
- Short-term conversation history
"""

import json
import os
import re
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Any, Optional
import hashlib
import threading
import shutil

class AdvancedMemoryManager:
    """Enhanced memory management system with sophisticated tracking"""
    
    def __init__(self, memory_file: str = "ingatan_shiro.json", world_file: str = "isekai_world.json"):
        self.lock = threading.RLock()
        self.memory_file = memory_file
        self.world_file = world_file
        # Deteksi otomatis Google Drive jika berjalan di Colab
        self.drive_dir = os.environ.get("SHIRO_DRIVE_DIR")
        if not self.drive_dir and os.path.exists("/content/drive/MyDrive/Shiro_Memory"):
            self.drive_dir = "/content/drive/MyDrive/Shiro_Memory"
        self.initialize_memory()
        self.load_world()
        self.load_memory()
    
    def initialize_memory(self):
        """Initialize empty memory structure"""
        self.system_metadata = {
            "version": "2.0",
            "created_date": datetime.now().isoformat(),
            "last_interaction": None,
            "total_turns": 0,
            "token_usage_approx": 0,
            "session_count": 0,
            "user_name": "Kakak"
        }
        
        self.user_profile = {
            "name": "Kakak",
            "aliases": [],
            "personality_traits": [],
            "preferences": {
                "interaction_style": "",
                "favorite_topics": [],
                "dislikes": []
            },
            "relationship_info": {
                "role": "User",
                "importance": "High"
            }
        }
        
        self.agent_persona = {
            "name": "Shiro",
            "current_mood": "Neutral & Menunggu",
            "emotional_state": {
                "happiness": 50,
                "anxiety": 0,
                "arousal": 0,
                "confidence": 50,
                "longing": 0
            },
            "relationship_status": {
                "label": "Unknown",
                "intimacy_level": 0,
                "commitment": ""
            },
            "internal_thought": "",
            "recent_actions": []
        }
        
        self.knowledge_base = {
            "facts": [],      # RDF triplets
            "concepts": {},   # Semantic concepts
            "relationships": {} # Entity relationships
        }
        
        self.episodic_memory = {
            "sessions": []    # Session summaries
        }
        
        self.learned_patterns = [
            {
                "user": "apakah kamu merindukan kakak?",
                "assistant": "*tersenyum manis dan memeluk lengan Kakak* Tentu saja Shiro rindu banget sama Kakak! Jangan tinggalin Shiro lama-lama lagi ya~ >//<",
                "keywords": ["rindu", "merindukan", "kakak"],
                "quality": 1.0,
                "timestamp": datetime.now().isoformat()
            },
            {
                "user": "Shiro mau makan apa?",
                "assistant": "*mata berbinar* Mau masakan Kakak! Apa aja yang Kakak bikin pasti enak banget! Shiro bantu siapin piringnya ya~",
                "keywords": ["makan", "laper", "masak"],
                "quality": 1.0,
                "timestamp": datetime.now().isoformat()
            }
        ]
        
        self.short_term_history = []  # Recent messages
        self.MAX_SHORT_TERM = 25
        
        # World/Setting data
        self.world = {
            "world_name": "Arcadia",
            "locations": {
                "home": "Pondok Kayu",
                "visited": []
            },
            "shiro_role": "Adik (Brocon)",
            "relationship_level": 1,
            "shared_memories": []
        }
    
    def load_world(self):
        """Load world/setting dari file atau gunakan default"""
        if self.drive_dir and os.path.exists(self.drive_dir):
            drive_world = os.path.join(self.drive_dir, os.path.basename(self.world_file))
            if os.path.exists(drive_world) and not os.path.exists(self.world_file):
                try:
                    shutil.copy2(drive_world, self.world_file)
                except Exception:
                    pass
        if os.path.exists(self.world_file):
            try:
                with open(self.world_file, 'r', encoding='utf-8') as f:
                    loaded_world = json.load(f)
                    self.world.update(loaded_world)
            except Exception as e:
                print(f"Warning: Could not load world file: {e}")
    
    def load_memory(self):
        """Load memory from file"""
        # Pulihkan ingatan dari Google Drive jika ada dan lokal belum ada atau lebih usang
        if self.drive_dir and os.path.exists(self.drive_dir):
            drive_mem = os.path.join(self.drive_dir, os.path.basename(self.memory_file))
            if os.path.exists(drive_mem):
                should_restore = not os.path.exists(self.memory_file) or (
                    os.path.getsize(drive_mem) > os.path.getsize(self.memory_file) and os.path.getsize(self.memory_file) < 500
                )
                if should_restore:
                    try:
                        shutil.copy2(drive_mem, self.memory_file)
                        print(f"[Memory] Memori dipulihkan dari Google Drive: {drive_mem}")
                    except Exception as e_res:
                        print(f"Warning: Gagal memulihkan ingatan dari Google Drive: {e_res}")
        if os.path.exists(self.memory_file):
            try:
                with open(self.memory_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Support both v1 and v2 formats
                if "system_metadata" in data:
                    # v2 format
                    self.system_metadata = data.get("system_metadata", self.system_metadata)
                    self.user_profile = data.get("user_profile", self.user_profile)
                    self.agent_persona = data.get("agent_persona", self.agent_persona)
                    self.knowledge_base = data.get("knowledge_base", self.knowledge_base)
                    
                    # Handle episodic_memory with both "sessions" and "summaries" keys
                    episodic_data = data.get("episodic_memory", {})
                    if "sessions" in episodic_data:
                        self.episodic_memory = episodic_data
                    elif "summaries" in episodic_data:
                        # Migrate from old format
                        self.episodic_memory = {"sessions": []}
                    else:
                        self.episodic_memory = self.episodic_memory
                    
                    loaded_patterns = data.get("learned_patterns", getattr(self, "learned_patterns", []))
                    clean_patterns = []
                    for p in loaded_patterns:
                        a_txt = p.get("assistant", "").lower()
                        if "<think>" in a_txt or "</think>" in a_txt or "let me break this down" in a_txt or "possible responses" in a_txt:
                            continue
                        clean_patterns.append(p)
                    self.learned_patterns = clean_patterns
                    self.short_term_history = data.get("short_term_history", [])
                else:
                    # v1 format - migrate
                    self._migrate_from_v1(data)
                    
            except Exception as e:
                print(f"Warning: Could not load memory: {e}")
                print("Starting with fresh memory")
        
        # Otomatis baca data training (Alpaca/ShareGPT) dari folder training_data atau Google Drive
        self.load_training_data()
    
    def load_training_data(self, training_dir: str = "training_data"):
        """Load and integrate fine-tuning dataset / training pairs into Shiro's active learned patterns"""
        # Pulihkan dataset training dari Google Drive jika ada di Drive dan lokal kosong/lama
        if self.drive_dir and os.path.exists(self.drive_dir):
            drive_train = os.path.join(self.drive_dir, "training_data")
            if os.path.exists(drive_train):
                if not os.path.exists(training_dir) or len(os.listdir(training_dir)) == 0:
                    try:
                        shutil.copytree(drive_train, training_dir, dirs_exist_ok=True)
                        print(f"[Memory] Dataset training dipulihkan dari Google Drive: {drive_train}")
                    except Exception as e_cp:
                        print(f"Warning: Gagal menyalin dataset dari Drive: {e_cp}")

        if not os.path.exists(training_dir):
            return

        loaded_count = 0
        existing_users = {p.get("user", "").strip().lower() for p in getattr(self, "learned_patterns", [])}

        candidate_files = [
            os.path.join(training_dir, "shiro_alpaca_train.json"),
            os.path.join(training_dir, "chat", "shiro_alpaca_train.json"),
            os.path.join(training_dir, "vision", "shiro_vision_alpaca.json"),
            os.path.join(training_dir, "shiro_sharegpt_train.json"),
            os.path.join(training_dir, "chat", "shiro_sharegpt_train.json"),
            os.path.join(training_dir, "vision", "shiro_vision_sharegpt.json"),
        ]

        for filepath in candidate_files:
            if not os.path.exists(filepath):
                continue
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    samples = json.load(f)
                if not isinstance(samples, list):
                    continue
                for item in samples:
                    u, a, img = None, None, None
                    # Format Alpaca
                    if "instruction" in item and "output" in item:
                        u = (item.get("instruction") or "").strip()
                        a = (item.get("output") or "").strip()
                        img = item.get("image")
                    # Format ShareGPT
                    elif "conversations" in item:
                        convs = item.get("conversations", [])
                        for i in range(len(convs) - 1):
                            if convs[i].get("from") in ["human", "user"] and convs[i+1].get("from") in ["gpt", "assistant"]:
                                u = convs[i].get("value", "").strip()
                                a = convs[i+1].get("value", "").strip()
                                img = item.get("image")
                                break
                    if not u or not a:
                        continue
                    # Bersihkan tag <image> jika ada di teks
                    u_clean = re.sub(r'<image>\s*', '', u).strip()
                    if not u_clean:
                        continue
                    u_lower = u_clean.lower()
                    if u_lower not in existing_users:
                        keywords = list(set(re.findall(r'\b\w{3,}\b', u_lower)))
                        pattern = {
                            "user": u_clean,
                            "assistant": a,
                            "keywords": keywords,
                            "quality": 1.0,
                            "timestamp": datetime.now().isoformat(),
                            "source": "training_data"
                        }
                        if img:
                            pattern["image"] = img
                        self.learned_patterns.append(pattern)
                        existing_users.add(u_lower)
                        loaded_count += 1
            except Exception as e:
                print(f"Warning: Gagal memuat file training {filepath}: {e}")

        # Batas maksimal pola pembelajaran diperluas hingga 500
        if len(self.learned_patterns) > 500:
            self.learned_patterns = self.learned_patterns[-500:]

        if loaded_count > 0:
            print(f"[Memory] [Training] {loaded_count} data training baru berhasil dimuat & diintegrasikan ke memori aktif Shiro!")
    
    def _migrate_from_v1(self, old_data: Dict):
        """Migrate from v1 format to v2"""
        print("[Memory] Migrating from v1 to v2 format...")
        
        conversations = old_data.get("conversations", [])
        
        # Extract user profile from conversations
        self._extract_user_profile(conversations)
        
        # Extract facts from conversations
        self._extract_facts_from_conversations(conversations)
        
        # Move conversations to short_term_history
        self.short_term_history = conversations[-self.MAX_SHORT_TERM:]
        
        # Create session from old data
        if conversations:
            session = {
                "session_id": self._generate_session_id(),
                "start_time": conversations[0].get("timestamp"),
                "end_time": conversations[-1].get("timestamp"),
                "turn_count": len(conversations),
                "summary": "Migrated from v1 format",
                "key_moments": [],
                "emotional_arc": [],
                "topics": []
            }
            self.episodic_memory["sessions"].append(session)
        
        self.system_metadata["total_turns"] = len(conversations)
    
    def _extract_user_profile(self, conversations: List[Dict]):
        """Extract user profile from conversation history"""
        user_messages = [m for m in conversations if m.get("role") == "user"]
        assistant_messages = [m for m in conversations if m.get("role") == "assistant"]
        
        # Extract name references from conversations
        names = set()
        names.add("Kakak")  # Default name
        
        # Extract aliases
        aliases = set()
        for msg in user_messages:
            content = msg.get("content", "").lower()
            if "kaka" in content:
                aliases.add("Kaka")
            if "onii" in content or "oni" in content:
                aliases.add("Onii-chan")
        
        # Also check assistant messages for how they address the user
        for msg in assistant_messages:
            content = msg.get("content", "").lower()
            if "kaka" in content:
                aliases.add("Kaka")
        
        self.user_profile["aliases"] = list(aliases)
        
        # Detect personality traits from language patterns
        traits = self._detect_personality_traits(user_messages)
        self.user_profile["personality_traits"] = traits if traits else ["Affectionate"]
        
        # Detect interaction preferences
        style = self._detect_interaction_style(user_messages)
        if style:
            self.user_profile["preferences"]["interaction_style"] = style
        else:
            self.user_profile["preferences"]["interaction_style"] = "Warm & Affectionate"
    
    def _detect_personality_traits(self, messages: List[Dict]) -> List[str]:
        """Detect personality traits from messages"""
        traits = []
        combined_text = " ".join([m.get("content", "").lower() for m in messages])
        
        # Pattern matching for traits
        trait_patterns = {
            "Patient": r"(sabar|tenang|menunggu)",
            "Teasing": r"(gombalin|gombalan|menggoda)",
            "Affectionate": r"(sayang|cinta|kasih|peluk|cium)",
            "Direct": r"(jelas|langsung|intinya)",
            "Curious": r"(tanya|penasaran|apa|kenapa)",
            "Romantic": r"(romantis|cinta|selamanya|selamanya)"
        }
        
        for trait, pattern in trait_patterns.items():
            if re.search(pattern, combined_text):
                traits.append(trait)
        
        return traits
    
    def _detect_interaction_style(self, messages: List[Dict]) -> str:
        """Detect interaction style from messages"""
        combined_text = " ".join([m.get("content", "").lower() for m in messages])
        
        if re.search(r"(romantis|sayang|cinta|kasih)", combined_text):
            return "Romantic & Affectionate"
        elif re.search(r"(direct|jelas|singkat)", combined_text):
            return "Direct & Clear"
        elif re.search(r"(gombalan|menggoda|main)", combined_text):
            return "Playful & Teasing"
        
        return ""
    
    def _extract_facts_from_conversations(self, conversations: List[Dict]):
        """Extract RDF-like facts from conversations"""
        for msg in conversations:
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            # Simple pattern-based fact extraction
            facts = self._extract_rdf_facts(content, role)
            self.knowledge_base["facts"].extend(facts)
    
    def _extract_rdf_facts(self, text: str, actor: str) -> List[Dict]:
        """Extract RDF triplets from text"""
        facts = []
        text_lower = text.lower()
        
        # Pattern-based extraction with higher coverage
        patterns = [
            # Love/affection patterns
            (r"(kakak|shiro)\s+(sayang|cinta|mahal|percaya|kangen|rindu)\s+(.+?)(?=[.!?,]|$)", 
             lambda m: {
                 "subject": m.group(1).capitalize(), 
                 "predicate": m.group(2), 
                 "object": m.group(3).strip(),
                 "confidence": 0.95
             }),
            
            # Expression patterns (expressed, told, said)
            (r"(kakak|shiro)\s+(mengungkapkan|bilang|katakan|express)\s+(.+?)(?=[.!?,]|$)",
             lambda m: {
                 "subject": m.group(1).capitalize(),
                 "predicate": "expressed",
                 "object": m.group(3).strip(),
                 "confidence": 0.9
             }),
            
            # Want/desire patterns
            (r"(kakak|shiro)\s+(ingin|mau|pengin|want)\s+(.+?)(?=[.!?,]|$)",
             lambda m: {
                 "subject": m.group(1).capitalize(),
                 "predicate": "wants",
                 "object": m.group(3).strip(),
                 "confidence": 0.85
             }),
            
            # Action patterns
            (r"(kakak|shiro)\s+(memeluk|memberi|memberikan|mengajak)\s+(.+?)(?=[.!?,]|$)",
             lambda m: {
                 "subject": m.group(1).capitalize(),
                 "predicate": m.group(2),
                 "object": m.group(3).strip(),
                 "confidence": 0.85
             }),
            
            # Is/being patterns
            (r"(kakak|shiro)\s+(adalah|ialah|merupakan|jadi)\s+(.+?)(?=[.!?,]|$)",
             lambda m: {
                 "subject": m.group(1).capitalize(),
                 "predicate": "is_a",
                 "object": m.group(3).strip(),
                 "confidence": 0.8
             }),
            
            # Promise & commitment patterns
            (r"(kakak|shiro)\s+(janji|berjanji)\s+(.+?)(?=[.!?,]|$)",
             lambda m: {
                 "subject": m.group(1).capitalize(),
                 "predicate": "berjanji",
                 "object": m.group(3).strip(),
                 "confidence": 0.95
             }),
            
            # Likes & preferences patterns
            (r"(kakak|shiro)\s+(suka|senang|gemar|favorit)\s+(.+?)(?=[.!?,]|$)",
             lambda m: {
                 "subject": m.group(1).capitalize(),
                 "predicate": "suka",
                 "object": m.group(3).strip(),
                 "confidence": 0.9
             }),
            
            # Dislikes patterns
            (r"(kakak|shiro)\s+(tidak suka|benci|gak suka|enggan)\s+(.+?)(?=[.!?,]|$)",
             lambda m: {
                 "subject": m.group(1).capitalize(),
                 "predicate": "tidak suka",
                 "object": m.group(3).strip(),
                 "confidence": 0.9
             }),
        ]
        
        for pattern, extractor in patterns:
            matches = re.finditer(pattern, text_lower, re.IGNORECASE)
            for match in matches:
                try:
                    fact = extractor(match)
                    fact["source"] = f"{actor}_dialog"
                    
                    # Only add if object is not too long or too short
                    if 3 < len(fact.get("object", "")) < 100:
                        facts.append(fact)
                except:
                    pass
        
        return facts
    
    def add_message(self, role: str, content: str, emotion: str = "neutral", image_path: Optional[str] = None):
        """Add message to short-term history and self-learn from conversation & response"""
        with self.lock:
            message = {
                "role": role,
                "content": content,
                "timestamp": datetime.now().isoformat(),
                "emotion": emotion,
                "keywords": self._extract_keywords(content)
            }
            if image_path:
                message["image"] = image_path
            
            if role == "assistant":
                message["actions"] = self._extract_actions(content)
            
            self.short_term_history.append(message)
            
            # Keep only recent messages
            if len(self.short_term_history) > self.MAX_SHORT_TERM:
                self.short_term_history = self.short_term_history[-self.MAX_SHORT_TERM:]
            
            # Update metadata
            self.system_metadata["last_interaction"] = message["timestamp"]
            self.system_metadata["total_turns"] += 1
            
            # Continuous Self-Learning: Extract facts from both user and assistant
            facts = self._extract_rdf_facts(content, role)
            existing_keys = set()
            for f in self.knowledge_base["facts"]:
                key = (f.get("subject", "").lower(), f.get("predicate", "").lower(), f.get("object", "").lower())
                existing_keys.add(key)
            for fact in facts:
                key = (fact.get("subject", "").lower(), fact.get("predicate", "").lower(), fact.get("object", "").lower())
                if key not in existing_keys:
                    self.knowledge_base["facts"].append(fact)
                    existing_keys.add(key)
            
            # Also learn user preferences dynamically
            if role == "user":
                content_lower = content.lower()
                for match in re.finditer(r"(?:aku|saya|kakak)\s+(?:suka|senang|gemar)\s+([a-zA-Z0-9\s]{3,30})(?=[.!?,]|$)", content_lower):
                    fav = match.group(1).strip()
                    if fav and fav not in self.user_profile["preferences"].get("favorite_topics", []):
                        self.user_profile["preferences"].setdefault("favorite_topics", []).append(fav)
                for match in re.finditer(r"(?:aku|saya|kakak)\s+(?:tidak suka|benci|gak suka)\s+([a-zA-Z0-9\s]{3,30})(?=[.!?,]|$)", content_lower):
                    dislike = match.group(1).strip()
                    if dislike and dislike not in self.user_profile["preferences"].get("dislikes", []):
                        self.user_profile["preferences"].setdefault("dislikes", []).append(dislike)
            
            # Limit facts to max 50, remove oldest if exceeded
            if len(self.knowledge_base["facts"]) > 50:
                self.knowledge_base["facts"] = self.knowledge_base["facts"][-50:]
            
            # Update emotions if assistant message
            if role == "assistant":
                self.update_emotional_state_from_response(content)
    
    def _extract_keywords(self, text: str) -> List[str]:
        """Extract important keywords from text"""
        # Remove stopwords
        stopwords = {
            'yang', 'ini', 'itu', 'dan', 'di', 'ke', 'dari', 'untuk', 'pada',
            'adalah', 'dengan', 'tidak', 'juga', 'saya', 'kamu', 'nya', 'ya'
        }
        
        words = re.findall(r'\b\w+\b', text.lower())
        keywords = [w for w in words if len(w) > 2 and w not in stopwords]
        return list(set(keywords))[:5]  # Return top 5 unique
    
    def _extract_actions(self, text: str) -> List[str]:
        """Extract actions from assistant response (text within asterisks)"""
        actions = re.findall(r'\*([^*]+)\*', text)
        return actions
    
    def update_emotional_state_from_response(self, response: str):
        """Update AI emotional state based on response content"""
        content_lower = response.lower()
        
        # Happiness detection
        if any(word in content_lower for word in ['hehe', 'tersenyum', 'tertawa', 'bahagia', 'senang']):
            self.agent_persona["emotional_state"]["happiness"] += 15
        
        # Longing/Rindu detection (Indonesian)
        if any(word in content_lower for word in ['kangen', 'rindu', 'rindu banget', 'kangen banget']):
            self.agent_persona["emotional_state"]["longing"] = self.agent_persona["emotional_state"].get("longing", 0) + 20
        
        # Anxiety detection
        if any(word in content_lower for word in ['cemas', 'khawatir', 'takut', 'gugup', 'khawatir']):
            self.agent_persona["emotional_state"]["anxiety"] += 10
        
        # Affection detection (romantic content)
        if any(word in content_lower for word in ['peluk', 'cium', 'sayang', 'cinta', 'mahal', 'erat-erat']):
            self.agent_persona["emotional_state"]["arousal"] = self.agent_persona["emotional_state"].get("arousal", 0) + 15
        
        # Confidence detection
        if any(word in content_lower for word in ['percaya', 'yakin', 'pasti', 'jaga']):
            self.agent_persona["emotional_state"]["confidence"] += 10
        
        # Ensure longing exists in emotional_state
        if "longing" not in self.agent_persona["emotional_state"]:
            self.agent_persona["emotional_state"]["longing"] = 50
        
        # Clamp values between 0-100
        for emotion in self.agent_persona["emotional_state"]:
            self.agent_persona["emotional_state"][emotion] = max(0, min(100, 
                self.agent_persona["emotional_state"][emotion]))
    
    def set_agent_mood(self, mood: str):
        """Set current mood of agent"""
        self.agent_persona["current_mood"] = mood
    
    def update_mood_from_emotions(self):
        """Update mood based on current emotional state"""
        emotions = self.agent_persona["emotional_state"]
        
        mood_parts = []
        
        # Check dominant emotions
        if emotions.get("longing", 0) > 70:
            mood_parts.append("Sangat Rindu")
        elif emotions.get("longing", 0) > 40:
            mood_parts.append("Rindu")
        
        if emotions.get("happiness", 0) > 70:
            mood_parts.append("Ceria")
        elif emotions.get("happiness", 0) < 30:
            mood_parts.append("Sedih")
        
        if emotions.get("arousal", 0) > 60:
            mood_parts.append("Manja")
        
        if emotions.get("anxiety", 0) > 50:
            mood_parts.append("Cemas")
        
        if mood_parts:
            self.agent_persona["current_mood"] = " & ".join(mood_parts[:2])
        else:
            self.agent_persona["current_mood"] = "Neutral"
    
    def set_internal_thought(self, thought: str):
        """Set internal thought of agent"""
        self.agent_persona["internal_thought"] = thought
    
    def update_relationship_status(self, label: str, intimacy: int, commitment: str):
        """Update relationship status"""
        self.agent_persona["relationship_status"] = {
            "label": label,
            "intimacy_level": min(100, max(0, intimacy)),
            "commitment": commitment
        }
    
    def create_session_summary(self, session_id: Optional[str] = None) -> Dict:
        """Create summary of current session"""
        if not self.short_term_history:
            return {}
        
        session = {
            "session_id": session_id or self._generate_session_id(),
            "start_time": self.short_term_history[0]["timestamp"],
            "end_time": self.short_term_history[-1]["timestamp"],
            "turn_count": len(self.short_term_history),
            "summary": self._generate_summary(),
            "key_moments": self._extract_key_moments(),
            "emotional_arc": self._trace_emotion_progression(),
            "topics": self._extract_topics()
        }
        
        return session
    
    def _generate_summary(self) -> str:
        """Generate text summary of session"""
        if not self.short_term_history:
            return ""
        
        user_msgs = [m["content"] for m in self.short_term_history if m["role"] == "user"]
        assistant_msgs = [m["content"] for m in self.short_term_history if m["role"] == "assistant"]
        
        # Build summary with context
        summary = f"Percakapan bermakna antara Kakak dan Shiro dengan {len(user_msgs)} pesan dari Kakak dan {len(assistant_msgs)} respons dari Shiro."
        
        # Extract and add key moments
        key_moments = []
        for msg in assistant_msgs:
            content_lower = msg.lower()
            if any(word in content_lower for word in ['kangen', 'cinta', 'sayang', 'peluk', 'memeluk']):
                # Get first meaningful sentence
                sentences = msg.split('*')
                for s in sentences:
                    if len(s.strip()) > 10:
                        key_moments.append(s.strip()[:50])
                        break
        
        # Add topics
        topics = self._extract_topics()
        if topics:
            summary += f" Topik: {', '.join(topics)}."
        
        # Add emotional context
        if key_moments:
            summary += f" Momen penting: {key_moments[0] if key_moments else 'Berbagi perasaan'}"
        
        return summary
    
    def _extract_key_moments(self) -> List[str]:
        """Extract pivotal moments from conversation"""
        moments = []
        
        for i, msg in enumerate(self.short_term_history):
            content = msg["content"].lower()
            
            # Detect key phrases
            if any(word in content for word in ['sayang', 'cinta', 'percaya', 'peluk', 'janji']):
                moments.append(msg["content"][:100])  # First 100 chars
        
        return moments[-3:]  # Return last 3 key moments
    
    def _trace_emotion_progression(self) -> List[str]:
        """Trace emotional progression throughout session"""
        emotions = []
        
        for msg in self.short_term_history:
            emotion = msg.get("emotion", "neutral")
            if emotion not in emotions:
                emotions.append(emotion)
        
        return " → ".join(emotions) if emotions else "neutral"
    
    def _extract_topics(self) -> List[str]:
        """Extract main topics discussed"""
        topics = []
        
        # Topic detection patterns
        topic_patterns = {
            "Kasih Sayang": r"(sayang|cinta|mahal|kasih|cinta|amore)",
            "Kebersamaan": r"(bersama|tidur bareng|peluk|dekat|menemani)",
            "Kerinduaan": r"(kangen|rindu|rindu banget|kangen banget|merasa sunyi)",
            "Keamanan": r"(aman|aman bersama|melindungi|menjaga|jaga)",
            "Perhatian": r"(perhatian|dengarkan|dengarkan aku|bantu|bantuan)",
            "Percaya": r"(percaya|kepercayaan|yakin|percaya diri)"
        }
        
        combined_text = " ".join([m.get("content", "").lower() for m in self.short_term_history])
        
        for topic, pattern in topic_patterns.items():
            if re.search(pattern, combined_text):
                topics.append(topic)
        
        # If no topics found, extract from keywords
        if not topics:
            all_keywords = []
            for msg in self.short_term_history:
                all_keywords.extend(msg.get("keywords", []))
            topics = list(set(all_keywords))[:5]
        
        return topics if topics else ["General Chat"]
    
    def finalize_session(self) -> Dict:
        """Finalize current session and move to episodic memory"""
        with self.lock:
            session = self.create_session_summary()
            
            if session:
                self.episodic_memory["sessions"].append(session)
                self.system_metadata["session_count"] += 1
            
            return session
    
    def _generate_session_id(self) -> str:
        """Generate unique session ID"""
        timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        rand_suffix = hashlib.md5(timestamp.encode()).hexdigest()[:6]
        return f"{timestamp}-{rand_suffix}"
    
    def save_memory(self):
        """Save memory to file with thread safety & atomic write"""
        with self.lock:
            try:
                # Update mood from emotions before saving
                self.update_mood_from_emotions()
                
                # Ensure topics and facts are not empty
                topics = self._extract_topics()
                key_moments = self._extract_key_moments()
                
                data = {
                    "system_metadata": {
                        **self.system_metadata,
                        "last_interaction": datetime.now().isoformat() if self.short_term_history else self.system_metadata.get("last_interaction"),
                        "topics_discussed": topics
                    },
                    "user_profile": {
                        **self.user_profile,
                        "name": self.system_metadata.get("user_name", "Kakak"),
                        "aliases": self.user_profile.get("aliases", ["Kakak"]),
                        "personality_traits": self.user_profile.get("personality_traits", ["Affectionate"]),
                        "preferences": {
                            **self.user_profile.get("preferences", {}),
                            "interaction_style": self.user_profile.get("preferences", {}).get("interaction_style", "Warm & Affectionate")
                        }
                    },
                    "agent_persona": self.agent_persona,
                    "knowledge_base": {
                        "facts": self.knowledge_base.get("facts", []) if self.knowledge_base.get("facts") else [{"subject": "Shiro", "predicate": "waiting", "object": "untuk Kakak", "confidence": 0.8}],
                        "concepts": self.knowledge_base.get("concepts", {"default": "Ready to serve Kakak"})
                    },
                    "episodic_memory": {
                        "sessions": self.episodic_memory.get("sessions", [])
                    },
                    "learned_patterns": getattr(self, "learned_patterns", []),
                    "short_term_history": self.short_term_history
                }
                
                tmp_path = self.memory_file + ".tmp"
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp_path, self.memory_file)
                
                # Real-time auto-sync ke Google Drive jika aktif
                if self.drive_dir and os.path.exists(self.drive_dir):
                    try:
                        shutil.copy2(self.memory_file, os.path.join(self.drive_dir, os.path.basename(self.memory_file)))
                        if os.path.exists(self.world_file):
                            shutil.copy2(self.world_file, os.path.join(self.drive_dir, os.path.basename(self.world_file)))
                    except Exception as drive_err:
                        pass
                
                print(f"[Memory] Saved: {len(self.short_term_history)} messages, {len(self.knowledge_base['facts'])} facts (total turns: {self.system_metadata['total_turns']})")
            
            except Exception as e:
                print(f"Error saving memory: {e}")
    
    def get_memory_context(self, limit: int = 5) -> List[Dict]:
        """Get recent messages for LLM context"""
        return self.short_term_history[-limit:]
    
    def get_full_memory(self) -> Dict:
        """Get complete memory structure"""
        return {
            "system_metadata": self.system_metadata,
            "user_profile": self.user_profile,
            "agent_persona": self.agent_persona,
            "knowledge_base": self.knowledge_base,
            "episodic_memory": self.episodic_memory,
            "short_term_history": self.short_term_history,
            "world": self.world
        }
    
    def reset_memory(self):
        """Reset all memory"""
        with self.lock:
            self.initialize_memory()
            self.save_memory()
            print("[Memory] All memory reset")

    def record_learned_pattern(self, user_text: str, assistant_text: str, quality: float = 1.0, image_path: Optional[str] = None):
        """Record high quality conversational turns for In-Context Few-Shot Learning"""
        with self.lock:
            if not user_text or not assistant_text:
                return
            u_clean = user_text.strip()
            a_clean = assistant_text.strip()
            if len(u_clean) < 3 or len(a_clean) < 5:
                return
            # Don't learn error or confused fallback responses
            if "error" in a_clean.lower() or "tidak mengerti" in a_clean.lower() or "shiro pusing" in a_clean.lower():
                return
            
            # Don't learn reasoning/think tags or English reasoning leakage
            if "<think>" in a_clean.lower() or "</think>" in a_clean.lower():
                return
            if any(k in a_clean.lower() for k in ["let me break this down", "the user is", "possible responses", "let's craft", "character traits"]):
                return
            
            keywords = list(set(re.findall(r'\b\w{3,}\b', u_clean.lower())))
            
            pattern = {
                "user": u_clean,
                "assistant": a_clean,
                "keywords": keywords,
                "quality": quality,
                "timestamp": datetime.now().isoformat()
            }
            if image_path:
                pattern["image"] = image_path
            
            # Update existing pattern if similar question
            for p in self.learned_patterns:
                if p.get("user", "").strip().lower() == u_clean.lower():
                    p["assistant"] = a_clean
                    p["quality"] = quality
                    p["timestamp"] = datetime.now().isoformat()
                    if image_path:
                        p["image"] = image_path
                    return
            
            self.learned_patterns.append(pattern)
            # Limit stored patterns to 50
            if len(self.learned_patterns) > 50:
                self.learned_patterns = self.learned_patterns[-50:]

    def get_relevant_exemplars(self, query: str, max_count: int = 2) -> List[Dict]:
        """Retrieve most relevant past dialogue patterns to prime LLM attention and mimic tone"""
        with self.lock:
            if not getattr(self, "learned_patterns", None):
                return []
            
            # Pastikan hanya pattern yang bersih tanpa reasoning/CoT yang dijadikan contoh
            clean_candidates = [
                p for p in self.learned_patterns
                if "<think>" not in p.get("assistant", "")
                and "let me break this down" not in p.get("assistant", "").lower()
                and not any(x in p.get("assistant", "").lower() for x in ["possible responses", "let's craft", "the user is"])
            ]
            if not clean_candidates:
                return []
            
            q_words = set(re.findall(r'\b\w{3,}\b', query.lower()))
            scored = []
            
            for p in clean_candidates:
                p_words = set(p.get("keywords", []))
                overlap = len(q_words.intersection(p_words))
                score = overlap * p.get("quality", 1.0)
                scored.append((score, p))
            
            scored.sort(key=lambda x: x[0], reverse=True)
            
            # Return top matches if score > 0
            relevant = [item[1] for item in scored if item[0] > 0][:max_count]
            # If no keyword overlap found, provide 1 high-quality general exemplar
            if not relevant and self.learned_patterns:
                relevant = self.learned_patterns[-1:]
            return relevant

