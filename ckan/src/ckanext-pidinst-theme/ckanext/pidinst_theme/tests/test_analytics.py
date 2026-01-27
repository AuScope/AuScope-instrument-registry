"""
Test suite for analytics tracking functionality
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
from ckanext.pidinst_theme import analytics


class TestAnalyticsTracker(unittest.TestCase):
    """Tests for AnalyticsTracker class"""
    
    @patch.dict('os.environ', {
        'RUDDERSTACK_ENABLED': 'true',
        'RUDDERSTACK_WRITE_KEY': 'test_key',
        'RUDDERSTACK_DATA_PLANE_URL': 'https://test.rudderstack.com'
    })
    @patch('ckanext.pidinst_theme.analytics.Client')
    def test_initialization(self, mock_client):
        """Test tracker initialization with valid config"""
        analytics.AnalyticsTracker._client = None
        analytics.AnalyticsTracker._enabled = False
        analytics.AnalyticsTracker.initialize()
        
        self.assertTrue(analytics.AnalyticsTracker.is_enabled())
        mock_client.assert_called_once()
    
    @patch.dict('os.environ', {'RUDDERSTACK_ENABLED': 'false'})
    def test_disabled_tracking(self):
        """Test that tracking is disabled when configured as such"""
        analytics.AnalyticsTracker._client = None
        analytics.AnalyticsTracker._enabled = False
        analytics.AnalyticsTracker.initialize()
        
        self.assertFalse(analytics.AnalyticsTracker.is_enabled())
    
    @patch.dict('os.environ', {
        'RUDDERSTACK_ENABLED': 'true',
        'RUDDERSTACK_WRITE_KEY': 'test_key',
        'RUDDERSTACK_DATA_PLANE_URL': 'https://test.rudderstack.com'
    })
    @patch('ckanext.pidinst_theme.analytics.Client')
    def test_track_event(self, mock_client):
        """Test tracking an event"""
        mock_instance = Mock()
        mock_client.return_value = mock_instance
        
        analytics.AnalyticsTracker._client = None
        analytics.AnalyticsTracker._enabled = False
        analytics.AnalyticsTracker.initialize()
        
        result = analytics.AnalyticsTracker.track(
            user_id='test_user',
            event='Test Event',
            properties={'key': 'value'}
        )
        
        self.assertTrue(result)
        mock_instance.track.assert_called_once()
    
    def test_track_dataset_created(self):
        """Test dataset creation tracking"""
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            dataset_dict = {
                'id': 'test-123',
                'name': 'test-dataset',
                'title': 'Test Dataset',
                'owner_org': 'org-123',
                'private': False,
                'resources': [{'id': 'res-1'}],
                'tags': [{'name': 'tag1'}]
            }
            
            analytics.track_dataset_created('user-123', dataset_dict)
            
            mock_track.assert_called_once()
            call_args = mock_track.call_args
            self.assertEqual(call_args[0][0], 'user-123')
            self.assertEqual(call_args[0][1], 'Dataset Created')
            self.assertEqual(call_args[1]['properties']['dataset_id'], 'test-123')


if __name__ == '__main__':
    unittest.main()
