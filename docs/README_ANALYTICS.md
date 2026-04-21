# 📊 CKAN Funnel Analytics Tracking

Complete analytics implementation for tracking user interactions and conversions in your CKAN instance. Integrates with **RudderStack** → **Amplitude** & **Mixpanel**.

## 🎯 Tracked Metrics

| # | Metric | Type | Status |
|---|--------|------|--------|
| 1 | Dataset search submitted | Frontend | ✅ |
| 2 | Search result click-through | Frontend | ✅ |
| 3 | Dataset page view | Frontend | ✅ |
| 4 | Resource download click | Frontend | ✅ |
| 5 | Download completion | Frontend | ✅ |
| 6 | Time to first download | Frontend | ✅ |
| 7 | Dataset created | Backend | ✅ |
| 8 | Dataset published with DOI | Backend | ✅ |
| 9 | Update existing dataset | Backend | ✅ |
| 10 | DOI-based citations | Frontend | ✅ |

## 🚀 Quick Start

### 1. Configure Environment

Edit your `.env` file:

```bash
RUDDERSTACK_ENABLED=true
RUDDERSTACK_WRITE_KEY=38ST3ZywfJz5uRodAvX3BfbLbNE
RUDDERSTACK_DATA_PLANE_URL=https://rudderstack.data.auscope.org.au
```

### 2. Install Dependencies (Optional - for backend tracking)

```bash
cd /opt/ckan
docker compose -f docker-compose.dev.yml exec ckan-dev bash
pip install rudderstack-python
```

### 3. Rebuild Container

```bash
docker compose -f docker-compose.dev.yml build ckan-dev
docker compose -f docker-compose.dev.yml up -d ckan-dev
```

### 4. Verify Setup

```bash
./check-analytics-setup.sh
```

## 📂 Documentation

- **[ANALYTICS_IMPLEMENTATION_SUMMARY.md](ANALYTICS_IMPLEMENTATION_SUMMARY.md)** - Complete implementation details
- **[ANALYTICS_SETUP.md](ckan/src/ckanext-pidinst-theme/ANALYTICS_SETUP.md)** - Detailed setup guide
- **[ANALYTICS_QUICK_REFERENCE.md](ckan/src/ckanext-pidinst-theme/ANALYTICS_QUICK_REFERENCE.md)** - Quick reference for events and queries

## 🧪 Testing

### Browser Console

```javascript
// Check if loaded
console.log(typeof window.CKANAnalytics);  // Should return "object"
console.log(typeof rudderanalytics);  // Should return "object"

// Track test event
window.CKANAnalytics.track('Test Event', {test: 'data'});
```

### Python Shell

```python
from ckanext.pidinst_theme import analytics

# Initialize
analytics.AnalyticsTracker.initialize()
print(analytics.AnalyticsTracker.is_enabled())  # Should return True

# Track event
analytics.AnalyticsTracker.track('test_user', 'Test Event', {'test': 'data'})
```

### API Testing

```bash
curl -X POST http://localhost:5000/api/analytics/track \
  -H "Content-Type: application/json" \
  -d '{"event":"Test Event","properties":{"key":"value"}}'
```

## 📊 Viewing Results

1. **RudderStack**: https://app.rudderstack.com/ → Your Source → Live Events
2. **Amplitude**: https://analytics.amplitude.com/ → Real-time tab
3. **Mixpanel**: https://mixpanel.com/ → Live View

## 🔧 Troubleshooting

### Events not appearing?

1. Check environment variables:
   ```bash
   docker compose exec ckan-dev env | grep RUDDERSTACK
   ```

2. Check browser console for errors (F12)

3. View container logs:
   ```bash
   docker compose -f docker-compose.dev.yml logs -f ckan-dev | grep analytics
   ```

4. Run setup check:
   ```bash
   ./check-analytics-setup.sh
   ```

## 📁 File Structure

```
/opt/ckan/
├── ANALYTICS_IMPLEMENTATION_SUMMARY.md
├── check-analytics-setup.sh
└── ckan/src/ckanext-pidinst-theme/
    ├── ANALYTICS_SETUP.md
    ├── ANALYTICS_QUICK_REFERENCE.md
    ├── analytics-requirements.txt
    └── ckanext/pidinst_theme/
        ├── analytics.py                    # Backend tracking
        ├── analytics_views.py              # API endpoints
        ├── assets/
        │   └── js/
        │       └── analytics-tracking.js   # Frontend tracking
        ├── templates/
        │   └── package/
        │       ├── read_base.html
        │       └── snippets/
        │           ├── package_item.html
        │           └── resource_item.html
        └── tests/
            └── test_analytics.py
```

## 🔍 Example Funnels

### Download Conversion

```
Dataset Search → Click Result → View Dataset → Download → Complete
```

Track conversion rates at each step in Amplitude/Mixpanel.

### DOI Publication

```
Dataset Created → Update Dataset → Publish DOI
```

Measure time from creation to publication.

### Citation Tracking

```
Dataset Page View → DOI Citation Click
```

Track engagement with DOIs and potential citations.

## 🛠️ Custom Events

Add custom tracking anywhere:

**JavaScript:**
```javascript
window.CKANAnalytics.track('Custom Event', {property: 'value'});
```

**Python:**
```python
from ckanext.pidinst_theme import analytics
analytics.AnalyticsTracker.track('user_id', 'Custom Event', {'key': 'value'})
```

## 📈 Key Insights Available

- **Search Performance**: Most common queries, zero-result searches
- **Dataset Popularity**: Most viewed/downloaded datasets
- **User Journey**: Complete path from search to download
- **Conversion Rates**: Search→View→Download percentages
- **Time Metrics**: Time to first download, session duration
- **DOI Impact**: Citation clicks, publication rates
- **Drop-off Points**: Where users abandon the funnel

## 🔐 Privacy

- Authenticated users tracked by user ID
- Anonymous users tracked by session ID
- No PII (Personally Identifiable Information) in event properties
- Compliant with existing RudderStack setup
- Consider adding opt-out if required

## 📞 Support

Need help? Check:
1. Setup documentation in `ANALYTICS_SETUP.md`
2. Quick reference in `ANALYTICS_QUICK_REFERENCE.md`
3. RudderStack docs: https://rudderstack.com/docs/
4. Container logs: `docker compose logs ckan-dev`

## ✅ Implementation Checklist

- [x] Frontend tracking script created
- [x] Backend tracking module created
- [x] API endpoints for tracking
- [x] Templates updated with tracking
- [x] All 10 metrics implemented
- [x] Documentation complete
- [x] Test suite created
- [ ] Environment variables configured (do this!)
- [ ] Container rebuilt (do this!)
- [ ] Verification in RudderStack (do this!)
- [ ] Verification in Amplitude/Mixpanel (do this!)

---

**Ready to track!** 🚀 Configure your environment variables and rebuild the container to start collecting analytics.
