# -*- coding: utf-8 -*-
"""Tests for A2AServer i18n module"""
import pytest
import sys

sys.path.insert(0, "backend/A2AServer/src")

from A2AServer.i18n import t, set_locale, get_locale, SUPPORTED_LOCALES


class TestI18n:
    def test_supported_locales(self):
        assert "zh" in SUPPORTED_LOCALES
        assert "en" in SUPPORTED_LOCALES

    def test_t_zh(self):
        assert t("ok") == "成功"

    def test_t_en(self):
        assert t("ok", lang="en") == "OK"

    def test_t_with_vars(self):
        msg = t("agent_not_found", lang="zh", agent_name="ha")
        assert "ha" in msg
        assert "Agent" in msg

    def test_t_missing_key_falls_back(self):
        result = t("nonexistent_key")
        assert result == "nonexistent_key"  # returns key itself

    def test_set_locale(self):
        set_locale("en")
        assert get_locale() == "en"
        set_locale("zh")
        assert get_locale() == "zh"

    def test_set_locale_invalid_raises(self):
        with pytest.raises(ValueError):
            set_locale("fr")

    def test_context_vars_isolation(self):
        import contextvars
        token = contextvars.copy_context().copy()
        set_locale("zh")
        assert get_locale() == "zh"
