"""Consulta dos resultados das auditorias e acesso aos arquivos gerados."""
from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from ..extensions import db
from ..models import Atendimento, Auditoria, Cliente, SITUACOES
from ..seguranca import login_required
from ..services.armazenamento_service import ErroArmazenamento, caminho_absoluto

bp = Blueprint("resultados", __name__, url_prefix="/resultados")


@bp.get("/")
@login_required
def listar():
    cliente_id = request.args.get("cliente_id", type=int)
    situacao = request.args.get("situacao") or ""
    busca = (request.args.get("busca") or "").strip()
    pagina = request.args.get("pagina", type=int, default=1)

    consulta = db.select(Auditoria).join(Atendimento, Auditoria.atendimento_id == Atendimento.id)
    if cliente_id:
        consulta = consulta.where(Auditoria.cliente_id == cliente_id)
    if situacao in SITUACOES:
        consulta = consulta.where(Auditoria.situacao == situacao)
    if busca:
        padrao = f"%{busca}%"
        consulta = consulta.where(
            db.or_(Atendimento.protocolo.ilike(padrao), Atendimento.atendente.ilike(padrao))
        )

    paginacao = db.paginate(
        consulta.order_by(Auditoria.executada_em.desc(), Auditoria.id.desc()),
        page=pagina,
        per_page=15,
        error_out=False,
    )

    return render_template(
        "resultados/listar.html",
        paginacao=paginacao,
        auditorias=paginacao.items,
        clientes=db.session.scalars(db.select(Cliente).order_by(Cliente.nome)).all(),
        cliente_id=cliente_id,
        situacao=situacao,
        busca=busca,
        situacoes=SITUACOES,
    )


@bp.get("/<int:auditoria_id>")
@login_required
def detalhe(auditoria_id):
    auditoria = db.get_or_404(Auditoria, auditoria_id)
    historico = db.session.scalars(
        db.select(Auditoria)
        .where(Auditoria.atendimento_id == auditoria.atendimento_id)
        .order_by(Auditoria.versao.desc())
    ).all()
    return render_template(
        "resultados/detalhe.html", auditoria=auditoria, historico=historico
    )


@bp.get("/<int:auditoria_id>/arquivo/<tipo>")
@login_required
def baixar_arquivo(auditoria_id, tipo):
    if tipo not in ("json", "txt"):
        abort(404)

    auditoria = db.get_or_404(Auditoria, auditoria_id)
    arquivo = auditoria.arquivo(tipo)
    if arquivo is None:
        abort(404)

    # O caminho vem do banco e e validado contra a pasta do cliente da auditoria,
    # impedindo acesso a arquivos de outros clientes ou fora do diretorio base.
    pasta_cliente = (auditoria.cliente.pasta or "") + "/"
    if not arquivo.caminho_relativo.startswith(pasta_cliente):
        abort(403)

    try:
        caminho = caminho_absoluto(arquivo)
    except ErroArmazenamento as erro:
        flash(str(erro), "erro")
        return redirect(url_for("resultados.detalhe", auditoria_id=auditoria.id))

    return send_file(
        caminho,
        as_attachment=True,
        download_name=caminho.name,
        mimetype="application/json" if tipo == "json" else "text/plain",
    )
