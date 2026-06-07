"""Streamlit investigator UI for the Identity Intelligence Platform.

Four pages:
1. Live Decision Feed — streaming view of recent decisions
2. Case Detail — drill into a case with evidence and graph view
3. Graph Explorer — interactive Neo4j-backed mule ring visualization
4. Audit Log — append-only log with FS-AI RMF traceability

Run with:
    streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Identity Intelligence Platform",
    page_icon="shield",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---- Page config ----

PAGES = ["Live Decision Feed", "Case Detail", "Graph Explorer", "Audit Log"]


def _api_base() -> str:
    return os.getenv("API_BASE_URL", "http://localhost:8000")


@st.cache_data(ttl=5)
def _api_get(path: str) -> Any:
    """Fetch from the FastAPI backend, with a graceful fallback for offline mode."""
    import urllib.error
    import urllib.request

    try:
        url = f"{_api_base()}{path}"
        with urllib.request.urlopen(url, timeout=2) as resp:
            return json.loads(resp.read().decode())
    except Exception:
        return None


def _live_decision_feed() -> None:
    st.title("Live Decision Feed")
    st.caption("Streaming view of recent AI-fraud decisions. Updates every 5s.")

    refresh = st.sidebar.button("Refresh now")
    auto = st.sidebar.checkbox("Auto-refresh", value=True)
    if auto or refresh:
        data = _api_get("/api/decisions?limit=100")
        if data is None:
            st.warning(
                f"Could not reach API at {_api_base()}. Showing sample decisions for UI demo."
            )
            data = _sample_decisions()
        _render_decision_table(data)

        stats = _api_get("/api/stats?window_minutes=60")
        if stats:
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Events / 60m", stats.get("event_count", 0))
            c2.metric("Decisions / 60m", stats.get("decision_count", 0))
            c3.metric("Cases / 60m", stats.get("case_count", 0))
            c4.metric("Block rate", f"{stats.get('block_rate', 0) * 100:.1f}%")


def _render_decision_table(decisions: list[dict]) -> None:
    if not decisions:
        st.info("No decisions yet.")
        return
    df = pd.DataFrame(decisions)
    df = df[
        [
            "decision_id",
            "event_id",
            "action",
            "final_score",
            "xgb_score",
            "rule_score",
            "created_at",
        ]
    ]
    df = df.rename(
        columns={
            "decision_id": "Decision",
            "event_id": "Event",
            "action": "Action",
            "final_score": "Score",
            "xgb_score": "XGBoost",
            "rule_score": "Rules",
            "created_at": "When",
        }
    )

    def _color_action(v: str) -> str:
        if v == "BLOCK":
            return "background-color: #f8d7da; color: #721c24"
        if v == "REVIEW":
            return "background-color: #fff3cd; color: #856404"
        return "background-color: #d4edda; color: #155724"

    st.dataframe(
        df.style.map(_color_action, subset=["Action"]),
        use_container_width=True,
        height=500,
    )


def _case_detail() -> None:
    st.title("Case Detail")
    case_id = st.text_input("Case ID", placeholder="e.g. CASE-2024-000123")
    if not case_id:
        st.info("Enter a case ID to view details.")
        return
    data = _api_get(f"/api/cases/{case_id}")
    if data is None:
        st.warning("Case not found or API offline.")
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Status", data.get("status", "unknown"))
    c2.metric("Final Score", f"{data.get('final_score', 0):.2f}")
    c3.metric("Opened", data.get("opened_at", ""))
    st.subheader("Triggering Rules")
    for rule in data.get("triggered_rules", []):
        st.write(f"- **{rule['code']}** — {rule['description']}")
    st.subheader("Raw Decision")
    st.json(data.get("decision", {}))


def _graph_explorer() -> None:
    st.title("Graph Explorer")
    st.caption("Mule rings, shared devices, and shared IPs from Neo4j.")
    rings = _api_get("/api/graph/mule-rings?min_size=3")
    if rings is None:
        rings = _sample_mule_rings()
    st.subheader(f"Detected Mule Rings ({len(rings)})")
    for r in rings:
        with st.expander(
            f"Ring #{r['community_id']} — {r['size']} members, density {r['density']:.2f}"
        ):
            st.json(r.get("members", []))


def _audit_log() -> None:
    st.title("Audit Log")
    st.caption("Append-only log mapped to U.S. Treasury FS-AI RMF traceability requirements.")
    entries = _api_get("/api/audit?limit=200")
    if entries is None:
        entries = _sample_audit()
    if not entries:
        st.info("No audit entries yet.")
        return
    df = pd.DataFrame(entries)
    st.dataframe(df, use_container_width=True, height=600)


# ---- Sample data (for offline / no-API demo) ----


def _sample_decisions() -> list[dict]:
    now = datetime.utcnow()
    return [
        {
            "decision_id": f"D-{i:08d}",
            "event_id": f"E-{i:08d}",
            "action": "BLOCK" if i % 7 == 0 else ("REVIEW" if i % 3 == 0 else "ALLOW"),
            "final_score": 0.4 + (i * 0.07) % 0.6,
            "xgb_score": 0.3 + (i * 0.05) % 0.7,
            "rule_score": 0.2 + (i * 0.09) % 0.8,
            "created_at": (now - timedelta(minutes=i)).isoformat(),
        }
        for i in range(40)
    ]


def _sample_mule_rings() -> list[dict]:
    return [
        {
            "community_id": "C-001",
            "size": 7,
            "density": 0.62,
            "members": [f"account-{i:04d}" for i in range(101, 108)],
        },
        {
            "community_id": "C-002",
            "size": 4,
            "density": 0.83,
            "members": [f"account-{i:04d}" for i in range(201, 205)],
        },
    ]


def _sample_audit() -> list[dict]:
    now = datetime.utcnow()
    return [
        {
            "audit_id": f"A-{i:08d}",
            "decision_id": f"D-{i:08d}",
            "event_id": f"E-{i:08d}",
            "actor": "system@identity-intel",
            "action_taken": "ALLOW" if i % 5 else "BLOCK",
            "final_score": 0.4 + (i * 0.07) % 0.6,
            "model_version_id": "identity_intel_xgb:1",
            "policy_version_id": "policy_v1.0",
            "rule_codes_hit": "R001,R005" if i % 3 == 0 else "",
            "fs_ai_rmf_principle": "Explainability",
            "fs_ai_rmf_evidence": "feature_snapshot.parquet",
            "created_at": (now - timedelta(seconds=i * 30)).isoformat(),
        }
        for i in range(50)
    ]


# ---- Main ----


def main() -> None:
    page = st.sidebar.radio("Navigate", PAGES)
    if page == "Live Decision Feed":
        _live_decision_feed()
    elif page == "Case Detail":
        _case_detail()
    elif page == "Graph Explorer":
        _graph_explorer()
    elif page == "Audit Log":
        _audit_log()


if __name__ == "__main__":
    main()
