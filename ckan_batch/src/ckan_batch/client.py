from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
import json

from ckan_batch.reader.pidinst import _to_ckan_payload
from ckanapi import RemoteCKAN
from ckanapi.errors import CKANAPIError, NotFound


@dataclass
class CreateResult:
    created: List[Dict[str, Any]]          # successful creates (and updates if enabled)
    failed: List[Dict[str, Any]]           # errors with payload + message
    resource_results: List[Dict[str, Any]] = field(default_factory=list)  # per-dataset resource upload results


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


class CKANClient(RemoteCKAN):
    """
    CKAN API client for managing datasets (instruments, etc.).
    Inherits from RemoteCKAN and provides convenient methods for batch operations.
    """

    def create_resources_for_dataset(
        self,
        package_id: str,
        resources: List[Dict[str, Any]],
        *,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Upload file resources to an existing CKAN dataset.
        Each resource dict: {path, name, is_cover, format, description}
        """
        created: List[Dict[str, Any]] = []
        failed: List[Dict[str, Any]] = []

        for res in resources:
            path_str = res.get("path")
            p = Path(path_str) if path_str else None

            if not p or not p.is_file():
                failed.append({"path": path_str, "error": "File not found or not a valid file path"})
                continue

            name = res.get("name") or p.name
            is_cover = res.get("is_cover")
            fmt = res.get("format") or ""
            desc = res.get("description") or ""

            payload = {
                "package_id": package_id,
                "url": "upload",
                "name": name,
                "description": desc,
                "format": fmt,
                "pidinst_is_cover_image": "true" if is_cover else "false",
            }

            if dry_run:
                created.append({"status": "dry_run", "path": str(p), "payload": payload})
                continue

            try:
                with open(p, "rb") as fh:
                    resp = self.action.resource_create(upload=fh, **payload)
                created.append({
                    "id": resp.get("id"),
                    "name": resp.get("name"),
                    "url": resp.get("url"),
                })
            except CKANAPIError as e:
                failed.append({
                    "path": str(p),
                    "error": "CKANAPIError",
                    "ckan_error": getattr(e, "error_dict", None) or str(e),
                })
            except Exception as e:
                failed.append({"path": str(p), "error": f"Unexpected error: {e}"})

        return {"created": created, "failed": failed}

    def create_datasets(
        self,
        datasets: List[Dict[str, Any]],
        make_public: bool = False,
        *,
        dataset_type: str = "dataset",
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
        resource_results: List[Dict[str, Any]] = []

        for i, payload in enumerate(datasets, start=1):
            # Extract __resources__ before building CKAN payload
            resources = list(payload.get("__resources__") or [])

            # Ensure dataset_type is set (scheming uses this)
            payload_to_send = dict(payload)
            payload_to_send.pop("__resources__", None)
            payload_to_send["private"] = not make_public
            payload_to_send.setdefault("type", dataset_type)

            if dry_run:
                rr = self.create_resources_for_dataset(f"dry_run_{i}", resources, dry_run=True)
                resource_results.append({"index": i, "package_id": None, **rr})
                created.append(
                    {
                        "status": "dry_run",
                        "index": i,
                        "title": payload_to_send.get("title"),
                        "payload": payload_to_send,
                        "resources_dry_run": rr,
                    }
                )
                continue

            try:
                # Create
                payload_to_send = _to_ckan_payload(payload_to_send)  # optional pre-processing if needed
                resp = self.action.package_create(**payload_to_send)
                pkg_id = resp.get("id")
                rr = self.create_resources_for_dataset(pkg_id, resources, dry_run=dry_run)
                resource_results.append({"index": i, "package_id": pkg_id, **rr})
                created.append(
                    {
                        "status": "created",
                        "index": i,
                        "id": pkg_id,
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
                            pkg_id2 = resp2.get("id")
                            rr2 = self.create_resources_for_dataset(pkg_id2, resources, dry_run=dry_run)
                            resource_results.append({"index": i, "package_id": pkg_id2, **rr2})
                            created.append(
                                {
                                    "status": "updated",
                                    "index": i,
                                    "id": pkg_id2,
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

        return CreateResult(created=created, failed=failed, resource_results=resource_results)

    def delete_all_in_org(
        self,
        owner_org: str = "auscope",
        *,
        dry_run: bool = True,
        dataset_type: Optional[str] = "instrument",
        include_draft: bool = True,
        include_private: bool = True,
        include_public: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Delete datasets in an organization with configurable inclusion of draft/private/public.

        IMPORTANT:
        - Draft visibility in `package_search` is controlled by `include_drafts=True` (not reliably by q/fq alone).
        - Private visibility in `package_search` is controlled by `include_private=True`.
        """
        if not (include_private or include_public or include_draft):
            print("Nothing to do: include_draft/include_private/include_public are all False.")
            return []

        owner_org_id = self.get_org_id_by_name(owner_org)
        if owner_org_id is None:
            raise NotFound(f"Organization {owner_org!r} not found.")

        # q: only put "type" filtering here (simple + stable)
        q_parts: List[str] = []
        if dataset_type is not None:
            q_parts.append(f"type:{dataset_type}")
            type_label = f"{dataset_type} "
        else:
            type_label = ""

        q = " AND ".join(q_parts) if q_parts else "*:*"

        # fq: owner_org + optional state/private filters
        fq_parts = [f"owner_org:{owner_org_id}"]

        # Visibility filters (field is `private`)
        # - public datasets are always included by default
        # - private datasets require include_private=True
        if include_private and not include_public:
            fq_parts.append("private:true")   # only private
        elif include_public and not include_private:
            fq_parts.append("private:false")  # only public
        elif not include_public and not include_private:
            # nothing can match
            print("Nothing to do: both include_private and include_public are False.")
            return []

        # State filters (field is `state`)
        # - drafts require include_drafts=True
        if include_draft and False:
            pass  # (keep both active + draft)
        elif include_draft and not include_public and not include_private:
            # already returned above, but keep logic explicit
            return []
        elif include_draft:
            # include both active+draft: no fq state filter
            pass
        else:
            # only active
            fq_parts.append("state:active")

        fq = " AND ".join(fq_parts)

        # These flags are the key for draft/private visibility in package_search
        include_drafts_flag = bool(include_draft)
        include_private_flag = bool(include_private)

        start = 0
        rows = 100
        to_delete: List[Dict[str, Any]] = []

        while True:
            res = self.action.package_search(
                q=q,
                fq=fq,
                start=start,
                rows=rows,
                include_drafts=include_drafts_flag,
                include_private=include_private_flag,
            )
            results = res.get("results", [])
            if not results:
                break

            for pkg in results:
                to_delete.append(
                    {
                        "id": pkg["id"],
                        "name": pkg["name"],
                        "title": pkg.get("title"),
                        "state": pkg.get("state"),
                        "private": pkg.get("private"),
                    }
                )
            start += rows

        print(
            f"Found {len(to_delete)} {type_label}dataset(s) in owner_org={owner_org!r} "
            f"(draft={include_draft}, private={include_private}, public={include_public})"
        )
        for p in to_delete[:20]:
            vis = "private" if p.get("private") else "public"
            print(f" - {p['name']} ({p['id']}) [{p.get('state')}, {vis}] | {p.get('title')}")
        if len(to_delete) > 20:
            print(f" ... and {len(to_delete) - 20} more")

        if dry_run:
            print("\nDRY RUN: no deletions performed.")
            return to_delete

        deleted = 0
        failed: List[Dict[str, Any]] = []
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
