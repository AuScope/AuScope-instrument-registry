/**
 * Party Tree Module
 *
 * Renders a hierarchical checkbox tree of parties in the search sidebar.
 *
 * Modes:
 *   1. Embedded: data-nodes attribute contains pre-rendered JSON nodes.
 *   2. API: fetches nodes from data-api-url (default /api/instrument_parties).
 *      Results cached in sessionStorage.
 *
 * Common attributes:
 *   data-filter-param      URL param to toggle (default: owner_party)
 *   data-is-platform       passed to API
 *   data-select-all-label  label for the "All" checkbox
 *   data-active-filters    JSON array of active filter values
 */
this.ckan.module('party-tree-module', function ($, _) {
  'use strict';

  return {
    /* ------------------------------------------------------------------ */
    /* Initialisation                                                      */
    /* ------------------------------------------------------------------ */
    initialize: function () {
      var self = this;

      self._isPlatform      = (self.el.data('is-platform') || 'false').toString();
      self._filterParam     = self.el.data('filter-param') || 'owner_party';
      self._selectAllLabel  = self.el.data('select-all-label') || 'All';

      // Parse active filters from data attribute, with URL params as override
      var rawFilters = [];
      try {
        rawFilters = self.el.data('active-filters') || [];
        if (!Array.isArray(rawFilters)) {
          rawFilters = JSON.parse(rawFilters);
        }
      } catch (e) {
        rawFilters = [];
      }

      // URL params override server-rendered value
      var urlParams = new URLSearchParams(window.location.search);
      var urlFilters = urlParams.getAll(self._filterParam);
      if (urlFilters.length > 0) {
        rawFilters = urlFilters;
      }

      // Use a Set for O(1) membership checks
      self._activeFilterSet = new Set(rawFilters);

      // Embedded-nodes mode: server rendered the tree data into the HTML
      var embeddedNodes = self.el.data('nodes');
      if (embeddedNodes !== undefined) {
        self._render(Array.isArray(embeddedNodes) ? embeddedNodes : []);
        return;
      }

      // API mode — try sessionStorage cache first.
      // Cache entries are keyed by URL and validated against a server-side
      // version number (cache_version) returned by the API.  When a party is
      // created/updated/deleted the server increments the version, so the
      // stored entry is treated as a miss and fresh data is fetched.
      var apiUrl = self.el.data('api-url') ||
                   '/api/instrument_parties?is_platform=' + encodeURIComponent(self._isPlatform);
      var cacheKey = 'party-tree:' + apiUrl;

      try {
        var cached = sessionStorage.getItem(cacheKey);
        if (cached) {
          var _ss0 = Date.now();
          var entry = JSON.parse(cached);
          // entry must have {version, nodes}; plain node arrays from old
          // cache format are intentionally treated as misses.
          if (entry && typeof entry.version !== 'undefined' && Array.isArray(entry.nodes)) {
            // Validate the stored version against the server before using.
            $.getJSON('/api/party_cache_version')
              .done(function (versionData) {
                if (versionData.version === entry.version) {
                  console.log('[PERF party-tree] ' + self._filterParam + ': sessionStorage HIT (v' + entry.version + ', ' + entry.nodes.length + ' nodes), parse: ' + (Date.now() - _ss0) + 'ms');
                  var _r0 = Date.now();
                  self._render(entry.nodes);
                  console.log('[PERF party-tree] ' + self._filterParam + ': render from cache: ' + (Date.now() - _r0) + 'ms');
                } else {
                  // Server version changed — stale cache; fetch fresh.
                  console.log('[PERF party-tree] ' + self._filterParam + ': sessionStorage STALE (stored v' + entry.version + ', server v' + versionData.version + ') — refetching');
                  self._fetchAndRender(apiUrl, cacheKey);
                }
              })
              .fail(function () {
                // Version check failed — fall back to fetching fresh data.
                self._fetchAndRender(apiUrl, cacheKey);
              });
            return;
          }
        }
      } catch (e) { /* storage unavailable or corrupt — fall through to fetch */ }

      self._fetchAndRender(apiUrl, cacheKey);
    },

    /* ------------------------------------------------------------------ */
    /* Fetch from API, cache, and render                                   */
    /* ------------------------------------------------------------------ */
    _fetchAndRender: function (apiUrl, cacheKey) {
      var self = this;
      var _fetchStart = Date.now();
      console.log('[PERF party-tree] ' + self._filterParam + ': sessionStorage MISS — fetching ' + apiUrl);

      $.getJSON(apiUrl)
        .done(function (data) {
          var _fetchMs = Date.now() - _fetchStart;
          var nodes = data.nodes || [];
          console.log('[PERF party-tree] ' + self._filterParam + ': API fetch done in ' + _fetchMs + 'ms (' + nodes.length + ' nodes)');
          // Store nodes alongside the server version so we can validate on
          // the next page load without fetching the full data set again.
          try {
            sessionStorage.setItem(cacheKey, JSON.stringify({
              version: data.cache_version,
              nodes: nodes
            }));
          } catch (e) { /* quota */ }
          var _r0 = Date.now();
          self._render(nodes);
          console.log('[PERF party-tree] ' + self._filterParam + ': render: ' + (Date.now() - _r0) + 'ms');
        })
        .fail(function (jqXHR, textStatus) {
          console.error('[PERF party-tree] ' + self._filterParam + ': API fetch FAILED after ' + (Date.now() - _fetchStart) + 'ms — status: ' + textStatus + ' (' + jqXHR.status + ')');
          self.el.find('.party-tree-loading').text('Could not load parties.');
        });
    },

    /* ------------------------------------------------------------------ */
    /* Build and render the tree                                           */
    /* ------------------------------------------------------------------ */
    _render: function (nodes) {
      var self = this;
      if (!nodes || nodes.length === 0) {
        self.el.find('.party-tree-loading').text('No parties found.');
        return;
      }

      self._nodeMap = {};
      nodes.forEach(function (n) { self._nodeMap[n.id] = n; });

      // Build children map  { parent_id: [child_node, ...] }
      var childrenMap = {};
      nodes.forEach(function (n) {
        var pid = n.parent_id || '__root__';
        if (!childrenMap[pid]) { childrenMap[pid] = []; }
        childrenMap[pid].push(n);
      });

      Object.keys(childrenMap).forEach(function (pid) {
        childrenMap[pid].sort(function (a, b) {
          return (a.title || a.id).localeCompare(b.title || b.id);
        });
      });

      // Precompute total counts and active-descendant flags
      var totalCountMap = {};      // nodeId → cumulative count
      var hasActiveDescMap = {};   // nodeId → boolean

      function precompute(nodeId) {
        var node = self._nodeMap[nodeId];
        var own  = node ? (node.count || 0) : 0;
        var children = childrenMap[nodeId] || [];
        var childSum = 0;
        var anyActive = false;
        children.forEach(function (c) {
          precompute(c.id);
          childSum += totalCountMap[c.id];
          if (self._activeFilterSet.has(c.id) || hasActiveDescMap[c.id]) {
            anyActive = true;
          }
        });
        totalCountMap[nodeId] = own + childSum;
        hasActiveDescMap[nodeId] = anyActive;
      }

      // Run precompute from every root
      (childrenMap['__root__'] || []).forEach(function (n) { precompute(n.id); });

      var $container = self.el.find('.party-tree-container');
      $container.empty();                       // guard against duplicate init

      // Build all DOM into a detached fragment
      var $frag = $(document.createDocumentFragment());

      // "Select All" checkbox
      var allChecked   = self._activeFilterSet.size === 0;
      var cbAllId      = 'party-tree-select-all-' + self._filterParam;
      var $selectAllRow = $('<div class="party-tree-select-all"></div>');
      var $selectAllCb  = $('<input type="checkbox">').attr('id', cbAllId).prop('checked', allChecked);
      var $selectAllLbl = $('<label>').attr('for', cbAllId).text(self._selectAllLabel);
      $selectAllRow.append($selectAllCb).append($selectAllLbl);
      $frag.append($selectAllRow);

      // Render root nodes
      var roots = childrenMap['__root__'] || [];
      roots.forEach(function (node) {
        $frag.append(self._buildNode(node, childrenMap, totalCountMap, hasActiveDescMap));
      });

      $container.append($frag);
      self.el.find('.party-tree-loading').hide();
      $container.show();

      self._bindEvents($container, $selectAllCb, childrenMap);
    },

    /* ------------------------------------------------------------------ */
    /* Build a single tree node (recursive)                                */
    /* ------------------------------------------------------------------ */
    _buildNode: function (node, childrenMap, totalCountMap, hasActiveDescMap) {
      var self = this;
      var children    = childrenMap[node.id] || [];
      var hasChildren = children.length > 0;
      var total       = totalCountMap[node.id] || 0;
      var cbId        = 'fac-' + node.id.replace(/[^a-zA-Z0-9_-]/g, '_');
      var isChecked   = self._activeFilterSet.has(node.id);

      var $wrapper = $('<div class="party-tree-node"></div>').attr('data-node-id', node.id);
      if (isChecked) { $wrapper.addClass('checked'); }

      var $row = $('<div class="party-tree-row"></div>');

      var $toggle = $('<span class="party-tree-toggle"></span>');
      if (hasChildren) {
        $toggle.html('&#9658;'); // ▶
        $toggle.addClass('has-children');
      }
      $row.append($toggle);

      var $cb = $('<input type="checkbox">')
        .attr('id', cbId)
        .attr('data-node-id', node.id)
        .prop('checked', isChecked);

      var $lbl = $('<label></label>').attr('for', cbId);
      $lbl.append($('<span class="party-tree-name"></span>').text(node.title || node.id));
      if (total > 0) {
        $lbl.append($('<span class="party-tree-count"></span>').text('(' + total + ')'));
      }

      $row.append($cb).append($lbl);
      $wrapper.append($row);

      if (hasChildren) {
        var $childContainer = $('<div class="party-tree-children" style="display:none;"></div>');
        children.forEach(function (child) {
          $childContainer.append(self._buildNode(child, childrenMap, totalCountMap, hasActiveDescMap));
        });
        $wrapper.append($childContainer);

        // Auto-expand if any descendant is active
        if (hasActiveDescMap[node.id]) {
          $childContainer.show();
          $toggle.html('&#9660;'); // ▼
        }
      }

      return $wrapper;
    },

    /* ------------------------------------------------------------------ */
    /* Event binding                                                       */
    /* ------------------------------------------------------------------ */
    _bindEvents: function ($container, $selectAllCb, childrenMap) {
      var self = this;
      var ns = '.partyTree';

      // Remove previous handlers to prevent stacking on re-init
      $container.off(ns);
      $selectAllCb.off(ns);

      $container.on('click' + ns, '.party-tree-toggle.has-children', function () {
        var $toggle     = $(this);
        var $childCont  = $toggle.closest('.party-tree-node').children('.party-tree-children');
        var isOpen      = $childCont.is(':visible');
        $childCont.toggle(!isOpen);
        $toggle.html(isOpen ? '&#9658;' : '&#9660;');
      });

      $container.on('change' + ns, 'input[type="checkbox"][data-node-id]', function () {
        var $cb       = $(this);
        var nodeId    = $cb.attr('data-node-id');
        var checked   = $cb.prop('checked');
        var $nodeDiv  = $cb.closest('.party-tree-node');

        // Cascade to all descendants
        var $childCbs = $nodeDiv.find('.party-tree-children input[type="checkbox"][data-node-id]');
        $childCbs.prop('checked', checked);

        // Update .checked class
        $nodeDiv.toggleClass('checked', checked);
        $childCbs.closest('.party-tree-node').toggleClass('checked', checked);

        $selectAllCb.prop('checked', false);
        self._applyFilters($container);
      });

      $selectAllCb.on('change' + ns, function () {
        if ($selectAllCb.prop('checked')) {
          $container.find('input[type="checkbox"][data-node-id]').prop('checked', false);
          $container.find('.party-tree-node.checked').removeClass('checked');
          self._navigateTo([]);
        }
      });
    },

    /* ------------------------------------------------------------------ */
    /* Collect checked IDs and navigate                                    */
    /* ------------------------------------------------------------------ */
    _applyFilters: function ($container) {
      var self = this;
      var seen = {};
      var ids  = [];
      $container.find('input[type="checkbox"][data-node-id]:checked').each(function () {
        var nid = $(this).attr('data-node-id');
        if (nid && !seen[nid]) {
          seen[nid] = true;
          ids.push(nid);
        }
      });
      self._navigateTo(ids);
    },

    /* ------------------------------------------------------------------ */
    /* Build URL and reload                                                */
    /* ------------------------------------------------------------------ */
    _navigateTo: function (ids) {
      // Full page reload; AJAX-only filtering could be a future enhancement.
      var params = new URLSearchParams(window.location.search);
      params.delete(this._filterParam);
      params.delete('page'); // reset pagination when filter changes
      ids.forEach(function (id) { params.append(this._filterParam, id); }, this);
      window.location.search = params.toString();
    }
  };
});
