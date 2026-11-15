import pytest

from app.services.llm.jsonfix import parse_json


def test_latex_single_backslashes_survive():
    raw = r'{"f": "$\frac{1}{2} \times \sqrt{x} \neq \beta$", "t": "ligne 1\nligne 2"}'
    data = parse_json(raw)
    assert data["f"] == r"$\frac{1}{2} \times \sqrt{x} \neq \beta$"
    assert data["t"] == "ligne 1\nligne 2"


def test_latex_double_backslashes_untouched():
    raw = r'{"f": "$\\frac{a}{b} \\to 0$", "g": "\\theta"}'
    data = parse_json(raw)
    assert data == {"f": r"$\frac{a}{b} \to 0$", "g": r"\theta"}


def test_real_newline_before_word_is_kept():
    data = parse_json(r'{"t": "a\nnous\ttab", "u": "été"}')
    assert data == {"t": "a\nnous\ttab", "u": "été"}


def test_code_fences_and_trailing_comma():
    data = parse_json('Voici :\n```json\n{"a": [1, 2,], "b": "x",}\n```')
    assert data == {"a": [1, 2], "b": "x"}


def test_arabic_and_raw_newlines():
    data = parse_json('{"t": "الدالة\nالعددية", "f": "$x \\in \\mathbb{R}$"}')
    assert data["t"] == "الدالة\nالعددية"
    assert data["f"] == r"$x \in \mathbb{R}$"


def test_garbage_raises():
    with pytest.raises(ValueError):
        parse_json("désolé, je ne peux pas")
