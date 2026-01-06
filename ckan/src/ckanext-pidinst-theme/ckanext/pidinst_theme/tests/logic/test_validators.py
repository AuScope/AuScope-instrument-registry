"""Tests for validators.py."""

import pytest

import ckan.plugins.toolkit as tk

from ckanext.pidinst_theme.logic import validators


def test_pidinst_theme_reauired_with_valid_value():
    assert validators.pidinst_theme_required("value") == "value"


def test_pidinst_theme_reauired_with_invalid_value():
    with pytest.raises(tk.Invalid):
        validators.pidinst_theme_required(None)
