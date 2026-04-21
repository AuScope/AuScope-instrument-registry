# Creating Solr-searchable fields for CKAN composite/repeating object lists

This note explains how to make CKAN fields searchable in Solr when the original data is stored as a list of objects, for example:

- `manufacturer` -> list of objects containing `manufacturer_name`
- `model` -> list of objects containing `model_name`
- `alternate_identifier_obj` -> list of objects containing `alternate_identifier`

A common pattern is to create derived search-only fields such as:

- `manufacturer_name_search`
- `model_name_search`
- `alternate_identifier_search`

These fields are flattened before indexing so Solr can query them reliably.

---

## Why this is needed

In CKAN, composite repeating fields are often stored as JSON-like structures, not as simple top-level searchable text fields.

Example source shape:

```python
{
    "manufacturer": [
        {
            "manufacturer_party_id": "abc",
            "manufacturer_name": "Phoenix Geophysics"
        }
    ]
}
```

If you try to query `manufacturer_name:"Phoenix Geophysics"` directly, it may fail because `manufacturer_name` is nested inside a list of objects and was never flattened into a Solr-searchable field.

---

## Recommended approach

Create dedicated flattened search fields during indexing.

Do not overwrite the original business fields. Instead, add separate derived fields such as:

- `manufacturer_name_search`
- `model_name_search`
- `alternate_identifier_search`

This is cleaner because:

- it avoids collisions with real schema fields
- it avoids confusion between stored metadata and search-only data
- it avoids Solr field-type surprises
- it makes maintenance easier

---

## Important Solr rule

If your Solr field is not multi-valued, do not assign a Python list to it.

This will fail:

```python
pkg_dict["alternate_identifier_search"] = ["SN-000099", "ALT-123"]
```

with an error like:

```text
multiple values encountered for non multiValued field alternate_identifier_search
```

Use a single flattened string instead:

```python
pkg_dict["alternate_identifier_search"] = " | ".join(["SN-000099", "ALT-123"])
```

---

## CKAN plugin hook

For CKAN 2.10+ / 2.11, use:

```python
def before_dataset_index(self, pkg_dict):
```

Older versions used `before_index`.

Your plugin should implement `IPackageController`.

---

## Example implementation

```python
import json
import logging

log = logging.getLogger(__name__)

def before_dataset_index(self, pkg_dict):
    def _load_list(value):
        if not value:
            return []
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except Exception:
                return []
        return value if isinstance(value, list) else []

    manufacturers = _load_list(pkg_dict.get("manufacturer"))
    manufacturer_names = [
        item.get("manufacturer_name")
        for item in manufacturers
        if isinstance(item, dict) and item.get("manufacturer_name")
    ]
    pkg_dict["manufacturer_name_search"] = " | ".join(manufacturer_names)

    models = _load_list(pkg_dict.get("model"))
    model_names = [
        item.get("model_name")
        for item in models
        if isinstance(item, dict) and item.get("model_name")
    ]
    pkg_dict["model_name_search"] = " | ".join(model_names)

    alternate_ids_obj = _load_list(pkg_dict.get("alternate_identifier_obj"))
    alternate_ids = [
        item.get("alternate_identifier")
        for item in alternate_ids_obj
        if isinstance(item, dict) and item.get("alternate_identifier")
    ]
    pkg_dict["alternate_identifier_search"] = " | ".join(alternate_ids)

    return pkg_dict
```

---

## How it works

### 1. Load the source field safely

Composite/repeating fields may come through as:

- a Python list
- a JSON string
- empty / null

The helper converts them into a safe list:

```python
def _load_list(value):
    if not value:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            return []
    return value if isinstance(value, list) else []
```

### 2. Extract the target subfield

For example:

- from each `manufacturer` object, extract `manufacturer_name`
- from each `model` object, extract `model_name`
- from each `alternate_identifier_obj` object, extract `alternate_identifier`

### 3. Flatten to a single string

Join the collected values into one string:

```python
" | ".join(values)
```

This makes the field safe for a normal non-multivalued Solr text field.

---

## Why use `_search` suffix

Using `_search` makes it obvious that the field is derived and not part of the canonical data model.

Good:

- `manufacturer_name_search`
- `model_name_search`
- `alternate_identifier_search`

Less ideal:

- `manufacturer_name`
- `model_name`
- `alternate_identifier`

The `_search` suffix helps avoid accidental conflicts with:

- schema-defined metadata fields
- future fields added to your dataset schema
- Solr field mappings that may already exist

---

## Rebuild steps

After adding or changing indexing logic:

1. rebuild your CKAN image/container if needed
2. restart CKAN
3. rebuild the search index

Typical command inside the CKAN container:

```bash
ckan -c /path/to/ckan.ini search-index rebuild
```

If needed, first enter the container:

```bash
docker ps
docker exec -it <container_name> bash
```

or with Docker Compose:

```bash
docker compose exec ckan bash
```

---

## How to query the new fields

Example search:

```python
ckan_client.action.package_search(
    q='*:*',
    fq='type:instrument AND manufacturer_name_search:"Phoenix Geophysics"',
    rows=100,
)
```

Another example:

```python
ckan_client.action.package_search(
    q='model_name_search:"MTU-5C" AND alternate_identifier_search:"SN-000099"',
    fq='type:instrument',
    rows=100,
)
```

---

## Important limitation

Quoted Solr/Lucene field search is phrase matching, not strict whole-field equality.

So this query:

```python
title:"Example Instrument"
```

can still match:

- `Example Instrument`
- `Example Instrument [2026-03-13]`

because the field contains that phrase.

If you need true exact matching, do a second validation pass in Python after the Solr search.

---

## Recommended search pattern

For best results:

1. use Solr on the `_search` fields to narrow the candidate set
2. validate the original composite fields in Python for exact equality

This gives you:

- good search performance
- reliable matching
- no need to force exact business logic into Solr text search

---

## Example validation pattern

```python
import json

def _load_list(value):
    if not value:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            return []
    return value if isinstance(value, list) else []

manufacturers = _load_list(pkg.get("manufacturer"))
manufacturer_match = any(
    (item.get("manufacturer_name") or "").strip() == manufacturer.strip()
    for item in manufacturers
    if isinstance(item, dict)
)
```

Use the same pattern for model and alternate identifier.

---

## Troubleshooting checklist

### Hook not running
For CKAN 2.11, make sure you used:

```python
def before_dataset_index(self, pkg_dict):
```

not `before_index`.

### Solr multi-value error
If you see:

```text
multiple values encountered for non multiValued field ...
```

you are still assigning a list instead of a string.

Fix by changing:

```python
pkg_dict["some_search_field"] = values
```

to:

```python
pkg_dict["some_search_field"] = " | ".join(values)
```

### Search returns nothing
Check whether the field actually exists in Solr by querying and requesting it in the results.

Example:

```python
ckan_client.action.package_search(
    q='*:*',
    fq='type:instrument',
    fl='name,title,manufacturer_name_search,model_name_search,alternate_identifier_search',
    rows=5,
)
```

If the field is missing, the indexing hook may not be running or the index may not have been rebuilt.

---

## Suggested conventions

- Keep original composite fields untouched
- Add dedicated `_search` fields only for indexing/querying
- Flatten values into a single string
- Rebuild the search index after changes
- Validate exact matches in Python if needed

---

## Suggested naming convention

| Source field | Nested value | Search field |
|---|---|---|
| `manufacturer` | `manufacturer_name` | `manufacturer_name_search` |
| `model` | `model_name` | `model_name_search` |
| `alternate_identifier_obj` | `alternate_identifier` | `alternate_identifier_search` |

---

## Final recommendation

For CKAN composite/repeating fields that are lists of objects:

- do not query nested subfields directly unless you know they are already indexed
- flatten them in `before_dataset_index`
- store them in dedicated `_search` fields
- make the flattened values single strings, not lists
- use Solr to narrow matches, then validate in Python if exactness matters
