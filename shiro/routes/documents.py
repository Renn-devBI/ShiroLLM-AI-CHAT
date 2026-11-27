# -*- coding: utf-8 -*-
"""
Shiro Document & File Management Routes
Handles document upload, text extraction, previews, and static file/image serving.
"""

import os
import re
from typing import Optional
from flask import Blueprint, request, jsonify, send_file
from shiro.auth import verify_api_key

documents_bp = Blueprint("documents_bp", __name__)

@documents_bp.route('/api/upload/document', methods=['POST'])
def upload_document():
    if not verify_api_key(allow_web_ui=True):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        if 'file' not in request.files:
            return jsonify({"success": False, "error": "Tidak ada file yang dipilih."}), 400
        
        f = request.files['file']
        if f.filename == '':
            return jsonify({"success": False, "error": "Nama file kosong."}), 400

        from shiro.document import extract_text_from_file, SUPPORTED_EXTENSIONS, is_probably_text_file
        ext = os.path.splitext(f.filename)[1].lower()

        upload_dir = os.path.join("data", "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        save_path = os.path.join(upload_dir, os.path.basename(f.filename))
        f.save(save_path)

        if ext not in SUPPORTED_EXTENSIONS and not is_probably_text_file(save_path):
            try:
                os.remove(save_path)
            except Exception:
                pass
            return jsonify({
                "success": False,
                "error": f"Format biner '{ext or f.filename}' tidak didukung. Gunakan berkas dokumen (PDF, DOCX, TXT, MD) atau berkas kode pemrograman (.js, .py, .ts, .cpp, .html, dll.)."
            }), 400

        from shiro.server_state import state
        from shiro.models import is_qwen38_27b_uncensored, get_active_model_ctx
        active_model_path = getattr(state.llm, 'model_path', '') if state.llm else ''
        doc_max_chars = None
        if not os.environ.get("SHIRO_MAX_DOC_CHARS") and is_qwen38_27b_uncensored(active_model_path):
            active_ctx_chars = get_active_model_ctx(state.llm) * 3 if state.llm else 1_500_000
            doc_max_chars = max(500_000, min(3_000_000, active_ctx_chars))

        res = extract_text_from_file(save_path, filename=f.filename, max_chars=doc_max_chars)
        if not res.get("success"):
            return jsonify(res), 400

        text = res.get("text", "")
        preview = text[:200] + ("..." if len(text) > 200 else "")
        res["preview"] = preview
        res["url"] = f"/api/files/{f.filename}"
        res["filename"] = f.filename
        return jsonify(res)
    except Exception as e:
        print(f"[Documents] Error in upload_document: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@documents_bp.route('/api/files/<path:filename>', methods=['GET'])
def get_uploaded_file(filename):
    """Serve uploaded document from data/uploads/"""
    upload_dir = os.path.abspath(os.path.join("data", "uploads"))
    target = os.path.abspath(os.path.join(upload_dir, filename))
    if not target.startswith(upload_dir) or not os.path.exists(target):
        return jsonify({"error": "File tidak ditemukan"}), 404
    
    as_attachment = request.args.get('download', '0') == '1'
    return send_file(target, as_attachment=as_attachment, download_name=os.path.basename(target))


@documents_bp.route('/api/artifacts/<artifact_id>/<path:filename>', methods=['GET'])
def get_generated_artifact(artifact_id, filename):
    """Serve generated archive/file/video artifact from data/generated_files/ preserving exact filename."""
    if not re.match(r'^[a-zA-Z0-9_-]{4,64}$', artifact_id or ''):
        return jsonify({"error": "ID artifak tidak valid"}), 400
    from shiro.agent.packager import GENERATED_ARTIFACTS_DIR
    artifacts_root = os.path.abspath(os.path.join(GENERATED_ARTIFACTS_DIR, artifact_id))
    target = os.path.abspath(os.path.join(artifacts_root, filename))
    if os.path.commonpath([artifacts_root, target]) != artifacts_root or not os.path.isfile(target):
        return jsonify({"error": "Berkas artifak tidak ditemukan"}), 404
    inline_mode = request.args.get('inline', '0') == '1'
    return send_file(
        target,
        as_attachment=not inline_mode,
        download_name=os.path.basename(target),
        conditional=True,
    )


def _compute_dynamic_doc_char_budget() -> int:
    from shiro.server_state import state
    from shiro.models import is_qwen38_27b_uncensored, get_active_model_ctx
    env_max = os.environ.get("SHIRO_MAX_DOC_CHARS", "").strip()
    if env_max.isdigit():
        return int(env_max)
    active_model_path = getattr(state.llm, 'model_path', '') if state.llm else ''
    if is_qwen38_27b_uncensored(active_model_path):
        active_ctx_chars = get_active_model_ctx(state.llm) * 3 if state.llm else 1_500_000
        return max(500_000, min(3_000_000, active_ctx_chars))
    return 120_000


def _process_single_uploaded_storage(f_storage, doc_max_chars: Optional[int] = None) -> dict:
    """Memproses satu berkas unggahan (dokumen, kode, arsip, gambar, atau video)."""
    import base64
    from werkzeug.utils import secure_filename
    from shiro.document import extract_text_from_file, SUPPORTED_EXTENSIONS, is_probably_text_file, extract_documents_from_archive
    from shiro.vision.video import is_video_filename, extract_video_frames_and_metadata

    raw_name = os.path.basename(f_storage.filename or "")
    if not raw_name:
        return {"kind": "error", "error": "Nama file kosong."}

    ext = os.path.splitext(raw_name)[1].lower()
    image_exts = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
    archive_exts = {".zip", ".tar", ".tgz", ".gz", ".bz2", ".xz"}

    # 1. Video -> simpan & ekstrak keyframe kronologis
    if is_video_filename(raw_name):
        vid_dir = os.path.join("data", "uploads", "videos")
        os.makedirs(vid_dir, exist_ok=True)
        safe_base = secure_filename(raw_name) or f"video_{os.urandom(3).hex()}{ext or '.mp4'}"
        save_path = os.path.join(vid_dir, safe_base)
        f_storage.save(save_path)
        max_frames = int(os.environ.get("SHIRO_VIDEO_MAX_FRAMES", "12"))
        vid_meta = extract_video_frames_and_metadata(save_path, filename=raw_name, max_frames=max_frames)
        if not vid_meta.get("success"):
            return {"kind": "error", "filename": raw_name, "error": vid_meta.get("error", "Gagal membaca video.")}
        vid_meta["kind"] = "video"
        vid_meta["url"] = f"/api/videos/{safe_base}"
        return vid_meta

    # 2. Gambar -> simpan & kembalikan data URI
    if ext in image_exts:
        upload_dir = os.path.join("data", "uploads")
        os.makedirs(upload_dir, exist_ok=True)
        save_path = os.path.join(upload_dir, raw_name)
        f_storage.save(save_path)
        with open(save_path, "rb") as im_f:
            b64 = base64.b64encode(im_f.read()).decode("ascii")
        mime_ext = "jpeg" if ext in (".jpg", ".jpeg") else ext.lstrip(".")
        return {
            "kind": "image",
            "filename": raw_name,
            "data_url": f"data:image/{mime_ext};base64,{b64}",
            "url": f"/api/files/{raw_name}",
        }

    # 3. Arsip (.zip, .tar.gz, .tgz, .tar) -> ekstrak seluruh berkas kode/dokumen di dalamnya
    upload_dir = os.path.join("data", "uploads")
    os.makedirs(upload_dir, exist_ok=True)
    save_path = os.path.join(upload_dir, raw_name)
    f_storage.save(save_path)

    if any(raw_name.lower().endswith(sfx) for sfx in (".zip", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar.xz", ".txz", ".tar")) or ext in archive_exts:
        budget = doc_max_chars or _compute_dynamic_doc_char_budget()
        arch_docs = extract_documents_from_archive(save_path, max_total_chars=budget)
        if arch_docs:
            for ad in arch_docs:
                ad["preview"] = (ad.get("text", "")[:200] + ("..." if len(ad.get("text", "")) > 200 else ""))
                ad["url"] = f"/api/files/{raw_name}"
                ad["archive_source"] = raw_name
            return {"kind": "archive_docs", "filename": raw_name, "documents": arch_docs}

    # 4. Dokumen / kode pemrograman biasa (termasuk custom extension via is_probably_text_file)
    if ext not in SUPPORTED_EXTENSIONS and not is_probably_text_file(save_path):
        try:
            os.remove(save_path)
        except Exception:
            pass
        return {
            "kind": "error",
            "filename": raw_name,
            "error": f"Format biner '{ext or raw_name}' tidak dapat diekstrak sebagai teks, gambar, atau video.",
        }

    budget = doc_max_chars or _compute_dynamic_doc_char_budget()
    res = extract_text_from_file(save_path, filename=raw_name, max_chars=budget)
    if not res.get("success"):
        return {"kind": "error", "filename": raw_name, "error": res.get("error", "Gagal membaca berkas.")}

    text = res.get("text", "")
    res["kind"] = "document"
    res["preview"] = text[:200] + ("..." if len(text) > 200 else "")
    res["url"] = f"/api/files/{raw_name}"
    res["filename"] = raw_name
    return res


@documents_bp.route('/api/upload/documents', methods=['POST'])
def upload_multiple_documents():
    """Mengunggah banyak berkas (kode, dokumen, arsip zip, gambar, dan video) secara bersamaan tanpa batas 1 file."""
    if not verify_api_key(allow_web_ui=True):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        file_list = request.files.getlist('files') or request.files.getlist('file')
        file_list = [f for f in file_list if f and getattr(f, 'filename', '')]
        if not file_list:
            return jsonify({"success": False, "error": "Tidak ada berkas yang dipilih."}), 400

        doc_budget = _compute_dynamic_doc_char_budget()
        documents = []
        images = []
        videos = []
        errors = []

        for f_item in file_list:
            parsed = _process_single_uploaded_storage(f_item, doc_max_chars=doc_budget)
            kind = parsed.get("kind")
            if kind == "document":
                documents.append(parsed)
            elif kind == "archive_docs":
                documents.extend(parsed.get("documents") or [])
            elif kind == "image":
                images.append(parsed)
            elif kind == "video":
                videos.append(parsed)
            else:
                errors.append({"filename": parsed.get("filename") or f_item.filename, "error": parsed.get("error", "Error")})

        has_any = bool(documents or images or videos)
        status_code = 200 if has_any else 400
        return jsonify({
            "success": has_any,
            "documents": documents,
            "images": images,
            "videos": videos,
            "errors": errors,
            "total_uploaded": len(documents) + len(images) + len(videos),
        }), status_code
    except Exception as e:
        print(f"[Documents] Error in upload_multiple_documents: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@documents_bp.route('/api/upload/video', methods=['POST'])
def upload_video_route():
    """Mengunggah satu atau banyak berkas video dan mengekstrak keyframe untuk Qwen3.8-27B Vision."""
    if not verify_api_key(allow_web_ui=True):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        file_list = request.files.getlist('files') or request.files.getlist('video') or request.files.getlist('file')
        file_list = [f for f in file_list if f and getattr(f, 'filename', '')]
        if not file_list:
            return jsonify({"success": False, "error": "Tidak ada berkas video yang dipilih."}), 400

        videos = []
        errors = []
        for f_item in file_list:
            parsed = _process_single_uploaded_storage(f_item)
            if parsed.get("kind") == "video":
                videos.append(parsed)
            else:
                errors.append({"filename": f_item.filename, "error": parsed.get("error", "Bukan berkas video valid.")})

        if not videos:
            return jsonify({"success": False, "error": errors[0]["error"] if errors else "Gagal memproses video.", "errors": errors}), 400
        return jsonify({"success": True, "video": videos[0], "videos": videos, "errors": errors})
    except Exception as e:
        print(f"[Documents] Error in upload_video_route: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@documents_bp.route('/api/videos/<path:filename>', methods=['GET'])
def get_uploaded_video(filename):
    """Menyajikan berkas video unggahan dengan dukungan range/seeking browser."""
    vid_dir = os.path.abspath(os.path.join("data", "uploads", "videos"))
    target = os.path.abspath(os.path.join(vid_dir, filename))
    if os.path.commonpath([vid_dir, target]) != vid_dir or not os.path.isfile(target):
        return jsonify({"error": "Video tidak ditemukan"}), 404
    return send_file(target, conditional=True)

@documents_bp.route('/api/document/preview', methods=['GET'])
def preview_document():
    """Retrieve extracted text and metadata of an uploaded document"""
    filename = request.args.get('filename')
    if not filename:
        return jsonify({"success": False, "error": "Parameter filename wajib diisi"}), 400
    
    upload_dir = os.path.abspath(os.path.join("data", "uploads"))
    target = os.path.abspath(os.path.join(upload_dir, filename))
    if not target.startswith(upload_dir) or not os.path.exists(target):
        return jsonify({"success": False, "error": "File tidak ditemukan"}), 404

    from shiro.document import extract_text_from_file
    res = extract_text_from_file(target, filename=filename)
    res["url"] = f"/api/files/{filename}"
    return jsonify(res)

@documents_bp.route('/api/images/<path:filename>', methods=['GET'])
@documents_bp.route('/images/<path:filename>', methods=['GET'])
def get_uploaded_image(filename):
    """Serve image from training_data/vision/images/ or data/uploads/"""
    v_dir = os.path.abspath(os.path.join("training_data", "vision", "images"))
    target_v = os.path.abspath(os.path.join(v_dir, filename))
    if target_v.startswith(v_dir) and os.path.exists(target_v):
        return send_file(target_v)
    
    u_dir = os.path.abspath(os.path.join("data", "uploads"))
    target_u = os.path.abspath(os.path.join(u_dir, filename))
    if target_u.startswith(u_dir) and os.path.exists(target_u):
        return send_file(target_u)
        
    return jsonify({"error": "Gambar tidak ditemukan"}), 404
