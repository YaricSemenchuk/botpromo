import os

import pytest

from tgparser.config import _env


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv("TEST_VAR", raising=False)
    return monkeypatch


def test_env_strips_trailing_newline(clean_env):
    clean_env.setenv("TEST_VAR", "value\n")
    assert _env("TEST_VAR") == "value"


def test_env_strips_trailing_carriage_return(clean_env):
    clean_env.setenv("TEST_VAR", "value\r\n")
    assert _env("TEST_VAR") == "value"


def test_env_strips_surrounding_whitespace(clean_env):
    clean_env.setenv("TEST_VAR", "  value  ")
    assert _env("TEST_VAR") == "value"


def test_env_preserves_internal_content(clean_env):
    clean_env.setenv("TEST_VAR", "  a b c  ")
    assert _env("TEST_VAR") == "a b c"


def test_env_missing_required_raises(clean_env):
    with pytest.raises(RuntimeError, match="TEST_VAR"):
        _env("TEST_VAR", required=True)


def test_env_whitespace_only_required_raises(clean_env):
    clean_env.setenv("TEST_VAR", "   \n")
    with pytest.raises(RuntimeError, match="TEST_VAR"):
        _env("TEST_VAR", required=True)
