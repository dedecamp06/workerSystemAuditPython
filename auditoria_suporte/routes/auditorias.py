"""Execucao das auditorias."""
from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from ..extensions import db
from ..models import Atendimento, Auditoria, Cliente, STATUS_CRITERIO
from ..seguranca import login_required
from ..services import auditoria_service
from ..services.armazenamento_service import ErroArmazenamento
from ..services.auditoria_service import ErroAuditoria

bp = Blueprint("auditorias", __name__, url_prefix="/auditorias")


@bp.get("/")
@login_required
def selecionar():
    cliente_id = request.args.get("cliente_id", type=int)
    exibir = request.args.get("exibir") or "pendentes"
    busca = (request.args.get("busca") or "").strip()
    pagina = request.args.get("pagina", type=int, default=1)

    consulta = db.select(Atendimento)
    existe_auditoria = db.exists().where(Auditoria.atendimento_id == Atendimento.id)
    if exibir == "pendentes":
        consulta = consulta.where(~existe_auditoria)
    elif exibir == "auditados":
        consulta = consulta.where(existe_auditoria)
    if cliente_id:
        consulta = consulta.where(Atendimento.cliente_id == cliente_id)
    if busca:
        padrao = f"%{busca}%"
        consulta = consulta.where(
            db.or_(Atendimento.protocolo.ilike(padrao), Atendimento.atendente.ilike(padrao))
        )

    paginacao = db.paginate(
        consulta.order_by(Atendimento.data_atendimento.desc(), Atendimento.id.desc()),
        page=pagina,
        per_page=15,
        error_out=False,
    )

    return render_template(
        "auditorias/selecionar.html",
        paginacao=paginacao,
        atendimentos=paginacao.items,
        clientes=db.session.scalars(db.select(Cliente).order_by(Cliente.nome)).all(),
        cliente_id=cliente_id,
        exibir=exibir,
        busca=busca,
    )


@bp.route("/executar/<int:atendimento_id>", methods=["GET", "POST"])
@login_required
def executar(atendimento_id):
    atendimento = db.get_or_404(Atendimento, atendimento_id)
    reauditar = (request.values.get("reauditar") or "") == "1"

    # Evita auditorias duplicadas acidentais: a reauditoria e explicita.
    if atendimento.auditado and not reauditar:
        return render_template(
            "auditorias/confirmar_reauditoria.html",
            atendimento=atendimento,
            auditoria=atendimento.auditoria_atual,
        )

    try:
        avaliacoes = auditoria_service.preparar_avaliacao(atendimento)
    except ErroAuditoria as erro:
        flash(str(erro), "erro")
        return redirect(url_for("atendimentos.detalhe", atendimento_id=atendimento.id))

    criterios_por_id = {c.id: c for c in atendimento.cliente.criterios}
    erros = []
    observacoes = ""

    if request.method == "POST":
        observacoes = request.form.get("observacoes") or ""
        avaliacoes, erros, houve_ajuste = auditoria_service.aplicar_ajustes(
            avaliacoes, request.form, criterios_por_id
        )
        if not erros:
            try:
                auditoria = auditoria_service.registrar_auditoria(
                    atendimento,
                    g.usuario,
                    avaliacoes,
                    observacoes=observacoes,
                    ajustada_manualmente=houve_ajuste,
                    metodo="regras_v1_revisada" if houve_ajuste else None,
                )
            except ErroArmazenamento as erro:
                flash(
                    "A auditoria NAO foi registrada porque o resultado nao pode ser "
                    f"gravado em disco: {erro}",
                    "erro",
                )
                return redirect(url_for("atendimentos.detalhe", atendimento_id=atendimento.id))
            except ErroAuditoria as erro:
                flash(str(erro), "erro")
                return redirect(url_for("atendimentos.detalhe", atendimento_id=atendimento.id))

            arquivos = ", ".join(a.caminho_relativo for a in auditoria.arquivos)
            flash(
                f"Auditoria #{auditoria.id} registrada ({auditoria.rotulo_situacao}, "
                f"{auditoria.pontuacao_formatada}). Arquivos gravados: {arquivos}",
                "sucesso",
            )
            return redirect(url_for("resultados.detalhe", auditoria_id=auditoria.id))

        for mensagem in erros:
            flash(mensagem, "erro")

    consolidado = auditoria_service.consolidar(avaliacoes, atendimento.cliente.nota_minima)

    return render_template(
        "auditorias/executar.html",
        atendimento=atendimento,
        avaliacoes=avaliacoes,
        criterios_por_id=criterios_por_id,
        consolidado=consolidado,
        status_disponiveis=STATUS_CRITERIO,
        reauditar=reauditar or atendimento.auditado,
        observacoes=observacoes,
        erros=erros,
    )
