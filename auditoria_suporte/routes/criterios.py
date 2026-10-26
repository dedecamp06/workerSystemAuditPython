"""Cadastro e configuracao dos criterios de auditoria por cliente."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..extensions import db
from ..models import Cliente, Criterio
from ..seguranca import login_required
from ..services import criterio_service

bp = Blueprint("criterios", __name__, url_prefix="/criterios")


def _clientes():
    return db.session.scalars(db.select(Cliente).order_by(Cliente.nome)).all()


@bp.get("/")
@login_required
def listar():
    cliente_id = request.args.get("cliente_id", type=int)
    somente_ativos = request.args.get("ativos", "0") == "1"

    consulta = db.select(Criterio)
    if cliente_id:
        consulta = consulta.where(Criterio.cliente_id == cliente_id)
    if somente_ativos:
        consulta = consulta.where(Criterio.ativo.is_(True))

    criterios = db.session.scalars(
        consulta.join(Cliente).order_by(Cliente.nome, Criterio.nome)
    ).all()

    return render_template(
        "criterios/listar.html",
        criterios=criterios,
        clientes=_clientes(),
        cliente_id=cliente_id,
        somente_ativos=somente_ativos,
    )


@bp.route("/novo", methods=["GET", "POST"])
@login_required
def novo():
    erros = []
    dados = {
        "cliente_id": request.args.get("cliente_id", type=int) or "",
        "peso": 1,
        "minimo_termos": 1,
        "ativo": "1",
    }
    if request.method == "POST":
        dados = request.form.to_dict()
        cliente = db.session.get(Cliente, request.form.get("cliente_id", type=int) or 0)
        if cliente is None:
            erros.append("Selecione um cliente valido para o criterio.")
        else:
            try:
                criterio = criterio_service.criar_criterio(cliente, dados)
                flash(
                    f"Criterio '{criterio.nome}' cadastrado para o cliente {cliente.nome}.",
                    "sucesso",
                )
                return redirect(url_for("criterios.listar", cliente_id=cliente.id))
            except ValueError as erro:
                db.session.rollback()
                erros = erro.args[0] if isinstance(erro.args[0], list) else [str(erro)]
    return render_template(
        "criterios/form.html", criterio=None, dados=dados, erros=erros, clientes=_clientes()
    )


@bp.route("/<int:criterio_id>/editar", methods=["GET", "POST"])
@login_required
def editar(criterio_id):
    criterio = db.get_or_404(Criterio, criterio_id)
    erros = []
    dados = {
        "cliente_id": criterio.cliente_id,
        "nome": criterio.nome,
        "descricao": criterio.descricao,
        "peso": criterio.peso,
        "obrigatorio": "1" if criterio.obrigatorio else "",
        "permite_nao_aplicavel": "1" if criterio.permite_nao_aplicavel else "",
        "ativo": "1" if criterio.ativo else "",
        "termos_esperados": criterio.termos_esperados,
        "termos_proibidos": criterio.termos_proibidos,
        "termos_contexto": criterio.termos_contexto,
        "minimo_termos": criterio.minimo_termos,
    }
    if request.method == "POST":
        dados = request.form.to_dict()
        dados["cliente_id"] = criterio.cliente_id  # o vinculo do criterio nao muda
        try:
            criterio_service.atualizar_criterio(criterio, dados)
            flash("Criterio atualizado com sucesso.", "sucesso")
            return redirect(url_for("criterios.listar", cliente_id=criterio.cliente_id))
        except ValueError as erro:
            db.session.rollback()
            erros = erro.args[0] if isinstance(erro.args[0], list) else [str(erro)]
    return render_template(
        "criterios/form.html",
        criterio=criterio,
        dados=dados,
        erros=erros,
        clientes=_clientes(),
    )


@bp.post("/<int:criterio_id>/excluir")
@login_required
def excluir(criterio_id):
    criterio = db.get_or_404(Criterio, criterio_id)
    cliente_id = criterio.cliente_id
    nome = criterio.nome
    acao = criterio_service.excluir_ou_desativar(criterio)
    if acao == "desativado":
        flash(
            f"O criterio '{nome}' ja foi utilizado em auditorias e foi desativado "
            "para preservar o historico.",
            "aviso",
        )
    else:
        flash(f"Criterio '{nome}' excluido.", "sucesso")
    return redirect(url_for("criterios.listar", cliente_id=cliente_id))


@bp.post("/<int:criterio_id>/alternar")
@login_required
def alternar(criterio_id):
    criterio = db.get_or_404(Criterio, criterio_id)
    criterio.ativo = not criterio.ativo
    db.session.commit()
    estado = "ativado" if criterio.ativo else "desativado"
    flash(f"Criterio '{criterio.nome}' {estado}.", "sucesso")
    return redirect(url_for("criterios.listar", cliente_id=criterio.cliente_id))
