"""Unit-test skeleton for group auth helpers and auth functions.

Run inside the CKAN test environment, e.g.:
    pytest ckanext/pidinst_theme/tests/logic/test_auth_group.py
"""
import pytest
from unittest.mock import MagicMock, patch

from ckanext.pidinst_theme.logic.auth import (
    _get_configured_admin_orgs,
    _user_is_admin_of_org,
    _user_is_admin_of_any_configured_admin_org,
    group_create,
    group_update,
)


# ---------------------------------------------------------------------------
# _get_configured_admin_orgs
# ---------------------------------------------------------------------------

class TestGetConfiguredAdminOrgs:
    def test_empty_config_returns_empty_list(self):
        with patch("ckanext.pidinst_theme.logic.auth.tk") as mock_tk:
            mock_tk.config.get.return_value = ""
            result = _get_configured_admin_orgs()
        assert result == []

    def test_single_org(self):
        with patch("ckanext.pidinst_theme.logic.auth.tk") as mock_tk:
            mock_tk.config.get.return_value = "my-org"
            result = _get_configured_admin_orgs()
        assert result == ["my-org"]

    def test_comma_separated_orgs(self):
        with patch("ckanext.pidinst_theme.logic.auth.tk") as mock_tk:
            mock_tk.config.get.return_value = "org-a, org-b , org-c"
            result = _get_configured_admin_orgs()
        assert result == ["org-a", "org-b", "org-c"]

    def test_empty_items_ignored(self):
        with patch("ckanext.pidinst_theme.logic.auth.tk") as mock_tk:
            mock_tk.config.get.return_value = "org-a,,  ,org-b"
            result = _get_configured_admin_orgs()
        assert result == ["org-a", "org-b"]

    def test_none_config_returns_empty_list(self):
        with patch("ckanext.pidinst_theme.logic.auth.tk") as mock_tk:
            mock_tk.config.get.return_value = None
            result = _get_configured_admin_orgs()
        assert result == []


# ---------------------------------------------------------------------------
# _user_is_admin_of_org
# ---------------------------------------------------------------------------

class TestUserIsAdminOfOrg:
    def test_returns_true_for_admin_role(self):
        with patch("ckanext.pidinst_theme.logic.auth.authz") as mock_authz:
            mock_authz.users_role_for_group_or_org.return_value = "admin"
            assert _user_is_admin_of_org("alice", "my-org") is True
            mock_authz.users_role_for_group_or_org.assert_called_once_with("my-org", "alice")

    def test_returns_false_for_editor_role(self):
        with patch("ckanext.pidinst_theme.logic.auth.authz") as mock_authz:
            mock_authz.users_role_for_group_or_org.return_value = "editor"
            assert _user_is_admin_of_org("alice", "my-org") is False

    def test_returns_false_for_no_role(self):
        with patch("ckanext.pidinst_theme.logic.auth.authz") as mock_authz:
            mock_authz.users_role_for_group_or_org.return_value = None
            assert _user_is_admin_of_org("alice", "my-org") is False

    def test_returns_false_on_exception(self):
        with patch("ckanext.pidinst_theme.logic.auth.authz") as mock_authz:
            mock_authz.users_role_for_group_or_org.side_effect = Exception("db error")
            assert _user_is_admin_of_org("alice", "missing-org") is False


# ---------------------------------------------------------------------------
# _user_is_admin_of_any_configured_admin_org
# ---------------------------------------------------------------------------

class TestUserIsAdminOfAnyConfiguredAdminOrg:
    def test_no_configured_orgs_returns_false(self):
        with patch("ckanext.pidinst_theme.logic.auth.tk") as mock_tk, \
             patch("ckanext.pidinst_theme.logic.auth.authz"):
            mock_tk.config.get.return_value = ""
            assert _user_is_admin_of_any_configured_admin_org("alice") is False

    def test_user_is_admin_of_one_org_returns_true(self):
        with patch("ckanext.pidinst_theme.logic.auth.tk") as mock_tk, \
             patch("ckanext.pidinst_theme.logic.auth.authz") as mock_authz:
            mock_tk.config.get.return_value = "org-a,org-b"
            mock_authz.users_role_for_group_or_org.side_effect = lambda org, user: (
                "admin" if org == "org-b" else "member"
            )
            assert _user_is_admin_of_any_configured_admin_org("alice") is True

    def test_user_is_not_admin_of_any_org_returns_false(self):
        with patch("ckanext.pidinst_theme.logic.auth.tk") as mock_tk, \
             patch("ckanext.pidinst_theme.logic.auth.authz") as mock_authz:
            mock_tk.config.get.return_value = "org-a,org-b"
            mock_authz.users_role_for_group_or_org.return_value = "member"
            assert _user_is_admin_of_any_configured_admin_org("alice") is False


# ---------------------------------------------------------------------------
# group_create / group_update auth functions
# ---------------------------------------------------------------------------

def _make_user(name="alice"):
    user = MagicMock()
    user.name = name
    return user


def _make_next_auth(success):
    def next_auth(context, data_dict):
        return {"success": success}
    return next_auth


class TestGroupCreateAuth:
    def test_anonymous_user_denied(self):
        context = {"auth_user_obj": None}
        result = group_create(_make_next_auth(False), context, {})
        assert result["success"] is False

    def test_core_allows_passes_through(self):
        context = {"auth_user_obj": _make_user()}
        result = group_create(_make_next_auth(True), context, {})
        assert result["success"] is True

    def test_admin_of_configured_org_allowed(self):
        context = {"auth_user_obj": _make_user("alice")}
        with patch(
            "ckanext.pidinst_theme.logic.auth._user_is_admin_of_any_configured_admin_org",
            return_value=True,
        ):
            result = group_create(_make_next_auth(False), context, {})
        assert result["success"] is True

    def test_non_admin_user_denied(self):
        context = {"auth_user_obj": _make_user("bob")}
        with patch(
            "ckanext.pidinst_theme.logic.auth._user_is_admin_of_any_configured_admin_org",
            return_value=False,
        ):
            result = group_create(_make_next_auth(False), context, {})
        assert result["success"] is False


class TestGroupUpdateAuth:
    def test_anonymous_user_denied(self):
        context = {"auth_user_obj": None}
        result = group_update(_make_next_auth(False), context, {})
        assert result["success"] is False

    def test_core_allows_passes_through(self):
        context = {"auth_user_obj": _make_user()}
        result = group_update(_make_next_auth(True), context, {})
        assert result["success"] is True

    def test_admin_of_configured_org_allowed(self):
        context = {"auth_user_obj": _make_user("alice")}
        with patch(
            "ckanext.pidinst_theme.logic.auth._user_is_admin_of_any_configured_admin_org",
            return_value=True,
        ):
            result = group_update(_make_next_auth(False), context, {})
        assert result["success"] is True

    def test_non_admin_user_denied(self):
        context = {"auth_user_obj": _make_user("bob")}
        with patch(
            "ckanext.pidinst_theme.logic.auth._user_is_admin_of_any_configured_admin_org",
            return_value=False,
        ):
            result = group_update(_make_next_auth(False), context, {})
        assert result["success"] is False
