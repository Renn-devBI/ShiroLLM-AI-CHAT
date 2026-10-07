# -*- coding: utf-8 -*-
"""
Neural Execution Pipeline Tracer & Event Broadcaster (n8n-style Visualizer)
Tracks execution nodes, metrics, latency, data transformations, and broadcasts via SSE.
"""

import threading
import queue
from datetime import datetime
from typing import Dict, Any, List

def create_initial_trace() -> Dict[str, Any]:
    """Mengembalikan objek trace neural pipeline awal dalam keadaan idle"""
    return {
        "id": "trace-initial",
        "timestamp": datetime.now().isoformat(),
        "status": "idle",
        "total_duration_ms": 0,
        "user_input": "Halo Kakak!",
        "reply": "Halo Kakak. Ada yang bisa Shiro bantu hari ini?",
        "nodes": [
            {"id": "node_input", "name": "Input Ingestion", "type": "trigger", "icon": "ph-chat-circle-dots", "color": "#3b82f6", "status": "idle", "duration_ms": 0, "summary": "Siap menerima input pesan/gambar", "data_in": {}, "data_out": {}},
            {"id": "node_emotion", "name": "Emotion & Tone Classifier", "type": "analyzer", "icon": "ph-heartbeat", "color": "#ec4899", "status": "idle", "duration_ms": 0, "summary": "Deteksi sentimen & tone afektif", "data_in": {}, "data_out": {}},
            {"id": "node_memory", "name": "Cognitive Memory & RDF Retrieval", "type": "database", "icon": "ph-brain", "color": "#8b5cf6", "status": "idle", "duration_ms": 0, "summary": "Pencarian fakta RDF & exemplars", "data_in": {}, "data_out": {}},
            {"id": "node_prompt", "name": "Dynamic Prompt Synthesizer", "type": "transform", "icon": "ph-brackets-curly", "color": "#06b6d4", "status": "idle", "duration_ms": 0, "summary": "Perakitan sistem prompt & persona", "data_in": {}, "data_out": {}},
            {"id": "node_llm", "name": "Neural Inference Engine", "type": "ai_model", "icon": "ph-cpu", "color": "#f59e0b", "status": "idle", "duration_ms": 0, "summary": "Eksekusi LLM GGUF Qwen", "data_in": {}, "data_out": {}},
            {"id": "node_filter", "name": "Anti-Hallucination & CoT Filter", "type": "filter", "icon": "ph-shield-check", "color": "#10b981", "status": "idle", "duration_ms": 0, "summary": "Pembersihan CoT & validasi", "data_in": {}, "data_out": {}},
            {"id": "node_state", "name": "State & Persistence Sync", "type": "persistence", "icon": "ph-database", "color": "#6366f1", "status": "idle", "duration_ms": 0, "summary": "Update mood & persistensi memori", "data_in": {}, "data_out": {}},
            {"id": "node_output", "name": "Response Delivery Stream", "type": "output", "icon": "ph-paper-plane-right", "color": "#3b82f6", "status": "idle", "duration_ms": 0, "summary": "Penyampaian hasil respon akhir", "data_in": {}, "data_out": {}}
        ]
    }

class PipelineTraceManager:
    """Manajer status dan live streaming SSE trace pipeline eksekusi Shiro"""
    def __init__(self):
        self.latest_trace = create_initial_trace()
        self.subscribers: List[queue.Queue] = []
        self.lock = threading.Lock()

    def get_latest_trace(self) -> Dict[str, Any]:
        return self.latest_trace

    def broadcast(self, trace: Dict[str, Any]):
        self.latest_trace = trace
        with self.lock:
            dead_queues = []
            for q in self.subscribers:
                try:
                    q.put_nowait(trace)
                except Exception:
                    dead_queues.append(q)
            for dq in dead_queues:
                if dq in self.subscribers:
                    self.subscribers.remove(dq)

    def subscribe(self) -> queue.Queue:
        q = queue.Queue(maxsize=10)
        with self.lock:
            self.subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue):
        with self.lock:
            if q in self.subscribers:
                self.subscribers.remove(q)

global_pipeline_manager = PipelineTraceManager()
