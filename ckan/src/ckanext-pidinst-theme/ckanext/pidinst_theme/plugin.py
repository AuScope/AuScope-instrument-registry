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

import logging

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


    # IPackageController
    # def process_doi_metadata(self, pkg_dict):
    #     pkg_dict['language_code'] = 'en'

    def before_view(self, pkg_dict):
        pass

    def after_dataset_create(self, context, pkg_dict):
        # 1) Ensure version_handler_id is set on first creation
        try:
            if not pkg_dict.get("version_handler_id"):
                pkg_id = pkg_dict["id"]

                patch_ctx = dict(context)
                patch_ctx["ignore_auth"] = True

                toolkit.get_action("package_patch")(
                    patch_ctx,
                    {"id": pkg_id, "version_handler_id": pkg_id}
                )

                # also update local copy so subsequent code sees it
                pkg_dict["version_handler_id"] = pkg_id

        except Exception as e:
            logging.exception("Failed to set version_handler_id on create: %s", e)

        # Track analytics event
        user = context.get('user')
        if user:
            try:
                analytics.track_dataset_created(user, pkg_dict)
            except Exception as e:
                logging.error(f"Failed to track instrument creation: {e}")

        # Sync party group membership
        self._sync_party_groups(context, pkg_dict)

    def after_dataset_update(self, context, pkg_dict):
        # Track analytics event
        user = context.get('user')
        if user:
            try:
                analytics.track_dataset_updated(user, pkg_dict)

                # Check if DOI was just created (doi field exists and is not empty)
                if pkg_dict.get('doi'):
                    analytics.track_doi_created(user, pkg_dict, pkg_dict.get('doi'))
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

            # Current groups this package belongs to
            pkg_full = toolkit.get_action('package_show')(ctx, {'id': pkg_id})
            current_party_groups = {
                g['name'] for g in pkg_full.get('groups', [])
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

    def before_dataset_search(self, *args, **kwargs):
        return schema.before_dataset_search(*args, **kwargs)

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
        facets_dict['instrument_type'] = toolkit._('Instrument Type')
        facets_dict['locality'] = toolkit._('Locality')
        return facets_dict

    def organization_facets(self, facets_dict, organization_type, package_type):
        facets_dict['instrument_type'] = toolkit._('Instrument Type')
        facets_dict['locality'] = toolkit._('Locality')
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
