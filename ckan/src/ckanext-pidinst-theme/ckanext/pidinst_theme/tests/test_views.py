"""Tests for views.py."""

import pytest

from ckanext.pidinst_theme import views


import ckan.plugins.toolkit as tk


@pytest.mark.ckan_config("ckan.plugins", "pidinst_theme")
@pytest.mark.usefixtures("with_plugins")
def test_pidinst_theme_blueprint(app, reset_db):
    resp = app.get(tk.h.url_for("pidinst_theme.page"))
    assert resp.status_code == 200
    assert resp.body == "Hello, pidinst_theme!"


class _User:
    def __init__(self, name):
        self.id = name
        self.name = name


def _facet_items_for_visible_records(context, data_dict, records):
    assert not context.get("ignore_auth")
    user_name = getattr(context.get("auth_user_obj"), "name", None) or context.get("user")
    include_private = data_dict.get("include_private") is True

    visible = []
    for record in records:
        if not record.get("private"):
            visible.append(record)
        elif include_private and user_name in record.get("allowed_users", []):
            visible.append(record)

    search_facets = {}
    for field in data_dict.get("facet.field", []):
        counts = {}
        for record in visible:
            for value in record.get(field, []):
                counts[value] = counts.get(value, 0) + 1
        search_facets[field] = {
            "items": [
                {"name": name, "display_name": name, "count": count}
                for name, count in sorted(counts.items())
            ]
        }
    return {"search_facets": search_facets}


def test_party_tree_nodes_keep_full_hierarchy_with_visibility_counts(monkeypatch):
    records = [
        {
            "id": "public-record",
            "private": False,
            "groups": ["public-owner", "public-funder", "applied-spectra"],
            "vocab_owner_party": ["Public Owner"],
            "vocab_funder_party": ["Public Owner", "Public Funder"],
            "vocab_manufacturer_party": ["Public Manufacturer", "Applied Spectra"],
        },
        {
            "id": "private-record",
            "private": True,
            "allowed_users": ["alice"],
            "groups": ["private-owner", "private-manufacturer"],
            "vocab_owner_party": ["Private Owner"],
            "vocab_funder_party": [],
            "vocab_manufacturer_party": ["private-manufacturer"],
        },
    ]

    parties = {
        "parent-owner": {"title": "Parent Owner", "party_role": ["Owner"]},
        "public-owner": {
            "title": "Public Owner",
            "party_role": ["Owner"],
            "parent_party": "parent-owner",
        },
        "public-funder": {
            "title": "Public Funder",
            "party_role": ["Funder"],
            "parent_party": "parent-owner",
        },
        "private-owner": {
            "title": "Private Owner",
            "party_role": ["Owner"],
            "parent_party": "parent-owner",
        },
        "orphaned-owner": {
            "title": "Orphaned Owner",
            "party_role": "Owner, Funder",
            "parent_party": "parent-manufacturer",
        },
        "parent-manufacturer": {
            "title": "Parent Manufacturer",
            "party_role": ["Manufacturer"],
        },
        "public-manufacturer": {
            "title": "Public Manufacturer",
            "party_role": ["Manufacturer"],
            "parent_party": "parent-manufacturer",
        },
        "private-manufacturer": {
            "title": "Private Manufacturer",
            "party_role": ["Manufacturer"],
            "parent_party": "parent-manufacturer",
        },
        "applied-spectra": {
            "title": "Applied Spectra",
            "party_role": ["Manufacturer"],
            "parent_party": "parent-manufacturer",
        },
    }

    def fake_get_action(name):
        assert name == "package_search"
        def _search(ctx, data):
            user_name = getattr(ctx.get("auth_user_obj"), "name", None) or ctx.get("user")
            include_private = data.get("include_private") is True
            visible = []
            for record in records:
                if not record.get("private"):
                    visible.append(record)
                elif include_private and user_name in record.get("allowed_users", []):
                    visible.append(record)

            if data.get("facet") == "true":
                assert data["facet.field"] == ["vocab_manufacturer_party"]
                return _facet_items_for_visible_records(ctx, data, records)

            assert data.get("fl") == (
                "id,name,vocab_owner_party,vocab_funder_party,"
                "validated_data_dict"
            )
            return {"count": len(visible), "results": visible}
        return _search

    monkeypatch.setattr(views.toolkit, "get_action", fake_get_action)
    monkeypatch.setattr(views, "_load_all_party_metadata", lambda: parties)
    monkeypatch.setattr(views, "_party_cache_get", lambda key: None)
    monkeypatch.setattr(views, "_party_cache_set", lambda key, value: None)

    owner_nodes, manufacturer_nodes = views._build_party_trees("false", {"user": None})

    owner_counts = {node["id"]: node["count"] for node in owner_nodes}
    manufacturer_counts = {node["id"]: node["count"] for node in manufacturer_nodes}
    assert owner_counts == {
        "parent-owner": 0,
        "public-owner": 1,
        "public-funder": 1,
        "private-owner": 0,
        "orphaned-owner": 0,
    }
    owner_parent_ids = {node["id"]: node["parent_id"] for node in owner_nodes}
    assert owner_parent_ids["orphaned-owner"] is None
    assert "applied-spectra" not in owner_counts
    assert manufacturer_counts == {
        "Parent Manufacturer": 0,
        "Public Manufacturer": 1,
        "Private Manufacturer": 0,
        "Applied Spectra": 1,
    }

    owner_nodes, manufacturer_nodes = views._build_party_trees(
        "false",
        {"user": "alice", "auth_user_obj": _User("alice")},
    )

    owner_counts = {node["id"]: node["count"] for node in owner_nodes}
    manufacturer_counts = {node["id"]: node["count"] for node in manufacturer_nodes}
    assert owner_counts == {
        "parent-owner": 0,
        "public-owner": 1,
        "public-funder": 1,
        "private-owner": 1,
        "orphaned-owner": 0,
    }
    assert manufacturer_counts == {
        "Parent Manufacturer": 0,
        "Public Manufacturer": 1,
        "Private Manufacturer": 1,
        "Applied Spectra": 1,
    }


def test_parse_party_roles_handles_stored_role_strings():
    assert views._parse_party_roles({"party_role": "Owner, Funder"}) == [
        "owner",
        "funder",
    ]
    assert views._parse_party_roles({"party_role": '["Owner", "Manufacturer"]'}) == [
        "owner",
        "manufacturer",
    ]


def test_owner_party_filter_targets_owner_and_funder_fields_only():
    parties = {
        "curtin-university": {"title": "Curtin University"},
        "arc": {"title": "Australian Research Council"},
    }

    fq = views._build_owner_funder_party_fq(
        ["curtin-university", "arc"],
        parties,
    )

    assert fq.startswith("+(")
    assert 'vocab_owner_party:"Curtin University"' in fq
    assert 'vocab_funder_party:"Curtin University"' in fq
    assert 'vocab_owner_party:"Australian Research Council"' in fq
    assert 'vocab_funder_party:"Australian Research Council"' in fq
    assert 'groups:' not in fq
    assert 'vocab_manufacturer_party:' not in fq
