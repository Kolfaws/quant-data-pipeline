"""Initialize, publish, or export versioned A-share daily data."""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    root.add_argument("--env-file", type=Path, help="explicit runtime credential file")
    sub = root.add_subparsers(dest="action", required=True)
    sub.add_parser("check")
    sub.add_parser("init")
    sub.add_parser("init-nav")
    publish = sub.add_parser("publish-nav")
    publish.add_argument("--duckdb", type=Path, required=True)
    publish.add_argument("--run-id", required=True)
    publish.add_argument("--input-version", type=int, required=True)
    nav_export = sub.add_parser("export-nav")
    nav_export.add_argument("--run-id", required=True)
    nav_export.add_argument("--revision", type=int, required=True)
    nav_export.add_argument("--output", type=Path, required=True)
    for action in ("ingest", "export"):
        command = sub.add_parser(action)
        command.add_argument("--start", type=date.fromisoformat, required=True)
        command.add_argument("--end", type=date.fromisoformat, required=True)
        if action == "export":
            command.add_argument("--output", type=Path, required=True)
            command.add_argument("--version", type=int)
            command.add_argument("--code", action="append", default=[])
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.env_file and not args.env_file.is_file():
        print("Configured environment file is unavailable")
        return 1
    try:
        import psycopg
    except ImportError:
        print("Install the postgres extra before running this command")
        return 1
    from data_pipeline.core.errors import ConfigError, FetchError
    from data_pipeline.postgres_connection import (
        connect_postgres,
        grant_postgres_roles,
        postgres_environment,
    )
    from data_pipeline.postgres_market import (
        BatchError,
        check_version,
        collect_market,
        init_postgres,
        publish_market,
    )

    try:
        environment = postgres_environment(
            args.env_file or (Path(__file__).resolve().parents[1] / ".env")
        )
        if args.action == "ingest" and not environment.get("TUSHARE_TOKEN"):
            print("Configure TUSHARE_TOKEN for Tushare ingestion")
            return 1
        role = {
            "init": "ADMIN",
            "init-nav": "ADMIN",
            "ingest": "WRITER",
            "publish-nav": "WRITER",
        }.get(args.action, "READER")
        with connect_postgres(role, environment) as connection:
            if args.action == "init":
                with connection.transaction():
                    init_postgres(connection)
                    grant_postgres_roles(connection, environment=environment)
                print("PostgreSQL market schema ready")
            elif args.action == "init-nav":
                from data_pipeline.postgres_nav import init_nav

                with connection.transaction():
                    init_nav(connection)
                    grant_postgres_roles(connection, nav=True, environment=environment)
                print("PostgreSQL NAV schema ready")
            elif args.action == "check":
                check_version(connection)
                print("PostgreSQL market schema verified")
            elif args.action == "ingest":
                from data_pipeline.sources.tushare_src import TushareSource

                check_version(connection)
                # Source errors can contain provider text. Keep those out of operator output.
                logging.getLogger("data_pipeline.tushare").disabled = True
                batch = collect_market(
                    TushareSource(token=environment["TUSHARE_TOKEN"]),
                    args.start,
                    args.end,
                )
                version, counts = publish_market(connection, batch)
                print(json.dumps({"publication_version": version, "inserted": counts}))
            elif args.action == "publish-nav":
                from data_pipeline.postgres_nav import publish_nav

                revision, rows, changed = publish_nav(
                    connection, args.duckdb, args.run_id, args.input_version
                )
                print(
                    json.dumps(
                        {
                            "run_id": args.run_id,
                            "revision": revision,
                            "rows": rows,
                            "inserted": changed,
                        }
                    )
                )
            elif args.action == "export-nav":
                from data_pipeline.postgres_nav import NAV_COLUMNS, read_nav

                output = args.output.resolve()
                input_version, rows = read_nav(connection, args.run_id, args.revision)
                with TemporaryDirectory(
                    prefix="nav-export-", dir=output.parent
                ) as temporary:
                    staging = Path(temporary) / "nav.csv"
                    with staging.open("w", newline="", encoding="utf-8") as stream:
                        writer = csv.writer(stream)
                        writer.writerow(NAV_COLUMNS)
                        writer.writerows(rows)
                    if os.name == "nt":
                        staging.rename(
                            output
                        )  # Windows refuses to replace an existing path.
                    else:
                        os.link(staging, output)
                print(
                    json.dumps(
                        {
                            "run_id": args.run_id,
                            "revision": args.revision,
                            "input_version": input_version,
                            "rows": len(rows),
                        }
                    )
                )
            else:
                from data_pipeline.postgres_research import export_research

                manifest = export_research(
                    connection,
                    args.output.resolve(),
                    start=args.start,
                    end=args.end,
                    codes=args.code,
                    version=args.version,
                )
                print(json.dumps(manifest))
    except BatchError as error:
        print(str(error))
        return 1
    except ConfigError as error:
        print(str(error))
        return 1
    except FetchError:
        print(
            "Tushare request failed; check provider authentication, permissions and availability"
        )
        return 1
    except (psycopg.Error, duckdb.Error, OSError, ValueError) as error:
        print(
            f"PostgreSQL operation failed ({getattr(error, 'sqlstate', None) or type(error).__name__})"
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
