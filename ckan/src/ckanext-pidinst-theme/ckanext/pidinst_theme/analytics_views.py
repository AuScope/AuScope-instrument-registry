"""
Blueprint views for analytics tracking endpoints
"""

from flask import Blueprint, jsonify, request
from ckan.plugins import toolkit
from ckan.common import current_user
import logging

from ckanext.pidinst_theme import analytics

log = logging.getLogger(__name__)

analytics_bp = Blueprint('analytics', __name__, url_prefix='/api/analytics')


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
        event = data.get('event')
        properties = data.get('properties', {})
        
        if not event:
            return jsonify({'success': False, 'error': 'Event name is required'}), 400
        
        # Get user ID if authenticated
        user_id = None
        if current_user.is_authenticated:
            user_id = current_user.id
        
        # Track the event
        success = analytics.AnalyticsTracker.track(
            user_id=user_id,
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
        "resource_name": "...",
        "resource_format": "..."
    }
    """
    try:
        data = request.get_json()
        
        user_id = None
        if current_user.is_authenticated:
            user_id = current_user.id
        
        analytics.track_resource_download(
            user_id=user_id,
            resource_id=data.get('resource_id', ''),
            dataset_id=data.get('dataset_id', ''),
            resource_name=data.get('resource_name', ''),
            resource_format=data.get('resource_format', '')
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
        "query": "search terms",
        "num_results": 10,
        "sort_by": "relevance"
    }
    """
    try:
        data = request.get_json()
        
        user_id = None
        if current_user.is_authenticated:
            user_id = current_user.id
        
        analytics.track_dataset_search(
            user_id=user_id,
            search_query=data.get('query', ''),
            num_results=data.get('num_results', 0),
            sort_by=data.get('sort_by', 'relevance')
        )
        
        return jsonify({'success': True})
        
    except Exception as e:
        log.error(f"Error tracking search: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
