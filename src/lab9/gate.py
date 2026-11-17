"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item
from lab9.graders import GRADERS


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    problems = []
    keys_of = lambda r: (r.get("item_id"), r.get("seed"))
    baseline_keys = {keys_of(r) for r in base.get("rows", [])}
    for name, report in (("PR", pr), ("baseline", base)):
        rows, manifest = report.get("rows", []), report.get("manifest", {})
        seeds = manifest.get("seeds", [])
        keys = [keys_of(r) for r in rows]
        items = {r.get("item_id") for r in rows}
        if len(rows) != manifest.get("items", 0) * len(seeds):
            problems.append(f"{name}: row count differs from manifest items × seeds")
        if len(set(keys)) != len(keys):
            problems.append(f"{name}: duplicate (item, seed) rows")
        if len(set(seeds)) != len(seeds) or len(items) != manifest.get("items"):
            problems.append(f"{name}: invalid manifest item/seed count")
        if not rows or set(keys) != {(i, s) for i in items for s in seeds}:
            problems.append(f"{name}: incomplete item × seed coverage")
        if set(keys) != baseline_keys:
            problems.append(f"{name}: item/seed set differs from baseline")
        if report.get("evaluator_failures"):
            problems.append(f"{name}: evaluator failures")
        if any(not isinstance(v, (int, float)) or not math.isfinite(v)
               for v in report.get("metrics", {}).values()):
            problems.append(f"{name}: non-finite or missing aggregate")
        for m in spec["metrics"]:
            mid = m["id"]
            if mid not in report.get("metrics", {}):
                problems.append(f"{name}: missing aggregate {mid}")
            graded = mid in GRADERS or any(mid in r for r in base.get("rows", []))
            if not graded:
                continue
            values = [r.get(mid) for r in rows]
            if any(not isinstance(v, (int, float)) or not math.isfinite(v) or v not in (0, 1)
                   for v in values):
                problems.append(f"{name}: invalid/missing row score for {mid}")
            elif values:
                expected = sum(values) if m.get("kind") == "safety" else round(sum(values) / len(values), 4)
                actual = report.get("metrics", {}).get(mid)
                if not isinstance(actual, (int, float)) or not math.isclose(actual, expected, abs_tol=1e-4):
                    problems.append(f"{name}: aggregate {mid} disagrees with rows")
        # Reliability and cost are derived metrics, not per-trial grades.
        by_item = {}
        for row in rows:
            by_item.setdefault(row.get("item_id"), []).append(row.get("pass_rate"))
        for mid, actual in report.get("metrics", {}).items():
            if mid == "pass_5" or mid.startswith(("pass_hat_", "pass_at_")):
                try:
                    k = 5 if mid == "pass_5" else int(mid.rsplit("_", 1)[1])
                    fn = stats.pass_at_k if mid.startswith("pass_at_") else stats.pass_hat_k
                    expected = round(sum(fn(len(v), sum(v), k) for v in by_item.values()) / len(by_item), 4)
                    if not isinstance(actual, (int, float)) or not math.isclose(actual, expected, abs_tol=1e-4):
                        problems.append(f"{name}: {mid} disagrees with rows")
                except (ValueError, TypeError, ZeroDivisionError):
                    problems.append(f"{name}: cannot derive {mid}")
        if "cost_per_success" in report.get("metrics", {}) and rows:
            costs = [r.get("cost") for r in rows]
            if any(not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in costs):
                problems.append(f"{name}: invalid costs")
            else:
                successes = sum(bool(r.get("pass_rate")) for r in rows)
                expected = round(sum(costs) / successes, 4) if successes else None
                if report["metrics"]["cost_per_success"] != expected:
                    problems.append(f"{name}: cost_per_success disagrees with rows")
    if set(pr.get("manifest", {}).get("seeds", [])) != set(base.get("manifest", {}).get("seeds", [])):
        problems.append("manifest seeds differ from baseline")
    if "seeds" in spec and set(pr.get("manifest", {}).get("seeds", [])) != set(spec["seeds"]):
        problems.append("manifest seeds differ from spec")
    tags = {keys_of(r): set(r.get("slices") or []) for r in base.get("rows", [])}
    if any(set(r.get("slices") or []) != tags.get(keys_of(r), set()) for r in pr.get("rows", [])):
        problems.append("slice tags differ from baseline")

    def ratchet(old, new, label):
        if old.get("blocking") and not new.get("blocking"):
            problems.append(f"ratchet: {label} is no longer blocking")
        for key in ("min", "max", "max_increase"):
            if key in old and (key not in new or
                               (new[key] < old[key] if key == "min" else new[key] > old[key])):
                problems.append(f"ratchet: {label}/{key} loosened")
        if old.get("no_significant_drop") and not new.get("no_significant_drop"):
            problems.append(f"ratchet: {label} dropped no_significant_drop")

    if base_spec and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        for section in ("metrics", "slices"):
            key = (lambda m: m["id"]) if section == "metrics" else (lambda m: (m["name"], m["metric"]))
            current = {key(m): m for m in spec.get(section, [])}
            for old in base_spec.get(section, []):
                label = f"{section}:{key(old)}"
                new = current.get(key(old))
                if new is None:
                    problems.append(f"ratchet: removed {label}")
                    continue
                ratchet(old, new, label)
                if section == "metrics":
                    ratchet(old.get("threshold", {}), new.get("threshold", {}), label)
                    if any(old.get(k) != new.get(k) for k in ("kind", "grader", "level")):
                        problems.append(f"ratchet: changed metric semantics {label}")
    return problems


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices", []):
        name, metric = s["name"], s["metric"]
        mid = f"slice:{name}/{metric}"
        a, b = per_item(pr, metric, name), per_item(base, metric, name)
        fail = not a or set(a) != set(b)
        value = sum(a.values()) / len(a) if a else None
        note = ""
        if value is not None:
            fail |= "min" in s and value < s["min"]
            fail |= "max" in s and value > s["max"]
            if s.get("no_significant_drop") and not (set(a) != set(b)):
                keys = sorted(a)
                d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                    n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                    confidence=bs.get("confidence", 0.95))
                fail |= hi < 0
                note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
        if fail and s.get("blocking"):
            blocked.append(mid)
        lines.append(f"  {mid} {value} {note} {'BLOCK' if fail and s.get('blocking') else 'warn' if fail else 'ok'}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                                               confidence=bs.get("confidence", 0.95))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
