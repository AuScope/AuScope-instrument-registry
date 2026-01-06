import click


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


def get_commands():
    return [pidinst_theme]
