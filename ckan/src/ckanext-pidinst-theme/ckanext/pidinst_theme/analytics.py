"""
Analytics tracking helpers for backend events
Integrates with RudderStack for server-side event tracking
"""

import os
import logging
from datetime import datetime
from typing import Dict, Optional, Any

log = logging.getLogger(__name__)

# Try to import RudderStack SDK
try:
    from rudderstack.analytics import Client
    RUDDERSTACK_AVAILABLE = True
except ImportError:
    RUDDERSTACK_AVAILABLE = False
    log.warning("RudderStack Python SDK not available. Install with: pip install rudderstack-python")


class AnalyticsTracker:
    """Server-side analytics event tracker using RudderStack"""
    
    _client = None
    _enabled = False
    
    @classmethod
    def initialize(cls):
        """Initialize RudderStack client from environment variables"""
        if not RUDDERSTACK_AVAILABLE:
            return
        
        write_key = os.environ.get('RUDDERSTACK_WRITE_KEY', '')
        data_plane_url = os.environ.get('RUDDERSTACK_DATA_PLANE_URL', '')
        enabled = os.environ.get('RUDDERSTACK_ENABLED', 'false').lower() == 'true'
        
        if enabled and write_key and data_plane_url:
            try:
                cls._client = Client(
                    write_key=write_key,
                    data_plane_url=data_plane_url,
                    gzip=True,
                    max_retries=3
                )
                cls._enabled = True
                log.info("RudderStack analytics initialized successfully")
            except Exception as e:
                log.error(f"Failed to initialize RudderStack: {e}")
                cls._enabled = False
        else:
            log.debug("RudderStack analytics not enabled or not configured")
    
    @classmethod
    def is_enabled(cls) -> bool:
        """Check if analytics tracking is enabled"""
        if cls._client is None:
            cls.initialize()
        return cls._enabled
    
    @classmethod
    def track(cls, user_id: Optional[str], event: str, properties: Dict[str, Any]) -> bool:
        """
        Track an event
        
        Args:
            user_id: User identifier (can be None for anonymous events)
            event: Event name
            properties: Event properties dictionary
            
        Returns:
            bool: True if event was tracked successfully
        """
        if not cls.is_enabled():
            log.debug(f"Analytics disabled, skipping event: {event}")
            return False
        
        try:
            # Add timestamp if not present
            if 'timestamp' not in properties:
                properties['timestamp'] = datetime.utcnow().isoformat()
            
            # Add environment context
            properties['environment'] = os.environ.get('CKAN_SITE_URL', 'unknown')
            
            if user_id:
                cls._client.track(
                    user_id=user_id,
                    event=event,
                    properties=properties
                )
            else:
                # For anonymous events, use anonymous_id
                anonymous_id = properties.get('anonymous_id', 'anonymous')
                cls._client.track(
                    anonymous_id=anonymous_id,
                    event=event,
                    properties=properties
                )
            
            log.debug(f"Tracked event: {event} for user: {user_id or 'anonymous'}")
            return True
            
        except Exception as e:
            log.error(f"Failed to track event {event}: {e}")
            return False
    
    @classmethod
    def identify(cls, user_id: str, traits: Dict[str, Any]) -> bool:
        """
        Identify a user with traits
        
        Args:
            user_id: User identifier
            traits: User traits dictionary
            
        Returns:
            bool: True if identification was successful
        """
        if not cls.is_enabled():
            return False
        
        try:
            cls._client.identify(
                user_id=user_id,
                traits=traits
            )
            log.debug(f"Identified user: {user_id}")
            return True
        except Exception as e:
            log.error(f"Failed to identify user {user_id}: {e}")
            return False


# Event tracking helper functions

def track_dataset_created(user_id: str, dataset_dict: Dict[str, Any]):
    """Track dataset creation event"""
    AnalyticsTracker.track(
        user_id=user_id,
        event='Dataset Created',
        properties={
            'dataset_id': dataset_dict.get('id'),
            'dataset_name': dataset_dict.get('name'),
            'dataset_title': dataset_dict.get('title'),
            'organization_id': dataset_dict.get('owner_org'),
            'private': dataset_dict.get('private', False),
            'num_resources': len(dataset_dict.get('resources', [])),
            'num_tags': len(dataset_dict.get('tags', [])),
            'has_doi': 'doi' in dataset_dict,
        }
    )


def track_dataset_updated(user_id: str, dataset_dict: Dict[str, Any]):
    """Track dataset update event"""
    AnalyticsTracker.track(
        user_id=user_id,
        event='Update Existing Dataset',
        properties={
            'dataset_id': dataset_dict.get('id'),
            'dataset_name': dataset_dict.get('name'),
            'dataset_title': dataset_dict.get('title'),
            'organization_id': dataset_dict.get('owner_org'),
            'private': dataset_dict.get('private', False),
            'num_resources': len(dataset_dict.get('resources', [])),
        }
    )


def track_doi_created(user_id: str, dataset_dict: Dict[str, Any], doi: str):
    """Track DOI creation/publication event"""
    AnalyticsTracker.track(
        user_id=user_id,
        event='Dataset Published with DOI',
        properties={
            'dataset_id': dataset_dict.get('id'),
            'dataset_name': dataset_dict.get('name'),
            'dataset_title': dataset_dict.get('title'),
            'doi': doi,
            'organization_id': dataset_dict.get('owner_org'),
        }
    )


def track_resource_download(user_id: Optional[str], resource_id: str, 
                            dataset_id: str, resource_name: str, 
                            resource_format: str):
    """Track resource download event"""
    AnalyticsTracker.track(
        user_id=user_id,
        event='Resource Download',
        properties={
            'resource_id': resource_id,
            'dataset_id': dataset_id,
            'resource_name': resource_name,
            'resource_format': resource_format,
        }
    )


def track_dataset_search(user_id: Optional[str], search_query: str, 
                         num_results: int, sort_by: str = 'relevance'):
    """Track dataset search event"""
    AnalyticsTracker.track(
        user_id=user_id,
        event='Dataset Search',
        properties={
            'search_query': search_query,
            'num_results': num_results,
            'sort_by': sort_by,
        }
    )
