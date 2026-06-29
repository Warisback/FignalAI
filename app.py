"""
app.py
------
Streamlit dashboard for FignalAI.

Run with:
    streamlit run app.py

Layout (plain, EDA-tool / Vivado-inspired, light theme):
  Top toolbar : logo · project picker · Run button · plain stat strip
  Left column : waveform (Before/After tabs)  +  Diff/Console tabs below
  Right column: live agent activity stream
  Bottom      : thin IDE status bar
"""

import time
import html
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
# Custom CSS — plain neutral "EDA tool" theme, native system fonts
# ---------------------------------------------------------------------------
st.markdown("""
<style>
  :root{
    --bg:#e9ebee; --panel:#ffffff; --hdr:#eceef1; --hdr2:#e2e5e9;
    --bd:#cdd2d9; --bd2:#bcc2cb;
    --text:#1f242b; --muted:#5b626d; --dim:#8a919c;
    --accent:#3f6ea3; --fail:#a23b39; --pass:#2f7344;
    --mono:Consolas,'Cascadia Mono','SFMono-Regular',ui-monospace,'Segoe UI Mono',monospace;
    --ui:'Segoe UI',system-ui,-apple-system,Roboto,'Helvetica Neue',Arial,sans-serif;
  }

  /* ---- base ---- */
  .stApp { background: var(--bg); }
  html, body, [class*="css"], .stMarkdown, p, span, div, label, input, button {
    font-family: var(--ui);
    font-variant-ligatures: none;
    font-feature-settings: "liga" 0, "calt" 0;
    color: var(--text);
  }
  header[data-testid="stHeader"] { background: transparent; height:0; }
  .block-container { padding-top: 1.2rem; padding-bottom: 2.6rem; max-width: 100%; }
  hr { border-color: var(--bd); margin: .5rem 0; }
  #MainMenu, footer { visibility: hidden; }

  /* ---- brand ---- */
  .brand { font-weight:600; font-size:20px; letter-spacing:-.01em; margin:0; padding-top:4px; }
  .brand b { color: var(--accent); }

  /* ---- tiny mono panel labels / headers ---- */
  .panel-label {
    font-family: var(--mono); font-size: 10.5px; font-weight: 600; letter-spacing: .13em;
    text-transform: uppercase; color: var(--muted); margin: 0;
  }
  .panel-hdr { display:flex; align-items:center; justify-content:space-between; margin-bottom:8px; }

  /* ---- plain stat strip (no colour) ---- */
  .stats { display:flex; justify-content:flex-end; border:1px solid var(--bd);
    border-radius:5px; overflow:hidden; background:var(--panel); width:fit-content; margin-left:auto; }
  .stat { padding:4px 16px; border-right:1px solid var(--bd); min-width:88px; }
  .stat:last-child { border-right:0; }
  .stat .k { font-family:var(--mono); font-size:9px; letter-spacing:.09em;
    text-transform:uppercase; color:var(--dim); }
  .stat .v { font-family:var(--mono); font-size:17px; font-weight:600; color:var(--text); line-height:1.2; }
  .stat .v small { font-size:11px; color:var(--muted); font-weight:500; }
  .stat .sub { font-family:var(--mono); font-size:9px; color:var(--muted); min-height:11px; }
  .stat .v.pending { animation: fa-pulse 1.1s ease-in-out infinite; }
  @keyframes fa-pulse { 50% { opacity:.4; } }

  /* ---- bordered containers = panels ---- */
  div[data-testid="stVerticalBlockBorderWrapper"] {
    background: var(--panel); border-radius:6px;
    border:1px solid var(--bd) !important;
  }

  /* ---- buttons ---- */
  .stButton > button {
    font-family: var(--ui); font-weight:600; font-size:13px;
    border-radius:5px; border:1px solid var(--bd); background:var(--panel); color:var(--text);
    padding:6px 14px;
  }
  .stButton > button[kind="primary"] { background:var(--accent); color:#fff; border-color:#355d8a; }
  .stButton > button[kind="primary"]:hover { background:#37618f; color:#fff; border-color:#2d527a; }

  /* ---- selectbox ---- */
  div[data-baseweb="select"] > div {
    background: var(--panel); border-color: var(--bd) !important;
    font-family: var(--mono); border-radius:5px;
  }

  /* ---- tabs (Vivado-style) ---- */
  [data-baseweb="tab-list"] { gap:0; border-bottom:1px solid var(--bd); background:var(--hdr); }
  button[data-baseweb="tab"] {
    font-family:var(--mono); font-size:11.5px; color:var(--muted);
    padding:5px 14px; border-right:1px solid var(--bd); height:auto;
  }
  button[data-baseweb="tab"][aria-selected="true"] { color:var(--text); background:var(--panel); }
  [data-baseweb="tab-highlight"] { background-color: var(--accent); height:2px; }
  [data-baseweb="tab-border"] { display:none; }
  [data-baseweb="tab-panel"] { padding-top:10px; }

  /* ---- images (waveform scope) ---- */
  [data-testid="stImage"] img { border:1px solid var(--bd); border-radius:4px; background:#fff; }

  /* ---- result status text (muted, no badges) ---- */
  .result { font-family:var(--mono); font-size:11px; font-weight:700; letter-spacing:.04em; }
  .result.fail { color:var(--fail); }
  .result.pass { color:var(--pass); }

  /* ---- diff ---- */
  .diff { font-family:var(--mono); font-size:12px; line-height:1.7; }
  .diff .dl { white-space:pre; padding:0 8px; }
  .diff .ctx { color:var(--muted); }
  .diff .del { background:#fbeceb; color:#7d2b29; }
  .diff .add { background:#e9f3ec; color:#235e34; }

  /* ---- console ---- */
  .con { font-family:var(--mono); font-size:12px; line-height:1.6; }
  .con .cl { white-space:pre-wrap; }
  .con .pr { color:var(--dim); } .con .er { color:var(--fail); } .con .ok { color:var(--pass); }

  /* ---- agent activity ---- */
  .log { max-height:64vh; overflow-y:auto; }
  .agent-row {
    display:flex; align-items:baseline; gap:9px; padding:7px 8px;
    border-bottom:1px solid #eef0f2; font-family:var(--mono); font-size:12px;
  }
  .agent-row .g { width:13px; flex:0 0 auto; text-align:center; color:var(--dim); }
  .agent-row .g.f { color:var(--fail); } .agent-row .g.k { color:var(--pass); } .agent-row .g.run { color:var(--accent); }
  .agent-row .nm { font-weight:600; color:var(--text); }
  .agent-row .dt { color:var(--muted); flex:1; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .agent-row .tm { color:var(--dim); font-size:11px; }
  .agent-row .tag { font-size:10px; color:var(--muted); border:1px solid var(--bd); border-radius:3px; padding:0 6px; }
  .agent-row code { background:#f1f3f5; border:1px solid var(--bd); border-radius:3px;
    padding:0 5px; color:var(--muted); font-size:11px; }
  .agent-row.culled { opacity:.5; }
  .agent-row.inprog { background:#f3f7fb; }
  .agent-row.inprog .nm { color:var(--accent); font-weight:500; }
  .spin { display:inline-block; width:10px; height:10px; flex:0 0 auto;
    border:1.7px solid #c7d4e2; border-top-color:var(--accent); border-radius:50%;
    animation: fa-spin .7s linear infinite; }
  @keyframes fa-spin { to { transform: rotate(360deg); } }
  .done-ok { margin:8px 0 0; padding:9px 11px; border:1px solid #bcd6c4; background:#eef5f0;
    border-radius:4px; font-family:var(--mono); font-size:12px; color:#235e34; }
  .done-err { margin:8px 0 0; padding:9px 11px; border:1px solid #e0c2c1; background:#fbeceb;
    border-radius:4px; font-family:var(--mono); font-size:12px; color:#7d2b29; }

  /* ---- status bar ---- */
  .statusbar { position:fixed; left:0; right:0; bottom:0; height:24px; z-index:1000;
    display:flex; align-items:center; gap:16px; padding:0 14px;
    background:var(--hdr); border-top:1px solid var(--bd2);
    font-family:var(--mono); font-size:10.5px; color:var(--muted); }
  .statusbar .dot { width:7px; height:7px; border-radius:50%; background:var(--pass);
    display:inline-block; margin-right:5px; }
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
if "baseline_measured" not in st.session_state: st.session_state.baseline_measured = False
if "png"        not in st.session_state: st.session_state.png       = None
if "before_png" not in st.session_state: st.session_state.before_png = None
if "fixed_png"  not in st.session_state: st.session_state.fixed_png  = None
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
    "alu":      ["op", "a", "b", "y"],   # combinational — no clock
}

# ---------------------------------------------------------------------------
# Top toolbar
# ---------------------------------------------------------------------------
logo_col, proj_col, run_col, spacer, stats_col = st.columns([1.0, 1.5, 1.1, 0.1, 5.8])

with logo_col:
    st.markdown('<p class="brand">Fignal<b>AI</b></p>', unsafe_allow_html=True)

with proj_col:
    selected = st.selectbox(
        "Project",
        projects if projects else ["— no examples found —"],
        label_visibility="collapsed",
    )

with run_col:
    run_clicked = st.button("▶ Run debug", type="primary", use_container_width=True)

# Wipe ALL previous-run state up front — BEFORE anything renders this script run —
# whenever a new run starts OR the project is switched, so the old agent log,
# waveforms, diff, console and timers never linger. The new run then fills the
# cleared panels stage by stage.
_switched = st.session_state.get("last_selected") != selected
st.session_state.last_selected = selected
_new_run  = bool(run_clicked and selected and selected != "— no examples found —")
if _new_run or _switched:
    st.session_state.events            = []
    st.session_state.png               = None
    st.session_state.before_png        = None
    st.session_state.fixed_png         = None
    st.session_state.sim_result        = None
    st.session_state.diff              = None
    st.session_state.console           = ""
    st.session_state.cerebras_ms       = None
    st.session_state.baseline_ms       = None
    st.session_state.tps               = None
    st.session_state.total_cycle_ms    = None
    st.session_state.baseline_measured = False
if _new_run:
    st.session_state.running = True


def _stat(label, val_html, sub="", pending=False):
    pend = " pending" if pending else ""
    sub_html = f'<div class="sub">{sub}</div>' if sub else '<div class="sub">&nbsp;</div>'
    return (f'<div class="stat"><div class="k">{label}</div>'
            f'<div class="v{pend}">{val_html}</div>{sub_html}</div>')


stats_ph = stats_col.empty()


def render_stats():
    """Four plain stat cells (no colour).

    The two inference cells measure the IDENTICAL scope — generation only:
      • Cerebras gen      : measured time to generate the run's output tokens
      • GPU measured/est  : SAME output tokens at the GPU rate (measured or derived)
    Wall-clock lives in its own 'Total cycle' cell (incl. sim + render) so it can
    never be misread as a Cerebras sub-metric. The total-cycle clock ticks live
    so the header is never frozen during free-tier rate-limit waits."""
    running = st.session_state.get("running", False)
    t_cere = st.session_state.cerebras_ms     # measured generation time (ms)
    t_gpu  = st.session_state.baseline_ms     # GPU generation time (ms)
    t_tps  = st.session_state.tps
    sp     = (t_gpu / t_cere) if (t_cere and t_gpu) else None
    faster = f'{sp:.0f}× faster' if sp else ''
    measured = st.session_state.get("baseline_measured")
    gpu_label = "GPU measured" if measured else "GPU est"
    gpu_sub   = "same model" if measured else "estimated"

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

        cere = f'{dcere/1000:.2f}<small>s</small>' if t_cere else '•••'
        gpu  = f'{dgpu/1000:.1f}<small>s</small>'  if t_gpu  else '•••'
        tps  = f'{round(dtps):,}<small> t/s</small>' if t_tps else '•••'
        cyc  = f'{cyc_ms/1000:.1f}<small>s</small>'
        pend = (not t_cere, not t_gpu, not t_tps, False)
    else:
        cere = f'{t_cere/1000:.2f}<small>s</small>' if t_cere else '—'
        gpu  = f'{t_gpu/1000:.1f}<small>s</small>'  if t_gpu  else '—'
        tps  = f'{t_tps:,}<small> t/s</small>'       if t_tps  else '—'
        tc   = st.session_state.get("total_cycle_ms")
        cyc  = f'{tc/1000:.1f}<small>s</small>' if tc else '—'
        pend = (False, False, False, False)

    stats_ph.markdown(
        '<div class="stats">'
        + _stat("Cerebras gen", cere, faster, pending=pend[0])
        + _stat(gpu_label, gpu, gpu_sub, pending=pend[1])
        + _stat("Throughput", tps, "", pending=pend[2])
        + _stat("Total cycle", cyc, "incl. sim+render", pending=pend[3])
        + '</div>',
        unsafe_allow_html=True,
    )


render_stats()

st.divider()

# ---------------------------------------------------------------------------
# Main split: left column (waveform + output)  |  right column (agent activity)
# ---------------------------------------------------------------------------
left_col, right_col = st.columns([1.55, 1], gap="small")

with left_col:
    wave_placeholder = st.empty()
    out_placeholder  = st.empty()
with right_col:
    stream_placeholder = st.empty()


# ---------------------------------------------------------------------------
# Helpers — render the panels from current session state
# ---------------------------------------------------------------------------

def _panel_hdr(title, right=""):
    st.markdown(
        f'<div class="panel-hdr"><span class="panel-label">{title}</span>{right}</div>',
        unsafe_allow_html=True,
    )


def render_waveform_panel():
    proj = st.session_state.get("last_selected", "")
    with wave_placeholder.container(border=True):
        before = st.session_state.before_png
        fixed  = st.session_state.fixed_png

        # once fixed, show before/after as two tabs (proof of the fix)
        if fixed and pathlib.Path(fixed).exists():
            _panel_hdr(f"dump.vcd · {proj}", '<span class="result pass">● RESULT: PASS</span>')
            t_before, t_after = st.tabs(["Waveform · before", "Waveform · after"])
            with t_before:
                st.markdown('<span class="result fail">RESULT: FAIL · before patch</span>',
                            unsafe_allow_html=True)
                if before and pathlib.Path(before).exists():
                    st.image(before, use_container_width=True)
            with t_after:
                st.markdown('<span class="result pass">RESULT: PASS · after patch</span>',
                            unsafe_allow_html=True)
                st.image(fixed, use_container_width=True)
            return

        # live single view (during the run)
        if st.session_state.sim_result is None:
            badge = ""
        elif st.session_state.sim_result:
            badge = '<span class="result pass">● RESULT: PASS</span>'
        else:
            badge = '<span class="result fail">● RESULT: FAIL</span>'
        _panel_hdr(f"dump.vcd · {proj}", badge)
        if st.session_state.png and pathlib.Path(st.session_state.png).exists():
            st.image(st.session_state.png, use_container_width=True)
        else:
            st.caption("Waveform will appear here after simulation runs.")


def _diff_html(text: str) -> str:
    rows = []
    for ln in text.split("\n"):
        e = html.escape(ln)
        cls = "del" if ln.startswith("-") else "add" if ln.startswith("+") else "ctx"
        rows.append(f'<div class="dl {cls}">{e or "&nbsp;"}</div>')
    return '<div class="diff">' + "".join(rows) + "</div>"


def _console_html(text: str) -> str:
    rows = []
    for ln in text.split("\n"):
        e = html.escape(ln)
        low = ln.lower()
        if "error" in low or "fail" in low:
            cls = "er"
        elif "pass" in low or "ok" in low:
            cls = "ok"
        elif ln.lstrip().startswith(("$", ">", "›")):
            cls = "pr"
        else:
            cls = ""
        rows.append(f'<div class="cl {cls}">{e or "&nbsp;"}</div>')
    return '<div class="con">' + "".join(rows) + "</div>"


def render_output_panel():
    """Diff + Console collapsed into tabs (fills the lower-left area)."""
    with out_placeholder.container(border=True):
        t_diff, t_console = st.tabs(["Diff", "Console"])
        with t_diff:
            if st.session_state.diff:
                st.markdown(_diff_html(st.session_state.diff), unsafe_allow_html=True)
            else:
                st.caption("Diff will appear here after a patch is applied.")
        with t_console:
            if st.session_state.console:
                st.markdown(_console_html(st.session_state.console), unsafe_allow_html=True)
            else:
                st.caption("Simulator stdout will appear here.")


def _current_activity(events):
    """What is happening *right now* — drives the live spinner row."""
    if not events:
        return None
    last = events[-1]
    k, d = last.kind, last.data
    if k in ("done", "error"):
        return None
    if k == "sim":
        return ("Simulating round %s …" % d.get("round", "")
                if d.get("status") == "running" else "Rendering the waveform …")
    if k == "render":
        return "Vision agent reading the waveform …"
    if k == "vision":
        return ("Vision agent reading the waveform …"
                if d.get("status") == "running" else "Code agents debating the root cause …")
    if k == "code":
        return ("Code agents debating the root cause …"
                if d.get("status") == "running" else "Voting on the winning hypothesis …")
    if k == "vote":
        return "Writing the patch …"
    if k == "verifier":
        return ("Verifier checking the hypothesis …"
                if d.get("status") == "running" else "Writing the patch …")
    if k == "patch":
        return ("Patch agent writing the fix …"
                if d.get("status") == "running" else "Re-simulating to verify the fix …")
    return "Working …"


def render_stream_panel():
    with stream_placeholder.container(border=True):
        _panel_hdr("Agent activity")
        if not st.session_state.events:
            st.caption("Starting…" if st.session_state.get("running")
                       else "Press ▶ Run debug to start.")
            return

        rows = "".join(_event_html(ev) for ev in st.session_state.events)

        # live spinner row for the step in progress right now
        if st.session_state.get("running"):
            act = _current_activity(st.session_state.events)
            if act:
                rows += (f'<div class="agent-row inprog"><span class="spin"></span>'
                         f'<span class="nm">{html.escape(act)}</span></div>')

        st.markdown(f'<div class="log">{rows}</div>', unsafe_allow_html=True)


def _row(glyph, gcls, name, detail="", tail="", tag="", row_cls=""):
    g   = f'<span class="g {gcls}">{glyph}</span>'
    nm  = f'<span class="nm">{name}</span>'
    dt  = f'<span class="dt">{detail}</span>' if detail else '<span class="dt"></span>'
    tm  = f'<span class="tm">{tail}</span>' if tail else ""
    tg  = f'<span class="tag">{tag}</span>' if tag else ""
    return f'<div class="agent-row {row_cls}">{g}{nm}{dt}{tm}{tg}</div>'


def _event_html(ev: Event) -> str:
    k, d = ev.kind, ev.data

    if k == "sim":
        if d.get("status") != "done":
            return ""   # running state is shown by the live spinner, not the log
        passed = d.get("passed")
        return _row("✓" if passed else "✗", "k" if passed else "f", "Simulator",
                    f'simulate · round {d.get("round","")}',
                    tail=f'{d.get("elapsed_ms","–")}ms',
                    row_cls="" if passed else "culled")

    if k == "vision":
        if d.get("status") == "done":
            anomaly = d.get("anomaly", {})
            return _row("●", "run", "Vision", html.escape(str(anomaly.get("anomaly", ""))),
                        tail=f'{d.get("elapsed_ms","–")}ms')
        return ""

    if k == "code":
        if d.get("status") != "done":
            return ""
        out = ""
        for item in d.get("details", []):
            if item.get("status") in ("error", "parse_error"):
                out += _row("○", "", f'Code C{item["idx"]}', "empty response — skipped",
                            row_cls="culled")
                continue
            kept = item.get("kept", False)
            code = html.escape(str(item.get("quoted_code", ""))[:40])
            out += _row("●" if kept else "○", "k" if kept else "", f'Code C{item["idx"]}',
                        f'line {item.get("line_no","?")} · <code>{code}</code>',
                        tag="kept" if kept else "culled",
                        row_cls="" if kept else "culled")
        return out

    if k == "baseline":
        cached = " (cached)" if d.get("cached") else ""
        return _row("⋯", "", "GPU baseline",
                    f'measured {d.get("tps","?")} t/s · same model{cached}')

    if k == "vote":
        w = d.get("winner") or d.get("fallback", {})
        if d.get("result") == "majority":
            label = f'line {w.get("line_no","?")} · {d.get("count","?")} agents agree'
        else:
            label = f'no clear majority — using line {w.get("line_no","?")}'
        return _row("▴", "", "Vote", label)

    if k == "verifier":
        if d.get("status") == "done":
            v = d.get("verdict", {})
            accept = v.get("verdict") == "accept"
            tail_note = "" if accept else " · advisory"
            return _row("✓" if accept else "!", "k" if accept else "f", "Verifier",
                        f'{v.get("verdict","?")} · {v.get("confidence","?")}% confidence{tail_note}',
                        tail=f'{d.get("elapsed_ms","–")}ms')
        return ""

    if k == "patch":
        if d.get("status") == "done":
            edits = d.get("edits") or d.get("patch", {}).get("edits", [])
            shown = " · ".join(
                f'line {e.get("line_no","?")} <code>{html.escape(str(e.get("before","")))} → '
                f'{html.escape(str(e.get("after","")))}</code>'
                for e in edits[:2]
            ) or "—"
            extra = f' (+{len(edits)-2} more)' if len(edits) > 2 else ''
            plural = "s" if len(edits) != 1 else ""
            return _row("✎", "", "Patch", f'{len(edits)} edit{plural} · {shown}{extra}')
        return ""

    if k == "done":
        if d.get("fixed"):
            gen = d.get("cerebras_gen_ms")
            msg = "✓ Bug fixed &amp; verified by simulator"
            if gen is not None:
                msg += f" · {gen/1000:.2f}s Cerebras generation" if gen > 100 else f" · {gen}ms Cerebras generation"
            if d.get("total_ms"):
                msg += f" (total cycle {d['total_ms']/1000:.1f}s, incl. sim + render)"
            return f'<div class="done-ok">{msg}</div>'
        return f'<div class="done-err">✗ Could not fix in {d.get("round","")} rounds.</div>'

    if k == "error":
        return f'<div class="done-err">{html.escape(str(d.get("message","unknown error")))}</div>'

    return ""


# ---------------------------------------------------------------------------
# Initial render
# ---------------------------------------------------------------------------
render_waveform_panel()
render_output_panel()
render_stream_panel()

# ---------------------------------------------------------------------------
# IDE-style status bar (fixed bottom)
# ---------------------------------------------------------------------------
_state = "Running…" if st.session_state.get("running") else "Ready"
st.markdown(
    f'<div class="statusbar"><span><span class="dot"></span>{_state}</span>'
    '<span>gemma-4-31b · Cerebras</span><span>100 RPM</span>'
    '<span>multimodal: on</span><span style="margin-left:auto">FignalAI</span></div>',
    unsafe_allow_html=True,
)


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
    # (per-run state was already reset up front, before the initial render)

    async def run():
        st.session_state.running   = True
        st.session_state.run_start = time.monotonic()
        st.session_state.disp_cere = 0.0
        st.session_state.disp_gpu  = 0.0
        st.session_state.disp_tps  = 0.0
        render_stats()
        render_stream_panel()

        # Background ticker: repaints the stat cells ~5×/sec so the live clock
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
                    if st.session_state.before_png is None:   # first failing render
                        st.session_state.before_png = d["png"]

                if event.kind == "done" and d.get("fixed_png"):
                    st.session_state.fixed_png = d["fixed_png"]

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
                        if p.get("rationale"):
                            out.append(f"# {p.get('rationale','')}")
                        st.session_state.diff = "\n".join(out)

                # live generation-vs-generation snapshot (on each sub-step done)
                if d.get("cerebras_gen_ms") is not None:
                    st.session_state.cerebras_ms = d["cerebras_gen_ms"]
                if d.get("baseline_gen_ms") is not None:
                    st.session_state.baseline_ms = d["baseline_gen_ms"]
                if d.get("tps") is not None:
                    st.session_state.tps = d["tps"]
                if d.get("baseline_measured") is not None:
                    st.session_state.baseline_measured = d["baseline_measured"]
                # total cycle = wall-clock (incl. sim + render) from the done event
                if d.get("total_ms") is not None:
                    st.session_state.total_cycle_ms = d["total_ms"]

                # repaint everything live as each event arrives
                render_stats()
                render_waveform_panel()
                render_output_panel()
                render_stream_panel()
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

    try:
        asyncio.run(run())
    except Exception as e:
        # a transient API/network error (Cerebras 429/connection) must NOT dump a
        # raw traceback into the UI — show a clean, retryable message instead
        st.session_state.running = False
        st.session_state.events.append(
            Event("error", message=f"Run interrupted — {type(e).__name__}: {e}. "
                                   "Cerebras may be busy; press Run debug to retry.")
        )
        render_stream_panel()

    # cerebras_ms / baseline_ms / tps are set from the done event (honest
    # inference time, not wall-clock which includes free-tier rate-limit waits)
    st.rerun()
