# Repairing incorrect `IsPartOf` relationships

## Issue

Component instrument records were given `IsPartOf` relationships containing their own DOI instead of the parent survey DOI. Existing incorrect rows were not repaired when a survey was published again because synchronization checked only the parent package ID.

This breaks component-to-survey navigation in DataCite and other metadata consumers. Some components may also have missing or orphaned `IsPartOf` rows after batch updates.

## Solution

The relationship synchronization now:

- resolves the identifier from the parent survey;
- uses `DOI` for a parent DOI and `URL` for an external identifier or landing page;
- corrects an existing relationship when its stored values are wrong; and
- remains idempotent, so repeated publication does not create duplicates.

A one-time `repair-ispartof` command was added. It uses survey-side `HasPart` rows as the authoritative source, fixes incorrect rows, creates missing rows, removes orphaned or duplicate rows, and re-exports changed published DOI records to DataCite.

No database migration is required.

## Production procedure

1. Back up the production CKAN database.
2. Deploy this release and restart the CKAN web and worker processes.
3. Run a dry-run and review the JSON report:

   ```bash
   docker compose exec -T ckan \
     ckan --config /srv/app/ckan.ini pidinst-theme repair-ispartof \
     --dry-run --report /tmp/ispartof-repair-dry-run.json --verbose
   ```

4. Investigate any `unresolved` entries. Confirm the planned `fixed`, `created`, and `removed` counts before continuing.
5. Apply the repair. The default behaviour also updates DataCite, so production DataCite credentials must be configured:

   ```bash
   docker compose exec -T ckan \
     ckan --config /srv/app/ckan.ini pidinst-theme repair-ispartof \
     --report /tmp/ispartof-repair-applied.json --verbose
   ```

6. Run the dry-run again. Successful reconciliation should report `fixed=0 created=0 removed=0`. A non-zero `unchanged` count is expected.

Use `--no-datacite` only when CKAN should be repaired without immediately updating DataCite. In that case, arrange a separate DataCite metadata re-export afterward.

The command is idempotent and can be safely rerun. Keep both JSON reports with the deployment records.
