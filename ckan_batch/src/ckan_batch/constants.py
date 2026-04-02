

COMPOSITE_FIELDS = {
    "manufacturer",
    "owner",
    "model",
    "date",
    "alternate_identifier_obj",
    "funder",
    "related_identifier_obj",
    "instrument_type",
    "measured_variable",
}

TAG_FIELDS = {
    "user_keywords",
    "gcmd_keywords_code",
}

PIDINST_SITE_DEFAULTS = {
    # Publisher (DataCite mapping)
    "publisher": "AuScope",
    "publisher_identifier": "https://ror.org/04s1m4564",
    "publisher_identifier_type": "ROR",

    # Primary contact (site-managed)
    "primary_contact_name": "AuScope Instrument Registry",
    "primary_contact_email": "help@data.auscope.org.au",

    # Optional extras you might also want to force:
    # "domain": "instrument-test.data.auscope.org.au",
    # "doi_publisher": "AuScope",
}


GCMD_BASE_URL = "https://vocabs.ardc.edu.au/repository/api/lda"
GCMD_VOCAB_ENDPOINTS = {
    "instruments": "ardc-curated/gcmd-instruments/22-8-2026-02-13",
    "measured_variables": "ardc-curated/gcmd-measurementname/21-5-2025-06-06",
    "platforms": "ardc-curated/gcmd-platforms/21-5-2025-06-17",
}
CUSTOM_TAXONOMY_NAMES = {
    "instruments": "instruments",
    "platforms": "platforms",
    "measured_variables": "measured-variables",
}
