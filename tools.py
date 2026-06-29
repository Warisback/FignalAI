"""
tools.py
--------
The four concrete tools the orchestrator uses.
Each is a thin Python wrapper around a system operation.

These are NOT LLM calls — they are the deterministic ground-truth layer.
  read_rtl   : read source lines from disk
  run_sim    : compile + simulate with iverilog/vvp
  apply_patch: safely edit one line of the RTL file
  (render_waveform lives in render.py)
"""

import subprocess
import pathlib
import shutil
import tempfile


# ---------------------------------------------------------------------------
# read_rtl
# ---------------------------------------------------------------------------

def read_rtl(path: str) -> list[str]:
    """
    Read a Verilog file and return its lines (1-indexed when passed to agents).

    Returns a list of strings — line N is at index N-1.
    """
    return pathlib.Path(path).read_text().splitlines()


# ---------------------------------------------------------------------------
# run_sim
# ---------------------------------------------------------------------------

def run_sim(rtl_path: str, tb_path: str, work_dir: str = ".") -> dict:
    """
    Compile and simulate the RTL module + testbench with Icarus Verilog.

    Steps:
      1. iverilog compiles design + TB into a simulation binary
      2. vvp runs the binary; the TB prints RESULT: PASS or RESULT: FAIL
      3. The VCD is written to <work_dir>/dump.vcd by the $dumpvars in the TB

    Returns a dict:
        passed : bool   — True if "RESULT: PASS" found in stdout
        stage  : str    — "compile" or "run" (where it failed, if it did)
        log    : str    — full stdout/stderr for the agents to read
        vcd    : str|None — path to the VCD file, or None on compile error
    """
    work    = pathlib.Path(work_dir)
    vcd     = str(work / "dump.vcd")

    # Run iverilog AND vvp from inside work_dir so the sim binary, the dumped
    # VCD, and vvp's cwd all agree. sim_bin is therefore work-dir-relative;
    # the sources are absolute so they resolve regardless of cwd.
    sim_bin = "sim_out"
    rtl_abs = str(pathlib.Path(rtl_path).resolve())
    tb_abs  = str(pathlib.Path(tb_path).resolve())

    # Step 1 — compile
    comp = subprocess.run(
        ["iverilog", "-g2012", "-o", sim_bin, rtl_abs, tb_abs],
        capture_output=True, text=True, timeout=30,
        cwd=work_dir,
    )
    if comp.returncode != 0:
        return {
            "passed": False,
            "stage":  "compile",
            "log":    comp.stderr,
            "vcd":    None,
        }

    # Step 2 — simulate
    run = subprocess.run(
        ["vvp", sim_bin],
        capture_output=True, text=True, timeout=60,
        cwd=work_dir,
    )
    stdout  = run.stdout + run.stderr
    passed  = "RESULT: PASS" in stdout

    return {
        "passed": passed,
        "stage":  "run",
        "log":    stdout,
        "vcd":    vcd if pathlib.Path(vcd).exists() else None,
    }


# ---------------------------------------------------------------------------
# apply_patch
# ---------------------------------------------------------------------------

def apply_patch(
    rtl_path: str,
    line_no:  int,
    before:   str,
    after:    str,
) -> dict:
    """
    Replace one line in the RTL file.

    Refuses to patch if the 'before' text is not found on line_no —
    this is a second deterministic guard that prevents a wrong patch
    from corrupting the source.

    Returns:
        success : bool
        message : str  — description of what happened
        backup  : str  — path to a .bak copy of the original file
    """
    lines = pathlib.Path(rtl_path).read_text().splitlines()

    # make a backup before touching anything
    backup = rtl_path + ".bak"
    shutil.copy2(rtl_path, backup)

    if not (1 <= line_no <= len(lines)):
        return {
            "success": False,
            "message": f"line_no {line_no} out of range (file has {len(lines)} lines)",
            "backup":  backup,
        }

    actual = lines[line_no - 1]
    if before.strip() not in actual:
        return {
            "success": False,
            "message": (
                f"Safety check failed: '{before.strip()}' not found on line {line_no}.\n"
                f"Actual line: '{actual}'"
            ),
            "backup": backup,
        }

    # perform the substitution
    lines[line_no - 1] = actual.replace(before.strip(), after.strip())
    pathlib.Path(rtl_path).write_text("\n".join(lines) + "\n")

    return {
        "success": True,
        "message": f"line {line_no}: '{before.strip()}' → '{after.strip()}'",
        "backup":  backup,
    }


# ---------------------------------------------------------------------------
# apply_patches  (multi-edit, atomic)
# ---------------------------------------------------------------------------

def apply_patches(rtl_path: str, edits: list) -> dict:
    """
    Apply a LIST of edits in one shot. Each edit is {line_no, before, after}.

    Validates EVERY edit against the current source first; if any fails its
    safety check, nothing is written (all-or-nothing). This lets a single patch
    fix a multi-line bug — e.g. blocking '=' that must become non-blocking '<='
    across three lines — in one round instead of three.

    Returns:
        success : bool
        message : str
        backup  : str          — .bak of the original file
        applied : list[str]    — one human-readable line per applied edit
    """
    path  = pathlib.Path(rtl_path)
    lines = path.read_text().splitlines()

    backup = rtl_path + ".bak"
    shutil.copy2(rtl_path, backup)

    if not edits:
        return {"success": False, "message": "no edits provided", "backup": backup, "applied": []}

    # --- validate ALL edits before touching the file ---
    for e in edits:
        ln     = e.get("line_no")
        before = (e.get("before") or "").strip()
        if not isinstance(ln, int) or not (1 <= ln <= len(lines)):
            return {"success": False, "applied": [], "backup": backup,
                    "message": f"line_no {ln} out of range (file has {len(lines)} lines)"}
        if before not in lines[ln - 1]:
            return {"success": False, "applied": [], "backup": backup,
                    "message": (f"Safety check failed: '{before}' not found on line {ln}.\n"
                                f"Actual line: '{lines[ln - 1]}'")}

    # --- apply all (each edit operates on its own line) ---
    applied = []
    for e in edits:
        ln     = e["line_no"]
        before = e["before"].strip()
        after  = (e.get("after") or "").strip()
        lines[ln - 1] = lines[ln - 1].replace(before, after)
        applied.append(f"line {ln}: '{before}' → '{after}'")

    path.write_text("\n".join(lines) + "\n")
    return {"success": True, "message": "; ".join(applied), "backup": backup, "applied": applied}


# ---------------------------------------------------------------------------
# restore_backup
# ---------------------------------------------------------------------------

def restore_backup(rtl_path: str) -> bool:
    """Restore the .bak file if the patch made things worse."""
    backup = rtl_path + ".bak"
    if pathlib.Path(backup).exists():
        shutil.copy2(backup, rtl_path)
        return True
    return False
