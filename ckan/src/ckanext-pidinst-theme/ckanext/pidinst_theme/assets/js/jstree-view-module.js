/**
 * jstree-view-module.js
 *
 * Recursive, lazy-loaded instrument family tree.
 *
 * Data flow:
 *  1. Reads data-related-identifiers (JSON from pkg.related_identifier_obj),
 *     filters HasPart/IsPartOf, lazy-loads deeper levels via package_show.
 *  2. Fallback: CKAN package_relationships_list (legacy parent_of).
 *
 * Key design decisions:
 *  - Multi-parent: same instrument may appear under multiple parents.
 *    Each display node gets a unique sequential id (nid()); real package
 *    id is in node.data.pkgId.
 *  - Cycle protection: ancestor chain per path; cycles show a placeholder.
 *  - Group nodes ("Is Part of"/"Has Part of") are lazy-loaded section headers.
 */
this.ckan.module('jstree-view-module', function ($, _) {
  'use strict';

  /* Sequential node-id generator – avoids collisions for multi-parent display */
  var _seq = 0;
  function nid() { return 'jtn-' + (++_seq); }

  return {

    initialize: function () {
      var self = this;
      this.packageId    = this.el.attr('data-id')    || '';
      this.packageTitle = this.el.attr('data-title') || this.packageId;
      this.packageName  = this.el.attr('data-name')  || this.packageId;

      /* In-memory caches */
      this._pkgCache = {};   // pkgId → resolved package object (with ._related)
      this._inflight = {};   // pkgId → jQuery Deferred  (de-dup in-flight reqs)

      this.$tree = this.el.find('.pidinst-family-tree');
      if (!this.$tree.length) {
        this.$tree = $('<div class="pidinst-family-tree"></div>');
        this.el.append(this.$tree);
      }

      /* Seed cache with root instrument data already on the page */
      var rootRelated = this._parseRelated(
        this.el.attr('data-related-identifiers') || ''
      );
      this._pkgCache[this.packageId] = {
        id:       this.packageId,
        title:    this.packageTitle,
        name:     this.packageName,
        _related: rootRelated
      };

      this._initTree();
    },

    /* ── JSON / relationship parsing ───────────────── */

    /** Parse a potentially double-encoded related_identifier_obj string. */
    _parseRelated: function (raw) {
      if (!raw) return [];
      try {
        var p = JSON.parse(raw);
        if (Array.isArray(p)) return p;
        if (typeof p === 'string') {
          var p2 = JSON.parse(p);
          return Array.isArray(p2) ? p2 : [];
        }
      } catch (e) { /* ignore */ }
      return [];
    },

    /**
     * Extract instrument-family entries from a related_identifier_obj list.
     * @returns {{ parents: Array<{pkgId:string, label:string}>,
     *             children: Array<{pkgId:string, label:string}> }}
     */
    _extractRelations: function (relatedList) {
      var parents = [], children = [];
      (relatedList || []).forEach(function (r) {
        var rt = (r.relation_type || '').trim();
        if (rt !== 'IsPartOf' && rt !== 'HasPart') return;
        var pkgId = (r.related_instrument_package_id || '').trim();
        var label = (r.related_identifier_name ||
                     r.related_identifier ||
                     pkgId || 'Unknown instrument').trim();
        if (rt === 'IsPartOf') parents.push({ pkgId: pkgId, label: label });
        else                   children.push({ pkgId: pkgId, label: label });
      });
      return { parents: parents, children: children };
    },

    /* ── package_show fetch with cache + de-dup ────── */

    _fetchPkg: function (pkgId) {
      var self = this;
      if (this._pkgCache[pkgId]) {
        return $.Deferred().resolve(this._pkgCache[pkgId]).promise();
      }
      if (this._inflight[pkgId]) {
        return this._inflight[pkgId].promise();
      }

      var dfd = $.Deferred();
      this._inflight[pkgId] = dfd;

      $.ajax({
        url: '/api/3/action/package_show',
        data: { id: pkgId },
        method: 'GET',
        dataType: 'json'
      }).done(function (resp) {
        if (resp.success && resp.result) {
          var pkg = resp.result;
          var ri  = pkg.related_identifier_obj;
          pkg._related = (typeof ri === 'string')
            ? self._parseRelated(ri)
            : (Array.isArray(ri) ? ri : []);
          self._pkgCache[pkgId] = pkg;
          dfd.resolve(pkg);
        } else {
          dfd.reject();
        }
      }).fail(function () {
        dfd.reject();
      }).always(function () {
        delete self._inflight[pkgId];
      });

      return dfd.promise();
    },

    /* ── jsTree initialisation ────────────────────── */

    _initTree: function () {
      var self  = this;
      var $tree = this.$tree;

      if ($tree.data('jstree')) $tree.jstree('destroy');

      $tree.jstree({
        core: {
          data: function (node, cb) { self._loadNode(node, cb); },
          check_callback: true,
          themes: { name: 'default', responsive: true, url: false, dots: true }
        },
        plugins: ['types', 'wholerow'],
        types: {
          'default':    { icon: false },
          instrument:   { icon: false },
          group:        { icon: false },
          cycle:        { icon: false },
          unresolved:   { icon: false }
        }
      });

      /* Click → navigate (instrument nodes only) */
      $tree.on('click', '.jstree-anchor', function (e) {
        e.preventDefault();
        var inst   = $tree.jstree(true);
        var nodeId = this.id.replace('_anchor', '');
        var node   = inst.get_node(nodeId);
        if (!node || !node.data) return;
        var nt = node.data.nodeType;

        // Group nodes: toggle expand/collapse on text click
        if (nt === 'group') { inst.toggle_node(node); return; }
        if (nt === 'cycle' || nt === 'root') return;

        // Instrument nodes: navigate to dataset page
        var href = node.data.pkgName
          ? '/dataset/' + node.data.pkgName
          : (node.data.pkgId ? '/dataset/' + node.data.pkgId : null);
        if (href) window.location.href = href;
      });
    },

    /* ── core.data router (called by jsTree for lazy nodes) ── */

    _loadNode: function (node, cb) {
      var self = this;

      /* Root call */
      if (node.id === '#') {
        var rootPkg  = this._pkgCache[this.packageId];
        var rootRels = this._extractRelations(rootPkg._related);
        var groups   = this._makeGroups(this.packageId, rootRels, [], true);

        if (groups.length === 0) {
          this._legacyFallback(cb);
          return;
        }

        cb([{
          id:       nid(),
          text:     this._trunc(this.packageTitle, 50),
          type:     'instrument',
          state:    { opened: true },
          data:     { pkgId: this.packageId, pkgName: this.packageName,
                      nodeType: 'root', ancestors: [] },
          a_attr:   { title: this.packageTitle, href: '#',
                      class: 'pidinst-current-node' },
          children: groups
        }]);
        return;
      }

      /* Expanding a group node */
      if (node.data && node.data.nodeType === 'group') {
        this._loadGroupKids(node, cb);
        return;
      }

      /* Expanding an instrument node */
      if (node.data && (node.data.nodeType === 'instrument' ||
                         node.data.nodeType === 'root')) {
        this._loadInstrumentKids(node, cb);
        return;
      }

      cb([]);
    },

    /* ── Build group nodes ────────────────────────── */

    _makeGroups: function (pkgId, rels, ancestors, autoOpen) {
      var out   = [];
      var chain = ancestors.concat([pkgId]);

      if (rels.parents.length) {
        out.push({
          id:       nid(),
          text:     'Is Part of',
          type:     'group',
          state:    { opened: !!autoOpen },
          data:     { nodeType: 'group', direction: 'parents',
                      ownerPkgId: pkgId, items: rels.parents,
                      ancestors: chain },
          a_attr:   { href: '#', class: 'pidinst-group-node' },
          children: true                /* ← lazy-load */
        });
      }

      if (rels.children.length) {
        out.push({
          id:       nid(),
          text:     'Has Part of',
          type:     'group',
          state:    { opened: !!autoOpen },
          data:     { nodeType: 'group', direction: 'children',
                      ownerPkgId: pkgId, items: rels.children,
                      ancestors: chain },
          a_attr:   { href: '#', class: 'pidinst-group-node' },
          children: true                /* ← lazy-load */
        });
      }

      return out;
    },

    /* ── Expand group → return instrument nodes ───── */

    _loadGroupKids: function (node, cb) {
      var self      = this;
      var items     = node.data.items || [];
      var ancestors = node.data.ancestors || [];
      var results   = [];
      var pending   = items.length;

      if (!pending) { cb([]); return; }

      items.forEach(function (item) {
        var pkgId = item.pkgId;
        var label = item.label || 'Unknown instrument';

        /* Cycle check */
        if (pkgId && ancestors.indexOf(pkgId) !== -1) {
          results.push(self._cycleNode(label));
          if (--pending === 0) cb(results);
          return;
        }

        /* No pkgId → unresolved */
        if (!pkgId) {
          results.push(self._unresolvedNode(label));
          if (--pending === 0) cb(results);
          return;
        }

        self._fetchPkg(pkgId).then(
          function (pkg) {
            var title   = pkg.title || pkg.name || label;
            var rels    = self._extractRelations(pkg._related);
            var hasMore = (rels.parents.length + rels.children.length) > 0;

            results.push({
              id:       nid(),
              text:     self._trunc(title, 50),
              type:     'instrument',
              data:     { nodeType: 'instrument',
                          pkgId: pkg.id,
                          pkgName: pkg.name || pkg.id,
                          ancestors: ancestors,
                          _rels: rels },
              a_attr:   { title: title,
                          href: '/dataset/' + (pkg.name || pkg.id),
                          class: 'clickable-node' },
              children: hasMore          /* true → show expand arrow */
            });
            if (--pending === 0) cb(results);
          },
          function () {
            results.push(self._unresolvedNode(label + ' (unavailable)', pkgId));
            if (--pending === 0) cb(results);
          }
        );
      });
    },

    /* ── Expand instrument → return its groups ────── */

    _loadInstrumentKids: function (node, cb) {
      var self      = this;
      var pkgId     = node.data.pkgId;
      var ancestors = node.data.ancestors || [];

      if (node.data._rels) {
        cb(self._makeGroups(pkgId, node.data._rels, ancestors, false));
        return;
      }

      self._fetchPkg(pkgId).then(
        function (pkg) {
          var rels = self._extractRelations(pkg._related);
          cb(self._makeGroups(pkgId, rels, ancestors, false));
        },
        function () { cb([]); }
      );
    },

    /* ── Node factories ──────────────────────────── */

    _cycleNode: function (label) {
      return {
        id:       nid(),
        text:     'Cycle detected (' + this._trunc(label, 30) +
                  ' already in this branch)',
        type:     'cycle',
        data:     { nodeType: 'cycle' },
        a_attr:   { href: '#', class: 'pidinst-cycle-node',
                    title: 'Circular reference \u2013 expansion stopped' },
        children: false
      };
    },

    _unresolvedNode: function (label, pkgId) {
      var hasUnavail = label.indexOf('unavailable') !== -1;
      return {
        id:       nid(),
        text:     this._trunc(label, 50) + (hasUnavail ? '' : ' (unresolved)'),
        type:     'unresolved',
        data:     { nodeType: 'unresolved', pkgId: pkgId || null },
        a_attr:   { href: pkgId ? '/dataset/' + pkgId : '#',
                    class: pkgId ? 'clickable-node' : 'pidinst-unresolved-node',
                    title: label },
        children: false
      };
    },

    /* ── Legacy fallback (package_relationships_list) ── */

    _legacyFallback: function (cb) {
      var self   = this;
      var rootId = this.packageId;

      $.ajax({
        url: '/api/3/action/package_relationships_list',
        method: 'GET',
        data: { id: rootId, rel: 'parent_of' }
      }).done(function (resp) {
        if (!resp.success || !resp.result || !resp.result.length) {
          self._emptyRoot(cb);
          return;
        }

        var kids      = [];
        var remaining = resp.result.length;

        resp.result.forEach(function (rel) {
          self._fetchPkg(rel.object).then(
            function (pkg) {
              if (pkg.state && pkg.state !== 'active') {
                if (--remaining === 0) finalize();
                return;
              }
              var title = pkg.title || pkg.name || rel.object;
              var rels  = self._extractRelations(pkg._related);
              kids.push({
                id:       nid(),
                text:     self._trunc(title, 50),
                type:     'instrument',
                data:     { nodeType: 'instrument',
                            pkgId: pkg.id,
                            pkgName: pkg.name || pkg.id,
                            ancestors: [rootId],
                            _rels: rels },
                a_attr:   { title: title,
                            href: '/dataset/' + (pkg.name || pkg.id),
                            class: 'clickable-node' },
                children: (rels.parents.length + rels.children.length) > 0
              });
              if (--remaining === 0) finalize();
            },
            function () {
              if (--remaining === 0) finalize();
            }
          );
        });

        function finalize() {
          var rootChildren = [];
          if (kids.length) {
            rootChildren.push({
              id:       nid(),
              text:     'Has Part of',
              type:     'group',
              state:    { opened: true },
              data:     { nodeType: 'group', direction: 'children',
                          ownerPkgId: rootId, items: [],
                          ancestors: [rootId] },
              a_attr:   { href: '#', class: 'pidinst-group-node' },
              children: kids            /* already resolved */
            });
          }

          cb([{
            id:       nid(),
            text:     self._trunc(self.packageTitle, 50),
            type:     'instrument',
            state:    { opened: true },
            data:     { pkgId: rootId, pkgName: self.packageName,
                        nodeType: 'root', ancestors: [] },
            a_attr:   { title: self.packageTitle, href: '#',
                        class: 'pidinst-current-node' },
            children: rootChildren.length ? rootChildren : false
          }]);

          if (!rootChildren.length) {
            self.el.find('.pidinst-family-empty').show();
          }
        }
      }).fail(function () {
        self._emptyRoot(cb);
      });
    },

    /** Render a lone root with no children + show empty-state message. */
    _emptyRoot: function (cb) {
      cb([{
        id:       nid(),
        text:     this._trunc(this.packageTitle, 50),
        type:     'instrument',
        state:    { opened: true },
        data:     { pkgId: this.packageId, pkgName: this.packageName,
                    nodeType: 'root', ancestors: [] },
        a_attr:   { title: this.packageTitle, href: '#',
                    class: 'pidinst-current-node' },
        children: false
      }]);
      this.el.find('.pidinst-family-empty').show();
    },

    /* ── Utilities ────────────────────────────────── */

    _trunc: function (text, max) {
      if (!text || text.length <= max) return text || '';
      return text.slice(0, Math.ceil(max / 2)) + '\u2026' +
             text.slice(-Math.floor(max / 2));
    }

  };
});
