"""Auditorias executadas, resultados por criterio e arquivos gerados."""
from datetime import datetime

from ..extensions import db

# Situacoes possiveis de uma auditoria
APROVADO = "aprovado"
REPROVADO = "reprovado"
PENDENTE_REVISAO = "pendente_revisao"
EM_REVISAO = "em_revisao"

SITUACOES = {
    APROVADO: "Aprovado",
    REPROVADO: "Reprovado",
    PENDENTE_REVISAO: "Pendente de revisao",
    EM_REVISAO: "Em revisao",
}

# Status possiveis de um criterio dentro de uma auditoria
ATENDIDO = "atendido"
NAO_ATENDIDO = "nao_atendido"
NAO_APLICAVEL = "nao_aplicavel"
INCONCLUSIVO = "inconclusivo"

STATUS_CRITERIO = {
    ATENDIDO: "Atendido",
    NAO_ATENDIDO: "Nao atendido",
    NAO_APLICAVEL: "Nao aplicavel",
    INCONCLUSIVO: "Inconclusivo",
}


class Auditoria(db.Model):
    __tablename__ = "auditorias"

    id = db.Column(db.Integer, primary_key=True)
    atendimento_id = db.Column(
        db.Integer,
        db.ForeignKey("atendimentos.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    cliente_id = db.Column(
        db.Integer,
        db.ForeignKey("clientes.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    usuario_id = db.Column(
        db.Integer, db.ForeignKey("usuarios.id", ondelete="SET NULL"), nullable=True
    )

    versao = db.Column(db.Integer, nullable=False, default=1)
    executada_em = db.Column(db.DateTime, nullable=False, default=datetime.now)
    metodo = db.Column(db.String(40), nullable=False, default="regras_v1")

    soma_pesos = db.Column(db.Float, nullable=False, default=0.0)
    soma_pontos = db.Column(db.Float, nullable=False, default=0.0)
    pontuacao_final = db.Column(db.Float, nullable=True)
    nota_minima_aplicada = db.Column(db.Float, nullable=False, default=70.0)

    situacao = db.Column(db.String(30), nullable=False, default=PENDENTE_REVISAO)
    requer_revisao_humana = db.Column(db.Boolean, nullable=False, default=False)
    ajustada_manualmente = db.Column(db.Boolean, nullable=False, default=False)
    observacoes = db.Column(db.Text, nullable=True)
    resumo_calculo = db.Column(db.Text, nullable=True)

    atendimento = db.relationship("Atendimento", back_populates="auditorias")
    cliente = db.relationship("Cliente", back_populates="auditorias")
    usuario = db.relationship("Usuario", back_populates="auditorias")
    resultados = db.relationship(
        "ResultadoCriterio",
        back_populates="auditoria",
        order_by="ResultadoCriterio.ordem",
        cascade="all, delete-orphan",
    )
    arquivos = db.relationship(
        "ArquivoAuditoria",
        back_populates="auditoria",
        order_by="ArquivoAuditoria.tipo",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        db.UniqueConstraint("atendimento_id", "versao", name="uq_auditoria_atendimento_versao"),
        db.CheckConstraint(
            "situacao in ('aprovado','reprovado','pendente_revisao','em_revisao')",
            name="ck_auditoria_situacao",
        ),
    )

    @property
    def rotulo_situacao(self) -> str:
        return SITUACOES.get(self.situacao, self.situacao)

    @property
    def obrigatorios_nao_atendidos(self):
        return [r for r in self.resultados if r.obrigatorio and r.status == NAO_ATENDIDO]

    @property
    def inconclusivos(self):
        return [r for r in self.resultados if r.status == INCONCLUSIVO]

    @property
    def pontuacao_formatada(self) -> str:
        if self.pontuacao_final is None:
            return "--"
        return f"{self.pontuacao_final:.1f}%"

    def arquivo(self, tipo: str):
        for arq in self.arquivos:
            if arq.tipo == tipo:
                return arq
        return None

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Auditoria {self.id} atendimento={self.atendimento_id} v{self.versao}>"


class ResultadoCriterio(db.Model):
    """Resultado individual de um criterio.

    Os dados do criterio sao copiados (snapshot) para preservar o historico:
    alteracoes futuras no cadastro nao modificam auditorias ja realizadas.
    """

    __tablename__ = "resultados_criterio"

    id = db.Column(db.Integer, primary_key=True)
    auditoria_id = db.Column(
        db.Integer,
        db.ForeignKey("auditorias.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    criterio_id = db.Column(
        db.Integer, db.ForeignKey("criterios.id", ondelete="SET NULL"), nullable=True
    )

    ordem = db.Column(db.Integer, nullable=False, default=0)
    criterio_nome = db.Column(db.String(160), nullable=False)
    criterio_descricao = db.Column(db.Text, nullable=True)
    peso = db.Column(db.Float, nullable=False, default=1.0)
    obrigatorio = db.Column(db.Boolean, nullable=False, default=False)

    status = db.Column(db.String(20), nullable=False, default=INCONCLUSIVO)
    pontuacao = db.Column(db.Float, nullable=False, default=0.0)
    considerado_no_calculo = db.Column(db.Boolean, nullable=False, default=True)
    justificativa = db.Column(db.Text, nullable=True)
    evidencias = db.Column(db.Text, nullable=True)
    confianca = db.Column(db.String(20), nullable=False, default="media")
    ajustado_manualmente = db.Column(db.Boolean, nullable=False, default=False)

    auditoria = db.relationship("Auditoria", back_populates="resultados")
    criterio = db.relationship("Criterio", back_populates="resultados")

    __table_args__ = (
        db.CheckConstraint(
            "status in ('atendido','nao_atendido','nao_aplicavel','inconclusivo')",
            name="ck_resultado_status",
        ),
    )

    @property
    def rotulo_status(self) -> str:
        return STATUS_CRITERIO.get(self.status, self.status)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ResultadoCriterio {self.criterio_nome}={self.status}>"


class ArquivoAuditoria(db.Model):
    """Arquivo de resultado gravado em disco (JSON/TXT)."""

    __tablename__ = "arquivos_auditoria"

    id = db.Column(db.Integer, primary_key=True)
    auditoria_id = db.Column(
        db.Integer,
        db.ForeignKey("auditorias.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tipo = db.Column(db.String(10), nullable=False)
    caminho_relativo = db.Column(db.String(400), nullable=False)
    tamanho_bytes = db.Column(db.Integer, nullable=False, default=0)
    sha256 = db.Column(db.String(64), nullable=True)
    gerado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)

    auditoria = db.relationship("Auditoria", back_populates="arquivos")

    __table_args__ = (
        db.UniqueConstraint("auditoria_id", "tipo", name="uq_arquivo_auditoria_tipo"),
        db.CheckConstraint("tipo in ('json','txt')", name="ck_arquivo_tipo"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ArquivoAuditoria {self.caminho_relativo}>"
