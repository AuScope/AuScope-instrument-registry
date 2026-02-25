from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import json

from ckanapi import RemoteCKAN
from ckanapi.errors import CKANAPIError, NotFound


@dataclass
class CreateResult:
    created: List[Dict[str, Any]]          # successful creates (and updates if enabled)
    failed: List[Dict[str, Any]]           # errors with payload + message


COMPOSITE_FIELDS = {
    "manufacturer",
    "owner",
    "model",
    "date",
    "alternate_identifier_obj",
    "funder",
    "related_identifier_obj",
}


def _extract_name_from_ckan_error(err: Any) -> Optional[str]:
    """
    Best-effort helper: tries to extract an existing 'name' from common CKAN error shapes.
    You can remove this if you don't want update behavior.
    """
    try:
        # Sometimes error is a dict like {"name": ["That URL is already in use."]}
        if isinstance(err, dict):
            if "name" in err and isinstance(err["name"], list):
                return None
        # Sometimes error is a string; no reliable extraction without your site's exact message format.
        return None
    except Exception:
        return None


def to_ckan_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    p = dict(payload)

    # Convert composite lists/dicts to JSON strings (scheming repeating composite pattern)
    for k in COMPOSITE_FIELDS:
        if k in p and isinstance(p[k], (list, dict)):
            p[k] = json.dumps(p[k], ensure_ascii=False)

    # Spatial is often stored as a string too
    if "spatial" in p and isinstance(p["spatial"], dict):
        p["spatial"] = json.dumps(p["spatial"], ensure_ascii=False)

    # Optional: remove keys with None values inside JSON composites
    # (usually not required, but keeps payload cleaner)
    return p


class CKANClient(RemoteCKAN):
    """
    CKAN API client for managing datasets (instruments, etc.).
    Inherits from RemoteCKAN and provides convenient methods for batch operations.
    """

    def create_datasets(
        self,
        datasets: List[Dict[str, Any]],
        make_public: bool = False,
        *,
        dataset_type: str = "instrument",
        dry_run: bool = False,
        allow_update_if_exists: bool = False,
    ) -> CreateResult:
        """
        Create CKAN datasets using package_create (or package_update if enabled and exists).

        Assumptions:
          - Your payload dicts match the CKAN scheming fields (e.g. title, owner, manufacturer, model, etc.)
          - CKAN will generate `name` and DOI (if applicable) server-side
        """
        created: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []

        for i, payload in enumerate(datasets, start=1):
            # Ensure dataset_type is set (scheming uses this)
            payload_to_send = dict(payload)
            payload_to_send["private"] = not make_public
            payload_to_send.setdefault("type", dataset_type)

            if dry_run:
                created.append(
                    {
                        "status": "dry_run",
                        "index": i,
                        "title": payload_to_send.get("title"),
                        "payload": payload_to_send,
                    }
                )
                continue

            try:
                # Create
                payload_to_send = to_ckan_payload(payload_to_send)
                resp = self.action.package_create(**payload_to_send)
                created.append(
                    {
                        "status": "created",
                        "index": i,
                        "id": resp.get("id"),
                        "name": resp.get("name"),
                        "title": resp.get("title"),
                        "doi": resp.get("doi"),  # may be None depending on your site/plugin behavior
                        "response": resp,
                    }
                )

            except CKANAPIError as e:
                # If already exists and update allowed, try update.
                # Note: CKAN typically errors on name collision; but your loader excludes name, so collision is unlikely.
                msg = getattr(e, "error_dict", None) or str(e)

                # Optional "exists → update" path, only if we can identify a target.
                if allow_update_if_exists:
                    # If server returns a name conflict, you can parse msg and attempt package_show+update.
                    # Otherwise you need an external key; if you store one, include it in payload as an extra field.
                    target_name = _extract_name_from_ckan_error(msg)  # best-effort helper below
                    if target_name:
                        try:
                            existing = self.action.package_show(id=target_name)
                            payload_to_send["id"] = existing["id"]
                            resp2 = self.action.package_update(**payload_to_send)
                            created.append(
                                {
                                    "status": "updated",
                                    "index": i,
                                    "id": resp2.get("id"),
                                    "name": resp2.get("name"),
                                    "title": resp2.get("title"),
                                    "doi": resp2.get("doi"),
                                    "response": resp2,
                                }
                            )
                            continue
                        except Exception as e2:
                            failed.append(
                                {
                                    "index": i,
                                    "title": payload_to_send.get("title"),
                                    "error": f"Create failed; update attempt failed: {e2}",
                                    "ckan_error": msg,
                                    "payload": payload_to_send,
                                }
                            )
                            continue

                failed.append(
                    {
                        "index": i,
                        "title": payload_to_send.get("title"),
                        "error": "CKANAPIError",
                        "ckan_error": msg,
                        "payload": payload_to_send,
                    }
                )

            except Exception as e:
                failed.append(
                    {
                        "index": i,
                        "title": payload_to_send.get("title"),
                        "error": f"Unexpected error: {e}",
                        "payload": payload_to_send,
                    }
                )

        return CreateResult(created=created, failed=failed)

    def delete_all_in_org(
        self,
        owner_org: str = 'auscope',
        *,
        dry_run: bool = True,
        dataset_type: Optional[str] = "instrument",
    ) -> List[Dict[str, Any]]:
        """
        Delete all datasets in an organization.

        Args:
            owner_org: The organization ID or name
            dry_run: If True, only list datasets without deleting
            dataset_type: Filter by dataset type. If None, delete all datasets in the org.

        Returns:
            List of datasets that were (or would be) deleted
        """
        # Build query based on whether dataset_type is specified
        if dataset_type is not None:
            q = f"type:{dataset_type}"
            type_label = f"{dataset_type} "
        else:
            q = "*:*"
            type_label = ""

        owner_org_id = self.get_org_id_by_name(owner_org)
        if owner_org_id is None:
            raise NotFound(f"Organization {owner_org!r} not found.")

        fq = f"owner_org:{owner_org_id}"
        start = 0
        rows = 100
        to_delete = []

        while True:
            res = self.action.package_search(q=q, fq=fq, start=start, rows=rows)
            results = res.get("results", [])
            if not results:
                break
            for pkg in results:
                to_delete.append({"id": pkg["id"], "name": pkg["name"], "title": pkg.get("title")})
            start += rows

        print(f"Found {len(to_delete)} {type_label}dataset(s) in owner_org={owner_org!r}")
        for p in to_delete[:20]:
            print(f" - {p['name']} ({p['id']}) | {p.get('title')}")
        if len(to_delete) > 20:
            print(f" ... and {len(to_delete)-20} more")

        if dry_run:
            print("\nDRY RUN: no deletions performed.")
            return to_delete

        deleted = 0
        failed = []
        for p in to_delete:
            try:
                self.action.package_delete(id=p["id"])
                deleted += 1
            except CKANAPIError as e:
                failed.append({"pkg": p, "error": getattr(e, "error_dict", None) or str(e)})

        print(f"\nDeleted: {deleted}")
        if failed:
            print(f"Failed: {len(failed)}")
            for f in failed[:10]:
                print(" -", f)
        return to_delete


    def get_org_id_by_name(self, org_name: str) -> Optional[str]:
        """
        Helper to get organization ID by name.
        Returns None if not found or on error.
        """
        try:
            return self.action.organization_show(id=org_name).get('id')
        except Exception as e:
            print(f"Error fetching organizations: {e}")
            return None


    def get_all(
        self,
        q: str = "*:*",
        fq: Optional[str] = None,
        rows: int = 500,
        include_private: bool = True,
        include_drafts: bool = True,
        verbose: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Returns all packages visible to the API key user.

        Notes:
        - Uses Solr via package_search.
        - You only get what the user can see (private datasets require permission).
        - `include_private/include_drafts` control CKAN search flags.
        """
        start = 0
        out: List[Dict[str, Any]] = []

        while True:
            res = self.action.package_search(
                q=q,
                fq=fq,
                start=start,
                rows=rows,
                include_private=include_private,
                include_drafts=include_drafts,
            )
            results = res.get("results", [])
            if not results:
                break

            for pkg in results:
                if verbose:
                    out.append(pkg)  # full package dict
                else:
                    out.append(
                        {
                            "id": pkg.get("id"),
                            "name": pkg.get("name"),
                            "title": pkg.get("title"),
                            "type": pkg.get("type"),
                            "state": pkg.get("state"),
                            "owner_org": pkg.get("owner_org"),
                        }
                    )

            start += rows

        return out
