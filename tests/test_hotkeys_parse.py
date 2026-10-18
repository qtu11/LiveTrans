import pytest

from livetrans.hotkeys import parse_hotkey


def test_ctrl_alt_letter():
    assert parse_hotkey("Ctrl+Alt+T") == (0x4003, 0x54)


def test_case_insensitive_function_key():
    assert parse_hotkey("ctrl+shift+F5") == (0x4006, 0x74)


def test_win_and_digit():
    assert parse_hotkey("Win+Alt+1") == (0x4009, 0x31)


@pytest.mark.parametrize("bad", ["Ctrl+", "Ctrl+Alt+Foo", "", "Ctrl+Alt", "T+Ctrl"])
def test_invalid(bad):
    with pytest.raises(ValueError):
        parse_hotkey(bad)
