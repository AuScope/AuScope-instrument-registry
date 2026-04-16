from __future__ import annotations
from typing import Any, Dict, Optional
import json
import re
from datetime import datetime, date
import shutil
from importlib import resources
from pathlib import Path

from ckan_batch.constants import COMPOSITE_FIELDS, TAG_FIELDS, PIDINST_SITE_DEFAULTS

_ALLOWED_PIDINST_DATE_RE = re.compile(
    r"^(?P<year>\d{4})"
    r"(?:-(?P<month>0[1-9]|1[0-2])"
    r"(?:-(?P<day>0[1-9]|[12]\d|3[01]))?)?$"
)

_ALLOWED_PIDINST_COVERAGE_RE = re.compile(
    r"^(?:(?P<start>\d{4}(?:-(?:0[1-9]|1[0-2])(?:-(?:0[1-9]|[12]\d|3[01]))?)?)?)"
    r"/"
    r"(?:(?P<end>\d{4}(?:-(?:0[1-9]|1[0-2])(?:-(?:0[1-9]|[12]\d|3[01]))?)?)?)$"
)


def _validate_pidinst_single_date_text(text: str) -> str:
    """
    Validate plain-text PIDINST single date:
      YYYY
      YYYY-MM
      YYYY-MM-DD
    """
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


def _validate_pidinst_coverage_date_text(text: str) -> str:
    """
    Validate plain-text PIDINST Coverage date:
      YYYY
      YYYY-MM
      YYYY-MM-DD
      YYYY/YYYY
      YYYY-MM/YYYY-MM
      YYYY-MM-DD/YYYY-MM-DD
      YYYY/
      YYYY-MM/
      YYYY-MM-DD/
      /YYYY
      /YYYY-MM
      /YYYY-MM-DD
    """
    if "/" not in text:
        return _validate_pidinst_single_date_text(text)

    m = _ALLOWED_PIDINST_COVERAGE_RE.fullmatch(text)
    if not m:
        raise ValueError(
            f"Invalid Coverage date value '{text}'. "
            "Please enter Coverage dates in Excel as plain text using one of: "
            "YYYY, YYYY-MM, YYYY-MM-DD, start/end, start/, or /end."
        )

    start = m.group("start")
    end = m.group("end")

    if not start and not end:
        raise ValueError(
            "Invalid Coverage date value '/'. "
            "Coverage start and end cannot both be empty."
        )

    if start:
        _validate_pidinst_single_date_text(start)
    if end:
        _validate_pidinst_single_date_text(end)

    return text


def validate_pidinst_date_text(
    value: Any,
    date_type: Optional[str] = None,
) -> Optional[str]:
    """
    Accept only plain-text PIDINST date formats.

    Standard dates:
      YYYY
      YYYY-MM
      YYYY-MM-DD

    Coverage dates:
      YYYY
      YYYY-MM
      YYYY-MM-DD
      YYYY/YYYY
      YYYY-MM/YYYY-MM
      YYYY-MM-DD/YYYY-MM-DD
      YYYY/
      YYYY-MM/
      YYYY-MM-DD/
      /YYYY
      /YYYY-MM
      /YYYY-MM-DD

    Returns normalized string if valid, None if blank.
    Raises ValueError otherwise.
    """
    if value is None:
        return None

    # Reject Excel-converted date/datetime values explicitly
    if isinstance(value, (datetime, date)):
        if isinstance(date_type, str) and date_type.strip().lower() == "coverage":
            raise ValueError(
                f"Coverage date value '{value}' is not plain text. "
                "Please enter Coverage dates in Excel as plain text using one of: "
                "YYYY, YYYY-MM, YYYY-MM-DD, start/end, start/, or /end."
            )
        raise ValueError(
            f"Date value '{value}' is not plain text. "
            "Please enter dates in Excel as plain text using one of: "
            "YYYY, YYYY-MM, YYYY-MM-DD."
        )

    if isinstance(value, str):
        text = value.strip()
    else:
        text = str(value).strip()

    if not text:
        return None

    if isinstance(date_type, str) and date_type.strip().lower() == "coverage":
        return _validate_pidinst_coverage_date_text(text)

    return _validate_pidinst_single_date_text(text)

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


def get_excel_template(target_path: Optional[str] = None) -> Path:
    """
    Copy the bundled PIDINST.xlsx template to a target location.

    If target_path is not provided, the template is copied into the current
    working directory with the name 'PIDINST.xlsx'.

    Args:
        target_path: Optional destination path. This can be either:
            - a full file path, e.g. "my_template.xlsx"
            - a directory path, e.g. "output/templates"

    Returns:
        Path to the copied template file.
    """
    template_resource = resources.files("ckan_batch.reader.templates").joinpath("PIDINST.xlsx")

    if target_path is None:
        destination = Path.cwd() / "PIDINST.xlsx"
    else:
        destination = Path(target_path)
        # If user passed a directory path, put the file inside it
        if destination.exists() and destination.is_dir():
            destination = destination / "PIDINST.xlsx"
        elif destination.suffix == "":
            destination.mkdir(parents=True, exist_ok=True)
            destination = destination / "PIDINST.xlsx"

    destination.parent.mkdir(parents=True, exist_ok=True)

    with resources.as_file(template_resource) as src_path:
        shutil.copy2(src_path, destination)

    return destination


def get_notebooks(target_dir: Optional[str] = None) -> list[Path]:
    """
    Copy all bundled notebook templates (*.ipynb) from
    ckan_batch.reader.templates to a target directory.

    If target_dir is not provided, notebooks are copied into the current
    working directory.

    Args:
        target_dir: Optional destination directory.

    Returns:
        List of paths to the copied notebooks.
    """
    templates_dir = resources.files("ckan_batch.reader.templates")

    destination_dir = Path(target_dir) if target_dir else Path.cwd()
    destination_dir.mkdir(parents=True, exist_ok=True)

    copied_files: list[Path] = []

    for item in templates_dir.iterdir():
        if item.is_file() and item.name.endswith(".ipynb"):
            destination = destination_dir / item.name
            with resources.as_file(item) as src_path:
                shutil.copy2(src_path, destination)
            copied_files.append(destination)

    return copied_files
