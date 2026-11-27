# -*- coding: utf-8 -*-
import os
import tempfile
import unittest
import zipfile

from shiro.agent.packager import (
    create_archive_artifact,
    detect_archive_claim_in_reply,
    detect_archive_request,
    extract_named_files_from_markdown,
    infer_project_name_from_text,
)


class TestArchiveNamingAndFormat(unittest.TestCase):
    def test_react_e_target_in_code_block_never_triggers_e_tar(self):
        reply = (
            "Berikut aplikasi Next.js lengkap untuk scraping Otakudesu.\n\n"
            "### File: package.json\n"
            "```json\n"
            '{"name": "otakudesu-anime-scraper", "version": "1.0.0"}\n'
            "```\n\n"
            "### File: components/SearchBar.tsx\n"
            "```tsx\n"
            "export function SearchBar({ onChange }: any) {\n"
            "  return <input onChange={(e) => onChange(e.target.value)} />;\n"
            "}\n"
            "```\n\n"
            "Cara menjalankan:\n"
            "1. Ekstrak ZIP -> masuk folder\n"
            "2. `npm install && npm run dev`\n"
        )
        # Tidak boleh menangkap `e.target` sebagai `e.tar`!
        claim = detect_archive_claim_in_reply(reply)
        self.assertIsNone(claim)

        files = extract_named_files_from_markdown(reply)
        proj_name = infer_project_name_from_text(reply, files)
        self.assertEqual(proj_name, "otakudesu-anime-scraper")

        with tempfile.TemporaryDirectory() as tmpdir:
            art = create_archive_artifact(files, fmt="zip", project_name=proj_name, base_dir=tmpdir)
            self.assertEqual(art["filename"], "otakudesu-anime-scraper.zip")
            self.assertEqual(art["format"], "zip")
            arch_path = os.path.join(tmpdir, art["id"], art["filename"])
            self.assertTrue(zipfile.is_zipfile(arch_path))

    def test_mismatched_extension_or_one_char_archive_name_is_normalized(self):
        files = [
            {
                "filename": "package.json",
                "basename": "package.json",
                "content": '{"name": "otakudesu-web-app"}\n',
                "language": "json",
            }
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1-char stem `e.tar` ditolak -> fallback ke nama proyek dari package.json + ekstensi .zip
            art1 = create_archive_artifact(files, fmt="zip", archive_name="e.tar", base_dir=tmpdir)
            self.assertEqual(art1["filename"], "otakudesu-web-app.zip")
            self.assertEqual(art1["format"], "zip")

            # Ekstensi tidak cocok (`otakudesu.tar` untuk format `zip`) -> dipaksa `.zip`
            art2 = create_archive_artifact(files, fmt="zip", archive_name="otakudesu.tar", base_dir=tmpdir)
            self.assertEqual(art2["filename"], "otakudesu.zip")
            self.assertEqual(art2["format"], "zip")

    def test_detect_archive_request_prefers_zip_over_indonesian_tar_word(self):
        prompt = (
            "Buatkan aplikasi web lokal full-stack Next.js untuk scraping otakudesu. "
            "Sertakan daftar episode dan komentar. "
            "Pastikan di akhir semua file dijadikan 1 dan bentukannya zip agar bisa diunduh langsung."
        )
        req = detect_archive_request(prompt)
        self.assertIsNotNone(req)
        self.assertEqual(req["format"], "zip")

        # Slang "tar" (nanti) + "zip" tetap harus menghasilkan "zip"
        req2 = detect_archive_request("tar tolong semua file dijadikan zip ya")
        self.assertIsNotNone(req2)
        self.assertEqual(req2["format"], "zip")

        # Permintaan eksplisit .tar tetap harus menghasilkan "tar"
        req3 = detect_archive_request("kompres semua file ke format .tar")
        self.assertIsNotNone(req3)
        self.assertEqual(req3["format"], "tar")

    def test_infer_project_name_from_folder_tree_and_layout_title(self):
        reply_tree = (
            "Struktur proyek:\n"
            "```\n"
            "anime-scraper-next/\n"
            "├── package.json\n"
            "└── src/\n"
            "```\n"
        )
        self.assertEqual(infer_project_name_from_text(reply_tree, []), "anime-scraper-next")

        layout_files = [
            {
                "filename": "app/layout.tsx",
                "basename": "layout.tsx",
                "content": 'export const metadata = { title: "Otakudesu Local Viewer" };\n',
                "language": "tsx",
            }
        ]
        self.assertEqual(infer_project_name_from_text("", layout_files), "otakudesu-local-viewer")


if __name__ == "__main__":
    unittest.main()
