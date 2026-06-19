"""Mapper: provider record -> FetchedMetadata + ResolvedFields.

Explicit field-to-field mapping logic for the DOI metadata resolution helper.
There are no heuristics, no external lookups, and no CKAN or network imports
here, so the Mapper stays independently unit-testable (Requirements 16.1, 16.2).

The mapping is deliberately tiny and explicit (Requirement 10):

* ``FetchedMetadata`` carries the full descriptive set for display only:
  ``title``, ``description``, ``creators``, ``publisher`` and
  ``publication_year``.
* ``ResolvedFields`` contains only safe field-to-field mappings. Simple fields
  can be auto-applied by the frontend, while composite fields are emitted as
  structured suggestions for manual review:

  * ``identifier_url`` from ``https://doi.org/{doi}``
  * ``title`` from the fetched title
  * ``notes`` from the fetched description
  * ``instrument_classification`` from DataCite ``types.resourceType`` when it
    exactly matches a schema choice

* Publication year, creators and publisher are displayed as fetched metadata
  only; the MVP schema has no clearly compatible free-text single-value field
  for them, so they are intentionally not mapped to any form field
  (Requirements 10.4, 10.5, 10.6).
* The Mapper never emits values that reference parties, owners, manufacturers,
  funders, instrument types, measured variables or taxonomy terms, so it
  creates none of them (Requirements 10.7, 10.8).
* For any descriptive field absent from the provider record, the corresponding
  fetched value is set to an empty value and exactly one descriptive warning is
  appended (Requirements 6.5, 14.1, 14.2).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from .types import FetchedMetadata, ProviderRecord, ResolvedFields

# Descriptive fields copied verbatim from the provider record into
# FetchedMetadata, in the stable order used for warning collection.
_FETCHED_FIELDS: Tuple[str, ...] = (
    'title',
    'description',
    'creators',
    'publisher',
    'publication_year',
)

# Descriptive warning emitted when the matching fetched field is absent from
# the provider record (Requirements 6.5, 14.2).
_MISSING_FIELD_WARNINGS = {
    'title': 'No title was provided by the source record.',
    'description': 'No description was provided by the source record.',
    'creators': 'No creators were provided by the source record.',
    'publisher': 'No publisher was provided by the source record.',
    'publication_year': 'No publication year was provided by the source record.',
}

_DATACITE_UNMAPPED_FIELDS: Tuple[Tuple[str, str], ...] = (
    ('creators', 'creators'),
    ('contributors', 'contributors'),
    ('subjects', 'subjects'),
    ('funding_references', 'fundingReferences'),
    ('related_identifiers', 'relatedIdentifiers'),
    ('rights', 'rightsList'),
    ('language', 'language'),
    ('version', 'version'),
    ('geo_locations', 'geoLocations'),
    ('resource_type', 'types'),
)

_CROSSREF_UNMAPPED_FIELDS: Tuple[Tuple[str, str], ...] = (
    ('authors', 'author'),
    ('contributors', 'contributor'),
    ('subjects', 'subject'),
    ('funders', 'funder'),
    ('related_identifiers', 'relation'),
    ('rights', 'license'),
    ('language', 'language'),
    ('version', 'version'),
    ('resource_type', 'type'),
    ('published', 'published'),
    ('issued', 'issued'),
)

_SAFE_INSTRUMENT_CLASSIFICATIONS = (
    'Geophysics',
    'Geochemistry',
    'Petrophysics',
    'Other',
)

_SUPPORTED_ALT_IDENTIFIER_TYPES = {
    'SerialNumber': 'SerialNumber',
    'InventoryNumber': 'InventoryNumber',
}

_MODEL_TECHNICAL_INFO_RE = re.compile(
    r'^\s*Model:\s*(?P<name>[^()]+?)\s*'
    r'(?:\(\s*URL:\s*(?P<url>https?://[^)\s]+)\s*\))?\s*$'
)

_INSTRUMENT_TYPE_TECHNICAL_INFO_RE = re.compile(
    r'^\s*Instrument\s+Type:\s*(?P<name>[^()]+?)\s*'
    r'(?:\(\s*URI:\s*(?P<uri>https?://[^)\s]+)\s*\))?\s*$'
)

_DATE_PART_RE = re.compile(r'^\d{4}(?:-\d{2}(?:-\d{2})?)?$')


def _stringify(value) -> str:
    """Coerce a scalar provider value into a stripped string."""
    if value is None:
        return ''
    return str(value).strip()


def _datacite_attributes(metadata) -> Dict[str, Any]:
    """Return DataCite ``data.attributes`` from a payload or attributes dict."""
    if not isinstance(metadata, dict):
        return {}
    data = metadata.get('data')
    if isinstance(data, dict):
        attributes = data.get('attributes')
        if isinstance(attributes, dict):
            return attributes
    attributes = metadata.get('attributes')
    if isinstance(attributes, dict):
        return attributes
    return metadata


def _datacite_identifier_value(entry, value_key: str) -> str:
    if not isinstance(entry, dict):
        return ''
    return _stringify(entry.get(value_key))


def _valid_pidinst_date_value(value: str) -> bool:
    """Return whether ``value`` matches schema-supported date formats."""
    if not value:
        return False
    if '/' in value:
        parts = value.split('/')
        if len(parts) != 2:
            return False
        start, end = parts
        return (
            (start == '' or _DATE_PART_RE.match(start) is not None)
            and (end == '' or _DATE_PART_RE.match(end) is not None)
            and (start != '' or end != '')
        )
    return _DATE_PART_RE.match(value) is not None


def extract_datacite_resource_type_classification(metadata) -> str:
    """Extract a safe PIDINST classification from DataCite resourceType."""
    attributes = _datacite_attributes(metadata)
    types = attributes.get('types')
    if not isinstance(types, dict):
        return ''
    resource_type = _stringify(types.get('resourceType'))
    if resource_type in _SAFE_INSTRUMENT_CLASSIFICATIONS:
        return resource_type
    return ''


def _alt_identifier_type_score(original_type: str) -> int:
    """Rank an alternate-identifier type so the most specific one wins on dedup.

    supported type (SerialNumber/InventoryNumber) > other non-empty type >
    missing/empty type.
    """
    if original_type in _SUPPORTED_ALT_IDENTIFIER_TYPES:
        return 3
    if original_type:
        return 2
    return 1


def extract_datacite_alternate_identifiers(metadata) -> List[Dict[str, str]]:
    """Map DataCite identifiers/alternateIdentifiers into PIDINST rows.

    Reads both ``attributes.identifiers`` and ``attributes.alternateIdentifiers``
    (Requirement 17.B.1). A value present in both arrays is NOT skipped; it
    produces exactly one output row (Requirement 17.B.2). When the same value
    carries different types across the arrays, the most specific type wins.

    Type mapping (Requirement 17.B.3-17.B.7):

    * ``SerialNumber`` -> ``SerialNumber``
    * ``InventoryNumber`` -> ``InventoryNumber``
    * any other non-empty type -> ``Other`` + ``alternate_identifier_name``
    * missing/empty type but a non-empty value -> ``Other`` (no name)
    * no usable identifier value -> skipped
    """
    attributes = _datacite_attributes(metadata)

    # Collect candidate (value, type) pairs in document order.
    # alternateIdentifiers come first so they keep precedence on first-seen
    # output ordering; identifiers follow for completeness.
    candidates: List[Dict[str, str]] = []

    alt_identifiers = attributes.get('alternateIdentifiers')
    if isinstance(alt_identifiers, list):
        for entry in alt_identifiers:
            value = _datacite_identifier_value(entry, 'alternateIdentifier')
            if value:
                candidates.append({
                    'value': value,
                    'type': _stringify(entry.get('alternateIdentifierType')),
                })

    identifiers = attributes.get('identifiers')
    if isinstance(identifiers, list):
        for entry in identifiers:
            id_type = _stringify(entry.get('identifierType'))
            if id_type.upper() == 'DOI':
                # The DOI itself is the primary identifier, not an alternate.
                continue
            value = _datacite_identifier_value(entry, 'identifier')
            if value:
                candidates.append({'value': value, 'type': id_type})

    # Choose the most specific type per value, preserving first-seen order.
    order: List[str] = []
    best_type: Dict[str, str] = {}
    for candidate in candidates:
        value = candidate['value']
        original_type = candidate['type']
        if value not in best_type:
            order.append(value)
            best_type[value] = original_type
        else:
            current = best_type[value]
            if _alt_identifier_type_score(original_type) > _alt_identifier_type_score(current):
                best_type[value] = original_type

    mapped: List[Dict[str, str]] = []
    for value in order:
        original_type = best_type[value]
        target_type = _SUPPORTED_ALT_IDENTIFIER_TYPES.get(original_type, 'Other')
        row: Dict[str, str] = {
            'alternate_identifier_type': target_type,
            'alternate_identifier': value,
        }
        # A non-empty original type that is not a supported one is preserved as
        # the supplementary name (Requirement 17.B.5). A missing type maps to
        # Other with no name (Requirement 17.B.6).
        if target_type == 'Other' and original_type:
            row['alternate_identifier_name'] = original_type
        mapped.append(row)

    return mapped


def extract_datacite_lifecycle_dates(
    metadata,
) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
    """Map only explicit PIDINST lifecycle dates from DataCite dates."""
    attributes = _datacite_attributes(metadata)
    dates = attributes.get('dates')
    mapped: List[Dict[str, str]] = []
    unmapped: List[Dict[str, Any]] = []
    if not isinstance(dates, list):
        return mapped, unmapped

    for entry in dates:
        if not isinstance(entry, dict):
            continue
        date_type = _stringify(entry.get('dateType'))
        date_information = _stringify(entry.get('dateInformation'))
        if date_type != 'Other' or not date_information:
            continue

        lowered = date_information.lower()
        target_type = ''
        if 'decommissioned' in lowered:
            target_type = 'DeCommissioned'
        elif 'commissioned' in lowered:
            target_type = 'Commissioned'
        if not target_type:
            continue

        value = _stringify(entry.get('date'))
        if _valid_pidinst_date_value(value):
            mapped.append({
                'date_value': value,
                'date_type': target_type,
            })
        else:
            unmapped.append(dict(entry))

    return mapped, unmapped


def extract_datacite_model_descriptions(
    metadata,
) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]]]:
    """Parse DataCite TechnicalInfo descriptions that match the model convention.

    Only entries where the description text starts with ``"Model:"`` are
    treated as model candidates.  Entries starting with ``"Instrument Type:"``
    are handled separately by :func:`extract_datacite_instrument_type_suggestions`
    and are NOT added to the unmapped list here so that no spurious model
    warnings are emitted for instrument type descriptions.
    """
    attributes = _datacite_attributes(metadata)
    descriptions = attributes.get('descriptions')
    mapped: List[Dict[str, str]] = []
    unmapped: List[Dict[str, Any]] = []
    if not isinstance(descriptions, list):
        return mapped, unmapped

    for entry in descriptions:
        if not isinstance(entry, dict):
            continue
        if _stringify(entry.get('descriptionType')) != 'TechnicalInfo':
            continue
        description = _stringify(entry.get('description'))
        # Only entries that start with "Model:" are model candidates.
        if not description.lstrip().startswith('Model:'):
            # Instrument Type entries are handled elsewhere; other TechnicalInfo
            # values that are neither Model nor Instrument Type are unmapped.
            if not description.lstrip().startswith('Instrument Type:'):
                unmapped.append(dict(entry))
            continue
        match = _MODEL_TECHNICAL_INFO_RE.match(description)
        if not match:
            unmapped.append(dict(entry))
            continue
        row = {'model_name': match.group('name').strip()}
        url = _stringify(match.group('url'))
        if url:
            row['model_identifier'] = url
            row['model_identifier_type'] = 'URL'
        mapped.append(row)

    return mapped, unmapped


def extract_datacite_instrument_type_suggestions(
    metadata,
) -> List[Dict[str, str]]:
    """Parse DataCite TechnicalInfo descriptions that describe instrument types.

    Only entries where the description starts with ``"Instrument Type:"`` are
    parsed.  These are emitted as suggestion-only metadata and MUST NOT be
    auto-applied to any form field or used to create taxonomy terms.

    Returns a list of dicts with:
      - ``instrument_type_name``
      - ``instrument_type_identifier`` (when a URI is present)
      - ``instrument_type_identifier_type`` = ``"URL"`` (when a URI is present)
    """
    attributes = _datacite_attributes(metadata)
    descriptions = attributes.get('descriptions')
    suggestions: List[Dict[str, str]] = []
    if not isinstance(descriptions, list):
        return suggestions

    for entry in descriptions:
        if not isinstance(entry, dict):
            continue
        if _stringify(entry.get('descriptionType')) != 'TechnicalInfo':
            continue
        description = _stringify(entry.get('description'))
        if not description.lstrip().startswith('Instrument Type:'):
            continue
        match = _INSTRUMENT_TYPE_TECHNICAL_INFO_RE.match(description)
        if not match:
            continue
        row: Dict[str, str] = {'instrument_type_name': match.group('name').strip()}
        uri = _stringify(match.group('uri'))
        if uri:
            row['instrument_type_identifier'] = uri
            row['instrument_type_identifier_type'] = 'URL'
        suggestions.append(row)

    return suggestions


def extract_datacite_related_identifiers(metadata) -> List[Dict[str, str]]:
    """Preserve safe related identifier fields from DataCite metadata."""
    attributes = _datacite_attributes(metadata)
    related_identifiers = attributes.get('relatedIdentifiers')
    mapped: List[Dict[str, str]] = []
    if not isinstance(related_identifiers, list):
        return mapped

    for entry in related_identifiers:
        if not isinstance(entry, dict):
            continue
        related_identifier = _stringify(entry.get('relatedIdentifier'))
        related_identifier_type = _stringify(entry.get('relatedIdentifierType'))
        relation_type = _stringify(entry.get('relationType'))
        if not (related_identifier and related_identifier_type and relation_type):
            continue
        mapped.append({
            'related_identifier': related_identifier,
            'related_identifier_type': related_identifier_type,
            'relation_type': relation_type,
        })
    return mapped


def _ror_from_name_identifiers(name_identifiers) -> str:
    """Return the first ROR identifier from a DataCite nameIdentifiers list."""
    if not isinstance(name_identifiers, list):
        return ''
    for entry in name_identifiers:
        if not isinstance(entry, dict):
            continue
        scheme = _stringify(entry.get('nameIdentifierScheme'))
        value = _stringify(entry.get('nameIdentifier'))
        scheme_uri = _stringify(entry.get('schemeUri'))
        if not value:
            continue
        if scheme.upper() == 'ROR' or 'ror.org' in value.lower() or 'ror.org' in scheme_uri.lower():
            return value
    return ''


def _affiliation_text(value) -> Any:
    """Normalise a DataCite affiliation field (list of dicts/strings or str)."""
    if isinstance(value, list):
        names = []
        for item in value:
            if isinstance(item, dict):
                name = _stringify(item.get('name'))
                if name:
                    names.append(name)
            else:
                text = _stringify(item)
                if text:
                    names.append(text)
        return names
    text = _stringify(value)
    return text


def extract_datacite_manufacturer_suggestions(metadata) -> List[Dict[str, Any]]:
    """Suggest manufacturers from organisational DataCite creators.

    Suggestion-only: never written to the ``manufacturer`` form field, never
    creates or links a party (Requirements 10.7, 10.8).
    """
    attributes = _datacite_attributes(metadata)
    creators = attributes.get('creators')
    suggestions: List[Dict[str, Any]] = []
    if not isinstance(creators, list):
        return suggestions

    for entry in creators:
        if not isinstance(entry, dict):
            continue
        name_type = _stringify(entry.get('nameType'))
        # Only organisational creators are plausible manufacturers.
        if name_type and name_type.lower() != 'organizational':
            continue
        if not name_type:
            # No nameType given; only treat as org suggestion when it lacks a
            # personal givenName/familyName split.
            if entry.get('givenName') or entry.get('familyName'):
                continue
        name = _stringify(entry.get('name'))
        if not name:
            continue
        suggestion: Dict[str, Any] = {
            'name': name,
            'nameType': name_type,
            'nameIdentifiers': entry.get('nameIdentifiers') or [],
            'source': 'creator',
            'suggested_role': 'manufacturer',
        }
        ror = _ror_from_name_identifiers(entry.get('nameIdentifiers'))
        if ror:
            suggestion['ror'] = ror
        affiliation = _affiliation_text(entry.get('affiliation'))
        if affiliation:
            suggestion['affiliation'] = affiliation
        suggestions.append(suggestion)

    return suggestions


def extract_datacite_owner_suggestions(metadata) -> List[Dict[str, Any]]:
    """Suggest owners from DataCite HostingInstitution contributors.

    Suggestion-only: never written to the ``owner`` form field, never creates
    or links a party (Requirements 10.7, 10.8).
    """
    attributes = _datacite_attributes(metadata)
    contributors = attributes.get('contributors')
    suggestions: List[Dict[str, Any]] = []
    if not isinstance(contributors, list):
        return suggestions

    for entry in contributors:
        if not isinstance(entry, dict):
            continue
        contributor_type = _stringify(entry.get('contributorType'))
        if contributor_type != 'HostingInstitution':
            continue
        name = _stringify(entry.get('name'))
        if not name:
            continue
        suggestion: Dict[str, Any] = {
            'name': name,
            'contributorType': contributor_type,
            'nameIdentifiers': entry.get('nameIdentifiers') or [],
            'source': 'contributor',
            'suggested_role': 'owner',
        }
        ror = _ror_from_name_identifiers(entry.get('nameIdentifiers'))
        if ror:
            suggestion['ror'] = ror
        affiliation = _affiliation_text(entry.get('affiliation'))
        if affiliation:
            suggestion['affiliation'] = affiliation
        suggestions.append(suggestion)

    return suggestions


def extract_datacite_funder_suggestions(metadata) -> List[Dict[str, Any]]:
    """Suggest funders from DataCite fundingReferences.

    Suggestion-only: never written to ``funder_party_id``, never creates or
    links a party (Requirements 10.7, 10.8).
    """
    attributes = _datacite_attributes(metadata)
    funding_references = attributes.get('fundingReferences')
    suggestions: List[Dict[str, Any]] = []
    if not isinstance(funding_references, list):
        return suggestions

    for entry in funding_references:
        if not isinstance(entry, dict):
            continue
        funder_name = _stringify(entry.get('funderName'))
        if not funder_name:
            continue
        suggestion: Dict[str, Any] = {
            'funderName': funder_name,
            'funderIdentifier': _stringify(entry.get('funderIdentifier')),
            'funderIdentifierType': _stringify(entry.get('funderIdentifierType')),
            'schemeUri': _stringify(entry.get('schemeUri')),
            'source': 'fundingReference',
            'suggested_role': 'funder',
        }
        award_number = _stringify(entry.get('awardNumber'))
        if award_number:
            suggestion['awardNumber'] = award_number
        award_title = _stringify(entry.get('awardTitle'))
        if award_title:
            suggestion['awardTitle'] = award_title
        award_uri = _stringify(entry.get('awardUri'))
        if award_uri:
            suggestion['awardUri'] = award_uri
        suggestions.append(suggestion)

    return suggestions


def extract_datacite_party_identifier_suggestions(metadata) -> List[Dict[str, Any]]:
    """Collect ORCID/ROR/name identifiers from creators and contributors.

    Suggestion-only: never links these to local parties (Requirement 10.8).
    """
    attributes = _datacite_attributes(metadata)
    suggestions: List[Dict[str, Any]] = []
    for role_key in ('creators', 'contributors'):
        people = attributes.get(role_key)
        if not isinstance(people, list):
            continue
        for person in people:
            if not isinstance(person, dict):
                continue
            name = _stringify(person.get('name'))
            name_identifiers = person.get('nameIdentifiers')
            if not isinstance(name_identifiers, list) or not name_identifiers:
                continue
            for nid in name_identifiers:
                if not isinstance(nid, dict):
                    continue
                value = _stringify(nid.get('nameIdentifier'))
                if not value:
                    continue
                suggestions.append({
                    'name': name,
                    'name_identifier': value,
                    'name_identifier_scheme': _stringify(
                        nid.get('nameIdentifierScheme')
                    ),
                    'scheme_uri': _stringify(nid.get('schemeUri')),
                    'source': role_key[:-1],  # 'creator' | 'contributor'
                })
    return suggestions


def extract_datacite_taxonomy_suggestions(metadata) -> List[Dict[str, Any]]:
    """Suggest taxonomy terms from DataCite subjects.

    Suggestion-only: never creates or links taxonomy terms (Requirement 10.8).
    """
    attributes = _datacite_attributes(metadata)
    subjects = attributes.get('subjects')
    suggestions: List[Dict[str, Any]] = []
    if not isinstance(subjects, list):
        return suggestions

    for entry in subjects:
        if not isinstance(entry, dict):
            continue
        subject = _stringify(entry.get('subject'))
        if not subject:
            continue
        suggestion: Dict[str, Any] = {'subject': subject, 'source': 'subject'}
        scheme = _stringify(entry.get('subjectScheme'))
        if scheme:
            suggestion['subject_scheme'] = scheme
        value_uri = _stringify(entry.get('valueURI'))
        if value_uri:
            suggestion['value_uri'] = value_uri
        suggestions.append(suggestion)

    return suggestions


def extract_datacite_geo_location_suggestions(metadata) -> List[Dict[str, Any]]:
    """Preserve DataCite geoLocations as suggestion-only metadata.

    Suggestion-only: not auto-applied to any spatial form field.
    """
    attributes = _datacite_attributes(metadata)
    geo_locations = attributes.get('geoLocations')
    if not isinstance(geo_locations, list):
        return []
    return [dict(entry) for entry in geo_locations if isinstance(entry, dict)]


def extract_datacite_publication_metadata_suggestions(metadata) -> Dict[str, Any]:
    """Collect publisher / year / lifecycle dates as suggestion-only metadata.

    Suggestion-only: the schema's publication fields are hidden/system-managed,
    so these are surfaced for manual reference and never auto-applied.
    """
    attributes = _datacite_attributes(metadata)
    suggestion: Dict[str, Any] = {'source': 'datacite'}

    publisher = _stringify(attributes.get('publisher'))
    if publisher:
        suggestion['publisher'] = publisher
    publication_year = _stringify(attributes.get('publicationYear'))
    if publication_year:
        suggestion['publication_year'] = publication_year

    dates = attributes.get('dates')
    if isinstance(dates, list):
        for entry in dates:
            if not isinstance(entry, dict):
                continue
            date_type = _stringify(entry.get('dateType'))
            value = _stringify(entry.get('date'))
            if not value:
                continue
            if date_type in ('Created', 'Issued', 'Updated', 'Registered',
                             'Available', 'Accepted', 'Submitted'):
                suggestion['{0}_date'.format(date_type.lower())] = value

    # Only return a meaningful suggestion when it carries more than the source.
    if len(suggestion) == 1:
        return {}
    return suggestion


def extract_datacite_related_identifier_suggestions(metadata) -> List[Dict[str, Any]]:
    """Preserve related identifiers that lack a safely inferable resource type.

    The PIDINST ``related_identifier_obj`` composite requires
    ``related_resource_type`` and ``relation_type`` (see instrument_schema.yaml).
    DataCite ``relatedIdentifiers`` do not carry a PIDINST resource type, so the
    full composite row cannot be safely auto-applied. These are surfaced as
    suggestion-only entries for manual review instead.
    """
    attributes = _datacite_attributes(metadata)
    related_identifiers = attributes.get('relatedIdentifiers')
    suggestions: List[Dict[str, Any]] = []
    if not isinstance(related_identifiers, list):
        return suggestions

    for entry in related_identifiers:
        if not isinstance(entry, dict):
            continue
        related_identifier = _stringify(entry.get('relatedIdentifier'))
        related_identifier_type = _stringify(entry.get('relatedIdentifierType'))
        relation_type = _stringify(entry.get('relationType'))
        if not (related_identifier and related_identifier_type and relation_type):
            continue
        suggestions.append({
            'related_identifier': related_identifier,
            'related_identifier_type': related_identifier_type,
            'relation_type': relation_type,
        })
    return suggestions


class Mapper:
    """Maps a provider record to fetched metadata and resolved form fields.

    The single public entry point :meth:`map` takes a provider-neutral
    :class:`ProviderRecord` and the canonical identifier URL constructed by the
    normaliser, and returns the display metadata, the restricted set of resolved
    form-field values, and the per-field warnings.
    """

    def map(
        self,
        record: ProviderRecord,
        identifier_url: str,
    ) -> Tuple[FetchedMetadata, ResolvedFields, List[str]]:
        """Map ``record`` into fetched metadata, resolved fields and warnings.

        Args:
            record: The provider-neutral metadata returned by a Provider_Client.
            identifier_url: The canonical ``https://doi.org/{bare_doi}`` URL for
                the resolved DOI, used to populate ``resolved_fields``.

        Returns:
            A ``(fetched, resolved_fields, warnings)`` tuple where ``fetched``
            is the full display metadata, ``resolved_fields`` is restricted to
            ``identifier_url``/``title``/``notes``, and ``warnings`` holds one
            descriptive entry per absent descriptive field.
        """
        # Display metadata: copy the descriptive fields verbatim, coercing any
        # absent value to its empty form (Requirements 14.1, 6.5).
        fetched = FetchedMetadata(
            title=record.title or '',
            description=record.description or '',
            creators=list(record.creators) if record.creators else [],
            publisher=record.publisher or '',
            publication_year=record.publication_year or '',
            provider_metadata=dict(record.provider_metadata or {}),
        )
        fetched.available_unmapped = self._available_unmapped(record, fetched)

        metadata = self._provider_metadata_root(record)

        # Resolved form fields: safe direct keys only. Composite values are
        # structured for review/display and are not automatically written by
        # the frontend unless a field is explicitly allowlisted there.
        resolved_fields = ResolvedFields(
            identifier_url=identifier_url or '',
            title=fetched.title,
            notes=fetched.description,
        )
        if record.source == 'datacite':
            resolved_fields.instrument_classification = (
                extract_datacite_resource_type_classification(metadata)
            )
            resolved_fields.alternate_identifier_obj = (
                extract_datacite_alternate_identifiers(metadata)
            )
            resolved_fields.date, unmapped_lifecycle_dates = (
                extract_datacite_lifecycle_dates(metadata)
            )
            resolved_fields.model, unmapped_model_descriptions = (
                extract_datacite_model_descriptions(metadata)
            )
            resolved_fields.related_identifier_obj = (
                extract_datacite_related_identifier_suggestions(metadata)
            )
            resolved_fields.instrument_type_suggestions = (
                extract_datacite_instrument_type_suggestions(metadata)
            )
            resolved_fields.manufacturer_suggestions = (
                extract_datacite_manufacturer_suggestions(metadata)
            )
            resolved_fields.owner_suggestions = (
                extract_datacite_owner_suggestions(metadata)
            )
            resolved_fields.funder_suggestions = (
                extract_datacite_funder_suggestions(metadata)
            )
            resolved_fields.party_identifier_suggestions = (
                extract_datacite_party_identifier_suggestions(metadata)
            )
            resolved_fields.taxonomy_suggestions = (
                extract_datacite_taxonomy_suggestions(metadata)
            )
            resolved_fields.geo_location_suggestions = (
                extract_datacite_geo_location_suggestions(metadata)
            )
            resolved_fields.publication_metadata_suggestions = (
                extract_datacite_publication_metadata_suggestions(metadata)
            )
        else:
            unmapped_lifecycle_dates = []
            unmapped_model_descriptions = []

        # One descriptive warning per absent descriptive field, in stable order
        # (Requirements 6.5, 14.2).
        warnings: List[str] = []
        for field_name in _FETCHED_FIELDS:
            if self._is_absent(getattr(fetched, field_name)):
                warnings.append(_MISSING_FIELD_WARNINGS[field_name])

        if record.source == 'datacite':
            self._add_datacite_mapping_notes(
                metadata,
                fetched.available_unmapped,
                warnings,
                resolved_fields,
                unmapped_lifecycle_dates,
                unmapped_model_descriptions,
            )

        return fetched, resolved_fields, warnings

    @staticmethod
    def _is_absent(value) -> bool:
        """Return ``True`` when a fetched value should count as absent.

        Empty/whitespace-only strings and empty lists are treated as absent so
        that a missing provider field both yields an empty fetched value and a
        warning.
        """
        if isinstance(value, str):
            return not value.strip()
        if isinstance(value, list):
            return len(value) == 0
        if isinstance(value, dict):
            return len(value) == 0
        return value is None

    def _available_unmapped(
        self,
        record: ProviderRecord,
        fetched: FetchedMetadata,
    ) -> Dict[str, Any]:
        """Curate safe provider fields that are intentionally not auto-mapped."""
        metadata = self._provider_metadata_root(record)
        available: Dict[str, Any] = {}

        # These are shown for manual use because the PIDINST schema fields they
        # might resemble are hidden, controlled, or party/taxonomy-backed.
        if fetched.creators:
            available[
                'creators' if record.source == 'datacite' else 'authors'
            ] = list(fetched.creators)
        if fetched.publisher:
            available['publisher'] = fetched.publisher
        if fetched.publication_year:
            available['publication_year'] = fetched.publication_year

        field_map = (
            _DATACITE_UNMAPPED_FIELDS
            if record.source == 'datacite'
            else _CROSSREF_UNMAPPED_FIELDS
        )
        for display_key, provider_key in field_map:
            value = metadata.get(provider_key)
            if not self._is_absent(value):
                available[display_key] = value

        affiliations = self._extract_affiliations(record.source, metadata)
        if affiliations:
            available['affiliations'] = affiliations

        name_identifiers = self._extract_name_identifiers(record.source, metadata)
        if name_identifiers:
            available['name_identifiers'] = name_identifiers

        return available

    def _provider_metadata_root(self, record: ProviderRecord) -> Dict[str, Any]:
        """Return the provider-specific metadata object used for field curation."""
        metadata = record.provider_metadata or {}
        if record.source == 'datacite':
            return _datacite_attributes(metadata)
        if record.source == 'crossref':
            message = metadata.get('message')
            if isinstance(message, dict):
                return message
        return metadata

    def _add_datacite_mapping_notes(
        self,
        metadata: Dict[str, Any],
        available: Dict[str, Any],
        warnings: List[str],
        resolved_fields: ResolvedFields,
        unmapped_lifecycle_dates: List[Dict[str, Any]],
        unmapped_model_descriptions: List[Dict[str, Any]],
    ) -> None:
        """Record conservative DataCite mapping warnings and manual suggestions."""
        types = metadata.get('types')
        if isinstance(types, dict):
            resource_type = _stringify(types.get('resourceType'))
            if resolved_fields.instrument_classification:
                available.pop('resource_type', None)
            elif resource_type:
                available['resource_type'] = types
                warnings.append(
                    'DataCite resourceType "{0}" does not match a supported '
                    'instrument classification.'.format(resource_type)
                )

        if unmapped_lifecycle_dates:
            available['lifecycle_dates'] = list(unmapped_lifecycle_dates)
            warnings.append(
                'One or more DataCite lifecycle dates were not in a supported '
                'PIDINST date format.'
            )

        if unmapped_model_descriptions:
            available['technical_info_descriptions'] = list(
                unmapped_model_descriptions
            )
            warnings.append(
                'One or more DataCite TechnicalInfo descriptions did not match '
                'the supported model format.'
            )

        if resolved_fields.alternate_identifier_obj:
            available.pop('alternate_identifiers', None)
        if resolved_fields.related_identifier_obj:
            available['related_identifiers'] = metadata.get('relatedIdentifiers')

    def _extract_affiliations(self, source: str, metadata) -> List[Any]:
        """Collect creator/author/contributor affiliations for manual display."""
        people_keys = (
            ('creators', 'contributors')
            if source == 'datacite'
            else ('author', 'contributor')
        )
        affiliations: List[Any] = []
        for key in people_keys:
            people = metadata.get(key)
            if not isinstance(people, list):
                continue
            for person in people:
                if not isinstance(person, dict):
                    continue
                value = person.get('affiliation')
                if self._is_absent(value):
                    continue
                if isinstance(value, list):
                    affiliations.extend(value)
                else:
                    affiliations.append(value)
        return affiliations

    def _extract_name_identifiers(self, source: str, metadata) -> List[Any]:
        """Collect ORCID/ROR/name identifiers without linking to local parties."""
        identifiers: List[Any] = []
        if source == 'datacite':
            for key in ('creators', 'contributors'):
                people = metadata.get(key)
                if not isinstance(people, list):
                    continue
                for person in people:
                    if not isinstance(person, dict):
                        continue
                    value = person.get('nameIdentifiers')
                    if not self._is_absent(value):
                        identifiers.append(value)
            return identifiers

        for key in ('author', 'contributor'):
            people = metadata.get(key)
            if not isinstance(people, list):
                continue
            for person in people:
                if not isinstance(person, dict):
                    continue
                for identifier_key in ('ORCID', 'authenticated-orcid'):
                    value = person.get(identifier_key)
                    if not self._is_absent(value):
                        identifiers.append({identifier_key: value})
        return identifiers
