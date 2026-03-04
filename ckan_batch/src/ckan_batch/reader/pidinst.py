from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable, Dict, List, Optional, Tuple
import math

import openpyxl



COMPOSITE_FIELDS = {
    "manufacturer",
    "owner",
    "model",
    "date",
    "alternate_identifier_obj",
    "funder",
    "related_identifier_obj",
}

TAG_FIELDS = {
    "measured_variable",
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

# -----------------------------
# Types
# -----------------------------
RelatedInstrumentResolver = Callable[[str, str, str], Optional[str]]
# resolver(manufacturer, model, serial) -> DOI (string) or None


@dataclass
class MappingResult:
    datasets: List[Dict[str, Any]]
    errors: List[str]


# -----------------------------
# Helpers
# -----------------------------
def _is_blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and math.isnan(v):
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    return False


def _clean(v: Any) -> Optional[str]:
    if _is_blank(v):
        return None
    if isinstance(v, str):
        return v.strip()
    return str(v).strip()


def _coerce_bool(v: Any) -> Optional[bool]:
    if _is_blank(v):
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in {"true", "t", "yes", "y", "1"}:
        return True
    if s in {"false", "f", "no", "n", "0"}:
        return False
    return None


def _append_unique(lst: List[Dict[str, Any]], item: Dict[str, Any], identity_keys: Tuple[str, ...]) -> None:
    """Append item if its identity tuple is not already present."""
    if not item:
        return
    ident = tuple((_clean(item.get(k)) or "") for k in identity_keys)
    if all(x == "" for x in ident):
        return
    for ex in lst:
        ex_ident = tuple((_clean(ex.get(k)) or "") for k in identity_keys)
        if ident == ex_ident:
            return
    lst.append(item)


def _split_comma_separated(value: Optional[str]) -> Optional[str]:
    """Split comma-separated values, trim each part, and rejoin with ', '."""
    if not value:
        return None
    parts = [part.strip() for part in value.split(",") if part.strip()]
    return ", ".join(parts) if parts else None


def _split_csv_cell(v: Optional[str]) -> List[str]:
    """
    Split a comma-separated cell value into a list of tokens.
    E.g. "a, b ,c" -> ["a","b","c"]
    """
    if not v:
        return []
    parts = [p.strip() for p in str(v).split(",")]
    return [p for p in parts if p]

def _accumulate_csv_field(acc: Dict[str, List[str]], field: str, cell_value: Optional[str]) -> None:
    """
    Accumulate comma-separated values into acc[field] with de-duplication.
    """
    tokens = _split_csv_cell(cell_value)
    if not tokens:
        return
    acc.setdefault(field, [])
    for t in tokens:
        if t not in acc[field]:
            acc[field].append(t)


# -----------------------------
# Template header parsing
# -----------------------------
def _forward_fill(values: List[Optional[str]]) -> List[Optional[str]]:
    out: List[Optional[str]] = []
    cur: Optional[str] = None
    for v in values:
        if v is not None and str(v).strip() != "":
            cur = str(v).strip()
        out.append(cur)
    return out


def _norm_header(label: Optional[str]) -> Optional[str]:
    if label is None:
        return None
    s = str(label).strip()
    return s if s else None


def _strip_required_star(col: str) -> Tuple[str, bool]:
    col = col.strip()
    if col.endswith("*"):
        return col[:-1].strip(), True
    return col, False


def _build_column_keys(ws, header_row: int = 5, section_row: int = 3, group_row: int = 4) -> Tuple[List[str], Dict[str, bool]]:
    """
    Builds stable, unique column keys using the multi-row header layout:
      - section_row (row 3): e.g. OWNER, DATES, etc (sparse)
      - group_row   (row 4): e.g. MODEL, MANUFACTURER, etc (sparse)
      - header_row  (row 5): actual column names (often repeated: Name*, Identifier, etc)

    Output keys look like:
      - "TITLE.Name"
      - "MANUFACTURER.IdentifierType"
      - "OWNER.Contact"
      - "RELATED_RESOURCES_REGISTERED.Serial Number"
      - "GEOLOCATION.Latitude"
    """
    max_col = ws.max_column

    sec = [_norm_header(ws.cell(section_row, c).value) for c in range(1, max_col + 1)]
    grp = [_norm_header(ws.cell(group_row, c).value) for c in range(1, max_col + 1)]
    hdr_raw = [_norm_header(ws.cell(header_row, c).value) for c in range(1, max_col + 1)]

    sec_ff = _forward_fill(sec)
    grp_ff = _forward_fill(grp)

    required_map: Dict[str, bool] = {}
    keys: List[str] = []

    for i in range(max_col):
        h = hdr_raw[i]
        if h is None:
            keys.append(f"__EMPTY__{i+1}")
            required_map[keys[-1]] = False
            continue

        h2, is_req = _strip_required_star(h)

        # Special-case: section rows in your template contain long text for the related blocks
        # Normalize those into short identifiers.
        sec_label = sec_ff[i] or ""
        if sec_label.startswith("RELATED RESOURCES (EXTERNAL)"):
            sec_label = "RELATED_RESOURCES_EXTERNAL"
        elif sec_label.startswith("RELATED RESOURCES (REGISTERED"):
            sec_label = "RELATED_RESOURCES_REGISTERED"

        grp_label = grp_ff[i] or ""
        # Prefer group label (row 4) when present, else section label (row 3)
        prefix = grp_label or sec_label or "FIELD"

        key = f"{prefix}.{h2}"
        keys.append(key)
        required_map[key] = is_req

    return keys, required_map

#-----------------------------
# Final adjustments
#-----------------------------

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
# -----------------------------
# Main mapper
# -----------------------------
def read_pidinst_template(
    excel_path: str,
    sheet_name: str = "Instruments",
    record_col_key: str = "FIELD.Record",  # derived key for Record* column
    related_instrument_resolver: Optional[RelatedInstrumentResolver] = None,
) -> MappingResult:
    """
    Reads your adjusted PIDINST template and maps it to CKAN dataset payload dicts.

    Grouping:
      - uses Record* as the grouping key (first row in a group holds base required fields)

    Repeating composites supported:
      - manufacturer, owner, model, date, alternate_identifier_obj, funder,
        related_identifier_obj (external + registered/internal)
    """
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    ws = wb[sheet_name]

    col_keys, required_cols = _build_column_keys(ws, header_row=5, section_row=3, group_row=4)

    # Data starts at row 7 in this template:
    # row 1 title, row 2 note, row 3/4 groups, row 5 headers, row 6 help, row 7+ data
    first_data_row = 7

    # Build row dicts with our stable keys
    rows: List[Dict[str, Any]] = []
    for r in range(first_data_row, ws.max_row + 1):
        row: Dict[str, Any] = {"__rownum__": r}
        empty = True
        for c, key in enumerate(col_keys, start=1):
            val = ws.cell(r, c).value
            if not _is_blank(val):
                empty = False
            row[key] = val
        if not empty:
            rows.append(row)

    errors: List[str] = []
    datasets: List[Dict[str, Any]] = []

    # Group by Record*
    groups: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        rec = _clean(row.get(record_col_key))
        if not rec:
            # If Record* is empty, ignore row (or flag – your choice)
            errors.append(f"[Row {row['__rownum__']}] Missing Record* (used for grouping).")
            continue
        groups.setdefault(rec, []).append(row)

    for record, grp in groups.items():
        ds: Dict[str, Any] = {}

        # Repeating composites (lists)
        for k in COMPOSITE_FIELDS:
            ds[k] = []

        # Tag-like accumulators
        tag_acc: Dict[str, List[str]] = {}


        # Validate required columns on the first row (your “first row has required info” rule)
        first = grp[0]
        missing_required_headers: List[str] = []
        for k, is_req in required_cols.items():
            if not is_req:
                continue
            if k == record_col_key:
                continue
            if _is_blank(first.get(k)):
                missing_required_headers.append(k)

        if missing_required_headers:
            errors.append(
                f"[Record {record}] Missing required values on first row: {', '.join(missing_required_headers)}"
            )
            continue

        for row in grp:
            # Base scalar fields
            org_own = _clean(row.get("SITE_ORG.Organisation"))
            if org_own and _is_blank(ds.get("owner_org")):
                ds["owner_org"] = org_own  # CKAN owner organization (not required in your template, but if present on any row in the group, use it)
            title = _clean(row.get("TITLE.Name"))
            if title and _is_blank(ds.get("title")):
                ds["title"] = title  # CKAN title

            desc = _clean(row.get("OTHER.Description"))
            if desc and _is_blank(ds.get("description")):
                ds["description"] = desc

            locality = _clean(row.get("GEOLOCATION.Locality"))
            if locality and _is_blank(ds.get("locality")):
                ds["locality"] = locality

            epsg = _clean(row.get("GEOLOCATION.EPSG"))
            if epsg and _is_blank(ds.get("epsg_code")):
                ds["epsg_code"] = epsg

            # Geo: template provides lon/lat columns; schema uses location_choice + location_data (+ spatial)
            lon_raw = _clean(row.get("GEOLOCATION.Longitude"))
            lat_raw = _clean(row.get("GEOLOCATION.Latitude"))

            lon = lat = None
            try:
                if lon_raw is not None and lat_raw is not None:
                    lon = float(lon_raw)
                    lat = float(lat_raw)
            except Exception:
                lon = lat = None

            # If this row has NO coords, do NOT clobber an existing point set by a previous row
            if lon is None or lat is None:
                if _is_blank(ds.get("location_choice")):
                    ds["location_choice"] = "noLocation"
                    ds["location_data"] = None
                    ds.pop("spatial", None)
            else:
                fc = {
                    "type": "FeatureCollection",
                    "features": [
                        {
                            "type": "Feature",
                            "properties": {},
                            "geometry": {"type": "Point", "coordinates": [lon, lat]},
                        }
                    ],
                }

                # Always prefer point if we have coords on any row
                ds["location_choice"] = "point"

                # Set location_data/spatial once (first coords wins)
                if _is_blank(ds.get("location_data")):
                    ds["location_data"] = fc
                if _is_blank(ds.get("spatial")):
                    ds["spatial"] = {"type": "Point", "coordinates": [lon, lat]}

            # Comma-separated fields (read from first row with value)
            if _is_blank(ds.get("measured_variable")):
                measured_var = _split_comma_separated(_clean(row.get("OTHER.MeasuredVariable")))
                if measured_var:
                    ds["measured_variable"] = measured_var

            if _is_blank(ds.get("user_keywords")):
                user_kw = _split_comma_separated(_clean(row.get("OTHER.UserKeywords")))
                if user_kw:
                    ds["user_keywords"] = user_kw

            if _is_blank(ds.get("gcmd_keywords_code")):
                gcmd_kw = _split_comma_separated(_clean(row.get("OTHER.GCMDKeywordsCode")))
                if gcmd_kw:
                    ds["gcmd_keywords_code"] = gcmd_kw

            # Tags
            # Tags / multi-token fields (now comma-separated in ONE cell)
            _accumulate_csv_field(tag_acc, "measured_variable", _clean(row.get("OTHER.MeasuredVariable")))
            _accumulate_csv_field(tag_acc, "user_keywords", _clean(row.get("OTHER.UserKeywords")))
            _accumulate_csv_field(tag_acc, "gcmd_keywords_code", _clean(row.get("OTHER.GCMDKeywordsCode")))

            credit = _clean(row.get("OTHER.Credit"))
            if credit and _is_blank(ds.get("credit")):
                ds["credit"] = credit

            # Manufacturer composite (repeating)
            m = {
                "manufacturer_name": _clean(row.get("MANUFACTURER.Name")),
                "manufacturer_identifier": _clean(row.get("MANUFACTURER.Identifier")),
                "manufacturer_identifier_type": _clean(row.get("MANUFACTURER.IdentifierType")),
            }
            # only append if manufacturer_name present
            if m.get("manufacturer_name"):
                _append_unique(ds["manufacturer"], m, identity_keys=("manufacturer_name", "manufacturer_identifier"))

            # Owner composite (repeating)
            o = {
                "owner_name": _clean(row.get("OWNER.Name")),
                "owner_contact": _clean(row.get("OWNER.Contact")),
                "owner_relationship_type": _clean(row.get("OWNER.Relationship")),
                "owner_identifier": _clean(row.get("OWNER.Identifier")),
                "owner_identifier_type": _clean(row.get("OWNER.IdentifierType")),
            }
            if o.get("owner_name") or o.get("owner_contact") or o.get("owner_relationship_type"):
                _append_unique(
                    ds["owner"], o, identity_keys=("owner_name", "owner_contact", "owner_relationship_type")
                )

            # Model composite (repeating)
            model = {
                "model_name": _clean(row.get("MODEL.Name")),
                "model_identifier": _clean(row.get("MODEL.Identifier")),
                "model_identifier_type": _clean(row.get("MODEL.IdentifierType")),
            }
            if model.get("model_name"):
                _append_unique(ds["model"], model, identity_keys=("model_name", "model_identifier"))

            # Date composite (repeating)
            dval = _clean(row.get("DATES.Date"))
            dtype = _clean(row.get("DATES.dateType"))
            if dval or dtype:
                date_obj = {"date_value": dval, "date_type": dtype}
                _append_unique(ds["date"], date_obj, identity_keys=("date_value", "date_type"))

            # Alternate Identifier composite (repeating)
            alt = {
                "alternate_identifier": _clean(row.get("ALTERNATE IDENTIFIER.Id")),
                "alternate_identifier_type": _clean(row.get("ALTERNATE IDENTIFIER.IdType")),
                "alternate_identifier_name": _clean(row.get("ALTERNATE IDENTIFIER.Name")),
            }
            if alt.get("alternate_identifier") or alt.get("alternate_identifier_type"):
                _append_unique(
                    ds["alternate_identifier_obj"],
                    alt,
                    identity_keys=("alternate_identifier_type", "alternate_identifier"),
                )

            # Funder composite (repeating)
            f = {
                "funder_name": _clean(row.get("FUNDER.Name")),
                "funder_identifier": _clean(row.get("FUNDER.Id")),
                "funder_identifier_type": _clean(row.get("FUNDER.IdType")),
                "award_number": _clean(row.get("FUNDER.AwardNumber")),
                "award_uri": _clean(row.get("FUNDER.AwardURI")),
                "award_title": _clean(row.get("FUNDER.AwardTitle")),
            }
            if f.get("funder_name") or f.get("funder_identifier") or f.get("award_number"):
                _append_unique(ds["funder"], f, identity_keys=("funder_name", "funder_identifier", "award_number"))

            # -----------------------------
            # Related resources: EXTERNAL
            # -----------------------------
            ext_id = _clean(row.get("RELATED_RESOURCES_EXTERNAL.Id"))
            ext_id_type = _clean(row.get("RELATED RESOURCES (EXTERNAL)\n[Use this block for resources that are not registered in our Instrument Registry (e.g. related documents or datasets)].IdType"))  # safe fallback if key changes
            # Prefer stable key if present:
            if _is_blank(ext_id_type):
                ext_id_type = _clean(row.get("RELATED_RESOURCES_EXTERNAL.IdType"))
            ext_res_type = _clean(row.get("RELATED_RESOURCES_EXTERNAL.ResourceType"))
            ext_rel = _clean(row.get("RELATED_RESOURCES_EXTERNAL.Relationship"))
            ext_name = _clean(row.get("RELATED_RESOURCES_EXTERNAL.IdentifierName"))

            if ext_id or ext_res_type or ext_rel:
                rel_obj = {
                    "related_identifier": ext_id,
                    "related_identifier_type": ext_id_type,
                    "related_resource_type": ext_res_type,
                    "relation_type": ext_rel,
                    "related_identifier_name": ext_name,
                }
                # keep only if something meaningful
                if rel_obj.get("related_identifier"):
                    _append_unique(
                        ds["related_identifier_obj"],
                        rel_obj,
                        identity_keys=("related_identifier_type", "related_identifier", "relation_type"),
                    )

            # -----------------------------
            # Related resources: REGISTERED
            # -----------------------------
            reg_id = _clean(row.get("RELATED_RESOURCES_REGISTERED.Id"))
            reg_manf = _clean(row.get("RELATED_RESOURCES_REGISTERED.Manufacturer"))
            reg_model = _clean(row.get("RELATED_RESOURCES_REGISTERED.Model"))
            reg_sn = _clean(row.get("RELATED_RESOURCES_REGISTERED.Serial Number"))
            reg_rel = _clean(row.get("RELATED_RESOURCES_REGISTERED.Relationship"))

            if reg_id or reg_manf or reg_model or reg_sn or reg_rel:
                doi: Optional[str] = None
                if reg_id:
                    doi = reg_id  # user provided DOI directly
                else:
                    # Must resolve via callback if not provided
                    if related_instrument_resolver and reg_manf and reg_model and reg_sn:
                        doi = related_instrument_resolver(reg_manf, reg_model, reg_sn)
                    else:
                        errors.append(
                            f"[Record {record} | Row {row['__rownum__']}] "
                            f"Registered related resource missing DOI, and/or missing (Manufacturer+Model+Serial) or resolver not provided."
                        )

                if doi:
                    rel_res_type = "Version" if (reg_rel == "IsNewVersionOf") else "Instrument"
                    reg_obj = {
                        "related_identifier": doi,
                        "related_identifier_type": "DOI",
                        "related_resource_type": rel_res_type,
                        "relation_type": reg_rel,
                    }
                    _append_unique(
                        ds["related_identifier_obj"],
                        reg_obj,
                        identity_keys=("related_identifier_type", "related_identifier", "relation_type"),
                    )
                else:
                    errors.append(
                        f"[Record {record} | Row {row['__rownum__']}] "
                        f"Could not resolve registered related instrument. Provided: DOI={reg_id}, "
                        f"Manufacturer={reg_manf}, Model={reg_model}, Serial={reg_sn}"
                    )

        # Apply accumulated tag fields (join)
        for k, vals in tag_acc.items():
            if vals:
                ds[k] = ", ".join(vals)

        # Clean empty repeating composites
        for k in COMPOSITE_FIELDS:
            if not ds.get(k):
                ds.pop(k, None)

        # Minimal required checks (based on your template)
        if _is_blank(ds.get("title")):
            errors.append(f"[Record {record}] Missing TITLE.Name (maps to CKAN title).")
            continue
        if not ds.get("manufacturer"):
            errors.append(f"[Record {record}] Missing at least one manufacturer (MANUFACTURER.Name).")
            continue
        if not ds.get("owner"):
            errors.append(f"[Record {record}] Missing at least one owner (OWNER.Name/Contact/Relationship).")
            continue
        if not ds.get("model"):
            errors.append(f"[Record {record}] Missing at least one model (MODEL.Name).")
            continue

        datasets.append(ds)

    return MappingResult(datasets=datasets, errors=errors)

