"""Usuarios do sistema."""
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from ..extensions import db

PERFIS = ("admin", "auditor")


class Usuario(db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    usuario = db.Column(db.String(60), nullable=False, unique=True, index=True)
    email = db.Column(db.String(160), nullable=False, unique=True, index=True)
    senha_hash = db.Column(db.String(255), nullable=False)
    perfil = db.Column(db.String(20), nullable=False, default="auditor")
    ativo = db.Column(db.Boolean, nullable=False, default=True)
    criado_em = db.Column(db.DateTime, nullable=False, default=datetime.now)
    ultimo_acesso = db.Column(db.DateTime, nullable=True)

    auditorias = db.relationship("Auditoria", back_populates="usuario")

    __table_args__ = (
        db.CheckConstraint("perfil in ('admin','auditor')", name="ck_usuario_perfil"),
    )

    def definir_senha(self, senha: str) -> None:
        self.senha_hash = generate_password_hash(senha)

    def verificar_senha(self, senha: str) -> bool:
        if not senha or not self.senha_hash:
            return False
        return check_password_hash(self.senha_hash, senha)

    @property
    def rotulo_perfil(self) -> str:
        return "Administrador" if self.perfil == "admin" else "Auditor"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Usuario {self.usuario}>"
