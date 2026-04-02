from typing import Any, Dict, Optional
import json
import re
from datetime import datetime, date
from ckan_batch.constants import COMPOSITE_FIELDS, TAG_FIELDS, PIDINST_SITE_DEFAULTS

_ALLOWED_PIDINST_DATE_RE = re.compile(
    r"^(?P<year>\d{4})"
    r"(?:-(?P<month>0[1-9]|1[0-2])"
    r"(?:-(?P<day>0[1-9]|[12]\d|3[01]))?)?$"
)


def validate_pidinst_date_text(value: Any) -> Optional[str]:
    """
    Accept only plain-text PIDINST date formats:
      YYYY
      YYYY-MM
      YYYY-MM-DD

    Returns normalized string if valid, None if blank.
    Raises ValueError otherwise.
    """
    if value is None:
        return None

    if isinstance(value, str):
        text = value.strip()
    else:
        text = str(value).strip()

    if not text:
        return None

    # Reject Excel-converted date/datetime values explicitly
    if isinstance(value, (datetime, date)):
        raise ValueError(
            f"Date value '{value}' is not plain text. "
            "Please enter dates in Excel as plain text using one of: "
            "YYYY, YYYY-MM, YYYY-MM-DD."
        )

    m = _ALLOWED_PIDINST_DATE_RE.fullmatch(text)
    if not m:
        raise ValueError(
            f"Invalid date value '{text}'. "
            "Please enter dates in Excel as plain text using one of: "
            "YYYY, YYYY-MM, YYYY-MM-DD."
        )

    year = int(m.group("year"))
    month = m.group("month")
    day = m.group("day")

    if month and day:
        try:
            datetime(year, int(month), int(day))
        except ValueError:
            raise ValueError(
                f"Invalid calendar date '{text}'. "
                "Please enter a real date in one of: YYYY, YYYY-MM, YYYY-MM-DD."
            )

    return text

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
