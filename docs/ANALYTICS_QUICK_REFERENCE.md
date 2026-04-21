# Quick Reference: Analytics Events

## Tracked Events

| Event Name | Trigger | Location | Properties |
|------------|---------|----------|------------|
| **Dataset Search Submitted** | User submits search form | Search page | `search_query`, `sort_by`, `page`, `url` |
| **Search Result Click-Through** | Click on dataset in search results | Search results | `dataset_title`, `dataset_url`, `search_query`, `result_position` |
| **Dataset Page View** | Dataset page loads | Dataset page | `dataset_id`, `dataset_title`, `organization`, `has_doi`, `num_resources` |
| **Resource Download Click** | Click download button | Dataset/Resource page | `download_id`, `resource_url`, `resource_name`, `resource_format` |
| **Download Completion** | After download initiated | Dataset/Resource page | `download_id`, `resource_url`, `completion_status` |
| **Time to First Download** | First download in session | Any download | `time_to_download_ms`, `time_to_download_seconds` |
| **Dataset Created** | Dataset created successfully | Backend | `dataset_id`, `dataset_title`, `num_resources`, `num_tags` |
| **Dataset Published with DOI** | DOI created for dataset | Backend | `dataset_id`, `dataset_title`, `doi` |
| **Update Existing Dataset** | Dataset updated | Backend | `dataset_id`, `dataset_title`, `num_resources` |
| **DOI-Based Citation** | Click on DOI badge/link | Dataset page | `doi`, `dataset_id`, `citation_link_clicked` |

## Event Flow Examples

### Download Funnel
```
1. Dataset Search Submitted
   └─> 2. Search Result Click-Through
       └─> 3. Dataset Page View
           └─> 4. Resource Download Click
               └─> 5. Download Completion
```

### Dataset Creation Funnel
```
1. Dataset Created
   └─> 2. Update Existing Dataset (optional, multiple times)
       └─> 3. Dataset Published with DOI
```

### Citation Tracking
```
1. Dataset Page View
   └─> 2. DOI-Based Citation (click)
```

## Testing Events

### Browser Console

```javascript
// Check if tracker is loaded
console.log(typeof window.CKANAnalytics);
// Output: "object"

// Check RudderStack
console.log(typeof rudderanalytics);
// Output: "object"

// Track custom event
window.CKANAnalytics.track('Test Event', {test: 'data'});
```

### Python Shell

```python
from ckanext.pidinst_theme import analytics

# Initialize tracker
analytics.AnalyticsTracker.initialize()

# Check if enabled
print(analytics.AnalyticsTracker.is_enabled())

# Track event
analytics.AnalyticsTracker.track(
    user_id='test_user',
    event='Test Event',
    properties={'test': 'data'}
)
```

## API Testing with cURL

```bash
# Track custom event
curl -X POST http://localhost:5000/api/analytics/track \
  -H "Content-Type: application/json" \
  -d '{"event":"Test Event","properties":{"key":"value"}}'

# Track resource download
curl -X POST http://localhost:5000/api/analytics/resource-download \
  -H "Content-Type: application/json" \
  -d '{
    "resource_id":"res-123",
    "dataset_id":"ds-456",
    "resource_name":"data.csv",
    "resource_format":"CSV"
  }'

# Track search
curl -X POST http://localhost:5000/api/analytics/search \
  -H "Content-Type: application/json" \
  -d '{
    "query":"climate data",
    "num_results":15,
    "sort_by":"relevance"
  }'
```

## Funnel Queries (Amplitude/Mixpanel)

### Download Conversion Rate

```
Step 1: Dataset Search Submitted
Step 2: Search Result Click-Through
Step 3: Dataset Page View
Step 4: Resource Download Click

Conversion = (Step 4 / Step 1) * 100%
```

### Time to First Download

```
Event: Time to First Download
Metric: Average(time_to_download_seconds)
Group By: User, Session
```

### DOI Publication Rate

```
Step 1: Dataset Created
Step 2: Dataset Published with DOI

Conversion = (Step 2 / Step 1) * 100%
```

### Most Downloaded Resources

```
Event: Resource Download Click
Count: resource_url or resource_name
Sort: Descending
Limit: Top 10
```

## Debugging

### Check if events are firing

1. Open browser DevTools (F12)
2. Go to Network tab
3. Filter by "rudderstack" or "analytics"
4. Perform actions that should trigger events
5. Look for network requests

### Common Issues

| Issue | Solution |
|-------|----------|
| Events not appearing | Check RUDDERSTACK_ENABLED=true in .env |
| Wrong event properties | Verify template has correct data attributes |
| Backend events not tracking | Install rudderstack-python SDK |
| Duplicate events | Check if tracking code is included multiple times |

## Data Retention

- RudderStack: As per your plan
- Amplitude: 30-365 days (depends on plan)
- Mixpanel: 5 years (depends on plan)

## Privacy Considerations

- User IDs are tracked for authenticated users
- Anonymous events use anonymous_id
- No PII (Personally Identifiable Information) in event properties by default
- Comply with GDPR/privacy policies
- Allow users to opt-out if required
