/**
 * jstree-view-module.js
 *
 * Lazy-loaded instrument family tree.
 * Instruments load as direct children — no relation-label group nodes.
 * Multi-parent safe (display ids via nid()), cycle-protected per branch.
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
          'default':  { icon: false },
          instrument: { icon: false },
          cycle:      { icon: false },
          unresolved: { icon: false }
        }
      });

      $tree.on('click', '.jstree-anchor', function (e) {
        e.preventDefault();
        var inst   = $tree.jstree(true);
        var nodeId = this.id.replace('_anchor', '');
        var node   = inst.get_node(nodeId);
        if (!node || !node.data) return;
        var nt = node.data.nodeType;
        if (nt === 'cycle' || nt === 'root') return;
        var href = node.data.pkgName
          ? '/instrument/' + node.data.pkgName
          : (node.data.pkgId ? '/instrument/' + node.data.pkgId : null);
        if (href) window.location.href = href;
      });
    },

    _loadNode: function (node, cb) {
      var self = this;

      if (node.id === '#') {
        var rootPkg  = this._pkgCache[this.packageId];
        var rootRels = this._extractRelations(rootPkg._related);
        var hasMore  = (rootRels.parents.length + rootRels.children.length) > 0;
        cb([{
          id:       nid(),
          text:     this._trunc(this.packageTitle, 200),
          type:     'instrument',
          state:    { opened: true },
          data:     { pkgId: this.packageId, pkgName: this.packageName,
                      nodeType: 'root', ancestors: [], _rels: rootRels },
          a_attr:   { title: this.packageTitle, href: '#',
                      class: 'pidinst-current-node' },
          children: hasMore
        }]);
        return;
      }

      if (node.data && (node.data.nodeType === 'instrument' ||
                         node.data.nodeType === 'root')) {
        this._loadInstrumentKids(node, cb);
        return;
      }

      cb([]);
    },

    _loadInstrumentKids: function (node, cb) {
      var self          = this;
      var pkgId         = node.data.pkgId;
      var ancestors     = node.data.ancestors || [];
      var nextAncestors = ancestors.concat([pkgId]);

      function buildNodes(rels) {
        var items   = rels.parents.concat(rels.children);
        var pending = items.length;
        if (!pending) { cb([]); return; }

        var results = [];
        items.forEach(function (item) {
          var id    = item.pkgId;
          var label = item.label || 'Unknown instrument';

          if (id && nextAncestors.indexOf(id) !== -1) {
            results.push(self._cycleNode(label));
            if (--pending === 0) cb(results);
            return;
          }

          if (!id) {
            results.push(self._unresolvedNode(label));
            if (--pending === 0) cb(results);
            return;
          }

          self._fetchPkg(id).then(
            function (pkg) {
              var title   = pkg.title || pkg.name || label;
              var rels    = self._extractRelations(pkg._related);
              var hasMore = (rels.parents.length + rels.children.length) > 0;
              results.push({
                id:       nid(),
                text:     self._trunc(title, 200),
                type:     'instrument',
                data:     { nodeType: 'instrument',
                            pkgId: pkg.id,
                            pkgName: pkg.name || pkg.id,
                            ancestors: nextAncestors,
                            _rels: rels },
                a_attr:   { title: title,
                            href: '/instrument/' + (pkg.name || pkg.id),
                            class: 'clickable-node' },
                children: hasMore
              });
              if (--pending === 0) cb(results);
            },
            function () {
              results.push(self._unresolvedNode(label + ' (unavailable)', id));
              if (--pending === 0) cb(results);
            }
          );
        });
      }

      if (node.data._rels) {
        buildNodes(node.data._rels);
        return;
      }

      self._fetchPkg(pkgId).then(
        function (pkg) { buildNodes(self._extractRelations(pkg._related)); },
        function ()    { cb([]); }
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
        text:     this._trunc(label, 200) + (hasUnavail ? '' : ' (unresolved)'),
        type:     'unresolved',
        data:     { nodeType: 'unresolved', pkgId: pkgId || null },
        a_attr:   { href: pkgId ? '/instrument/' + pkgId : '#',
                    class: pkgId ? 'clickable-node' : 'pidinst-unresolved-node',
                    title: label },
        children: false
      };
    },

    /* ── Utilities ────────────────────────────────── */

    _trunc: function (text, max) {
      if (!text || text.length <= max) return text || '';
      return text.slice(0, Math.ceil(max / 2)) + '\u2026' +
             text.slice(-Math.floor(max / 2));
    }

  };
});
