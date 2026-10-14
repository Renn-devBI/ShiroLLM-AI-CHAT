# -*- coding: utf-8 -*-
"""
Shiro MoE Dual-Brain Orchestrator (System-Level Mixture of Experts)

Menghubungkan dua "otak" berbeda secara modular dan on-demand:
- Visual Cortex Expert   : model vision sejati (mis. Qwen2.5-VL-7B-Instruct + mmproj)
- Cognitive Expert       : model chat aktif (mis. Qwen3.8-27B-Uncensored)

Bobot model TIDAK digabung. Visual expert hanya bertugas mengamati gambar dan menghasilkan
"Visual Evidence Contract" (fakta objektif), lalu cognitive expert menyusun jawaban akhir
berdasarkan kontrak tersebut.

Mode:
- off        : MoE nonaktif. Gambar pada model teks memakai OCR lokal.
- auto       : MoE aktif otomatis bila model chat tidak punya vision DAN visual expert tersedia di disk.
               Visual expert dimuat sekali lalu tetap di memori (seperti concurrent).
- concurrent : Visual expert dimuat dan dipertahankan di VRAM berdampingan dengan model chat (GPU besar, mis. A100).
- swap       : Visual expert dimuat hanya saat ada gambar, lalu dilepas dari memori (GPU 16 GB, mis. T4).
"""

import gc
import json
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional

VALID_MODES = ("off", "auto", "concurrent", "swap")
DEFAULT_MODE = "auto"
VISION_EXPERT_CTX = 8192

EVIDENCE_PROMPT = (
    "Kamu adalah modul pengamat visual yang objektif. Amati gambar dengan teliti dan "
    "laporkan HANYA hal yang benar-benar terlihat. Jangan menebak identitas, situs web, atau "
    "konteks yang tidak tampak di gambar.\n"
    "Balas HANYA dengan JSON valid berformat:\n"
    "{\n"
    '  "image_type": "foto | screenshot aplikasi | screenshot browser | poster/banner | diagram | dokumen | kode | lainnya",\n'
    '  "is_webpage_screenshot": true/false,\n'
    '  "primary_subject": "objek/subjek utama",\n'
    '  "detected_texts": ["setiap teks yang terbaca persis seperti tertulis"],\n'
    '  "objects": ["objek penting yang terlihat"],\n'
    '  "visual_details": "warna, tata letak, suasana, ekspresi",\n'
    '  "uncertain": ["hal yang tidak jelas/terpotong"]\n'
    "}\n"
)


def _load_moe_settings() -> Dict[str, Any]:
    from shiro.models import load_model_config
    cfg = load_model_config()
    moe = cfg.get("moe") or {}
    mode = str(os.environ.get("SHIRO_MOE_MODE") or moe.get("mode") or DEFAULT_MODE).lower()
    if mode not in VALID_MODES:
        mode = DEFAULT_MODE
    return {
        "mode": mode,
        "vision_expert": os.environ.get("SHIRO_VISION_EXPERT") or moe.get("vision_expert") or "",
    }


def _save_moe_settings(settings: Dict[str, Any]) -> None:
    from shiro.models import load_model_config, save_model_config
    cfg = load_model_config()
    cfg["moe"] = {
        "mode": settings.get("mode", DEFAULT_MODE),
        "vision_expert": settings.get("vision_expert", ""),
    }
    save_model_config(cfg)


def find_vision_expert_path(preferred: str = "") -> Optional[str]:
    """Cari model vision sejati di disk (prioritas: preferensi pengguna → VL-7B → VL lain)."""
    from shiro.models import get_available_gguf_models, is_vision_model

    if preferred and os.path.exists(preferred) and is_vision_model(preferred):
        return preferred

    candidates = [p for p in get_available_gguf_models() if is_vision_model(p)]
    if not candidates:
        return None

    def rank(p: str) -> int:
        n = os.path.basename(p).lower()
        if "vl-7b" in n or "vl_7b" in n:
            return 0
        if "vl-32b" in n or "vl_32b" in n:
            return 1
        return 2

    candidates.sort(key=rank)
    return candidates[0]


def parse_evidence_json(text: str) -> Optional[Dict[str, Any]]:
    """Parse JSON kontrak bukti secara toleran (mendukung blok ```json dan teks tambahan)."""
    if not text:
        return None
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, flags=re.DOTALL)
    blob = fence.group(1) if fence else None
    if not blob:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start != -1 and end > start:
            blob = cleaned[start:end + 1]
    if not blob:
        return None
    try:
        data = json.loads(blob)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def format_evidence_block(contract: Dict[str, Any], frame_label: str = "") -> str:
    """Ubah kontrak JSON menjadi blok teks ringkas untuk otak kognitif."""
    lines = []
    head = f"Gambar {frame_label}".strip()
    img_type = contract.get("image_type")
    if img_type:
        lines.append(f"- {head} — Jenis: {img_type}")
    if contract.get("primary_subject"):
        lines.append(f"- Subjek utama: {contract['primary_subject']}")
    texts = [t for t in (contract.get("detected_texts") or []) if str(t).strip()]
    if texts:
        lines.append("- Teks terbaca: " + "; ".join(f'"{str(t).strip()}"' for t in texts[:40]))
    objs = [o for o in (contract.get("objects") or []) if str(o).strip()]
    if objs:
        lines.append("- Objek terlihat: " + ", ".join(str(o) for o in objs[:20]))
    if contract.get("visual_details"):
        lines.append(f"- Detail visual: {contract['visual_details']}")
    unc = [u for u in (contract.get("uncertain") or []) if str(u).strip()]
    if unc:
        lines.append("- Tidak jelas: " + ", ".join(str(u) for u in unc[:10]))
    if contract.get("is_webpage_screenshot") is False:
        lines.append("- Catatan: gambar ini BUKAN tangkapan layar halaman web.")
    return "\n".join(lines)


class MoEOrchestrator:
    """Pengelola visual expert dan perakit Visual Evidence Contract."""

    def __init__(self):
        self._lock = threading.Lock()
        self._expert = None
        self._expert_path: Optional[str] = None
        self.last_status: Dict[str, Any] = {}

    # ---------------------- Konfigurasi ----------------------
    def get_settings(self) -> Dict[str, Any]:
        return _load_moe_settings()

    def set_mode(self, mode: str, vision_expert: Optional[str] = None) -> Dict[str, Any]:
        mode = (mode or "").lower().strip()
        if mode not in VALID_MODES:
            raise ValueError(f"Mode MoE tidak valid: {mode}. Pilihan: {', '.join(VALID_MODES)}")
        settings = _load_moe_settings()
        settings["mode"] = mode
        if vision_expert is not None:
            settings["vision_expert"] = vision_expert
        _save_moe_settings(settings)
        if mode in ("off", "swap"):
            self.unload_expert()
        return self.status()

    def status(self) -> Dict[str, Any]:
        settings = _load_moe_settings()
        path = find_vision_expert_path(settings.get("vision_expert", ""))
        return {
            "mode": settings["mode"],
            "valid_modes": list(VALID_MODES),
            "vision_expert_path": path,
            "vision_expert_available": bool(path),
            "vision_expert_loaded": self._expert is not None,
            "loaded_expert_path": self._expert_path,
            "last_run": self.last_status,
        }

    # ---------------------- Keputusan routing ----------------------
    def should_route(self, has_image: bool, chat_has_vision: bool) -> bool:
        """MoE dipakai hanya jika ada gambar, model chat buta visual, dan mode tidak off."""
        if not has_image or chat_has_vision:
            return False
        settings = _load_moe_settings()
        if settings["mode"] == "off":
            return False
        return bool(find_vision_expert_path(settings.get("vision_expert", "")))

    # ---------------------- Manajemen expert ----------------------
    def _load_expert(self, path: str):
        from llama_cpp import Llama
        from shiro.models import init_vision_handler, get_gpu_layers

        handler = init_vision_handler(path)
        if handler is None:
            raise RuntimeError(f"Vision projector (mmproj) untuk {os.path.basename(path)} tidak ditemukan.")
        print(f"[MoE] Memuat Visual Cortex Expert: {os.path.basename(path)}")
        return Llama(
            model_path=path,
            chat_handler=handler,
            n_ctx=VISION_EXPERT_CTX,
            n_gpu_layers=get_gpu_layers(),
            n_threads=4,
            verbose=False,
        )

    def _get_expert(self, path: str):
        if self._expert is not None and self._expert_path == path:
            return self._expert
        self.unload_expert()
        self._expert = self._load_expert(path)
        self._expert_path = path
        return self._expert

    def unload_expert(self) -> None:
        if self._expert is not None:
            try:
                if hasattr(self._expert, "close"):
                    self._expert.close()
            except Exception as e:
                print(f"[MoE] Warning melepas visual expert: {e}")
            self._expert = None
            self._expert_path = None
            gc.collect()

    # ---------------------- Ekstraksi bukti visual ----------------------
    def extract_visual_evidence(self, images: List[str], user_query: str = "") -> Dict[str, Any]:
        """
        Jalankan visual expert terhadap gambar dan kembalikan:
        {"ok": bool, "source": "vl_expert"|"ocr", "evidence_text": str, "contracts": [...], "duration_ms": float}
        Bila visual expert gagal, otomatis fallback ke OCR lokal.
        """
        t0 = time.perf_counter()
        settings = _load_moe_settings()
        path = find_vision_expert_path(settings.get("vision_expert", ""))
        result: Dict[str, Any] = {"ok": False, "source": "ocr", "evidence_text": "", "contracts": [], "expert": None}

        if path:
            with self._lock:
                try:
                    expert = self._get_expert(path)
                    blocks = []
                    for idx, img in enumerate(images[:4]):
                        url = img if img.startswith("data:image/") else f"data:image/jpeg;base64,{img}"
                        prompt = EVIDENCE_PROMPT
                        if user_query:
                            prompt += f"\nPertanyaan pengguna tentang gambar (jangan dijawab, cukup amati bagian relevan): \"{user_query[:500]}\""
                        res = expert.create_chat_completion(
                            messages=[{
                                "role": "user",
                                "content": [
                                    {"type": "image_url", "image_url": {"url": url}},
                                    {"type": "text", "text": prompt},
                                ],
                            }],
                            temperature=0.1,
                            top_p=0.9,
                            max_tokens=900,
                        )
                        raw = (res["choices"][0]["message"].get("content") or "").strip()
                        contract = parse_evidence_json(raw)
                        label = f"#{idx + 1}" if len(images) > 1 else ""
                        if contract:
                            result["contracts"].append(contract)
                            blocks.append(format_evidence_block(contract, label))
                        elif raw:
                            blocks.append(f"- Gambar {label}: {raw[:1500]}".replace("  ", " "))
                    if blocks:
                        result.update(ok=True, source="vl_expert", evidence_text="\n".join(blocks),
                                      expert=os.path.basename(path))
                except Exception as e:
                    print(f"[MoE] Visual expert gagal, fallback OCR: {e}")
                    result["error"] = str(e)[:200]
                finally:
                    if settings["mode"] == "swap":
                        self.unload_expert()

        if not result["ok"]:
            from shiro.vision.bridge import extract_local_image_text_and_info
            ocr = extract_local_image_text_and_info(images)
            result.update(ok=bool(ocr), source="ocr", evidence_text=ocr or "Berkas gambar terlampir (tidak ada teks terdeteksi).")

        result["duration_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        self.last_status = {k: v for k, v in result.items() if k != "contracts"}
        return result


_orchestrator: Optional[MoEOrchestrator] = None


def get_orchestrator() -> MoEOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = MoEOrchestrator()
    return _orchestrator


def parse_moe_command(text: str) -> Optional[str]:
    """
    Kenali perintah eksplisit untuk mengatur mode MoE dari chat.
    Format: /moe on|off|auto|concurrent|swap|status
    """
    m = re.match(r"^\s*/moe(?:\s+(\w+))?\s*$", text or "", flags=re.IGNORECASE)
    if not m:
        return None
    arg = (m.group(1) or "status").lower()
    alias = {"on": "concurrent", "aktif": "concurrent", "nyala": "concurrent",
             "mati": "off", "nonaktif": "off", "otomatis": "auto"}
    return alias.get(arg, arg)
