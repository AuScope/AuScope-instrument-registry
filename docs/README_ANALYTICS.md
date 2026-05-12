# AuScope Data Repository — Analytics Tracking

Analytics implementation for the AuScope PIDINST CKAN extension. Tracks conversion and stewardship metrics using RudderStack.

## Implemented Events

### Conversion

| Event | Source |
|---|---|
| `Search` | Backend — `_instrument_platform_search` after `package_search` |
| `Empty-Result Search` | Backend — same call when `result_count == 0` |
| `Search Result Click-Through` | Frontend JS — click on search result heading |
| `Dataset Page View` | Frontend JS — dataset detail page load |
| `Resource Preview Opened` | Frontend JS — click on resource view / explore link |
| `Download` | Frontend JS — click on download link |
| `Time To First Download` | Frontend JS — first download per dataset page load |
| `Dataset View Duration` | Frontend JS (sendBeacon) — user leaves dataset page |

### Stewardship

| Event | Source |
|---|---|
| `Dataset Created` | Backend — `after_dataset_create` hook |
| `Update Existing Dataset` | Backend — `after_dataset_update` hook (user edits only) |
| `Dataset Published With DOI` | Backend — first DOI publication transition |
| `Dataset Reuse Created` | Backend — `after_dataset_create` for new-version datasets |
| `DOI-Based Citation` | Frontend JS (proxy) — DOI badge link click |

## Quick Start

### 1. Configure environment

```bash
RUDDERSTACK_ENABLED=true
RUDDERSTACK_WRITE_KEY=your_write_key
RUDDERSTACK_DATA_PLANE_URL=https://your-dataplane.example.com
```

### 2. Rebuild and start

```bash
docker compose -f docker-compose.dev.yml build ckan-dev
docker compose -f docker-compose.dev.yml up -d ckan-dev
```

### 3. Verify

```bash
./check-analytics-setup.sh
```

## Documentation

- [ANALYTICS_SETUP.md](ANALYTICS_SETUP.md) — configuration, file structure, troubleshooting
- [ANALYTICS_QUICK_REFERENCE.md](ANALYTICS_QUICK_REFERENCE.md) — event names, payload schemas, allowed properties
- [ANALYTICS_IMPLEMENTATION_PLAN.md](ANALYTICS_IMPLEMENTATION_PLAN.md) — full implementation history and metric coverage table

## Known Limitations

- **Download Completion** — not implemented. Client-side detection is unreliable; requires a server-side CKAN download route override.
- **DOI-Based Citation** — proxy only (DOI link click). Real citation tracking requires the DataCite Event Data API.
- **Dataset Withdrawn** — not implemented.
- **Unique / Returning Visitors** — partially covered by RudderStack's built-in anonymous ID.

## Privacy

- No PII in any event payload. Email, username, display name, dataset title, resource name, and raw DOI values are never sent.
- Authenticated users are identified by their stable CKAN internal UUID only.
- Anonymous users use RudderStack's built-in anonymous ID; `identify()` is never called for them.

## Testing

```bash
cd ckan/src/ckanext-pidinst-theme
python -m pytest ckanext/pidinst_theme/tests/test_analytics.py -q --no-header -p no:warnings
```

Expected: 203+ tests passing.
