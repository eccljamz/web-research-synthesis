"""Unit and Integration Tests for Local Web Dashboard & REST Server.

Milestone 4 Component Tested:
- ResearchServerHandler & ServerState (server.py)
- Threading HTTP Server endpoints (GET /, /api/health, /api/briefs, /brief/<id>, /api/synthesize)
- Synchronous and asynchronous synthesis job polling
- Safe resource teardown and error handling

Pure Python Standard Library (unittest, urllib.request) - Zero External Dependencies.
"""

from __future__ import annotations

import json
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict

# Ensure repository root and src directory are on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from research_synthesis.models import (
        BriefMetadata,
        ResearchBrief,
        SourceCitation,
        ThematicSection,
    )
    from research_synthesis.server import (
        ResearchServerHandler,
        ServerState,
        SynthesisJob,
    )
except ImportError:
    from src.research_synthesis.models import (
        BriefMetadata,
        ResearchBrief,
        SourceCitation,
        ThematicSection,
    )
    from src.research_synthesis.server import (
        ResearchServerHandler,
        ServerState,
        SynthesisJob,
    )

from http.server import ThreadingHTTPServer


def find_free_port() -> int:
    """Find a dynamically available TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class TestServerState(unittest.TestCase):
    """Tests for in-memory and disk state management."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.temp_dir.name)
        self.state = ServerState(output_dir=self.output_dir, default_mode="mock")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_job_lifecycle(self):
        job = self.state.create_job("Solid-State Batteries", mode="mock")
        self.assertTrue(job.job_id.startswith("job-"))
        self.assertEqual(job.status, "queued")
        self.assertEqual(job.topic, "Solid-State Batteries")
        self.assertEqual(job.mode, "mock")

        fetched = self.state.get_job(job.job_id)
        self.assertEqual(fetched.job_id, job.job_id)

    def test_brief_registration_and_persistence(self):
        job = self.state.create_job("Battery Tech", mode="mock")
        mock_brief = ResearchBrief(
            brief_id="brief-state-test",
            topic="Battery Tech Evolution",
            executive_summary="Executive summary context regarding solid state battery development.",
            key_takeaways=[],
            thematic_sections=[
                ThematicSection(
                    section_id="sec-01",
                    title="Section 1",
                    narrative="Section narrative content.",
                )
            ],
            sources=[
                SourceCitation(
                    citation_index=1,
                    source_id="SRC-01",
                    title="Source 1",
                    url="https://source1.org",
                    snippet="Snippet text for testing.",
                )
            ],
        )

        self.state.register_completed_brief(job, mock_brief)
        self.assertEqual(job.status, "completed")
        self.assertEqual(job.brief_id, "brief-state-test")

        # Verify brief is indexed
        indexed = self.state.get_brief("brief-state-test")
        self.assertIsNotNone(indexed)
        self.assertEqual(indexed.topic, "Battery Tech Evolution")

        # Verify brief metadata list
        briefs_list = self.state.list_briefs()
        self.assertEqual(len(briefs_list), 1)
        self.assertEqual(briefs_list[0]["brief_id"], "brief-state-test")

        # Verify files written to disk
        self.assertTrue(any(self.output_dir.glob("*.json")))
        self.assertTrue(any(self.output_dir.glob("*.md")))
        self.assertTrue(any(self.output_dir.glob("*.html")))


class TestResearchServerEndpoints(unittest.TestCase):
    """Integration tests executing HTTP requests against ResearchServerHandler."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.output_dir = Path(cls.temp_dir.name)
        cls.state = ServerState(output_dir=cls.output_dir, default_mode="mock")

        class BoundHandler(ResearchServerHandler):
            server_state = cls.state

        cls.port = find_free_port()
        cls.server = ThreadingHTTPServer(("127.0.0.1", cls.port), BoundHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp_dir.cleanup()

    def _http_get(self, path: str) -> Tuple[int, bytes, Dict[str, str]]:
        url = f"{self.base_url}{path}"
        req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req) as resp:
                headers = dict(resp.getheaders())
                return resp.status, resp.read(), headers
        except urllib.error.HTTPError as e:
            try:
                return e.code, e.read(), dict(e.headers)
            finally:
                e.close()

    def _http_post(self, path: str, data: Dict[str, Any]) -> Tuple[int, bytes, Dict[str, str]]:
        url = f"{self.base_url}{path}"
        payload = json.dumps(data).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as resp:
                headers = dict(resp.getheaders())
                return resp.status, resp.read(), headers
        except urllib.error.HTTPError as e:
            try:
                return e.code, e.read(), dict(e.headers)
            finally:
                e.close()

    def test_dashboard_index_html(self):
        status, body, headers = self._http_get("/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers.get("Content-Type", ""))
        body_text = body.decode("utf-8")
        self.assertIn("Autonomous Web Research &amp; Synthesis Engine", body_text)
        self.assertIn("Synthesize Research Brief", body_text)

    def test_api_health(self):
        status, body, _ = self._http_get("/api/health")
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertEqual(data.get("status"), "ok")
        self.assertEqual(data.get("version"), "0.1.0")

    def test_api_briefs_empty_initially(self):
        status, body, _ = self._http_get("/api/briefs")
        self.assertEqual(status, 200)
        data = json.loads(body.decode("utf-8"))
        self.assertIsInstance(data, list)

    def test_synthesize_sync_and_get_artifacts(self):
        """Test synchronous synthesis request through HTTP POST, then inspect JSON, HTML, and MD endpoints."""
        topic = "Next-Generation Solid-State Battery Commercialization"
        status, body, _ = self._http_post("/api/synthesize", {
            "topic": topic,
            "mode": "mock",
            "async": False,
        })
        self.assertEqual(status, 200)
        resp_data = json.loads(body.decode("utf-8"))
        self.assertIn("job", resp_data)
        self.assertIn("brief", resp_data)
        self.assertEqual(resp_data["job"]["status"], "completed")

        brief_id = resp_data["job"]["brief_id"]
        self.assertTrue(brief_id.startswith("brief-"))

        # 1. Test GET /api/briefs/<brief_id>
        b_status, b_body, _ = self._http_get(f"/api/briefs/{brief_id}")
        self.assertEqual(b_status, 200)
        b_data = json.loads(b_body.decode("utf-8"))
        self.assertEqual(b_data["brief_id"], brief_id)
        self.assertEqual(b_data["topic"], topic)
        self.assertGreaterEqual(len(b_data["thematic_sections"]), 2)

        # 2. Test GET /brief/<brief_id> (HTML)
        h_status, h_body, h_headers = self._http_get(f"/brief/{brief_id}")
        self.assertEqual(h_status, 200)
        self.assertIn("text/html", h_headers.get("Content-Type", ""))
        self.assertIn("<!DOCTYPE html>", h_body.decode("utf-8"))

        # 3. Test GET /brief/<brief_id>/markdown (Markdown)
        m_status, m_body, m_headers = self._http_get(f"/brief/{brief_id}/markdown")
        self.assertEqual(m_status, 200)
        self.assertIn("text/markdown", m_headers.get("Content-Type", ""))
        self.assertIn("# Research Brief:", m_body.decode("utf-8"))

        # Rendered Obsidian Note
        o_status, o_body, o_headers = self._http_get(f"/brief/{brief_id}/obsidian")
        self.assertEqual(o_status, 200)
        self.assertIn("text/markdown", o_headers.get("Content-Type", ""))
        self.assertIn("> [!summary] Executive Summary", o_body.decode("utf-8"))

        # Obsidian Vault Manifest
        v_status, v_body, _ = self._http_get(f"/brief/{brief_id}/obsidian-vault")
        self.assertEqual(v_status, 200)
        vault_data = json.loads(v_body.decode("utf-8"))
        self.assertIn("files", vault_data)
        self.assertIn("Index.md", vault_data["files"])
        self.assertIn("Knowledge_Graph.canvas", vault_data["files"])

    def test_synthesize_async_and_poll_status(self):
        """Test async synthesis, poll job until completed, and verify progress tracking."""
        topic = "Global Supply Chain Re-Shoring Dynamics"
        status, body, _ = self._http_post("/api/synthesize", {
            "topic": topic,
            "mode": "mock",
            "async": True,
        })
        self.assertEqual(status, 202)
        resp_data = json.loads(body.decode("utf-8"))
        job_id = resp_data["job_id"]
        self.assertTrue(job_id.startswith("job-"))

        # Poll job status
        max_attempts = 30
        completed = False
        final_job = None

        for _ in range(max_attempts):
            time.sleep(0.1)
            j_status, j_body, _ = self._http_get(f"/api/jobs/{job_id}")
            self.assertEqual(j_status, 200)
            job_data = json.loads(j_body.decode("utf-8"))
            if job_data["status"] == "completed":
                completed = True
                final_job = job_data
                break

        self.assertTrue(completed, "Async job failed to complete within polling window")
        self.assertEqual(final_job["progress"]["percentage"], 100)
        self.assertTrue(final_job["brief_id"].startswith("brief-"))

    def test_bad_requests_and_404s(self):
        # 1. Missing topic
        status, body, _ = self._http_post("/api/synthesize", {"topic": "   "})
        self.assertEqual(status, 400)

        # 2. Unknown brief ID
        status, body, _ = self._http_get("/api/briefs/brief-nonexistent")
        self.assertEqual(status, 404)

        # 3. Unknown job ID
        status, body, _ = self._http_get("/api/jobs/job-unknown")
        self.assertEqual(status, 404)

        # 4. Unknown endpoint
        status, body, _ = self._http_get("/api/unknown_endpoint")
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
