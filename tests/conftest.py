"""Configuracao dos testes.

Todos os testes usam um banco SQLite e um diretorio de auditorias temporarios
(``tmp_path``), de modo que os dados reais do usuario nunca sao lidos,
alterados ou apagados.
"""
import re
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from auditoria_suporte import create_app  # noqa: E402
from auditoria_suporte.extensions import db  # noqa: E402
from auditoria_suporte.services import (  # noqa: E402
    atendimento_service,
    autenticacao_service,
    cliente_service,
    criterio_service,
)

SENHA_TESTE = "senha-de-teste-123"

CONTEUDO_BOM = (
    "Atendente: Bom dia, central de suporte, meu nome e Maria. Em que posso ajudar? "
    "Cliente: bom dia, estou sem acesso. Atendente: vou confirmando seus dados, "
    "por favor informe o CPF. Cliente: informado. Atendente: obrigada, o problema foi "
    "resolvido e o protocolo e 12345. Posso ajudar em algo mais?"
)

CONTEUDO_RUIM = (
    "Cliente: preciso de ajuda com a minha conexao de internet que caiu hoje de manha. "
    "Atendente: calma ai, isso nao e problema meu, procura o fabricante do aparelho. "
    "Cliente: mas o equipamento foi fornecido por voces e eu pago mensalmente por isso. "
    "Atendente: ja respondi o que tinha para responder, estou encerrando este contato."
)


@pytest.fixture
def app(tmp_path):
    aplicacao = create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "chave-exclusiva-de-teste",
            "INSTANCE_DIR": tmp_path / "instance",
            "AUDIT_STORAGE_DIR": tmp_path / "auditorias",
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{(tmp_path / 'teste.db').as_posix()}",
        }
    )
    yield aplicacao
    with aplicacao.app_context():
        db.session.remove()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def usuario(app):
    with app.app_context():
        novo = autenticacao_service.criar_usuario(
            "Auditor de Teste", "auditor", "auditor@teste.local", SENHA_TESTE, perfil="admin"
        )
        return {"id": novo.id, "usuario": novo.usuario, "email": novo.email}


def extrair_csrf(resposta_html: str) -> str:
    achado = re.search(r'name="_csrf_token" value="([^"]+)"', resposta_html)
    assert achado, "Token CSRF nao encontrado na pagina."
    return achado.group(1)


def obter_csrf(client, url: str) -> str:
    resposta = client.get(url)
    assert resposta.status_code == 200, f"Falha ao abrir {url}: {resposta.status_code}"
    return extrair_csrf(resposta.get_data(as_text=True))


@pytest.fixture
def autenticado(client, usuario):
    """Cliente HTTP com sessao autenticada."""
    token = obter_csrf(client, "/login")
    resposta = client.post(
        "/login",
        data={"identificador": usuario["usuario"], "senha": SENHA_TESTE, "_csrf_token": token},
        follow_redirects=True,
    )
    assert resposta.status_code == 200
    return client


@pytest.fixture
def cenario(app):
    """Cria cliente, criterios e atendimentos de teste. Retorna os ids."""
    with app.app_context():
        cliente_a = cliente_service.criar_cliente(
            {"nome": "Cliente Alfa", "codigo": "ALFA", "nota_minima": 70}
        )
        cliente_b = cliente_service.criar_cliente(
            {"nome": "Cliente Beta", "codigo": "BETA", "nota_minima": 80}
        )

        saudacao = criterio_service.criar_criterio(
            cliente_a,
            {
                "nome": "Saudacao inicial",
                "peso": 1,
                "obrigatorio": "1",
                "termos_esperados": "bom dia, boa tarde, meu nome e",
                "minimo_termos": 1,
            },
        )
        confirmacao = criterio_service.criar_criterio(
            cliente_a,
            {
                "nome": "Confirmacao de dados",
                "peso": 3,
                "obrigatorio": "1",
                "termos_esperados": "confirmando seus dados, cpf",
                "minimo_termos": 1,
            },
        )
        protocolo = criterio_service.criar_criterio(
            cliente_a,
            {"nome": "Informou protocolo", "peso": 1, "termos_esperados": "protocolo"},
        )
        criterio_b = criterio_service.criar_criterio(
            cliente_b,
            {"nome": "Criterio exclusivo do Beta", "peso": 2, "termos_esperados": "beta"},
        )

        atendimento_bom = atendimento_service.criar_atendimento(
            cliente_a,
            {
                "protocolo": "ALFA-001",
                "atendente": "Maria Souza",
                "data_atendimento": date.today().strftime("%Y-%m-%d"),
                "canal": "telefone",
                "conteudo": CONTEUDO_BOM,
            },
        )
        atendimento_ruim = atendimento_service.criar_atendimento(
            cliente_a,
            {
                "protocolo": "ALFA-002",
                "atendente": "Carla Dias",
                "data_atendimento": date.today().strftime("%Y-%m-%d"),
                "conteudo": CONTEUDO_RUIM,
            },
        )

        return {
            "cliente_a": cliente_a.id,
            "cliente_b": cliente_b.id,
            "criterio_saudacao": saudacao.id,
            "criterio_confirmacao": confirmacao.id,
            "criterio_protocolo": protocolo.id,
            "criterio_beta": criterio_b.id,
            "atendimento_bom": atendimento_bom.id,
            "atendimento_ruim": atendimento_ruim.id,
        }
