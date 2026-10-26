"""Extensoes compartilhadas da aplicacao."""
import sqlite3

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine

db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def _ativar_chaves_estrangeiras(dbapi_connection, connection_record):
    """O SQLite ignora chaves estrangeiras por padrao; aqui elas sao ativadas."""
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
