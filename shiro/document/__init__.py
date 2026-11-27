from shiro.document.reader import (
    extract_text_from_file,
    extract_text_from_folder,
    extract_documents_from_archive,
    detect_document_intent,
    build_document_prompt,
    build_multi_document_prompt,
    SUPPORTED_EXTENSIONS,
    is_probably_text_file
)

__all__ = [
    "extract_text_from_file",
    "extract_text_from_folder",
    "extract_documents_from_archive",
    "detect_document_intent",
    "build_document_prompt",
    "build_multi_document_prompt",
    "SUPPORTED_EXTENSIONS",
    "is_probably_text_file"
]
