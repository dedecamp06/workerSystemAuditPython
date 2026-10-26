"""Rotas de autenticacao."""
from flask import (
    Blueprint,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from ..seguranca import gerar_token_csrf, login_required
from ..services.autenticacao_service import ErroValidacao, alterar_senha, autenticar

bp = Blueprint("auth", __name__)


def _destino_seguro(destino: str) -> str:
    """Evita redirecionamento para fora da aplicacao."""
    if destino and destino.startswith("/") and not destino.startswith("//"):
        return destino
    return url_for("dashboard.index")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if getattr(g, "usuario", None) is not None:
        return redirect(url_for("dashboard.index"))

    erros = []
    identificador = ""
    if request.method == "POST":
        identificador = (request.form.get("identificador") or "").strip()
        senha = request.form.get("senha") or ""

        if not identificador:
            erros.append("Informe o usuario ou e-mail.")
        if not senha:
            erros.append("Informe a senha.")

        if not erros:
            usuario = autenticar(identificador, senha)
            if usuario is None:
                erros.append("Usuario ou senha invalidos.")
            else:
                session.clear()
                session["usuario_id"] = usuario.id
                session.permanent = True
                gerar_token_csrf()
                flash(f"Bem-vindo(a), {usuario.nome}!", "sucesso")
                return redirect(_destino_seguro(request.form.get("next", "")))

    return render_template("login.html", erros=erros, identificador=identificador), (
        200 if request.method == "GET" else 401
    )


@bp.post("/logout")
@login_required
def logout():
    session.clear()
    flash("Sessao encerrada.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/perfil", methods=["GET", "POST"])
@login_required
def perfil():
    erros = []
    if request.method == "POST":
        try:
            alterar_senha(
                g.usuario,
                request.form.get("senha_atual") or "",
                request.form.get("nova_senha") or "",
            )
            flash("Senha alterada com sucesso.", "sucesso")
            return redirect(url_for("auth.perfil"))
        except ErroValidacao as erro:
            erros = erro.erros
    return render_template("perfil.html", erros=erros)
