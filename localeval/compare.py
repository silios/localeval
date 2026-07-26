"""Side-by-side diff of two localeval runs.

Pure read-only analysis: loads summary.json from two run directories,
computes deltas (overall score, per-category/constraint, latency), and
returns a structured dict for display.
"""

from __future__ import annotations


def _pct_field(mode: str) -> str:
    """The percentage field name in the summary for each mode."""
    if mode == "mmlu":
        return "accuracy_pct"
    elif mode == "code":
        return "pass_rate_pct"
    else:
        return "overall_pass_rate_pct"


def _earned_wrong(mode: str, summary: dict) -> tuple:
    """Return (earned, wrong) counts from a summary dict."""
    if mode == "mmlu":
        return summary["correct"], summary["wrong"]
    return summary["pass"], summary["fail"]


def _category_field(mode: str) -> str:
    """The per-group field name: 'by_category' for mmlu, 'by_constraint' for ifeval."""
    return "by_constraint" if mode == "ifeval" else "by_category"


def _group_pct_field(mode: str) -> str:
    """The percentage field inside each group dict."""
    return "pass_rate_pct" if mode == "ifeval" else "accuracy_pct"


def _group_earned_wrong(mode: str, g: dict) -> tuple:
    """Return (earned, wrong) from a group (category/constraint) dict."""
    if mode == "ifeval":
        return g["pass"], g["fail"]
    return g["correct"], g["wrong"]


def _bench_group_diff(a: dict, b: dict) -> dict:
    """pp/tg t/s deltas between two bench summary dicts (overall or one
    depth's stats) - positive delta means b is faster."""
    pp_a = a.get("pp_tokens_per_sec_median", 0)
    pp_b = b.get("pp_tokens_per_sec_median", 0)
    tg_a = a.get("tg_tokens_per_sec_median", 0)
    tg_b = b.get("tg_tokens_per_sec_median", 0)
    return {
        "pp_tps_a": pp_a,
        "pp_tps_b": pp_b,
        "pp_tps_delta": round(pp_b - pp_a, 1),
        "tg_tps_a": tg_a,
        "tg_tps_b": tg_b,
        "tg_tps_delta": round(tg_b - tg_a, 1),
    }


def diff_bench_summaries(a: dict, b: dict) -> dict:
    """Compute pp/tg t/s deltas between two bench summaries, overall and
    per context depth. a is the baseline (run 1), b is the comparison
    (run 2) - positive deltas mean b is faster."""
    overall = _bench_group_diff(a, b)
    overall["errors_a"] = a.get("error", 0)
    overall["errors_b"] = b.get("error", 0)

    depths_a = a.get("by_depth", {})
    depths_b = b.get("by_depth", {})
    all_depths = sorted(set(depths_a) | set(depths_b), key=int)

    by_depth = {}
    for depth in all_depths:
        da = depths_a.get(depth)
        db = depths_b.get(depth)
        if da and db:
            by_depth[depth] = _bench_group_diff(da, db)
        elif da:
            by_depth[depth] = {
                "pp_tps_a": da.get("pp_tokens_per_sec_median", 0), "pp_tps_b": "-", "pp_tps_delta": "-",
                "tg_tps_a": da.get("tg_tokens_per_sec_median", 0), "tg_tps_b": "-", "tg_tps_delta": "-",
            }
        else:
            by_depth[depth] = {
                "pp_tps_a": "-", "pp_tps_b": db.get("pp_tokens_per_sec_median", 0), "pp_tps_delta": "-",
                "tg_tps_a": "-", "tg_tps_b": db.get("tg_tokens_per_sec_median", 0), "tg_tps_delta": "-",
            }

    return {"mode": "bench", "overall": overall, "by_depth": by_depth}


def diff_summaries(mode: str, a: dict, b: dict) -> dict:
    """Compute deltas between two summary dicts of the same mode.

    Returns a structured dict with overall, per-category/constraint, and
    latency comparisons. a is the baseline (run 1), b is the comparison
    (run 2) - positive deltas mean b did better.
    """
    if mode == "bench":
        return diff_bench_summaries(a, b)

    pct_key = _pct_field(mode)
    earned_a, wrong_a = _earned_wrong(mode, a)
    earned_b, wrong_b = _earned_wrong(mode, b)
    total_a = earned_a + wrong_a
    total_b = earned_b + wrong_b

    overall = {
        "earned_a": earned_a,
        "earned_b": earned_b,
        "earned_delta": earned_b - earned_a,
        "total_a": total_a,
        "total_b": total_b,
        "total_delta": total_b - total_a,
        "pct_a": round(a.get(pct_key, 0), 1),
        "pct_b": round(b.get(pct_key, 0), 1),
        "pct_delta": round(b.get(pct_key, 0) - a.get(pct_key, 0), 1),
        "errors_a": a.get("error", 0),
        "errors_b": b.get("error", 0),
    }

    # Per-category / per-constraint deltas
    group_key = _category_field(mode)
    gpct = _group_pct_field(mode)
    groups_a = a.get(group_key, {})
    groups_b = b.get(group_key, {})

    group_deltas = {}
    all_group_names = set(groups_a) | set(groups_b)
    for name in sorted(all_group_names):
        ga = groups_a.get(name)
        gb = groups_b.get(name)
        if ga and gb:
            ea, wa = _group_earned_wrong(mode, ga)
            eb, wb = _group_earned_wrong(mode, gb)
            group_deltas[name] = {
                "pct_a": round(ga.get(gpct, 0), 1),
                "pct_b": round(gb.get(gpct, 0), 1),
                "pct_delta": round(gb.get(gpct, 0) - ga.get(gpct, 0), 1),
                "earned_a": ea,
                "earned_b": eb,
                "total_a": ea + wa,
                "total_b": eb + wb,
            }
        elif ga:
            ea, wa = _group_earned_wrong(mode, ga)
            group_deltas[name] = {
                "pct_a": round(ga.get(gpct, 0), 1),
                "pct_b": "-",
                "pct_delta": "-",
                "earned_a": ea,
                "earned_b": "-",
                "total_a": ea + wa,
                "total_b": "-",
            }
        else:
            eb, wb = _group_earned_wrong(mode, gb)
            group_deltas[name] = {
                "pct_a": "-",
                "pct_b": round(gb.get(gpct, 0), 1),
                "pct_delta": "-",
                "earned_a": "-",
                "earned_b": eb,
                "total_a": "-",
                "total_b": eb + wb,
            }

    # Latency comparison
    la = a.get("latency") or {}
    lb = b.get("latency") or {}
    latency = {}
    if la and lb:
        for field, suffix in [("ttft_p50_ms", "ms"), ("ttft_p95_ms", "ms"), ("tps_p50", ""), ("tps_p95", "")]:
            va = la.get(field)
            vb = lb.get(field)
            if va is not None and vb is not None:
                delta_key = field.replace("_ms", "_delta_ms") if field.endswith("_ms") else f"{field}_delta"
                latency[delta_key] = round(vb - va, 1)
                a_key = field + "_a"
                b_key = field + "_b"
                latency[a_key] = round(va, 1)
                latency[b_key] = round(vb, 1)

    result = {
        "mode": mode,
        "overall": overall,
        "latency": latency,
    }
    result["categories" if mode != "ifeval" else "constraints"] = group_deltas
    return result
