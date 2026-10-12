# -*- coding: utf-8 -*-
"""
Shiro Conversation Analysis & Fact Extraction
Helper for similarity checking and fact memory extraction.
"""

import re
from collections import defaultdict
from typing import List, Dict, Any, Set

class ConversationAnalyzer:
    """Analisis pola percakapan untuk ekstraksi fakta dan memori"""
    
    @staticmethod
    def extract_keywords(text: str, min_length: int = 3) -> List[str]:
        """Ekstrak keyword penting dari teks"""
        stopwords: Set[str] = {
            'yang', 'ini', 'itu', 'dan', 'di', 'ke', 'dari', 'untuk', 'pada',
            'adalah', 'dengan', 'tidak', 'juga', 'saya', 'kamu', 'nya', 'ya',
            'atau', 'akan', 'sudah', 'bisa', 'ada', 'apa', 'siapa', 'kenapa'
        }
        words = re.findall(r'\b\w+\b', text.lower())
        return [w for w in words if len(w) >= min_length and w not in stopwords]
    
    @staticmethod
    def calculate_similarity(text1: str, text2: str) -> float:
        """Hitung similaritas kata antara dua teks"""
        words1 = set(ConversationAnalyzer.extract_keywords(text1))
        words2 = set(ConversationAnalyzer.extract_keywords(text2))
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    @staticmethod
    def detect_topic_shift(current_msg: str, previous_msgs: List[Dict[str, Any]], threshold: float = 0.3) -> bool:
        """Deteksi pergantian topik percakapan"""
        if not previous_msgs:
            return True
        recent_msg = previous_msgs[-1].get('content', '')
        similarity = ConversationAnalyzer.calculate_similarity(current_msg, recent_msg)
        return similarity < threshold
    
    @staticmethod
    def extract_facts(conversation_history: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Ekstrak fakta penting dari riwayat percakapan"""
        facts = {
            'names': set(),
            'locations': set(),
            'events': [],
            'preferences': defaultdict(list)
        }
        
        for msg in conversation_history:
            content = msg.get('content', '')
            names = re.findall(r'\b[A-Z][a-z]+\b', content)
            facts['names'].update(names)
            
            if any(word in content.lower() for word in ['suka', 'senang', 'favorit']):
                facts['preferences']['likes'].append(content)
            if any(word in content.lower() for word in ['benci', 'tidak suka', 'gak suka']):
                facts['preferences']['dislikes'].append(content)
        
        return facts
