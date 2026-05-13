"""
Blueprint views for analytics tracking endpoints
"""

from flask import Blueprint, jsonify, request
from ckan.plugins import toolkit
import logging

from ckanext.pidinst_theme import analytics

log = logging.getLogger(__name__)

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api/analytics')

# CSRF note: these endpoints receive browser sendBeacon / fetch calls that
# carry no CKAN CSRF token.  CKAN 2.11's CsrfTokenMiddleware skips paths
# whose REQUEST_PATH starts with '/api', so these routes should already be
# exempt.  If a 403 is observed from sendBeacon, add the following to
# ckan.ini (or CKAN_INI_SETTINGS):
#   WTF_CSRF_EXEMPT_URLS = api/analytics
@analytics_bp.before_request
def _skip_csrf():
    """Mark this request as CSRF-exempt for flask_wtf if it is applied."""
    try:
        request.csrf_exempt = True  # type: ignore[attr-defined]
    except Exception:
        pass

# Whitelist imported from analytics.py so it can be tested without Flask.
_KNOWN_FRONTEND_EVENTS = analytics.KNOWN_FRONTEND_EVENTS


@analytics_bp.route('/track', methods=['POST'])
def track_event():
    """
    Endpoint for tracking custom analytics events from frontend
    
    POST /api/analytics/track
    {
        "event": "Event Name",
        "properties": {
            "key": "value"
        }
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Request body required'}), 400
        event = data.get('event')
        properties = data.get('properties', {})

        if not event:
            return jsonify({'success': False, 'error': 'Event name is required'}), 400

        if event not in _KNOWN_FRONTEND_EVENTS:
            return jsonify({'success': False, 'error': 'Unknown event name'}), 400

        success = analytics.AnalyticsTracker.track(
            event=event,
            properties=properties
        )
        
        return jsonify({'success': success})
        
    except Exception as e:
        log.error(f"Error tracking event: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@analytics_bp.route('/resource-download', methods=['POST'])
def track_resource_download():
    """
    Endpoint for tracking resource downloads

    POST /api/analytics/resource-download
    {
        "resource_id": "...",
        "dataset_id": "...",
        "resource_format": "...",
        "size_bytes": 1234567,
        "dataset_type": "instrument|platform|unknown"
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Request body required'}), 400

        size_raw = data.get('size_bytes')
        size_bytes = int(size_raw) if size_raw is not None else None

        analytics.track_resource_download(
            resource_id=data.get('resource_id', ''),
            dataset_id=data.get('dataset_id', ''),
            resource_format=data.get('resource_format', ''),
            size_bytes=size_bytes,
            dataset_type=data.get('dataset_type'),
        )

        return jsonify({'success': True})

    except Exception as e:
        log.error(f"Error tracking resource download: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@analytics_bp.route('/search', methods=['POST'])
def track_search():
    """
    Endpoint for tracking search events

    POST /api/analytics/search
    {
        "search_term": "search terms",
        "result_count": 10
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'Request body required'}), 400

        analytics.track_dataset_search(
            search_term=data.get('search_term', data.get('query', '')),
            result_count=int(data.get('result_count', data.get('num_results', 0))),
        )

        return jsonify({'success': True})

    except Exception as e:
        log.error(f"Error tracking search: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
