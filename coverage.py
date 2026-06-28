"""
coverage.py
-----------
Deterministic functional coverage from a simulation VCD — no instrumentation,
no extra tooling. We reuse the VCD parser and compute TOGGLE coverage: for every
signal bit, did it take both 0 and 1 during the run?

A bit that never toggles is a coverage HOLE — often an untested path or a stuck
bug (e.g. an FSM state that's never reached shows up as a high bit stuck at 0).

This is the deterministic core of the coverage-driven bug hunt: measure → find
holes → (agent) generate stimulus to hit them → repeat until a threshold.
"""

from render import parse_vcd


def signal_widths(vcd_path: str) -> dict:
    """Declared bit-width of each signal, from the VCD $var header.

    Needed so an FSM whose high bit never sets (e.g. DONE never reached) is still
    treated as a 2-bit bus and the unreached bit shows up as a hole — inferring
    width from observed values would miss exactly that case.
    """
    widths = {}
    with open(vcd_path) as f:
        for line in f:
            s = line.strip()
            if s.startswith("$var"):
                p = s.split()            # $var <type> <size> <id> <name> ...
                if len(p) >= 5:
                    try:
                        widths.setdefault(p[4], int(p[2]))
                    except ValueError:
                        pass
            elif s.startswith("$enddefinitions"):
                break
    return widths


def _per_bit_seen(values: list[str], width: int) -> list[set]:
    """Per-bit sets of chars seen, padded to `width`. Index 0 is the MSB."""
    seen = [set() for _ in range(width)]
    for v in values:
        if set(v) <= set("01xz"):
            for i, ch in enumerate(v.rjust(width, "0")[-width:]):
                seen[i].add(ch)
    return seen


def toggle_coverage(vcd_path: str, signals: list[str] | None = None) -> dict:
    """
    Compute toggle coverage over the given signals (or all signals in the VCD).

    Returns:
        overall_pct  : float    — covered_bits / total_bits * 100
        total_bits   : int
        covered_bits : int
        per_signal   : {name: {bits, covered, pct}}
        holes        : [{signal, bit, stuck}]   — bits that never toggled
    """
    tv = parse_vcd(vcd_path)
    widths = signal_widths(vcd_path)
    names = signals if signals is not None else list(tv.keys())

    per_signal, holes = {}, []
    total_bits = covered_bits = 0

    for name in names:
        vals = [v for _, v in tv.get(name, [])]
        width = widths.get(name, 1)
        if not vals:
            per_signal[name] = {"bits": 0, "covered": 0, "pct": 0.0}
            continue

        if width <= 1:                                # scalar signal
            chars = set("".join(vals))
            cov = 1 if {"0", "1"} <= chars else 0
            per_signal[name] = {"bits": 1, "covered": cov, "pct": 100.0 * cov}
            total_bits += 1; covered_bits += cov
            if not cov:
                holes.append({"signal": name, "bit": None,
                              "stuck": next(iter(chars & {"0", "1"}), "x")})
        else:                                         # bus signal — per bit
            seen  = _per_bit_seen(vals, width)
            cov   = sum(1 for s in seen if {"0", "1"} <= s)
            per_signal[name] = {"bits": width, "covered": cov,
                                "pct": round(100.0 * cov / width, 1) if width else 0.0}
            total_bits += width; covered_bits += cov
            for i, s in enumerate(seen):
                if not ({"0", "1"} <= s):
                    holes.append({"signal": name, "bit": width - 1 - i,
                                  "stuck": next(iter(s & {"0", "1"}), "x")})

    overall = round(100.0 * covered_bits / total_bits, 1) if total_bits else 0.0
    return {
        "overall_pct":  overall,
        "total_bits":   total_bits,
        "covered_bits": covered_bits,
        "per_signal":   per_signal,
        "holes":        holes,
    }


def coverage_report(cov: dict) -> str:
    """One-line-per-signal text report (for logs / the agent's coverage view)."""
    lines = [f"Toggle coverage: {cov['overall_pct']}% "
             f"({cov['covered_bits']}/{cov['total_bits']} bits)"]
    for name, s in cov["per_signal"].items():
        lines.append(f"  {name:<12} {s['pct']:>5}%  ({s['covered']}/{s['bits']} bits)")
    if cov["holes"]:
        lines.append("Holes (never toggled):")
        for h in cov["holes"]:
            where = name_bit(h)
            lines.append(f"  {where} stuck at {h['stuck']}")
    return "\n".join(lines)


def name_bit(hole: dict) -> str:
    return hole["signal"] if hole["bit"] is None else f"{hole['signal']}[{hole['bit']}]"
