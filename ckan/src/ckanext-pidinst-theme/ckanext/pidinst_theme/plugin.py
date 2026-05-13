import json

import ckan.plugins as plugins
import ckan.plugins.toolkit as toolkit
from ckanext.doi.lib import metadata as doi_metadata
import os

from ckanext.pidinst_theme.logic import validators
from ckanext.pidinst_theme import views
from ckanext.pidinst_theme import helpers
from ckanext.pidinst_theme import analytics
from ckanext.pidinst_theme import relation_sync

import ckan.model as model
import logging
log = logging.getLogger(__name__)


# import ckanext.pidinst_theme.cli as cli
from ckanext.pidinst_theme.logic import (
    action, schema, auth, validators
)


original_build_metadata_dict = doi_metadata.build_metadata_dict


def patched_build_metadata_dict(pkg_dict):
    """
    A patched version of build_metadata_dict to correct language handling and possibly other
    adjustments needed for DOI metadata.
    """
    # Call the original function
    xml_dict = original_build_metadata_dict(pkg_dict)

    # Correct the language field
    xml_dict['language'] = 'en'  # or some other logic to determine the correct language

    # Remove geoLocations if present (user doesn't want locality in DOI)
    if 'geoLocations' in xml_dict:
        del xml_dict['geoLocations']

    # Return the modified metadata dict
    return xml_dict


# Apply the patch
doi_metadata.build_metadata_dict = patched_build_metadata_dict


def _apply_or_within_block_for_group_page(fq):
    """Replace per-value AND clauses with OR groups for multi-selected checkbox facets.

    CKAN's group/org read view calls _get_search_details() which appends each
    selected value as a separate  field:"value"  clause (always ANDed by Solr).
    This function converts them to a single  +(field:"a" OR field:"b")  clause
    so that matching either value is sufficient (OR within a facet block).

    Uses request.args as the authoritative source of selected values rather than
    parsing the fq string, so exact string replacement is used instead of regex.
    The  new_fq != fq  guard means baseline queries (which don't contain these
    clauses) are returned unchanged without any separate flag mechanism.
    """
    try:
        request_args = toolkit.request.args
    except RuntimeError:
        return fq  # No active Flask request context (e.g. CLI or background job)

    for field in views._CHECKBOX_FACET_FIELDS:
        values = request_args.getlist(field)
        if len(values) <= 1:
            continue
        # Remove each individual AND clause that CKAN's _get_search_details added.
        # Format is always " field:\"value\"" (space-prefixed, no + sign).
        new_fq = fq
        for v in values:
            new_fq = new_fq.replace(f' {field}:"{v}"', '')
        if new_fq == fq:
            # Nothing was replaced: this field is not in the fq (e.g. baseline
            # query with only owner_org scope filter). Skip without modifying.
            continue
        fq = new_fq.rstrip()
        # Re-add as a single required OR group so Solr returns docs matching any value.
        or_parts = ' OR '.join(f'{field}:"{v}"' for v in values)
        fq += f' +({or_parts})'

    return fq.strip()


class PidinstThemePlugin(plugins.SingletonPlugin):
    plugins.implements(plugins.IConfigurer)
    plugins.implements(plugins.IPackageController, inherit=True)
    plugins.implements(plugins.IResourceController, inherit=True)

    plugins.implements(plugins.IAuthFunctions)
    plugins.implements(plugins.IActions)
    plugins.implements(plugins.IBlueprint)
    # plugins.implements(plugins.IClick)
    plugins.implements(plugins.ITemplateHelpers)
    plugins.implements(plugins.IValidators)
    plugins.implements(plugins.ITranslation)
    plugins.implements(plugins.IFacets, inherit=True)
    plugins.implements(plugins.IDatasetForm, inherit=True)
    plugins.implements(plugins.IAuthenticator, inherit=True)

    # IAuthenticator
    def authenticate(self, identity):
        """Case-insensitive email login support.

        CKAN's default authenticator uses User.by_email() which does an
        exact (case-sensitive) match on PostgreSQL.  This implementation
        falls back to a case-insensitive email lookup so that users can
        log in regardless of how they capitalised their email address.

        We also filter for active users only, so that deleted accounts
        sharing the same email address do not shadow the active one.
        """
        login = identity.get('login', '')
        password = identity.get('password', '')
        if not login or not password:
            return None

        from ckan.model import User
        from sqlalchemy import func

        # Try username first (exact match, same as CKAN default)
        user_obj = User.by_name(login)

        # Fall back to case-insensitive email lookup (active users only)
        if not user_obj and '@' in login:
            user_obj = (
                model.Session.query(User)
                .filter(func.lower(User.email) == login.lower())
                .filter(User.state == 'active')
                .first()
            )

        if user_obj is None:
            return None
        if not user_obj.is_active:
            return None
        if not user_obj.validate_password(password):
            return None
        return user_obj

    # ITranslation
    def i18n_domain(self):
        # This should return the extension's name
        return 'pidinst_theme'

    def i18n_locales(self):
        # Return a list of locales your extension supports
        return ['en_AU']
        # return ['en']


    def i18n_directory(self):
        # This points to 'ckanext-pidinst_theme/ckanext/pidinst_theme/i18n'
        # CKAN uses this path relative to the CKAN extensions directory.
        return os.path.join('ckanext', 'pidinst_theme', 'i18n')

    # IConfigurer
    def update_config(self, config_):
        # toolkit.add_template_directory(config_, '/shared/templates')
        toolkit.add_template_directory(config_, "templates")
        toolkit.add_public_directory(config_, '/shared/public')
        toolkit.add_public_directory(config_, "public")
        toolkit.add_resource("assets", "pidinst_theme")
        # Initialise backend analytics eagerly so startup logs reveal config problems
        # (SDK missing, WRITE_KEY absent, etc.) instead of silently failing on first event.
        analytics.AnalyticsTracker.initialize()


    # IPackageController
    # def process_doi_metadata(self, pkg_dict):
    #     pkg_dict['language_code'] = 'en'
    # IPackageController
    # def process_doi_metadata(self, pkg_dict):
    #     pkg_dict['language_code'] = 'en'
    def before_dataset_index(self, pkg_dict):
        import json

        def _load_list(value):
            if not value:
                return []
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except Exception:
                    return []
            return value if isinstance(value, list) else []

        def _extract_names(items, key):
            """Extract non-empty values for key from a list of dicts."""
            return [
                item.get(key)
                for item in items
                if isinstance(item, dict) and item.get(key)
            ]

        # --- text-search fields ---
        manufacturers = _load_list(pkg_dict.get("manufacturer"))
        manufacturer_names = _extract_names(manufacturers, "manufacturer_name")
        pkg_dict["manufacturer_name_search"] = " | ".join(manufacturer_names)

        models = _load_list(pkg_dict.get("model"))
        pkg_dict["model_name_search"] = " | ".join(_extract_names(models, "model_name"))

        alternate_id_objs = _load_list(pkg_dict.get("alternate_identifier_obj"))
        pkg_dict["alternate_identifier_search"] = " | ".join(
            _extract_names(alternate_id_objs, "alternate_identifier"))

        # --- multi-valued facet fields ---

        def _is_gcmd(item):
            """True if the entry came from a GCMD/ARDC vocabulary (by identifier URI)."""
            ident = (item.get("instrument_type_identifier")
                     or item.get("measured_variable_identifier") or "")
            return (
                'cmr.earthdata.nasa.gov' in ident
                or 'gcmd.earthdata.nasa.gov' in ident
                or 'vocabs.ardc.edu.au' in ident
            )

        def _split_by_source(items, name_key):
            """Split items into (all, gcmd_only, custom_only) name lists."""
            all_names = _extract_names(items, name_key)
            gcmd = [n for n, it in zip(all_names, items) if _is_gcmd(it)]
            custom = [n for n, it in zip(all_names, items) if not _is_gcmd(it)]
            return all_names, gcmd, custom

        instrument_types = _load_list(pkg_dict.get("instrument_type"))
        all_it, gcmd_it, custom_it = _split_by_source(instrument_types, "instrument_type_name")
        pkg_dict["vocab_instrument_type"] = all_it
        pkg_dict["vocab_instrument_type_gcmd"] = gcmd_it
        pkg_dict["vocab_instrument_type_custom"] = custom_it

        # Instrument classification (simple select field)
        classification = (pkg_dict.get("instrument_classification") or "").strip()
        pkg_dict["vocab_instrument_classification"] = [classification] if classification else []

        owners = _load_list(pkg_dict.get("owner"))
        pkg_dict["vocab_owner_party"] = _extract_names(owners, "owner_name")

        pkg_dict["vocab_manufacturer_party"] = list(manufacturer_names)

        funders = _load_list(pkg_dict.get("funder"))
        pkg_dict["vocab_funder_party"] = _extract_names(funders, "funder_name")

        measured_vars = _load_list(pkg_dict.get("measured_variable"))
        all_mv, gcmd_mv, custom_mv = _split_by_source(measured_vars, "measured_variable_name")
        pkg_dict["vocab_measured_variable"] = all_mv
        pkg_dict["vocab_measured_variable_gcmd"] = gcmd_mv
        pkg_dict["vocab_measured_variable_custom"] = custom_mv

        # User-specified keywords (stored as a JSON list string)
        user_kw_raw = pkg_dict.get("user_keywords")
        if isinstance(user_kw_raw, list):
            pkg_dict["vocab_user_keyword"] = [str(k).strip() for k in user_kw_raw if str(k).strip()]
        elif isinstance(user_kw_raw, str):
            try:
                kw_list = json.loads(user_kw_raw)
                pkg_dict["vocab_user_keyword"] = (
                    [str(k).strip() for k in kw_list if str(k).strip()]
                    if isinstance(kw_list, list) else []
                )
            except Exception:
                pkg_dict["vocab_user_keyword"] = []
        else:
            pkg_dict["vocab_user_keyword"] = []

        # --- Date indexing (tokens + integer interval bounds for overlap queries) ---
        def _date_tokens(date_str):
            parts = date_str.strip().split('-')
            return {'-'.join(parts[:i]) for i in range(1, len(parts) + 1) if parts[0]}

        def _date_to_int_range(date_str):
            """Convert date string to (start, end) YYYYMMDD integers."""
            import calendar
            parts = date_str.strip().split('-')
            try:
                if len(parts) == 1:
                    y = int(parts[0])
                    return (y * 10000 + 101, y * 10000 + 1231)
                elif len(parts) == 2:
                    y, m = int(parts[0]), int(parts[1])
                    last_day = calendar.monthrange(y, m)[1]
                    return (y * 10000 + m * 100 + 1, y * 10000 + m * 100 + last_day)
                elif len(parts) == 3:
                    y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                    val = y * 10000 + m * 100 + d
                    return (val, val)
            except (ValueError, TypeError):
                pass
            return (None, None)

        dates = _load_list(pkg_dict.get("date"))
        commissioned_tokens = set()
        decommissioned_tokens = set()
        commissioned_year = None
        decommissioned_year = None

        # Track earliest start / latest end for interval bounds
        comm_starts, comm_ends = [], []
        decomm_starts, decomm_ends = [], []

        for entry in dates:
            if not isinstance(entry, dict):
                continue
            date_type = entry.get("date_type", "")
            date_val = (entry.get("date_value") or "").strip()
            if not date_val:
                continue

            if date_type == "Commissioned":
                commissioned_tokens.update(_date_tokens(date_val))
                s, e = _date_to_int_range(date_val)
                if s is not None:
                    comm_starts.append(s)
                    comm_ends.append(e)
                year_str = date_val[:4]
                if year_str.isdigit() and commissioned_year is None:
                    commissioned_year = int(year_str)

            elif date_type == "DeCommissioned":
                decommissioned_tokens.update(_date_tokens(date_val))
                s, e = _date_to_int_range(date_val)
                if s is not None:
                    decomm_starts.append(s)
                    decomm_ends.append(e)
                year_str = date_val[:4]
                if year_str.isdigit() and decommissioned_year is None:
                    decommissioned_year = int(year_str)

        pkg_dict["vocab_commissioned_date"] = list(commissioned_tokens)
        pkg_dict["vocab_decommissioned_date"] = list(decommissioned_tokens)
        # Keep year integers for backward compat
        if commissioned_year is not None:
            pkg_dict["commissioned_year_i"] = commissioned_year
        if decommissioned_year is not None:
            pkg_dict["decommissioned_year_i"] = decommissioned_year

        # Integer interval bounds for overlap queries
        if comm_starts:
            pkg_dict["commissioned_start_i"] = min(comm_starts)
        if comm_ends:
            pkg_dict["commissioned_end_i"] = max(comm_ends)
        if decomm_starts:
            pkg_dict["decommissioned_start_i"] = min(decomm_starts)
        if decomm_ends:
            pkg_dict["decommissioned_end_i"] = max(decomm_ends)

        return pkg_dict



    def before_view(self, pkg_dict):
        pass

    def before_dataset_update(self, context, pkg_dict):
        """Snapshot the DOI published state before the update.

        Stores ``context['_analytics_doi_was_published']``:
          * ``True``  – DOI record existed and ``doi.published`` was set.
          * ``False`` – DOI record absent or ``doi.published`` was None.
          * ``None``  – Query failed; state is unknown.

        Stage 3A transition rule (in after_dataset_update):
          * Only fire if was_published=False AND now published=True.
          * was_published=None → conservative: skip event to avoid duplicates.

        For reliable detection this plugin must be listed *after* ``doi`` in
        ``ckan.plugins`` so that ckanext-doi's after_dataset_update (which
        calls ``mint_doi()`` and sets ``doi.published``) has already run when
        our after_dataset_update hook executes.
        """
        try:
            pkg_id = pkg_dict.get('id')
            if pkg_id:
                from ckanext.doi.model.crud import DOIQuery  # noqa: PLC0415
                record = DOIQuery.read_package(pkg_id)
                context['_analytics_doi_was_published'] = (
                    record is not None and record.published is not None
                )
            else:
                context['_analytics_doi_was_published'] = None
        except Exception:
            context['_analytics_doi_was_published'] = None
        return pkg_dict

    def after_dataset_create(self, context, pkg_dict):
        # 1) Ensure version_handler_id is set on first creation
        try:
            if not pkg_dict.get("version_handler_id"):
                pkg_id = pkg_dict["id"]

                patch_ctx = dict(context)
                patch_ctx["ignore_auth"] = True
                # Prevent after_dataset_update from firing a spurious
                # 'Update Existing Dataset' analytics event for this
                # internal package_patch call.
                patch_ctx["_analytics_suppress"] = True

                toolkit.get_action("package_patch")(
                    patch_ctx,
                    {"id": pkg_id, "version_handler_id": pkg_id}
                )

                # also update local copy so subsequent code sees it
                pkg_dict["version_handler_id"] = pkg_id

        except Exception as e:
            logging.exception("Failed to set version_handler_id on create: %s", e)

        try:
            analytics.track_dataset_created(pkg_dict)
        except Exception as e:
            logging.error(f"Failed to track instrument creation: {e}")

        try:
            if analytics._is_new_version_pkg(pkg_dict):
                source_id = analytics._reuse_source_from_pkg(pkg_dict)
                analytics.track_dataset_reuse_created(pkg_dict,
                                                      source_dataset_id=source_id)
        except Exception as e:
            logging.error(f"Failed to track dataset reuse creation: {e}")

        # Sync party group membership
        self._sync_party_groups(context, pkg_dict)

    def after_dataset_update(self, context, pkg_dict):
        # Skip analytics tracking when the update was triggered internally
        # (e.g. the package_patch call inside after_dataset_create that sets
        # version_handler_id).  The caller sets _analytics_suppress=True to
        # signal this.
        if context.get('_analytics_suppress'):
            return

        try:
            analytics.track_dataset_updated(pkg_dict)

            was_published = context.get('_analytics_doi_was_published')
            if was_published is False:
                pkg_id = pkg_dict.get('id', '')
                is_now_published, doi_status = analytics._doi_status_from_db(pkg_id)
                if is_now_published:
                    analytics.track_doi_published(pkg_dict, doi_status=doi_status)
        except Exception as e:
            logging.error(f"Failed to track instrument update: {e}")

        # Sync party group membership
        self._sync_party_groups(context, pkg_dict)

        # Sync reciprocal instrument relationships on publish
        try:
            relation_sync.sync_publish_reciprocals(context, pkg_dict)
        except Exception as e:
            logging.error('Failed to sync publish reciprocals: %s', e)

        # Clean up reciprocals if withdrawn
        pub_status = pkg_dict.get('publication_status', '')
        if pub_status in ('withdrawn', 'duplicate'):
            try:
                relation_sync.cleanup_reciprocals(context, pkg_dict)
            except Exception as e:
                logging.error('Failed to cleanup reciprocals: %s', e)

    def after_dataset_delete(self, context, pkg_dict):
        try:
            relation_sync.cleanup_reciprocals(context, pkg_dict)
        except Exception as e:
            logging.error('Failed to cleanup reciprocals on delete: %s', e)

        # self.process_doi_metadata(pkg_dict)

    def _sync_party_groups(self, context, pkg_dict):
        """Add/remove this package from party CKAN groups so that
        group-based faceting (``fq=groups:name``) and party-page
        instrument counts work automatically.

        Reads party IDs from the ``owner``, ``funder``, and
        ``manufacturer`` composite fields and ensures the package is a
        member of exactly those party groups.
        """
        try:
            pkg_id = pkg_dict.get('id')
            if not pkg_id:
                return

            # ---- Desired party IDs from composite fields ------------- #
            desired = set()

            # Helper to extract party IDs from a composite repeating field
            def _collect_party_ids(field_name, id_key):
                raw = pkg_dict.get(field_name)
                if not raw:
                    return
                if isinstance(raw, str):
                    try:
                        entries = json.loads(raw)
                    except (json.JSONDecodeError, ValueError):
                        entries = []
                elif isinstance(raw, list):
                    entries = raw
                else:
                    entries = []
                for entry in entries:
                    party_id = (entry.get(id_key) or '').strip()
                    if party_id:
                        desired.add(party_id)

            _collect_party_ids('owner', 'owner_party_id')
            _collect_party_ids('funder', 'funder_party_id')
            _collect_party_ids('manufacturer', 'manufacturer_party_id')

            # ---- Current party group memberships --------------------- #
            ctx = {'ignore_auth': True}

            # All party group names in the system
            all_party_names = set(
                toolkit.get_action('group_list')(ctx, {'type': 'party'})
            )

            # Current groups this package belongs to.
            # pkg_dict is the full package result already returned by
            # package_create / package_update, so no extra package_show is needed.
            current_party_groups = {
                g['name'] for g in pkg_dict.get('groups', [])
                if g.get('name') in all_party_names
            }

            # ---- Reconcile ------------------------------------------------ #
            to_add = (desired & all_party_names) - current_party_groups
            to_remove = current_party_groups - desired

            for fac_id in to_add:
                try:
                    toolkit.get_action('member_create')(ctx, {
                        'id': fac_id,
                        'object': pkg_id,
                        'object_type': 'package',
                        'capacity': 'public',
                    })
                except Exception as e:
                    logging.error(
                        'Failed to add package %s to party group %s: %s',
                        pkg_id, fac_id, e,
                    )

            for fac_id in to_remove:
                try:
                    toolkit.get_action('member_delete')(ctx, {
                        'id': fac_id,
                        'object': pkg_id,
                        'object_type': 'package',
                    })
                except Exception as e:
                    logging.error(
                        'Failed to remove package %s from party group %s: %s',
                        pkg_id, fac_id, e,
                    )

            if to_add or to_remove:
                logging.info(
                    'Party group sync for %s: added=%s removed=%s',
                    pkg_id, to_add, to_remove,
                )

        except Exception as e:
            logging.exception('Failed to sync party groups for %s: %s',
                              pkg_dict.get('id', '?'), e)

    def after_dataset_show(self, *args, **kwargs):
        return schema.after_dataset_show(*args, **kwargs)

    def before_dataset_search(self, search_params):
        search_params = schema.before_dataset_search(search_params)
        path = '<no-request>'
        is_group_page = False
        try:
            path = toolkit.request.path
            is_group_page = path.startswith('/organization/') or path.startswith('/party/')
        except RuntimeError:
            pass
        if is_group_page:
            original_fq = search_params.get('fq', '')
            rewritten_fq = _apply_or_within_block_for_group_page(original_fq)
            log.debug(
                '[pidinst] before_dataset_search path=%s fq_before=%r fq_after=%r',
                path, original_fq, rewritten_fq,
            )
            search_params['fq'] = rewritten_fq
        return search_params

    # IAuthFunctions

    def get_auth_functions(self):
        return auth.get_auth_functions()

    # IActions

    def get_actions(self):
        return action.get_actions()

    # IBlueprint

    def get_blueprint(self):
        return views.get_blueprints()

    # IClick

    # def get_commands(self):
    #     return cli.get_commands()

    # ITemplateHelpers

    def get_helpers(self):
        return helpers.get_helpers()

    # IValidators

    def get_validators(self):
        return validators.get_validators() or {}


    def dataset_facets(self, facets_dict, package_type):
        facets_dict.pop('instrument_type', None)
        facets_dict.pop('vocab_instrument_type', None)
        facets_dict['vocab_instrument_type_gcmd'] = toolkit._('Instrument Type (GCMD)')
        facets_dict['vocab_instrument_type_custom'] = toolkit._('Instrument Type (Custom)')
        facets_dict['vocab_measured_variable_gcmd'] = toolkit._('Measured Variable (GCMD)')
        facets_dict['vocab_measured_variable_custom'] = toolkit._('Measured Variable (Custom)')
        facets_dict['vocab_instrument_classification'] = toolkit._('Instrument Class')
        facets_dict['vocab_manufacturer_party'] = toolkit._('Manufacturers')
        return facets_dict

    def organization_facets(self, facets_dict, organization_type, package_type):
        facets_dict.clear()
        facets_dict['vocab_owner_party'] = toolkit._('Owners')
        facets_dict['vocab_funder_party'] = toolkit._('Funders')
        facets_dict['vocab_manufacturer_party'] = toolkit._('Manufacturers')
        facets_dict['vocab_instrument_classification'] = toolkit._('Instrument Class')
        facets_dict['vocab_instrument_type_gcmd'] = toolkit._('Instrument Type (GCMD)')
        facets_dict['vocab_instrument_type_custom'] = toolkit._('Instrument Type (Custom)')
        facets_dict['vocab_measured_variable_gcmd'] = toolkit._('Measured Variable (GCMD)')
        facets_dict['vocab_measured_variable_custom'] = toolkit._('Measured Variable (Custom)')
        return facets_dict

    def group_facets(self, facets_dict, group_type, package_type):
        if group_type == 'party':
            facets_dict.clear()
            facets_dict['vocab_instrument_classification'] = toolkit._('Instrument Class')
            facets_dict['vocab_instrument_type_gcmd'] = toolkit._('Instrument Type (GCMD)')
            facets_dict['vocab_instrument_type_custom'] = toolkit._('Instrument Type (Custom)')
            facets_dict['vocab_measured_variable_gcmd'] = toolkit._('Measured Variable (GCMD)')
            facets_dict['vocab_measured_variable_custom'] = toolkit._('Measured Variable (Custom)')
            facets_dict['vocab_manufacturer_party'] = toolkit._('Manufacturers')
        return facets_dict

    # IDatasetForm
    # ------------------------------------------------------------------
    # IResourceController – enforce "one cover photo per instrument"
    # ------------------------------------------------------------------

    def after_resource_create(self, context, resource):
        self._enforce_single_cover_photo(context, resource)

    def after_resource_update(self, context, resource):
        self._enforce_single_cover_photo(context, resource)

    def _enforce_single_cover_photo(self, context, resource):
        """If *resource* is flagged as cover photo, clear the flag on every
        other resource in the same instrument."""
        cover_val = resource.get('pidinst_is_cover_image')
        if cover_val not in (True, 'true', 'True'):
            return

        package_id = resource.get('package_id')
        if not package_id:
            return

        try:
            ctx = {'ignore_auth': True}
            pkg = toolkit.get_action('package_show')(ctx, {'id': package_id})
            for r in pkg.get('resources', []):
                if r['id'] == resource['id']:
                    continue
                r_cover = r.get('pidinst_is_cover_image')
                if r_cover in (True, 'true', 'True'):
                    toolkit.get_action('resource_patch')(
                        {'ignore_auth': True},
                        {'id': r['id'], 'pidinst_is_cover_image': 'false'},
                    )
        except Exception as e:
            logging.error('Failed to enforce single cover photo: %s', e)

    def before_dataset_view(self, pkg_dict):
        vhid = pkg_dict.get("version_handler_id")
        if not vhid:
            pkg_dict["is_latest"] = True
            pkg_dict["versions"] = []
            return pkg_dict

        # Build action context correctly
        user = getattr(toolkit.c, "user", None)
        auth_user_obj = getattr(toolkit.c, "userobj", None)

        ctx = {
            "model": model,
            "session": model.Session,
            "user": user,
            "auth_user_obj": auth_user_obj,
        }

        # IMPORTANT: fq must match how you stored it; your API shows version_handler_id works
        fq = f'version_handler_id:"{vhid}"'

        res = toolkit.get_action("package_search")(
            ctx,
            {
                "q": "*:*",
                "fq": fq,
                "rows": 200,
                "sort": "metadata_created desc",
            },
        )

        results = res.get("results", []) or []
        log.warning("version_handler_id=%s fq=%s count=%s", vhid, fq, len(results))

        if not results:
            pkg_dict["is_latest"] = True
            pkg_dict["versions"] = []
            return pkg_dict

        latest_id = results[0].get("id")
        pkg_dict["is_latest"] = (pkg_dict.get("id") == latest_id)

        pkg_dict["versions"] = [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "title": p.get("title") or p.get("name"),
                "url": toolkit.url_for("instrument.read", id=(p.get("name") or p.get("id")), qualified=True),
                "version_number": p.get("version_number"),
                "metadata_created": p.get("metadata_created"),
            }
            for p in results
        ]

        return pkg_dict
