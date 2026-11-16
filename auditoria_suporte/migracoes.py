"""Ajustes automaticos de esquema para bancos criados por versoes anteriores.

O ``db.create_all()`` cria tabelas novas, mas nao adiciona colunas em tabelas
que ja existem. Este modulo cobre essa lacuna sem apagar dados.
"""
from pathlib import Path

from sqlalchemy import inspect, text

from .extensions import db


def atualizar_esquema(app) -> None:
    _adicionar_coluna_conteudo()
    _importar_arquivos_legados(Path(app.config["PASTA_LEGADA_AUDITORIAS"]), app.logger)


def _adicionar_coluna_conteudo() -> None:
    """Versao antiga: os resultados ficavam so em disco, sem a coluna ``conteudo``."""
    colunas = {c["name"] for c in inspect(db.engine).get_columns("arquivos_auditoria")}
    if "conteudo" in colunas:
        return
    with db.engine.begin() as conexao:
        conexao.execute(text("ALTER TABLE arquivos_auditoria ADD COLUMN conteudo TEXT"))


def _importar_arquivos_legados(pasta: Path, logger) -> None:
    """Copia para o banco os resultados que a versao antiga gravou em disco."""
    if not pasta.is_dir():
        return

    from .models import ArquivoAuditoria

    pendentes = db.session.scalars(
        db.select(ArquivoAuditoria).where(ArquivoAuditoria.conteudo.is_(None))
    ).all()
    if not pendentes:
        return

    base = pasta.resolve()
    importados = 0
    for arquivo in pendentes:
        destino = (base / arquivo.caminho_relativo).resolve()
        if base not in destino.parents or not destino.is_file():
            continue
        arquivo.conteudo = destino.read_text(encoding="utf-8")
        importados += 1

    if importados:
        db.session.commit()
        logger.info("%s arquivo(s) de resultado copiados do disco para o banco.", importados)
