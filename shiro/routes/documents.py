# -*- coding: utf-8 -*-
"""
Shiro Document & File Management Routes
Handles document upload, text extraction, previews, and static file/image serving.
"""

import os
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

        res = extract_text_from_file(save_path, filename=f.filename)
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
    return send_file(target, as_attachment=as_attachment)

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
