"""Tests for views.py."""

import pytest

import ckanext.pidinst_theme.validators as validators


import ckan.plugins.toolkit as tk


@pytest.mark.ckan_config("ckan.plugins", "pidinst_theme")
@pytest.mark.usefixtures("with_plugins")
def test_pidinst_theme_blueprint(app, reset_db):
    resp = app.get(tk.h.url_for("pidinst_theme.page"))
    assert resp.status_code == 200
    assert resp.body == "Hello, pidinst_theme!"
