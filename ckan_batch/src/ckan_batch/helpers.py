from typing import Any, Dict
import json
from ckan_batch.constants import COMPOSITE_FIELDS, TAG_FIELDS, PIDINST_SITE_DEFAULTS

def apply_site_defaults(payload: Dict[str, Any], *, override: bool = False) -> Dict[str, Any]:
    """
    Adds site-managed hidden fields required by scheming validation.
    If override=False, only fills missing/blank values.
    """
    p = dict(payload)
    for k, v in PIDINST_SITE_DEFAULTS.items():
        if override or (k not in p) or (p[k] is None) or (isinstance(p[k], str) and p[k].strip() == ""):
            p[k] = v
    return p

def _to_ckan_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    p = dict(payload)

    # Ensure resources exists (fine)
    if "resources" not in p:
        p["resources"] = []

    # ---- IMPORTANT: tag-string fields must never be Missing/None ----
    # If your scheming uses tag_string_convert on these, CKAN crashes when value is Missing.
    for k in TAG_FIELDS:
        if k not in p or p[k] is None:
            p[k] = ""  # safest value for tag_string_convert
        else:
            # ensure it's a plain string (not list/dict)
            p[k] = str(p[k]).strip()

    # Convert composite lists/dicts to JSON strings (scheming repeating composite pattern)
    for k in COMPOSITE_FIELDS:
        if k in p and isinstance(p[k], (list, dict)):
            p[k] = json.dumps(p[k], ensure_ascii=False)

    # Spatial is often stored as a string too
    if "spatial" in p and isinstance(p["spatial"], dict):
        p["spatial"] = json.dumps(p["spatial"], ensure_ascii=False)


    if "location_data" in p and isinstance(p["location_data"], dict):
        p["location_data"] = json.dumps(p["location_data"], ensure_ascii=False)

    # Optional: drop None scalars to avoid weird Missing conversions elsewhere
    for k in list(p.keys()):
        if p[k] is None:
            del p[k]

    p = apply_site_defaults(p)

    return p
