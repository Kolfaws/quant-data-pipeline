"""Connection settings and role grants for the shared QuantData database."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from quant_schema.postgres_backtest_ddl import BACKTEST_NAV, BACKTEST_RUN
from quant_schema.postgres_ddl import (
    DATASETS,
    FACTOR_DEFINITION,
    FACTOR_VALUE,
    INSTRUMENT,
    PUBLICATION,
)

from data_pipeline.core.errors import ConfigError
from data_pipeline.environment import dotenv_values


def postgres_environment(path: Path) -> dict[str, str]:
    selected = dotenv_values(path)
    link = os.getenv("QUANTDATA_POSTGRES_ENV") or selected.get("QUANTDATA_POSTGRES_ENV")
    defaults = {}
    if link:
        shared = path.resolve().parent / link
        if not shared.is_file():
            raise ConfigError("Shared QuantData environment file is unavailable")
        defaults = dotenv_values(shared)
    return defaults | selected | dict(os.environ)


def connect_postgres(
    role: str, environment: Mapping[str, str] = os.environ
) -> psycopg.Connection[Any]:
    dsn = environment.get("QUANTDATA_POSTGRES_DSN")
    if dsn:
        return psycopg.connect(dsn, autocommit=True, connect_timeout=5)
    address = environment.get("POSTGRE_IP", "").strip()
    user = environment.get(f"{role}_NAME")
    password = environment.get(f"{role}_PASSWORD")
    if not address or not user or not password:
        raise ConfigError(f"Configure POSTGRE_IP and {role} credentials for QuantData")
    endpoint = re.fullmatch(r"(?:\[([^]]+)\]|([^:]+))(?::([0-9]+))?", address)
    if not endpoint:
        raise ConfigError("POSTGRE_IP must use host[:port] or [IPv6]:port syntax")
    return psycopg.connect(
        host=endpoint[1] or endpoint[2],
        port=endpoint[3] or "5432",
        dbname=environment.get("POSTGRE_DB") or "quantdata",
        user=user,
        password=password,
        autocommit=True,
        connect_timeout=5,
    )


def grant_postgres_roles(
    connection: psycopg.Connection[Any],
    *,
    nav: bool = False,
    environment: Mapping[str, str] = os.environ,
) -> None:
    """Grant only the named pipeline roles access to owned relations."""
    if environment.get("QUANTDATA_POSTGRES_DSN"):
        return  # The DSN can identify an independently provisioned role.
    reader, writer = environment.get("READER_NAME"), environment.get("WRITER_NAME")
    if not reader or not writer:
        raise ConfigError(
            "Configure reader and writer names before initializing QuantData"
        )
    users = sql.SQL(", ").join(
        sql.Identifier(name) for name in dict.fromkeys((reader, writer))
    )
    market = (
        INSTRUMENT,
        PUBLICATION,
        FACTOR_DEFINITION,
        FACTOR_VALUE,
        *(dataset.table for dataset in DATASETS),
    )
    tables = (BACKTEST_RUN, BACKTEST_NAV) if nav else market
    schemas = sorted({table.split(".")[0] for table in tables})
    table_list = sql.SQL(", ").join(
        sql.Identifier(*table.split(".")) for table in tables
    )
    schema_list = sql.SQL(", ").join(sql.Identifier(schema) for schema in schemas)
    owner = sql.Identifier(writer)
    with connection.transaction():
        connection.execute(
            sql.SQL("GRANT USAGE ON SCHEMA {} TO {}").format(schema_list, users)
        )
        connection.execute(
            sql.SQL("GRANT SELECT ON {} TO {}").format(table_list, users)
        )
        connection.execute(sql.SQL("GRANT USAGE ON SCHEMA control TO {}").format(users))
        connection.execute(
            sql.SQL("GRANT SELECT ON control.schema_version TO {}").format(users)
        )
        if nav:
            connection.execute(
                sql.SQL("GRANT INSERT ON {} TO {}").format(table_list, owner)
            )
        else:
            market_writes = (
                INSTRUMENT,
                PUBLICATION,
                *(dataset.table for dataset in DATASETS),
            )
            write_tables = sql.SQL(", ").join(
                sql.Identifier(*table.split(".")) for table in market_writes
            )
            connection.execute(
                sql.SQL("GRANT INSERT ON {} TO {}").format(write_tables, owner)
            )
            connection.execute(
                sql.SQL("GRANT UPDATE (counts) ON control.publication TO {}").format(
                    owner
                )
            )
