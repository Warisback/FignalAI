"""
checks.py
---------
Deterministic (non-LLM) guards against model hallucinations.
These run in microseconds and are the strongest filter in the pipeline.
"""


def line_check(rtl_lines: list[str], line_no: int, quoted_code: str) -> bool:
    """
    Guard 1 — deterministic line verification.

    The Code agent returns both a line_no and the quoted_code it claims
    sits on that line. This function checks that claim without calling
    any model.

    Returns False (reject hypothesis) if:
      - line_no is out of range
      - the quoted text does not appear on that line

    Why this matters: the most common hallucination is a model inventing
    a line number. This catches that cheaply and certainly.
    """
    if not (1 <= line_no <= len(rtl_lines)):
        return False  # line out of range — fabricated

    actual = rtl_lines[line_no - 1].strip()
    quoted = quoted_code.strip()

    # Accept if either is a substring of the other
    # (the model may quote a partial line, which is fine)
    return quoted in actual or actual in quoted


def patch_check(rtl_lines: list[str], line_no: int, before: str) -> bool:
    """
    Guard before applying a patch.
    Refuses to modify the file if the 'before' text isn't on the claimed line.
    Prevents a wrong patch from corrupting the source.
    """
    return line_check(rtl_lines, line_no, before)


def majority_vote(hypotheses: list[dict]) -> dict | None:
    """
    Given a list of Code-agent hypotheses (each with 'line_no' and 'bug_class'),
    return the one that appears most often.

    If there is no majority (all unique), return None to signal low confidence.
    """
    if not hypotheses:
        return None

    from collections import Counter
    votes = Counter(
        (h["line_no"], h.get("bug_class", "unknown"))
        for h in hypotheses
    )
    (line_no, bug_class), count = votes.most_common(1)[0]

    if count == 1 and len(hypotheses) > 1:
        return None  # no agreement — flag as low confidence

    # Return the first hypothesis that matches the winning vote
    for h in hypotheses:
        if h["line_no"] == line_no and h.get("bug_class", "unknown") == bug_class:
            return h

    return hypotheses[0]
