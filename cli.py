# Simple CLI for Alpha Panda
import asyncio
import click
from app.main import main as run_app


@click.group()
def cli():
    """Alpha Panda CLI"""
    pass


@cli.command()
def run():
    """Run the Alpha Panda application"""
    click.echo("🐼 Starting Alpha Panda...")
    asyncio.run(run_app())


@cli.command()
def bootstrap():
    """Bootstrap topics in Redpanda"""
    click.echo("🚀 Bootstrapping topics...")
    from scripts.bootstrap_topics import main as bootstrap_main
    asyncio.run(bootstrap_main())


@cli.command()
def seed():
    """Seed test data"""
    click.echo("🌱 Seeding test data...")
    from scripts.seed_strategies import seed_data
    asyncio.run(seed_data())


@cli.command()
def api():
    """Run the API server"""
    click.echo("🚀 Starting Alpha Panda API server...")
    from api.main import run as run_api
    run_api()


if __name__ == "__main__":
    cli()