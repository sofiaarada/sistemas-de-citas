from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator

import mysql.connector

from config import settings


@contextmanager
def get_cursor(dictionary: bool = False) -> Generator[tuple[Any, Any], None, None]:
    connection = mysql.connector.connect(**settings.mysql_config())
    cursor = connection.cursor(dictionary=dictionary)

    try:
        yield connection, cursor
    finally:
        cursor.close()
        connection.close()


def fetch_one(query: str, params: tuple[Any, ...] = (), dictionary: bool = False) -> Any:
    with get_cursor(dictionary=dictionary) as (_, cursor):
        cursor.execute(query, params)
        return cursor.fetchone()


def fetch_all(query: str, params: tuple[Any, ...] = (), dictionary: bool = False) -> list[Any]:
    with get_cursor(dictionary=dictionary) as (_, cursor):
        cursor.execute(query, params)
        return cursor.fetchall()


def execute(query: str, params: tuple[Any, ...] = ()) -> int:
    with get_cursor(dictionary=False) as (connection, cursor):
        cursor.execute(query, params)
        connection.commit()
        return cursor.rowcount