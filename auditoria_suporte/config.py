"""Configuracao da aplicacao.

A chave secreta nunca fica fixa no codigo: ela e lida de uma variavel de
ambiente ou de um arquivo local gerado automaticamente na primeira execucao.
"""
import os
import secrets
import stat
from pathlib import Path


def obter_chave_secreta(instance_dir: Path) -> str:
    """Retorna a chave secreta da instalacao local.

    Ordem de precedencia:
    1. variavel de ambiente AUDITORIA_SECRET_KEY;
    2. arquivo instance/secret_key (criado automaticamente, permissao restrita).
    """
    chave_env = os.getenv("AUDITORIA_SECRET_KEY")
    if chave_env:
        return chave_env

    instance_dir = Path(instance_dir)
    instance_dir.mkdir(parents=True, exist_ok=True)
    arquivo = instance_dir / "secret_key"

    if arquivo.exists():
        conteudo = arquivo.read_text(encoding="utf-8").strip()
        if conteudo:
            return conteudo

    chave = secrets.token_hex(32)
    arquivo.write_text(chave, encoding="utf-8")
    try:  # permissoes restritas (ignorado silenciosamente no Windows)
        arquivo.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return chave


class Config:
    BASE_DIR = Path(__file__).resolve().parent.parent
    INSTANCE_DIR = BASE_DIR / "instance"
    AUDIT_STORAGE_DIR = BASE_DIR / "auditorias"

    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{(INSTANCE_DIR / 'auditoria.db').as_posix()}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Upload de arquivos de importacao (CSV/TXT)
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB
    EXTENSOES_IMPORTACAO = {".csv", ".txt"}

    # Regras de negocio
    NOTA_MINIMA_PADRAO = 70.0
    TAMANHO_MINIMO_CONTEUDO = 120  # abaixo disso a avaliacao vira inconclusiva

    # Sessao
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8  # 8 horas

    SISTEMA_NOME = "Auditoria Automatizada de Atendimentos"
