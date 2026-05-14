# Quick Reference: Analytics Events

## Event Taxonomy

All event names are defined as `EVENT_*` constants in `analytics.py` and as `EVENTS.*` in `analytics-tracking.js`. Names must be used exactly as shown.

### Conversion Events

| Event Name | Source | Core Properties |
|---|---|---|
| `Search` | Backend | `search_term`, `search_keywords`, `search_context`, `result_count`, `is_empty`, `dataset_type?`, `page_number?`, `sort_by?` |
| `Empty-Result Search` | Backend | same as `Search`; fires only when `result_count == 0` |
| `Search Result Click-Through` | Frontend JS | `result_position`, `dataset_id?`, `dataset_type?`, `search_term?` |
| `Dataset Page View` | Frontend JS | `dataset_id`, `dataset_type`, `is_public`, `has_doi` |
| `Resource Preview Opened` | Frontend JS | `dataset_id`, `dataset_type?`, `resource_id?`, `resource_format?` |
| `Download` | Frontend JS | `resource_id?`, `dataset_id?`, `resource_format`, `dataset_type?`, `file_size_group` |
| `Time To First Download` | Frontend JS | `dataset_id?`, `dataset_type?`, `resource_id?`, `resource_format?`, `seconds_to_download` |
| `Dataset View Duration` | Frontend JS (sendBeacon) | `dataset_id`, `dataset_type`, `is_public`, `has_doi`, `duration_seconds` |

### Stewardship Events

| Event Name | Source | Core Properties |
|---|---|---|
| `Dataset Created` | Backend | `dataset_id`, `dataset_type`, `is_public`, `has_doi` |
| `Update Existing Dataset` | Backend | `dataset_id`, `dataset_type`, `is_public`, `has_doi` |
| `Dataset Published With DOI` | Backend | `dataset_id`, `dataset_type`, `is_public`, `has_doi`, `doi_status` |
| `Dataset Reuse Created` | Backend | `dataset_id`, `dataset_type`, `is_public`, `has_doi`, `reuse_type`, `source_dataset_id?` |
| `DOI-Based Citation` | Frontend JS (proxy) | `dataset_id?`, `dataset_type?`, `is_public?`, `citation_source` |

### Not Implemented

| Metric | Reason |
|---|---|
| Download Completion | Client-side detection unreliable; requires server-side CKAN download route override |
| Dataset Withdrawn | Planned; not yet implemented |
| DOI-Based Citation (real) | Requires DataCite Event Data API polling; current event is a proxy (link click) |

## Allowed Properties

| Property | Type | Description |
|---|---|---|
| `dataset_id` | string (UUID) | CKAN package UUID |
| `dataset_type` | `'instrument'` \| `'platform'` \| `'unknown'` | Derived from `is_platform` field |
| `is_public` | boolean \| null | Derived from `private` field (`!pkg.private`) |
| `has_doi` | boolean | True when a non-empty DOI value is present |
| `search_term` | string | The query string submitted |
| `result_count` | integer | Number of results returned |
| `is_empty` | boolean | True when `result_count == 0` |
| `result_position` | integer | 1-based rank in the search results list |
| `resource_id` | string (UUID) | CKAN resource UUID |
| `resource_format` | string | File format label (e.g. `CSV`) |
| `file_size_group` | `'small'` \| `'medium'` \| `'large'` \| `'unknown'` | Bucketed from raw bytes; raw value never sent |
| `duration_seconds` | integer | Page view duration, capped at 1800 s, minimum 2 s |
| `seconds_to_download` | integer | Time from dataset page load to first download click |
| `doi_status` | `'published'` \| `'minted'` \| `'none'` \| `'unknown'` | From `_doi_status_from_db()` |
| `source_dataset_id` | string (UUID) | Predecessor package UUID for `Dataset Reuse Created` |
| `reuse_type` | `'new_version'` | Always `'new_version'` for the current workflow |
| `citation_source` | `'doi_link_click'` | Always this value; DOI-Based Citation is proxy-only |
| `page_number` | integer | Page number in search results (backend only) |
| `sort_by` | string | Sort parameter (backend only) |
| `search_keywords` | string[] | Cleaned flat list of search term + active filter values. Each entry is lowercased, with hyphens/underscores replaced by spaces. Capped at 20 entries, 100 chars each. Empty when no term and no filters. |
| `search_context` | string | Pipe-joined summary of search term + filter values. Format: `"seismometer \| sensor"` or `"no search term \| geophysics"`. Values only — no internal field names. Never contains PII, URLs, IDs, or DOIs. |
| `user_type` | `'anonymous'` \| `'logged_in'` | Injected automatically; use to segment all events by auth state |

## Never Send

The following must never appear in any event payload:

- `email`, `username`, `display_name`
- `dataset_title`, `dataset_name`, `name`, `title`
- `resource_name`, `resource_title`
- `doi` (full DOI identifier)
- `size_bytes` (raw file size)
- `description`, `notes`
- `url` (full page URL)
- `organization_id`, `owner_org`

## Example Payloads

### Search
```json
{
  "event": "Search",
  "properties": {
    "search_term": "seismometer",
    "result_count": 14,
    "is_empty": false,
    "dataset_type": "instrument",
    "page_number": 1,
    "sort_by": "score desc"
  }
}
```

### Dataset Page View
```json
{
  "event": "Dataset Page View",
  "properties": {
    "dataset_id": "3f8a2b1c-4d5e-6f7a-8b9c-0d1e2f3a4b5c",
    "dataset_type": "instrument",
    "is_public": true,
    "has_doi": true
  }
}
```

### Download
```json
{
  "event": "Download",
  "properties": {
    "resource_id": "res-uuid",
    "dataset_id": "pkg-uuid",
    "resource_format": "CSV",
    "dataset_type": "instrument",
    "file_size_group": "small"
  }
}
```

### Dataset Published With DOI
```json
{
  "event": "Dataset Published With DOI",
  "properties": {
    "dataset_id": "pkg-uuid",
    "dataset_type": "instrument",
    "is_public": true,
    "has_doi": true,
    "doi_status": "published"
  }
}
```

### Dataset Reuse Created
```json
{
  "event": "Dataset Reuse Created",
  "properties": {
    "dataset_id": "new-uuid",
    "dataset_type": "instrument",
    "is_public": false,
    "has_doi": false,
    "reuse_type": "new_version",
    "source_dataset_id": "original-uuid"
  }
}
```

## User Identity

### user_id resolution

| User type | Frontend | Backend |
|---|---|---|
| Logged-in | `rudderanalytics.identify(ckanUUID)` — UUID only, no traits | `get_analytics_user_id()` returns the CKAN internal user UUID |
| Anonymous | `rudderanalytics.identify(browserId)` — stable cookie UUID | `get_analytics_user_id()` returns the `pidinst_browser_id` cookie UUID |

### user_type property

Every event — backend and frontend — carries a `user_type` property that
identifies whether the action was performed by an authenticated or anonymous
user.  It is injected automatically by `AnalyticsTracker.track()` (backend)
and by `AnalyticsTracker.track()` (frontend JS) so individual event helpers
never need to set it explicitly.

| Value | Meaning |
|---|---|
| `'logged_in'` | A CKAN user is authenticated in the current request / browser session |
| `'anonymous'` | No authenticated user; the stable `pidinst_browser_id` browser UUID is used as the identity |

`user_type` is a label string — it never contains an email, username, UUID,
or any other PII.

### Amplitude segmentation examples

- **Compare engagement**: `user_type = logged_in` vs `user_type = anonymous` on any event chart.
- **Funnel by auth state**: filter the Search → Dataset Page View → Download funnel to `user_type = anonymous` to measure anonymous discovery-to-download conversion.
- **Stewardship actions**: `Dataset Created` is always `user_type = logged_in` in practice; `user_type = anonymous` there would indicate a misconfigured public endpoint.

## Metric Coverage

| Metric | Status |
|---|---|
| Search | ✅ Implemented (backend) |
| Empty-Result Search | ✅ Implemented (backend) |
| Search Result Click-Through | ✅ Implemented (frontend) |
| Dataset Page View | ✅ Implemented (frontend) |
| Resource Preview Opened | ✅ Implemented (frontend) |
| Download | ✅ Implemented (frontend) |
| Time To First Download | ✅ Implemented (frontend) |
| Dataset View Duration | ✅ Implemented (frontend sendBeacon) |
| Dataset Created | ✅ Implemented (backend) |
| Update Existing Dataset | ✅ Implemented (backend) |
| Dataset Published With DOI | ✅ Implemented (backend, transition-detected) |
| Dataset Reuse Created | ✅ Implemented (backend) |
| DOI-Based Citation | ⚠️ Proxy only (link click) |
| Download Completion | ❌ Not implemented |
| Dataset Withdrawn | ❌ Not implemented |
| Unique / Returning Visitors | ⚠️ Partial — RudderStack built-in anonymous ID |
| Average Engagement Time | ⚠️ Partial — `Dataset View Duration` per page; session average from platform |

## Funnel Queries

### Download Conversion
```
1. Search
2. Search Result Click-Through
3. Dataset Page View
4. Download
```

### Stewardship Pipeline
```
1. Dataset Created
2. Update Existing Dataset  (0..N times)
3. Dataset Published With DOI
```

### Reuse Detection
```
1. Dataset Created (ordinary)
2. Dataset Reuse Created (new version — both fire together)
```
