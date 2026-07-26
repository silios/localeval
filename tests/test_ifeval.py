from localeval import ifeval


def test_exact_word_count():
    assert ifeval.check_exact_word_count("one two three", {"n": 3}) is True
    assert ifeval.check_exact_word_count("one two", {"n": 3}) is False


def test_must_include_and_not_include():
    assert ifeval.check_must_include("The Cat sat", {"word": "cat"}) is True
    assert ifeval.check_must_not_include("The dog sat", {"word": "cat"}) is True
    assert ifeval.check_must_not_include("The Cat sat", {"word": "cat"}) is False


def test_valid_json():
    assert ifeval.check_valid_json('{"ok": true}', {}) is True
    assert ifeval.check_valid_json("not json", {}) is False
    assert ifeval.check_valid_json('```json\n{"ok": true}\n```', {}) is True


def test_exact_bullet_count():
    text = "- apple\n- banana\n- cherry"
    assert ifeval.check_exact_bullet_count(text, {"n": 3}) is True
    assert ifeval.check_exact_bullet_count(text, {"n": 2}) is False


def test_forbidden_letter():
    assert ifeval.check_forbidden_letter("no vowels here", {"letter": "z"}) is True
    assert ifeval.check_forbidden_letter("hello", {"letter": "e"}) is False


def test_all_lowercase_uppercase():
    assert ifeval.check_all_lowercase("all lower", {}) is True
    assert ifeval.check_all_lowercase("Not Lower", {}) is False
    assert ifeval.check_all_uppercase("ALL UPPER", {}) is True


def test_exact_sentence_count():
    assert ifeval.check_exact_sentence_count("One. Two. Three.", {"n": 3}) is True
