import click
import json

from ckanext.pidinst_theme import relation_repair


@click.group(short_help="pidinst_theme CLI.")
def pidinst_theme():
    """pidinst_theme CLI.
    """
    pass


@pidinst_theme.command()
@click.argument("name", default="pidinst_theme")
def command(name):
    """Docs.
    """
    click.echo("Hello, {name}!".format(name=name))


@pidinst_theme.command(name='repair-ispartof')
@click.option('--dry-run', is_flag=True, help='Plan and report changes without writing.')
@click.option('--id', 'package_ids', multiple=True, help='Restrict repair to package id/name (repeatable).')
@click.option('--limit', type=click.IntRange(min=1), help='Maximum number of records to inspect.')
@click.option('--no-datacite', is_flag=True, help='Do not re-export corrected metadata to DataCite.')
@click.option('--report', 'report_path', type=click.Path(dir_okay=False), help='Write a JSON report.')
@click.option('--verbose', is_flag=True, help='Print per-record actions.')
def repair_ispartof(dry_run, package_ids, limit, no_datacite, report_path, verbose):
    """Repair child IsPartOf rows from authoritative survey HasPart rows."""
    if dry_run:
        click.secho('=== DRY RUN: no CKAN or DataCite writes will be made ===', fg='yellow', bold=True)

    result = relation_repair.run_repair(
        ids=package_ids,
        limit=limit,
        dry_run=dry_run,
        reexport=not no_datacite,
    )
    data = result.to_dict()
    totals = data['totals']
    click.echo(
        'fixed={fixed} created={created} removed={removed} unchanged={unchanged} '
        'unresolved={unresolved} reexported={reexported} '
        'reexport_failed={reexport_failed}'.format(**totals)
    )

    if verbose:
        for record in data['records']:
            if not record['actions'] and not record['unresolved']:
                continue
            click.echo('{}: {}'.format(
                record['id'],
                ', '.join(
                    '{}:{}'.format(item['action'], item.get('parent_id', ''))
                    for item in record['actions']
                ) or 'unresolved',
            ))

    if report_path:
        with open(report_path, 'w', encoding='utf-8') as report_file:
            json.dump(data, report_file, indent=2, sort_keys=True)
            report_file.write('\n')
        click.echo('Report written to {}'.format(report_path))

    if data['failures']:
        raise click.exceptions.Exit(1)


def get_commands():
    return [pidinst_theme]
