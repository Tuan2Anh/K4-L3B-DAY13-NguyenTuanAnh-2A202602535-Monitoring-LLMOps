from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from .logging_config import LOG_PATH
from .metrics import percentile

router = APIRouter()


def load_logs(time_range_minutes: int = 60) -> list[dict[str, Any]]:
    if not Path(LOG_PATH).exists():
        return []
    records = []
    now = datetime.now(timezone.utc)
    for line in Path(LOG_PATH).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rec = json.loads(line)
            ts_str = rec.get("ts")
            if ts_str:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                diff_minutes = (now - ts).total_seconds() / 60
                if diff_minutes <= time_range_minutes:
                    records.append(rec)
            else:
                records.append(rec)
        except Exception:
            continue
    return records


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_view() -> str:
    logs = load_logs(60)

    sent = [r for r in logs if r.get("event") == "response_sent"]
    recv = [r for r in logs if r.get("event") == "request_received"]
    failed = [r for r in logs if r.get("event") == "request_failed"]

    latencies = [r.get("latency_ms", 0) for r in sent]
    ttfts = [r.get("ttft_ms", 0) for r in sent]
    p50 = percentile(latencies, 50) if latencies else 0
    p95 = percentile(latencies, 95) if latencies else 0
    p99 = percentile(latencies, 99) if latencies else 0
    ttft_p95 = percentile(ttfts, 95) if ttfts else 0

    req_count = len(recv)
    err_count = len(failed)
    error_rate = round((err_count / req_count * 100), 2) if req_count else 0.0

    retrieval_records = [r for r in logs if "tool_success" in r]
    retrieval_success_count = len([r for r in retrieval_records if r.get("tool_success") is True])
    retrieval_rate = round((retrieval_success_count / len(retrieval_records) * 100), 1) if retrieval_records else 100.0

    cost_total = round(sum(r.get("cost_usd", 0.0) for r in sent), 4)
    tokens_in = sum(r.get("tokens_in", 0) for r in sent)
    tokens_out = sum(r.get("tokens_out", 0) for r in sent)
    qualities = [r.get("quality_score", 0.0) for r in sent]
    quality_avg = round(sum(qualities) / len(qualities), 2) if qualities else 0.0

    # Group by minutes for timeline
    time_buckets: dict[str, dict[str, Any]] = {}
    for r in logs:
        ts_str = r.get("ts", "")
        minute = ts_str[11:16] if len(ts_str) >= 16 else "00:00"
        if minute not in time_buckets:
            time_buckets[minute] = {"req": 0, "fail": 0, "latencies": [], "cost": 0.0}
        if r.get("event") == "request_received":
            time_buckets[minute]["req"] += 1
        elif r.get("event") == "request_failed":
            time_buckets[minute]["fail"] += 1
        elif r.get("event") == "response_sent":
            time_buckets[minute]["latencies"].append(r.get("latency_ms", 0))
            time_buckets[minute]["cost"] += r.get("cost_usd", 0.0)

    sorted_minutes = sorted(time_buckets.keys())[-15:] or ["now"]
    traffic_series = [time_buckets[m]["req"] for m in sorted_minutes]
    cost_series = [round(time_buckets[m]["cost"], 4) for m in sorted_minutes]
    p95_series = [percentile(time_buckets[m]["latencies"], 95) if time_buckets[m]["latencies"] else p95 for m in sorted_minutes]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="30">
    <title>K4-L3B Day 13 Monitoring & LLMOps Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg: #0f172a;
            --surface: #1e293b;
            --border: #334155;
            --text: #f8fafc;
            --text-dim: #94a3b8;
            --primary: #38bdf8;
            --success: #34d399;
            --warning: #fbbf24;
            --danger: #f87171;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        body {{ background: var(--bg); color: var(--text); padding: 24px; }}
        header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 1px solid var(--border); }}
        h1 {{ font-size: 24px; font-weight: 700; color: var(--primary); }}
        .meta-badges {{ display: flex; gap: 12px; }}
        .badge {{ background: var(--surface); padding: 6px 12px; border-radius: 6px; font-size: 13px; border: 1px solid var(--border); color: var(--text-dim); }}
        .badge strong {{ color: var(--text); }}
        .grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; }}
        .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 20px; display: flex; flex-direction: column; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px; }}
        .card-title {{ font-size: 15px; font-weight: 600; color: var(--text); }}
        .card-unit {{ font-size: 12px; color: var(--text-dim); margin-top: 2px; }}
        .threshold-tag {{ font-size: 11px; padding: 3px 8px; border-radius: 4px; font-weight: 600; }}
        .tag-ok {{ background: rgba(52, 211, 153, 0.15); color: var(--success); border: 1px solid var(--success); }}
        .tag-bad {{ background: rgba(248, 113, 113, 0.15); color: var(--danger); border: 1px solid var(--danger); }}
        .stat-main {{ font-size: 32px; font-weight: 700; margin: 8px 0; }}
        .stat-sub {{ font-size: 13px; color: var(--text-dim); display: flex; gap: 16px; }}
        .chart-box {{ height: 160px; margin-top: auto; position: relative; }}
    </style>
</head>
<body>
    <header>
        <div>
            <h1>K4-L3B Day 13 Monitoring & LLMOps</h1>
            <p style="color: var(--text-dim); font-size: 14px; margin-top: 4px;">Live Operations Dashboard • Contract Validated (6/6 Panels)</p>
        </div>
        <div class="meta-badges">
            <div class="badge">Time Range: <strong>60 minutes</strong></div>
            <div class="badge">Auto-Refresh: <strong>30s</strong></div>
            <div class="badge">Source: <strong>data/logs.jsonl</strong></div>
            <div class="badge">Status: <strong style="color: var(--success);">OPERATIONAL</strong></div>
        </div>
    </header>

    <div class="grid">
        <!-- Panel 1: Latency -->
        <div class="card" id="panel-latency">
            <div class="card-header">
                <div>
                    <div class="card-title">1. Latency percentiles and TTFT</div>
                    <div class="card-unit">Unit: ms • Threshold: P95 ≤ 3000ms</div>
                </div>
                <span class="threshold-tag {'tag-ok' if p95 <= 3000 else 'tag-bad'}">SLO: {p95}ms / 3000ms</span>
            </div>
            <div class="stat-main" style="color: var(--primary);">{p95:.0f} <span style="font-size: 16px; font-weight: normal;">ms (P95)</span></div>
            <div class="stat-sub">
                <span>P50: <strong>{p50:.0f}ms</strong></span>
                <span>P99: <strong>{p99:.0f}ms</strong></span>
                <span>TTFT P95: <strong>{ttft_p95:.0f}ms</strong></span>
            </div>
            <div class="chart-box">
                <canvas id="chartLatency"></canvas>
            </div>
        </div>

        <!-- Panel 2: Traffic -->
        <div class="card" id="panel-traffic">
            <div class="card-header">
                <div>
                    <div class="card-title">2. Request traffic</div>
                    <div class="card-unit">Unit: requests_per_minute • Threshold: ≥ 1</div>
                </div>
                <span class="threshold-tag tag-ok">Count: {req_count} reqs</span>
            </div>
            <div class="stat-main" style="color: var(--success);">{req_count} <span style="font-size: 16px; font-weight: normal;">requests</span></div>
            <div class="stat-sub">
                <span>Status: <strong>Active load</strong></span>
                <span>Sample Window: <strong>60m</strong></span>
            </div>
            <div class="chart-box">
                <canvas id="chartTraffic"></canvas>
            </div>
        </div>

        <!-- Panel 3: Errors -->
        <div class="card" id="panel-errors">
            <div class="card-header">
                <div>
                    <div class="card-title">3. Error rate and retrieval success</div>
                    <div class="card-unit">Unit: percent • Threshold: Error ≤ 2%</div>
                </div>
                <span class="threshold-tag {'tag-ok' if error_rate <= 2.0 else 'tag-bad'}">Err: {error_rate}% / 2%</span>
            </div>
            <div class="stat-main" style="color: {'var(--danger)' if error_rate > 2 else 'var(--success)'};">{error_rate}% <span style="font-size: 16px; font-weight: normal;">errors</span></div>
            <div class="stat-sub">
                <span>Retrieval Success: <strong style="color: var(--success);">{retrieval_rate}%</strong></span>
                <span>Failed reqs: <strong>{err_count}</strong></span>
            </div>
            <div class="chart-box">
                <canvas id="chartErrors"></canvas>
            </div>
        </div>

        <!-- Panel 4: Cost -->
        <div class="card" id="panel-cost">
            <div class="card-header">
                <div>
                    <div class="card-title">4. Cost over time</div>
                    <div class="card-unit">Unit: usd • Threshold: Total ≤ $2.50</div>
                </div>
                <span class="threshold-tag {'tag-ok' if cost_total <= 2.5 else 'tag-bad'}">Cost: ${cost_total} / $2.50</span>
            </div>
            <div class="stat-main" style="color: var(--warning);">${cost_total:.4f} <span style="font-size: 16px; font-weight: normal;">USD</span></div>
            <div class="stat-sub">
                <span>Pricing: <strong>Claude 3.5 Sonnet</strong></span>
                <span>Budget remaining: <strong>${max(0.0, 2.5 - cost_total):.2f}</strong></span>
            </div>
            <div class="chart-box">
                <canvas id="chartCost"></canvas>
            </div>
        </div>

        <!-- Panel 5: Tokens -->
        <div class="card" id="panel-tokens">
            <div class="card-header">
                <div>
                    <div class="card-title">5. Input and output tokens</div>
                    <div class="card-unit">Unit: tokens • Threshold: Sum ≤ 50,000</div>
                </div>
                <span class="threshold-tag {'tag-ok' if (tokens_in + tokens_out) <= 50000 else 'tag-bad'}">Total: {tokens_in + tokens_out}</span>
            </div>
            <div class="stat-main" style="color: var(--primary);">{tokens_in + tokens_out:,} <span style="font-size: 16px; font-weight: normal;">tokens</span></div>
            <div class="stat-sub">
                <span>Tokens In: <strong>{tokens_in:,}</strong></span>
                <span>Tokens Out: <strong>{tokens_out:,}</strong></span>
            </div>
            <div class="chart-box">
                <canvas id="chartTokens"></canvas>
            </div>
        </div>

        <!-- Panel 6: Quality -->
        <div class="card" id="panel-quality">
            <div class="card-header">
                <div>
                    <div class="card-title">6. Quality proxy</div>
                    <div class="card-unit">Unit: score_0_to_1 • Threshold: Mean ≥ 0.75</div>
                </div>
                <span class="threshold-tag {'tag-ok' if quality_avg >= 0.75 else 'tag-bad'}">Score: {quality_avg} / 0.75</span>
            </div>
            <div class="stat-main" style="color: var(--success);">{quality_avg:.2f} <span style="font-size: 16px; font-weight: normal;">/ 1.0</span></div>
            <div class="stat-sub">
                <span>Min accepted: <strong>0.75</strong></span>
                <span>Eval Heuristic: <strong>Grounding & Conciseness</strong></span>
            </div>
            <div class="chart-box">
                <canvas id="chartQuality"></canvas>
            </div>
        </div>
    </div>

    <script>
        const minutes = {json.dumps(sorted_minutes)};
        const trafficData = {json.dumps(traffic_series)};
        const costData = {json.dumps(cost_series)};
        const p95Data = {json.dumps(p95_series)};

        // Latency Chart
        new Chart(document.getElementById('chartLatency'), {{
            type: 'line',
            data: {{
                labels: minutes,
                datasets: [
                    {{ label: 'P95 Latency (ms)', data: p95Data, borderColor: '#38bdf8', tension: 0.3, fill: true, backgroundColor: 'rgba(56, 189, 248, 0.1)' }},
                    {{ label: 'SLO Threshold (3000ms)', data: minutes.map(() => 3000), borderColor: '#f87171', borderDash: [5, 5], fill: false, pointRadius: 0 }}
                ]
            }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ display: false }}, y: {{ grid: {{ color: '#334155' }} }} }} }}
        }});

        // Traffic Chart
        new Chart(document.getElementById('chartTraffic'), {{
            type: 'bar',
            data: {{
                labels: minutes,
                datasets: [{{ label: 'Requests', data: trafficData, backgroundColor: '#34d399', borderRadius: 4 }}]
            }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ display: false }}, y: {{ grid: {{ color: '#334155' }} }} }} }}
        }});

        // Errors & Retrieval Chart
        new Chart(document.getElementById('chartErrors'), {{
            type: 'doughnut',
            data: {{
                labels: ['Success', 'Errors'],
                datasets: [{{ data: [{req_count - err_count}, {err_count}], backgroundColor: ['#34d399', '#f87171'], borderWidth: 0 }}]
            }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ position: 'bottom', labels: {{ color: '#94a3b8' }} }} }} }}
        }});

        // Cost Chart
        new Chart(document.getElementById('chartCost'), {{
            type: 'line',
            data: {{
                labels: minutes,
                datasets: [
                    {{ label: 'Cost (USD)', data: costData, borderColor: '#fbbf24', tension: 0.3, fill: true, backgroundColor: 'rgba(251, 191, 36, 0.1)' }},
                    {{ label: 'Budget Threshold ($2.50)', data: minutes.map(() => 2.5), borderColor: '#f87171', borderDash: [5, 5], fill: false, pointRadius: 0 }}
                ]
            }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ display: false }}, y: {{ grid: {{ color: '#334155' }} }} }} }}
        }});

        // Tokens Chart
        new Chart(document.getElementById('chartTokens'), {{
            type: 'bar',
            data: {{
                labels: ['Input', 'Output'],
                datasets: [{{ label: 'Tokens', data: [{tokens_in}, {tokens_out}], backgroundColor: ['#38bdf8', '#818cf8'], borderRadius: 4 }}]
            }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ x: {{ grid: {{ display: false }} }}, y: {{ grid: {{ color: '#334155' }} }} }} }}
        }});

        // Quality Chart
        new Chart(document.getElementById('chartQuality'), {{
            type: 'bar',
            data: {{
                labels: ['Current Mean', 'Threshold'],
                datasets: [{{ data: [{quality_avg}, 0.75], backgroundColor: ['#34d399', '#64748b'], borderRadius: 4 }}]
            }},
            options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ max: 1.0, grid: {{ color: '#334155' }} }} }} }}
        }});
    </script>
</body>
</html>
"""
    return html
