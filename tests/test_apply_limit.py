"""Tests for reporting.apply_limit - the --limit stride-sampling logic.

A plain [:limit] slice is a biased sample when items are grouped by
category (e.g. easy categories first, hard ones last), which would make
--limit systematically optimistic instead of representative.
"""

from localeval.reporting import apply_limit


def test_no_limit_returns_all_items():
    items = list(range(10))
    assert apply_limit(items, None) == items


def test_limit_greater_than_length_returns_all_items():
    items = list(range(5))
    assert apply_limit(items, 100) == items


def test_limit_spreads_across_full_range_not_just_the_start():
    items = list(range(200))
    result = apply_limit(items, 20)
    assert len(result) == 20
    # must not be a biased first-N slice
    assert result != items[:20]
    # must actually span the whole range, not cluster at the start
    assert max(result) > 100


def test_limit_equal_to_length_returns_all_items():
    items = list(range(5))
    assert apply_limit(items, 5) == items


def test_limit_one_returns_first_item():
    items = list(range(10))
    assert apply_limit(items, 1) == [0]
