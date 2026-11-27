# -*- coding: utf-8 -*-
"""
Shiro Video Understanding & Programmatic MP4 Rendering Engine
- Ekstraksi keyframe kronologis + metadata video (MP4, WebM, MOV, MKV, AVI, M4V, GIF)
  untuk dianalisis langsung oleh model multimodal Qwen3.8-27B.
- Generator video MP4 programatik (slideshow gambar / motion-graphic teks) dengan output
  yang langsung dapat diputar di browser maupun diunduh.
"""

import io
import os
import re
import glob
import uuid
import shutil
import base64
import tempfile
import subprocess
import urllib.parse
from typing import Dict, Any, List, Optional, Tuple

from shiro.agent.packager import GENERATED_ARTIFACTS_DIR, format_size, sanitize_filename

VIDEO_EXTENSIONS = {
    ".mp4", ".webm", ".mov", ".mkv", ".avi", ".m4v", ".mpeg", ".mpg", ".ogv", ".gif"
}


def is_video_filename(filename: str) -> bool:
    """Memeriksa apakah nama berkas berekstensi video / animasi yang didukung."""
    if not filename:
        return False
    ext = os.path.splitext(str(filename).strip())[1].lower()
    return ext in VIDEO_EXTENSIONS


def _pil_to_jpeg_data_uri(pil_img: Any, max_dim: int = 768, quality: int = 82) -> str:
    """Mengubah PIL Image menjadi JPEG data URI dengan batas dimensi maksimum."""
    from PIL import Image
    img = pil_img.convert("RGB")
    w, h = img.size
    if max(w, h) > max_dim and max_dim > 0:
        scale = max_dim / float(max(w, h))
        new_w = max(2, int(round(w * scale)))
        new_h = max(2, int(round(h * scale)))
        img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}"


def _extract_gif_frames(video_path: str, max_frames: int, max_dim: int) -> Tuple[List[str], List[float], float, int, int, int]:
    from PIL import Image
    frames_b64: List[str] = []
    timestamps: List[float] = []
    with Image.open(video_path) as im:
        n_frames = getattr(im, "n_frames", 1) or 1
        w, h = im.size
        total_ms = 0
        durations_ms: List[int] = []
        for idx in range(n_frames):
            try:
                im.seek(idx)
                dur = int(im.info.get("duration", 100) or 100)
            except Exception:
                dur = 100
            durations_ms.append(max(20, dur))
            total_ms += max(20, dur)

        sample_count = min(max_frames, n_frames)
        if sample_count <= 1:
            indices = [0]
        else:
            indices = sorted(set(int(round(i * (n_frames - 1) / float(sample_count - 1))) for i in range(sample_count)))

        cum_ms = [0]
        for d in durations_ms:
            cum_ms.append(cum_ms[-1] + d)

        for idx in indices:
            im.seek(idx)
            frames_b64.append(_pil_to_jpeg_data_uri(im, max_dim=max_dim))
            timestamps.append(round(cum_ms[idx] / 1000.0, 2))
        duration_sec = round(total_ms / 1000.0, 2)
    return frames_b64, timestamps, duration_sec, w, h, n_frames


def _extract_cv2_frames(video_path: str, max_frames: int, max_dim: int) -> Tuple[List[str], List[float], float, float, int, int, int]:
    import cv2
    from PIL import Image

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError("OpenCV gagal membuka berkas video.")
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        if fps <= 0.0 or fps > 240.0:
            fps = 24.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)

        frames_b64: List[str] = []
        timestamps: List[float] = []

        if total_frames > 0:
            sample_count = min(max_frames, total_frames)
            if sample_count <= 1:
                indices = [0]
            else:
                indices = sorted(set(int(round(i * (total_frames - 1) / float(sample_count - 1))) for i in range(sample_count)))

            for f_idx in indices:
                cap.set(cv2.CAP_PROP_POS_FRAMES, f_idx)
                ok, bgr = cap.read()
                if not ok or bgr is None:
                    continue
                if width <= 0 or height <= 0:
                    height, width = bgr.shape[:2]
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                frames_b64.append(_pil_to_jpeg_data_uri(Image.fromarray(rgb), max_dim=max_dim))
                timestamps.append(round(f_idx / fps, 2))
            duration_sec = round(total_frames / fps, 2)
        else:
            # Stream container tanpa metadata frame_count: baca berurutan lalu subsample
            raw_frames: List[Tuple[float, Any]] = []
            idx = 0
            while len(raw_frames) < 480:
                ok, bgr = cap.read()
                if not ok or bgr is None:
                    break
                if width <= 0 or height <= 0:
                    height, width = bgr.shape[:2]
                raw_frames.append((round(idx / fps, 2), bgr))
                idx += 1
            total_frames = len(raw_frames)
            duration_sec = round(total_frames / fps, 2)
            if raw_frames:
                step_n = min(max_frames, len(raw_frames))
                pick = sorted(set(int(round(i * (len(raw_frames) - 1) / float(max(1, step_n - 1)))) for i in range(step_n)))
                for p_i in pick:
                    ts, bgr = raw_frames[p_i]
                    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                    frames_b64.append(_pil_to_jpeg_data_uri(Image.fromarray(rgb), max_dim=max_dim))
                    timestamps.append(ts)

        return frames_b64, timestamps, duration_sec, round(fps, 2), width, height, total_frames
    finally:
        cap.release()


def _extract_ffmpeg_frames(video_path: str, max_frames: int, max_dim: int) -> Tuple[List[str], List[float], float, float, int, int, int]:
    from PIL import Image
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RuntimeError("ffmpeg tidak tersedia di sistem.")

    ffprobe_bin = shutil.which("ffprobe")
    duration_sec = 0.0
    fps = 24.0
    width = 0
    height = 0
    if ffprobe_bin:
        try:
            probe = subprocess.run(
                [ffprobe_bin, "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", video_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
            )
            if probe.returncode == 0 and probe.stdout:
                import json as _json
                pdata = _json.loads(probe.stdout)
                duration_sec = float((pdata.get("format") or {}).get("duration") or 0.0)
                for st in pdata.get("streams") or []:
                    if st.get("codec_type") == "video":
                        width = int(st.get("width") or 0)
                        height = int(st.get("height") or 0)
                        rfps = str(st.get("r_frame_rate") or "24/1")
                        if "/" in rfps:
                            num, den = rfps.split("/", 1)
                            if float(den or 1) > 0:
                                fps = float(num) / float(den)
                        break
        except Exception:
            pass

    target_fps = max(0.25, min(4.0, (max_frames / duration_sec) if duration_sec > 0.5 else 2.0))
    tmp_dir = tempfile.mkdtemp(prefix="shiro_vid_ff_")
    try:
        out_pat = os.path.join(tmp_dir, "frame_%03d.jpg")
        cmd = [
            ffmpeg_bin, "-y", "-v", "error", "-i", video_path,
            "-vf", f"fps={target_fps:.3f},scale='min({max_dim},iw)':-2",
            "-frames:v", str(max_frames),
            out_pat,
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        jpgs = sorted(glob.glob(os.path.join(tmp_dir, "frame_*.jpg")))
        if not jpgs:
            raise RuntimeError("ffmpeg tidak menghasilkan frame gambar.")

        frames_b64: List[str] = []
        timestamps: List[float] = []
        for idx, jp in enumerate(jpgs):
            with Image.open(jp) as im:
                if width <= 0 or height <= 0:
                    width, height = im.size
                frames_b64.append(_pil_to_jpeg_data_uri(im, max_dim=max_dim))
            if duration_sec > 0 and len(jpgs) > 1:
                timestamps.append(round((idx / float(len(jpgs) - 1)) * duration_sec, 2))
            else:
                timestamps.append(round(idx / target_fps, 2))
        total_est = int(round(duration_sec * fps)) if duration_sec > 0 else len(frames_b64)
        return frames_b64, timestamps, round(duration_sec, 2), round(fps, 2), width, height, total_est
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def extract_video_frames_and_metadata(
    video_path: str,
    filename: Optional[str] = None,
    max_frames: int = 12,
    max_dim: int = 768,
) -> Dict[str, Any]:
    """
    Mengekstrak keyframe kronologis dan metadata video untuk dipahami model multimodal
    Qwen3.8-27B / Vision Cortex / OCR lokal.
    """
    display_name = filename or os.path.basename(video_path)
    if not video_path or not os.path.exists(video_path):
        return {
            "success": False,
            "filename": display_name,
            "error": "Berkas video tidak ditemukan.",
            "frames": [],
        }

    ext = os.path.splitext(display_name)[1].lower()
    frames: List[str] = []
    timestamps: List[float] = []
    duration_sec = 0.0
    fps = 24.0
    width = 0
    height = 0
    total_frames = 0
    engine_used = "unknown"
    last_err = ""

    if ext == ".gif":
        try:
            frames, timestamps, duration_sec, width, height, total_frames = _extract_gif_frames(video_path, max_frames, max_dim)
            fps = round(total_frames / max(0.1, duration_sec), 2) if duration_sec > 0 else 10.0
            engine_used = "pillow_gif"
        except Exception as e_gif:
            last_err = str(e_gif)

    if not frames:
        try:
            frames, timestamps, duration_sec, fps, width, height, total_frames = _extract_cv2_frames(video_path, max_frames, max_dim)
            engine_used = "opencv"
        except Exception as e_cv:
            last_err = str(e_cv)

    if not frames:
        try:
            frames, timestamps, duration_sec, fps, width, height, total_frames = _extract_ffmpeg_frames(video_path, max_frames, max_dim)
            engine_used = "ffmpeg"
        except Exception as e_ff:
            last_err = f"{last_err}; {e_ff}".strip("; ")

    if not frames:
        return {
            "success": False,
            "filename": display_name,
            "error": f"Gagal mengekstrak frame video: {last_err or 'codec tidak didukung'}",
            "frames": [],
        }

    res_label = f"{width}x{height}" if (width > 0 and height > 0) else "unknown"
    return {
        "success": True,
        "filename": display_name,
        "duration_sec": round(duration_sec, 2),
        "fps": round(fps, 2),
        "width": width,
        "height": height,
        "resolution": res_label,
        "total_frames": total_frames,
        "sampled_frame_count": len(frames),
        "frame_timestamps": timestamps,
        "frames": frames,
        "thumbnail": frames[0],
        "engine": engine_used,
    }


def detect_video_generation_request(text: str) -> Optional[Dict[str, Any]]:
    """
    Mendeteksi perintah eksplisit pengguna untuk membuat/render video MP4
    (sambil menghindari salah deteksi saat pengguna meminta analisis/membaca video yang diunggah).
    """
    if not text or not text.strip():
        return None
    low = text.lower().strip()

    # Pastikan perintah eksplisit membuat video, BUKAN membaca/menganalisa video
    if re.search(r"\b(baca|lihat|tonton|analisa|analisis|periksa|cek|jelaskan|rangkum|review|inspect|watch)\s+(?:isi\s+)?video\b", low):
        if not re.search(r"\b(buatkan|buat|bikin|generate|render|jadikan)\s+video\b", low):
            return None

    has_gen_kw = bool(
        re.search(
            r"\b(?:buatkan|buat|bikin|generate|render|jadikan|create)\s+(?:sebuah\s+)?(?:video|animasi|slideshow|klip|mp4)\b",
            low,
        )
        or re.search(r"\b(?:video|animasi|slideshow)\s+mp4\b", low)
    )
    if not has_gen_kw:
        return None

    out_m = re.search(r"\b([A-Za-z0-9_\-.]+\.(?:mp4|webm|gif))\b", text, re.IGNORECASE)
    output_name = sanitize_filename(out_m.group(1), allow_subdirs=False) if out_m else None

    dur_sec = 5.0
    dur_m = re.search(r"\b(\d{1,2})\s*(?:detik|s|sec|seconds?)\b", low)
    if dur_m:
        try:
            dur_sec = max(2.0, min(20.0, float(dur_m.group(1))))
        except ValueError:
            dur_sec = 5.0

    return {
        "prompt": text.strip(),
        "output_name": output_name,
        "duration_sec": dur_sec,
    }


def _load_pil_font(size: int = 28):
    from PIL import ImageFont
    candidates = [
        "arial.ttf",
        "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arial.ttf",
    ]
    for fp in candidates:
        try:
            return ImageFont.truetype(fp, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _wrap_text_lines(text: str, max_chars: int = 44) -> List[str]:
    words = (text or "").strip().split()
    lines: List[str] = []
    cur = ""
    for w in words:
        if len(cur) + len(w) + 1 <= max_chars:
            cur = f"{cur} {w}".strip()
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or ["Shiro AI Video"]


def render_video_artifact(
    title: str,
    scenes: Optional[List[str]] = None,
    input_images_b64: Optional[List[str]] = None,
    output_name: Optional[str] = None,
    duration_sec: float = 5.0,
    fps: int = 24,
    size: Tuple[int, int] = (960, 540),
    base_dir: str = GENERATED_ARTIFACTS_DIR,
) -> Dict[str, Any]:
    """
    Merender video MP4 nyata yang langsung bisa diputar & diunduh:
    - Jika `input_images_b64` tersedia: membuat slideshow animasi crossfade dari gambar.
    - Jika tidak: merender motion-graphic kartu adegan minimalis yang bersih & tajam.
    """
    import numpy as np
    from PIL import Image, ImageDraw

    w, h = int(size[0]), int(size[1])
    fps = max(10, min(30, int(fps)))
    duration_sec = max(2.0, min(20.0, float(duration_sec)))
    total_frames = max(20, int(round(duration_sec * fps)))

    bundle_id = uuid.uuid4().hex[:12]
    bundle_dir = os.path.abspath(os.path.join(base_dir, bundle_id))
    os.makedirs(bundle_dir, exist_ok=True)

    exact_name = sanitize_filename(output_name or "", allow_subdirs=False) or f"shiro_video_{bundle_id[:6]}.mp4"
    if not exact_name.lower().endswith(".mp4"):
        exact_name = os.path.splitext(exact_name)[0] + ".mp4"
    out_path = os.path.join(bundle_dir, exact_name)

    decoded_imgs: List[Image.Image] = []
    if input_images_b64:
        for b64_item in input_images_b64[:8]:
            try:
                raw_b64 = b64_item.split(",", 1)[1] if "," in b64_item else b64_item
                im = Image.open(io.BytesIO(base64.b64decode(raw_b64))).convert("RGB")
                # Fit with letterbox
                im.thumbnail((w, h), Image.Resampling.LANCZOS)
                canvas = Image.new("RGB", (w, h), (17, 19, 24))
                canvas.paste(im, ((w - im.width) // 2, (h - im.height) // 2))
                decoded_imgs.append(canvas)
            except Exception:
                pass

    scene_list = [s.strip() for s in (scenes or []) if s and s.strip()]
    if not scene_list:
        clean_title = re.sub(r"^(?:tolong\s+)?(?:buatkan|buat|bikin|generate|render)\s+(?:video|animasi)\s*(?:tentang)?\s*", "", title or "", flags=re.IGNORECASE).strip()
        scene_list = [
            clean_title[:140] or "Shiro AI Agent Motion Video",
            f"Generated by ShiroHaru-Lyra-Agent · {duration_sec:.0f}s",
        ]

    font_title = _load_pil_font(34)
    font_sub = _load_pil_font(20)
    font_meta = _load_pil_font(15)

    def _make_frame(frame_idx: int) -> np.ndarray:
        progress = frame_idx / float(max(1, total_frames - 1))
        if decoded_imgs:
            n_img = len(decoded_imgs)
            pos = progress * n_img
            idx_a = min(n_img - 1, int(pos))
            idx_b = min(n_img - 1, idx_a + 1)
            frac = pos - idx_a
            if idx_a != idx_b and frac > 0.72:
                alpha = (frac - 0.72) / 0.28
                frame_im = Image.blend(decoded_imgs[idx_a], decoded_imgs[idx_b], min(1.0, max(0.0, alpha)))
            else:
                frame_im = decoded_imgs[idx_a].copy()
        else:
            frame_im = Image.new("RGB", (w, h), (18, 20, 26))
            draw = ImageDraw.Draw(frame_im)
            # Garis aksen horizontal tipis & kartu bersih minimalis
            pad = 64
            card_top = 88
            card_bottom = h - 88
            draw.rounded_rectangle([pad, card_top, w - pad, card_bottom], radius=16, fill=(25, 28, 36), outline=(54, 62, 78), width=2)

            s_idx = min(len(scene_list) - 1, int(progress * len(scene_list)))
            cur_scene = scene_list[s_idx]
            lines = _wrap_text_lines(cur_scene, max_chars=40)

            y_start = (h // 2) - (len(lines) * 24)
            for l_i, ln in enumerate(lines[:5]):
                bbox = draw.textbbox((0, 0), ln, font=font_title)
                tw = bbox[2] - bbox[0]
                draw.text(((w - tw) // 2, y_start + l_i * 44), ln, fill=(238, 242, 248), font=font_title)

            sub_str = f"Scene {s_idx + 1}/{len(scene_list)}  ·  {progress * duration_sec:.1f}s / {duration_sec:.1f}s"
            sb = draw.textbbox((0, 0), sub_str, font=font_meta)
            draw.text(((w - (sb[2] - sb[0])) // 2, card_bottom - 44), sub_str, fill=(148, 163, 184), font=font_meta)

            # Progress bar halus di bawah kartu
            bar_x0 = pad + 40
            bar_x1 = w - pad - 40
            bar_y = card_bottom - 18
            draw.rectangle([bar_x0, bar_y, bar_x1, bar_y + 4], fill=(42, 48, 60))
            fill_x = int(bar_x0 + (bar_x1 - bar_x0) * progress)
            draw.rectangle([bar_x0, bar_y, max(bar_x0 + 2, fill_x), bar_y + 4], fill=(59, 130, 246))

            header_lbl = "SHIRO AI AGENT · VIDEO OUTPUT"
            draw.text((pad + 24, card_top + 20), header_lbl, fill=(130, 145, 170), font=font_sub if False else font_meta)

        return np.asarray(frame_im, dtype=np.uint8)

    ffmpeg_bin = shutil.which("ffmpeg")
    rendered = False
    if ffmpeg_bin:
        try:
            proc = subprocess.Popen(
                [
                    ffmpeg_bin, "-y", "-v", "error",
                    "-f", "rawvideo", "-pix_fmt", "rgb24",
                    "-s", f"{w}x{h}", "-r", str(fps),
                    "-i", "-",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    "-movflags", "+faststart",
                    out_path,
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                assert proc.stdin is not None
                for f_i in range(total_frames):
                    proc.stdin.write(_make_frame(f_i).tobytes())
                proc.stdin.close()
                proc.wait(timeout=45)
                rendered = proc.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 0
            except Exception:
                proc.kill()
        except Exception:
            rendered = False

    if not rendered:
        import cv2
        writer = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
        try:
            for f_i in range(total_frames):
                rgb = _make_frame(f_i)
                bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
                writer.write(bgr)
        finally:
            writer.release()
        rendered = os.path.exists(out_path) and os.path.getsize(out_path) > 0

    if not rendered:
        raise RuntimeError("Gagal merender berkas video MP4.")

    size_bytes = os.path.getsize(out_path)
    encoded_name = urllib.parse.quote(exact_name)
    return {
        "id": bundle_id,
        "kind": "video",
        "filename": exact_name,
        "format": "mp4",
        "size_bytes": size_bytes,
        "size_label": format_size(size_bytes),
        "duration_sec": round(duration_sec, 1),
        "resolution": f"{w}x{h}",
        "download_url": f"/api/artifacts/{bundle_id}/{encoded_name}",
        "video_url": f"/api/artifacts/{bundle_id}/{encoded_name}?inline=1",
        "files_included": [exact_name],
        "file_count": 1,
    }
