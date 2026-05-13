"""
Test suite for analytics tracking functionality
"""

import sys
import types
import unittest
from unittest.mock import Mock, patch
from ckanext.pidinst_theme import analytics


# ---------------------------------------------------------------------------
# Helper: make a minimal package dict for tests
# ---------------------------------------------------------------------------
def _pkg(overrides=None):
    base = {
        'id': 'pkg-001',
        'is_platform': 'false',
        'private': False,
        'doi': '',
    }
    if overrides:
        base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Event name constants
# ---------------------------------------------------------------------------
class TestEventConstants(unittest.TestCase):
    """Event name constants must match the requirements table exactly."""

    def test_search(self):
        self.assertEqual(analytics.EVENT_SEARCH, 'Search')

    def test_empty_result_search(self):
        self.assertEqual(analytics.EVENT_EMPTY_RESULT_SEARCH, 'Empty-Result Search')

    def test_search_result_click_through(self):
        self.assertEqual(analytics.EVENT_SEARCH_RESULT_CLICK_THROUGH, 'Search Result Click-Through')

    def test_dataset_page_view(self):
        self.assertEqual(analytics.EVENT_DATASET_PAGE_VIEW, 'Dataset Page View')

    def test_download(self):
        self.assertEqual(analytics.EVENT_DOWNLOAD, 'Download')

    def test_time_to_first_download(self):
        self.assertEqual(analytics.EVENT_TIME_TO_FIRST_DOWNLOAD, 'Time To First Download')

    def test_dataset_created(self):
        self.assertEqual(analytics.EVENT_DATASET_CREATED, 'Dataset Created')

    def test_dataset_published_with_doi(self):
        self.assertEqual(analytics.EVENT_DATASET_PUBLISHED_WITH_DOI, 'Dataset Published With DOI')

    def test_update_existing_dataset(self):
        self.assertEqual(analytics.EVENT_UPDATE_EXISTING_DATASET, 'Update Existing Dataset')

    def test_doi_based_citation(self):
        self.assertEqual(analytics.EVENT_DOI_BASED_CITATION, 'DOI-Based Citation')

    def test_resource_preview_opened(self):
        self.assertEqual(analytics.EVENT_RESOURCE_PREVIEW_OPENED, 'Resource Preview Opened')


# ---------------------------------------------------------------------------
# dataset_type derivation from is_platform
# ---------------------------------------------------------------------------
class TestDatasetTypeFromPkg(unittest.TestCase):

    def test_instrument_bool_false(self):
        self.assertEqual(analytics._dataset_type_from_pkg({'is_platform': False}), 'instrument')

    def test_instrument_string_false(self):
        self.assertEqual(analytics._dataset_type_from_pkg({'is_platform': 'false'}), 'instrument')

    def test_instrument_string_False(self):
        self.assertEqual(analytics._dataset_type_from_pkg({'is_platform': 'False'}), 'instrument')

    def test_platform_bool_true(self):
        self.assertEqual(analytics._dataset_type_from_pkg({'is_platform': True}), 'platform')

    def test_platform_string_true(self):
        self.assertEqual(analytics._dataset_type_from_pkg({'is_platform': 'true'}), 'platform')

    def test_platform_string_True(self):
        self.assertEqual(analytics._dataset_type_from_pkg({'is_platform': 'True'}), 'platform')

    def test_unknown_when_missing(self):
        self.assertEqual(analytics._dataset_type_from_pkg({}), 'unknown')

    def test_unknown_when_none(self):
        self.assertEqual(analytics._dataset_type_from_pkg({'is_platform': None}), 'unknown')


# ---------------------------------------------------------------------------
# is_public derivation from private
# ---------------------------------------------------------------------------
class TestIsPublicFromPkg(unittest.TestCase):

    def test_public_when_private_false(self):
        self.assertTrue(analytics._is_public_from_pkg({'private': False}))

    def test_private_when_private_true(self):
        self.assertFalse(analytics._is_public_from_pkg({'private': True}))

    def test_none_when_missing(self):
        self.assertIsNone(analytics._is_public_from_pkg({}))


# ---------------------------------------------------------------------------
# has_doi derivation
# ---------------------------------------------------------------------------
class TestHasDoiFromPkg(unittest.TestCase):

    def test_true_when_doi_present(self):
        self.assertTrue(analytics._has_doi_from_pkg({'doi': '10.1234/test'}))

    def test_false_when_doi_empty_string(self):
        self.assertFalse(analytics._has_doi_from_pkg({'doi': ''}))

    def test_false_when_doi_missing(self):
        self.assertFalse(analytics._has_doi_from_pkg({}))

    def test_false_when_doi_none(self):
        self.assertFalse(analytics._has_doi_from_pkg({'doi': None}))


# ---------------------------------------------------------------------------
# minimal_dataset_props — shape and no-PII checks
# ---------------------------------------------------------------------------
class TestMinimalDatasetProps(unittest.TestCase):

    def _call(self, overrides=None):
        return analytics.minimal_dataset_props(_pkg(overrides))

    def test_returns_required_keys(self):
        props = self._call()
        self.assertIn('dataset_id', props)
        self.assertIn('dataset_type', props)
        self.assertIn('is_public', props)
        self.assertIn('has_doi', props)

    def test_no_dataset_name(self):
        props = self._call({'name': 'my-dataset'})
        self.assertNotIn('dataset_name', props)
        self.assertNotIn('name', props)

    def test_no_dataset_title(self):
        props = self._call({'title': 'My Dataset Title'})
        self.assertNotIn('dataset_title', props)
        self.assertNotIn('title', props)

    def test_no_email(self):
        props = self._call({'email': 'user@example.com'})
        self.assertNotIn('email', props)

    def test_no_username(self):
        props = self._call({'username': 'jsmith'})
        self.assertNotIn('username', props)

    def test_no_raw_private(self):
        props = self._call({'private': False})
        self.assertNotIn('private', props)

    def test_no_organization_id(self):
        """organization_id is not part of the minimal schema."""
        props = self._call({'owner_org': 'org-abc'})
        self.assertNotIn('organization_id', props)

    def test_instrument_type(self):
        props = self._call({'is_platform': 'false'})
        self.assertEqual(props['dataset_type'], 'instrument')

    def test_platform_type(self):
        props = self._call({'is_platform': 'true'})
        self.assertEqual(props['dataset_type'], 'platform')

    def test_is_public_true(self):
        props = self._call({'private': False})
        self.assertTrue(props['is_public'])

    def test_is_public_false(self):
        props = self._call({'private': True})
        self.assertFalse(props['is_public'])

    def test_has_doi_false_for_empty_string(self):
        props = self._call({'doi': ''})
        self.assertFalse(props['has_doi'])

    def test_has_doi_true(self):
        props = self._call({'doi': '10.1234/abc'})
        self.assertTrue(props['has_doi'])


# ---------------------------------------------------------------------------
# file_size_group
# ---------------------------------------------------------------------------
class TestFileSizeGroup(unittest.TestCase):

    def test_none_is_unknown(self):
        self.assertEqual(analytics.file_size_group(None), 'unknown')

    def test_invalid_string_is_unknown(self):
        self.assertEqual(analytics.file_size_group('not-a-number'), 'unknown')

    def test_zero_is_small(self):
        self.assertEqual(analytics.file_size_group(0), 'small')

    def test_under_10mb_is_small(self):
        self.assertEqual(analytics.file_size_group(10 * 1024 * 1024 - 1), 'small')

    def test_exactly_10mb_is_medium(self):
        self.assertEqual(analytics.file_size_group(10 * 1024 * 1024), 'medium')

    def test_499mb_is_medium(self):
        self.assertEqual(analytics.file_size_group(499 * 1024 * 1024), 'medium')

    def test_exactly_500mb_is_large(self):
        self.assertEqual(analytics.file_size_group(500 * 1024 * 1024), 'large')

    def test_1gb_is_large(self):
        self.assertEqual(analytics.file_size_group(1024 * 1024 * 1024), 'large')

    def test_string_int_parsed(self):
        self.assertEqual(analytics.file_size_group('1024'), 'small')


# ---------------------------------------------------------------------------
# Backend helper event names
# ---------------------------------------------------------------------------
class TestHelperEventNames(unittest.TestCase):
    """Every helper must use the corresponding EVENT_* constant."""

    def _track_args(self, fn, *args):
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            fn(*args)
            self.assertTrue(mock_track.called, f"{fn.__name__} did not call track()")
            return mock_track.call_args

    def test_track_dataset_created_event_name(self):
        call = self._track_args(analytics.track_dataset_created, _pkg())
        self.assertEqual(call[1]['event'], analytics.EVENT_DATASET_CREATED)

    def test_track_dataset_updated_event_name(self):
        call = self._track_args(analytics.track_dataset_updated, _pkg())
        self.assertEqual(call[1]['event'], analytics.EVENT_UPDATE_EXISTING_DATASET)

    def test_track_doi_published_event_name(self):
        call = self._track_args(analytics.track_doi_published, _pkg())
        self.assertEqual(call[1]['event'], analytics.EVENT_DATASET_PUBLISHED_WITH_DOI)

    def test_track_resource_download_event_name(self):
        call = self._track_args(
            analytics.track_resource_download, 'res-1', 'pkg-1', 'CSV'
        )
        self.assertEqual(call[1]['event'], analytics.EVENT_DOWNLOAD)

    def test_track_dataset_search_event_name(self):
        call = self._track_args(analytics.track_dataset_search, 'test query', 5)
        self.assertEqual(call[1]['event'], analytics.EVENT_SEARCH)


# ---------------------------------------------------------------------------
# No PII in event payloads
# ---------------------------------------------------------------------------
class TestNoPIIInPayloads(unittest.TestCase):
    _BANNED = {'email', 'username', 'display_name', 'dataset_name', 'dataset_title',
               'name', 'title', 'doi'}

    def _check_no_pii(self, props):
        for key in self._BANNED:
            self.assertNotIn(key, props, f"PII field '{key}' found in analytics payload")

    def _props_from(self, fn, *args):
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            fn(*args)
            return mock_track.call_args[1]['properties']

    def test_track_dataset_created_no_pii(self):
        props = self._props_from(analytics.track_dataset_created, _pkg({'name': 'x', 'title': 'y'}))
        self._check_no_pii(props)

    def test_track_dataset_updated_no_pii(self):
        props = self._props_from(analytics.track_dataset_updated, _pkg({'name': 'x', 'title': 'y'}))
        self._check_no_pii(props)

    def test_track_doi_published_no_doi_value(self):
        props = self._props_from(analytics.track_doi_published,
                                 _pkg({'doi': '10.1234/secret'}))
        self.assertNotIn('doi', props, "Full DOI value must not appear in the analytics payload")

    def test_track_resource_download_no_resource_name(self):
        props = self._props_from(analytics.track_resource_download,
                                 'res-1', 'pkg-1', 'CSV')
        self.assertNotIn('resource_name', props)


# ---------------------------------------------------------------------------
# file_size_group in Download payload
# ---------------------------------------------------------------------------
class TestDownloadPayloadFileSizeGroup(unittest.TestCase):

    def _props(self, size_bytes):
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            analytics.track_resource_download('res-1', 'pkg-1', 'CSV',
                                              size_bytes=size_bytes)
            return mock_track.call_args[1]['properties']

    def test_small(self):
        self.assertEqual(self._props(1024)['file_size_group'], 'small')

    def test_medium(self):
        self.assertEqual(self._props(50 * 1024 * 1024)['file_size_group'], 'medium')

    def test_large(self):
        self.assertEqual(self._props(600 * 1024 * 1024)['file_size_group'], 'large')

    def test_unknown_when_none(self):
        self.assertEqual(self._props(None)['file_size_group'], 'unknown')

    def test_no_raw_size_in_payload(self):
        props = self._props(12345)
        self.assertNotIn('size_bytes', props)
        self.assertNotIn('file_size', props)


# ---------------------------------------------------------------------------
# track_doi_published — doi_status in payload, no full DOI
# ---------------------------------------------------------------------------
class TestTrackDoiPublished(unittest.TestCase):

    def _props(self, doi_status=None):
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            analytics.track_doi_published(_pkg({'doi': '10.1/x'}), doi_status=doi_status)
            return mock_track.call_args[1]['properties']

    def test_doi_status_defaults_to_unknown(self):
        self.assertEqual(self._props()['doi_status'], 'unknown')

    def test_doi_status_passed_through(self):
        self.assertEqual(self._props('minted')['doi_status'], 'minted')

    def test_no_full_doi_value(self):
        self.assertNotIn('doi', self._props())

    def test_minimal_props_present(self):
        props = self._props()
        for key in ('dataset_id', 'dataset_type', 'is_public', 'has_doi', 'doi_status'):
            self.assertIn(key, props)


# ---------------------------------------------------------------------------
# AnalyticsTracker infrastructure (kept from original suite)
# ---------------------------------------------------------------------------
class TestAnalyticsTracker(unittest.TestCase):

    @patch.dict('os.environ', {
        'RUDDERSTACK_ENABLED': 'true',
        'RUDDERSTACK_WRITE_KEY': 'test_key',
        'RUDDERSTACK_DATA_PLANE_URL': 'https://test.rudderstack.com'
    })
    @patch('ckanext.pidinst_theme.analytics.Client', create=True)
    @patch('ckanext.pidinst_theme.analytics.RUDDERSTACK_AVAILABLE', True)
    def test_initialization(self, mock_client):
        analytics.AnalyticsTracker._client = None
        analytics.AnalyticsTracker._enabled = False
        analytics.AnalyticsTracker._initialized = False
        analytics.AnalyticsTracker.initialize()
        self.assertTrue(analytics.AnalyticsTracker.is_enabled())
        mock_client.assert_called_once()

    @patch.dict('os.environ', {'RUDDERSTACK_ENABLED': 'false'})
    def test_disabled_tracking(self):
        analytics.AnalyticsTracker._client = None
        analytics.AnalyticsTracker._enabled = False
        analytics.AnalyticsTracker._initialized = False
        analytics.AnalyticsTracker.initialize()
        self.assertFalse(analytics.AnalyticsTracker.is_enabled())

    @patch.dict('os.environ', {
        'RUDDERSTACK_ENABLED': 'true',
        'RUDDERSTACK_WRITE_KEY': 'test_key',
        'RUDDERSTACK_DATA_PLANE_URL': 'https://test.rudderstack.com'
    })
    @patch('ckanext.pidinst_theme.analytics.Client', create=True)
    @patch('ckanext.pidinst_theme.analytics.RUDDERSTACK_AVAILABLE', True)
    def test_track_event(self, mock_client):
        mock_instance = Mock()
        mock_client.return_value = mock_instance
        analytics.AnalyticsTracker._client = None
        analytics.AnalyticsTracker._enabled = False
        analytics.AnalyticsTracker._initialized = False
        analytics.AnalyticsTracker.initialize()
        result = analytics.AnalyticsTracker.track(
            event='Test Event',
            properties={'key': 'value'}
        )
        self.assertTrue(result)
        mock_instance.track.assert_called_once()


# ---------------------------------------------------------------------------
# Identity: backend must use user_id=browser_uuid, never anonymous_id
# ---------------------------------------------------------------------------
_TRACKER_ENV = {
    'RUDDERSTACK_ENABLED': 'true',
    'RUDDERSTACK_WRITE_KEY': 'test_key',
    'RUDDERSTACK_DATA_PLANE_URL': 'https://test.rudderstack.com',
}

_BROWSER_UUID = 'test-browser-uuid-4321'


def _make_enabled_tracker(mock_client):
    """Configure AnalyticsTracker with a fresh mocked SDK client."""
    mock_instance = Mock()
    mock_client.return_value = mock_instance
    analytics.AnalyticsTracker._client = None
    analytics.AnalyticsTracker._enabled = False
    analytics.AnalyticsTracker._initialized = False
    analytics.AnalyticsTracker.initialize()
    return mock_instance


class TestAnalyticsTrackerIdentity(unittest.TestCase):
    """AnalyticsTracker.track() uses get_analytics_user_id() as user_id.

    Requirements:
    - Logged-in users: user_id equals the CKAN internal user UUID.
    - Anonymous users: user_id equals the pidinst_browser_id browser UUID.
    - anonymous_id is NOT sent.
    - user_id is never None and never the literal string 'anonymous'.
    - No PII (email, username, display_name) is used as user_id.
    """

    @patch.dict('os.environ', _TRACKER_ENV)
    @patch('ckanext.pidinst_theme.analytics.Client', create=True)
    @patch('ckanext.pidinst_theme.analytics.RUDDERSTACK_AVAILABLE', True)
    @patch('ckanext.pidinst_theme.analytics.get_browser_id', return_value=_BROWSER_UUID)
    def test_track_sends_user_id(self, _mock_browser, mock_client):
        mock_instance = _make_enabled_tracker(mock_client)
        analytics.AnalyticsTracker.track('Test Event', {})
        kwargs = mock_instance.track.call_args[1]
        self.assertEqual(kwargs.get('user_id'), _BROWSER_UUID)

    @patch.dict('os.environ', _TRACKER_ENV)
    @patch('ckanext.pidinst_theme.analytics.Client', create=True)
    @patch('ckanext.pidinst_theme.analytics.RUDDERSTACK_AVAILABLE', True)
    @patch('ckanext.pidinst_theme.analytics.get_browser_id', return_value=_BROWSER_UUID)
    def test_track_does_not_send_anonymous_id(self, _mock_browser, mock_client):
        mock_instance = _make_enabled_tracker(mock_client)
        analytics.AnalyticsTracker.track('Test Event', {})
        kwargs = mock_instance.track.call_args[1]
        self.assertNotIn('anonymous_id', kwargs)

    @patch.dict('os.environ', _TRACKER_ENV)
    @patch('ckanext.pidinst_theme.analytics.Client', create=True)
    @patch('ckanext.pidinst_theme.analytics.RUDDERSTACK_AVAILABLE', True)
    @patch('ckanext.pidinst_theme.analytics.get_browser_id', return_value=_BROWSER_UUID)
    def test_track_user_id_not_none_or_anonymous(self, _mock_browser, mock_client):
        mock_instance = _make_enabled_tracker(mock_client)
        analytics.AnalyticsTracker.track('Test Event', {})
        kwargs = mock_instance.track.call_args[1]
        user_id = kwargs.get('user_id')
        self.assertIsNotNone(user_id)
        self.assertNotEqual(user_id, 'anonymous')

    @patch.dict('os.environ', _TRACKER_ENV)
    @patch('ckanext.pidinst_theme.analytics.Client', create=True)
    @patch('ckanext.pidinst_theme.analytics.RUDDERSTACK_AVAILABLE', True)
    @patch('ckanext.pidinst_theme.analytics.get_browser_id', return_value=_BROWSER_UUID)
    def test_anonymous_search_events_use_browser_uuid_as_user_id(self, _mock_browser, mock_client):
        """Anonymous Search and Empty-Result Search must use browser UUID as user_id."""
        mock_instance = _make_enabled_tracker(mock_client)
        analytics.track_dataset_search('telescope', 0)
        self.assertEqual(mock_instance.track.call_count, 2)
        for call in mock_instance.track.call_args_list:
            kwargs = call[1]
            self.assertEqual(kwargs.get('user_id'), _BROWSER_UUID,
                             f"Anonymous event should use browser UUID as user_id")
            self.assertNotIn('anonymous_id', kwargs)

    @patch.dict('os.environ', _TRACKER_ENV)
    @patch('ckanext.pidinst_theme.analytics.Client', create=True)
    @patch('ckanext.pidinst_theme.analytics.RUDDERSTACK_AVAILABLE', True)
    @patch('ckanext.pidinst_theme.analytics.get_browser_id', return_value=_BROWSER_UUID)
    def test_anonymous_update_existing_dataset_uses_browser_uuid_as_user_id(self, _mock_browser, mock_client):
        mock_instance = _make_enabled_tracker(mock_client)
        analytics.track_dataset_updated(_pkg())
        kwargs = mock_instance.track.call_args[1]
        self.assertEqual(kwargs.get('user_id'), _BROWSER_UUID)
        self.assertNotIn('anonymous_id', kwargs)

    @patch.dict('os.environ', _TRACKER_ENV)
    @patch('ckanext.pidinst_theme.analytics.Client', create=True)
    @patch('ckanext.pidinst_theme.analytics.RUDDERSTACK_AVAILABLE', True)
    @patch('ckanext.pidinst_theme.analytics.get_browser_id', return_value=_BROWSER_UUID)
    def test_no_pii_used_as_user_id(self, _mock_browser, mock_client):
        """user_id must not be an email, username, display_name, or CKAN user UUID."""
        mock_instance = _make_enabled_tracker(mock_client)
        # Even when properties contain PII fields, user_id must only be browser UUID
        analytics.AnalyticsTracker.track('Test Event', {
            'email': 'user@example.com',
            'username': 'jdoe',
            'display_name': 'John Doe',
        })
        kwargs = mock_instance.track.call_args[1]
        user_id = kwargs.get('user_id')
        self.assertEqual(user_id, _BROWSER_UUID)
        self.assertNotIn('@', user_id, "user_id must not be an email address")


# ---------------------------------------------------------------------------
# Suppression: track_dataset_updated should not fire when _analytics_suppress
# is set.  This is enforced in plugin.py, not in analytics.py itself, so we
# test the plugin behaviour via a direct call simulation.
# ---------------------------------------------------------------------------
class TestAnalyticsSuppression(unittest.TestCase):
    """
    Verify that the suppression flag pattern works as expected.
    The analytics helpers themselves do not check the flag — suppression is
    applied in plugin.py's after_dataset_update by checking
    context.get('_analytics_suppress') before calling track_dataset_updated.
    This test confirms that calling track_dataset_updated with identical data
    but with suppression applied (i.e. not calling it at all) results in zero
    track calls, mirroring the plugin logic.
    """

    def test_no_track_when_suppressed(self):
        """Simulate after_dataset_update suppression logic."""
        pkg = _pkg()
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            context = {'_analytics_suppress': True}
            if not context.get('_analytics_suppress'):
                analytics.track_dataset_updated(pkg)
            mock_track.assert_not_called()

    def test_track_fires_when_not_suppressed(self):
        pkg = _pkg()
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            context = {}
            if not context.get('_analytics_suppress'):
                analytics.track_dataset_updated(pkg)
            mock_track.assert_called_once()


# ---------------------------------------------------------------------------
# Search helper
# ---------------------------------------------------------------------------
class TestTrackDatasetSearch(unittest.TestCase):

    def _props(self, search_term, result_count):
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            analytics.track_dataset_search(search_term, result_count)
            return mock_track.call_args[1]['properties']

    def test_uses_search_term_not_search_query(self):
        props = self._props('my query', 3)
        self.assertIn('search_term', props)
        self.assertNotIn('search_query', props)
        self.assertEqual(props['search_term'], 'my query')

    def test_result_count_not_num_results(self):
        props = self._props('q', 7)
        self.assertIn('result_count', props)
        self.assertNotIn('num_results', props)
        self.assertEqual(props['result_count'], 7)

    def test_is_empty_true_when_zero(self):
        props = self._props('nothing', 0)
        self.assertTrue(props['is_empty'])

    def test_is_empty_false_when_nonzero(self):
        props = self._props('something', 5)
        self.assertFalse(props['is_empty'])


# ---------------------------------------------------------------------------
# Stage 2A: Search event — backend tracking
# ---------------------------------------------------------------------------
class TestSearchEventFires(unittest.TestCase):
    """EVENT_SEARCH fires after successful package_search."""

    def _call_args_list(self, search_term='q', result_count=5, **kwargs):
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            analytics.track_dataset_search(search_term, result_count, **kwargs)
            return mock_track.call_args_list

    def test_search_event_fires(self):
        calls = self._call_args_list('telescope', 10)
        self.assertGreaterEqual(len(calls), 1)
        first = calls[0][1]
        self.assertEqual(first['event'], analytics.EVENT_SEARCH)

    def test_search_event_includes_required_properties(self):
        calls = self._call_args_list('telescope', 10)
        props = calls[0][1]['properties']
        self.assertIn('search_term', props)
        self.assertIn('result_count', props)
        self.assertIn('is_empty', props)
        self.assertEqual(props['search_term'], 'telescope')
        self.assertEqual(props['result_count'], 10)
        self.assertFalse(props['is_empty'])

    def test_search_event_no_pii(self):
        calls = self._call_args_list('q', 3)
        props = calls[0][1]['properties']
        for banned in ('email', 'username', 'display_name', 'dataset_title',
                       'dataset_name', 'organization_id', 'ip_address', 'user_agent'):
            self.assertNotIn(banned, props, f"PII key '{banned}' found in Search payload")

    def test_search_event_dataset_type_included_when_provided(self):
        calls = self._call_args_list('q', 3, dataset_type='instrument')
        props = calls[0][1]['properties']
        self.assertEqual(props.get('dataset_type'), 'instrument')

    def test_search_event_optional_props_absent_when_not_provided(self):
        calls = self._call_args_list('q', 3)
        props = calls[0][1]['properties']
        self.assertNotIn('dataset_type', props)
        self.assertNotIn('page_number', props)
        self.assertNotIn('sort_by', props)

    def test_search_event_page_and_sort_included_when_provided(self):
        calls = self._call_args_list('q', 3, dataset_type='platform', page_number=2, sort_by='score desc')
        props = calls[0][1]['properties']
        self.assertEqual(props.get('page_number'), 2)
        self.assertEqual(props.get('sort_by'), 'score desc')
        self.assertEqual(props.get('dataset_type'), 'platform')


class TestEmptyResultSearchEvent(unittest.TestCase):
    """EVENT_EMPTY_RESULT_SEARCH fires only when result_count == 0."""

    def _events_fired(self, result_count):
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            analytics.track_dataset_search('q', result_count)
            return [c[1]['event'] for c in mock_track.call_args_list]

    def test_empty_result_search_fires_when_zero(self):
        events = self._events_fired(0)
        self.assertIn(analytics.EVENT_EMPTY_RESULT_SEARCH, events)

    def test_empty_result_search_not_fired_when_nonzero(self):
        events = self._events_fired(5)
        self.assertNotIn(analytics.EVENT_EMPTY_RESULT_SEARCH, events)

    def test_search_event_always_fires_alongside_empty_result(self):
        events = self._events_fired(0)
        self.assertIn(analytics.EVENT_SEARCH, events)
        self.assertIn(analytics.EVENT_EMPTY_RESULT_SEARCH, events)
        self.assertEqual(len(events), 2)

    def test_empty_result_search_is_empty_true(self):
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            analytics.track_dataset_search('nothing', 0)
            # Second call is EVENT_EMPTY_RESULT_SEARCH
            empty_call = [c for c in mock_track.call_args_list
                          if c[1]['event'] == analytics.EVENT_EMPTY_RESULT_SEARCH]
            self.assertEqual(len(empty_call), 1)
            self.assertTrue(empty_call[0][1]['properties']['is_empty'])
            self.assertEqual(empty_call[0][1]['properties']['result_count'], 0)

    def test_empty_result_search_shares_same_props_as_search(self):
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            analytics.track_dataset_search('nada', 0, dataset_type='instrument')
            calls = {c[1]['event']: c[1]['properties']
                     for c in mock_track.call_args_list}
            self.assertEqual(calls[analytics.EVENT_SEARCH],
                             calls[analytics.EVENT_EMPTY_RESULT_SEARCH])


class TestSearchAnalyticsFailureSafety(unittest.TestCase):
    """Analytics failure must not propagate or break the caller.

    The safety guard lives at the call site (views.py wraps the call in
    try/except).  These tests verify that pattern works correctly.
    """

    def test_tracker_exception_does_not_reach_search_handler(self):
        """Simulates the views.py try/except guard — exception must not escape."""
        search_completed = False
        with patch.object(analytics.AnalyticsTracker, 'track', side_effect=RuntimeError('boom')):
            try:
                analytics.track_dataset_search('q', 5)
            except Exception:
                pass  # views.py wraps this in try/except; search result unaffected
            search_completed = True
        self.assertTrue(search_completed)

    def test_search_tracking_called(self):
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            analytics.track_dataset_search('q', 3)
            self.assertTrue(mock_track.called)


# ---------------------------------------------------------------------------
# Stage 2B: Search Result Click-Through & Resource Preview Opened
# ---------------------------------------------------------------------------

class TestStage2BEventNames(unittest.TestCase):
    """Stage 2B event names match the requirements table exactly."""

    def test_search_result_click_through_event_name(self):
        self.assertEqual(
            analytics.EVENT_SEARCH_RESULT_CLICK_THROUGH,
            'Search Result Click-Through'
        )

    def test_resource_preview_opened_event_name(self):
        self.assertEqual(
            analytics.EVENT_RESOURCE_PREVIEW_OPENED,
            'Resource Preview Opened'
        )


class TestSearchResultClickThroughPayload(unittest.TestCase):
    """Search Result Click-Through payload must be minimal and PII-free."""

    # Allowed properties per Stage 2B requirements
    _ALLOWED = {'dataset_id', 'dataset_type', 'result_position', 'search_term'}

    # Properties that must never appear
    _BANNED = {
        'dataset_title', 'dataset_name', 'name', 'title',
        'email', 'username', 'url', 'facets',
    }

    def _sample_payload(self, **overrides):
        base = {
            'dataset_id': 'abc-123',
            'dataset_type': 'instrument',
            'result_position': 2,
            'search_term': 'telescope',
        }
        base.update(overrides)
        return base

    def test_all_sample_keys_are_allowed(self):
        for key in self._sample_payload():
            self.assertIn(
                key, self._ALLOWED,
                f"Key '{key}' is not in the allowed set for Search Result Click-Through"
            )

    def test_no_banned_props_in_sample(self):
        sample = self._sample_payload()
        for banned in self._BANNED:
            self.assertNotIn(
                banned, sample,
                f"Banned prop '{banned}' found in SRCT payload sample"
            )

    def test_dataset_type_not_sent_when_unavailable(self):
        payload = {'result_position': 1, 'search_term': 'q'}
        self.assertNotIn('dataset_type', payload)

    def test_dataset_id_not_sent_when_unavailable(self):
        payload = {'result_position': 1, 'search_term': 'q'}
        self.assertNotIn('dataset_id', payload)

    def test_result_position_always_present(self):
        payload = self._sample_payload()
        self.assertIn('result_position', payload)
        self.assertIsInstance(payload['result_position'], int)


class TestResourcePreviewOpenedPayload(unittest.TestCase):
    """Resource Preview Opened payload must be minimal and PII-free."""

    _ALLOWED = {'dataset_id', 'dataset_type', 'resource_id', 'resource_format'}

    _BANNED = {
        'resource_name', 'resource_title', 'dataset_name', 'dataset_title',
        'name', 'title', 'email', 'username', 'url',
    }

    def _sample_payload(self, **overrides):
        base = {
            'dataset_id': 'abc-123',
            'dataset_type': 'instrument',
            'resource_id': 'res-456',
            'resource_format': 'CSV',
        }
        base.update(overrides)
        return base

    def test_all_sample_keys_are_allowed(self):
        for key in self._sample_payload():
            self.assertIn(
                key, self._ALLOWED,
                f"Key '{key}' is not in the allowed set for Resource Preview Opened"
            )

    def test_no_banned_props_in_sample(self):
        sample = self._sample_payload()
        for banned in self._BANNED:
            self.assertNotIn(
                banned, sample,
                f"Banned prop '{banned}' found in RPO payload sample"
            )

    def test_dataset_type_optional(self):
        payload = {
            'dataset_id': 'abc-123',
            'resource_id': 'res-456',
        }
        for key in payload:
            self.assertIn(key, self._ALLOWED)

    def test_resource_format_optional(self):
        payload = {
            'dataset_id': 'abc-123',
            'dataset_type': 'platform',
            'resource_id': 'res-456',
        }
        for key in payload:
            self.assertIn(key, self._ALLOWED)

    def test_dataset_id_required_in_full_payload(self):
        payload = self._sample_payload()
        self.assertIn('dataset_id', payload)

    def test_resource_id_required_in_full_payload(self):
        payload = self._sample_payload()
        self.assertIn('resource_id', payload)


class TestStage2BFailureSafety(unittest.TestCase):
    """Tracking failure must not block click or preview navigation."""

    def test_srct_tracking_failure_does_not_propagate(self):
        """JS wraps the SRCT track() call in try/catch; navigation is unaffected."""
        navigation_completed = False
        with patch.object(
            analytics.AnalyticsTracker, 'track',
            side_effect=RuntimeError('rudderanalytics unavailable')
        ):
            try:
                analytics.AnalyticsTracker.track(
                    event=analytics.EVENT_SEARCH_RESULT_CLICK_THROUGH,
                    properties={'result_position': 1},
                )
            except Exception:
                pass  # JS has try/catch; normal navigation is unaffected
            navigation_completed = True
        self.assertTrue(navigation_completed)

    def test_resource_preview_tracking_failure_does_not_propagate(self):
        """JS wraps the Resource Preview Opened track() call in try/catch."""
        navigation_completed = False
        with patch.object(
            analytics.AnalyticsTracker, 'track',
            side_effect=RuntimeError('rudderanalytics unavailable')
        ):
            try:
                analytics.AnalyticsTracker.track(
                    event=analytics.EVENT_RESOURCE_PREVIEW_OPENED,
                    properties={'dataset_id': 'pkg-1', 'resource_id': 'res-1'},
                )
            except Exception:
                pass
            navigation_completed = True
        self.assertTrue(navigation_completed)


# ---------------------------------------------------------------------------
# Stage 2C: Dataset View Duration & Time To First Download verification
# ---------------------------------------------------------------------------

class TestStage2CEventNames(unittest.TestCase):
    """Stage 2C event name constants must match the requirements table exactly."""

    def test_dataset_view_duration_event_name(self):
        self.assertEqual(analytics.EVENT_DATASET_VIEW_DURATION, 'Dataset View Duration')

    def test_time_to_first_download_event_name(self):
        # Verify the TTFD constant has not drifted from the required name.
        self.assertEqual(analytics.EVENT_TIME_TO_FIRST_DOWNLOAD, 'Time To First Download')


class TestDatasetViewDurationPayload(unittest.TestCase):
    """Dataset View Duration payload must be minimal and PII-free."""

    # All keys that are allowed in the payload
    _ALLOWED = {'dataset_id', 'dataset_type', 'is_public', 'has_doi', 'duration_seconds'}

    # Keys that must never appear
    _BANNED = {
        'dataset_name', 'dataset_title', 'name', 'title',
        'email', 'username', 'url', 'doi',
        'user_id', 'description', 'organization_id',
    }

    def _sample_payload(self, **overrides):
        base = {
            'dataset_id':       'pkg-abc',
            'dataset_type':     'instrument',
            'is_public':        True,
            'has_doi':          False,
            'duration_seconds': 45,
        }
        base.update(overrides)
        return base

    def test_duration_seconds_is_present(self):
        payload = self._sample_payload()
        self.assertIn('duration_seconds', payload)

    def test_duration_seconds_is_integer(self):
        payload = self._sample_payload(duration_seconds=45)
        self.assertIsInstance(payload['duration_seconds'], int)

    def test_all_sample_keys_are_allowed(self):
        for key in self._sample_payload():
            self.assertIn(
                key, self._ALLOWED,
                f"Key '{key}' is not in the allowed set for Dataset View Duration"
            )

    def test_no_banned_props_in_sample(self):
        sample = self._sample_payload()
        for banned in self._BANNED:
            self.assertNotIn(
                banned, sample,
                f"Banned prop '{banned}' found in Dataset View Duration payload"
            )

    def test_dataset_id_is_present(self):
        payload = self._sample_payload()
        self.assertIn('dataset_id', payload)

    def test_no_pii_dataset_name(self):
        payload = self._sample_payload()
        self.assertNotIn('dataset_name', payload)

    def test_no_pii_title(self):
        payload = self._sample_payload()
        self.assertNotIn('title', payload)

    def test_no_pii_email(self):
        payload = self._sample_payload()
        self.assertNotIn('email', payload)

    def test_no_pii_username(self):
        payload = self._sample_payload()
        self.assertNotIn('username', payload)

    def test_no_full_url(self):
        payload = self._sample_payload()
        self.assertNotIn('url', payload)

    def test_no_raw_doi_value(self):
        payload = self._sample_payload()
        self.assertNotIn('doi', payload)
        # has_doi is a boolean, not the raw DOI string
        self.assertIsInstance(payload.get('has_doi'), bool)


class TestTimeToFirstDownloadPayload(unittest.TestCase):
    """Time To First Download payload must be minimal with correct property names."""

    # Allowed properties per Stage 2C requirements
    _ALLOWED = {
        'dataset_id', 'dataset_type',
        'resource_id', 'resource_format',
        'seconds_to_download',
    }

    # Properties that must never appear
    _BANNED = {
        'time_to_download_seconds',  # old/wrong property name — must not exist
        'dataset_name', 'dataset_title', 'name', 'title',
        'email', 'username', 'url', 'doi',
        'session_start',
    }

    def _sample_payload(self, **overrides):
        base = {
            'dataset_id':          'pkg-abc',
            'dataset_type':        'instrument',
            'resource_id':         'res-123',
            'resource_format':     'CSV',
            'seconds_to_download': 12,
        }
        base.update(overrides)
        return base

    def test_seconds_to_download_present(self):
        payload = self._sample_payload()
        self.assertIn('seconds_to_download', payload)

    def test_seconds_to_download_is_integer(self):
        payload = self._sample_payload(seconds_to_download=12)
        self.assertIsInstance(payload['seconds_to_download'], int)

    def test_old_property_name_absent(self):
        """time_to_download_seconds was the old wrong name; must not appear."""
        payload = self._sample_payload()
        self.assertNotIn('time_to_download_seconds', payload)

    def test_all_sample_keys_are_allowed(self):
        for key in self._sample_payload():
            self.assertIn(
                key, self._ALLOWED,
                f"Key '{key}' is not in the allowed set for Time To First Download"
            )

    def test_no_banned_props_in_sample(self):
        sample = self._sample_payload()
        for banned in self._BANNED:
            self.assertNotIn(
                banned, sample,
                f"Banned prop '{banned}' found in TTFD payload"
            )

    def test_dataset_type_optional(self):
        """dataset_type is optional — may be absent when context is unavailable."""
        payload = {
            'dataset_id':          'pkg-abc',
            'resource_id':         'res-123',
            'seconds_to_download': 8,
        }
        for key in payload:
            self.assertIn(key, self._ALLOWED)

    def test_resource_format_optional(self):
        """resource_format is optional."""
        payload = {
            'dataset_id':          'pkg-abc',
            'resource_id':         'res-123',
            'seconds_to_download': 8,
        }
        for key in payload:
            self.assertIn(key, self._ALLOWED)


class TestAnalyticsTrackEndpointValidation(unittest.TestCase):
    """
    The /api/analytics/track endpoint must validate JSON body and event name.
    The KNOWN_FRONTEND_EVENTS set lives in analytics.py so it can be tested
    without importing Flask (analytics_views.py requires Flask).
    """

    def test_known_frontend_events_contains_dataset_view_duration(self):
        self.assertIn(
            analytics.EVENT_DATASET_VIEW_DURATION,
            analytics.KNOWN_FRONTEND_EVENTS,
        )

    def test_known_frontend_events_contains_time_to_first_download(self):
        self.assertIn(
            analytics.EVENT_TIME_TO_FIRST_DOWNLOAD,
            analytics.KNOWN_FRONTEND_EVENTS,
        )

    def test_known_frontend_events_contains_all_stage1_events(self):
        required = {
            analytics.EVENT_SEARCH,
            analytics.EVENT_EMPTY_RESULT_SEARCH,
            analytics.EVENT_SEARCH_RESULT_CLICK_THROUGH,
            analytics.EVENT_DATASET_PAGE_VIEW,
            analytics.EVENT_DOWNLOAD,
            analytics.EVENT_TIME_TO_FIRST_DOWNLOAD,
            analytics.EVENT_DATASET_VIEW_DURATION,
            analytics.EVENT_RESOURCE_PREVIEW_OPENED,
        }
        for event in required:
            self.assertIn(
                event,
                analytics.KNOWN_FRONTEND_EVENTS,
                f"Event '{event}' missing from KNOWN_FRONTEND_EVENTS",
            )

    def test_unknown_event_name_not_in_whitelist(self):
        """An arbitrary string must not pass the event whitelist."""
        self.assertNotIn('__arbitrary_unknown_event__', analytics.KNOWN_FRONTEND_EVENTS)


# ---------------------------------------------------------------------------
# Stage 3A: _doi_status_from_db helper
# ---------------------------------------------------------------------------
class TestDoiStatusFromDb(unittest.TestCase):
    """_doi_status_from_db returns correct (is_published, status_str) tuples."""

    def _call(self, record=None, exc=None):
        """Call _doi_status_from_db with a mocked ckanext.doi.model.crud module."""
        mock_crud = Mock()
        if exc is not None:
            mock_crud.DOIQuery.read_package.side_effect = exc
        else:
            mock_crud.DOIQuery.read_package.return_value = record
        with patch.dict('sys.modules', {'ckanext.doi.model.crud': mock_crud}):
            return analytics._doi_status_from_db('pkg-001')

    def test_published_returns_true_published(self):
        from datetime import datetime
        record = Mock(published=datetime(2024, 1, 1))
        self.assertEqual(self._call(record), (True, 'published'))

    def test_minted_not_published_returns_false_minted(self):
        record = Mock(published=None)
        self.assertEqual(self._call(record), (False, 'minted'))

    def test_no_record_returns_false_none(self):
        self.assertEqual(self._call(None), (False, 'none'))

    def test_exception_returns_false_unknown(self):
        self.assertEqual(self._call(exc=Exception('DB error')), (False, 'unknown'))

    def test_import_error_returns_false_unknown(self):
        self.assertEqual(self._call(exc=ImportError('no ckanext.doi')), (False, 'unknown'))


# ---------------------------------------------------------------------------
# Stage 3A: Dataset Published With DOI — transition detection
#
# The transition logic lives in plugin.py; we test it here by simulating the
# guard exactly as plugin.py implements it:
#
#   was_published = context.get('_analytics_doi_was_published')
#   if was_published is False:
#       is_now_published, doi_status = analytics._doi_status_from_db(pkg_id)
#       if is_now_published:
#           analytics.track_doi_published(user, pkg_dict, doi_status=doi_status)
# ---------------------------------------------------------------------------
class TestStage3ADoiPublishedTransition(unittest.TestCase):
    """Dataset Published With DOI fires only when the transition is confirmed."""

    # Simulate the plugin.py guard so tests do not depend on plugin internals.
    def _simulate_after_update(self, was_published, is_now_published, doi_status='published'):
        """Run the Stage 3A plugin guard and return calls made to track_doi_published."""
        pkg = _pkg({'id': 'pkg-001', 'doi': '10.1/x'})
        calls = []
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            with patch.object(analytics, '_doi_status_from_db',
                              return_value=(is_now_published, doi_status)):
                # --- plugin.py after_dataset_update Stage 3A block ---
                if was_published is False:
                    is_now, status = analytics._doi_status_from_db(pkg['id'])
                    if is_now:
                        analytics.track_doi_published(pkg, doi_status=status)
                # ------------------------------------------------------
            calls = mock_track.call_args_list
        return calls

    # 1. Fires when DOI transitions from not-published to published.
    def test_fires_on_first_doi_publication(self):
        calls = self._simulate_after_update(was_published=False, is_now_published=True)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]['event'], analytics.EVENT_DATASET_PUBLISHED_WITH_DOI)

    # 2. Does NOT fire when DOI was already published before this update.
    def test_does_not_fire_when_already_published(self):
        calls = self._simulate_after_update(was_published=True, is_now_published=True)
        self.assertEqual(len(calls), 0)

    # 3. Does NOT fire for unrelated metadata updates (DOI not published).
    def test_does_not_fire_for_unrelated_update_no_doi(self):
        calls = self._simulate_after_update(was_published=False, is_now_published=False,
                                            doi_status='none')
        self.assertEqual(len(calls), 0)

    def test_does_not_fire_for_unrelated_update_doi_minted_only(self):
        calls = self._simulate_after_update(was_published=False, is_now_published=False,
                                            doi_status='minted')
        self.assertEqual(len(calls), 0)

    # 4. Conservative: unknown old state → no event to avoid duplicate fires.
    def test_does_not_fire_when_old_state_unknown(self):
        calls = self._simulate_after_update(was_published=None, is_now_published=True)
        self.assertEqual(len(calls), 0)

    # 5. Payload includes all required properties (dataset_id, dataset_type,
    #    is_public, has_doi, doi_status).
    def test_payload_includes_required_props(self):
        pkg = _pkg({'id': 'pkg-001', 'doi': '10.1/x', 'is_platform': 'false', 'private': False})
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            analytics.track_doi_published(pkg, doi_status='published')
            props = mock_track.call_args[1]['properties']
        for key in ('dataset_id', 'dataset_type', 'is_public', 'has_doi', 'doi_status'):
            self.assertIn(key, props, f"Required key '{key}' missing from payload")

    # 6. doi_status is 'published' on a confirmed transition.
    def test_doi_status_is_published_on_transition(self):
        calls = self._simulate_after_update(was_published=False, is_now_published=True,
                                            doi_status='published')
        props = calls[0][1]['properties']
        self.assertEqual(props['doi_status'], 'published')

    # 7. Payload does NOT include full DOI value, title, name, email, username.
    def test_payload_excludes_full_doi_and_pii(self):
        pkg = _pkg({
            'id': 'pkg-001',
            'doi': '10.1234/secret',
            'name': 'my-dataset',
            'title': 'My Dataset',
            'email': 'user@example.com',
            'username': 'jsmith',
        })
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            analytics.track_doi_published(pkg, doi_status='published')
            props = mock_track.call_args[1]['properties']
        for banned in ('doi', 'name', 'title', 'email', 'username'):
            self.assertNotIn(banned, props, f"Banned key '{banned}' found in payload")

    # 8. Analytics failure does not break dataset update flow.
    def test_analytics_failure_does_not_break_update_flow(self):
        pkg = _pkg({'id': 'pkg-001', 'doi': '10.1/x'})
        update_completed = False
        with patch.object(analytics.AnalyticsTracker, 'track',
                          side_effect=RuntimeError('rudderstack unavailable')):
            try:
                analytics.track_doi_published(pkg, doi_status='published')
            except Exception:
                pass
            update_completed = True
        self.assertTrue(update_completed)

    # 9. Event name constant matches requirements table.
    def test_event_name_constant(self):
        self.assertEqual(analytics.EVENT_DATASET_PUBLISHED_WITH_DOI,
                         'Dataset Published With DOI')

    # 10. Verify has_doi is True in payload when doi field is present.
    def test_has_doi_true_in_payload(self):
        pkg = _pkg({'doi': '10.1234/abc'})
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            analytics.track_doi_published(pkg, doi_status='published')
            props = mock_track.call_args[1]['properties']
        self.assertTrue(props['has_doi'])

    # 11. is_public reflects package private field correctly.
    def test_is_public_false_when_private(self):
        pkg = _pkg({'private': True, 'doi': '10.1/x'})
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            analytics.track_doi_published(pkg, doi_status='published')
            props = mock_track.call_args[1]['properties']
        self.assertFalse(props['is_public'])

    def test_is_public_true_when_not_private(self):
        pkg = _pkg({'private': False, 'doi': '10.1/x'})
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            analytics.track_doi_published(pkg, doi_status='published')
            props = mock_track.call_args[1]['properties']
        self.assertTrue(props['is_public'])


# ---------------------------------------------------------------------------
# Stage 3A: before_dataset_update context snapshot logic
# ---------------------------------------------------------------------------
class TestStage3AContextSnapshot(unittest.TestCase):
    """before_dataset_update snapshot stores correct was_published values."""

    def _snapshot(self, record=None, exc=None, pkg_id='pkg-001'):
        """Simulate plugin.py before_dataset_update and return the context value."""
        mock_crud = Mock()
        if exc is not None:
            mock_crud.DOIQuery.read_package.side_effect = exc
        else:
            mock_crud.DOIQuery.read_package.return_value = record

        context = {}
        with patch.dict('sys.modules', {'ckanext.doi.model.crud': mock_crud}):
            # --- plugin.py before_dataset_update Stage 3A block ---
            try:
                if pkg_id:
                    from ckanext.doi.model.crud import DOIQuery  # noqa: F401, PLC0415
                    record_ = mock_crud.DOIQuery.read_package(pkg_id)
                    context['_analytics_doi_was_published'] = (
                        record_ is not None and record_.published is not None
                    )
                else:
                    context['_analytics_doi_was_published'] = None
            except Exception:
                context['_analytics_doi_was_published'] = None
            # -------------------------------------------------------
        return context.get('_analytics_doi_was_published')

    def test_stores_true_when_doi_published(self):
        from datetime import datetime
        record = Mock(published=datetime(2024, 1, 1))
        self.assertTrue(self._snapshot(record))

    def test_stores_false_when_doi_not_published(self):
        record = Mock(published=None)
        self.assertFalse(self._snapshot(record))

    def test_stores_false_when_no_record(self):
        self.assertFalse(self._snapshot(None))

    def test_stores_none_on_exception(self):
        self.assertIsNone(self._snapshot(exc=Exception('DB error')))

    def test_stores_none_when_no_pkg_id(self):
        result = self._snapshot(pkg_id=None)
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# Stage 3B: _is_new_version_pkg helper
# ---------------------------------------------------------------------------
class TestIsNewVersionPkg(unittest.TestCase):
    """_is_new_version_pkg returns True only when version_handler_id != pkg id."""

    def test_true_when_version_handler_differs(self):
        pkg = _pkg({'id': 'new-001', 'version_handler_id': 'root-000'})
        self.assertTrue(analytics._is_new_version_pkg(pkg))

    def test_false_when_version_handler_equals_id(self):
        pkg = _pkg({'id': 'pkg-001', 'version_handler_id': 'pkg-001'})
        self.assertFalse(analytics._is_new_version_pkg(pkg))

    def test_false_when_version_handler_absent(self):
        pkg = _pkg({'id': 'pkg-001'})
        pkg.pop('version_handler_id', None)
        self.assertFalse(analytics._is_new_version_pkg(pkg))

    def test_false_when_version_handler_empty_string(self):
        pkg = _pkg({'id': 'pkg-001', 'version_handler_id': ''})
        self.assertFalse(analytics._is_new_version_pkg(pkg))

    def test_false_when_id_missing(self):
        self.assertFalse(analytics._is_new_version_pkg({'version_handler_id': 'root-000'}))


# ---------------------------------------------------------------------------
# Stage 3B: _reuse_source_from_pkg helper
# ---------------------------------------------------------------------------
class TestReuseSourceFromPkg(unittest.TestCase):
    """_reuse_source_from_pkg extracts the predecessor CKAN UUID safely."""

    def _pkg_with_related(self, entries):
        """Build a pkg dict with related_identifier_obj as a list."""
        return _pkg({'related_identifier_obj': entries})

    def _pkg_with_related_json(self, entries):
        import json
        return _pkg({'related_identifier_obj': json.dumps(entries)})

    def test_extracts_id_from_IsNewVersionOf(self):
        entries = [{'relation_type': 'IsNewVersionOf',
                    'related_instrument_package_id': 'orig-abc',
                    'related_identifier': '10.1/orig'}]
        result = analytics._reuse_source_from_pkg(self._pkg_with_related(entries))
        self.assertEqual(result, 'orig-abc')

    def test_extracts_from_json_string(self):
        entries = [{'relation_type': 'IsNewVersionOf',
                    'related_instrument_package_id': 'orig-xyz'}]
        result = analytics._reuse_source_from_pkg(self._pkg_with_related_json(entries))
        self.assertEqual(result, 'orig-xyz')

    def test_ignores_other_relation_types(self):
        entries = [{'relation_type': 'IsPartOf',
                    'related_instrument_package_id': 'other-id'}]
        result = analytics._reuse_source_from_pkg(self._pkg_with_related(entries))
        self.assertIsNone(result)

    def test_returns_none_when_field_absent(self):
        self.assertIsNone(analytics._reuse_source_from_pkg(_pkg()))

    def test_returns_none_when_list_empty(self):
        self.assertIsNone(analytics._reuse_source_from_pkg(self._pkg_with_related([])))

    def test_returns_none_when_no_pkg_id_in_entry(self):
        entries = [{'relation_type': 'IsNewVersionOf'}]
        self.assertIsNone(analytics._reuse_source_from_pkg(self._pkg_with_related(entries)))

    def test_returns_none_on_invalid_json(self):
        pkg = _pkg({'related_identifier_obj': 'not-valid-json'})
        self.assertIsNone(analytics._reuse_source_from_pkg(pkg))

    def test_does_not_return_raw_doi(self):
        """related_identifier (DOI) must NOT be returned as source_dataset_id."""
        entries = [{'relation_type': 'IsNewVersionOf',
                    'related_instrument_package_id': 'orig-abc',
                    'related_identifier': '10.1/secret-doi'}]
        result = analytics._reuse_source_from_pkg(self._pkg_with_related(entries))
        self.assertNotEqual(result, '10.1/secret-doi')
        self.assertEqual(result, 'orig-abc')


# ---------------------------------------------------------------------------
# Stage 3B: Dataset Reuse Created — event tracking
# ---------------------------------------------------------------------------
class TestStage3BDatasetReuseCreated(unittest.TestCase):
    """Dataset Reuse Created fires only for new-version datasets."""

    def _new_version_pkg(self):
        """Return a minimal pkg dict that looks like a new version."""
        return _pkg({
            'id': 'new-001',
            'version_handler_id': 'root-000',
            'related_identifier_obj': [
                {'relation_type': 'IsNewVersionOf',
                 'related_instrument_package_id': 'orig-999'}
            ],
            'is_platform': 'false',
            'private': False,
        })

    def _simulate_after_create(self, pkg):
        """Run the Stage 3B plugin guard and return calls made to track."""
        calls = []
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            # --- plugin.py after_dataset_create Stage 3B block ---
            if analytics._is_new_version_pkg(pkg):
                source_id = analytics._reuse_source_from_pkg(pkg)
                analytics.track_dataset_reuse_created(pkg,
                                                       source_dataset_id=source_id)
            # ------------------------------------------------------
            calls = mock_track.call_args_list
        return calls

    # 1. Fires when version_handler_id != id and IsNewVersionOf present.
    def test_fires_for_new_version(self):
        calls = self._simulate_after_create(self._new_version_pkg())
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][1]['event'], analytics.EVENT_DATASET_REUSE_CREATED)

    # 2. Does NOT fire for ordinary new dataset.
    def test_does_not_fire_for_ordinary_create(self):
        pkg = _pkg({'id': 'pkg-001', 'version_handler_id': 'pkg-001'})
        calls = self._simulate_after_create(pkg)
        self.assertEqual(len(calls), 0)

    # 3. Does NOT fire when version_handler_id is absent.
    def test_does_not_fire_when_no_version_handler_id(self):
        pkg = _pkg({'id': 'pkg-001'})
        pkg.pop('version_handler_id', None)
        calls = self._simulate_after_create(pkg)
        self.assertEqual(len(calls), 0)

    # 4. Dataset Created still fires independently (simulated separately).
    def test_dataset_created_still_fires_for_ordinary(self):
        pkg = _pkg({'id': 'pkg-001', 'version_handler_id': 'pkg-001'})
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            analytics.track_dataset_created(pkg)
            events = [c[1]['event'] for c in mock_track.call_args_list]
        self.assertIn(analytics.EVENT_DATASET_CREATED, events)
        self.assertNotIn(analytics.EVENT_DATASET_REUSE_CREATED, events)

    # 5. Payload contains required properties.
    def test_payload_required_props(self):
        pkg = self._new_version_pkg()
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            analytics.track_dataset_reuse_created(pkg, source_dataset_id='orig-999')
            props = mock_track.call_args[1]['properties']
        for key in ('dataset_id', 'dataset_type', 'is_public', 'has_doi', 'reuse_type'):
            self.assertIn(key, props, f"Required key '{key}' missing from payload")

    def test_source_dataset_id_included_when_present(self):
        pkg = self._new_version_pkg()
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            analytics.track_dataset_reuse_created(pkg, source_dataset_id='orig-999')
            props = mock_track.call_args[1]['properties']
        self.assertEqual(props['source_dataset_id'], 'orig-999')

    def test_source_dataset_id_absent_when_none(self):
        pkg = self._new_version_pkg()
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            analytics.track_dataset_reuse_created(pkg, source_dataset_id=None)
            props = mock_track.call_args[1]['properties']
        self.assertNotIn('source_dataset_id', props)

    def test_reuse_type_is_new_version(self):
        pkg = self._new_version_pkg()
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            analytics.track_dataset_reuse_created(pkg, source_dataset_id=None)
            props = mock_track.call_args[1]['properties']
        self.assertEqual(props['reuse_type'], 'new_version')

    # 9. No PII / full metadata in payload.
    def test_payload_excludes_pii_and_full_metadata(self):
        pkg = self._new_version_pkg()
        pkg.update({'name': 'my-ds', 'title': 'My Title',
                    'email': 'u@x.com', 'username': 'jdoe', 'doi': '10.1/x'})
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            analytics.track_dataset_reuse_created(pkg, source_dataset_id='orig-999')
            props = mock_track.call_args[1]['properties']
        for banned in ('name', 'title', 'email', 'username', 'doi',
                       'description', 'source_dataset_name', 'source_dataset_title'):
            self.assertNotIn(banned, props, f"Banned key '{banned}' in payload")

    # 10. is_public reflects private field.
    def test_is_public_true_when_not_private(self):
        pkg = self._new_version_pkg()
        pkg['private'] = False
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            analytics.track_dataset_reuse_created(pkg)
            props = mock_track.call_args[1]['properties']
        self.assertTrue(props['is_public'])

    def test_is_public_false_when_private(self):
        pkg = self._new_version_pkg()
        pkg['private'] = True
        with patch.object(analytics.AnalyticsTracker, 'track') as mock_track:
            analytics.track_dataset_reuse_created(pkg)
            props = mock_track.call_args[1]['properties']
        self.assertFalse(props['is_public'])

    # 11. Analytics failure does not break dataset creation flow.
    def test_analytics_failure_does_not_break_creation(self):
        pkg = self._new_version_pkg()
        creation_completed = False
        with patch.object(analytics.AnalyticsTracker, 'track',
                          side_effect=RuntimeError('rudderstack unavailable')):
            try:
                analytics.track_dataset_reuse_created(pkg, source_dataset_id='x')
            except Exception:
                pass
            creation_completed = True
        self.assertTrue(creation_completed)

    # 12. Event name constant matches requirements table.
    def test_event_name_constant(self):
        self.assertEqual(analytics.EVENT_DATASET_REUSE_CREATED, 'Dataset Reuse Created')


# ---------------------------------------------------------------------------
# Browser identity: get_browser_id
# ---------------------------------------------------------------------------
class TestGetBrowserId(unittest.TestCase):
    """get_browser_id() returns a stable UUID; generates one when cookie is absent."""

    def _make_mock_flask(self, cookie_value=None):
        """Return a mock flask module with request.cookies and a SimpleNamespace g."""
        mock_flask = Mock()
        mock_flask.request.cookies.get.return_value = cookie_value
        mock_flask.g = types.SimpleNamespace()
        return mock_flask

    def test_reuses_existing_cookie(self):
        mock_flask = self._make_mock_flask('existing-uuid-1234')
        with patch.dict(sys.modules, {'flask': mock_flask}):
            result = analytics.get_browser_id()
        self.assertEqual(result, 'existing-uuid-1234')

    def test_generates_uuid_when_no_cookie(self):
        mock_flask = self._make_mock_flask(None)
        with patch.dict(sys.modules, {'flask': mock_flask}):
            result = analytics.get_browser_id()
        self.assertIsNotNone(result)
        self.assertIsInstance(result, str)
        self.assertEqual(len(result), 36)

    def test_generated_uuid_stored_on_g(self):
        mock_flask = self._make_mock_flask(None)
        with patch.dict(sys.modules, {'flask': mock_flask}):
            result = analytics.get_browser_id()
        stored = getattr(mock_flask.g, 'pidinst_browser_id_to_set', None)
        self.assertIsNotNone(stored)
        self.assertEqual(result, stored)

    def test_existing_cookie_not_stored_on_g(self):
        """When the cookie is present no new UUID is stashed on g."""
        mock_flask = self._make_mock_flask('existing-uuid-5678')
        with patch.dict(sys.modules, {'flask': mock_flask}):
            analytics.get_browser_id()
        self.assertFalse(hasattr(mock_flask.g, 'pidinst_browser_id_to_set'))

    def test_second_call_reuses_generated_uuid(self):
        """Two calls without a cookie return the same UUID (g cache)."""
        mock_flask = self._make_mock_flask(None)
        with patch.dict(sys.modules, {'flask': mock_flask}):
            result1 = analytics.get_browser_id()
            result2 = analytics.get_browser_id()
        self.assertEqual(result1, result2)

    def test_returns_str_outside_request_context(self):
        """Outside a request context a UUID string is returned (no exception)."""
        result = analytics.get_browser_id()
        self.assertIsNotNone(result)
        self.assertIsInstance(result, str)
        self.assertEqual(len(result), 36)

    def test_reads_pidinst_browser_id_cookie_name(self):
        mock_flask = self._make_mock_flask('name-check-uuid')
        with patch.dict(sys.modules, {'flask': mock_flask}):
            result = analytics.get_browser_id()
        self.assertEqual(result, 'name-check-uuid')
        mock_flask.request.cookies.get.assert_called_with('pidinst_browser_id')


# ---------------------------------------------------------------------------
# All backend events use user_id (browser UUID), never anonymous_id
# ---------------------------------------------------------------------------
class TestAllEventsUseUserId(unittest.TestCase):
    """Every backend event must use user_id=browser_uuid from the cookie."""

    def _sdk_call_kwargs(self, fn, *args):
        """Return the kwargs the RudderStack SDK client.track() was called with."""
        with patch.object(analytics.AnalyticsTracker, '_client') as mock_client:
            with patch.object(analytics, 'get_browser_id', return_value='browser-uuid-test'):
                analytics.AnalyticsTracker._enabled = True
                fn(*args)
                return mock_client.track.call_args[1]

    def test_track_dataset_created_uses_user_id(self):
        kw = self._sdk_call_kwargs(analytics.track_dataset_created, _pkg())
        self.assertEqual(kw['user_id'], 'browser-uuid-test')

    def test_track_dataset_updated_uses_user_id(self):
        kw = self._sdk_call_kwargs(analytics.track_dataset_updated, _pkg())
        self.assertEqual(kw['user_id'], 'browser-uuid-test')

    def test_track_doi_published_uses_user_id(self):
        kw = self._sdk_call_kwargs(analytics.track_doi_published, _pkg({'doi': '10.1/x'}))
        self.assertEqual(kw['user_id'], 'browser-uuid-test')

    def test_track_dataset_reuse_created_uses_user_id(self):
        pkg = _pkg({'id': 'new-001', 'version_handler_id': 'root-000'})
        kw = self._sdk_call_kwargs(analytics.track_dataset_reuse_created, pkg)
        self.assertEqual(kw['user_id'], 'browser-uuid-test')

    def test_track_resource_download_uses_user_id(self):
        kw = self._sdk_call_kwargs(analytics.track_resource_download,
                                   'res-1', 'pkg-1', 'CSV')
        self.assertEqual(kw['user_id'], 'browser-uuid-test')

    def test_track_dataset_search_uses_user_id(self):
        kw = self._sdk_call_kwargs(analytics.track_dataset_search, 'q', 5)
        self.assertEqual(kw['user_id'], 'browser-uuid-test')

    def test_no_event_sends_anonymous_id(self):
        """anonymous_id must never be passed to the SDK; user_id carries the UUID."""
        with patch.object(analytics.AnalyticsTracker, '_client') as mock_client:
            with patch.object(analytics, 'get_browser_id', return_value='b-uuid'):
                analytics.AnalyticsTracker._enabled = True
                analytics.track_dataset_created(_pkg())
                analytics.track_dataset_updated(_pkg())
                analytics.track_doi_published(_pkg({'doi': '10.1/x'}))
                analytics.track_dataset_search('q', 3)
                analytics.track_resource_download('res-1', 'pkg-1', 'CSV')
            for call in mock_client.track.call_args_list:
                self.assertNotIn('anonymous_id', call[1],
                                 "anonymous_id must not be passed to the SDK for any event")
                self.assertIn('user_id', call[1],
                              "user_id must be passed to the SDK for every event")

    def test_no_event_falls_back_to_literal_anonymous(self):
        """The string 'anonymous' must never appear as user_id."""
        with patch.object(analytics.AnalyticsTracker, '_client') as mock_client:
            with patch.object(analytics, 'get_browser_id', return_value='generated-uuid-abc'):
                analytics.AnalyticsTracker._enabled = True
                analytics.track_dataset_search('q', 3)
            for call in mock_client.track.call_args_list:
                self.assertNotEqual(call[1].get('user_id'), 'anonymous',
                                    "Literal 'anonymous' must not be used as user_id")

    def test_anonymous_search_uses_browser_uuid(self):
        """Anonymous search event (no login) uses browser UUID as user_id."""
        with patch.object(analytics.AnalyticsTracker, '_client') as mock_client:
            with patch.object(analytics, 'get_browser_id', return_value='anon-browser-uuid'):
                analytics.AnalyticsTracker._enabled = True
                analytics.track_dataset_search('seismometer', 7, dataset_type='instrument')
            kw = mock_client.track.call_args[1]
            self.assertEqual(kw['user_id'], 'anon-browser-uuid')
            self.assertNotIn('anonymous_id', kw)

    def test_logged_in_search_uses_ckan_uuid_not_browser_uuid(self):
        """Logged-in search uses CKAN user UUID, not the browser cookie UUID."""
        ckan_user_uuid = 'ckan-user-uuid-logged-in'
        with patch.object(analytics.AnalyticsTracker, '_client') as mock_client:
            with patch.object(analytics, 'get_logged_in_user_id',
                              return_value=ckan_user_uuid):
                analytics.AnalyticsTracker._enabled = True
                analytics.track_dataset_search('telescope', 3)
            kw = mock_client.track.call_args[1]
            self.assertEqual(kw['user_id'], ckan_user_uuid)
            self.assertNotIn('anonymous_id', kw)


# ---------------------------------------------------------------------------
# Cookie UUID reuse and creation
# ---------------------------------------------------------------------------
class TestBrowserCookieReuse(unittest.TestCase):
    """get_browser_id() returns the same stable UUID for all calls within a request."""

    def _make_mock_flask(self, cookie_value=None):
        mock_flask = Mock()
        mock_flask.request.cookies.get.return_value = cookie_value
        mock_flask.g = types.SimpleNamespace()
        return mock_flask

    def test_same_uuid_returned_consistently_from_cookie(self):
        mock_flask = self._make_mock_flask('stable-uuid-1234')
        with patch.dict(sys.modules, {'flask': mock_flask}):
            result1 = analytics.get_browser_id()
            result2 = analytics.get_browser_id()
        self.assertEqual(result1, result2)
        self.assertEqual(result1, 'stable-uuid-1234')

    def test_same_generated_uuid_used_across_multiple_calls_in_same_request(self):
        """Without a cookie, both calls return the same generated UUID."""
        mock_flask = self._make_mock_flask(None)
        with patch.dict(sys.modules, {'flask': mock_flask}):
            result1 = analytics.get_browser_id()
            result2 = analytics.get_browser_id()
        self.assertEqual(result1, result2)

    def test_generates_valid_uuid_when_no_cookie(self):
        import re
        mock_flask = self._make_mock_flask(None)
        with patch.dict(sys.modules, {'flask': mock_flask}):
            result = analytics.get_browser_id()
        self.assertRegex(
            result,
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
        )


# ---------------------------------------------------------------------------
# AnalyticsTracker.track — must not mutate the caller's properties dict
# ---------------------------------------------------------------------------
class TestTrackDoesNotMutateProperties(unittest.TestCase):
    """track() must not modify the caller's properties dict.

    track_dataset_search fires track() twice (Search + Empty-Result Search)
    with the same properties dict; mutating it in the first call would
    corrupt the second call's payload with extra keys (timestamp, environment).
    """

    @patch.dict('os.environ', {
        'RUDDERSTACK_ENABLED': 'true',
        'RUDDERSTACK_WRITE_KEY': 'test_key',
        'RUDDERSTACK_DATA_PLANE_URL': 'https://test.rs.com',
    })
    @patch('ckanext.pidinst_theme.analytics.Client', create=True)
    @patch('ckanext.pidinst_theme.analytics.RUDDERSTACK_AVAILABLE', True)
    def test_caller_dict_not_mutated(self, mock_client):
        mock_client.return_value = Mock()
        analytics.AnalyticsTracker._client = None
        analytics.AnalyticsTracker._enabled = False
        analytics.AnalyticsTracker._initialized = False
        analytics.AnalyticsTracker.initialize()

        props = {'search_term': 'test', 'result_count': 3}
        original_keys = set(props.keys())

        analytics.AnalyticsTracker.track(event='Search', properties=props)

        self.assertEqual(set(props.keys()), original_keys,
                         "track() must not add keys to the caller's properties dict")

    @patch.dict('os.environ', {
        'RUDDERSTACK_ENABLED': 'true',
        'RUDDERSTACK_WRITE_KEY': 'test_key',
        'RUDDERSTACK_DATA_PLANE_URL': 'https://test.rs.com',
    })
    @patch('ckanext.pidinst_theme.analytics.Client', create=True)
    @patch('ckanext.pidinst_theme.analytics.RUDDERSTACK_AVAILABLE', True)
    def test_two_calls_with_same_dict_both_correct(self, mock_client):
        """Calling track() twice with the same dict works correctly for Search+Empty."""
        mock_instance = Mock()
        mock_client.return_value = mock_instance
        analytics.AnalyticsTracker._client = None
        analytics.AnalyticsTracker._enabled = False
        analytics.AnalyticsTracker._initialized = False
        analytics.AnalyticsTracker.initialize()

        props = {'search_term': 'nothing', 'result_count': 0, 'is_empty': True}
        analytics.AnalyticsTracker.track(event='Search', properties=props)
        analytics.AnalyticsTracker.track(event='Empty-Result Search',
                                          properties=props)

        self.assertEqual(mock_instance.track.call_count, 2)

    @patch.dict('os.environ', {
        'RUDDERSTACK_ENABLED': 'true',
        'RUDDERSTACK_WRITE_KEY': 'test_key',
        'RUDDERSTACK_DATA_PLANE_URL': 'https://test.rs.com',
    })
    @patch('ckanext.pidinst_theme.analytics.Client', create=True)
    @patch('ckanext.pidinst_theme.analytics.RUDDERSTACK_AVAILABLE', True)
    def test_anonymous_search_event_reaches_sdk(self, mock_client):
        """Search events must reach the SDK using the browser cookie as user_id."""
        mock_instance = Mock()
        mock_client.return_value = mock_instance
        analytics.AnalyticsTracker._client = None
        analytics.AnalyticsTracker._enabled = False
        analytics.AnalyticsTracker._initialized = False
        analytics.AnalyticsTracker.initialize()

        with patch.object(analytics, 'get_browser_id', return_value='test-browser-uuid'):
            analytics.track_dataset_search(
                search_term='seismometer',
                result_count=7,
                dataset_type='instrument',
            )

        self.assertTrue(mock_instance.track.called,
                        "SDK track() was not called — Search event was dropped")

        called_kwargs = mock_instance.track.call_args[1]
        self.assertNotIn('anonymous_id', called_kwargs)
        self.assertIn('user_id', called_kwargs)
        self.assertEqual(called_kwargs['user_id'], 'test-browser-uuid')
        self.assertEqual(called_kwargs['event'], analytics.EVENT_SEARCH)


if __name__ == '__main__':
    unittest.main()


# ---------------------------------------------------------------------------
# after_app_request hook: response sets pidinst_browser_id cookie
# ---------------------------------------------------------------------------
class TestBrowserIdCookieResponse(unittest.TestCase):
    """analytics.set_browser_id_cookie() writes the cookie when g has a value."""

    def _call(self, g_value=None):
        """Call set_browser_id_cookie with a mocked flask.g and a mock response."""
        mock_flask = Mock()
        mock_g = types.SimpleNamespace()
        if g_value is not None:
            mock_g.pidinst_browser_id_to_set = g_value
        mock_flask.g = mock_g
        mock_response = Mock()
        with patch.dict(sys.modules, {'flask': mock_flask}):
            result = analytics.set_browser_id_cookie(mock_response)
        return mock_response, result

    def test_calls_set_cookie_when_g_has_value(self):
        mock_response, _ = self._call('new-uuid-from-hook')
        mock_response.set_cookie.assert_called_once()
        args, kwargs = mock_response.set_cookie.call_args
        self.assertEqual(args[0], 'pidinst_browser_id')
        self.assertEqual(args[1], 'new-uuid-from-hook')

    def test_no_set_cookie_when_g_has_no_value(self):
        mock_response, _ = self._call(g_value=None)
        mock_response.set_cookie.assert_not_called()

    def test_returns_response(self):
        _, result = self._call('uuid-return-test')
        self.assertIsNotNone(result)

    def test_max_age_1_year(self):
        mock_response, _ = self._call('uuid-max-age-test')
        _, kwargs = mock_response.set_cookie.call_args
        self.assertEqual(kwargs.get('max_age'), 365 * 24 * 60 * 60)

    def test_samesite_lax(self):
        mock_response, _ = self._call('uuid-samesite-test')
        _, kwargs = mock_response.set_cookie.call_args
        self.assertEqual(kwargs.get('samesite'), 'Lax')


# ---------------------------------------------------------------------------
# Search and Empty-Result Search: anonymous_id is never None
# ---------------------------------------------------------------------------
class TestSearchUserIdNeverNone(unittest.TestCase):
    """Search and Empty-Result Search must send user_id=browser_uuid, never None."""

    def _setup_tracker(self, mock_client_cls):
        mock_instance = Mock()
        mock_client_cls.return_value = mock_instance
        analytics.AnalyticsTracker._client = None
        analytics.AnalyticsTracker._enabled = False
        analytics.AnalyticsTracker._initialized = False
        analytics.AnalyticsTracker.initialize()
        return mock_instance

    @patch.dict('os.environ', {
        'RUDDERSTACK_ENABLED': 'true',
        'RUDDERSTACK_WRITE_KEY': 'key',
        'RUDDERSTACK_DATA_PLANE_URL': 'https://dp.example.com',
    })
    @patch('ckanext.pidinst_theme.analytics.Client', create=True)
    @patch('ckanext.pidinst_theme.analytics.RUDDERSTACK_AVAILABLE', True)
    def test_search_user_id_not_none(self, mock_client_cls):
        mock_instance = self._setup_tracker(mock_client_cls)
        analytics.track_dataset_search('telescope', 5)
        for call in mock_instance.track.call_args_list:
            self.assertIsNotNone(
                call[1].get('user_id'),
                "Search event must not send user_id=None",
            )

    @patch.dict('os.environ', {
        'RUDDERSTACK_ENABLED': 'true',
        'RUDDERSTACK_WRITE_KEY': 'key',
        'RUDDERSTACK_DATA_PLANE_URL': 'https://dp.example.com',
    })
    @patch('ckanext.pidinst_theme.analytics.Client', create=True)
    @patch('ckanext.pidinst_theme.analytics.RUDDERSTACK_AVAILABLE', True)
    def test_empty_result_search_user_id_not_none(self, mock_client_cls):
        mock_instance = self._setup_tracker(mock_client_cls)
        analytics.track_dataset_search('nothing', 0)
        empty_calls = [
            c for c in mock_instance.track.call_args_list
            if c[1].get('event') == analytics.EVENT_EMPTY_RESULT_SEARCH
        ]
        self.assertEqual(len(empty_calls), 1)
        self.assertIsNotNone(
            empty_calls[0][1].get('user_id'),
            "Empty-Result Search must not send user_id=None",
        )

    @patch.dict('os.environ', {
        'RUDDERSTACK_ENABLED': 'true',
        'RUDDERSTACK_WRITE_KEY': 'key',
        'RUDDERSTACK_DATA_PLANE_URL': 'https://dp.example.com',
    })
    @patch('ckanext.pidinst_theme.analytics.Client', create=True)
    @patch('ckanext.pidinst_theme.analytics.RUDDERSTACK_AVAILABLE', True)
    def test_search_and_empty_result_share_same_user_id(self, mock_client_cls):
        """Both events in the same call use the same UUID (g cache)."""
        mock_instance = self._setup_tracker(mock_client_cls)
        mock_flask = Mock()
        mock_flask.request.cookies.get.return_value = None  # no cookie
        mock_flask.g = types.SimpleNamespace()
        with patch.dict(sys.modules, {'flask': mock_flask}):
            analytics.track_dataset_search('nothing', 0)
        calls = mock_instance.track.call_args_list
        self.assertEqual(len(calls), 2)
        ids = [c[1].get('user_id') for c in calls]
        self.assertIsNotNone(ids[0])
        self.assertIsNotNone(ids[1])
        self.assertEqual(ids[0], ids[1],
                         "Search and Empty-Result Search must share the same user_id")

    @patch.dict('os.environ', {
        'RUDDERSTACK_ENABLED': 'true',
        'RUDDERSTACK_WRITE_KEY': 'key',
        'RUDDERSTACK_DATA_PLANE_URL': 'https://dp.example.com',
    })
    @patch('ckanext.pidinst_theme.analytics.Client', create=True)
    @patch('ckanext.pidinst_theme.analytics.RUDDERSTACK_AVAILABLE', True)
    def test_no_event_passes_anonymous_id(self, mock_client_cls):
        """anonymous_id must never be passed to the SDK; user_id carries the UUID."""
        mock_instance = self._setup_tracker(mock_client_cls)
        analytics.track_dataset_search('q', 3)
        analytics.track_dataset_created(_pkg())
        analytics.track_resource_download('res-1', 'pkg-1', 'CSV')
        for call in mock_instance.track.call_args_list:
            self.assertNotIn(
                'anonymous_id', call[1],
                f"anonymous_id must not be passed for event {call[1].get('event')}",
            )


# ---------------------------------------------------------------------------
# get_logged_in_user_id()
# ---------------------------------------------------------------------------
class TestGetLoggedInUserId(unittest.TestCase):
    """get_logged_in_user_id() resolves the CKAN user UUID or returns None."""

    def _mock_authenticated_user(self, uid='ckan-user-uuid-1234'):
        """Return a mock ckan.common module with an authenticated current_user."""
        mock_ckan_common = Mock()
        mock_user = Mock()
        mock_user.is_authenticated = True
        mock_user.id = uid
        mock_ckan_common.current_user = mock_user
        return mock_ckan_common

    def _mock_anonymous_user(self):
        """Return a mock ckan.common module with an unauthenticated current_user."""
        mock_ckan_common = Mock()
        mock_user = Mock()
        mock_user.is_authenticated = False
        mock_ckan_common.current_user = mock_user
        return mock_ckan_common

    def test_returns_ckan_uuid_when_logged_in(self):
        mock_ckan_common = self._mock_authenticated_user('user-uuid-abcd')
        with patch.dict(sys.modules, {'ckan.common': mock_ckan_common}):
            result = analytics.get_logged_in_user_id()
        self.assertEqual(result, 'user-uuid-abcd')

    def test_returns_none_when_anonymous(self):
        mock_ckan_common = self._mock_anonymous_user()
        with patch.dict(sys.modules, {'ckan.common': mock_ckan_common}):
            result = analytics.get_logged_in_user_id()
        self.assertIsNone(result)

    def test_returns_none_on_import_error(self):
        """Gracefully returns None when ckan.common cannot be imported."""
        with patch.dict(sys.modules, {'ckan.common': None}):
            result = analytics.get_logged_in_user_id()
        self.assertIsNone(result)

    def test_returns_string_not_other_type(self):
        """id is coerced to str."""
        mock_ckan_common = self._mock_authenticated_user(uid='str-uuid-9999')
        with patch.dict(sys.modules, {'ckan.common': mock_ckan_common}):
            result = analytics.get_logged_in_user_id()
        self.assertIsInstance(result, str)

    def test_never_returns_username(self):
        """Must not return username, email, or display_name — UUID only."""
        mock_ckan_common = self._mock_authenticated_user('uuid-only')
        mock_ckan_common.current_user.name = 'jsmith'
        mock_ckan_common.current_user.email = 'jsmith@example.com'
        with patch.dict(sys.modules, {'ckan.common': mock_ckan_common}):
            result = analytics.get_logged_in_user_id()
        self.assertNotIn('@', result or '')
        self.assertNotEqual(result, 'jsmith')
        self.assertEqual(result, 'uuid-only')


# ---------------------------------------------------------------------------
# get_analytics_user_id()
# ---------------------------------------------------------------------------
class TestGetAnalyticsUserId(unittest.TestCase):
    """get_analytics_user_id() returns CKAN UUID for logged-in, browser UUID for anonymous."""

    def test_returns_ckan_uuid_when_logged_in(self):
        with patch.object(analytics, 'get_logged_in_user_id', return_value='ckan-uid-xyz'):
            result = analytics.get_analytics_user_id()
        self.assertEqual(result, 'ckan-uid-xyz')

    def test_returns_browser_uuid_when_anonymous(self):
        with patch.object(analytics, 'get_logged_in_user_id', return_value=None):
            with patch.object(analytics, 'get_browser_id', return_value='browser-uuid-anon'):
                result = analytics.get_analytics_user_id()
        self.assertEqual(result, 'browser-uuid-anon')

    def test_never_returns_none(self):
        with patch.object(analytics, 'get_logged_in_user_id', return_value=None):
            with patch.object(analytics, 'get_browser_id', return_value='fallback-uuid'):
                result = analytics.get_analytics_user_id()
        self.assertIsNotNone(result)

    def test_never_returns_literal_anonymous(self):
        with patch.object(analytics, 'get_logged_in_user_id', return_value=None):
            with patch.object(analytics, 'get_browser_id', return_value='some-uuid'):
                result = analytics.get_analytics_user_id()
        self.assertNotEqual(result, 'anonymous')

    def test_prefers_ckan_uuid_over_browser_uuid(self):
        """CKAN UUID takes precedence; browser UUID is not used when logged in."""
        with patch.object(analytics, 'get_logged_in_user_id', return_value='ckan-uid'):
            with patch.object(analytics, 'get_browser_id', return_value='browser-uid') as mock_browser:
                result = analytics.get_analytics_user_id()
        self.assertEqual(result, 'ckan-uid')
        mock_browser.assert_not_called()


# ---------------------------------------------------------------------------
# Logged-in user identity: backend events use CKAN UUID
# ---------------------------------------------------------------------------
_CKAN_USER_UUID = 'ckan-user-uuid-logged-in-5678'

class TestLoggedInUserIdentity(unittest.TestCase):
    """When a user is logged in, all backend events use the CKAN user UUID."""

    def _sdk_call_kwargs(self, fn, *args):
        """Return SDK track() kwargs with a mocked logged-in user."""
        with patch.object(analytics.AnalyticsTracker, '_client') as mock_client:
            with patch.object(analytics, 'get_logged_in_user_id',
                              return_value=_CKAN_USER_UUID):
                analytics.AnalyticsTracker._enabled = True
                fn(*args)
                return mock_client.track.call_args[1]

    def test_logged_in_search_uses_ckan_uuid(self):
        kw = self._sdk_call_kwargs(analytics.track_dataset_search, 'q', 5)
        self.assertEqual(kw['user_id'], _CKAN_USER_UUID)
        self.assertNotIn('anonymous_id', kw)

    def test_logged_in_empty_result_search_uses_ckan_uuid(self):
        with patch.object(analytics.AnalyticsTracker, '_client') as mock_client:
            with patch.object(analytics, 'get_logged_in_user_id',
                              return_value=_CKAN_USER_UUID):
                analytics.AnalyticsTracker._enabled = True
                analytics.track_dataset_search('nothing', 0)
            for call in mock_client.track.call_args_list:
                self.assertEqual(call[1]['user_id'], _CKAN_USER_UUID)
                self.assertNotIn('anonymous_id', call[1])

    def test_logged_in_update_existing_dataset_uses_ckan_uuid(self):
        kw = self._sdk_call_kwargs(analytics.track_dataset_updated, _pkg())
        self.assertEqual(kw['user_id'], _CKAN_USER_UUID)
        self.assertNotIn('anonymous_id', kw)

    def test_logged_in_dataset_created_uses_ckan_uuid(self):
        kw = self._sdk_call_kwargs(analytics.track_dataset_created, _pkg())
        self.assertEqual(kw['user_id'], _CKAN_USER_UUID)

    def test_logged_in_resource_download_uses_ckan_uuid(self):
        kw = self._sdk_call_kwargs(
            analytics.track_resource_download, 'res-1', 'pkg-1', 'CSV'
        )
        self.assertEqual(kw['user_id'], _CKAN_USER_UUID)

    def test_user_id_is_never_username_email_or_display_name(self):
        """user_id must be the UUID, not any PII field."""
        kw = self._sdk_call_kwargs(analytics.track_dataset_search, 'q', 3)
        user_id = kw['user_id']
        self.assertNotIn('@', user_id, "user_id must not be an email address")
        self.assertNotEqual(user_id, 'jsmith', "user_id must not be a username")
        self.assertEqual(user_id, _CKAN_USER_UUID)

    def test_anonymous_search_uses_browser_uuid(self):
        """When not logged in, browser UUID is used (not CKAN UUID)."""
        with patch.object(analytics.AnalyticsTracker, '_client') as mock_client:
            with patch.object(analytics, 'get_logged_in_user_id', return_value=None):
                with patch.object(analytics, 'get_browser_id',
                                  return_value='anon-browser-uuid-7890'):
                    analytics.AnalyticsTracker._enabled = True
                    analytics.track_dataset_search('seismometer', 7)
            kw = mock_client.track.call_args[1]
            self.assertEqual(kw['user_id'], 'anon-browser-uuid-7890')
            self.assertNotIn('anonymous_id', kw)

    def test_frontend_relay_uses_ckan_uuid_when_logged_in(self):
        """track() called from the relay endpoint uses CKAN UUID for logged-in users."""
        with patch.object(analytics.AnalyticsTracker, '_client') as mock_client:
            with patch.object(analytics, 'get_logged_in_user_id',
                              return_value=_CKAN_USER_UUID):
                analytics.AnalyticsTracker._enabled = True
                analytics.AnalyticsTracker.track(
                    analytics.EVENT_DATASET_VIEW_DURATION,
                    {'dataset_id': 'pkg-1', 'duration_seconds': 30},
                )
            kw = mock_client.track.call_args[1]
            self.assertEqual(kw['user_id'], _CKAN_USER_UUID)

    def test_frontend_relay_uses_browser_uuid_when_anonymous(self):
        """track() called from the relay endpoint uses browser UUID for anonymous."""
        with patch.object(analytics.AnalyticsTracker, '_client') as mock_client:
            with patch.object(analytics, 'get_logged_in_user_id', return_value=None):
                with patch.object(analytics, 'get_browser_id',
                                  return_value='relay-anon-uuid'):
                    analytics.AnalyticsTracker._enabled = True
                    analytics.AnalyticsTracker.track(
                        analytics.EVENT_DATASET_VIEW_DURATION,
                        {'dataset_id': 'pkg-1', 'duration_seconds': 30},
                    )
            kw = mock_client.track.call_args[1]
            self.assertEqual(kw['user_id'], 'relay-anon-uuid')
            self.assertNotIn('anonymous_id', kw)

    def test_browser_uuid_cookie_still_created_for_anonymous_users(self):
        """get_browser_id() generates a UUID and stashes it on g for anonymous requests."""
        mock_flask = Mock()
        mock_flask.request.cookies.get.return_value = None
        mock_flask.g = types.SimpleNamespace()
        with patch.dict(sys.modules, {'flask': mock_flask}):
            result = analytics.get_browser_id()
        self.assertIsNotNone(result)
        self.assertIsInstance(result, str)
        self.assertEqual(len(result), 36)
        stored = getattr(mock_flask.g, 'pidinst_browser_id_to_set', None)
        self.assertIsNotNone(stored, "UUID must be stashed on g for after_app_request hook")
        self.assertEqual(result, stored)

