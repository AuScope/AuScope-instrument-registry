import pytest

from ckanext.pidinst_theme.doi_resolution.input_normalizer import (
    normalize_input,
    uses_datacite_test_api,
)


@pytest.mark.parametrize(
    'value,expected',
    [
        ('10.1234/example', '10.1234/example'),
        (' doi:10.1234/Example ', '10.1234/Example'),
        ('https://doi.org/10.1234/example', '10.1234/example'),
        ('http://dx.doi.org/10.1234/example', '10.1234/example'),
        ('https://handle.test.datacite.org/10.83627/yst9hxwy',
         '10.83627/yst9hxwy'),
        ('https://doi.test.datacite.org/dois/10.83627/yst9hxwy',
         '10.83627/yst9hxwy'),
        ('https://api.test.datacite.org/dois/10.83627/yst9hxwy',
         '10.83627/yst9hxwy'),
    ],
)
def test_valid_doi_forms_are_normalized(value, expected):
    result = normalize_input(value)

    assert result.is_doi is True
    assert result.is_valid is True
    assert result.input_type == 'doi'
    assert result.bare_doi == expected
    assert result.identifier_url == 'https://doi.org/{}'.format(expected)


@pytest.mark.parametrize(
    'value',
    ['', '   ', 'not a doi', 'ftp://example.com/file'],
)
def test_non_doi_non_url_input_is_rejected(value):
    result = normalize_input(value)

    assert result.is_valid is False
    assert result.is_doi is False
    assert result.input_type == ''
    assert result.bare_doi == ''
    assert result.identifier_url == ''


@pytest.mark.parametrize(
    'value',
    [
        'https://example.com/instruments/123',
        'http://my-metadata-server.org/api/records/456',
        'https://some-repo.org/datasets/10.1234/not-a-doi-url',
    ],
)
def test_valid_http_url_is_accepted_as_url_type(value):
    result = normalize_input(value)

    assert result.is_valid is True
    assert result.is_doi is False
    assert result.input_type == 'url'
    assert result.bare_doi == ''
    assert result.identifier_url == value


@pytest.mark.parametrize(
    'value,expected',
    [
        ('https://handle.test.datacite.org/10.83627/yst9hxwy', True),
        ('https://doi.test.datacite.org/dois/10.83627/yst9hxwy', True),
        ('https://api.test.datacite.org/dois/10.83627/yst9hxwy', True),
        ('https://doi.org/10.83627/yst9hxwy', False),
        ('10.83627/yst9hxwy', False),
    ],
)
def test_datacite_test_resolver_urls_use_test_api(value, expected):
    assert uses_datacite_test_api(value) is expected


def test_doi_url_from_allowed_host_is_doi_not_url():
    """A DOI URL from doi.org should be classified as DOI, not URL."""
    result = normalize_input('https://doi.org/10.1234/example')
    assert result.input_type == 'doi'
    assert result.bare_doi == '10.1234/example'


def test_url_from_doi_host_without_valid_doi_path_is_url():
    """A URL from doi.org without a valid DOI path is classified as URL."""
    result = normalize_input('https://doi.org/')
    # An empty path on a DOI host without a valid DOI -> URL type
    assert result.is_valid is True
    assert result.input_type == 'url'


def test_backward_compat_is_doi_property():
    """The is_doi property is backwards compatible."""
    doi_result = normalize_input('10.1234/example')
    assert doi_result.is_doi is True

    url_result = normalize_input('https://example.com/test')
    assert url_result.is_doi is False

    invalid_result = normalize_input('not valid')
    assert invalid_result.is_doi is False
