"""Criterios de auditoria, sempre vinculados a um cliente."""
from datetime import datetime

from ..extensions import db


def _lista(valor: str):
    if not valor:
        return []
    bruto = valor.replace("\n", ",").replace(";", ",")
    return [item.strip() for item in bruto.split(",") if item.strip()]


class Criterio(db.Model):
    __tablename__ = "criterios"

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(
        db.Integer,
        db.ForeignKey("clientes.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    nome = db.Column(db.String(160), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    obrigatorio = db.Column(db.Boolean, nullable=False, default=False)
    peso = db.Column(db.Float, nullable=False, default=1.0)

    # Regras configuraveis usadas pelo motor de avaliacao
    termos_esperados = db.Column(db.Text, nullable=True)
    termos_proibidos = db.Column(db.Text, nullable=True)
    termos_contexto = db.Column(db.Text, nullable=True)
    minimo_termos = db.Column(db.Integer, nullable=False, default=1)
    permite_nao_aplicavel = db.Column(db.Boolean, nullable=False, default=False)

    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, nullable=True, onupdate=datetime.now)

    cliente = db.relationship("Cliente", back_populates="criterios")
    resultados = db.relationship("ResultadoCriterio", back_populates="criterio")

    __table_args__ = (
        db.UniqueConstraint("cliente_id", "nome", name="uq_criterio_cliente_nome"),
        db.CheckConstraint("peso > 0", name="ck_criterio_peso_positivo"),
        db.CheckConstraint("minimo_termos >= 1", name="ck_criterio_minimo_termos"),
    )

    @property
    def lista_esperados(self):
        return _lista(self.termos_esperados)

    @property
    def lista_proibidos(self):
        return _lista(self.termos_proibidos)

    @property
    def lista_contexto(self):
        return _lista(self.termos_contexto)

    @property
    def utilizado_em_auditorias(self) -> bool:
        return bool(self.resultados)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Criterio {self.nome} cliente={self.cliente_id}>"
