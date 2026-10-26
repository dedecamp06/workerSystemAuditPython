"""Cadastro e autenticacao de usuarios."""
from datetime import datetime

from sqlalchemy import func, or_

from ..extensions import db
from ..models.usuario import PERFIS, Usuario
from .utilitarios import email_valido, texto_limpo

TAMANHO_MINIMO_SENHA = 8


class ErroValidacao(Exception):
    """Erro de validacao com lista de mensagens amigaveis."""

    def __init__(self, erros):
        self.erros = erros if isinstance(erros, list) else [erros]
        super().__init__("; ".join(self.erros))


def criar_usuario(nome, usuario, email, senha, perfil="auditor", ativo=True) -> Usuario:
    nome = texto_limpo(nome, 120)
    usuario = texto_limpo(usuario, 60).lower()
    email = texto_limpo(email, 160).lower()
    erros = []

    if not nome:
        erros.append("Informe o nome do usuario.")
    if not usuario:
        erros.append("Informe o nome de acesso (login).")
    elif len(usuario) < 3:
        erros.append("O login deve ter ao menos 3 caracteres.")
    if not email_valido(email):
        erros.append("Informe um e-mail valido.")
    if not senha or len(senha) < TAMANHO_MINIMO_SENHA:
        erros.append(f"A senha deve ter ao menos {TAMANHO_MINIMO_SENHA} caracteres.")
    if perfil not in PERFIS:
        erros.append("Perfil invalido.")

    if usuario and db.session.scalar(
        db.select(Usuario).where(func.lower(Usuario.usuario) == usuario)
    ):
        erros.append("Ja existe um usuario com esse login.")
    if email and db.session.scalar(
        db.select(Usuario).where(func.lower(Usuario.email) == email)
    ):
        erros.append("Ja existe um usuario com esse e-mail.")

    if erros:
        raise ErroValidacao(erros)

    novo = Usuario(nome=nome, usuario=usuario, email=email, perfil=perfil, ativo=ativo)
    novo.definir_senha(senha)
    db.session.add(novo)
    db.session.commit()
    return novo


def autenticar(identificador: str, senha: str):
    """Retorna o usuario autenticado ou ``None``.

    Aceita login ou e-mail. Nao informa qual dos dois campos falhou.
    """
    identificador = texto_limpo(identificador, 160).lower()
    if not identificador or not senha:
        return None

    usuario = db.session.scalar(
        db.select(Usuario).where(
            or_(
                func.lower(Usuario.usuario) == identificador,
                func.lower(Usuario.email) == identificador,
            )
        )
    )
    if usuario is None or not usuario.ativo:
        return None
    if not usuario.verificar_senha(senha):
        return None

    usuario.ultimo_acesso = datetime.now()
    db.session.commit()
    return usuario


def alterar_senha(usuario: Usuario, senha_atual: str, nova_senha: str) -> None:
    erros = []
    if not usuario.verificar_senha(senha_atual):
        erros.append("A senha atual esta incorreta.")
    if not nova_senha or len(nova_senha) < TAMANHO_MINIMO_SENHA:
        erros.append(f"A nova senha deve ter ao menos {TAMANHO_MINIMO_SENHA} caracteres.")
    if erros:
        raise ErroValidacao(erros)
    usuario.definir_senha(nova_senha)
    db.session.commit()


def existe_administrador() -> bool:
    return bool(
        db.session.scalar(db.select(Usuario).where(Usuario.perfil == "admin", Usuario.ativo.is_(True)))
    )
