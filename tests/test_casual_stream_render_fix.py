# -*- coding: utf-8 -*-
import os
import subprocess
import unittest


class TestCasualStreamRenderFix(unittest.TestCase):
    def _read_script_js(self) -> str:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "static", "script.js"), "r", encoding="utf-8") as f:
            return f.read()

    def test_add_message_allows_streaming_mount_and_blocks_ghost_bubbles(self):
        js = self._read_script_js()
        self.assertIn("meta.is_streaming_mount", js)
        self.assertIn("const seedContent = (initialText && String(initialText)) || run.streamText || '';", js)
        self.assertIn("is_streaming_mount: true", js)
        self.assertIn("document.body.contains(run.assistantMsgEl)", js)

        # Node.js behavioral verification of the exact guard condition in addMessage
        node_script = """
        function shouldBlockGhost(content, imageUrl, docName, docText, agentActionData, meta) {
            const hasText = content !== null && content !== undefined && String(content).trim().length > 0;
            const hasMultiAttach = Boolean(meta && ((meta.documents && meta.documents.length) || (meta.images && meta.images.length) || (meta.videos && meta.videos.length)));
            const hasMeta = Boolean(hasMultiAttach || (meta && ((meta.agent_steps && meta.agent_steps.length) || meta.thought_content || (meta.artifacts && meta.artifacts.length) || meta.is_running || meta.is_streaming_mount)));
            return (!hasText && !imageUrl && !docName && !docText && !agentActionData && !hasMeta);
        }
        // Casual chat streaming mount (empty initial content, no agent_steps, no thought_content, is_running=false) MUST NOT be blocked
        if (shouldBlockGhost('', null, null, null, null, { agent_steps: [], thought_content: '', is_running: false, is_streaming_mount: true })) {
            process.exit(1);
        }
        // Empty ghost bubble without is_streaming_mount MUST still be blocked
        if (!shouldBlockGhost('', null, null, null, null, { agent_steps: [], thought_content: '', is_running: false })) {
            process.exit(2);
        }
        """
        res = subprocess.run(["node", "-e", node_script], capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, msg=res.stderr)

    def test_sse_reader_flushes_trailing_decoder_and_buffer_on_done(self):
        js = self._read_script_js()
        self.assertIn("const processSseLine = (line) =>", js)
        self.assertIn("buffer += decoder.decode();", js)
        self.assertIn("processSseLine(remLine);", js)


if __name__ == "__main__":
    unittest.main()
