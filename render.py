"""
render.py
---------
Parses a VCD (Value Change Dump) file produced by iverilog/vvp
and renders a clean, annotated PNG for the Vision agent to read.

Key design decisions:
- Renders itself (no GTKWave / display server needed)
- Prints decimal values as text on bus signals so the vision model
  can read numbers instead of counting bit transitions
- Dark background + cyan traces = high contrast for the vision model
- Downscales to ~768px wide to keep image token cost low
"""

import pathlib
import matplotlib
matplotlib.use("Agg")   # non-interactive backend — no display needed
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


# ---------------------------------------------------------------------------
# VCD parser
# ---------------------------------------------------------------------------

def parse_vcd(vcd_path: str) -> dict:
    """
    Parse a VCD file into:  signal_name -> [(time:int, value:str), ...]

    Values are raw VCD strings: "0", "1", "x", "z" for scalars, or a binary
    string like "0110" for buses.

    Handles:
      - hierarchical $scope / $upscope (a name like `count` may appear in both
        `tb` and `dut`; we keep the first/shallowest occurrence — the TB's view)
      - scalar changes   (e.g. `0#`, `1"`, `x!`)
      - vector changes   (e.g. `b0110 &`)
      - the initial `$dumpvars` block (values at t=0)
    """
    with open(vcd_path) as f:
        lines = f.readlines()

    # --- pass 1: header — build id <-> name (first occurrence of a name wins) ---
    name_to_id: dict[str, str] = {}
    header_end = len(lines)
    for idx, line in enumerate(lines):
        s = line.strip()
        if s.startswith("$var"):
            parts = s.split()           # $var <type> <size> <id> <name> [range] $end
            if len(parts) >= 5:
                vid, name = parts[3], parts[4]
                name_to_id.setdefault(name, vid)
        elif s.startswith("$enddefinitions"):
            header_end = idx
            break

    id_to_name = {vid: name for name, vid in name_to_id.items()}
    tv_map: dict[str, list] = {name: [] for name in name_to_id}

    # --- pass 2: body — value changes ---
    current_t = 0
    for line in lines[header_end + 1:]:
        s = line.strip()
        if not s or s.startswith("$"):
            continue                    # $dumpvars / $end / $comment markers
        if s[0] == "#":
            current_t = int(s[1:])
        elif s[0] in "01xXzZ":          # scalar: value char then id
            val, vid = s[0], s[1:].strip()
            name = id_to_name.get(vid)
            if name is not None:
                tv_map[name].append((current_t, val))
        elif s[0] in "bBrR":            # vector / real: b<bits> <id>
            parts = s.split()
            if len(parts) >= 2:
                name = id_to_name.get(parts[1])
                if name is not None:
                    tv_map[name].append((current_t, parts[0][1:]))

    return tv_map


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------

def render_waveform(
    vcd_path: str,
    signals: list[str],
    out_path: str = "waveform.png",
    highlight_anomaly: str | None = None,
    title: str = "",
) -> str:
    """
    Render selected signals from a VCD to a PNG.

    Parameters
    ----------
    vcd_path          : path to the .vcd file
    signals           : list of signal names to plot (in order, top to bottom)
    out_path          : output PNG path
    highlight_anomaly : signal name whose anomaly region to highlight in amber
    title             : optional title printed above the waveform

    Returns the out_path so callers can chain it.
    """
    tv_map = parse_vcd(vcd_path)

    n = len(signals)
    fig_h = max(1.8, 0.9 * n + 0.6)
    fig, axes = plt.subplots(n, 1, figsize=(7.68, fig_h), sharex=True)
    if n == 1:
        axes = [axes]

    fig.patch.set_facecolor("#0C0C0E")

    if title:
        fig.suptitle(title, color="#A6A9AE", fontsize=9,
                     fontfamily="monospace", y=0.98)

    # find max time for x-axis
    max_t = 0
    for sig in signals:
        tv = tv_map.get(sig, [])
        if tv:
            max_t = max(max_t, tv[-1][0])
    if max_t == 0:
        max_t = 200

    for ax, sig in zip(axes, signals):
        ax.set_facecolor("#0C0C0E")
        ax.tick_params(colors="#6C7077", labelsize=7)
        for spine in ax.spines.values():
            spine.set_edgecolor("#1C1C20")

        tv = tv_map.get(sig, [])
        if not tv:
            ax.set_ylabel(sig, color="#6C7077", fontsize=8,
                          fontfamily="monospace", rotation=0,
                          ha="right", va="center", labelpad=4)
            continue

        # extend last value to max_t so the trace reaches the right edge
        times  = [p[0] for p in tv] + [max_t]
        raw    = [p[1] for p in tv]

        # determine if scalar (0/1/x/z) or bus (binary string)
        is_bus = any(len(v) > 1 for v in raw)

        if is_bus:
            # draw parallelogram bus shape and print decimal value
            for k in range(len(raw)):
                t0 = times[k]
                t1 = times[k + 1]
                w  = t1 - t0
                if w <= 0:
                    continue
                try:
                    val_int = int(raw[k], 2)
                    label   = str(val_int)
                    color   = "#5CCAE0"
                    # amber highlight for the anomalous value
                    if sig == highlight_anomaly and val_int > 9:
                        color = "#E0B45C"
                except ValueError:
                    label = raw[k]
                    color = "#6C7077"

                mid = 0.5
                slant = min(w * 0.08, 4)
                xs = [t0 + slant, t1 - slant, t1, t0]
                ys = [1.0,        1.0,         0.0, 0.0]
                ax.fill(xs, ys, color=color, alpha=0.15)
                ax.plot([t0 + slant, t1 - slant], [1.0, 1.0], color=color, lw=1.4)
                ax.plot([t0 + slant, t1 - slant], [0.0, 0.0], color=color, lw=1.4)
                ax.plot([t0, t0 + slant], [0.0, 1.0], color=color, lw=1.0)
                ax.plot([t1 - slant, t1], [1.0, 0.0], color=color, lw=1.0)

                # print value label in the middle of the segment
                if w > max_t * 0.018:  # show values unless the segment is tiny
                    ax.text(
                        (t0 + t1) / 2, 0.52, label,
                        ha="center", va="center",
                        color=color if color != "#5CCAE0" else "#F2F3F5",
                        fontsize=8, fontfamily="monospace", fontweight="bold",
                    )

        else:
            # scalar signal — step plot
            vals_num = []
            for v in raw:
                if v == "1":
                    vals_num.append(1)
                elif v == "0":
                    vals_num.append(0)
                else:
                    vals_num.append(0.5)  # X/Z

            # extend the last value out to max_t so x and y match in length
            ax.step(times, vals_num + [vals_num[-1]], where="post",
                    color="#5CCAE0", linewidth=1.6)
            ax.set_ylim(-0.2, 1.3)

        ax.set_ylabel(sig, color="#A6A9AE", fontsize=8,
                      fontfamily="monospace", rotation=0,
                      ha="right", va="center", labelpad=6)
        ax.set_xlim(0, max_t)
        ax.grid(True, color="#1C1C20", linewidth=0.5, linestyle="--", alpha=0.6)
        ax.set_yticks([])

    axes[-1].tick_params(axis="x", colors="#6C7077", labelsize=7)
    axes[-1].set_xlabel("time (ns)", color="#6C7077", fontsize=7,
                        fontfamily="monospace")

    plt.tight_layout(rect=[0.08, 0, 1, 0.97])
    plt.savefig(out_path, dpi=110, bbox_inches="tight",
                facecolor="#0C0C0E", edgecolor="none")
    plt.close()
    return out_path


# ---------------------------------------------------------------------------
# Text description (fallback for when multimodal image input is unavailable)
# ---------------------------------------------------------------------------

def _fmt_value(v: str) -> str:
    """VCD raw value -> human string. Buses -> decimal; keep x/z literal."""
    if len(v) > 1:
        return str(int(v, 2)) if set(v) <= set("01") else v
    return v


def _value_at(tv: list, t: int) -> str | None:
    """Value of a signal at time t = its last transition at or before t."""
    val = None
    for tt, v in tv:
        if tt <= t:
            val = v
        else:
            break
    return val


def describe_waveform(vcd_path: str, signals: list[str]) -> str:
    """
    Build a compact, unambiguous TEXT description of the waveform.

    Used by the Vision agent when multimodal image input is not enabled for
    the org/model (Cerebras returns 403 otherwise). Because we already parse
    the VCD ourselves, the agent gets the same information the picture encodes.

    Instead of raw timestamps (which tempt the model to over-analyse clock /
    reset alignment), we sample every signal once per CLOCK CYCLE — exactly how
    an engineer reads a waveform. The per-cycle value sequence makes a data
    anomaly (e.g. a counter reaching 10) impossible to miss.

    Flip orchestrator VISION_MODE to "image" once multimodal lands.
    """
    tv_map = parse_vcd(vcd_path)

    # Identify the clock: prefer a signal literally named like a clock,
    # else the scalar signal with the most regular toggles.
    clk = None
    for s in signals:
        if "clk" in s.lower() and tv_map.get(s):
            clk = s
            break
    if clk is None:
        scalars = [
            (len(tv_map.get(s, [])), s)
            for s in signals
            if tv_map.get(s) and all(len(v) == 1 for _, v in tv_map[s])
        ]
        clk = max(scalars)[1] if scalars else None

    # Rising edges of the clock define the cycle boundaries.
    edges = []
    if clk:
        prev = None
        for t, v in tv_map[clk]:
            if v == "1" and prev != "1":
                edges.append(t)
            prev = v

    if not edges:  # no usable clock — fall back to a raw transition list
        lines = ["Signal transitions (value@time):", ""]
        for s in signals:
            tv = tv_map.get(s, [])
            lines.append(
                f"{s}: " + " -> ".join(f"{_fmt_value(v)}@{t}" for t, v in tv)
                if tv else f"{s}: (no activity)"
            )
        return "\n".join(lines)

    lines = [
        "Digital RTL waveform, sampled once per clock cycle (at each rising "
        "clock edge). Each signal is listed as its value on cycle 1, 2, 3, ...",
        "Bus values are decimal; 'x' means undefined. The clock and reset are "
        "normal test scaffolding — focus on whether the DATA signals follow "
        "their expected sequence.",
        "",
        f"(total cycles: {len(edges)})",
    ]
    for s in signals:
        if s == clk:
            continue
        tv = tv_map.get(s, [])
        if not tv:
            lines.append(f"{s}: (no activity)")
            continue
        seq = [
            _fmt_value(_value_at(tv, t)) if _value_at(tv, t) is not None else "-"
            for t in edges
        ]
        lines.append(f"{s} (per cycle): " + ", ".join(seq))

    return "\n".join(lines)
