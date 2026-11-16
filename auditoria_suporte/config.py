"""Configuracao da aplicacao.

A chave secreta nunca fica fixa no codigo: ela e lida de uma variavel de
ambiente ou de um arquivo local gerado automaticamente na primeira execucao.

Execucao local: banco SQLite em ``instance/auditoria.db``.
Execucao na nuvem (Vercel): banco Postgres informado em ``DATABASE_URL``
e chave secreta em ``AUDITORIA_SECRET_KEY``.
"""
import os
import secrets
import stat
from pathlib import Path


# Na Vercel (e em outros ambientes serverless) o disco e somente leitura.
EM_SERVERLESS = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))


def normalizar_url_banco(url: str) -> str:
    """Ajusta URLs ``postgres://`` (Neon, Heroku) para o driver psycopg 3."""
    url = (url or "").strip()
    for prefixo in ("postgres://", "postgresql://"):
        if url.startswith(prefixo):
            return "postgresql+psycopg://" + url[len(prefixo):]
    return url


def obter_chave_secreta(instance_dir: Path) -> str:
    """Retorna a chave secreta da instalacao local.

    Ordem de precedencia:
    1. variavel de ambiente AUDITORIA_SECRET_KEY;
    2. arquivo instance/secret_key (criado automaticamente, permissao restrita).
    """
    chave_env = os.getenv("AUDITORIA_SECRET_KEY")
    if chave_env:
        return chave_env

    if EM_SERVERLESS:
        raise RuntimeError(
            "Configure a variavel de ambiente AUDITORIA_SECRET_KEY no painel da "
            "hospedagem (Settings > Environment Variables)."
        )

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
    # Pasta usada pela versao antiga, que gravava os resultados em disco.
    # Lida apenas uma vez, para copiar os arquivos antigos para o banco.
    PASTA_LEGADA_AUDITORIAS = BASE_DIR / "auditorias"

    SQLALCHEMY_DATABASE_URI = normalizar_url_banco(
        os.getenv("DATABASE_URL")
        or os.getenv("POSTGRES_URL")
        or f"sqlite:///{(INSTANCE_DIR / 'auditoria.db').as_posix()}"
    )
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Upload de arquivos de importacao (CSV/TXT).
    # A Vercel recusa requisicoes acima de 4,5 MB.
    MAX_CONTENT_LENGTH = 4 * 1024 * 1024  # 4 MB
    EXTENSOES_IMPORTACAO = {".csv", ".txt"}

    # Regras de negocio
    NOTA_MINIMA_PADRAO = 70.0
    TAMANHO_MINIMO_CONTEUDO = 120  # abaixo disso a avaliacao vira inconclusiva

    # Sessao
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8  # 8 horas

    # Marca exibida nas telas. Pode ser trocada sem mexer no codigo.
    SISTEMA_NOME = os.getenv("SISTEMA_NOME", "Auris")
    SISTEMA_SLOGAN = os.getenv("SISTEMA_SLOGAN", "Auditoria Automatizada de Atendimentos")
