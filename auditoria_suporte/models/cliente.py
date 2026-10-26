"""Clientes auditados."""
from datetime import datetime

from ..extensions import db


class Cliente(db.Model):
    __tablename__ = "clientes"

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(40), nullable=False, unique=True, index=True)
    nome = db.Column(db.String(160), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    contato = db.Column(db.String(120), nullable=True)
    email = db.Column(db.String(160), nullable=True)
    nota_minima = db.Column(db.Float, nullable=False, default=70.0)
    pasta = db.Column(db.String(160), nullable=True, unique=True)
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, nullable=True, onupdate=datetime.now)

    atendimentos = db.relationship(
        "Atendimento", back_populates="cliente", order_by="Atendimento.id"
    )
    criterios = db.relationship(
        "Criterio", back_populates="cliente", order_by="Criterio.nome"
    )
    auditorias = db.relationship("Auditoria", back_populates="cliente")

    __table_args__ = (
        db.CheckConstraint("nota_minima >= 0 and nota_minima <= 100", name="ck_cliente_nota"),
    )

    @property
    def criterios_ativos(self):
        return [c for c in self.criterios if c.ativo]

    @property
    def possui_vinculos(self) -> bool:
        return bool(self.atendimentos or self.criterios or self.auditorias)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Cliente {self.codigo}>"
