/**
 * Propagation Progress Module
 *
 * Polls /api/propagation_progress/<entity_key> and renders a Bootstrap
 * progress bar while a background propagation job is running.
 *
 * Usage (add to a container element in the template):
 *   data-module="propagation-progress"
 *   data-module-entity-key="party=phoenix-geophysics"
 *
 * The module is a no-op if no active job is found for the given entity key.
 */
this.ckan.module('propagation-progress', function ($) {
  'use strict';

  return {
    options: {
      entityKey: '',       // e.g. "party=phoenix-geophysics"
      pollInterval: 1200,  // ms between polls while running
      doneTimeout: 8000,   // ms to show completion banner before reloading
    },

    initialize: function () {
      var self = this;
      self._entityKey = self.el.data('entity-key') || self.options.entityKey;
      if (!self._entityKey) { return; }

      self._pollTimer = null;
      // True once we have observed at least one pending/running poll.
      self._seenRunning = false;
      // sessionStorage key used to prevent reload loops when propagation
      // finishes before this page's first poll.
      self._ssKey = 'pidinst_propagation_reloaded:' + self._entityKey;
      self._container = self._buildContainer();
      self.el.prepend(self._container);

      // Begin polling immediately
      self._poll();
    },

    teardown: function () {
      if (this._pollTimer) {
        clearTimeout(this._pollTimer);
      }
    },

    // ------------------------------------------------------------------
    // Internal
    // ------------------------------------------------------------------

    _apiUrl: function () {
      return '/api/propagation_progress/' + encodeURIComponent(this._entityKey);
    },

    _poll: function () {
      var self = this;
      $.getJSON(self._apiUrl())
        .done(function (data) { self._handleResponse(data); })
        .fail(function ()     { /* silently ignore network errors */ });
    },

    _scheduleNextPoll: function () {
      var self = this;
      self._pollTimer = setTimeout(function () { self._poll(); }, self.options.pollInterval);
    },

    _handleResponse: function (data) {
      var self = this;

      if (data.status === 'no_job') {
        // No active job – stay hidden and stop polling
        return;
      }

      // status is pending / running / done – handled below
      var total   = data.total || 0;
      var done    = data.done  || 0;
      var pct     = (total > 0) ? Math.round((done / total) * 100) : 0;
      var updated = data.updated || 0;
      var fails   = data.failures || 0;

      if (data.status === 'pending') {
        self._seenRunning = true;
        self._container.show();
        self._setProgress(0, null, 'Preparing to update instruments\u2026', 'info');
        self._scheduleNextPoll();
        return;
      }

      if (data.status === 'running') {
        self._seenRunning = true;
        self._container.show();
        var label = total
          ? ('Updating instruments: ' + done + ' / ' + total + ' (' + pct + '%)')
          : ('Updating instruments\u2026 (' + done + ' done)');
        self._setProgress(pct || 5, total ? pct : null, label, 'info');
        self._scheduleNextPoll();
        return;
      }

      if (data.status === 'done') {
        var msg = 'Done. ' + updated + ' of ' + total + ' instrument(s) updated.';
        if (fails > 0) {
          msg += ' ' + fails + ' failed (see server log).';
        }

        // Use the real job_id (or finished_at as fallback) as a unique marker
        // so sessionStorage can prevent reloading the same job twice.
        var reloadMarker = data.job_id || String(data.finished_at || '');
        var alreadyReloaded = (reloadMarker && sessionStorage.getItem(self._ssKey) === reloadMarker);
        var shouldReload = updated > 0 && !alreadyReloaded;

        if (shouldReload) {
          self._container.show();
          self._setProgress(100, 100, msg, fails > 0 ? 'warning' : 'success');
          if (reloadMarker) {
            sessionStorage.setItem(self._ssKey, reloadMarker);
          }
          // Reload quickly when propagation was already done on arrival (user
          // did not see a progress bar); otherwise give the banner time to show.
          var reloadDelay = self._seenRunning ? self.options.doneTimeout : 800;
          setTimeout(function () { window.location.reload(); }, reloadDelay);
        } else if (self._seenRunning) {
          self._container.show();
          self._setProgress(100, 100, msg, fails > 0 ? 'warning' : 'success');
          setTimeout(function () { self._container.hide(); }, self.options.doneTimeout);
        }
        return;
      }
    },

    /**
     * @param {number}      animated   0-100 visual fill (null = animated stripe)
     * @param {number|null} ariaValue  aria-valuenow (null hides the label)
     * @param {string}      text       human-readable status text
     * @param {string}      type       Bootstrap context: info / success / warning
     */
    _setProgress: function (animated, ariaValue, text, type) {
      var bar      = this._container.find('.progress-bar');
      var alert    = this._container.find('.propagation-alert');
      var msgEl    = this._container.find('.propagation-msg');

      // Update alert context colour
      alert.removeClass('alert-info alert-success alert-warning')
           .addClass('alert-' + type);

      // Animated stripe while indeterminate
      if (ariaValue === null) {
        bar.addClass('progress-bar-striped progress-bar-animated')
           .css('width', '100%')
           .attr('aria-valuenow', 0);
      } else {
        bar.removeClass('progress-bar-striped progress-bar-animated')
           .css('width', animated + '%')
           .attr('aria-valuenow', animated);
      }

      msgEl.text(text);
    },

    _buildContainer: function () {
      return $(
        '<div class="propagation-progress-widget" style="display:none; margin-bottom:12px;">' +
          '<div class="alert alert-info propagation-alert" style="padding:10px 14px;">' +
            '<strong>Background Update</strong> ' +
            '<span class="propagation-msg"></span>' +
            '<div class="progress" style="margin-top:8px; margin-bottom:0; height:14px;">' +
              '<div class="progress-bar progress-bar-striped progress-bar-animated"' +
                   ' role="progressbar"' +
                   ' style="width:100%; min-width:2em;"' +
                   ' aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">' +
              '</div>' +
            '</div>' +
          '</div>' +
        '</div>'
      );
    },
  };
});
