/**
 * Party Tree Module
 *
 * Renders a hierarchical checkbox tree of parties (CKAN groups of type
 * "party") in the search page sidebar.  Checking items filters the
 * result set via the `owner_party` URL parameter (multi-value, OR logic).
 *
 * Nodes are fetched from /api/instrument_parties which now reads from
 * CKAN groups, returning {id, title, parent_id, contact, count}.
 */
this.ckan.module('party-tree-module', function ($, _) {
  'use strict';

  return {
    /* ------------------------------------------------------------------ */
    /* Initialisation                                                       */
    /* ------------------------------------------------------------------ */
    initialize: function () {
      var self = this;

      self._isPlatform = (self.el.data('is-platform') || 'false').toString();

      // Active filters from the server-rendered data attribute
      try {
        self._activeFilters = JSON.parse(self.el.attr('data-active-filters') || '[]');
      } catch (e) {
        self._activeFilters = [];
      }

      // Also read directly from the current URL in case of client navigation
      var urlParams = new URLSearchParams(window.location.search);
      var urlFilters = urlParams.getAll('owner_party');
      if (urlFilters.length > 0) {
        self._activeFilters = urlFilters;
      }

      var apiUrl = '/api/instrument_parties?is_platform=' + encodeURIComponent(self._isPlatform);

      $.getJSON(apiUrl)
        .done(function (data) {
          self._render(data.nodes || []);
        })
        .fail(function () {
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

      // Store nodeMap on self for _totalCount
      self._nodeMap = {};
      nodes.forEach(function (n) { self._nodeMap[n.id] = n; });

      // Build children map  { parent_id: [child_node, ...] }
      var childrenMap = {};
      nodes.forEach(function (n) {
        var pid = n.parent_id || '__root__';
        if (!childrenMap[pid]) { childrenMap[pid] = []; }
        childrenMap[pid].push(n);
      });

      // Sort children alphabetically by title
      Object.keys(childrenMap).forEach(function (pid) {
        childrenMap[pid].sort(function (a, b) {
          return (a.title || a.id).localeCompare(b.title || b.id);
        });
      });

      var $container = self.el.find('.party-tree-container');

      // ---- "Select All" root checkbox --------------------------------- //
      var allChecked = self._activeFilters.length === 0;
      var $selectAllRow = $('<div class="party-tree-select-all"></div>');
      var $selectAllCb  = $('<input type="checkbox" id="party-tree-select-all">');
      $selectAllCb.prop('checked', allChecked);
      var $selectAllLbl = $('<label for="party-tree-select-all">All Parties</label>');
      $selectAllRow.append($selectAllCb).append($selectAllLbl);
      $container.append($selectAllRow);

      // ---- Render root nodes ------------------------------------------ //
      var roots = childrenMap['__root__'] || [];
      roots.forEach(function (node) {
        $container.append(self._buildNode(node, childrenMap, 0));
      });

      // Show container, hide loader
      self.el.find('.party-tree-loading').hide();
      $container.show();

      // ---- Wire up events --------------------------------------------- //
      self._bindEvents($container, $selectAllCb, childrenMap);
    },

    /* ------------------------------------------------------------------ */
    /* Build a single tree node element (recursive)                        */
    /* ------------------------------------------------------------------ */
    _buildNode: function (node, childrenMap, depth) {
      var self = this;
      var children    = childrenMap[node.id] || [];
      var hasChildren = children.length > 0;
      var total       = self._totalCount(node.id, childrenMap);
      var cbId        = 'fac-' + node.id.replace(/[^a-zA-Z0-9_-]/g, '_');
      var isChecked   = self._activeFilters.indexOf(node.id) !== -1;

      var $wrapper = $('<div class="party-tree-node"></div>').attr('data-node-id', node.id);
      if (isChecked) { $wrapper.addClass('checked'); }

      // Row: toggle + checkbox + label + count
      var $row = $('<div class="party-tree-row"></div>');

      // Expand/collapse toggle
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

      // Children container (collapsed by default unless a child is active)
      if (hasChildren) {
        var $childContainer = $('<div class="party-tree-children" style="display:none;"></div>');
        children.forEach(function (child) {
          $childContainer.append(self._buildNode(child, childrenMap, depth + 1));
        });
        $wrapper.append($childContainer);

        // Auto-expand if any descendant is in active filters
        if (self._anyDescendantActive(node.id, childrenMap)) {
          $childContainer.show();
          $toggle.html('&#9660;'); // ▼
        }
      }

      return $wrapper;
    },

    /* ------------------------------------------------------------------ */
    /* Recursive total-count helper                                        */
    /* ------------------------------------------------------------------ */
    _totalCount: function (nodeId, childrenMap) {
      var self = this;
      var node = self._nodeMap && self._nodeMap[nodeId];
      var own  = node ? (node.count || 0) : 0;
      var children = childrenMap[nodeId] || [];
      var childSum = 0;
      children.forEach(function (c) {
        childSum += self._totalCount(c.id, childrenMap);
      });
      return own + childSum;
    },

    /* ------------------------------------------------------------------ */
    /* Check whether any descendant is in active filters                   */
    /* ------------------------------------------------------------------ */
    _anyDescendantActive: function (nodeId, childrenMap) {
      var self = this;
      var children = childrenMap[nodeId] || [];
      for (var i = 0; i < children.length; i++) {
        var child = children[i];
        if (self._activeFilters.indexOf(child.id) !== -1) { return true; }
        if (self._anyDescendantActive(child.id, childrenMap)) { return true; }
      }
      return false;
    },

    /* ------------------------------------------------------------------ */
    /* Event binding                                                       */
    /* ------------------------------------------------------------------ */
    _bindEvents: function ($container, $selectAllCb, childrenMap) {
      var self = this;

      // ---- Toggle expand/collapse for nodes with children ------------- //
      $container.on('click', '.party-tree-toggle.has-children', function () {
        var $toggle     = $(this);
        var $childCont  = $toggle.closest('.party-tree-node').children('.party-tree-children');
        var isOpen      = $childCont.is(':visible');
        $childCont.toggle(!isOpen);
        $toggle.html(isOpen ? '&#9658;' : '&#9660;');
      });

      // ---- Individual checkbox change --------------------------------- //
      $container.on('change', 'input[type="checkbox"][data-node-id]', function () {
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

        // Uncheck "Select All" if anything is individually checked
        $selectAllCb.prop('checked', false);

        self._applyFilters($container);
      });

      // ---- Select All checkbox ---------------------------------------- //
      $selectAllCb.on('change', function () {
        if ($selectAllCb.prop('checked')) {
          // Uncheck everything and remove filter
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
      var self  = this;
      var ids = [];
      $container.find('input[type="checkbox"][data-node-id]:checked').each(function () {
        var nid = $(this).attr('data-node-id');
        if (nid && ids.indexOf(nid) === -1) {
          ids.push(nid);
        }
      });
      self._navigateTo(ids);
    },

    /* ------------------------------------------------------------------ */
    /* Build URL and reload                                                */
    /* ------------------------------------------------------------------ */
    _navigateTo: function (ids) {
      var params = new URLSearchParams(window.location.search);
      params.delete('owner_party');
      params.delete('page'); // reset pagination when filter changes
      ids.forEach(function (id) { params.append('owner_party', id); });
      window.location.search = params.toString();
    }
  };
});
