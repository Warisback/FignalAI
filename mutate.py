"""
mutate.py
---------
Deterministic RTL bug-injector. Takes KNOWN-GOOD Verilog and injects a single,
realistic bug via classic mutation operators (the same bug classes FignalAI is
built to catch). No LLM involved — it's a verifiable ground truth.

Why it matters: feeding FignalAI a freshly-mutated module (a bug it has never
seen) and watching it diagnose + fix it proves the system generalises, rather
than memorising the shipped examples.

Each operator scans the source and returns the first applicable mutation:
    {line_no, before, after, op, desc}
`inject()` applies one and returns (mutated_lines, mutation) — or (None, None)
if nothing was applicable.
"""

import re

# Each operator: take list[str] lines -> mutation dict or None.
# A mutation records the exact (line_no, before, after) so it is reversible and
# can be compared against whatever FignalAI proposes.


def _off_by_one(lines):
    """Bump a decimal compare constant by one  (== 4'd9  ->  == 4'd10)."""
    for i, l in enumerate(lines):
        if "==" in l:
            m = re.search(r"'d(\d+)", l)
            if m:
                num = int(m.group(1))
                return dict(line_no=i + 1, before=f"'d{num}", after=f"'d{num + 1}",
                            op="off_by_one", desc=f"compare constant 'd{num} -> 'd{num + 1}")
    return None


def _blocking(lines):
    """Turn a non-blocking assignment into a blocking one  (<=  ->  =)."""
    for i, l in enumerate(lines):
        s = l.strip()
        if "<=" in l and s.endswith(";") and not s.startswith("if") and "if (" not in l:
            return dict(line_no=i + 1, before="<=", after="=",
                        op="blocking_assignment", desc="non-blocking <= -> blocking =")
    return None


def _cmp_flip(lines):
    """Flip an equality comparison  (==  ->  !=)."""
    for i, l in enumerate(lines):
        if "==" in l:
            return dict(line_no=i + 1, before="==", after="!=",
                        op="wrong_comparison", desc="== -> !=")
    return None


def _arith_flip(lines):
    """Flip an arithmetic operator  ( + -> - )  outside of sensitivity lists."""
    for i, l in enumerate(lines):
        if " + " in l and "always" not in l and "@" not in l:
            return dict(line_no=i + 1, before=" + ", after=" - ",
                        op="wrong_operator", desc="+ -> -")
    return None


# Order matters only for the default scan; `prefer` can force a class.
OPERATORS = {
    "off_by_one":         _off_by_one,
    "blocking_assignment": _blocking,
    "wrong_comparison":   _cmp_flip,
    "wrong_operator":     _arith_flip,
}


def inject(lines: list[str], prefer: str | None = None):
    """
    Inject ONE bug into a copy of `lines`.

    prefer : optional op name to try first (else scans OPERATORS in order).
    Returns (mutated_lines, mutation_dict) or (None, None) if nothing applied.
    """
    order = list(OPERATORS)
    if prefer in OPERATORS:
        order = [prefer] + [o for o in order if o != prefer]

    for name in order:
        m = OPERATORS[name](lines)
        if m:
            mutated = list(lines)
            idx = m["line_no"] - 1
            mutated[idx] = mutated[idx].replace(m["before"], m["after"], 1)
            return mutated, m
    return None, None
