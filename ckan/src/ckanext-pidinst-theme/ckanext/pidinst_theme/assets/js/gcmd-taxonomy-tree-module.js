/**
 * gcmd-taxonomy-tree-module.js
 *
 * Lazy-loading tree for GCMD vocabularies on the /taxonomies page.
 * Uses the existing /api/proxy/fetch_gcmd endpoint (paginated + search)
 * and /api/proxy/fetch_gcmd_narrower for child concepts.
 *
 * Concept URIs from ARDC are canonical NASA CMR URIs. For clickable links
 * we construct ARDC resource viewer URLs.
 */
(function () {
  'use strict';

  /* ── state ─────────────────────────────────────────────────── */
  var SCHEMES = ['instruments', 'platforms', 'measured_variables'];
  var rootLoaded = {};           // scheme -> bool
  var searchTimer = null;
  var searchPage = {};           // scheme -> next page number for search
  var lastSearchTerm = '';

  /* ── ARDC vocab paths (must match the backend VOCAB_ENDPOINTS) ── */
  var VOCAB_PATHS = {
    'instruments':        'ardc-curated/gcmd-instruments/22-8-2026-02-13',
    'platforms':          'ardc-curated/gcmd-platforms/21-5-2025-06-17',
    'measured_variables': 'ardc-curated/gcmd-measurementname/21-5-2025-06-06'
  };
  var ARDC_BASE = 'https://vocabs.ardc.edu.au/repository/api/lda';

  /**
   * Build an ARDC resource viewer URL for a concept URI within a scheme.
   */
  function ardcViewerUrl(conceptUri, scheme) {
    var path = VOCAB_PATHS[scheme];
    if (!path || !conceptUri) return '';
    return ARDC_BASE + '/' + path + '/resource?uri=' + encodeURIComponent(conceptUri);
  }

  /* ── helpers ────────────────────────────────────────────────── */

  function buildTermLi(item, scheme) {
    var label = item.prefLabel ? item.prefLabel._value : (item.label || item.text || '');
    var uri = item._about || item.uri || '';
    var hasNarrower = item.narrower && item.narrower.length > 0;

    var li = document.createElement('li');
    li.className = 'taxonomy-node gcmd-term-node';
    li.setAttribute('data-uri', uri);
    li.setAttribute('data-scheme', scheme || '');

    var row = document.createElement('div');
    row.className = 'taxonomy-node-row';

    // toggle
    var toggle = document.createElement('span');
    toggle.className = 'taxonomy-toggle gcmd-child-toggle';
    toggle.title = 'Expand/collapse';
    if (hasNarrower) {
      toggle.innerHTML = '<i class="fa fa-caret-right"></i>';
      toggle.style.cursor = 'pointer';
    } else {
      toggle.innerHTML = '<i class="fa fa-circle-o fa-xs"></i>';
    }
    row.appendChild(toggle);

    // label (clickable link to ARDC resource viewer page)
    var a = document.createElement('a');
    a.className = 'taxonomy-label';
    a.textContent = label;
    var viewUrl = ardcViewerUrl(uri, scheme);
    if (viewUrl) {
      a.href = viewUrl;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
    }
    row.appendChild(a);

    li.appendChild(row);

    if (hasNarrower) {
      var childUl = document.createElement('ul');
      childUl.className = 'taxonomy-children gcmd-children';
      childUl.style.display = 'none';
      var loader = document.createElement('li');
      loader.className = 'gcmd-loading';
      loader.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Loading…';
      childUl.appendChild(loader);
      li.appendChild(childUl);
      li.setAttribute('data-children-loaded', 'false');
    }

    return li;
  }

  function renderItems(ul, items, scheme) {
    // Remove the loading spinner
    var loader = ul.querySelector('.gcmd-loading');
    if (loader) loader.remove();

    items.forEach(function (item) {
      ul.appendChild(buildTermLi(item, scheme));
    });

    if (items.length === 0 && ul.children.length === 0) {
      var empty = document.createElement('li');
      empty.className = 'text-muted';
      empty.textContent = 'No terms found.';
      ul.appendChild(empty);
    }
  }

  /* ── fetch top-level concepts for a scheme ─────────────────── */

  function loadRootConcepts(root) {
    var scheme = root.getAttribute('data-gcmd-scheme');
    if (rootLoaded[scheme]) return;
    rootLoaded[scheme] = true;

    var ul = root.querySelector('.gcmd-children');

    fetch('/api/proxy/fetch_gcmd?scheme=' + encodeURIComponent(scheme) + '&page=0&keywords=')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var items = (data.result && data.result.items) ? data.result.items : [];
        renderItems(ul, items, scheme);

        // If there are more pages, add a "load more" link
        if (data.result && data.result.next) {
          appendLoadMore(ul, scheme, (data.result.page || 0) + 1);
        }
      })
      .catch(function () {
        var loader = ul.querySelector('.gcmd-loading');
        if (loader) loader.innerHTML = '<span class="text-danger">Failed to load.</span>';
      });
  }

  function appendLoadMore(ul, scheme, page) {
    var li = document.createElement('li');
    li.className = 'gcmd-load-more-item';
    var btn = document.createElement('button');
    btn.className = 'btn btn-default btn-xs';
    btn.textContent = 'Load more…';
    btn.addEventListener('click', function () {
      btn.disabled = true;
      btn.innerHTML = '<i class="fa fa-spinner fa-spin"></i> Loading…';
      fetch('/api/proxy/fetch_gcmd?scheme=' + encodeURIComponent(scheme) + '&page=' + page + '&keywords=')
        .then(function (r) { return r.json(); })
        .then(function (data) {
          li.remove();
          var items = (data.result && data.result.items) ? data.result.items : [];
          items.forEach(function (item) {
            ul.appendChild(buildTermLi(item, scheme));
          });
          if (data.result && data.result.next) {
            appendLoadMore(ul, scheme, (data.result.page || 0) + 1);
          }
        });
    });
    li.appendChild(btn);
    ul.appendChild(li);
  }

  /* ── fetch narrower (child) concepts ───────────────────────── */

  function loadNarrower(li) {
    if (li.getAttribute('data-children-loaded') === 'true') return;
    li.setAttribute('data-children-loaded', 'true');

    var uri = li.getAttribute('data-uri');
    var scheme = li.getAttribute('data-scheme') || '';
    var ul = li.querySelector('.gcmd-children');

    fetch('/api/proxy/fetch_gcmd_narrower?uri=' + encodeURIComponent(uri) + '&scheme=' + encodeURIComponent(scheme))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var items = data.items || [];
        renderItems(ul, items, scheme);
      })
      .catch(function () {
        var loader = ul.querySelector('.gcmd-loading');
        if (loader) loader.innerHTML = '<span class="text-danger">Failed to load.</span>';
      });
  }

  /* ── toggle handler ────────────────────────────────────────── */

  function toggleNode(toggle) {
    var node = toggle.closest('.gcmd-term-node, .gcmd-root');
    if (!node) return;

    var childUl = node.querySelector(':scope > .taxonomy-children, :scope > .gcmd-children');
    if (!childUl) return;

    var icon = toggle.querySelector('i');
    var isOpen = childUl.style.display !== 'none';

    if (isOpen) {
      childUl.style.display = 'none';
      if (icon) { icon.className = 'fa fa-caret-right'; }
    } else {
      childUl.style.display = 'block';
      if (icon) { icon.className = 'fa fa-caret-down'; }

      // Lazy-load if this is a GCMD root node
      if (node.classList.contains('gcmd-root')) {
        loadRootConcepts(node);
      }
      // Lazy-load narrower concepts for child nodes
      if (node.classList.contains('gcmd-term-node') && node.getAttribute('data-children-loaded') === 'false') {
        loadNarrower(node);
      }
    }
  }

  /* ── search ────────────────────────────────────────────────── */

  function doSearch(term) {
    var resultsDiv = document.getElementById('gcmd-search-results');
    var treeDiv = document.getElementById('gcmd-tree-container');
    var heading = document.getElementById('gcmd-search-results-heading');
    var list = document.getElementById('gcmd-search-results-list');
    var moreDiv = document.getElementById('gcmd-search-results-more');
    var spinner = document.getElementById('gcmd-search-spinner');

    if (!term || term.length < 2) {
      resultsDiv.style.display = 'none';
      treeDiv.style.display = 'block';
      return;
    }

    treeDiv.style.display = 'none';
    resultsDiv.style.display = 'block';
    list.innerHTML = '';
    moreDiv.style.display = 'none';
    spinner.style.display = 'block';
    heading.textContent = 'Results for "' + term + '"';
    lastSearchTerm = term;

    // Search across all three schemes
    SCHEMES.forEach(function (scheme) {
      searchPage[scheme] = 0;
    });

    var completed = 0;
    var totalResults = 0;

    SCHEMES.forEach(function (scheme) {
      fetchSearchResults(scheme, term, 0, function (items, hasMore) {
        completed++;
        totalResults += items.length;

        if (items.length > 0) {
          var schemeHeading = document.createElement('li');
          schemeHeading.className = 'list-group-item gcmd-scheme-heading';
          var schemeLabel = scheme.replace(/_/g, ' ');
          schemeLabel = schemeLabel.charAt(0).toUpperCase() + schemeLabel.slice(1);
          schemeHeading.innerHTML = '<strong>' + schemeLabel + '</strong>';
          list.appendChild(schemeHeading);

          items.forEach(function (item) {
            var li = document.createElement('li');
            li.className = 'list-group-item gcmd-search-item';
            var label = item.prefLabel ? item.prefLabel._value : '';
            var uri = item._about || '';
            var definition = '';
            if (item.definition) {
              definition = (typeof item.definition === 'object' && item.definition._value)
                ? item.definition._value
                : (typeof item.definition === 'string' ? item.definition : '');
            }
            var labelHtml = uri
              ? '<a class="gcmd-search-label" href="' + escapeHtml(uri) + '" target="_blank" rel="noopener noreferrer">' + escapeHtml(label) + '</a>'
              : '<span class="gcmd-search-label">' + escapeHtml(label) + '</span>';
            li.innerHTML = labelHtml +
              (definition ? '<br><small class="text-muted gcmd-search-definition">' + escapeHtml(definition) + '</small>' : '');
            list.appendChild(li);
          });
        }

        if (completed === SCHEMES.length) {
          spinner.style.display = 'none';
          if (totalResults === 0) {
            list.innerHTML = '<li class="list-group-item text-muted">No GCMD keywords found.</li>';
          }
        }
      });
    });
  }

  function fetchSearchResults(scheme, term, page, callback) {
    fetch('/api/proxy/fetch_gcmd?scheme=' + encodeURIComponent(scheme) +
          '&page=' + page + '&keywords=' + encodeURIComponent(term))
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var items = (data.result && data.result.items) ? data.result.items : [];
        var hasMore = !!(data.result && data.result.next);
        callback(items, hasMore);
      })
      .catch(function () {
        callback([], false);
      });
  }

  function escapeHtml(str) {
    var div = document.createElement('div');
    div.appendChild(document.createTextNode(str));
    return div.innerHTML;
  }

  /* ── initialization ────────────────────────────────────────── */

  function init() {
    // Delegate click on GCMD toggles only (custom tree has its own handler)
    var gcmdSection = document.querySelector('.gcmd-taxonomy-section');
    if (gcmdSection) {
      gcmdSection.addEventListener('click', function (e) {
        var toggle = e.target.closest('.gcmd-toggle, .gcmd-child-toggle');
        if (toggle) {
          e.preventDefault();
          e.stopPropagation();
          toggleNode(toggle);
        }
      });
    }

    // GCMD search box
    var searchInput = document.getElementById('gcmd-search');
    if (searchInput) {
      searchInput.addEventListener('input', function () {
        clearTimeout(searchTimer);
        var val = searchInput.value.trim();
        searchTimer = setTimeout(function () {
          doSearch(val);
        }, 400);
      });
    }
  }

  /* ── run on DOM ready ──────────────────────────────────────── */
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
