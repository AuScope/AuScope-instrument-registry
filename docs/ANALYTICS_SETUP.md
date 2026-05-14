# Analytics Tracking Setup Guide

## Overview

This analytics implementation tracks user interactions for conversion and stewardship metrics using RudderStack. Event data is forwarded to a downstream analytics destination (e.g. Amplitude, Mixpanel, or a data warehouse).

Event tracking is split between the backend (Python/RudderStack SDK) and the frontend (RudderStack JS SDK). Neither layer sends PII — no email, username, display name, dataset title, resource name, or raw DOI value is included in any event payload.

## Implemented Events

### Conversion Events

| Event Name | Source | Trigger |
|---|---|---|
| `Search` | Backend | After successful `package_search` in `_instrument_platform_search` |
| `Empty-Result Search` | Backend | Same call when `result_count == 0` |
| `Search Result Click-Through` | Frontend JS | User clicks a search result heading |
| `Dataset Page View` | Frontend JS | Dataset detail page loads |
| `Resource Preview Opened` | Frontend JS | User clicks a resource view / explore link |
| `Download` | Frontend JS | User clicks a download link |
| `Time To First Download` | Frontend JS | First download click per dataset page load |
| `Dataset View Duration` | Frontend JS (sendBeacon) | User navigates away from dataset page |

### Stewardship Events

| Event Name | Source | Trigger |
|---|---|---|
| `Dataset Created` | Backend | `after_dataset_create` hook |
| `Update Existing Dataset` | Backend | `after_dataset_update` hook (user edits only) |
| `Dataset Published With DOI` | Backend | First DOI publication transition detected |
| `Dataset Reuse Created` | Backend | `after_dataset_create` when a new version is created |
| `DOI-Based Citation` | Frontend JS (proxy) | User clicks a DOI badge or link |

### Not Implemented

- **Download Completion** — client-side completion detection is unreliable. Requires a server-side CKAN download route override. Not implemented.
- **Dataset Withdrawn** — planned; not yet implemented.
- **DOI-Based Citation (real)** — the JS event above is a proxy (link click intent). Real citation detection requires the DataCite Event Data API. Not implemented.

## Configuration

### Environment Variables

Add to your `.env` file:

```bash
RUDDERSTACK_ENABLED=true
RUDDERSTACK_WRITE_KEY=your_write_key_here
RUDDERSTACK_DATA_PLANE_URL=https://your-rudderstack-dataplane.example.com
```

When `RUDDERSTACK_ENABLED` is not `true`, all backend events are silently dropped and the JS snippet is not injected into the page.

### Docker Setup

```bash
# Install Python SDK (already in requirements.txt — rebuild the image)
docker compose -f docker-compose.dev.yml build ckan-dev
docker compose -f docker-compose.dev.yml up -d ckan-dev
```

### Verify Setup

```bash
./check-analytics-setup.sh
```

## API Endpoints

These endpoints receive browser-originated events and relay them to RudderStack via the backend SDK. All endpoints require a valid JSON body and a whitelisted event name.

### POST /api/analytics/track

Relay a frontend event to RudderStack. The `event` field must match a known event name.

```json
{
  "event": "Dataset View Duration",
  "properties": {
    "dataset_id": "3f8a2b1c-...",
    "dataset_type": "instrument",
    "is_public": true,
    "has_doi": false,
    "duration_seconds": 45
  }
}
```

### POST /api/analytics/resource-download

Track a resource download. Raw file size is bucketed server-side; `size_bytes` is not stored.

```json
{
  "resource_id": "res-uuid",
  "dataset_id": "pkg-uuid",
  "resource_format": "CSV",
  "size_bytes": 1048576,
  "dataset_type": "instrument"
}
```

### POST /api/analytics/search

Track a search event (primarily called from views.py backend). Can also be used for manual testing.

```json
{
  "search_term": "climate sensor",
  "result_count": 12
}
```

> **Note:** `search_keywords` and `search_context` are derived automatically by the backend from
> the CKAN request parameters when called from `views.py`. They are not currently accepted via
> this HTTP endpoint.

## Search Keywords Analytics

### How it works

When a user performs a search on `/instruments` or `/platforms`, the backend view handler
(`_instrument_platform_search` in `views.py`) collects all active facet/filter selections into a
`fields_grouped` dict. Before firing the `Search` (and `Empty-Result Search`) analytics event,
`analytics.extract_filter_values(fields_grouped)` is called to produce a flat list of selected
filter values. These, combined with the search term, are passed to `build_search_keywords()` and
`build_search_context()` to produce the event payload.

### Filter field whitelist

Only the following CKAN facet fields contribute filter values to analytics events. All other request
parameters (including `fq`, `q`, `id`, `owner_org`, and any unknown field) are silently ignored.

| CKAN internal field | Description |
|---|---|
| `vocab_instrument_type_gcmd` | GCMD instrument type |
| `vocab_instrument_type_custom` | Custom instrument type |
| `vocab_measured_variable_gcmd` | GCMD measured variable |
| `vocab_measured_variable_custom` | Custom measured variable |
| `vocab_instrument_classification` | Instrument classification |
| `vocab_manufacturer_party` | Manufacturer |
| `owner_party` | Owner / funder party |

### Example Search event payload (with filters)

```json
{
  "search_term": "seismometer",
  "search_keywords": ["seismometer", "seismometer", "seismic waveforms"],
  "search_context": "seismometer | seismometer | seismic waveforms",
  "result_count": 4,
  "is_empty": false,
  "dataset_type": "instrument",
  "page_number": 1,
  "sort_by": "score desc, metadata_modified desc"
}
```

### `search_keywords` property

A cleaned, deduplicated flat list of all active search keywords — the search term followed by
any active filter values. Used to enable Amplitude's "group by array property" feature.

**Cleaning rules applied to each value:**
- Lowercased
- Leading/trailing whitespace stripped
- Hyphens and underscores replaced with spaces
- Multiple consecutive spaces collapsed

**Bounds:** capped at `_KEYWORD_MAX_COUNT` entries (default 20); each entry capped at
`_KEYWORD_MAX_LEN` characters (default 100). Duplicates (case-insensitive) are removed.

### `search_context` property

A single derived string joining the search term and active filter values with ` | `. Designed
for Amplitude chart grouping — each distinct combination becomes a row in a frequency table.

**Format:** values only — no internal CKAN field names appear.

| Scenario | Example value |
|---|---|
| Term only | `"seismometer"` |
| Term + one filter | `"seismometer \| sensor"` |
| Term + multiple filters | `"seismometer \| sensor \| seismic waveforms"` |
| Filters only | `"no search term \| geophysics"` |
| Neither term nor filters | `"no search term"` |

**Safety:** only values that passed through `extract_filter_values()` (i.e. from the whitelist)
can appear. URLs, package IDs, org IDs, usernames, emails, and DOIs never appear.

### Example Amplitude charts

#### Top search terms
- **Chart type:** Bar chart
- **Event:** `Search`
- **Group by:** `search_term`
- **Insight:** Most common raw search queries.

#### Top search keywords
- **Chart type:** Bar chart
- **Event:** `Search`
- **Group by:** `search_keywords` (explode array property)
- **Insight:** Most common terms + filter values across all searches.

#### Top search contexts (search_context)
- **Chart type:** Table or horizontal bar chart
- **Event:** `Search`
- **Metric:** Event count (or unique users)
- **Group by:** `search_context`
- **Insight:** Most common combinations of search term + filter selections at a glance.

#### Empty-result searches by context
- **Chart type:** Table
- **Event:** `Empty-Result Search`
- **Columns:** `search_term`, `search_keywords`, `search_context`
- **Insight:** Which term + filter combinations yield no results (potential vocabulary gaps).

## File Structure

```
ckan/src/ckanext-pidinst-theme/
├── ckanext/pidinst_theme/
│   ├── analytics.py                  # Backend: AnalyticsTracker, event helpers, constants
│   ├── analytics_views.py            # Backend: /api/analytics/* relay endpoints
│   ├── assets/js/
│   │   └── analytics-tracking.js    # Frontend: all JS event tracking
│   ├── templates/
│   │   ├── base.html                 # Injects RudderStack snippet; sets PIDINST_ANALYTICS_USER_ID
│   │   └── package/
│   │       ├── read_base.html        # data-* attributes on dataset page wrapper
│   │       └── snippets/
│   │           ├── package_item.html # data-dataset-id / data-dataset-type on search results
│   │           └── resource_item.html # data-id, data-resource-format on resource rows
│   └── tests/
│       └── test_analytics.py        # 203+ unit tests covering all implemented events
docs/
├── ANALYTICS_IMPLEMENTATION_PLAN.md # Full implementation history and metric coverage
├── ANALYTICS_QUICK_REFERENCE.md     # Event taxonomy and payload reference
└── ANALYTICS_SETUP.md               # This file
```

## Privacy

- Authenticated users: identified by their stable internal CKAN UUID only (`window.PIDINST_ANALYTICS_USER_ID` in JS; `get_safe_analytics_user_id()` in Python). No email, username, or display name is sent.
- Anonymous users: identified only by RudderStack's built-in anonymous ID. `identify()` is never called for anonymous visitors.
- All event payloads are reviewed against the allowed-properties list. Title, name, description, organisation membership, raw file size, and full DOI value are never sent.

## Troubleshooting

### Events not appearing in RudderStack

1. Check environment variables:
   ```bash
   docker compose exec ckan-dev env | grep RUDDERSTACK
   ```

2. Check CKAN container logs:
   ```bash
   docker compose -f docker-compose.dev.yml logs -f ckan-dev | grep -i analytics
   ```

3. Open browser DevTools → Network tab, filter by `api/analytics` or `rudderstack`.

4. Verify the JS SDK is loaded:
   ```javascript
   typeof window.rudderanalytics   // should be "object"
   typeof window.CKANAnalytics     // should be "object"
   ```

### Backend events not tracked

Ensure `rudder-sdk-python` is installed in the container:
```bash
docker compose exec ckan-dev pip show rudder-sdk-python
```

If missing, add `rudder-sdk-python` to `ckan/src/requirements.txt` and rebuild.

## Troubleshooting

### Events Not Tracking

1. **Check if RudderStack is loaded:**
   ```javascript
   console.log(typeof rudderanalytics);
   // Should output: "object"
   ```

2. **Check environment variables:**
   ```bash
   docker compose exec ckan-dev env | grep RUDDERSTACK
   ```

3. **Check logs:**
   ```bash
   docker compose logs -f ckan-dev | grep -i analytics
   ```

### Backend Events Not Tracking

1. **Verify Python SDK is installed:**
   ```bash
   docker compose exec ckan-dev pip list | grep rudderstack
   ```

2. **Check Python logs:**
   ```python
   import logging
   logging.getLogger('ckanext.pidinst_theme.analytics').setLevel(logging.DEBUG)
   ```

## Funnel Analysis in Amplitude/Mixpanel

### Example Funnel: Download Conversion

1. Search
2. Search Result Click-Through
3. Dataset Page View
4. Resource Download Click
5. Download Completion

### Example Funnel: DOI Publication

1. Dataset Created
2. Dataset Page View (by creator)
3. Dataset Published with DOI

## Best Practices

1. **User Privacy**: Ensure compliance with privacy policies
2. **Event Naming**: Keep event names consistent
3. **Properties**: Include relevant context in properties
4. **Testing**: Test events in development before production
5. **Monitoring**: Regularly check analytics dashboards

## Support

For issues or questions:
1. Check browser console for errors
2. Review Docker logs
3. Verify RudderStack configuration
4. Check Amplitude/Mixpanel event debugger
