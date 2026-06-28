"""
app.py
------
Streamlit dashboard for ScopePilot.

Run with:
    streamlit run app.py

Layout:
  Top bar  : project picker · Run button · Cerebras/GPU timer cards
  Left     : waveform panel (the image the vision agent reads)
  Right    : live agent activity stream
  Bottom   : patch diff  |  simulator console output
"""

import time
import asyncio
import shutil
import pathlib
import streamlit as st

# ---------------------------------------------------------------------------
# Page config — must be the first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="FignalAI",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# Minimal custom CSS — keep it small; Streamlit handles the rest
# ---------------------------------------------------------------------------
st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=IBM+Plex+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500;600;700&display=swap');

  /* ---- base ---- */
  .stApp { background: #0A0A0C; }
  html, body, [class*="css"], .stMarkdown, p, span, div, label, input, button {
    font-family: 'IBM Plex Sans', sans-serif;
    font-variant-ligatures: none;
    font-feature-settings: "liga" 0, "calt" 0;
  }
  header[data-testid="stHeader"] { background: transparent; }
  .block-container { padding-top: 2.4rem; padding-bottom: 2rem; }
  hr { border-color: rgba(255,255,255,.07); }

  /* ---- tiny mono panel labels ---- */
  .panel-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10.5px; font-weight: 600; letter-spacing: .14em;
    text-transform: uppercase; color: #6C7077; margin: 0;
  }
  .panel-hdr { display:flex; align-items:center; justify-content:space-between; margin-bottom:10px; }

  /* ---- top stat cards ---- */
  .statbar { display:flex; gap:8px; justify-content:flex-end; flex-wrap:wrap; }
  .stat-card {
    background:#141417; border:1px solid rgba(255,255,255,.07);
    border-radius:8px; padding:9px 13px; min-width:94px;
  }
  .sc-label { display:block; font-family:'JetBrains Mono',monospace; font-size:10px;
    font-weight:600; letter-spacing:.12em; text-transform:uppercase; color:#6C7077; margin-bottom:4px; }
  .sc-val { font-family:'Space Grotesk',sans-serif; font-weight:600; font-size:22px;
    letter-spacing:-.02em; line-height:1.05; }
  .sc-val .u { font-size:12px; color:#6C7077; font-family:'JetBrains Mono',monospace; }
  .sc-delta { display:block; font-family:'JetBrains Mono',monospace; font-size:10.5px; color:#5CE09E; margin-top:3px; }
  .sc-note { display:block; font-family:'JetBrains Mono',monospace; font-size:10px; color:#6C7077; margin-top:3px; }
  .c-green{color:#5CE09E}.c-red{color:#E0695C}.c-cyan{color:#5CCAE0}.c-cyc{color:#A6A9AE}

  /* ---- bordered containers = panels ---- */
  div[data-testid="stVerticalBlockBorderWrapper"] {
    background:#141417; border-radius:12px;
    border:1px solid rgba(255,255,255,.07) !important;
  }

  /* ---- buttons ---- */
  .stButton > button {
    font-family:'Space Grotesk',sans-serif; font-weight:600;
    border-radius:8px; border:1px solid rgba(255,255,255,.18);
  }
  .stButton > button[kind="primary"] { background:#E0B45C; color:#1A1303; }
  .stButton > button[kind="primary"]:hover {
    background:#E6BE6E; color:#1A1303; border-color:rgba(255,255,255,.28);
    box-shadow:0 0 0 4px rgba(224,180,92,.16);
  }

  /* ---- selectbox ---- */
  div[data-baseweb="select"] > div {
    background:#0C0C0E; border-color:rgba(255,255,255,.1) !important;
    font-family:'JetBrains Mono',monospace; border-radius:999px;
  }

  /* ---- code blocks (diff / console) ---- */
  [data-testid="stCode"] { background:#0C0C0E !important;
    border:1px solid rgba(255,255,255,.07); border-radius:8px; }
  code, pre, [data-testid="stCode"] * { font-family:'JetBrains Mono', monospace !important; }

  /* ---- agent rows ---- */
  .agent-row {
    background:#0C0C0E; border:1px solid rgba(255,255,255,.07);
    border-radius:8px; padding:9px 12px; margin-bottom:7px;
    font-family:'JetBrains Mono',monospace; font-size:12.5px; color:#F2F3F5;
  }
  .agent-row b { color:#F2F3F5; font-weight:600; }
  .agent-row code {
    background:rgba(255,255,255,.05); border:1px solid rgba(255,255,255,.08);
    border-radius:5px; padding:1px 6px; color:#A6A9AE; font-size:11.5px;
  }
  .culled { opacity:.5; }

  /* ---- in-progress timeline row (the spinning "next step") ---- */
  .agent-row.inprog { display:flex; align-items:center; gap:10px;
    border-color:rgba(224,180,92,.35); background:rgba(224,180,92,.06); color:#E0B45C; }
  .agent-row.inprog b { color:#E0B45C; font-weight:500; }
  .spin { width:13px; height:13px; flex:0 0 auto; border-radius:50%;
    border:2px solid rgba(224,180,92,.25); border-top-color:#E0B45C;
    animation: fa-spin .7s linear infinite; }
  @keyframes fa-spin { to { transform: rotate(360deg); } }
  /* subtle pulse for stat values still computing */
  .sc-val.pending { animation: fa-pulse 1.1s ease-in-out infinite; }
  @keyframes fa-pulse { 50% { opacity:.35; } }

  /* ---- result badges ---- */
  .badge-fail { color:#E0695C; background:rgba(224,105,92,.12); border:1px solid rgba(224,105,92,.34);
    padding:4px 11px; border-radius:999px; font-family:'JetBrains Mono',monospace;
    font-size:11px; font-weight:700; letter-spacing:.06em; }
  .badge-pass { color:#5CE09E; background:rgba(92,224,158,.12); border:1px solid rgba(92,224,158,.32);
    padding:4px 11px; border-radius:999px; font-family:'JetBrains Mono',monospace;
    font-size:11px; font-weight:700; letter-spacing:.06em; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Import project modules (after config)
# ---------------------------------------------------------------------------
from orchestrator import debug, Event

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
if "events"     not in st.session_state: st.session_state.events    = []
if "running"    not in st.session_state: st.session_state.running   = False
if "cerebras_ms" not in st.session_state: st.session_state.cerebras_ms = None
if "baseline_ms" not in st.session_state: st.session_state.baseline_ms = None
if "tps"        not in st.session_state: st.session_state.tps       = None
if "total_cycle_ms" not in st.session_state: st.session_state.total_cycle_ms = None
if "png"        not in st.session_state: st.session_state.png       = None
if "sim_result" not in st.session_state: st.session_state.sim_result = None
if "diff"       not in st.session_state: st.session_state.diff      = None
if "console"    not in st.session_state: st.session_state.console   = ""

# ---------------------------------------------------------------------------
# Discover example projects
# ---------------------------------------------------------------------------
examples_dir = pathlib.Path("examples")
projects = sorted([
    p.name for p in examples_dir.iterdir()
    if p.is_dir() and (p / "design.v").exists() and (p / "tb.v").exists()
]) if examples_dir.exists() else []

SIGNALS = {
    "counter":  ["clk", "rst_n", "count"],
    "fsm":      ["clk", "rst_n", "go", "state"],
    "shiftreg": ["clk", "din", "q1", "q2", "dout"],
}

# ---------------------------------------------------------------------------
# Top bar
# ---------------------------------------------------------------------------
logo_col, proj_col, run_col, spacer, stats_col = st.columns([1.1, 1.5, 1.2, 0.1, 5.6])

with logo_col:
    if pathlib.Path("assets/fignalai logo.png").exists():
        st.image("assets/fignalai logo.png", width=150)
    else:
        st.markdown("### FignalAI")

with proj_col:
    selected = st.selectbox(
        "Project",
        projects if projects else ["— no examples found —"],
        label_visibility="collapsed",
    )

with run_col:
    run_clicked = st.button("▶ Run debug", type="primary", use_container_width=True)

def _stat(label, val_html, color_cls, delta="", pending=False):
    pend = " pending" if pending else ""
    return (f'<div class="stat-card"><span class="sc-label">{label}</span>'
            f'<span class="sc-val {color_cls}{pend}">{val_html}</span>{delta}</div>')


stats_ph = stats_col.empty()


def render_stats():
    """Four stat cards.

    The two inference cards measure the IDENTICAL scope — generation only:
      • Cerebras (gen)    : measured time to generate the run's output tokens
      • GPU baseline · est: SAME output tokens at the assumed GPU rate (derived)
    Wall-clock lives in its own 'Total cycle' card (incl. sim + render) so it can
    never be misread as a Cerebras sub-metric. The total-cycle clock ticks live
    so the header is never frozen during free-tier rate-limit waits."""
    running = st.session_state.get("running", False)
    t_cere = st.session_state.cerebras_ms     # measured generation time (ms)
    t_gpu  = st.session_state.baseline_ms     # est. GPU generation time (ms)
    t_tps  = st.session_state.tps
    sp     = (t_gpu / t_cere) if (t_cere and t_gpu) else None
    faster = f'<span class="sc-delta">{sp:.0f}× faster</span>' if sp else ''

    if running:
        # ease displayed numbers toward the latest real values (count-up)
        for key, tgt in (("disp_cere", t_cere), ("disp_gpu", t_gpu), ("disp_tps", t_tps)):
            if tgt:
                cur = st.session_state.get(key, 0.0)
                st.session_state[key] = cur + (tgt - cur) * 0.28
        dcere = st.session_state.get("disp_cere", 0.0)
        dgpu  = st.session_state.get("disp_gpu", 0.0)
        dtps  = st.session_state.get("disp_tps", 0.0)
        cyc_ms = (time.monotonic() - st.session_state.get("run_start", time.monotonic())) * 1000
        st.session_state.total_cycle_ms = cyc_ms   # persist for the post-run rerun

        cere = f'{dcere/1000:.2f}<span class="u">s</span>' if t_cere else '•••'
        gpu  = f'{dgpu/1000:.1f}<span class="u">s</span>'  if t_gpu  else '•••'
        tps  = f'{round(dtps):,}<span class="u"> t/s</span>' if t_tps else '•••'
        cyc  = f'{cyc_ms/1000:.1f}<span class="u">s</span>'
        pend = (not t_cere, not t_gpu, not t_tps, False)
    else:
        cere = f'{t_cere/1000:.2f}<span class="u">s</span>' if t_cere else '—'
        gpu  = f'{t_gpu/1000:.1f}<span class="u">s</span>'  if t_gpu  else '—'
        tps  = f'{t_tps:,}<span class="u"> t/s</span>'       if t_tps  else '—'
        tc   = st.session_state.get("total_cycle_ms")
        cyc  = f'{tc/1000:.1f}<span class="u">s</span>' if tc else '—'
        pend = (False, False, False, False)

    note = '<span class="sc-note">incl. sim + render</span>'
    stats_ph.markdown(
        '<div class="statbar">'
        + _stat("Cerebras · gen", cere, "c-green", faster, pending=pend[0])
        + _stat("GPU baseline · est", gpu, "c-red", pending=pend[1])
        + _stat("Throughput", tps, "c-cyan", pending=pend[2])
        + _stat("Total cycle", cyc, "c-cyc", note, pending=pend[3])
        + '</div>',
        unsafe_allow_html=True,
    )


render_stats()

st.divider()

# ---------------------------------------------------------------------------
# Main panels
# ---------------------------------------------------------------------------
wave_col, stream_col = st.columns([1.5, 1])

wave_placeholder   = wave_col.empty()
status_placeholder = wave_col.empty()
stream_placeholder = stream_col.empty()

diff_col, console_col = st.columns([1.3, 1])
diff_placeholder    = diff_col.empty()
console_placeholder = console_col.empty()


# ---------------------------------------------------------------------------
# Helpers — render the panels from current session state
# ---------------------------------------------------------------------------

def render_waveform_panel():
    with wave_placeholder.container(border=True):
        if st.session_state.sim_result is None:
            badge = ""
        elif st.session_state.sim_result:
            badge = '<span class="badge-pass">● RESULT: PASS</span>'
        else:
            badge = '<span class="badge-fail">● RESULT: FAIL</span>'
        st.markdown(
            f'<div class="panel-hdr"><span class="panel-label">Waveform · dump.vcd</span>{badge}</div>',
            unsafe_allow_html=True,
        )
        if st.session_state.png and pathlib.Path(st.session_state.png).exists():
            st.image(st.session_state.png, use_container_width=True)
        else:
            st.caption("Waveform will appear here after simulation runs.")


def _current_activity(events):
    """What is happening *right now* — drives the live banner above the log."""
    if not events:
        return None
    last = events[-1]
    k, d = last.kind, last.data
    if k == "done":
        return ("done", "Bug fixed & verified by the simulator"
                if d.get("fixed") else "Run finished")
    if k == "error":
        return ("error", d.get("message", "Error"))
    # in-flight steps — the last event during a blocking call is the matching
    # "running" event, so this reflects exactly what the agents are doing now
    if k == "sim":
        return ("run", f"Simulating round {d.get('round','')} …"
                if d.get("status") == "running" else "Rendering the waveform …")
    if k == "render":
        return ("run", "Vision agent reading the waveform …")
    if k == "vision":
        return ("run", "Vision agent reading the waveform …"
                if d.get("status") == "running" else "Code agents debating the root cause …")
    if k == "code":
        return ("run", "Code agents debating the root cause …"
                if d.get("status") == "running" else "Voting on the winning hypothesis …")
    if k == "vote":
        return ("run", "Writing the patch …")
    if k == "verifier":
        return ("run", "Verifier checking the hypothesis …"
                if d.get("status") == "running" else "Writing the patch …")
    if k == "patch":
        return ("run", "Patch agent writing the fix …"
                if d.get("status") == "running" else "Re-simulating to verify the fix …")
    return ("run", "Working …")


def render_stream_panel():
    with stream_placeholder.container(border=True):
        st.markdown('<div class="panel-label">Agent activity</div>', unsafe_allow_html=True)
        st.write("")

        if not st.session_state.events:
            st.caption("Press ▶ Run debug to start.")
            return

        # completed steps (each ends with a ✅ / ❌ / pill)
        for ev in st.session_state.events:
            _render_event(ev)

        # timeline tip: the step in progress right now, as an animated spinner row.
        # When it finishes its ✅ row is appended above and the next spinner shows.
        if st.session_state.get("running"):
            act = _current_activity(st.session_state.events)
            if act and act[0] == "run":
                st.markdown(
                    f'<div class="agent-row inprog"><span class="spin"></span>'
                    f'<b>{act[1]}</b></div>',
                    unsafe_allow_html=True,
                )


def _render_event(ev: Event):
    k = ev.kind
    d = ev.data

    if k == "sim":
        if d.get("status") != "done":
            return   # running state is shown by the live banner, not the log
        icon  = "✅" if d.get("passed") else "❌"
        label = f"Simulate · round {d.get('round','')} · {d.get('elapsed_ms','–')}ms"
        cls   = "" if d.get("passed") else "culled"
        st.markdown(
            f'<div class="agent-row {cls}">{icon} <b>Simulator</b> · {label}</div>',
            unsafe_allow_html=True,
        )

    elif k == "vision":
        if d.get("status") == "done":
            anomaly = d.get("anomaly", {})
            st.markdown(
                f'<div class="agent-row">👁 <b>Vision</b> · {d.get("elapsed_ms","–")}ms · '
                f'{anomaly.get("anomaly","")}</div>',
                unsafe_allow_html=True,
            )

    elif k == "code":
        if d.get("status") == "done":
            for item in d.get("details", []):
                # empty / errored model response — not a hallucination, just skip
                if item.get("status") in ("error", "parse_error"):
                    st.markdown(
                        f'<div class="agent-row culled">⚪ <b>Code C{item["idx"]}</b> · '
                        f'empty response — skipped</div>',
                        unsafe_allow_html=True,
                    )
                    continue
                kept = item.get("kept", False)
                cls  = "" if kept else "culled"
                # 🟢 survived the deterministic line-check; 🔴 hallucinated line caught
                tag  = "kept" if kept else "culled (line-check)"
                st.markdown(
                    f'<div class="agent-row {cls}">{"🟢" if kept else "🔴"} '
                    f'<b>Code C{item["idx"]}</b> · line {item.get("line_no","?")} · '
                    f'<code>{item.get("quoted_code","")[:40]}</code> · {tag}</div>',
                    unsafe_allow_html=True,
                )

    elif k == "vote":
        w = d.get("winner") or d.get("fallback", {})
        if d.get("result") == "majority":
            label = f'line {w.get("line_no","?")} wins · {d.get("count","?")} agents agree'
        else:
            label = f'no clear majority — using line {w.get("line_no","?")}'
        st.markdown(
            f'<div class="agent-row">🗳 <b>Vote</b> · {label}</div>',
            unsafe_allow_html=True,
        )

    elif k == "verifier":
        if d.get("status") == "done":
            v = d.get("verdict", {})
            icon = "✅" if v.get("verdict") == "accept" else "❌"
            st.markdown(
                f'<div class="agent-row">{icon} <b>Verifier</b> · '
                f'{v.get("verdict","?")} · {v.get("confidence","?")}% confidence · '
                f'{d.get("elapsed_ms","–")}ms</div>',
                unsafe_allow_html=True,
            )

    elif k == "patch":
        if d.get("status") == "done":
            edits = d.get("edits") or d.get("patch", {}).get("edits", [])
            shown = " · ".join(
                f'line {e.get("line_no","?")} <code>{e.get("before","")}</code>→<code>{e.get("after","")}</code>'
                for e in edits[:3]
            ) or "—"
            extra = f' (+{len(edits)-3} more)' if len(edits) > 3 else ''
            plural = "es" if len(edits) != 1 else ""
            st.markdown(
                f'<div class="agent-row">✏️ <b>Patch</b> · {len(edits)} edit{plural} · {shown}{extra}</div>',
                unsafe_allow_html=True,
            )

    elif k == "done":
        if d.get("fixed"):
            gen = d.get("cerebras_gen_ms")
            msg = "✅ Bug fixed and verified by simulator"
            if gen is not None:
                msg += f" · {gen}ms Cerebras generation"
            if d.get("total_ms"):
                msg += f"  (total cycle {d['total_ms']/1000:.1f}s, incl. sim + render"
                msg += " + free-tier rate-limit wait)"
            st.success(msg)
        else:
            st.error(f"❌ Could not fix in {d.get('round','')} rounds.")

    elif k == "error":
        st.error(f"Error: {d.get('message','unknown error')}")


def render_diff_panel():
    with diff_placeholder.container(border=True):
        st.markdown('<div class="panel-label">Patch diff</div>', unsafe_allow_html=True)
        st.write("")
        if st.session_state.diff:
            st.code(st.session_state.diff, language="diff")
        else:
            st.caption("Diff will appear here after a patch is applied.")


def render_console_panel():
    with console_placeholder.container(border=True):
        st.markdown('<div class="panel-label">Console</div>', unsafe_allow_html=True)
        st.write("")
        if st.session_state.console:
            st.code(st.session_state.console, language="bash")
        else:
            st.caption("Simulator stdout will appear here.")


# ---------------------------------------------------------------------------
# Initial render
# ---------------------------------------------------------------------------
render_waveform_panel()
render_stream_panel()
render_diff_panel()
render_console_panel()


# ---------------------------------------------------------------------------
# Run button handler
# ---------------------------------------------------------------------------
if run_clicked and selected and selected != "— no examples found —":
    # Run on a disposable working copy so the pristine buggy design.v is never
    # mutated — this makes the demo repeatable (every run starts from the bug).
    src_dir  = examples_dir / selected
    work_dir = pathlib.Path("runs") / selected
    work_dir.mkdir(parents=True, exist_ok=True)
    rtl_path = str(work_dir / "design.v")
    tb_path  = str(work_dir / "tb.v")
    shutil.copy2(src_dir / "design.v", rtl_path)
    shutil.copy2(src_dir / "tb.v",     tb_path)
    sigs     = SIGNALS.get(selected, ["clk"])

    # clear previous run state (incl. stats, so the cards flip to "•••" live)
    st.session_state.events      = []
    st.session_state.png         = None
    st.session_state.sim_result  = None
    st.session_state.diff        = None
    st.session_state.console     = ""
    st.session_state.cerebras_ms = None
    st.session_state.baseline_ms = None
    st.session_state.tps         = None
    st.session_state.total_cycle_ms = None

    async def run():
        st.session_state.running   = True
        st.session_state.run_start = time.monotonic()
        st.session_state.disp_cere = 0.0
        st.session_state.disp_gpu  = 0.0
        st.session_state.disp_tps  = 0.0
        render_stats()
        render_stream_panel()

        # Background ticker: repaints the stat cards ~5×/sec so the live ⏱ clock
        # keeps counting and the values ease up — even while the agents are blocked
        # waiting on the rate-limit window (asyncio runs this between awaits).
        async def ticker():
            try:
                while st.session_state.get("running"):
                    render_stats()
                    await asyncio.sleep(0.2)
            except (asyncio.CancelledError, Exception):
                pass

        tick = asyncio.create_task(ticker())
        try:
            async for event in debug(rtl_path, tb_path, sigs, work_dir=str(work_dir)):
                st.session_state.events.append(event)
                d = event.data

                if event.kind == "render" and d.get("png"):
                    st.session_state.png = d["png"]

                if event.kind == "sim":
                    if "passed" in d:
                        st.session_state.sim_result = d["passed"]
                    if d.get("log"):
                        st.session_state.console = d["log"]

                if event.kind == "patch" and d.get("status") == "done":
                    p = d.get("patch", {})
                    edits = d.get("edits") or p.get("edits") or []
                    if edits:
                        out = []
                        for e in edits:
                            out.append(f"- line {e.get('line_no','?')}   {e.get('before','')}")
                            out.append(f"+ line {e.get('line_no','?')}   {e.get('after','')}")
                        out.append(f"# {p.get('rationale','')}")
                        st.session_state.diff = "\n".join(out)

                # live generation-vs-generation snapshot (on each sub-step done)
                if d.get("cerebras_gen_ms") is not None:
                    st.session_state.cerebras_ms = d["cerebras_gen_ms"]
                if d.get("baseline_gen_ms") is not None:
                    st.session_state.baseline_ms = d["baseline_gen_ms"]
                if d.get("tps") is not None:
                    st.session_state.tps = d["tps"]
                # total cycle = wall-clock (incl. sim + render) from the done event
                if d.get("total_ms") is not None:
                    st.session_state.total_cycle_ms = d["total_ms"]

                # repaint everything live as each event arrives
                render_stats()
                render_waveform_panel()
                render_stream_panel()
                render_diff_panel()
                render_console_panel()
        finally:
            st.session_state.running = False
            tick.cancel()
            try:
                await tick
            except Exception:
                pass

        # final snap to exact values (no easing) + clear the spinner row
        render_stats()
        render_stream_panel()

    asyncio.run(run())

    # cerebras_ms / baseline_ms / tps are set from the done event (honest
    # inference time, not wall-clock which includes free-tier rate-limit waits)
    st.rerun()
