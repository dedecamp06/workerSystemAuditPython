"""Dashboard com indicadores calculados a partir do banco de dados."""
from flask import Blueprint, render_template

from ..extensions import db
from ..models import (
    APROVADO,
    Atendimento,
    Auditoria,
    Cliente,
    Criterio,
    PENDENTE_REVISAO,
    REPROVADO,
)
from ..seguranca import login_required

bp = Blueprint("dashboard", __name__)


@bp.get("/")
@login_required
def index():
    total_clientes = db.session.scalar(db.select(db.func.count(Cliente.id))) or 0
    clientes_ativos = (
        db.session.scalar(
            db.select(db.func.count(Cliente.id)).where(Cliente.ativo.is_(True))
        )
        or 0
    )
    total_atendimentos = db.session.scalar(db.select(db.func.count(Atendimento.id))) or 0
    total_auditorias = db.session.scalar(db.select(db.func.count(Auditoria.id))) or 0
    total_criterios = (
        db.session.scalar(db.select(db.func.count(Criterio.id)).where(Criterio.ativo.is_(True)))
        or 0
    )

    # Atendimentos sem nenhuma auditoria registrada
    pendentes = (
        db.session.scalar(
            db.select(db.func.count(Atendimento.id)).where(
                ~db.exists().where(Auditoria.atendimento_id == Atendimento.id)
            )
        )
        or 0
    )

    def contar_situacao(situacao):
        return (
            db.session.scalar(
                db.select(db.func.count(Auditoria.id)).where(Auditoria.situacao == situacao)
            )
            or 0
        )

    aprovadas = contar_situacao(APROVADO)
    reprovadas = contar_situacao(REPROVADO)
    em_revisao = contar_situacao(PENDENTE_REVISAO)

    media = db.session.scalar(
        db.select(db.func.avg(Auditoria.pontuacao_final)).where(
            Auditoria.pontuacao_final.isnot(None)
        )
    )

    ultimas = db.session.scalars(
        db.select(Auditoria).order_by(Auditoria.executada_em.desc(), Auditoria.id.desc()).limit(8)
    ).all()

    atendimentos_pendentes = db.session.scalars(
        db.select(Atendimento)
        .where(~db.exists().where(Auditoria.atendimento_id == Atendimento.id))
        .order_by(Atendimento.data_atendimento.desc(), Atendimento.id.desc())
        .limit(8)
    ).all()

    indicadores = {
        "total_clientes": total_clientes,
        "clientes_ativos": clientes_ativos,
        "total_atendimentos": total_atendimentos,
        "total_auditorias": total_auditorias,
        "total_criterios": total_criterios,
        "pendentes": pendentes,
        "aprovadas": aprovadas,
        "reprovadas": reprovadas,
        "em_revisao": em_revisao,
        "media_pontuacao": round(media, 1) if media is not None else None,
    }

    return render_template(
        "dashboard.html",
        indicadores=indicadores,
        ultimas=ultimas,
        atendimentos_pendentes=atendimentos_pendentes,
    )
