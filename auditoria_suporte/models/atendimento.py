"""Atendimentos de suporte submetidos a auditoria."""
from datetime import datetime

from ..extensions import db

ORIGENS = ("manual", "importacao_csv", "importacao_txt")


class Atendimento(db.Model):
    __tablename__ = "atendimentos"

    id = db.Column(db.Integer, primary_key=True)
    cliente_id = db.Column(
        db.Integer,
        db.ForeignKey("clientes.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    protocolo = db.Column(db.String(60), nullable=False, index=True)
    atendente = db.Column(db.String(120), nullable=False)
    data_atendimento = db.Column(db.Date, nullable=False)
    canal = db.Column(db.String(40), nullable=True)
    conteudo = db.Column(db.Text, nullable=False)
    origem = db.Column(db.String(20), nullable=False, default="manual")
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)
    atualizado_em = db.Column(db.DateTime, nullable=True, onupdate=datetime.now)

    cliente = db.relationship("Cliente", back_populates="atendimentos")
    auditorias = db.relationship(
        "Auditoria",
        back_populates="atendimento",
        order_by="Auditoria.versao",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        db.UniqueConstraint("cliente_id", "protocolo", name="uq_atendimento_cliente_protocolo"),
    )

    @property
    def pasta(self) -> str:
        """Nome de pasta seguro e unico do atendimento."""
        return f"atendimento_{self.id}"

    @property
    def auditado(self) -> bool:
        return bool(self.auditorias)

    @property
    def auditoria_atual(self):
        """Ultima auditoria executada (maior versao)."""
        if not self.auditorias:
            return None
        return max(self.auditorias, key=lambda a: (a.versao, a.id))

    @property
    def resumo_conteudo(self) -> str:
        texto = " ".join((self.conteudo or "").split())
        return texto[:160] + ("..." if len(texto) > 160 else "")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Atendimento {self.protocolo}>"
