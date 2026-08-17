from stock_platform.domain.research.decision_diff import build_decision_diff


def test_decision_diff_is_deterministic_and_sorted() -> None:
    previous = {"opinion": "NEUTRAL", "confidence": "0.50", "unchanged": ["A"]}
    current = {"unchanged": ["A"], "confidence": "0.75", "opinion": "BULLISH"}

    expected = {
        "confidence": {"before": "0.50", "after": "0.75"},
        "opinion": {"before": "NEUTRAL", "after": "BULLISH"},
    }

    assert build_decision_diff(previous, current) == expected
    assert list(build_decision_diff(previous, current)) == ["confidence", "opinion"]


def test_decision_diff_represents_added_and_removed_fields() -> None:
    assert build_decision_diff({"removed": 1}, {"added": 2}) == {
        "added": {"before": None, "after": 2},
        "removed": {"before": 1, "after": None},
    }
