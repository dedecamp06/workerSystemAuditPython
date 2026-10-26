"""Cadastro e consulta de clientes."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..extensions import db
from ..models import Atendimento, Auditoria, Cliente, Criterio
from ..seguranca import login_required
from ..services import cliente_service
from ..services.armazenamento_service import contar_arquivos_cliente

bp = Blueprint("clientes", __name__, url_prefix="/clientes")


@bp.get("/")
@login_required
def listar():
    busca = (request.args.get("busca") or "").strip()
    situacao = request.args.get("situacao") or "todos"

    consulta = db.select(Cliente)
    if busca:
        padrao = f"%{busca}%"
        consulta = consulta.where(
            db.or_(Cliente.nome.ilike(padrao), Cliente.codigo.ilike(padrao))
        )
    if situacao == "ativos":
        consulta = consulta.where(Cliente.ativo.is_(True))
    elif situacao == "inativos":
        consulta = consulta.where(Cliente.ativo.is_(False))

    clientes = db.session.scalars(consulta.order_by(Cliente.nome)).all()
    return render_template(
        "clientes/listar.html", clientes=clientes, busca=busca, situacao=situacao
    )


@bp.route("/novo", methods=["GET", "POST"])
@login_required
def novo():
    erros = []
    dados = {"nota_minima": 70}
    if request.method == "POST":
        dados = request.form.to_dict()
        try:
            cliente = cliente_service.criar_cliente(dados)
            flash(f"Cliente '{cliente.nome}' cadastrado com sucesso.", "sucesso")
            return redirect(url_for("clientes.detalhe", cliente_id=cliente.id))
        except ValueError as erro:
            db.session.rollback()
            erros = erro.args[0] if isinstance(erro.args[0], list) else [str(erro)]
    return render_template("clientes/form.html", cliente=None, dados=dados, erros=erros)


@bp.get("/<int:cliente_id>")
@login_required
def detalhe(cliente_id):
    cliente = db.get_or_404(Cliente, cliente_id)
    total_atendimentos = (
        db.session.scalar(
            db.select(db.func.count(Atendimento.id)).where(Atendimento.cliente_id == cliente.id)
        )
        or 0
    )
    total_auditorias = (
        db.session.scalar(
            db.select(db.func.count(Auditoria.id)).where(Auditoria.cliente_id == cliente.id)
        )
        or 0
    )
    total_criterios = (
        db.session.scalar(
            db.select(db.func.count(Criterio.id)).where(
                Criterio.cliente_id == cliente.id, Criterio.ativo.is_(True)
            )
        )
        or 0
    )
    pendentes = (
        db.session.scalar(
            db.select(db.func.count(Atendimento.id)).where(
                Atendimento.cliente_id == cliente.id,
                ~db.exists().where(Auditoria.atendimento_id == Atendimento.id),
            )
        )
        or 0
    )
    ultimas = db.session.scalars(
        db.select(Auditoria)
        .where(Auditoria.cliente_id == cliente.id)
        .order_by(Auditoria.executada_em.desc())
        .limit(5)
    ).all()

    return render_template(
        "clientes/detalhe.html",
        cliente=cliente,
        total_atendimentos=total_atendimentos,
        total_auditorias=total_auditorias,
        total_criterios=total_criterios,
        pendentes=pendentes,
        ultimas=ultimas,
        arquivos_armazenados=contar_arquivos_cliente(cliente),
    )


@bp.route("/<int:cliente_id>/editar", methods=["GET", "POST"])
@login_required
def editar(cliente_id):
    cliente = db.get_or_404(Cliente, cliente_id)
    erros = []
    dados = {
        "nome": cliente.nome,
        "codigo": cliente.codigo,
        "descricao": cliente.descricao,
        "contato": cliente.contato,
        "email": cliente.email,
        "nota_minima": cliente.nota_minima,
        "ativo": "1" if cliente.ativo else "0",
    }
    if request.method == "POST":
        dados = request.form.to_dict()
        try:
            cliente_service.atualizar_cliente(cliente, dados)
            flash("Cliente atualizado com sucesso.", "sucesso")
            return redirect(url_for("clientes.detalhe", cliente_id=cliente.id))
        except ValueError as erro:
            db.session.rollback()
            erros = erro.args[0] if isinstance(erro.args[0], list) else [str(erro)]
    return render_template("clientes/form.html", cliente=cliente, dados=dados, erros=erros)


@bp.post("/<int:cliente_id>/excluir")
@login_required
def excluir(cliente_id):
    cliente = db.get_or_404(Cliente, cliente_id)
    nome = cliente.nome
    try:
        acao = cliente_service.excluir_ou_desativar(cliente)
    except Exception:
        db.session.rollback()
        flash(
            f"Nao foi possivel excluir o cliente '{nome}' porque existem registros vinculados.",
            "erro",
        )
        return redirect(url_for("clientes.detalhe", cliente_id=cliente_id))

    if acao == "desativado":
        flash(
            f"O cliente '{nome}' possui registros vinculados e foi desativado "
            "para preservar o historico de auditorias.",
            "aviso",
        )
        return redirect(url_for("clientes.detalhe", cliente_id=cliente_id))

    flash(f"Cliente '{nome}' excluido.", "sucesso")
    return redirect(url_for("clientes.listar"))


@bp.post("/<int:cliente_id>/reativar")
@login_required
def reativar(cliente_id):
    cliente = db.get_or_404(Cliente, cliente_id)
    cliente.ativo = True
    db.session.commit()
    flash(f"Cliente '{cliente.nome}' reativado.", "sucesso")
    return redirect(url_for("clientes.detalhe", cliente_id=cliente.id))
