# ckanext-taxonomy — Integration Guide

[ckanext-taxonomy](https://github.com/NaturalHistoryMuseum/ckanext-taxonomy) adds a first-class **Taxonomy** (and **TaxonomyTerm**) model to CKAN, letting you define controlled vocabularies that can be attached to datasets, organizations, or groups via the scheming extension.

---

## Project Setup

| What | Where |
|------|-------|
| Installation | `Dockerfile` / `Dockerfile.dev` — `pip install ckanext-taxonomy` (via GitHub) |
| Plugin name | `taxonomy` (added to `CKAN__PLUGINS` in `.env`) |
| DB init | Startup scripts (`start_ckan.sh.override` / `start_ckan_development.sh.override`) call `ckan taxonomy initdb` |
| Default seeds | Same startup scripts create the three default taxonomies on first boot |

### Default seeded taxonomies

| Name | Title |
|------|-------|
| `instrument` | Instrument |
| `platform` | Platform |
| `measured_variable` | Measured Variable |

---

## CLI Commands Cheat Sheet

All commands require a running CKAN config (inside the Docker container):

```sh
export CKAN_INI=/srv/app/ckan.ini
```

| Command | Description |
|---------|-------------|
| `ckan -c $CKAN_INI taxonomy initdb` | Create taxonomy DB tables (run once on first start) |
| `ckan -c $CKAN_INI taxonomy load <file.json>` | Load / update a taxonomy from a JSON file |

### JSON format for `taxonomy load`

```json
{
  "name": "instrument",
  "title": "Instrument",
  "uri": "https://example.com/vocab/instrument",
  "terms": [
    {
      "label": "Mass Spectrometer",
      "uri": "https://example.com/vocab/instrument/mass-spectrometer",
      "broader": null
    },
    {
      "label": "Seismometer",
      "uri": "https://example.com/vocab/instrument/seismometer",
      "broader": null
    }
  ]
}
```

Run the load command:

```sh
ckan -c $CKAN_INI taxonomy load /path/to/instrument.json
```

---

## API Actions Cheat Sheet

Base URL: `http://localhost:5000/api/3/action/`

All write operations require an `Authorization` header with a CKAN API token.

### Taxonomy actions

| Action | Method | Key Parameters | Description |
|--------|--------|---------------|-------------|
| `taxonomy_list` | GET | — | List all taxonomies |
| `taxonomy_show` | GET | `id` (name or UUID) | Get a single taxonomy |
| `taxonomy_create` | POST | `name`, `title`, `uri` *(opt)* | Create a new taxonomy |
| `taxonomy_update` | POST | `id`, `name` *(opt)*, `title` *(opt)* | Update a taxonomy |
| `taxonomy_delete` | POST | `id` | Delete a taxonomy and all its terms |

### Taxonomy term actions

| Action | Method | Key Parameters | Description |
|--------|--------|---------------|-------------|
| `taxonomy_term_list` | GET | `taxonomy_id` | List all terms in a taxonomy |
| `taxonomy_term_show` | GET | `id` (UUID) | Get a single term |
| `taxonomy_term_create` | POST | `taxonomy_id`, `label`, `uri` *(opt)*, `parent_id` *(opt)* | Create a term |
| `taxonomy_term_update` | POST | `id`, `label` *(opt)*, `uri` *(opt)* | Update a term |
| `taxonomy_term_delete` | POST | `id` | Delete a term |

---

## curl Examples

### Taxonomy CRUD

```sh
CKAN_URL=http://localhost:5000
API_KEY=<your-api-token>

# List all taxonomies
curl -s "$CKAN_URL/api/3/action/taxonomy_list" | python3 -m json.tool

# Show a specific taxonomy by name
curl -s "$CKAN_URL/api/3/action/taxonomy_show?id=instrument" | python3 -m json.tool

# Create a new taxonomy
curl -s -X POST "$CKAN_URL/api/3/action/taxonomy_create" \
  -H "Authorization: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "sensor_type", "title": "Sensor Type"}' | python3 -m json.tool

# Update a taxonomy
curl -s -X POST "$CKAN_URL/api/3/action/taxonomy_update" \
  -H "Authorization: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"id": "sensor_type", "title": "Sensor Types"}' | python3 -m json.tool

# Delete a taxonomy
curl -s -X POST "$CKAN_URL/api/3/action/taxonomy_delete" \
  -H "Authorization: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"id": "sensor_type"}' | python3 -m json.tool
```

### Taxonomy term CRUD

```sh
# List terms in a taxonomy
curl -s "$CKAN_URL/api/3/action/taxonomy_term_list?taxonomy_id=instrument" | python3 -m json.tool

# Create a term
curl -s -X POST "$CKAN_URL/api/3/action/taxonomy_term_create" \
  -H "Authorization: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "taxonomy_id": "instrument",
    "label": "Mass Spectrometer",
    "uri": "https://example.com/vocab/instrument/mass-spectrometer"
  }' | python3 -m json.tool

# Show a specific term (use UUID returned by create/list)
curl -s "$CKAN_URL/api/3/action/taxonomy_term_show?id=<term-uuid>" | python3 -m json.tool

# Update a term
curl -s -X POST "$CKAN_URL/api/3/action/taxonomy_term_update" \
  -H "Authorization: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"id": "<term-uuid>", "label": "Mass Spectrometer (MS)"}' | python3 -m json.tool

# Delete a term
curl -s -X POST "$CKAN_URL/api/3/action/taxonomy_term_delete" \
  -H "Authorization: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"id": "<term-uuid>"}' | python3 -m json.tool
```

---

## Python API Examples (inside a CKAN plugin or script)

```python
import ckan.plugins.toolkit as toolkit

context = {'ignore_auth': True}

# List all taxonomies
taxonomies = toolkit.get_action('taxonomy_list')(context, {})

# Show a taxonomy
taxonomy = toolkit.get_action('taxonomy_show')(context, {'id': 'instrument'})

# Create a taxonomy
toolkit.get_action('taxonomy_create')(context, {
    'name': 'sensor_type',
    'title': 'Sensor Type',
})

# Add a term
toolkit.get_action('taxonomy_term_create')(context, {
    'taxonomy_id': 'instrument',
    'label': 'Mass Spectrometer',
    'uri': 'https://example.com/vocab/instrument/mass-spectrometer',
})
```

---

## Using Taxonomies in Scheming Schemas

Reference a taxonomy field in `instrument_schema.yaml` (or any scheming schema):

```yaml
- field_name: instrument_type
  label: Instrument Type
  preset: taxonomy_field         # provided by ckanext-taxonomy
  taxonomy: instrument           # name of the taxonomy to draw terms from
  form_snippet: taxonomy.html
  display_snippet: taxonomy.html
```

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `taxonomy` not recognized as a plugin | Extension not installed | Rebuild Docker image |
| `ProgrammingError: relation "taxonomy" does not exist` | `initdb` not run | Run `ckan -c $CKAN_INI taxonomy initdb` |
| Default taxonomies missing after first boot | Seeding script failed silently | Check container logs for `Warning: Could not seed taxonomies` and re-run the Python seed block manually |
| `ObjectNotFound` on `taxonomy_show` | Taxonomy name typo or not seeded | Run `taxonomy_list` to see what exists |
