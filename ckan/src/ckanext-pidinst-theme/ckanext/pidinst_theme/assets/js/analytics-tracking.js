/**
 * CKAN Analytics Tracking Module
 * Tracks user interactions for funnel analysis using RudderStack
 *
 * Event names must match the requirements table exactly.
 * Property rules:
 *   - Never send dataset_title, dataset_name, resource_name, email, username
 *   - dataset_type and is_public are read from data-* attributes on the
 *     [data-module="dataset-view"] wrapper set by read_base.html
 */

(function(window, document) {
  'use strict';

  // ---------------------------------------------------------------------------
  // Event name constants — must match analytics.py EVENT_* constants
  // ---------------------------------------------------------------------------
  var EVENTS = {
    SEARCH:                     'Search',
    EMPTY_RESULT_SEARCH:        'Empty-Result Search',
    SEARCH_RESULT_CLICK_THROUGH:'Search Result Click-Through',
    DATASET_PAGE_VIEW:          'Dataset Page View',
    DOWNLOAD:                   'Download',
    TIME_TO_FIRST_DOWNLOAD:     'Time To First Download',
    DATASET_CREATED:            'Dataset Created',
    DATASET_PUBLISHED_WITH_DOI: 'Dataset Published With DOI',
    UPDATE_EXISTING_DATASET:    'Update Existing Dataset',
    DOI_BASED_CITATION:         'DOI-Based Citation',
    RESOURCE_PREVIEW_OPENED:    'Resource Preview Opened',
    DATASET_VIEW_DURATION:      'Dataset View Duration'
  };

  // ---------------------------------------------------------------------------
  // Analytics tracking helper
  // ---------------------------------------------------------------------------
  var AnalyticsTracker = {

    isReady: function() {
      return typeof window.rudderanalytics !== 'undefined' && window.rudderanalytics.track;
    },

    track: function(eventName, properties, callback) {
      if (this.isReady()) {
        try {
          window.rudderanalytics.track(eventName, properties || {});
          if (callback) callback();
        } catch (e) {
          console.error('Analytics tracking error:', e);
        }
      } else {
        // Retry once after SDK loads
        var self = this;
        setTimeout(function() {
          if (self.isReady()) {
            self.track(eventName, properties, callback);
          }
        }, 500);
      }
    },

    trackPageView: function(properties) {
      if (this.isReady()) {
        window.rudderanalytics.page(properties || {});
      }
    }
  };

  // ---------------------------------------------------------------------------
  // Helper: read dataset context attributes from the page wrapper div
  // ---------------------------------------------------------------------------
  function getDatasetContext() {
    var wrapper = document.querySelector('[data-module="dataset-view"]');
    if (!wrapper) return null;
    return {
      dataset_id:   wrapper.getAttribute('data-dataset-id') || undefined,
      dataset_type: wrapper.getAttribute('data-dataset-type') || 'unknown',
      is_public:    wrapper.getAttribute('data-is-public') === 'true'
                    ? true
                    : wrapper.getAttribute('data-is-public') === 'false'
                    ? false
                    : undefined
    };
  }

  // ---------------------------------------------------------------------------
  // Search tracking
  // ---------------------------------------------------------------------------
  function initSearchTracking() {
    // Note: Search and Empty-Result Search events are now fired from the
    // backend (_instrument_platform_search in views.py) which has reliable
    // result_count.  The form-submit handler has been removed to avoid
    // duplicates.  This function now only sets up click-through tracking.

    // Search result click-through: primary selector
    var datasetListItems = document.querySelectorAll('.dataset-item');
    datasetListItems.forEach(function(item, index) {
      var link = item.querySelector('.dataset-heading a, h3.dataset-heading a');
      if (!link) return;
      // Dedup guard — prevent double-binding if initSearchTracking is called twice
      if (link.getAttribute('data-analytics-click-tracked')) return;
      link.setAttribute('data-analytics-click-tracked', '1');

      // Read dataset_id and dataset_type from the wrapper div (Stage 2B data-* attrs)
      var wrapper = item.querySelector('.dataset-item-wrapper');
      var datasetId   = (wrapper && wrapper.getAttribute('data-dataset-id'))   ||
                        item.getAttribute('data-dataset-id')                   ||
                        link.getAttribute('data-dataset-id');
      var datasetType = (wrapper && wrapper.getAttribute('data-dataset-type')) ||
                        item.getAttribute('data-dataset-type');

      link.addEventListener('click', function() {
        try {
          var searchTerm = new URLSearchParams(window.location.search).get('q');
          var props = { result_position: index + 1 };
          if (datasetId)   props.dataset_id   = datasetId;
          if (datasetType) props.dataset_type = datasetType;
          if (searchTerm)  props.search_term  = searchTerm;
          AnalyticsTracker.track(EVENTS.SEARCH_RESULT_CLICK_THROUGH, props);
        } catch (e) {
          // Tracking failure must not prevent navigation
          console.error('Analytics SRCT error:', e);
        }
      });
    });

    // Fallback: bare heading links when no .dataset-item wrappers are found
    if (datasetListItems.length === 0) {
      var headingLinks = document.querySelectorAll('.dataset-heading a');
      headingLinks.forEach(function(link, index) {
        if (link.getAttribute('data-analytics-click-tracked')) return;
        link.setAttribute('data-analytics-click-tracked', '1');
        link.addEventListener('click', function() {
          try {
            var searchTerm = new URLSearchParams(window.location.search).get('q');
            var props = { result_position: index + 1 };
            if (searchTerm) props.search_term = searchTerm;
            AnalyticsTracker.track(EVENTS.SEARCH_RESULT_CLICK_THROUGH, props);
          } catch (e) {
            console.error('Analytics SRCT fallback error:', e);
          }
        });
      });
    }
  }

  // ---------------------------------------------------------------------------
  // Resource preview tracking (Stage 2B)
  // Fires when the user navigates to a resource view/read page.
  // Covers:
  //   1. .resource-item a.heading links (resource_item_short.html)
  //   2. Explore-dropdown links whose href contains /resource/ (CKAN core)
  // Only active on dataset read pages (requires [data-module="dataset-view"]).
  // ---------------------------------------------------------------------------
  function initResourcePreviewTracking() {
    var ctx = getDatasetContext();
    if (!ctx || !ctx.dataset_id) return;  // not on a dataset page

    // Collect resource-page links from both rendering paths
    var headingLinks  = document.querySelectorAll('.resource-item a.heading');
    var exploreLinks  = document.querySelectorAll(
      '.resource-item .dropdown-item[href*="/resource/"], ' +
      '.resource-item a[href*="/resource/"]'
    );

    var seen = {};
    var allLinks = [];
    [headingLinks, exploreLinks].forEach(function(nodeList) {
      nodeList.forEach(function(el) {
        if (!seen[el]) { seen[el] = true; allLinks.push(el); }
      });
    });

    allLinks.forEach(function(link) {
      // Dedup guard
      if (link.getAttribute('data-analytics-preview-tracked')) return;
      link.setAttribute('data-analytics-preview-tracked', '1');

      link.addEventListener('click', function() {
        try {
          var resourceItem = link.closest('.resource-item');

          // Resolve resource_id: prefer DOM data-id, fall back to href segment
          var resourceId = (resourceItem && resourceItem.getAttribute('data-id')) || undefined;
          if (!resourceId) {
            var href = link.getAttribute('href') || '';
            var m = href.match(/\/resource\/([a-f0-9-]{36})/);
            if (m) resourceId = m[1];
          }

          // Resolve resource_format: prefer wrapper data-resource-format, then format-label
          var resourceFormat;
          var dropdownWrapper = link.closest('[data-resource-format]');
          if (dropdownWrapper) {
            resourceFormat = dropdownWrapper.getAttribute('data-resource-format') || undefined;
          }
          if (!resourceFormat && resourceItem) {
            var fmtEl = resourceItem.querySelector('[data-format]');
            resourceFormat = fmtEl ? (fmtEl.getAttribute('data-format') || undefined) : undefined;
          }

          var props = { dataset_id: ctx.dataset_id };
          if (ctx.dataset_type) props.dataset_type = ctx.dataset_type;
          if (resourceId)       props.resource_id   = resourceId;
          if (resourceFormat)   props.resource_format = resourceFormat;

          AnalyticsTracker.track(EVENTS.RESOURCE_PREVIEW_OPENED, props);
        } catch (e) {
          // Tracking failure must not prevent navigation
          console.error('Analytics Resource Preview error:', e);
        }
      });
    });
  }

  // ---------------------------------------------------------------------------
  // Dataset page view tracking
  // Single source of truth — the inline script in read_base.html has been
  // removed.  This function is the only place Dataset Page View fires.
  // ---------------------------------------------------------------------------
  function trackDatasetPageView() {
    var ctx = getDatasetContext();
    if (!ctx || !ctx.dataset_id) return;

    var hasDOI = document.querySelector('.doi-badge, [data-doi]') !== null;

    AnalyticsTracker.track(EVENTS.DATASET_PAGE_VIEW, {
      dataset_id:   ctx.dataset_id,
      dataset_type: ctx.dataset_type,
      is_public:    ctx.is_public,
      has_doi:      hasDOI
    });
  }

  // ---------------------------------------------------------------------------
  // Dataset view duration tracking (Stage 2C)
  // Uses visibilitychange + pagehide as primary triggers.
  // Uses sendBeacon (with Blob for JSON content-type) where available;
  // falls back to fetch(..., { keepalive: true }).
  // Fires at most once per page view; ignores < 2 s; caps at 30 min.
  // ---------------------------------------------------------------------------
  function initDatasetViewDurationTracking() {
    var ctx = getDatasetContext();
    if (!ctx || !ctx.dataset_id) return;  // only on dataset read pages

    var hasDOI = document.querySelector('.doi-badge, [data-doi]') !== null;
    var pageStart = Date.now();
    var fired = false;

    function sendDuration() {
      if (fired) return;
      fired = true;

      var durationMs  = Date.now() - pageStart;
      var durationSec = Math.round(durationMs / 1000);

      // Ignore very short durations (< 2 s — likely accidental navigation)
      if (durationSec < 2) return;
      // Cap unrealistically long durations (max 30 min = 1800 s)
      if (durationSec > 1800) durationSec = 1800;

      var payload = JSON.stringify({
        event: EVENTS.DATASET_VIEW_DURATION,
        properties: {
          dataset_id:       ctx.dataset_id,
          dataset_type:     ctx.dataset_type,
          is_public:        ctx.is_public,
          has_doi:          hasDOI,
          duration_seconds: durationSec
        }
      });

      var url = '/api/analytics/track';
      try {
        if (navigator.sendBeacon) {
          // Wrap in Blob so the browser sends Content-Type: application/json
          navigator.sendBeacon(url, new Blob([payload], { type: 'application/json' }));
        } else {
          // keepalive: true ensures the request survives page unload
          fetch(url, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    payload,
            keepalive: true
          }).catch(function() {});  // failure must never affect navigation
        }
      } catch (e) {
        // Tracking failure must never affect navigation
        console.error('Analytics view duration error:', e);
      }
    }

    // Primary: fires when the tab is hidden (switch tabs, navigate away, minimise)
    document.addEventListener('visibilitychange', function() {
      if (document.visibilityState === 'hidden') {
        sendDuration();
      }
    });

    // Secondary: fires on back/forward cache eviction and legacy unloads
    window.addEventListener('pagehide', function() {
      sendDuration();
    });
  }

  // ---------------------------------------------------------------------------
  // Resource download tracking
  // ---------------------------------------------------------------------------
  function initDownloadTracking() {
    var downloadLinks = document.querySelectorAll(
      'a[href*="/download/"], .resource-url-analytics, a.resource-url'
    );

    // Capture the dataset page load time for Time To First Download measurement.
    // This is intentionally page-specific (not the overall session start) so the
    // metric reflects time from dataset page load to first download click.
    var datasetPageLoadTime = Date.now();

    downloadLinks.forEach(function(link) {
      link.addEventListener('click', function() {
        var resourceId = this.getAttribute('data-resource-id');
        var resourceFormat = this.getAttribute('data-format') ||
                             (this.closest('.resource-item') &&
                              this.closest('.resource-item').querySelector('.format-label') &&
                              this.closest('.resource-item').querySelector('.format-label').textContent.trim());
        var ctx = getDatasetContext();
        var datasetId = ctx && ctx.dataset_id;

        var props = {
          resource_format: resourceFormat || ''
        };
        if (resourceId)  props.resource_id  = resourceId;
        if (datasetId)   props.dataset_id   = datasetId;
        if (ctx && ctx.dataset_type) props.dataset_type = ctx.dataset_type;

        AnalyticsTracker.track(EVENTS.DOWNLOAD, props);

        // Time To First Download — fires at most once per session.
        // seconds_to_download measures from dataset page load to this click.
        if (!sessionStorage.getItem('has_downloaded')) {
          var elapsed = Date.now() - datasetPageLoadTime;
          var ttfdProps = {
            seconds_to_download: Math.round(elapsed / 1000)
          };
          if (resourceId)              ttfdProps.resource_id      = resourceId;
          if (datasetId)               ttfdProps.dataset_id       = datasetId;
          if (ctx && ctx.dataset_type) ttfdProps.dataset_type     = ctx.dataset_type;
          if (resourceFormat)          ttfdProps.resource_format  = resourceFormat;
          AnalyticsTracker.track(EVENTS.TIME_TO_FIRST_DOWNLOAD, ttfdProps);
          sessionStorage.setItem('has_downloaded', 'true');
        }
      });
    });
  }

  // ---------------------------------------------------------------------------
  // DOI tracking
  // ---------------------------------------------------------------------------
  function initDOITracking() {
    // DOI badge / link clicks — proxy for citation intent only.
    // NOTE: a hyperlink click is NOT a real citation.  This event is documented
    // as a proxy.  Real DOI-Based Citation tracking requires the DataCite
    // Event Data API (planned Stage 4).
    var doiBadges = document.querySelectorAll('.doi-badge, [data-doi] a, a[href*="doi.org"]');
    doiBadges.forEach(function(badge) {
      badge.addEventListener('click', function() {
        var ctx = getDatasetContext();
        AnalyticsTracker.track(EVENTS.DOI_BASED_CITATION, {
          dataset_id:      ctx && ctx.dataset_id,
          dataset_type:    ctx && ctx.dataset_type,
          is_public:       ctx && ctx.is_public,
          citation_source: 'doi_link_click'  // proxy only — not a real citation
        });
      });
    });
  }

  // ---------------------------------------------------------------------------
  // User identity
  // Reads window.PIDINST_ANALYTICS_USER_ID (set by base.html only when a user
  // is logged in) and calls rudderanalytics.identify() so that all subsequent
  // frontend track calls are correlated with the same stable UUID used by
  // backend lifecycle events (Dataset Created, Update Existing Dataset, etc.).
  //
  // For anonymous visitors the variable is absent; identify() is NOT called
  // and RudderStack assigns its own anonymous ID automatically.
  //
  // Privacy rules:
  //   - Never send email, username, display name, or any other PII as traits.
  //   - Only the stable internal CKAN user UUID is passed to identify().
  // ---------------------------------------------------------------------------
  function initUserIdentity() {
    var analyticsUserId = window.PIDINST_ANALYTICS_USER_ID;
    if (!analyticsUserId) {
      // Anonymous user — do not call identify(); RudderStack anonymous ID applies.
      return;
    }
    function doIdentify() {
      try {
        // No traits object — only the stable UUID is sent.
        window.rudderanalytics.identify(analyticsUserId);
      } catch (e) {
        console.error('Analytics identify error:', e);
      }
    }
    if (typeof window.rudderanalytics !== 'undefined' && window.rudderanalytics.ready) {
      window.rudderanalytics.ready(doIdentify);
    }
    // If RudderStack is not loaded (e.g. RUDDERSTACK_ENABLED=false),
    // doIdentify is never called; tracking degrades silently.
  }

  // ---------------------------------------------------------------------------
  // Initialise all tracking
  // ---------------------------------------------------------------------------
  function initializeTracking() {
    initUserIdentity();
    initSearchTracking();
    trackDatasetPageView();
    initDatasetViewDurationTracking();
    initDownloadTracking();
    initResourcePreviewTracking();
    initDOITracking();
    // initFormTracking() removed: Dataset Created and Update Existing Dataset
    // are tracked server-side via CKAN hooks (after_dataset_create /
    // after_dataset_update in plugin.py).  Frontend form-submit tracking was
    // a duplicate source and has been intentionally removed.
  }

  function init() {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initializeTracking);
    } else {
      initializeTracking();
    }
  }

  // Expose tracker globally for custom events
  window.CKANAnalytics = AnalyticsTracker;
  window.CKANAnalyticsEvents = EVENTS;

  init();

})(window, document);
