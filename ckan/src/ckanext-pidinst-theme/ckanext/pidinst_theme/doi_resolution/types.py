"""Framework-free data models for the DOI metadata resolution pipeline.

These are plain dataclasses with no CKAN or network imports. ``ResolveResult``
carries a ``to_dict()`` that produces the uniform result envelope serialised by
the ``pidinst_resolve_doi_metadata`` action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class NormalizedInput:
    """The outcome of normalising a raw identifier input string.

    ``input_type`` is one of ``'doi'``, ``'url'``, or ``''`` (invalid).
    For backward compatibility, ``is_doi`` is kept as a convenience property
    equivalent to ``input_type == 'doi'``.
    """

    is_valid: bool
    input_type: str = ''      # 'doi' | 'url' | ''
    bare_doi: str = ''        # '' when not a DOI
    identifier_url: str = ''  # the canonical URL for DOIs, or the original URL

    @property
    def is_doi(self) -> bool:
        """Backward-compatible property: True when this is a DOI input."""
        return self.input_type == 'doi'


@dataclass
class ProviderRecord:
    """Provider-neutral descriptive metadata returned by a Provider_Client."""

    source: str                  # 'datacite' | 'crossref'
    title: str = ''
    description: str = ''
    creators: List[str] = field(default_factory=list)
    publisher: str = ''
    publication_year: str = ''
    provider_metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FetchedMetadata:
    """Normalised descriptive metadata for display in the Resolve_Dialog."""

    title: str = ''
    description: str = ''
    creators: List[str] = field(default_factory=list)
    publisher: str = ''
    publication_year: str = ''
    provider_metadata: Dict[str, Any] = field(default_factory=dict)
    available_unmapped: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Always emit the full set of fetched keys (Requirement 6.3)."""
        return {
            'title': self.title,
            'description': self.description,
            'creators': list(self.creators),
            'publisher': self.publisher,
            'publication_year': self.publication_year,
            'provider_metadata': dict(self.provider_metadata),
            'available_unmapped': dict(self.available_unmapped),
        }


@dataclass
class ResolvedFields:
    """The subset of metadata mapped to PIDINST form-field keys.

    ``notes`` is bound to the scheming ``description`` form field client-side.
    Composite fields are emitted as structured values for display/review, but
    the frontend only auto-applies fields it can find and safely write.

    ``instrument_type_suggestions`` is suggestion-only metadata; it is never
    auto-applied to any form field and must not create taxonomy terms.
    """

    # Tier 1 — auto-applicable simple fields
    identifier_url: str = ''
    title: str = ''
    notes: str = ''
    instrument_classification: str = ''
    # Tier 2 — resolved composite fields for manual review
    alternate_identifier_obj: List[Dict[str, Any]] = field(default_factory=list)
    date: List[Dict[str, Any]] = field(default_factory=list)
    model: List[Dict[str, Any]] = field(default_factory=list)
    related_identifier_obj: List[Dict[str, Any]] = field(default_factory=list)
    # Tier 3 — suggestion-only fields (never auto-applied, never create/link
    # parties or taxonomy terms)
    instrument_type_suggestions: List[Dict[str, Any]] = field(default_factory=list)
    owner_suggestions: List[Dict[str, Any]] = field(default_factory=list)
    manufacturer_suggestions: List[Dict[str, Any]] = field(default_factory=list)
    funder_suggestions: List[Dict[str, Any]] = field(default_factory=list)
    party_identifier_suggestions: List[Dict[str, Any]] = field(default_factory=list)
    taxonomy_suggestions: List[Dict[str, Any]] = field(default_factory=list)
    geo_location_suggestions: List[Dict[str, Any]] = field(default_factory=list)
    publication_metadata_suggestions: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Always emit all supported resolved keys (Requirement 6.4)."""
        return {
            # Tier 1
            'identifier_url': self.identifier_url,
            'title': self.title,
            'notes': self.notes,
            'instrument_classification': self.instrument_classification,
            # Tier 2
            'alternate_identifier_obj': list(self.alternate_identifier_obj),
            'date': list(self.date),
            'model': list(self.model),
            'related_identifier_obj': list(self.related_identifier_obj),
            # Tier 3
            'instrument_type_suggestions': list(self.instrument_type_suggestions),
            'owner_suggestions': list(self.owner_suggestions),
            'manufacturer_suggestions': list(self.manufacturer_suggestions),
            'funder_suggestions': list(self.funder_suggestions),
            'party_identifier_suggestions': list(self.party_identifier_suggestions),
            'taxonomy_suggestions': list(self.taxonomy_suggestions),
            'geo_location_suggestions': list(self.geo_location_suggestions),
            'publication_metadata_suggestions': dict(
                self.publication_metadata_suggestions
            ),
        }


@dataclass
class ResolveResult:
    """The uniform result envelope returned by the Resolver/action.

    ``status`` is one of ``ok``, ``invalid_input``, ``not_found``,
    ``fetch_error``, ``unsupported_format``.
    """

    status: str
    source: str = ''
    doi: str = ''
    identifier_url: str = ''
    fetched: Optional[FetchedMetadata] = None
    resolved_fields: Optional[ResolvedFields] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialise to the uniform envelope consumed by the dialog.

        On ``status == 'ok'`` the envelope carries ``source``, ``doi``,
        ``identifier_url``, ``fetched``, ``resolved_fields`` and ``warnings``.
        For any non-``ok`` status only ``status`` and ``warnings`` are emitted.
        """
        if self.status != 'ok':
            return {
                'status': self.status,
                'warnings': list(self.warnings),
            }

        fetched = self.fetched if self.fetched is not None else FetchedMetadata()
        resolved = (
            self.resolved_fields
            if self.resolved_fields is not None
            else ResolvedFields()
        )
        return {
            'status': self.status,
            'source': self.source,
            'doi': self.doi,
            'identifier_url': self.identifier_url,
            'fetched': fetched.to_dict(),
            'provider_metadata': dict(fetched.provider_metadata),
            'available_unmapped': dict(fetched.available_unmapped),
            'resolved_fields': resolved.to_dict(),
            'warnings': list(self.warnings),
        }
