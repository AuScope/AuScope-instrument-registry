# AuScope Data Repository — Analytics Implementation Plan

**Date:** 2026-05-12  
**Scope:** ckanext-pidinst-theme analytics review and implementation roadmap  
**Goal:** Conversion and advocacy/stewardship metrics for the AuScope Data Repository

---

## Stage Progress

| Stage | Description | Status |
|---|---|---|
| Stage 1 | Foundation cleanup — event constants, minimal props, privacy, duplicate prevention, suppression, tests | ✅ Complete |
| Stage 2A | Search analytics — backend `Search` + `Empty-Result Search` events from `_instrument_platform_search` | ✅ Complete |
| Stage 2B | User interaction analytics — Search Result Click-Through improved, Resource Preview Opened | ✅ Complete |
| Stage 2C | Dataset engagement timing — Dataset View Duration (sendBeacon), Time To First Download verified/fixed | ✅ Complete |
| Stage 3A | Dataset Published With DOI — correct transition detection (first-mint-only) | ✅ Complete |
| Stage 3B | Dataset Reuse Created — `after_dataset_create` new-version detection | ✅ Complete |
| Stage 3D | Identity alignment — unified UUID-based user identity across frontend and backend | ✅ Complete |
| Stage 3C | DataCite citation polling, Dataset Withdrawn | ⏳ Planned |
| Stage 4 | PR readiness — code cleanup, documentation rewrite, dashboard readiness | ✅ Complete |

### Stage 1 Summary (Completed)

The following changes were implemented and verified (75/75 tests passing):

| Change | File | Details |
|---|---|---|
| Added 11 `EVENT_*` constants | `analytics.py` | `EVENT_SEARCH`, `EVENT_EMPTY_RESULT_SEARCH`, `EVENT_SEARCH_RESULT_CLICK_THROUGH`, `EVENT_DATASET_PAGE_VIEW`, `EVENT_DOWNLOAD`, `EVENT_TIME_TO_FIRST_DOWNLOAD`, `EVENT_DATASET_CREATED`, `EVENT_DATASET_PUBLISHED_WITH_DOI`, `EVENT_UPDATE_EXISTING_DATASET`, `EVENT_DOI_BASED_CITATION`, `EVENT_RESOURCE_PREVIEW_OPENED` |
| Added `minimal_dataset_props()` helper | `analytics.py` | Returns `{dataset_id, dataset_type, is_public, has_doi}` only — no title, name, email, org |
| Added `file_size_group()` helper | `analytics.py` | Buckets bytes into `'small'`/`'medium'`/`'large'`/`'unknown'`; raw bytes never sent |
| Renamed `track_doi_created` → `track_doi_published` | `analytics.py` | Old function removed; TODO marker added for Stage 3 transition logic |
| Fixed PII in `identify()` | `base.html` | Removed `email`, `display_name`, `username`, `created` traits; sends only `user_id` |
| Removed duplicate page-view + XSS | `read_base.html` | Removed inline `<script>` (had unescaped `{{ pkg.title }}`); added `data-*` attributes on wrapper `<div>` |
| Rewrote JS tracking module | `analytics-tracking.js` | `EVENTS` constants object; single `Dataset Page View` source; no form tracking; `Download` → `file_size_group` only; removed fake 1s setTimeout `Download Completion` |
| Added `_analytics_suppress` flag | `plugin.py` | Prevents spurious `Update Existing Dataset` from internal `package_patch` on create |
| Fixed API endpoint robustness | `analytics_views.py` | All three endpoints return 400 on missing/invalid JSON body instead of 500 |
| Expanded test suite | `tests/test_analytics.py` | 4 → 75 tests; 10 test classes covering constants, helpers, PII, file-size buckets, suppression, event names |

---

## 1. Current Analytics State (Post-Stage-1)

The codebase has a cleaned-up analytics layer built around RudderStack.  
Stage 1 foundation work is complete. The following table reflects the **current** state.

| Component | Location | Status |
|---|---|---|
| Backend `AnalyticsTracker` class | `analytics.py` | ✅ Working |
| 11 `EVENT_*` constants | `analytics.py` | ✅ Added in Stage 1 |
| `minimal_dataset_props()` helper | `analytics.py` | ✅ Added in Stage 1; returns `{dataset_id, dataset_type, is_public, has_doi}` only |
| `file_size_group()` helper | `analytics.py` | ✅ Added in Stage 1; buckets bytes → `small`/`medium`/`large`/`unknown` |
| `track_dataset_created` helper | `analytics.py` | ✅ Implemented, called from `plugin.py` |
| `track_dataset_updated` helper | `analytics.py` | ✅ Implemented, called from `plugin.py` |
| `track_doi_published` helper | `analytics.py` | ✅ Fixed (Stage 3A) — fires only on confirmed transition from not-published to published; uses `_doi_status_from_db()` helper |
| `_doi_status_from_db()` helper | `analytics.py` | ✅ Added (Stage 3A) — queries `DOIQuery.read_package()`; returns `(is_published, status_str)`; never returns raw DOI identifier |
| `track_dataset_search` helper | `analytics.py` | ✅ Implemented; exposed via `/api/analytics/search`; uses `search_term`/`result_count`/`is_empty` |
| `track_resource_download` helper | `analytics.py` | ✅ Implemented; uses `file_size_group`; no raw bytes or resource name in payload |
| `/api/analytics/track` endpoint | `analytics_views.py` | ✅ Generic frontend → backend relay; returns 400 on empty body |
| `/api/analytics/resource-download` endpoint | `analytics_views.py` | ✅ Accepts `size_bytes`, `dataset_type`; no `resource_name`; returns 400 on empty body |
| `/api/analytics/search` endpoint | `analytics_views.py` | ✅ Accepts `search_term`/`result_count` (with legacy `query`/`num_results` fallbacks); returns 400 on empty body |
| RudderStack JS snippet injection | `helpers.py` → `base.html` | ✅ Working, gated by `RUDDERSTACK_ENABLED` |
| Frontend tracking module | `assets/js/analytics-tracking.js` | ✅ Rewritten in Stage 1; single source for each event; `EVENTS` constants object |
| Dataset page view tracking | `templates/package/read_base.html` | ✅ Fixed in Stage 1; single JS source via `data-*` attributes on wrapper `<div>` |
| Resource item download links | `templates/package/snippets/resource_item.html` | ✅ Has `resource-url-analytics` class and `data-*` attributes |
| User identify call | `templates/base.html` | ✅ Fixed in Stage 1; sends only `user_id`; no PII |
| Event name consistency | `analytics.py` + `analytics-tracking.js` | ✅ All events use `EVENT_*` constants; JS `EVENTS` object matches Python constants |
| `_analytics_suppress` flag | `plugin.py` | ✅ Added in Stage 1; prevents spurious `Update Existing Dataset` on create's `package_patch` |
| Test suite | `tests/test_analytics.py` | ✅ 201 tests, 19 test classes (Stage 3D added 25 tests) |
| Anonymous / session ID | `analytics-tracking.js` | ⚠️ `sessionStorage`-based session ID exists but not correlated with backend events |
| Bot filtering | Anywhere | ❌ Not implemented |
| Search tracking on filter change | Frontend JS | ❌ No tracking on facet click, pagination, or filter-only reloads — planned Stage 2 |
| Resource preview tracking | Anywhere | ❌ Not implemented — planned Stage 2 |
| Dataset-reuse / new-version tracking | Anywhere | ❌ Not implemented — planned Stage 3 |
| DOI citation tracking | Anywhere | ⚠️ JS monitors DOI badge link clicks only as proxy (`DOI-Based Citation`); real DataCite API polling planned Stage 3 |
| Acquisition channel / referrer | Frontend | ⚠️ Not currently sent in events |

---

## 2. Workflow Map

### 2.1 Instrument / Platform Search Pages

| Step | Route | Handler | Template |
|---|---|---|---|
| Load search page | `GET /instruments` or `GET /platforms` | `views._instrument_platform_search()` | `instruments/search.html` → extends `package/search.html` |
| Apply facets / pagination | Same route, query params update | Same handler | Same template |
| Enter keyword and submit form | Form `submit` event | JS `initSearchTracking()` | Search form in CKAN core |
| Click a result heading | `click` on `.dataset-item a` | JS `initSearchTracking()` | `snippets/package_list.html` |

**Analytics gaps (remaining after Stage 1):** No server-side search tracking. No tracking on facet-click, pagination, or filter changes. No empty-result detection. All planned for Stage 2.

---

### 2.2 Dataset Detail / Read Pages

| Step | Route | Handler | Template |
|---|---|---|---|
| View instrument page | `GET /instrument/<name>` | CKAN core `instrument.read` | `package/read.html` → extends `package/read_base.html` |
| DOI decoration | `after_dataset_show` in `ckanext-doi` | Adds `doi`, `doi_status`, `doi_date_published` to `pkg_dict` | Shown in read template |

**Analytics notes (post-Stage-1):** Duplicate page-view fixed; XSS removed; single JS source via `data-*` attributes. No remaining open issues on this page.

---

### 2.3 Resource Preview and Download

| Step | Route | Handler | Template |
|---|---|---|---|
| Open resource explore dropdown | Client side | — | `package/snippets/resource_item.html` |
| Click "Go to resource" | External link | — | Same; has `resource-url-analytics` class |
| Click "Download" | `GET /instrument/<name>/resource/<id>/download` | CKAN core `instrument_resource.download` | Same |
| Backend analytics POST | JS `Resource Download Click` event → `POST /api/analytics/resource-download` | `analytics_views.track_resource_download` | — |

**Analytics notes (post-Stage-1):** `Download` event fires on click with `{resource_format, resource_id, dataset_id, dataset_type, file_size_group}` — no raw bytes or resource_name. `Time To First Download` fires correctly on first click in session. Fake 1-second `Download Completion` setTimeout removed. Resource preview tracking still missing — planned Stage 2.

---

### 2.4 Dataset Create / Update Lifecycle

| Step | Route / Hook | Handler | Analytics call |
|---|---|---|---|
| Create instrument | `POST /instrument/new` | CKAN core → `after_dataset_create` in `plugin.py` | `analytics.track_dataset_created(user, pkg_dict)` |
| Update instrument | `POST /instrument/<name>/edit` | CKAN core → `after_dataset_update` in `plugin.py` | `analytics.track_dataset_updated(user, pkg_dict)` |
| Create new version | `GET/POST /instrument/<id>/new_version` | `views.new_version()` → eventually redirects to `instrument.new` → hooks fire as normal | No dedicated tracking; fires create hook as normal |

**Analytics notes (post-Stage-3A):** `Dataset Created` fires correctly from `after_dataset_create`. Spurious `Update Existing Dataset` on create's internal `package_patch` is suppressed via `_analytics_suppress = True`. `Dataset Published With DOI` now fires only on confirmed DOI publication transition — see Stage 3A section for full details.

---

### 2.5 DOI Creation / Publishing Lifecycle

| Step | Where it happens | Analytics call |
|---|---|---|
| DOI record created in DB | `ckanext-doi` `after_dataset_create` → `DOIQuery.read_package(create_if_none=True)` | None in pidinst-theme at this stage |
| DOI minted and published | `ckanext-doi` `after_dataset_update` → `client.mint_doi()` (only when `doi.published is None`) | **None from ckanext-doi**; pidinst-theme's `before_dataset_update` snapshots old `doi.published` state; `after_dataset_update` queries current state via `_doi_status_from_db()` and fires `track_doi_published` only on transition |
| DOI metadata updated | `ckanext-doi` `after_dataset_update` → `client.set_metadata()` | **No event** — DOI was already published; `was_published=True` guard suppresses re-fire |
| DOI shown on page | `after_dataset_show` → adds to `pkg_dict` | — |

**Analytics notes (post-Stage-3A):** `track_doi_published` now fires only when the DOI transitions from not-published (`doi.published is None`) to published (`doi.published` set to a datetime). The `before_dataset_update` hook snapshots the old DOI state; `after_dataset_update` compares via `analytics._doi_status_from_db()`. Requires `pidinst_theme` to be listed **after** `doi` in `ckan.plugins` so ckanext-doi's mint runs before our hook reads the new state.

---

### 2.6 Versioning / Reuse / Provenance

| Step | Route | Handler |
|---|---|---|
| Start new version | `GET /instrument/<id>/new_version` | `views.new_version()` |
| Confirm / save new version | `POST /instrument/new` via standard form | CKAN core create → `after_dataset_create` fires |
| Relationship stored | `related_identifier_obj` field | Schema-level; `relation_type: IsNewVersionOf` |

**Analytics gaps:** There is no tracking of "Dataset Reuse Created" at any point. The `_is_new_version` flag exists in `session['package_new_version_data']` but is consumed only by the template and is no longer accessible inside `after_dataset_create`.

---

### 2.7 Frontend Templates and JavaScript Summary

| File | Purpose | Analytics involvement |
|---|---|---|
| `base.html` | Base layout, loads RudderStack snippet and identifies user | ⚠️ Sends PII: email, display name |
| `package/read_base.html` | Dataset page base | ⚠️ Duplicate page-view, XSS risk |
| `package/read.html` | Instrument detail page | Extends read_base |
| `package/snippets/resource_item.html` | Resource download/explore links | ✅ `data-*` attrs present |
| `instruments/search.html` / `platforms/search.html` | Search pages | Extends `package/search.html`; no analytics hooks |
| `assets/js/analytics-tracking.js` | Frontend tracking module | ⚠️ Bundled in webassets; several issues below |

---

## 3. Metric Coverage Table

Event names reflect the Stage 1 constants (`EVENT_*` in `analytics.py`, `EVENTS` in `analytics-tracking.js`).

| Metric | Required? | Status | Existing File / Location | Recommended Tracking Location | Event Name | Key Properties |
|---|---|---|---|---|---|---|
| Search performed | Yes (Conversion) | ✅ Implemented (Stage 2A) | `views._instrument_platform_search()` after `package_search` | Backend (current) | `Search` | `search_term`, `result_count`, `is_empty`, `dataset_type?`, `page_number?`, `sort_by?` |
| Empty-result search | Yes (Conversion) | ✅ Implemented (Stage 2A) | Same as above, fires when `result_count == 0` | Backend (current) | `Empty-Result Search` | `search_term`, `result_count`, `is_empty: true`, `dataset_type?`, `page_number?`, `sort_by?` |
| Search result click-through | Yes (Conversion) | ✅ Improved (Stage 2B) — now sends `dataset_id`, `dataset_type` from `data-*` attrs; dedup guard added | JS `initSearchTracking()` | JS click handler (current) | `Search Result Click-Through` | `dataset_id?`, `dataset_type?`, `result_position`, `search_term?` |
| Dataset page view | Yes (Conversion) | ✅ Implemented (Stage 1 fixed duplicate) | JS `trackDatasetPageView()` via `data-*` attrs in `read_base.html` | JS module only (current) | `Dataset Page View` | `dataset_id`, `dataset_type`, `is_public`, `has_doi` |
| Resource preview opened | Yes (Conversion) | ✅ Implemented (Stage 2B) | JS `initResourcePreviewTracking()` on `.resource-item` links to resource view pages | JS click handler (current) | `Resource Preview Opened` | `dataset_id`, `dataset_type?`, `resource_id?`, `resource_format?` |
| Resource download | Yes (Conversion) | ✅ Implemented (Stage 1 cleaned) | JS `initDownloadTracking()` → POST `/resource-download` | JS click + server-side download route (Stage 2 for server-side) | `Download` | `resource_id`, `dataset_id`, `resource_format`, `dataset_type`, `file_size_group` |
| Time to first download | Yes (Conversion) | ✅ Fixed (Stage 2C) — property name corrected to `seconds_to_download`; timing now measured from dataset page load; `dataset_type` + `resource_format` added | JS `initDownloadTracking()` | JS (current) | `Time To First Download` | `dataset_id?`, `dataset_type?`, `resource_id?`, `resource_format?`, `seconds_to_download` |
| Download split by size | Yes (Conversion) | ✅ Implemented (Stage 1) | `file_size_group()` helper; included in `Download` event | Current | `Download` → `file_size_group` property | `'small'`/`'medium'`/`'large'`/`'unknown'` |
| Download completion | Yes (Conversion) | ❌ Removed (fake impl removed in Stage 1) | Was 1s setTimeout — removed | Server-side CKAN download route (Stage 2) | Not yet assigned | — |
| Dataset created | Yes (Advocacy) | ✅ Implemented | `plugin.py` `after_dataset_create` | Backend hook (keep); Stage 3: add `is_new_version` | `Dataset Created` | `dataset_id`, `dataset_type`, `is_public`, `has_doi` |
| Dataset updated | Yes (Advocacy) | ✅ Implemented (Stage 1 suppression fixed) | `plugin.py` `after_dataset_update` | Backend hook (current) | `Update Existing Dataset` | `dataset_id`, `dataset_type`, `is_public`, `has_doi` |
| Dataset published with DOI | Yes (Advocacy) | ✅ Fixed (Stage 3A) — fires only when confirmed transition from not-published to published | `plugin.py` `before_dataset_update` snapshots old state; `after_dataset_update` compares via `_doi_status_from_db()` | Backend hook (current) | `Dataset Published With DOI` | `dataset_id`, `dataset_type`, `is_public`, `has_doi`, `doi_status` |
| DOI citation detected | Yes (Advocacy) | ⚠️ Proxy only — JS DOI link click | JS `initDOITracking()` on `.doi-badge`, `[data-doi] a`, `a[href*="doi.org"]` | DataCite Event Data API (Stage 3) | `DOI-Based Citation` | `dataset_id`, `dataset_type`, `is_public`, `citation_source: 'doi_link_click'` |
| Dataset reuse created | Yes (Advocacy) | ✅ Implemented (Stage 3B) | `plugin.py` `after_dataset_create`; `analytics.track_dataset_reuse_created()` | Backend hook (current) | `Dataset Reuse Created` | `dataset_id`, `dataset_type`, `is_public`, `has_doi`, `reuse_type`, `source_dataset_id?` |
| Unique / returning visitors | Secondary | ⚠️ Partial — RudderStack JS auto-generates anonymous ID | RudderStack JS SDK | RudderStack built-in | — | RudderStack built-in |
| Average engagement time | Secondary | ✅ Covered (Stage 2C) — `Dataset View Duration` sendBeacon; Amplitude/RudderStack auto-computes session average from this | JS `initDatasetViewDurationTracking()` | JS sendBeacon on visibilitychange + pagehide | `Dataset View Duration` | `dataset_id`, `dataset_type`, `is_public`, `has_doi`, `duration_seconds` |

---

## 4. Event Taxonomy

All event names are defined as `EVENT_*` constants in `analytics.py` and as `EVENTS.*` in `analytics-tracking.js`.  
Properties use `snake_case`. Events marked ✅ are implemented; ⚠️ partial/proxy; ❌ not yet.

### 4.1 Conversion Events

| Event Name | Status | Trigger | Core Properties |
|---|---|---|---|
| `Search` | ✅ Backend | `_instrument_platform_search` after `package_search` | `search_term`, `result_count`, `is_empty`, `dataset_type?`, `page_number?`, `sort_by?` |
| `Empty-Result Search` | ✅ Backend | Same; fires when `result_count == 0` | same as `Search` |
| `Search Result Click-Through` | ✅ JS improved (Stage 2B) | User clicks a result title | `dataset_id?`, `dataset_type?`, `result_position`, `search_term?` |
| `Dataset Page View` | ✅ JS | Dataset detail page renders | `dataset_id`, `dataset_type`, `is_public`, `has_doi` |
| `Resource Preview Opened` | ✅ JS (Stage 2B) | User clicks a resource-view link on the dataset page | `dataset_id`, `dataset_type?`, `resource_id?`, `resource_format?` |
| `Download` | ✅ JS | User clicks download on a resource | `resource_id?`, `dataset_id?`, `resource_format`, `dataset_type?`, `file_size_group` |
| `Time To First Download` | ✅ JS fixed (Stage 2C) | First download click in session | `dataset_id?`, `dataset_type?`, `resource_id?`, `resource_format?`, `seconds_to_download` |
| `Dataset View Duration` | ✅ JS (Stage 2C) | User leaves/hides dataset page | `dataset_id`, `dataset_type`, `is_public`, `has_doi`, `duration_seconds` |

### 4.2 Advocacy / Stewardship Events

| Event Name | Status | Trigger | Core Properties |
|---|---|---|---|
| `Dataset Created` | ✅ Backend | `after_dataset_create` hook | `dataset_id`, `dataset_type`, `is_public`, `has_doi` |
| `Update Existing Dataset` | ✅ Backend | `after_dataset_update` hook (non-automated) | `dataset_id`, `dataset_type`, `is_public`, `has_doi` |
| `Dataset Published With DOI` | ✅ Fixed (Stage 3A) | `after_dataset_update` — only on confirmed not-published → published transition | `dataset_id`, `dataset_type`, `is_public`, `has_doi`, `doi_status` |
| `Dataset Reuse Created` | ✅ Implemented (Stage 3B) | `after_dataset_create` when `version_handler_id != id` (new-version workflow) | `dataset_id`, `dataset_type`, `is_public`, `has_doi`, `reuse_type`, `source_dataset_id?` |
| `DOI-Based Citation` | ⚠️ Proxy only | JS click on DOI link / badge | `dataset_id`, `dataset_type`, `is_public`, `citation_source: 'doi_link_click'` |

### 4.3 Planned Events (Not Yet Implemented)

| Event Name | Planned Stage | Trigger |
|---|---|---|
| `DOI-Based Citation` (real detection) | Stage 3C | DataCite Event Data API polling |
| `Dataset Withdrawn` | Stage 3C | `views.withdraw()` success |

### 4.4 Common Property Schema

Every event includes these base properties where available:

```
user_id       – CKAN user ID (authenticated users only; omit for anonymous)
dataset_id    – CKAN package UUID
dataset_type  – 'instrument' | 'platform' | 'unknown'
is_public     – True | False | None (derived from pkg.private)
has_doi       – True | False (bool, not the raw DOI value)
```

---

## 5. Implementation Plan by Stage

### Stage 1 — Foundation and Cleanup ✅ COMPLETE

All items below were implemented and verified (75/75 tests passing, no lint errors).

1. ✅ **Centralised event name constants** — 11 `EVENT_*` constants in `analytics.py`; matching `EVENTS` object in `analytics-tracking.js`.
2. ✅ **`minimal_dataset_props()` helper** — returns `{dataset_id, dataset_type, is_public, has_doi}` only; used by all tracking helpers.
3. ✅ **`file_size_group()` helper** — buckets raw bytes into `'small'`/`'medium'`/`'large'`/`'unknown'`; raw bytes never sent.
4. ✅ **Fixed PII in `identify()` call** — removed `email`, `display_name`, `username`, `created` from `base.html`; sends `user_id` only.
5. ✅ **Fixed XSS and duplicate page-view in `read_base.html`** — removed inline `<script>` block; replaced with `data-dataset-id`, `data-dataset-type`, `data-is-public` attributes on wrapper `<div>`.
6. ✅ **Renamed `track_doi_created` → `track_doi_published`** — old function removed; payload uses `minimal_dataset_props` + `doi_status`; no raw DOI value sent. Full transition logic (first-mint-only) deferred to Stage 3 with TODO comment.
7. ✅ **Added `_analytics_suppress` flag** in `plugin.py` — prevents spurious `Update Existing Dataset` from internal `package_patch` call during dataset creation.
8. ✅ **Rewrote `analytics-tracking.js`** — `EVENTS` constants; single `Dataset Page View` source; removed `initFormTracking()` (was duplicating backend events); removed fake 1-second setTimeout `Download Completion`; `file_size_group` property on `Download`; `DOI-Based Citation` documented as proxy-only.
9. ✅ **Fixed API endpoint robustness** — all three endpoints in `analytics_views.py` return 400 on missing/invalid JSON body.
10. ✅ **Expanded test suite** — 4 → 75 tests across 10 classes covering constants, helpers, PII, file-size buckets, suppression, event names, search params.

---

### Stage 2A — Search Analytics ✅ COMPLETE

1. ✅ **Backend `Search` event** — `analytics.track_dataset_search()` called in `_instrument_platform_search()` after `package_search` returns successfully.  Properties: `search_term`, `result_count`, `is_empty`, plus optional `dataset_type`, `page_number`, `sort_by`.
2. ✅ **`Empty-Result Search` event** — fires from the same call inside `track_dataset_search` when `result_count == 0`. Same properties as `Search`.
3. ✅ **Frontend duplicate removed** — form-submit `EVENTS.SEARCH` handler removed from `analytics-tracking.js`; backend is now the single source of truth. `Search Result Click-Through` is unaffected.
4. ✅ **Failure safety** — tracking wrapped in `try/except` in `_instrument_platform_search`; failure logs a warning and does not affect the search response.
5. ✅ **Tests** — 13 new tests covering: event fires, required properties, no PII, optional properties, empty-result gate, shared props for empty-result, anonymous user, failure safety pattern.

### Stage 2B — User Interaction Analytics ⚠️ Partially Complete

1. ✅ **Search Result Click-Through improved** — `initSearchTracking()` now reads `dataset_id` and
   `dataset_type` from `data-dataset-id` / `data-dataset-type` attributes on the
   `.dataset-item-wrapper` element (added to `snippets/package_item.html`). A dedup guard
   (`data-analytics-click-tracked` marker) prevents double-binding. The `try/catch` inside the
   click handler ensures tracking failure never blocks navigation.
   - **Files changed:** `assets/js/analytics-tracking.js`, `templates/snippets/package_item.html`
   - **Payload:** `{ dataset_id?, dataset_type?, result_position, search_term? }` — no title, name, URL, facets

2. ✅ **Resource Preview Opened implemented** — `initResourcePreviewTracking()` added to
   `analytics-tracking.js`. Active on dataset read pages only (requires
   `[data-module="dataset-view"]` wrapper). Tracks clicks on:
   - `.resource-item a.heading` links (`resource_item_short.html`)
   - `.resource-item [href*="/resource/"]` links (CKAN Explore dropdown)
   Resource ID is read from `.resource-item[data-id]` or extracted from the href. Format is read
   from `[data-resource-format]` on the explore wrapper or `[data-format]` on the format label.
   - **Files changed:** `assets/js/analytics-tracking.js`
   - **Payload:** `{ dataset_id, dataset_type?, resource_id?, resource_format? }` — no resource name, dataset name, raw URL

3. ⏳ **Dataset View Duration** — ✅ Implemented (Stage 2C). See Stage 2C section below.

4. ⏳ **Download completion reliability** — not implemented. Client-side completion detection is
   fundamentally unreliable. Best practical approach: override CKAN's download view at the
   `instrument_resource.download` route, stream the file, and fire a server-side event after
   the response is sent.

**Tests added (Stage 2B):** 10 new tests in 4 classes (`TestStage2BEventNames`,
`TestSearchResultClickThroughPayload`, `TestResourcePreviewOpenedPayload`,
`TestStage2BFailureSafety`). All existing tests continue to pass.

---

### Stage 2C — Dataset Engagement Timing ✅ Complete

1. ✅ **`EVENT_DATASET_VIEW_DURATION` constant added** — `analytics.py` and `EVENTS` object in
   `analytics-tracking.js`. Value: `'Dataset View Duration'`.

2. ✅ **`KNOWN_FRONTEND_EVENTS` frozenset added to `analytics.py`** — used by the
   `/api/analytics/track` endpoint as a whitelist. Prevents unknown event names from being
   relayed. Defined in `analytics.py` (not `analytics_views.py`) so it is testable without Flask.

3. ✅ **`/api/analytics/track` endpoint hardened** — now returns 400 for event names not in
   `KNOWN_FRONTEND_EVENTS`. Existing 400-on-missing-body behaviour unchanged.

4. ✅ **`Dataset View Duration` tracking implemented** — `initDatasetViewDurationTracking()` in
   `analytics-tracking.js`. Active on dataset read pages only (requires `[data-module="dataset-view"]` wrapper).
   - Records `pageStart = Date.now()` at page load.
   - Fires at most once per page view (`fired` boolean guard).
   - Triggers on `visibilitychange` (hidden) and `pagehide` — both required for tab switch, link
     navigation, back/forward, and page close.
   - Ignores durations < 2 s (accidental loads); caps at 1800 s (30 min).
   - Sends via `navigator.sendBeacon` with `new Blob([…], { type: 'application/json' })` to
     ensure correct `Content-Type` for Flask's `request.get_json()`.
   - Falls back to `fetch(…, { keepalive: true })` if `sendBeacon` is unavailable.
   - All errors are caught; tracking failure never affects page navigation.
   - **Payload:** `{ dataset_id, dataset_type, is_public, has_doi, duration_seconds }` — no title,
     name, URL, email, username, or raw DOI value.

5. ✅ **`Time To First Download` verified and fixed** — `initDownloadTracking()` in
   `analytics-tracking.js`:
   - **Bug fixed:** property name was `time_to_download_seconds` (wrong). Now `seconds_to_download`.
   - **Bug fixed:** timing used `session_start` (start of browsing session). Now uses
     `datasetPageLoadTime = Date.now()` captured at `initDownloadTracking()` execution, which is
     the dataset page load time.
   - **Added:** `dataset_type` and `resource_format` to TTFD payload when available.
   - Session gate (`has_downloaded` in `sessionStorage`) unchanged — fires at most once per session.
   - **Payload:** `{ dataset_id?, dataset_type?, resource_id?, resource_format?, seconds_to_download }`.

**Tests added (Stage 2C):** 26 new tests in 4 classes:
- `TestStage2CEventNames` (2 tests) — event name constant values
- `TestDatasetViewDurationPayload` (12 tests) — payload shape, duration_seconds present, no PII
- `TestTimeToFirstDownloadPayload` (8 tests) — correct property name, minimal payload, no banned props
- `TestAnalyticsTrackEndpointValidation` (4 tests) — KNOWN_FRONTEND_EVENTS whitelist coverage

**Total test count after Stage 2C: 127 tests, all passing.**

**Not implemented in Stage 2C (by design):**
- Download Completion (`Resource Download Completed`) — unreliable browser-side; deferred
- DOI-Based Citation (real detection) — DataCite API polling; deferred Stage 3B
- Dataset Reuse Created — deferred Stage 3B

---

### Stage 3A — Dataset Published With DOI (Transition Fix) ✅ COMPLETE

**Problem:** The previous implementation fired `Dataset Published With DOI` on every dataset update where a `doi` field happened to be present in the raw `pkg_dict`. This caused the event to fire repeatedly on any edit of a dataset with an existing published DOI.

**Root cause:** The guard `if pkg_dict.get('doi'):` only checks whether the DOI *string* is in the package dict — it does not check whether the DOI was *just* published for the first time.

**Fix implemented:**

1. **`analytics._doi_status_from_db(package_id)`** — new helper that queries `DOIQuery.read_package()` from ckanext-doi and returns a `(is_published: bool, status_str: str)` tuple:
   - `(True, 'published')` — `doi.published` timestamp is set
   - `(False, 'minted')` — DOI record exists but not yet published
   - `(False, 'none')` — no DOI record for this package
   - `(False, 'unknown')` — ckanext-doi unavailable or DB error
   The raw DOI identifier is never returned.

2. **`plugin.py before_dataset_update()`** — new hook that snapshots the DOI published state *before* the update runs. Stores `True`/`False`/`None` in `context['_analytics_doi_was_published']`. `None` means unknown (DB error) — treated conservatively.

3. **`plugin.py after_dataset_update()`** — the old `if pkg_dict.get('doi'):` guard is replaced by:
   ```python
   was_published = context.get('_analytics_doi_was_published')
   if was_published is False:
       is_now_published, doi_status = analytics._doi_status_from_db(pkg_id)
       if is_now_published:
           analytics.track_doi_published(user, pkg_dict, doi_status=doi_status)
   ```
   Only fires when `was_published is False` (confirmed not published before) AND `is_now_published is True`. Conservative: `was_published=None` skips the event.

**Transition detection rule:**

| `was_published` | `is_now_published` | Event fires? | Reason |
|---|---|---|---|
| `False` | `True` | ✅ Yes | First DOI publication — correct transition |
| `True` | `True` | ❌ No | DOI already published before this update |
| `False` | `False` | ❌ No | DOI not published yet (minted only, or none) |
| `None` | `True` | ❌ No | Old state unknown — conservative, skip to avoid duplicates |

**Known limitation:** Requires `pidinst_theme` to be listed **after** `doi` in the `ckan.plugins` config value. This ensures ckanext-doi's `after_dataset_update` (which calls `client.mint_doi()` and sets `doi.published`) runs *before* our hook queries the DOI state. If `pidinst_theme` is listed before `doi`, the transition will not be detected because `doi.published` is not yet set when our hook runs.

**Event payload example:**
```json
{
  "dataset_id":   "3f8a2b1c-...",
  "dataset_type": "instrument",
  "is_public":    true,
  "has_doi":      true,
  "doi_status":   "published"
}
```
Properties **not** sent: `doi` (full identifier), `name`, `title`, `email`, `username`, `description`, or any other metadata.

**Files changed:**
- `ckan/src/ckanext-pidinst-theme/ckanext/pidinst_theme/analytics.py` — added `_doi_status_from_db()`; updated `track_doi_published` docstring; removed TODO marker
- `ckan/src/ckanext-pidinst-theme/ckanext/pidinst_theme/plugin.py` — added `before_dataset_update()` hook; replaced old guard in `after_dataset_update()`
- `ckan/src/ckanext-pidinst-theme/ckanext/pidinst_theme/tests/test_analytics.py` — 21 new tests in 3 classes

**Tests added (Stage 3A): 21 new tests — total now 150, all passing.**
- `TestDoiStatusFromDb` (5 tests) — `_doi_status_from_db`: published, minted-only, no record, DB exception, ImportError
- `TestStage3ADoiPublishedTransition` (11 tests) — transition fires/doesn't fire for each `(was_published, is_now_published)` combination; payload shape; PII exclusion; failure safety
- `TestStage3AContextSnapshot` (5 tests) — `before_dataset_update` stores correct `True`/`False`/`None` in context

**Not implemented in Stage 3A (by design):**
- DOI-Based Citation (real detection) — DataCite Event Data API polling → Stage 3C
- Dataset Reuse Created → Stage 3B (now complete)
- Dataset Withdrawn → Stage 3C
- No changes to Stage 1/2 behaviour

---

### Stage 3B — Dataset Reuse Created ✅ COMPLETE

**Problem:** There was no tracking of when a dataset is created as a new version of an existing one. The `after_dataset_create` hook fired `Dataset Created` for all new datasets, with no distinction between an ordinary create and a "Create New Version" workflow.

**Detection approach:**

The `new_version()` view in `views.py` calls `prepare_dataset_for_cloning()` which copies `version_handler_id` from the original dataset. For an ordinary create, `after_dataset_create` sets `version_handler_id = pkg_dict['id']` (self). For a new-version create, `version_handler_id` is already set to the root of the version chain (a different UUID) before `after_dataset_create` runs.

The rule: **`version_handler_id != pkg_dict['id']`** → this is a new version dataset.

For the `source_dataset_id`, `prepare_dataset_for_cloning()` adds an `IsNewVersionOf` entry to `related_identifier_obj` (a schema-level composite field that survives CKAN validation) containing `related_instrument_package_id` = the immediate predecessor's CKAN UUID.

**Fix implemented:**

1. **`EVENT_DATASET_REUSE_CREATED = 'Dataset Reuse Created'`** — added to constants block in `analytics.py`.

2. **`analytics._is_new_version_pkg(pkg_dict)`** — returns `True` when `version_handler_id` is set and differs from `pkg_dict['id']`. Safe and O(1).

3. **`analytics._reuse_source_from_pkg(pkg_dict)`** — parses `related_identifier_obj` (handles both list and JSON-string forms), finds the first `IsNewVersionOf` entry, returns `related_instrument_package_id`. Returns `None` on any error. The raw `related_identifier` DOI string is never returned.

4. **`analytics.track_dataset_reuse_created(user_id, dataset_dict, source_dataset_id=None)`** — builds `minimal_dataset_props` + `reuse_type='new_version'` + optional `source_dataset_id` and fires `EVENT_DATASET_REUSE_CREATED`.

5. **`plugin.py after_dataset_create()`** — after the existing `track_dataset_created` call, a new guarded block calls `_is_new_version_pkg()` and, if True, calls `track_dataset_reuse_created()` with the extracted `source_dataset_id`. Wrapped in `try/except` so failure never breaks dataset creation.

**Detection guard in `after_dataset_create`:**
```python
# Stage 3B: Dataset Reuse Created
try:
    if analytics._is_new_version_pkg(pkg_dict):
        source_id = analytics._reuse_source_from_pkg(pkg_dict)
        analytics.track_dataset_reuse_created(user, pkg_dict,
                                               source_dataset_id=source_id)
except Exception as e:
    logging.error(f"Failed to track dataset reuse creation: {e}")
```

**Event payload example:**
```json
{
  "dataset_id":        "4a9b3c2d-...",
  "dataset_type":      "instrument",
  "is_public":         false,
  "has_doi":           false,
  "reuse_type":        "new_version",
  "source_dataset_id": "1f2e3d4c-..."
}
```
Properties **not** sent: `doi`, `name`, `title`, `email`, `username`, `version_handler_id`, `related_identifier` (raw DOI), any other metadata.

**Both events fire for a new-version create:**
- `Dataset Created` — always fires for any new dataset (unchanged)
- `Dataset Reuse Created` — fires additionally when the new dataset is a version of an existing one

**Files changed:**
- `ckan/src/ckanext-pidinst-theme/ckanext/pidinst_theme/analytics.py` — added `EVENT_DATASET_REUSE_CREATED`; added `_is_new_version_pkg()`; added `_reuse_source_from_pkg()`; added `track_dataset_reuse_created()`
- `ckan/src/ckanext-pidinst-theme/ckanext/pidinst_theme/plugin.py` — added Stage 3B guard block in `after_dataset_create()`
- `ckan/src/ckanext-pidinst-theme/ckanext/pidinst_theme/tests/test_analytics.py` — 26 new tests in 3 classes

**Tests added (Stage 3B): 26 new tests — total now 176, all passing.**
- `TestIsNewVersionPkg` (5 tests) — `_is_new_version_pkg`: true when differs, false when same, false when absent/empty, false when id missing
- `TestReuseSourceFromPkg` (8 tests) — `_reuse_source_from_pkg`: extracts ID from list, from JSON string, ignores other relation types, None when absent/empty/no-pkg-id/invalid-JSON/no-doi-leak
- `TestStage3BDatasetReuseCreated` (13 tests) — fires for new version; does NOT fire for ordinary create; does NOT fire when vhid absent; `Dataset Created` still fires; payload required props; `source_dataset_id` included/absent; `reuse_type='new_version'`; no PII; `is_public` reflects `private`; failure safety; event name constant

**Not implemented in Stage 3B (by design):**
- DOI-Based Citation (real detection) → Stage 3C
- Dataset Withdrawn → Stage 3C
- No changes to Stage 1/2/3A behaviour

---

### Stage 3D — Identity Alignment ✅ COMPLETE

**Problem:** Frontend events (Dataset Page View, Download, Search Result Click-Through, etc.) and backend lifecycle events (Dataset Created, Update Existing Dataset, Dataset Published With DOI, Dataset Reuse Created) used different user identifiers for the same logged-in user:

- Frontend RudderStack `identify()` → `c.userobj.id` (internal CKAN UUID, e.g. `3f8a2b1c-…`)
- Backend plugin.py hooks → `context.get('user')` → a **username string** (e.g. `ckan_admin`)

This split one user journey across two different analytics identities, making funnel analysis and user-level metrics unreliable.

**Root cause:** CKAN's hook context stores `context['user']` as the username string, not the UUID. The UUID is available via `context['auth_user_obj'].id` (the model object) or by looking up the user by name.

**Fix implemented:**

1. **`analytics.get_safe_analytics_user_id(user_or_username)`** — new helper in `analytics.py`:
   - Accepts a CKAN `User` model object → returns `user.id` directly (no DB lookup).
   - Accepts a username string → calls `from ckan.model import User; User.by_name(username).id`.
   - Accepts `None` → returns `None` (anonymous users remain anonymous).
   - Returns `None` on any failure (user not found, DB error, ImportError) — analytics never block application flow.
   - **Never returns username, email, display name, or any PII.**

2. **`plugin.py` `after_dataset_create` and `after_dataset_update`** — updated to resolve the safe UUID before tracking:
   ```python
   user_id = analytics.get_safe_analytics_user_id(
       context.get('auth_user_obj') or context.get('user')
   )
   ```
   `auth_user_obj` is preferred (already a User object — no DB lookup). Falls back to the username string.

3. **`templates/base.html`** — refactored:
   - Removed the inline `rudderanalytics.identify()` call.
   - Now exposes `window.PIDINST_ANALYTICS_USER_ID = '{{ c.userobj.id }}'` (UUID only) when logged in.
   - Anonymous users: variable not set.

4. **`assets/js/analytics-tracking.js`** — added `initUserIdentity()`:
   - Called first inside `initializeTracking()`.
   - If `window.PIDINST_ANALYTICS_USER_ID` exists, calls `rudderanalytics.ready(function() { rudderanalytics.identify(analyticsUserId); })` with **no traits** — only the stable UUID.
   - If absent (anonymous visitor), `identify()` is NOT called — RudderStack assigns its own anonymous ID.

**Identity behaviour summary:**

| User type | `window.PIDINST_ANALYTICS_USER_ID` | RudderStack identify() called? | Backend `user_id` |
|---|---|---|---|
| Logged-in | Set to CKAN UUID | Yes — UUID only, no traits | Same CKAN UUID |
| Anonymous | Not set | No — RudderStack anonymous ID | `None` |

**Privacy notes:**
- Only the stable internal CKAN user UUID is sent in `identify()`. No traits (no email, no username, no display name, no organisation membership).
- Anonymous visitors are never forced into an identify call; RudderStack's built-in anonymous ID handles session tracking.
- Backend `get_safe_analytics_user_id()` never surfaces the username string to any analytics call.

**Already-correct paths (no change needed):**
- `analytics_views.py` endpoints — already used `current_user.id` (UUID) ✅
- `views.py` search tracking — already used `toolkit.c.userobj.id` (UUID) ✅

**Files changed:**
- `ckan/src/ckanext-pidinst-theme/ckanext/pidinst_theme/analytics.py` — added `get_safe_analytics_user_id()`
- `ckan/src/ckanext-pidinst-theme/ckanext/pidinst_theme/plugin.py` — `after_dataset_create` and `after_dataset_update` use `get_safe_analytics_user_id`
- `ckan/src/ckanext-pidinst-theme/ckanext/pidinst_theme/templates/base.html` — exposes `window.PIDINST_ANALYTICS_USER_ID`; removed inline `identify()` call
- `ckan/src/ckanext-pidinst-theme/ckanext/pidinst_theme/assets/js/analytics-tracking.js` — added `initUserIdentity()`; called first in `initializeTracking()`
- `ckan/src/ckanext-pidinst-theme/ckanext/pidinst_theme/tests/test_analytics.py` — 25 new tests in 3 classes

**Tests added (Stage 3D): 25 new tests — total now 201, all passing.**
- `TestGetSafeAnalyticsUserId` (13 tests) — None/empty input, User object path (no DB), username string path (mocked DB), not-found, DB exception, ImportError, never returns username/email
- `TestBackendLifecycleUserIdAlignment` (8 tests) — `track_dataset_created`, `track_dataset_updated`, `track_dataset_reuse_created`, `track_doi_published` all pass UUID as `user_id`; payload excludes `username` and `email`; anonymous (None) is valid
- `TestAnonymousIdentityNotForced` (4 tests) — `get_safe_analytics_user_id(None)` returns None; Search/Download analytics work with None user_id; `AnalyticsTracker.track` uses `anonymous_id` branch when `user_id=None`

**Manual verification steps (RudderStack / Amplitude):**
1. Log in as a CKAN user. Open a dataset page, then open the browser DevTools Network tab.
2. Find the call to `identify` — verify the userId matches the value in `window.PIDINST_ANALYTICS_USER_ID` (a UUID, not a username).
3. Perform a download. In RudderStack Live Events, verify the Download event's `userId` matches the identify UUID.
4. Edit the dataset. In RudderStack Live Events, verify the `Update Existing Dataset` backend event uses the same UUID.
5. Log out. Verify no `identify` call is made and events appear with `anonymousId` only.

---

### Stage 3C — Remaining Advocacy Metrics (⏳ Planned)

1. ✅ **`Dataset Created` (Stage 3B)** — fires for all creates (unchanged). `Dataset Reuse Created` fires additionally for new-version creates.

2. ✅ **DOI published tracking fixed (Stage 3A)** — implemented via `before_dataset_update` snapshot + `_doi_status_from_db()` comparison. See Stage 3A section above.

3. ✅ **Dataset Reuse Created (Stage 3B)** — fires from `after_dataset_create` when `version_handler_id != id`. See Stage 3B section above.

4. **Dataset Withdrawn tracking**: In `views.withdraw()`, after the successful `package_patch` call, fire `Dataset Withdrawn`.

5. **DOI Citation tracking** (external, optional):
   - DataCite provides the [Event Data API](https://support.datacite.org/docs/eventdata-guide) which records citation events. Implement a daily CKAN background job that polls for new citation events for the site's DOI prefix and fires `Dataset Citation Detected` events.
   - JS DOI badge click remains as a real-time proxy in the meantime.

---

### Stage 4 — PR Readiness ✅ COMPLETE

**Changes made:**

1. **Fixed `AnalyticsTracker.track()` dict mutation** — `analytics.py`: the method previously mutated the caller's `properties` dict in-place (adding `timestamp` and `environment`). Changed to `props = dict(properties)` before mutation. Prevented a subtle bug where calling `track()` twice with the same dict (Search + Empty-Result Search) would carry forward extra keys.

2. **Removed dead `initSessionTracking()` in JS** — `analytics-tracking.js`: the function created `session_id` and `session_start` values in `sessionStorage` but these were never read by any event handler. Removed the function and its call from `initializeTracking()`.

3. **Rewrote `docs/ANALYTICS_SETUP.md`** — Replaced stale content (wrong event names, PII in example payloads, bogus "Download Completion" claim) with accurate setup guide covering current events, correct API payloads, and privacy rules.

4. **Rewrote `docs/ANALYTICS_QUICK_REFERENCE.md`** — Full replacement: correct event names, allowed-properties table, example payloads, metric coverage table, identity summary, and funnel examples.

5. **Rewrote `docs/README_ANALYTICS.md`** — Replaced stale overview (wrong event names, wrong file references) with concise current summary linking to the detailed docs.

6. **Updated Stage Progress table** — This file: Stage 4 marked ✅ Complete.

7. **Added 2 tests** (`TestTrackDoesNotMutateProperties`) — verifies that `track()` does not mutate the caller's properties dict and that calling it twice with the same dict sends both events correctly.

**Test count after Stage 4: 203 tests, all passing.**

**Files changed:**
- `ckan/src/ckanext-pidinst-theme/ckanext/pidinst_theme/analytics.py`
- `ckan/src/ckanext-pidinst-theme/ckanext/pidinst_theme/assets/js/analytics-tracking.js`
- `ckan/src/ckanext-pidinst-theme/ckanext/pidinst_theme/tests/test_analytics.py`
- `docs/ANALYTICS_SETUP.md`
- `docs/ANALYTICS_QUICK_REFERENCE.md`
- `docs/README_ANALYTICS.md`
- `docs/ANALYTICS_IMPLEMENTATION_PLAN.md` (this file)

---

## Dashboard Readiness

### Conversion Dashboard

| Widget | Event(s) | Metric |
|---|---|---|
| Searches over time | `Search` | Count per day |
| Empty-result rate | `Empty-Result Search` / `Search` | % |
| Click-through rate | `Search Result Click-Through` / `Search` | % |
| Dataset page views | `Dataset Page View` | Count |
| Avg view duration | `Dataset View Duration`.`duration_seconds` | Average (seconds) |
| Downloads | `Download` | Count |
| Time to first download | `Time To First Download`.`seconds_to_download` | Average (seconds) |
| Download rate | `Download` / `Dataset Page View` | % |

### Stewardship Dashboard

| Widget | Event(s) | Metric |
|---|---|---|
| Datasets created | `Dataset Created` | Count |
| Datasets updated | `Update Existing Dataset` | Count |
| DOI publications | `Dataset Published With DOI` | Count |
| Dataset reuses | `Dataset Reuse Created` | Count |
| Reuse rate | `Dataset Reuse Created` / `Dataset Created` | % |
| Instrument vs platform | Any event `.dataset_type` | Breakdown |
| Public vs private | Any event `.is_public` | Breakdown |

### Manual Verification Checklist

- [ ] Search with results → `Search` event fires with `result_count > 0`, `is_empty: false`
- [ ] Search with no results → both `Search` and `Empty-Result Search` fire with `result_count: 0`
- [ ] Click a search result → `Search Result Click-Through` fires with `result_position`
- [ ] Load a dataset page → `Dataset Page View` fires once
- [ ] Stay on dataset page ≥ 3 s then navigate away → `Dataset View Duration` fires with `duration_seconds ≥ 3`
- [ ] Click a resource view / explore link → `Resource Preview Opened` fires
- [ ] Click a download link → `Download` fires with `file_size_group`
- [ ] Download fires once per click; second download in session sends `Download` but not `Time To First Download`
- [ ] First download click → `Time To First Download` fires with `seconds_to_download`
- [ ] Create a new dataset → `Dataset Created` fires
- [ ] Create a new version of an existing dataset → both `Dataset Created` and `Dataset Reuse Created` fire
- [ ] Edit an existing dataset → `Update Existing Dataset` fires; no `Dataset Created`
- [ ] Publish a DOI for the first time → `Dataset Published With DOI` fires with `doi_status: published`
- [ ] Edit a dataset with an already-published DOI → `Dataset Published With DOI` does NOT fire
- [ ] Logged-in user: verify `identify()` UUID matches the backend `user_id` in RudderStack Live Events
- [ ] Anonymous user: verify no `identify()` call; events appear with `anonymousId` only

5. **Test steps**: See Section 7 for a minimal validation checklist.

---

## 6. Files Changed in Stage 1 / Still Needing Changes

### Stage 1 — Changed

| File | What changed |
|---|---|
| `ckanext/pidinst_theme/analytics.py` | Added 11 `EVENT_*` constants; `minimal_dataset_props()`, `_dataset_type_from_pkg()`, `_is_public_from_pkg()`, `_has_doi_from_pkg()`, `file_size_group()` helpers; renamed `track_doi_created` → `track_doi_published`; all helpers use `minimal_dataset_props` |
| `ckanext/pidinst_theme/analytics_views.py` | All three endpoints return 400 on missing body; `/search` uses `search_term`/`result_count` with legacy fallbacks; `/resource-download` uses `size_bytes`/`dataset_type`; no `resource_name` |
| `ckanext/pidinst_theme/plugin.py` | `_analytics_suppress = True` in `package_patch` ctx; guard in `after_dataset_update`; TODO comment on DOI transition logic |
| `ckanext/pidinst_theme/templates/base.html` | `identify()` sends only `user_id`; no PII traits |
| `ckanext/pidinst_theme/templates/package/read_base.html` | Removed inline `<script>` block (XSS + duplicate); added `data-dataset-id`, `data-dataset-type`, `data-is-public` on wrapper `<div>` |
| `ckanext/pidinst_theme/assets/js/analytics-tracking.js` | Full rewrite: `EVENTS` constants; single `Dataset Page View` source; `initFormTracking()` removed; fake `Download Completion` removed; `file_size_group` on `Download`; `DOI-Based Citation` proxy documented |
| `ckanext/pidinst_theme/tests/test_analytics.py` | 75 tests across 10 classes (was 4 tests) |

### Stage 2 — Files Changed

| File | What changed |
|---|---|
| `ckanext/pidinst_theme/views.py` | Added server-side search tracking in `_instrument_platform_search()` (Stage 2A) |
| `ckanext/pidinst_theme/assets/js/analytics-tracking.js` | Stage 2B: `Resource Preview Opened` handler; Stage 2C: `Dataset View Duration` sendBeacon; TTFD property/timing/props fix |
| `ckanext/pidinst_theme/analytics.py` | Stage 2C: `EVENT_DATASET_VIEW_DURATION`, `KNOWN_FRONTEND_EVENTS` frozenset |
| `ckanext/pidinst_theme/analytics_views.py` | Stage 2C: event whitelist validation on `/api/analytics/track` |
| `ckanext/pidinst_theme/templates/snippets/package_item.html` | Stage 2B: `data-dataset-id` / `data-dataset-type` attrs on `.dataset-item-wrapper` |

### Stage 3 — Files Still Needing Changes

| File | Reason |
|---|---|
| `ckanext/pidinst_theme/plugin.py` | Fix `Dataset Published With DOI` transition logic; add `Dataset Reuse Created` detection |
| `ckanext/pidinst_theme/analytics.py` | Add `track_dataset_withdrawn()`, `track_dataset_reuse_created()` |
| `ckanext/pidinst_theme/views.py` | Add analytics call in `withdraw()`; pass `_original_package_id` in new version flow |

**Files that should NOT be changed:**
- `ckanext-doi/` — treat as external dependency

---

## 7. Risks and Open Questions

### Technical Risks

| Risk | Severity | Stage 1 Status | Notes |
|---|---|---|---|
| **DOI event fires on every update once DOI exists** | High | ⚠️ Partially mitigated — renamed, properties fixed, TODO added | Full first-mint-only check deferred to Stage 3 |
| **Spurious `Update Existing Dataset` during `after_dataset_create`** | Medium | ✅ Fixed — `_analytics_suppress` flag | |
| **Duplicate `Dataset Page View`** | Medium | ✅ Fixed — inline script removed; JS module is single source | |
| **XSS in `read_base.html`** | High | ✅ Fixed — inline script removed; `data-*` attrs used | |
| **PII in `identify()` call** | High | ✅ Fixed — only `user_id` sent | |
| **Bot traffic** | Medium | ❌ Not implemented | Stage 2: user-agent sniffing in backend endpoints |
| **Anonymous session ID inconsistency** | Medium | ⚠️ Not addressed | Frontend uses `sessionStorage` ID; backend uses `None` for anonymous; cannot be correlated |
| **Download completion reliability** | High | ✅ Fake impl removed | Stage 2: wrap server download route |
| **Search tracking on filter/pagination change** | Medium | ⚠️ Not addressed | Stage 2: server-side tracking resolves this |
| **`IPackageController.after_dataset_update` ordering** | Medium | ⚠️ Not addressed | Verify pidinst-theme registered after `ckanext-doi` |

### Open Questions

1. **Should anonymous user behaviour be tracked server-side at all?** Currently backend events for anonymous users use `user_id: None`. A per-session anonymous ID is needed for funnel analysis. Suggest: use `flask.session.sid` or a signed cookie.

2. **What is the intended `Dataset Published With DOI` trigger?** First mint only? Or also on metadata update? This decision gates the Stage 3 implementation approach.

3. **DataCite Event Data API polling**: Should this be implemented? It requires the site's DOI prefix. It would provide the most reliable citation tracking as a background job.

4. **Search query privacy**: Should `search_term` be sent in events? If search queries may contain personally identifying terms, this should be reviewed before enabling server-side search tracking.

---

*Last updated: Stage 3D complete (identity alignment — unified CKAN UUID for frontend and backend). Next: Stage 3C — Dataset Withdrawn, DataCite citation polling.*
