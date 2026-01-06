"""Tests for helpers.py."""

import ckanext.pidinst_theme.helpers as helpers


def test_pidinst_theme_hello():
    assert helpers.pidinst_theme_hello() == "Hello, pidinst_theme!"
