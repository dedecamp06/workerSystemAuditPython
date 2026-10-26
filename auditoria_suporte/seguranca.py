"""Autenticacao de sessao, protecao CSRF e utilitarios de seguranca."""
import secrets
from functools import wraps

from flask import abort, flash, g, redirect, request, session, url_for

from .extensions import db

METODOS_INSEGUROS = {"POST", "PUT", "PATCH", "DELETE"}
CAMPO_CSRF = "_csrf_token"


def gerar_token_csrf() -> str:
    """Cria (ou reaproveita) o token CSRF da sessao atual."""
    if CAMPO_CSRF not in session:
        session[CAMPO_CSRF] = secrets.token_hex(32)
    return session[CAMPO_CSRF]


def validar_token_csrf() -> bool:
    enviado = request.form.get(CAMPO_CSRF) or request.headers.get("X-CSRF-Token", "")
    atual = session.get(CAMPO_CSRF, "")
    if not enviado or not atual:
        return False
    return secrets.compare_digest(str(enviado), str(atual))


def carregar_usuario_logado():
    """Disponibiliza o usuario autenticado em ``g.usuario``."""
    from .models.usuario import Usuario

    usuario_id = session.get("usuario_id")
    g.usuario = None
    if usuario_id is None:
        return
    usuario = db.session.get(Usuario, usuario_id)
    if usuario is None or not usuario.ativo:
        session.clear()
        return
    g.usuario = usuario


def login_required(view):
    """Bloqueia o acesso de visitantes nao autenticados."""

    @wraps(view)
    def wrapper(*args, **kwargs):
        if getattr(g, "usuario", None) is None:
            flash("Faca login para acessar o sistema.", "aviso")
            return redirect(url_for("auth.login", next=request.full_path))
        return view(*args, **kwargs)

    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if getattr(g, "usuario", None) is None:
            flash("Faca login para acessar o sistema.", "aviso")
            return redirect(url_for("auth.login"))
        if g.usuario.perfil != "admin":
            abort(403)
        return view(*args, **kwargs)

    return wrapper
