"""Streamlit UI — Chat / Triage / Metrics tabs over the FastAPI backend."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from uniassist.ui import client
from uniassist.ui.client import API_BASE, APIError

st.set_page_config(page_title="UniAssist", layout="wide")

_CHIP_CSS = """
<style>
.chip { display:inline-block; padding:2px 8px; border-radius:10px;
        font-size:0.75rem; font-weight:600; margin-left:6px; color:#fff; }
.chip-web { background:#1f77b4; }
.chip-sn  { background:#ff7f0e; }
.chip-man { background:#6c757d; }
/* Chat avatar colors: user (question) green, assistant (AI) blue */
[data-testid="stChatMessageAvatarUser"],
[data-testid="chatAvatarIcon-user"] {
    background-color: #2e7d32 !important;
    color: #fff !important;
}
[data-testid="stChatMessageAvatarAssistant"],
[data-testid="chatAvatarIcon-assistant"] {
    background-color: #1565c0 !important;
    color: #fff !important;
}
[data-testid="stChatMessageAvatarUser"] svg,
[data-testid="chatAvatarIcon-user"] svg,
[data-testid="stChatMessageAvatarAssistant"] svg,
[data-testid="chatAvatarIcon-assistant"] svg {
    fill: #fff !important;
    color: #fff !important;
}
/* Chat input: default grey; turn fully white (border + button) only on focus.
   Streamlit's red on focus comes from the theme primary color; override the
   CSS variable inside the chat-input container so only this widget changes. */
[data-testid="stChatInput"] {
    --primary-color: #ffffff !important;
    --primary-color-rgb: 255, 255, 255 !important;
}
[data-testid="stChatInput"]:focus-within {
    border-color: #fff !important;
    outline-color: #fff !important;
    caret-color: #fff !important;
}
[data-testid="stChatInput"]:focus-within > div {
    border-color: #fff !important;
}
[data-testid="stChatInput"] [data-baseweb="textarea"]:focus-within,
[data-testid="stChatInput"] [data-baseweb="base-input"]:focus-within {
    border-color: #fff !important;
    outline-color: #fff !important;
}
[data-testid="stChatInput"]:focus-within textarea {
    border-color: #fff !important;
    outline-color: #fff !important;
    box-shadow: none !important;
}
[data-testid="stChatInput"]:focus-within [data-testid="stChatInputSubmitButton"],
[data-testid="stChatInput"]:focus-within button {
    background-color: #fff !important;
    color: #000 !important;
    border-color: #fff !important;
}
[data-testid="stChatInput"]:focus-within [data-testid="stChatInputSubmitButton"] svg,
[data-testid="stChatInput"]:focus-within button svg {
    fill: #000 !important;
    color: #000 !important;
}
/* Tighten the empty space above the page title without hiding the
   Streamlit header (which contains the sidebar toggle and menu). */
[data-testid="stAppViewContainer"] .main .block-container,
[data-testid="stMainBlockContainer"] {
    padding-top: 1.5rem !important;
}
header[data-testid="stHeader"] {
    background: transparent !important;
}
/* Pin the chat input to the bottom, centered within the main content area
   (i.e. the viewport minus the sidebar). Streamlit only auto-docks
   `st.chat_input` at the top level; here it lives inside `st.tabs`, so we
   position it manually so it behaves like ChatGPT (always at the bottom). */
[data-testid="stChatInput"] {
    position: fixed !important;
    bottom: 1rem !important;
    left: 0 !important;
    right: 0 !important;
    margin: 0 auto !important;
    width: min(720px, calc(100% - 4rem)) !important;
    max-width: 720px !important;
    z-index: 100 !important;
    background: var(--background-color, #0e1117) !important;
}
/* When the sidebar is open, shift the input right by the sidebar width so
   it stays centered within the visible main content area. When the
   sidebar is collapsed Streamlit sets aria-expanded="false", so the rule
   no longer matches and the input recenters across the full viewport. */
body:has([data-testid="stSidebar"][aria-expanded="true"])
    [data-testid="stChatInput"] {
    left: 21rem !important;
}
[data-testid="stMainBlockContainer"] {
    padding-bottom: 8rem !important;
}
/* Match chat message bubbles to the chat input width */
[data-testid="stChatMessage"] {
    max-width: 720px !important;
    margin-left: auto !important;
    margin-right: auto !important;
}
/* ChatGPT-style alignment: assistant on the left, user on the right.
   Keep the message row inside the centered 720px column; flip the avatar
   to the right and push the bubble against it. */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {
    flex-direction: row-reverse !important;
    justify-content: flex-start !important;
    background: transparent !important;
}
/* The content wrapper that Streamlit gives a default background — clear it. */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
    > div:not([data-testid="stChatMessageAvatarUser"]) {
    background: transparent !important;
    flex: 0 1 auto !important;
    width: auto !important;
    max-width: 80% !important;
    min-width: 0 !important;
    margin-right: 0 !important;
    margin-left: auto !important;
    text-align: right !important;
}
/* Only the actual text container (markdown bubble) gets the grey background. */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"])
    [data-testid="stMarkdownContainer"] {
    background: rgba(255,255,255,0.08);
    border-radius: 14px;
    padding: 8px 12px;
    display: inline-block;
    max-width: 100%;
    margin-left: auto !important;
    margin-right: 0 !important;
    text-align: left !important;
}
/* Ensure every block-level wrapper between the message row and the bubble
   aligns its content to the right so the bubble hugs the avatar. */
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) div {
    text-align: right !important;
}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarAssistant"]) {
    background: transparent !important;
}
/* App font: scope to text elements only, never to icon spans/SVGs.
   Streamlit's icon arrows/chevrons rely on the Material Symbols icon font
   loaded on specific elements — overriding `*` breaks them. */
html, body,
[data-testid="stAppViewContainer"] h1,
[data-testid="stAppViewContainer"] h2,
[data-testid="stAppViewContainer"] h3,
[data-testid="stAppViewContainer"] h4,
[data-testid="stAppViewContainer"] h5,
[data-testid="stAppViewContainer"] h6,
[data-testid="stAppViewContainer"] p,
[data-testid="stAppViewContainer"] li,
[data-testid="stAppViewContainer"] a,
[data-testid="stAppViewContainer"] label,
[data-testid="stAppViewContainer"] button,
[data-testid="stAppViewContainer"] input,
[data-testid="stAppViewContainer"] textarea,
[data-testid="stAppViewContainer"] div[data-testid="stMarkdownContainer"],
[data-testid="stAppViewContainer"] div[data-testid="stCaptionContainer"],
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3,
[data-testid="stSidebar"] h4,
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] li,
[data-testid="stSidebar"] a,
[data-testid="stSidebar"] button,
[data-testid="stSidebar"] div[data-testid="stMarkdownContainer"] {
    font-family: Calibri, 'Segoe UI', Tahoma, Arial,
        "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol",
        "Noto Color Emoji", sans-serif !important;
}
[data-testid="stAppViewContainer"] h1 {
    font-weight: 700 !important;
    letter-spacing: -0.01em !important;
}
.app-subtitle {
    font-size: 1.15rem !important;
    line-height: 1.45 !important;
    color: #c9ccd1;
    margin: 0.25rem 0 1rem 0 !important;
}
/* Larger tab labels */
[data-testid="stTabs"] button[role="tab"] p {
    font-size: 1.15rem !important;
    font-weight: 600 !important;
}
/* Sidebar layout: column-flex so the footer (Clear button) sticks to the bottom */
[data-testid="stSidebar"] [data-testid="stSidebarContent"],
[data-testid="stSidebar"] > div:first-child > div:first-child {
    display: flex !important;
    flex-direction: column !important;
    height: 100% !important;
}
[data-testid="stSidebar"] .sidebar-spacer { flex: 1 1 auto !important; }
[data-testid="stSidebar"] .sidebar-section {
    padding: 0.25rem 0 0.5rem 0;
}
[data-testid="stSidebar"] .sidebar-section h4 {
    font-size: 0.78rem !important;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: #9aa0a6;
    margin: 0 0 0.35rem 0 !important;
    font-weight: 600 !important;
}
[data-testid="stSidebar"] .sidebar-section p,
[data-testid="stSidebar"] .sidebar-section li {
    font-size: 0.88rem;
    line-height: 1.35;
    margin: 0.15rem 0;
}
[data-testid="stSidebar"] .status-dot {
    display:inline-block; width:8px; height:8px; border-radius:50%;
    margin-right:6px; vertical-align: middle;
}
[data-testid="stSidebar"] .status-ok  { background:#2e7d32; }
[data-testid="stSidebar"] .status-bad { background:#c62828; }
[data-testid="stSidebar"] .kv { display:flex; justify-content:space-between; gap:8px;
    font-size:0.85rem; padding:2px 0; border-bottom:1px solid rgba(255,255,255,0.06); }
[data-testid="stSidebar"] .kv:last-child { border-bottom:none; }
[data-testid="stSidebar"] .kv .k { color:#9aa0a6; }
[data-testid="stSidebar"] .kv .v { color:#e8eaed; text-align:right;
    overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:60%; }
[data-testid="stSidebar"] .kv .v code {
    background:transparent !important; padding:0 !important; font-size:0.82rem; }
</style>
"""
st.markdown(_CHIP_CSS, unsafe_allow_html=True)


def _chip(source_type: str) -> str:
    label = {"web": "Web", "servicenow_kb": "ServiceNow KB", "manual": "Manual"}.get(
        source_type, source_type or "?"
    )
    cls = {"web": "chip-web", "servicenow_kb": "chip-sn", "manual": "chip-man"}.get(
        source_type, "chip-man"
    )
    return f'<span class="chip {cls}">{label}</span>'


# ---------- Header + sidebar ----------
st.title("UniAssist")
st.markdown(
    "<p class='app-subtitle'>AI assistant for University of Sydney IT "
    "support — ask about UniKey, WiFi, VPN, email, Canvas, printing, "
    "software, and account access, or triage a ticket.</p>",
    unsafe_allow_html=True,
)

from uniassist import __version__ as _APP_VERSION  # noqa: E402

_health: dict[str, Any] = {}
try:
    _health = client.healthz()
    api_up = True
except Exception as exc:  # noqa: BLE001
    api_up = False
    _health_error = str(exc)
else:
    _health_error = ""

with st.sidebar:
    st.markdown("### UniAssist")
    st.caption(f"v{_APP_VERSION}")

    # ----- Status -----
    st.markdown("<div class='sidebar-section'><h4>Status</h4>", unsafe_allow_html=True)
    if api_up:
        ok = _health.get("ollama_available", False)
        dot = "status-ok" if ok else "status-bad"
        label = "Online" if ok else "Degraded"
        st.markdown(
            f"<div class='kv'><span class='k'><span class='status-dot {dot}'></span>API</span>"
            f"<span class='v'>{label}</span></div>"
            f"<div class='kv'><span class='k'>Endpoint</span>"
            f"<span class='v'><a href='{API_BASE}' target='_blank'>{API_BASE}</a></span></div>"
            f"<div class='kv'><span class='k'>Chat model</span>"
            f"<span class='v'><code>{_health.get('model_chat','?')}</code></span></div>"
            f"<div class='kv'><span class='k'>Indexed docs</span>"
            f"<span class='v'>{_health.get('chroma_docs', 0):,}</span></div>",
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f"<div class='kv'><span class='k'><span class='status-dot status-bad'></span>API</span>"
            f"<span class='v'>Unreachable</span></div>"
            f"<div class='kv'><span class='k'>Endpoint</span>"
            f"<span class='v'>{API_BASE}</span></div>",
            unsafe_allow_html=True,
        )
        st.caption(f"Start it with `run.ps1 api`. ({_health_error})")
    st.markdown("</div>", unsafe_allow_html=True)

    # ----- About -----
    st.markdown(
        "<div class='sidebar-section'><h4>About</h4>"
        "<p>Retrieval-augmented answers grounded in University of "
        "Sydney IT knowledge base articles, ServiceNow KBs, and "
        "internal manuals.</p></div>",
        unsafe_allow_html=True,
    )

    # ----- Tips -----
    st.markdown(
        "<div class='sidebar-section'><h4>Tips</h4>"
        "<ul style='padding-left:1.1rem;margin:0.2rem 0;'>"
        "<li>Be specific (device, OS, error text).</li>"
        "<li>Use <b>Triage</b> to classify a ticket.</li>"
        "<li>Cited sources appear below each answer.</li>"
        "</ul></div>",
        unsafe_allow_html=True,
    )

    # ----- Spacer pushes the footer to the bottom -----
    st.markdown("<div class='sidebar-spacer'></div>", unsafe_allow_html=True)

    # ----- Footer: clear conversation -----
    if st.button("Clear conversation", width="stretch"):
        st.session_state.messages = []
        st.rerun()
    st.caption("© University of Sydney · Internal preview")


tab_chat, tab_triage, tab_metrics = st.tabs(["Chat", "Triage", "Metrics"])


# ============================================================ Chat
with tab_chat:
    if "messages" not in st.session_state:
        st.session_state.messages = []

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg["role"] == "assistant":
                latency = msg.get("latency_ms")
                if latency is not None:
                    st.caption(f"⏱ {latency} ms")
                cites = msg.get("citations") or []
                if cites:
                    with st.expander(f"Sources ({len(cites)})"):
                        for c in cites:
                            url = c.get("source_url") or "#"
                            title = c.get("title") or c.get("file") or "source"
                            chip = _chip(c.get("source_type", ""))
                            st.markdown(
                                f"[{c['n']}] [{title}]({url}) {chip}",
                                unsafe_allow_html=True,
                            )

    prompt = st.chat_input(
        "Ask about IT, accounts, WiFi…", disabled=not api_up
    )

    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})

        # Render the just-submitted question immediately, before the LLM call.
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            text_slot = st.empty()
            meta_slot = st.container()
            full_text = ""
            citations: list[dict] = []
            latency_ms: int | None = None
            error_msg: str | None = None
            try:
                for evt in client.chat_stream(prompt):
                    etype = evt.get("type")
                    if etype == "token":
                        full_text += evt.get("text", "")
                        text_slot.markdown(full_text + "▌")
                    elif etype == "citations":
                        citations = evt.get("citations", []) or citations
                    elif etype == "final":
                        full_text = evt.get("answer", full_text)
                        citations = evt.get("citations", citations) or citations
                        latency_ms = evt.get("latency_ms")
                    elif etype == "error":
                        error_msg = evt.get("message", "stream error")
                        break
            except APIError as exc:
                error_msg = str(exc)

            if error_msg:
                text_slot.error(f"API error: {error_msg}")
                full_text = f"API error: {error_msg}"
            else:
                text_slot.markdown(full_text)
                with meta_slot:
                    if latency_ms is not None:
                        st.caption(f"⏱ {latency_ms} ms")
                    if citations:
                        with st.expander(f"Sources ({len(citations)})"):
                            for c in citations:
                                url = c.get("source_url") or "#"
                                title = c.get("title") or c.get("file") or "source"
                                chip = _chip(c.get("source_type", ""))
                                st.markdown(
                                    f"[{c['n']}] [{title}]({url}) {chip}",
                                    unsafe_allow_html=True,
                                )

        st.session_state.messages.append({
            "role": "assistant",
            "content": full_text,
            "citations": citations,
            "latency_ms": latency_ms,
        })


# ============================================================ Triage
with tab_triage:
    st.subheader("Ticket triage")
    text = st.text_area(
        "Ticket text",
        height=180,
        placeholder="e.g. My VPN keeps dropping every 10 minutes…",
        disabled=not api_up,
    )
    submit = st.button("Triage", type="primary", disabled=not api_up)
    if submit and text.strip():
        try:
            with st.spinner("Classifying…"):
                resp = client.triage(text)
            result = resp["result"]
            left, right = st.columns(2)
            with left:
                st.metric("Category", result.get("category", "?"))
                st.metric("Priority", result.get("priority", "?"))
                st.metric("Queue", result.get("suggested_queue", "?"))
            with right:
                conf = float(result.get("confidence") or 0.0)
                st.markdown(f"**Confidence: {conf:.0%}**")
                st.progress(min(max(conf, 0.0), 1.0))
                st.markdown("**Rationale**")
                st.markdown(result.get("rationale", "_n/a_"))
                st.caption(
                    f"⏱ {resp.get('latency_ms', 0)} ms · "
                    f"retries: {resp.get('retries', 0)}"
                )
            with st.expander("Raw response"):
                st.json(resp)
        except APIError as exc:
            st.error(f"API error: {exc}")


# ============================================================ Metrics
with tab_metrics:
    header_l, header_r = st.columns([4, 1])
    with header_l:
        st.subheader("Usage metrics")
    with header_r:
        if st.button("Refresh", disabled=not api_up):
            st.rerun()

    if not api_up:
        st.info("Start the API to see metrics.")
    else:
        try:
            summary = client.metrics()
            recent_rows = client.recent(limit=20)
        except APIError as exc:
            st.error(f"API error: {exc}")
            summary, recent_rows = None, []

        if summary:
            counts = summary.get("counts", {}) or {}
            latency = summary.get("latency_ms", {}) or {}

            c1, c2, c3 = st.columns(3)
            c1.metric("Chat calls", counts.get("chat", 0))
            c2.metric("Triage calls", counts.get("triage", 0))
            p50_values = [
                v.get("p50") for v in latency.values()
                if isinstance(v, dict) and v.get("p50") is not None
            ]
            overall_p50 = int(sum(p50_values) / len(p50_values)) if p50_values else 0
            c3.metric("Avg P50 latency (ms)", overall_p50)

            if latency:
                lat_df = pd.DataFrame({
                    ep: {"p50": v.get("p50") or 0, "p95": v.get("p95") or 0}
                    for ep, v in latency.items()
                }).T
                st.markdown("**Latency by endpoint (ms)**")
                st.bar_chart(lat_df)

            top = summary.get("top_categories") or []
            if top:
                cat_df = pd.DataFrame(top, columns=["category", "count"]).set_index(
                    "category"
                )
                st.markdown("**Top triage categories**")
                st.bar_chart(cat_df)

        if recent_rows:
            st.markdown("**Recent queries**")
            df = pd.DataFrame(recent_rows)
            if "input_redacted" in df.columns:
                df["input_redacted"] = df["input_redacted"].astype(str).str.slice(0, 80)
            cols = [c for c in ["ts", "endpoint", "input_redacted", "latency_ms"]
                    if c in df.columns]
            st.dataframe(df[cols], width="stretch", hide_index=True)
            st.caption(
                f"Showing {len(df)} most recent · loaded {datetime.now():%H:%M:%S}"
            )
        else:
            st.caption("No queries logged yet.")
