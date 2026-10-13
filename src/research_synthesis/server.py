"""Zero-Dependency Local Web Server & Interactive Dashboard.

Milestone 4 - Autonomous Web Research & Knowledge Synthesis System.
Pure Python Standard Library (3.10+) - Zero External Dependencies.

Provides:
1. Local Threading HTTP Server running on standard library `http.server`.
2. Interactive Single-Page Web Dashboard (zero CDN/external dependencies, 100% offline capable).
3. Real-time background job execution with stage-by-stage progress polling.
4. REST API endpoints for automated headless integration.
5. In-browser interactive viewing of HTML reports, Markdown, and JSON schema outputs.
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
import sys
import threading
import time
import urllib.parse
import webbrowser
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from research_synthesis.models import ResearchBrief
    from research_synthesis.pipeline import ResearchPipeline
except ImportError:
    try:
        from src.research_synthesis.models import ResearchBrief
        from src.research_synthesis.pipeline import ResearchPipeline
    except ImportError:
        from .models import ResearchBrief
        from .pipeline import ResearchPipeline


# ============================================================================
# Job State & Management
# ============================================================================

class SynthesisJob:
    """Tracks asynchronous state and progress for a research synthesis run."""

    def __init__(self, job_id: str, topic: str, mode: str = "mock") -> None:
        self.job_id = job_id
        self.topic = topic
        self.mode = mode
        self.status = "queued"  # "queued", "running", "completed", "failed"
        self.progress_stage = 0
        self.total_stages = 6
        self.progress_message = "Job queued..."
        self.error: Optional[str] = None
        self.brief: Optional[ResearchBrief] = None
        self.brief_id: Optional[str] = None
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.completed_at: Optional[str] = None
        self.elapsed_sec: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "topic": self.topic,
            "mode": self.mode,
            "status": self.status,
            "progress": {
                "stage": self.progress_stage,
                "total_stages": self.total_stages,
                "percentage": int((self.progress_stage / self.total_stages) * 100) if self.total_stages > 0 else 0,
                "message": self.progress_message,
            },
            "brief_id": self.brief_id,
            "error": self.error,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "elapsed_sec": round(self.elapsed_sec, 3),
        }


class ServerState:
    """Thread-safe state container managing jobs and archived briefs."""

    def __init__(self, output_dir: Path, default_mode: str = "mock") -> None:
        self.output_dir = output_dir
        self.default_mode = default_mode
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.jobs: Dict[str, SynthesisJob] = {}
        self.briefs: Dict[str, ResearchBrief] = {}
        self.brief_metadata_cache: List[Dict[str, Any]] = []
        self._load_existing_briefs()

    def _load_existing_briefs(self) -> None:
        """Scan output directory for existing saved brief JSON files."""
        if not self.output_dir.exists():
            return
        for json_file in self.output_dir.glob("*.json"):
            if json_file.name == "verification_report.json":
                continue
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and "brief_id" in data and "thematic_sections" in data:
                    brief = ResearchBrief.from_dict(data)
                    self.briefs[brief.brief_id] = brief
                    self.brief_metadata_cache.append({
                        "brief_id": brief.brief_id,
                        "topic": brief.topic,
                        "generated_at": brief.generated_at,
                        "sections_count": len(brief.thematic_sections),
                        "sources_count": len(brief.sources),
                        "file_stem": json_file.stem,
                    })
            except Exception:
                continue
        # Sort newest first
        self.brief_metadata_cache.sort(key=lambda b: b.get("generated_at", ""), reverse=True)

    def create_job(self, topic: str, mode: Optional[str] = None) -> SynthesisJob:
        with self.lock:
            job_id = f"job-{int(time.time() * 1000):x}"
            chosen_mode = mode if mode in ("live", "mock") else self.default_mode
            job = SynthesisJob(job_id=job_id, topic=topic, mode=chosen_mode)
            self.jobs[job_id] = job
            return job

    def get_job(self, job_id: str) -> Optional[SynthesisJob]:
        with self.lock:
            return self.jobs.get(job_id)

    def register_completed_brief(self, job: SynthesisJob, brief: ResearchBrief) -> None:
        with self.lock:
            job.status = "completed"
            job.brief = brief
            job.brief_id = brief.brief_id
            job.completed_at = datetime.now(timezone.utc).isoformat()
            self.briefs[brief.brief_id] = brief

            # Save artifacts
            clean_name = re.sub(r"[^\w\-]+", "_", brief.topic.lower()).strip("_")[:40] or "brief"
            base_path = self.output_dir / clean_name

            try:
                # 1. JSON
                with open(f"{base_path}.json", "w", encoding="utf-8") as f:
                    f.write(brief.to_json())
                # 2. Markdown
                with open(f"{base_path}.md", "w", encoding="utf-8") as f:
                    f.write(brief.to_markdown())
                # 3. HTML
                with open(f"{base_path}.html", "w", encoding="utf-8") as f:
                    f.write(brief.to_html())
            except Exception as e:
                logging.error(f"Failed to save exported artifacts to disk: {e}")

            # Update cache
            entry = {
                "brief_id": brief.brief_id,
                "topic": brief.topic,
                "generated_at": brief.generated_at,
                "sections_count": len(brief.thematic_sections),
                "sources_count": len(brief.sources),
                "file_stem": clean_name,
            }
            # Remove existing if any
            self.brief_metadata_cache = [b for b in self.brief_metadata_cache if b["brief_id"] != brief.brief_id]
            self.brief_metadata_cache.insert(0, entry)

    def get_brief(self, brief_id: str) -> Optional[ResearchBrief]:
        with self.lock:
            return self.briefs.get(brief_id)

    def list_briefs(self) -> List[Dict[str, Any]]:
        with self.lock:
            return list(self.brief_metadata_cache)


# ============================================================================
# Web Dashboard Single-Page HTML / CSS / JS Template
# ============================================================================

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Autonomous Web Research & Knowledge Synthesis</title>
    <style>
        :root {
            --bg-color: #f8fafc;
            --card-bg: #ffffff;
            --text-primary: #0f172a;
            --text-secondary: #475569;
            --border: #e2e8f0;
            --accent: #2563eb;
            --accent-hover: #1d4ed8;
            --accent-light: #eff6ff;
            --code-bg: #f1f5f9;
            --success: #16a34a;
            --warning: #ca8a04;
            --danger: #dc2626;
        }
        @media (prefers-color-scheme: dark) {
            :root {
                --bg-color: #0b0f19;
                --card-bg: #1e293b;
                --text-primary: #f8fafc;
                --text-secondary: #94a3b8;
                --border: #334155;
                --accent: #3b82f6;
                --accent-hover: #60a5fa;
                --accent-light: #1e3a8a;
                --code-bg: #0f172a;
            }
        }
        [data-theme="light"] {
            --bg-color: #f8fafc;
            --card-bg: #ffffff;
            --text-primary: #0f172a;
            --text-secondary: #475569;
            --border: #e2e8f0;
            --accent: #2563eb;
            --accent-light: #eff6ff;
            --code-bg: #f1f5f9;
        }
        [data-theme="dark"] {
            --bg-color: #0b0f19;
            --card-bg: #1e293b;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --border: #334155;
            --accent: #3b82f6;
            --accent-light: #1e3a8a;
            --code-bg: #0f172a;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-primary);
            line-height: 1.5;
            padding: 1.5rem;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding-bottom: 1.25rem;
            margin-bottom: 1.5rem;
            border-bottom: 1px solid var(--border);
        }
        .brand {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }
        .brand-icon {
            font-size: 1.75rem;
            background: var(--accent-light);
            color: var(--accent);
            padding: 0.35rem 0.6rem;
            border-radius: 8px;
            font-weight: 800;
        }
        .brand-title {
            font-size: 1.35rem;
            font-weight: 700;
        }
        .brand-subtitle {
            font-size: 0.85rem;
            color: var(--text-secondary);
        }
        .header-actions {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }
        .theme-toggle, .btn {
            background: var(--card-bg);
            border: 1px solid var(--border);
            color: var(--text-primary);
            padding: 0.5rem 0.85rem;
            border-radius: 6px;
            cursor: pointer;
            font-size: 0.875rem;
            font-weight: 500;
            transition: all 0.15s ease;
        }
        .btn:hover, .theme-toggle:hover {
            border-color: var(--accent);
            color: var(--accent);
        }
        .btn-primary {
            background: var(--accent);
            color: #ffffff !important;
            border-color: var(--accent);
        }
        .btn-primary:hover {
            background: var(--accent-hover);
        }
        .main-layout {
            display: grid;
            grid-template-columns: 360px 1fr;
            gap: 1.5rem;
        }
        @media (max-width: 900px) {
            .main-layout { grid-template-columns: 1fr; }
        }
        .card {
            background: var(--card-bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 1.25rem;
            margin-bottom: 1.25rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
        }
        .card-header {
            font-size: 1.05rem;
            font-weight: 600;
            margin-bottom: 1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .form-group {
            margin-bottom: 1rem;
        }
        label {
            display: block;
            font-size: 0.85rem;
            font-weight: 600;
            margin-bottom: 0.4rem;
            color: var(--text-secondary);
        }
        textarea, select, input[type="text"] {
            width: 100%;
            padding: 0.65rem;
            border: 1px solid var(--border);
            border-radius: 6px;
            background: var(--bg-color);
            color: var(--text-primary);
            font-size: 0.9rem;
            font-family: inherit;
        }
        textarea:focus, select:focus, input[type="text"]:focus {
            outline: none;
            border-color: var(--accent);
        }
        .samples {
            display: flex;
            flex-wrap: wrap;
            gap: 0.35rem;
            margin-top: 0.5rem;
        }
        .sample-chip {
            background: var(--code-bg);
            border: 1px solid var(--border);
            padding: 0.2rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            cursor: pointer;
            color: var(--text-secondary);
        }
        .sample-chip:hover {
            color: var(--accent);
            border-color: var(--accent);
        }
        .progress-bar-container {
            width: 100%;
            height: 8px;
            background: var(--code-bg);
            border-radius: 4px;
            overflow: hidden;
            margin: 0.75rem 0;
        }
        .progress-bar {
            height: 100%;
            width: 0%;
            background: var(--accent);
            transition: width 0.3s ease;
        }
        .progress-text {
            font-size: 0.85rem;
            color: var(--text-secondary);
            font-family: monospace;
        }
        .archive-list {
            list-style: none;
            max-height: 400px;
            overflow-y: auto;
        }
        .archive-item {
            padding: 0.75rem;
            border: 1px solid var(--border);
            border-radius: 6px;
            margin-bottom: 0.5rem;
            cursor: pointer;
            transition: all 0.15s ease;
        }
        .archive-item:hover {
            border-color: var(--accent);
            background: var(--accent-light);
        }
        .archive-item.active {
            border-color: var(--accent);
            background: var(--accent-light);
        }
        .archive-item-title {
            font-size: 0.875rem;
            font-weight: 600;
            margin-bottom: 0.25rem;
        }
        .archive-item-meta {
            font-size: 0.75rem;
            color: var(--text-secondary);
            display: flex;
            gap: 0.5rem;
        }
        .badge {
            background: var(--code-bg);
            padding: 0.15rem 0.4rem;
            border-radius: 4px;
            font-family: monospace;
            font-size: 0.75rem;
        }
        .tab-bar {
            display: flex;
            gap: 0.5rem;
            border-bottom: 1px solid var(--border);
            margin-bottom: 1rem;
        }
        .tab-btn {
            background: none;
            border: none;
            padding: 0.5rem 1rem;
            cursor: pointer;
            font-size: 0.9rem;
            font-weight: 600;
            color: var(--text-secondary);
            border-bottom: 2px solid transparent;
        }
        .tab-btn.active {
            color: var(--accent);
            border-bottom-color: var(--accent);
        }
        .tab-content {
            display: none;
        }
        .tab-content.active {
            display: block;
        }
        iframe.brief-frame {
            width: 100%;
            height: 750px;
            border: 1px solid var(--border);
            border-radius: 6px;
            background: #ffffff;
        }
        pre.code-view {
            background: var(--code-bg);
            border: 1px solid var(--border);
            border-radius: 6px;
            padding: 1rem;
            overflow-x: auto;
            max-height: 750px;
            font-family: monospace;
            font-size: 0.85rem;
            white-space: pre-wrap;
        }
        .empty-placeholder {
            text-align: center;
            padding: 4rem 1rem;
            color: var(--text-secondary);
        }
        .status-pill {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 0.4rem;
        }
        .status-pill.ready { background: var(--success); }
        .status-pill.running { background: var(--warning); animation: pulse 1s infinite; }
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.3; }
            100% { opacity: 1; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="brand">
                <div class="brand-icon">S</div>
                <div>
                    <div class="brand-title">Autonomous Web Research &amp; Synthesis Engine</div>
                    <div class="brand-subtitle">Extractive Knowledge Synthesis • Continuous IEEE [N] Attributions</div>
                </div>
            </div>
            <div class="header-actions">
                <span class="badge"><span class="status-pill ready" id="statusPill"></span><span id="serverStatusText">Ready</span></span>
                <button class="theme-toggle" onclick="toggleTheme()" title="Toggle Dark/Light Mode">Theme</button>
            </div>
        </header>

        <div class="main-layout">
            <!-- Sidebar: Controls & Archive -->
            <aside>
                <div class="card">
                    <div class="card-header">New Research Topic</div>
                    <form id="researchForm" onsubmit="submitResearch(event)">
                        <div class="form-group">
                            <label for="topicInput">Research Query or Topic</label>
                            <textarea id="topicInput" rows="3" placeholder="Enter research topic..." required>Next-Generation Solid-State Battery Commercialization</textarea>
                            <div class="samples">
                                <span class="sample-chip" onclick="setTopic('Next-Generation Solid-State Battery Commercialization')">Batteries</span>
                                <span class="sample-chip" onclick="setTopic('Global Supply Chain Re-Shoring and Friend-Shoring Dynamics')">Supply Chain</span>
                                <span class="sample-chip" onclick="setTopic('The Little Ice Age Climate Shocks in 17th Century Europe')">Little Ice Age</span>
                                <span class="sample-chip" onclick="setTopic('Microplastic Bioaccumulation in Agricultural Soil Ecosystems')">Microplastics</span>
                            </div>
                        </div>

                        <div class="form-group">
                            <label for="modeSelect">Retrieval Mode</label>
                            <select id="modeSelect">
                                <option value="mock" selected>Mock Corpus (Offline, Deterministic)</option>
                                <option value="live">Live Web (DuckDuckGo + Wikipedia)</option>
                            </select>
                        </div>

                        <button type="submit" class="btn btn-primary" id="submitBtn" style="width: 100%;">
                            Synthesize Research Brief
                        </button>
                    </form>
                </div>

                <div class="card" id="progressCard" style="display: none;">
                    <div class="card-header">
                        <span>Pipeline Progress</span>
                        <span class="badge" id="progressPercent">0%</span>
                    </div>
                    <div class="progress-bar-container">
                        <div class="progress-bar" id="progressBar"></div>
                    </div>
                    <div class="progress-text" id="progressMessage">Initializing...</div>
                </div>

                <div class="card">
                    <div class="card-header">
                        <span>Generated Briefs</span>
                        <button class="btn" style="padding: 0.2rem 0.5rem; font-size: 0.75rem;" onclick="loadBriefsArchive()">Refresh</button>
                    </div>
                    <ul class="archive-list" id="archiveList">
                        <li style="padding: 0.5rem; color: var(--text-secondary); font-size: 0.85rem;">No briefs loaded yet.</li>
                    </ul>
                </div>
            </aside>

            <!-- Main Content Area: Brief Viewer -->
            <main>
                <div class="card">
                    <div class="tab-bar">
                        <button class="tab-btn active" onclick="switchTab('html')">Interactive Brief (HTML)</button>
                        <button class="tab-btn" onclick="switchTab('markdown')">Markdown</button>
                        <button class="tab-btn" onclick="switchTab('json')">JSON Schema</button>
                        <div style="margin-left: auto; display: flex; gap: 0.5rem;">
                            <button class="btn" onclick="copyCurrentContent()" title="Copy active content to clipboard">Copy</button>
                            <button class="btn" onclick="downloadCurrentContent()" title="Download current artifact">Download</button>
                        </div>
                    </div>

                    <div id="emptyView" class="empty-placeholder">
                        <h3>No Research Brief Loaded</h3>
                        <p style="margin-top: 0.5rem;">Submit a research query on the left or select an archived brief to begin.</p>
                    </div>

                    <div id="htmlTab" class="tab-content active" style="display: none;">
                        <iframe id="briefIframe" class="brief-frame" title="Rendered Research Brief"></iframe>
                    </div>

                    <div id="markdownTab" class="tab-content">
                        <pre class="code-view" id="markdownCode"></pre>
                    </div>

                    <div id="jsonTab" class="tab-content">
                        <pre class="code-view" id="jsonCode"></pre>
                    </div>
                </div>
            </main>
        </div>
    </div>

    <script>
        let currentBriefId = null;
        let activeTab = 'html';
        let currentJobId = null;
        let pollInterval = null;

        function setTopic(text) {
            document.getElementById('topicInput').value = text;
        }

        function toggleTheme() {
            const body = document.documentElement;
            const current = body.getAttribute('data-theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
            const next = current === 'dark' ? 'light' : 'dark';
            body.setAttribute('data-theme', next);
            localStorage.setItem('rs_theme', next);
        }

        // Initialize theme
        const savedTheme = localStorage.getItem('rs_theme');
        if (savedTheme) {
            document.documentElement.setAttribute('data-theme', savedTheme);
        }

        function switchTab(tab) {
            activeTab = tab;
            document.querySelectorAll('.tab-btn').forEach((btn, idx) => {
                const tabs = ['html', 'markdown', 'json'];
                btn.classList.toggle('active', tabs[idx] === tab);
            });
            document.getElementById('htmlTab').style.display = (tab === 'html' && currentBriefId) ? 'block' : 'none';
            document.getElementById('markdownTab').style.display = (tab === 'markdown' && currentBriefId) ? 'block' : 'none';
            document.getElementById('jsonTab').style.display = (tab === 'json' && currentBriefId) ? 'block' : 'none';
        }

        async function submitResearch(event) {
            event.preventDefault();
            const topic = document.getElementById('topicInput').value.trim();
            const mode = document.getElementById('modeSelect').value;
            if (!topic) return;

            const submitBtn = document.getElementById('submitBtn');
            submitBtn.disabled = true;
            submitBtn.textContent = 'Synthesizing...';

            const progressCard = document.getElementById('progressCard');
            progressCard.style.display = 'block';
            updateProgress(0, 'Submitting job...');

            document.getElementById('statusPill').className = 'status-pill running';
            document.getElementById('serverStatusText').textContent = 'Processing';

            try {
                const res = await fetch('/api/synthesize', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ topic, mode, async: true })
                });
                const data = await res.json();
                if (data.job_id) {
                    currentJobId = data.job_id;
                    pollJobStatus();
                } else if (data.error) {
                    alert('Synthesis failed: ' + data.error);
                    resetSubmitButton();
                }
            } catch (err) {
                alert('Connection error: ' + err.message);
                resetSubmitButton();
            }
        }

        function updateProgress(percent, msg) {
            document.getElementById('progressBar').style.width = percent + '%';
            document.getElementById('progressPercent').textContent = percent + '%';
            document.getElementById('progressMessage').textContent = msg;
        }

        function pollJobStatus() {
            if (pollInterval) clearInterval(pollInterval);
            pollInterval = setInterval(async () => {
                if (!currentJobId) {
                    clearInterval(pollInterval);
                    return;
                }
                try {
                    const res = await fetch(`/api/jobs/${currentJobId}`);
                    const job = await res.json();

                    if (job.progress) {
                        updateProgress(job.progress.percentage, job.progress.message);
                    }

                    if (job.status === 'completed') {
                        clearInterval(pollInterval);
                        resetSubmitButton();
                        updateProgress(100, 'Complete!');
                        document.getElementById('statusPill').className = 'status-pill ready';
                        document.getElementById('serverStatusText').textContent = 'Ready';
                        if (job.brief_id) {
                            loadBrief(job.brief_id);
                            loadBriefsArchive();
                        }
                    } else if (job.status === 'failed') {
                        clearInterval(pollInterval);
                        resetSubmitButton();
                        alert('Synthesis error: ' + (job.error || 'Unknown failure'));
                        document.getElementById('statusPill').className = 'status-pill ready';
                        document.getElementById('serverStatusText').textContent = 'Error';
                    }
                } catch (e) {
                    console.error('Job polling error:', e);
                }
            }, 500);
        }

        function resetSubmitButton() {
            const submitBtn = document.getElementById('submitBtn');
            submitBtn.disabled = false;
            submitBtn.textContent = 'Synthesize Research Brief';
        }

        async function loadBrief(briefId) {
            currentBriefId = briefId;
            document.getElementById('emptyView').style.display = 'none';

            // 1. Load HTML
            const iframe = document.getElementById('briefIframe');
            iframe.src = `/brief/${briefId}`;

            // 2. Load JSON
            try {
                const resJson = await fetch(`/api/briefs/${briefId}`);
                const dataJson = await resJson.json();
                document.getElementById('jsonCode').textContent = JSON.stringify(dataJson, null, 2);
            } catch (e) {
                document.getElementById('jsonCode').textContent = 'Failed to load JSON: ' + e;
            }

            // 3. Load Markdown
            try {
                const resMd = await fetch(`/brief/${briefId}/markdown`);
                const dataMd = await resMd.text();
                document.getElementById('markdownCode').textContent = dataMd;
            } catch (e) {
                document.getElementById('markdownCode').textContent = 'Failed to load Markdown: ' + e;
            }

            switchTab(activeTab);

            // Highlight in archive
            document.querySelectorAll('.archive-item').forEach(el => {
                el.classList.toggle('active', el.dataset.briefId === briefId);
            });
        }

        async function loadBriefsArchive() {
            try {
                const res = await fetch('/api/briefs');
                const briefs = await res.json();
                const listEl = document.getElementById('archiveList');
                listEl.innerHTML = '';

                if (!briefs || briefs.length === 0) {
                    listEl.innerHTML = '<li style="padding: 0.5rem; color: var(--text-secondary); font-size: 0.85rem;">No briefs available.</li>';
                    return;
                }

                briefs.forEach(b => {
                    const li = document.createElement('li');
                    li.className = 'archive-item' + (b.brief_id === currentBriefId ? ' active' : '');
                    li.dataset.briefId = b.brief_id;
                    li.onclick = () => loadBrief(b.brief_id);
                    li.innerHTML = `
                        <div class="archive-item-title">${escapeHtml(b.topic)}</div>
                        <div class="archive-item-meta">
                            <span>ID: <code>${b.brief_id}</code></span>
                            <span>•</span>
                            <span>${b.sections_count} sec</span>
                            <span>•</span>
                            <span>${b.sources_count} src</span>
                        </div>
                    `;
                    listEl.appendChild(li);
                });
            } catch (e) {
                console.error('Failed to load briefs archive:', e);
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        function copyCurrentContent() {
            let content = '';
            if (activeTab === 'markdown') {
                content = document.getElementById('markdownCode').textContent;
            } else if (activeTab === 'json') {
                content = document.getElementById('jsonCode').textContent;
            } else {
                alert('To copy HTML, open the brief in a new tab or view Markdown/JSON tabs.');
                return;
            }
            navigator.clipboard.writeText(content).then(() => {
                alert('Copied to clipboard!');
            }).catch(e => {
                alert('Clipboard error: ' + e);
            });
        }

        function downloadCurrentContent() {
            if (!currentBriefId) return;
            let url = '', filename = '';
            if (activeTab === 'markdown') {
                url = `/brief/${currentBriefId}/markdown`;
                filename = `${currentBriefId}.md`;
            } else if (activeTab === 'json') {
                url = `/api/briefs/${currentBriefId}`;
                filename = `${currentBriefId}.json`;
            } else {
                url = `/brief/${currentBriefId}`;
                filename = `${currentBriefId}.html`;
            }

            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        }

        // On initial page load
        window.addEventListener('DOMContentLoaded', () => {
            loadBriefsArchive();
        });
    </script>
</body>
</html>
"""


# ============================================================================
# HTTP Request Handler
# ============================================================================

class ResearchServerHandler(BaseHTTPRequestHandler):
    """Pure Standard Library HTTP Request Handler for Research Synthesis Server."""

    server_state: ServerState

    def _send_cors_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, status: int, data: Any) -> None:
        payload = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(payload)

    def _send_text(self, status: int, content: str, content_type: str = "text/plain; charset=utf-8") -> None:
        payload = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path.rstrip("/")

        # 1. Dashboard Root
        if path == "" or path == "/index.html":
            self._send_text(HTTPStatus.OK, DASHBOARD_HTML, "text/html; charset=utf-8")
            return

        # 2. Health Check
        if path == "/api/health":
            self._send_json(HTTPStatus.OK, {
                "status": "ok",
                "version": "0.1.0",
                "mode": self.server_state.default_mode,
                "total_briefs": len(self.server_state.list_briefs()),
            })
            return

        # 3. List Briefs
        if path == "/api/briefs":
            self._send_json(HTTPStatus.OK, self.server_state.list_briefs())
            return

        # 4. Get Brief JSON by ID: /api/briefs/{brief_id}
        brief_match = re.match(r"^/api/briefs/([a-zA-Z0-9_\-]+)$", path)
        if brief_match:
            b_id = brief_match.group(1)
            brief = self.server_state.get_brief(b_id)
            if brief:
                self._send_json(HTTPStatus.OK, brief.to_dict())
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Brief '{b_id}' not found"})
            return

        # 5. Get Job Status: /api/jobs/{job_id}
        job_match = re.match(r"^/api/jobs/([a-zA-Z0-9_\-]+)$", path)
        if job_match:
            j_id = job_match.group(1)
            job = self.server_state.get_job(j_id)
            if job:
                self._send_json(HTTPStatus.OK, job.to_dict())
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Job '{j_id}' not found"})
            return

        # 6. Rendered Brief HTML: /brief/{brief_id}
        html_match = re.match(r"^/brief/([a-zA-Z0-9_\-]+)$", path)
        if html_match:
            b_id = html_match.group(1)
            brief = self.server_state.get_brief(b_id)
            if brief:
                self._send_text(HTTPStatus.OK, brief.to_html(), "text/html; charset=utf-8")
            else:
                self._send_text(HTTPStatus.NOT_FOUND, f"<h1>404 Not Found</h1><p>Brief '{b_id}' was not found.</p>", "text/html; charset=utf-8")
            return

        # 7. Rendered Brief Markdown: /brief/{brief_id}/markdown
        md_match = re.match(r"^/brief/([a-zA-Z0-9_\-]+)/markdown$", path)
        if md_match:
            b_id = md_match.group(1)
            brief = self.server_state.get_brief(b_id)
            if brief:
                self._send_text(HTTPStatus.OK, brief.to_markdown(), "text/markdown; charset=utf-8")
            else:
                self._send_text(HTTPStatus.NOT_FOUND, f"# 404 Not Found\n\nBrief '{b_id}' was not found.", "text/markdown; charset=utf-8")
            return

        # Not Found Fallback
        self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Endpoint '{self.path}' not found"})

    def do_POST(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path.rstrip("/")

        if path == "/api/synthesize":
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length <= 0:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Missing JSON request body"})
                return

            try:
                body_bytes = self.rfile.read(content_length)
                payload = json.loads(body_bytes.decode("utf-8"))
            except Exception as e:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": f"Invalid JSON payload: {e}"})
                return

            topic = payload.get("topic", "").strip()
            if not topic:
                self._send_json(HTTPStatus.BAD_REQUEST, {"error": "Field 'topic' is required"})
                return

            mode = payload.get("mode", self.server_state.default_mode)
            is_async = payload.get("async", True)

            job = self.server_state.create_job(topic=topic, mode=mode)

            def _worker():
                t0 = time.perf_counter()
                job.status = "running"
                job.progress_stage = 1
                job.progress_message = "Starting research pipeline..."

                def _progress_cb(stage: int, total: int, msg: str):
                    job.progress_stage = stage
                    job.total_stages = total
                    job.progress_message = msg

                try:
                    pipeline = ResearchPipeline(mode=job.mode)
                    brief = pipeline.run(topic=job.topic, progress_callback=_progress_cb)
                    job.elapsed_sec = time.perf_counter() - t0
                    self.server_state.register_completed_brief(job, brief)
                except Exception as exc:
                    job.status = "failed"
                    job.error = str(exc)
                    job.elapsed_sec = time.perf_counter() - t0
                    job.completed_at = datetime.now(timezone.utc).isoformat()

            if is_async:
                thread = threading.Thread(target=_worker, daemon=True)
                thread.start()
                self._send_json(HTTPStatus.ACCEPTED, job.to_dict())
            else:
                _worker()
                if job.status == "completed":
                    self._send_json(HTTPStatus.OK, {
                        "job": job.to_dict(),
                        "brief": job.brief.to_dict() if job.brief else None,
                    })
                else:
                    self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {
                        "job": job.to_dict(),
                        "error": job.error,
                    })
            return

        self._send_json(HTTPStatus.NOT_FOUND, {"error": f"Endpoint '{self.path}' not found"})

    def log_message(self, format: str, *args: Any) -> None:
        # Standardize logging without unhandled exceptions
        pass


# ============================================================================
# Server Runner Helper
# ============================================================================

def run_server(
    host: str = "127.0.0.1",
    port: int = 8080,
    output_dir: Optional[Path] = None,
    default_mode: str = "mock",
    open_browser: bool = False,
) -> ThreadingHTTPServer:
    """Instantiate and start the ThreadingHTTPServer on specified host/port."""
    out_dir = Path(output_dir or Path.cwd() / "reports")
    state = ServerState(output_dir=out_dir, default_mode=default_mode)

    class CustomHandler(ResearchServerHandler):
        server_state = state

    server = ThreadingHTTPServer((host, port), CustomHandler)
    url = f"http://{host}:{port}"
    print("=" * 80)
    print(" [*] AUTONOMOUS WEB RESEARCH & KNOWLEDGE SYNTHESIS - LOCAL DASHBOARD")
    print("=" * 80)
    print(f" Server URL:   {url}")
    print(f" Default Mode: {default_mode.upper()}")
    print(f" Reports Dir:  {out_dir.resolve()}")
    print(f" Active Jobs:  http://{host}:{port}/api/jobs")
    print(f" Briefs API:   http://{host}:{port}/api/briefs")
    print("-" * 80)
    print(" Press Ctrl+C to terminate server.")
    print("=" * 80)

    if open_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    return server


def main() -> None:
    """CLI Entry point for research-server."""
    parser = argparse.ArgumentParser(
        description="Autonomous Web Research & Knowledge Synthesis - Local Web Dashboard & REST Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-H", "--host", default="127.0.0.1", help="Host interface to bind (default: 127.0.0.1)")
    parser.add_argument("-p", "--port", type=int, default=8080, help="Port to bind (default: 8080)")
    parser.add_argument("-m", "--mode", choices=["mock", "live"], default="mock", help="Default retrieval mode (default: mock)")
    parser.add_argument("-o", "--output-dir", default="./reports", help="Directory to save/load research briefs (default: ./reports)")
    parser.add_argument("--open-browser", action="store_true", help="Automatically launch web browser on startup")

    args = parser.parse_args()

    server = run_server(
        host=args.host,
        port=args.port,
        output_dir=Path(args.output_dir),
        default_mode=args.mode,
        open_browser=args.open_browser,
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[*] Shutting down research synthesis server...")
        server.shutdown()
        server.server_close()
        print("[*] Server shutdown complete.")


if __name__ == "__main__":
    main()
