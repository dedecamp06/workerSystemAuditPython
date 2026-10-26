"""Fabrica da aplicacao Flask do sistema de Auditoria Automatizada de Atendimentos."""
from pathlib import Path

from flask import Flask, g, render_template, request

from .cli import registrar_comandos
from .config import Config, obter_chave_secreta
from .extensions import db
from .models import SITUACOES, STATUS_CRITERIO  # noqa: F401 (registra os modelos)
from .routes import BLUEPRINTS
from .seguranca import (
    METODOS_INSEGUROS,
    carregar_usuario_logado,
    gerar_token_csrf,
    validar_token_csrf,
)

CLASSES_SITUACAO = {
    "aprovado": "badge badge-aprovado",
    "reprovado": "badge badge-reprovado",
    "pendente_revisao": "badge badge-revisao",
    "em_revisao": "badge badge-revisao",
}

CLASSES_STATUS = {
    "atendido": "badge badge-aprovado",
    "nao_atendido": "badge badge-reprovado",
    "inconclusivo": "badge badge-revisao",
    "nao_aplicavel": "badge badge-neutro",
}


def create_app(config_override: dict = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if config_override:
        app.config.update(config_override)

    instance_dir = Path(app.config["INSTANCE_DIR"])
    instance_dir.mkdir(parents=True, exist_ok=True)
    Path(app.config["AUDIT_STORAGE_DIR"]).mkdir(parents=True, exist_ok=True)

    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = obter_chave_secreta(instance_dir)

    db.init_app(app)

    for blueprint in BLUEPRINTS:
        app.register_blueprint(blueprint)

    _registrar_ganchos(app)
    _registrar_filtros(app)
    _registrar_erros(app)
    registrar_comandos(app)

    with app.app_context():
        db.create_all()  # cria o banco e as tabelas sem apagar dados existentes

    return app


def _registrar_ganchos(app: Flask) -> None:
    @app.before_request
    def _antes_de_cada_requisicao():
        carregar_usuario_logado()
        if request.endpoint == "static":
            return None
        if request.method in METODOS_INSEGUROS and not validar_token_csrf():
            return (
                render_template(
                    "erro.html",
                    codigo=400,
                    titulo="Sessao expirada ou formulario invalido",
                    mensagem=(
                        "Nao foi possivel validar a origem do formulario (token CSRF). "
                        "Recarregue a pagina e envie novamente."
                    ),
                ),
                400,
            )
        return None

    @app.context_processor
    def _variaveis_globais():
        return {
            "sistema_nome": app.config["SISTEMA_NOME"],
            "usuario_logado": getattr(g, "usuario", None),
            "csrf_token": gerar_token_csrf,
            "situacoes": SITUACOES,
            "status_criterio": STATUS_CRITERIO,
        }


def _registrar_filtros(app: Flask) -> None:
    @app.template_filter("data_br")
    def _data_br(valor):
        return valor.strftime("%d/%m/%Y") if valor else "-"

    @app.template_filter("datahora_br")
    def _datahora_br(valor):
        return valor.strftime("%d/%m/%Y %H:%M") if valor else "-"

    @app.template_filter("classe_situacao")
    def _classe_situacao(valor):
        return CLASSES_SITUACAO.get(valor, "badge badge-neutro")

    @app.template_filter("classe_status")
    def _classe_status(valor):
        return CLASSES_STATUS.get(valor, "badge badge-neutro")

    @app.template_filter("numero")
    def _numero(valor, casas=2):
        if valor is None:
            return "--"
        return f"{float(valor):.{casas}f}".replace(".", ",")


def _registrar_erros(app: Flask) -> None:
    def _pagina(codigo, titulo, mensagem):
        return render_template("erro.html", codigo=codigo, titulo=titulo, mensagem=mensagem), codigo

    @app.errorhandler(403)
    def _403(_erro):
        return _pagina(403, "Acesso negado", "Voce nao tem permissao para acessar este recurso.")

    @app.errorhandler(404)
    def _404(_erro):
        return _pagina(404, "Pagina nao encontrada", "O endereco acessado nao existe no sistema.")

    @app.errorhandler(413)
    def _413(_erro):
        limite = app.config["MAX_CONTENT_LENGTH"] // (1024 * 1024)
        return _pagina(
            413,
            "Arquivo muito grande",
            f"O arquivo enviado excede o limite de {limite} MB.",
        )

    @app.errorhandler(500)
    def _500(erro):  # pragma: no cover - rede de seguranca
        app.logger.exception("Erro interno nao tratado: %s", erro)
        db.session.rollback()
        return _pagina(
            500,
            "Erro interno",
            "Ocorreu um erro inesperado. A operacao foi cancelada e o incidente "
            "foi registrado no log do servidor.",
        )
