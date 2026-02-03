# Analytics Tracking Setup Guide

## Overview

This analytics implementation tracks user interactions for funnel analysis using RudderStack, which is connected to Amplitude and Mixpanel.

## Events Tracked

### Frontend Events (JavaScript)

1. **Dataset Search Submitted**
   - Triggered when user submits search form
   - Properties: search_query, sort_by, page, url

2. **Search Result Click-Through**
   - Triggered when user clicks on dataset from search results
   - Properties: dataset_title, dataset_url, search_query, result_position

3. **Dataset Page View**
   - Triggered when dataset page loads
   - Properties: dataset_id, dataset_title, organization, has_doi, page_url, referrer

4. **Resource Download Click**
   - Triggered when user clicks download button
   - Properties: download_id, resource_url, resource_name, resource_format, dataset_id

5. **Download Completion**
   - Triggered after download initiated
   - Properties: download_id, resource_url, resource_name, completion_status

6. **Time to First Download**
   - Triggered on first download of session
   - Properties: time_to_download_ms, time_to_download_seconds

7. **DOI-Based Citation**
   - Triggered when user clicks DOI badge/link
   - Properties: doi, dataset_id, citation_link_clicked

### Backend Events (Python)

8. **Dataset Created**
   - Triggered after successful dataset creation
   - Properties: dataset_id, dataset_title, organization_id, num_resources, num_tags

9. **Dataset Published with DOI**
   - Triggered when DOI is created for dataset
   - Properties: dataset_id, dataset_title, doi, organization_id

10. **Update Existing Dataset**
    - Triggered after dataset update
    - Properties: dataset_id, dataset_title, organization_id, num_resources

## Installation

### 1. Install Python Dependencies (Optional - for server-side tracking)

```bash
cd /opt/ckan/ckan/src/ckanext-pidinst-theme
pip install -r analytics-requirements.txt
```

### 2. Configure Environment Variables

Add to your `.env` file:

```bash
# Analytics Configuration
RUDDERSTACK_ENABLED=true
RUDDERSTACK_WRITE_KEY=your_write_key_here
RUDDERSTACK_DATA_PLANE_URL=https://rudderstack.data.auscope.org.au
```

### 3. Rebuild Docker Container

```bash
cd /opt/ckan
docker compose -f docker-compose.dev.yml build ckan-dev
docker compose -f docker-compose.dev.yml up -d ckan-dev
```

## Files Created/Modified

### New Files
- `assets/js/analytics-tracking.js` - Frontend tracking logic
- `analytics.py` - Backend tracking helpers
- `analytics_views.py` - API endpoints for tracking
- `analytics-requirements.txt` - Python dependencies

### Modified Files
- `assets/webassets.yml` - Added analytics JS to bundle
- `plugin.py` - Integrated backend event tracking
- `helpers.py` - Added analytics helper functions
- `views.py` - Registered analytics blueprint

### New Templates
- `templates/package/snippets/package_item.html` - Search result tracking
- `templates/package/read_base.html` - Dataset page view tracking
- `templates/package/snippets/resource_item.html` - Download tracking

## API Endpoints

### POST /api/analytics/track
Generic event tracking endpoint

```json
{
  "event": "Custom Event Name",
  "properties": {
    "key": "value"
  }
}
```

### POST /api/analytics/resource-download
Track resource downloads

```json
{
  "resource_id": "...",
  "dataset_id": "...",
  "resource_name": "...",
  "resource_format": "..."
}
```

### POST /api/analytics/search
Track search events

```json
{
  "query": "search terms",
  "num_results": 10,
  "sort_by": "relevance"
}
```

## Custom Event Tracking

You can track custom events from JavaScript:

```javascript
if (typeof window.CKANAnalytics !== 'undefined') {
  window.CKANAnalytics.track('Custom Event', {
    property1: 'value1',
    property2: 'value2'
  });
}
```

From Python:

```python
from ckanext.pidinst_theme import analytics

analytics.AnalyticsTracker.track(
    user_id='user_id_here',
    event='Custom Event',
    properties={'key': 'value'}
)
```

## Verification

### 1. Check Browser Console
Open browser DevTools and check for:
- "Analytics tracking initialized" message
- Event tracking logs

### 2. Check RudderStack Dashboard
- Log into your RudderStack dashboard
- Navigate to Live Events
- Verify events are being received

### 3. Check Amplitude/Mixpanel
- Log into Amplitude or Mixpanel
- Check recent events
- Verify event properties are correct

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

1. Dataset Search Submitted
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
