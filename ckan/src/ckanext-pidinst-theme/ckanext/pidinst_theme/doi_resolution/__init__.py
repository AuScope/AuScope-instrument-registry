"""Network-isolated, read-only DOI metadata resolution package.

This package contains the framework-free resolution pipeline (input
normalisation, provider clients, mapper, resolver) and its data models. It
must remain free of any CKAN or network imports at module import time so that
each component is independently unit-testable without a CKAN request context.
"""
