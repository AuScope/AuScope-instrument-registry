/**
 * CKAN Analytics Tracking Module
 * Tracks user interactions for funnel analysis using RudderStack
 */

(function(window, document) {
  'use strict';

  // Analytics tracking helper
  var AnalyticsTracker = {
    
    // Check if RudderStack is loaded
    isReady: function() {
      return typeof window.rudderanalytics !== 'undefined' && window.rudderanalytics.track;
    },

    // Track event with retry mechanism
    track: function(eventName, properties, callback) {
      if (this.isReady()) {
        try {
          window.rudderanalytics.track(eventName, properties || {});
          if (callback) callback();
        } catch (e) {
          console.error('Analytics tracking error:', e);
        }
      } else {
        // Retry after RudderStack loads
        var self = this;
        setTimeout(function() {
          if (self.isReady()) {
            self.track(eventName, properties, callback);
          }
        }, 500);
      }
    },

    // Track page view
    trackPageView: function(properties) {
      if (this.isReady()) {
        window.rudderanalytics.page(properties || {});
      }
    }
  };

  // Dataset Search Tracking
  function initSearchTracking() {
    // Track search form submission
    var searchForm = document.querySelector('form.search-form');
    if (searchForm) {
      searchForm.addEventListener('submit', function(e) {
        var searchQuery = document.querySelector('input[name="q"]');
        var sortBy = document.querySelector('select[name="sort"]');
        
        AnalyticsTracker.track('Dataset Search Submitted', {
          search_query: searchQuery ? searchQuery.value : '',
          sort_by: sortBy ? sortBy.value : 'relevance',
          page: window.location.pathname,
          url: window.location.href
        });
      });
    }

    // Track search result clicks - improved selectors
    var datasetListItems = document.querySelectorAll('.dataset-item');
    datasetListItems.forEach(function(item, index) {
      var link = item.querySelector('.dataset-heading a, h3.dataset-heading a');
      if (link) {
        link.addEventListener('click', function(e) {
          var searchQuery = new URLSearchParams(window.location.search).get('q');
          
          AnalyticsTracker.track('Search Result Click-Through', {
            dataset_title: this.textContent.trim(),
            dataset_url: this.href,
            search_query: searchQuery || '',
            result_position: index + 1
          });
        });
      }
    });
    
    // Also track direct heading clicks (fallback)
    if (datasetListItems.length === 0) {
      var headingLinks = document.querySelectorAll('.dataset-heading a');
      headingLinks.forEach(function(link, index) {
        link.addEventListener('click', function(e) {
          var searchQuery = new URLSearchParams(window.location.search).get('q');
          
          AnalyticsTracker.track('Search Result Click-Through', {
            dataset_title: this.textContent.trim(),
            dataset_url: this.href,
            search_query: searchQuery || '',
            result_position: index + 1
          });
        });
      });
    }
  }

  // Dataset Page View Tracking
  function trackDatasetPageView() {
    var datasetPage = document.querySelector('.package-read, [data-module="dataset-view"]');
    if (datasetPage) {
      var datasetId = datasetPage.getAttribute('data-dataset-id') || 
                      document.querySelector('meta[property="og:url"]')?.content.split('/').pop();
      var datasetTitle = document.querySelector('h1.page-heading')?.textContent.trim() || 
                         document.querySelector('meta[property="og:title"]')?.content;
      var organizationName = document.querySelector('.dataset-organization')?.textContent.trim();
      var hasDOI = document.querySelector('.doi-badge, [data-doi]') !== null;
      
      AnalyticsTracker.track('Dataset Page View', {
        dataset_id: datasetId,
        dataset_title: datasetTitle,
        organization: organizationName,
        has_doi: hasDOI,
        page_url: window.location.href,
        referrer: document.referrer,
        view_timestamp: new Date().toISOString()
      });
    }
  }

  // Resource Download Tracking
  function initDownloadTracking() {
    var downloadLinks = document.querySelectorAll('a[href*="/download/"], .resource-url-analytics, a.resource-url');
    var downloadStartTimes = {};
    
    downloadLinks.forEach(function(link) {
      link.addEventListener('click', function(e) {
        var resourceUrl = this.href;
        var resourceName = this.getAttribute('data-resource-name') || 
                          this.closest('.resource-item')?.querySelector('.heading')?.textContent.trim() ||
                          this.textContent.trim();
        var resourceFormat = this.getAttribute('data-format') || 
                            this.closest('.resource-item')?.querySelector('.format-label')?.textContent.trim();
        var datasetId = document.querySelector('[data-dataset-id]')?.getAttribute('data-dataset-id');
        var downloadId = 'download_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        
        // Store download start time
        downloadStartTimes[downloadId] = Date.now();
        sessionStorage.setItem('last_download_id', downloadId);
        sessionStorage.setItem('last_download_start', downloadStartTimes[downloadId]);
        
        AnalyticsTracker.track('Resource Download Click', {
          download_id: downloadId,
          resource_url: resourceUrl,
          resource_name: resourceName,
          resource_format: resourceFormat,
          dataset_id: datasetId,
          click_timestamp: new Date().toISOString()
        });

        // Track download completion (attempt via beacon on page unload)
        setTimeout(function() {
          AnalyticsTracker.track('Download Completion', {
            download_id: downloadId,
            resource_url: resourceUrl,
            resource_name: resourceName,
            completion_status: 'initiated'
          });
        }, 1000);
      });
    });

    // Track time to first download
    var isFirstDownload = !sessionStorage.getItem('has_downloaded');
    if (isFirstDownload) {
      var sessionStart = sessionStorage.getItem('session_start');
      if (!sessionStart) {
        sessionStart = Date.now();
        sessionStorage.setItem('session_start', sessionStart);
      }

      downloadLinks.forEach(function(link) {
        link.addEventListener('click', function() {
          if (!sessionStorage.getItem('has_downloaded')) {
            var timeToFirstDownload = Date.now() - parseInt(sessionStart);
            
            AnalyticsTracker.track('Time to First Download', {
              time_to_download_ms: timeToFirstDownload,
              time_to_download_seconds: Math.round(timeToFirstDownload / 1000),
              session_start: new Date(parseInt(sessionStart)).toISOString()
            });
            
            sessionStorage.setItem('has_downloaded', 'true');
          }
        });
      });
    }
  }

  // Track form interactions (dataset creation/update)
  function initFormTracking() {
    var datasetForm = document.querySelector('form.dataset-form, #dataset-edit');
    
    if (datasetForm) {
      var isEdit = window.location.pathname.includes('/edit');
      var startTime = Date.now();
      
      datasetForm.addEventListener('submit', function(e) {
        var formData = new FormData(this);
        var datasetTitle = formData.get('title') || formData.get('name');
        var hasResources = document.querySelectorAll('.resource-item').length > 0;
        var timeSpent = Math.round((Date.now() - startTime) / 1000);
        
        if (isEdit) {
          AnalyticsTracker.track('Update Existing Dataset', {
            dataset_title: datasetTitle,
            has_resources: hasResources,
            time_spent_seconds: timeSpent,
            form_completion_timestamp: new Date().toISOString()
          });
        } else {
          AnalyticsTracker.track('Dataset Created', {
            dataset_title: datasetTitle,
            has_resources: hasResources,
            time_spent_seconds: timeSpent,
            creation_timestamp: new Date().toISOString()
          });
        }
      });
    }
  }

  // Track DOI publication
  function initDOITracking() {
    // Track DOI creation button clicks - multiple selectors for different DOI plugin versions
    var doiSelectors = [
      'a[href*="doi/create"]',
      'button[name="doi"]',
      '[data-action="create-doi"]',
      '.btn-doi-create',
      'a.btn-doi',
      'form[action*="doi"] button[type="submit"]'
    ];
    
    doiSelectors.forEach(function(selector) {
      var doiButtons = document.querySelectorAll(selector);
      doiButtons.forEach(function(button) {
        button.addEventListener('click', function(e) {
          var datasetId = this.getAttribute('data-dataset-id') || 
                         this.getAttribute('data-package-id') ||
                         document.querySelector('[data-dataset-id]')?.getAttribute('data-dataset-id') ||
                         window.location.pathname.split('/dataset/')[1]?.split('/')[0];
          var datasetTitle = document.querySelector('h1.page-heading, h1')?.textContent.trim();
          
          AnalyticsTracker.track('Dataset Published with DOI', {
            dataset_id: datasetId,
            dataset_title: datasetTitle,
            doi_button_selector: selector,
            doi_request_timestamp: new Date().toISOString()
          });
          
          console.log('DOI creation tracked:', datasetId, datasetTitle);
        });
      });
    });

    // Track DOI badge clicks (potential citations)
    var doiBadges = document.querySelectorAll('.doi-badge, [data-doi] a, a[href*="doi.org"]');
    doiBadges.forEach(function(badge) {
      badge.addEventListener('click', function() {
        var doi = this.getAttribute('data-doi') || 
                 this.textContent.trim() ||
                 this.href.split('doi.org/')[1];
        var datasetId = document.querySelector('[data-dataset-id]')?.getAttribute('data-dataset-id');
        
        AnalyticsTracker.track('DOI-Based Citation', {
          doi: doi,
          dataset_id: datasetId,
          citation_link_clicked: this.href,
          click_timestamp: new Date().toISOString()
        });
      });
    });
  }

  // Initialize session tracking
  function initSessionTracking() {
    if (!sessionStorage.getItem('session_id')) {
      var sessionId = 'session_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
      sessionStorage.setItem('session_id', sessionId);
      sessionStorage.setItem('session_start', Date.now());
    }
  }

  // Initialize all tracking on page load
  function init() {
    // Wait for DOM to be ready
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', function() {
        initializeTracking();
      });
    } else {
      initializeTracking();
    }
  }

  function initializeTracking() {
    initSessionTracking();
    initSearchTracking();
    trackDatasetPageView();
    initDownloadTracking();
    initFormTracking();
    initDOITracking();

    console.log('Analytics tracking initialized');
  }

  // Expose tracker globally for custom events
  window.CKANAnalytics = AnalyticsTracker;

  // Start initialization
  init();

})(window, document);
