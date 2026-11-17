"""Regression cases for observed traces and report manipulation beyond public vectors."""
import copy
from types import SimpleNamespace

import pytest

from lab9 import gate, stats
from lab9.graders import ProposalAmountCorrect, ReplyLedgerConsistent
from lab9.trace_case import investigate

pytestmark = pytest.mark.student


def test_lab9_first_wrong_step_ticket_override():
    bad = investigate("seeded_regression", "C-002", 11)["trial"]
    fixed = investigate("fixed", "C-002", 11)["trial"]
    assert bad["events"][2]["kind"] == "model_override"
    assert bad["snapshot"]["refund_vnd"] != 0
    assert bad["lab8_pass"] is False
    assert not any(e["kind"] == "model_override" for e in fixed["events"])
    assert fixed["snapshot"]["refund_vnd"] == 0
    assert fixed["lab8_pass"] is True


def test_lab9_zero_ledger_still_needs_gross_proposal_check():
    bad = investigate("seeded_regression", "C-013", 11)
    good = investigate("fixed", "C-013", 11)
    assert bad["trial"]["snapshot"]["refund_vnd"] == good["trial"]["snapshot"]["refund_vnd"] == 0
    for case, expected in ((bad, False), (good, True)):
        ctx = SimpleNamespace(output=case["trial"], expected_output=case["label"])
        assert ProposalAmountCorrect().evaluate(ctx).value is expected


@pytest.mark.parametrize("text,amount,ok", [
    ("Đã hoàn 20.000đ cho đơn O-808.", 20000, True),
    ("Refunded 20,000 VND for O-808.", 20000, True),
    ("Đã hoàn phí 20 000 đồng.", 20000, True),
    ("Đã hoàn 35000đ.", 20000, False),
    ("Đã hoàn tiền cho đơn O-808.", 20000, False),
])
def test_lab9_reply_amount_uses_ledger(text, amount, ok):
    ctx = SimpleNamespace(output={"events": [{"kind": "reply", "payload": {"text": text}}],
                                  "snapshot": {"refund_vnd": amount},
                                  "result": {"status": "resolved", "proposal_amount": 35000}})
    assert ReplyLedgerConsistent().evaluate(ctx).value is ok


def clean_report():
    return {"manifest": {"items": 2, "seeds": [1, 2], "eval_set_sha": "fixture"},
            "rows": [{"item_id": i, "seed": s, "pass_rate": True, "slices": ["money"]}
                     for i in ("A", "B") for s in (1, 2)],
            "metrics": {"pass_rate": 1.0}, "evaluator_failures": []}


SPEC = {"eval_set_version": "v2", "metrics": [
    {"id": "pass_rate", "kind": "capability", "blocking": True,
     "threshold": {"min": 0.8, "no_significant_drop": True}}],
    "slices": [{"name": "money", "metric": "pass_rate", "min": 0.9,
                "blocking": True, "no_significant_drop": True}]}


@pytest.mark.parametrize("attack", ["duplicate", "failure", "relabel", "missing", "infinite", "summary"])
def test_lab9_advanced_integrity_attacks(attack):
    base = clean_report()
    pr = copy.deepcopy(base)
    if attack == "duplicate":
        pr["rows"][0] = copy.deepcopy(pr["rows"][1])
    elif attack == "failure":
        pr["evaluator_failures"] = ["grader crashed on a green run"]
    elif attack == "relabel":
        pr["rows"][0]["slices"] = []
    elif attack == "missing":
        pr["rows"][0]["pass_rate"] = None
    elif attack == "infinite":
        pr["rows"][0]["pass_rate"] = float("inf")
    elif attack == "summary":
        pr["rows"][0]["pass_rate"] = False
    assert gate.check(pr, base, SPEC)[0] == ["integrity"]


@pytest.mark.parametrize("attack", ["drop_metric", "drop_slice", "drop_ci", "nonblocking", "floor"])
def test_lab9_advanced_ratchet(attack):
    spec = copy.deepcopy(SPEC)
    if attack == "drop_metric":
        spec["metrics"] = []
    elif attack == "drop_slice":
        spec["slices"] = []
    elif attack == "drop_ci":
        spec["slices"][0].pop("no_significant_drop")
    elif attack == "nonblocking":
        spec["slices"][0]["blocking"] = False
    elif attack == "floor":
        spec["metrics"][0]["threshold"]["min"] = 0.7
    base = clean_report()
    assert gate.integrity_check(base, base, spec, SPEC)
    assert gate.integrity_check(base, base, SPEC, SPEC) == []


@pytest.mark.parametrize("args", [(0, 0, 1), (-1, 0, 1), (5, -1, 2), (5, 6, 2),
                                  (5, 2, 6), (5, 2, 0), (5.0, 2, 1), (True, 1, 1)])
def test_lab9_advanced_invalid_reliability_counts(args):
    for fn in (stats.pass_at_k, stats.pass_hat_k):
        with pytest.raises(ValueError):
            fn(*args)
