"""Testes da execucao da auditoria, do calculo da pontuacao e do historico."""
from datetime import date

import pytest

from conftest import CONTEUDO_BOM, obter_csrf


@pytest.fixture
def executar_auditoria(app):
    """Executa a auditoria de um atendimento usando os servicos de negocio."""

    def _executar(atendimento_id, avaliacoes_ajustadas=None):
        from auditoria_suporte.extensions import db
        from auditoria_suporte.models import Atendimento, Usuario
        from auditoria_suporte.services import auditoria_service

        with app.app_context():
            atendimento = db.session.get(Atendimento, atendimento_id)
            usuario = db.session.scalar(db.select(Usuario))
            avaliacoes = auditoria_service.preparar_avaliacao(atendimento)
            if avaliacoes_ajustadas:
                avaliacoes_ajustadas(avaliacoes)
            auditoria = auditoria_service.registrar_auditoria(atendimento, usuario, avaliacoes)
            return {
                "id": auditoria.id,
                "versao": auditoria.versao,
                "pontuacao": auditoria.pontuacao_final,
                "situacao": auditoria.situacao,
                "revisao": auditoria.requer_revisao_humana,
                "soma_pesos": auditoria.soma_pesos,
                "soma_pontos": auditoria.soma_pontos,
                "resultados": {r.criterio_nome: r.status for r in auditoria.resultados},
                "arquivos": [a.caminho_relativo for a in auditoria.arquivos],
            }

    return _executar


def test_atendimento_conforme_e_aprovado(executar_auditoria, cenario):
    resultado = executar_auditoria(cenario["atendimento_bom"])
    assert resultado["situacao"] == "aprovado"
    assert resultado["pontuacao"] == 100.0
    assert resultado["soma_pesos"] == 5.0
    assert resultado["soma_pontos"] == 5.0
    assert set(resultado["resultados"].values()) == {"atendido"}


def test_criterios_obrigatorios_nao_atendidos_reprovam(executar_auditoria, cenario, app):
    resultado = executar_auditoria(cenario["atendimento_ruim"])
    assert resultado["situacao"] == "reprovado"
    assert resultado["pontuacao"] == 0.0
    assert resultado["resultados"]["Saudacao inicial"] == "nao_atendido"
    assert resultado["resultados"]["Confirmacao de dados"] == "nao_atendido"

    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Auditoria

    with app.app_context():
        auditoria = db.session.get(Auditoria, resultado["id"])
        nomes = [r.criterio_nome for r in auditoria.obrigatorios_nao_atendidos]
        assert "Saudacao inicial" in nomes and "Confirmacao de dados" in nomes
        assert "obrigatorios nao atendidos" in auditoria.resumo_calculo


def test_pontuacao_ponderada_parcial(app, executar_auditoria):
    """2 de 5 pontos possiveis = 40%, abaixo da nota minima => reprovado."""
    from auditoria_suporte.services import atendimento_service, cliente_service, criterio_service

    with app.app_context():
        cliente = cliente_service.criar_cliente(
            {"nome": "Cliente Peso", "codigo": "PESO", "nota_minima": 70}
        )
        criterio_service.criar_criterio(
            cliente,
            {"nome": "Criterio leve", "peso": 2, "termos_esperados": "bom dia", "minimo_termos": 1},
        )
        criterio_service.criar_criterio(
            cliente,
            {
                "nome": "Criterio pesado",
                "peso": 3,
                "termos_esperados": "termo-que-nao-existe-no-texto",
                "minimo_termos": 1,
            },
        )
        atendimento = atendimento_service.criar_atendimento(
            cliente,
            {
                "atendente": "Teste Peso",
                "data_atendimento": date.today().strftime("%Y-%m-%d"),
                "conteudo": CONTEUDO_BOM,
            },
        )
        atendimento_id = atendimento.id

    resultado = executar_auditoria(atendimento_id)
    assert resultado["soma_pesos"] == 5.0
    assert resultado["soma_pontos"] == 2.0
    assert resultado["pontuacao"] == 40.0
    assert resultado["situacao"] == "reprovado"


def test_criterio_inconclusivo_gera_pendencia_de_revisao(app, executar_auditoria):
    from auditoria_suporte.services import atendimento_service, cliente_service, criterio_service

    with app.app_context():
        cliente = cliente_service.criar_cliente({"nome": "Cliente Incon", "codigo": "INCON"})
        criterio_service.criar_criterio(
            cliente, {"nome": "Sem regras configuradas", "peso": 1}
        )
        criterio_service.criar_criterio(
            cliente, {"nome": "Com regra", "peso": 1, "termos_esperados": "bom dia"}
        )
        atendimento = atendimento_service.criar_atendimento(
            cliente,
            {
                "atendente": "Teste Incon",
                "data_atendimento": date.today().strftime("%Y-%m-%d"),
                "conteudo": CONTEUDO_BOM,
            },
        )
        atendimento_id = atendimento.id

    resultado = executar_auditoria(atendimento_id)
    assert resultado["resultados"]["Sem regras configuradas"] == "inconclusivo"
    assert resultado["situacao"] == "pendente_revisao"
    assert resultado["revisao"] is True
    # o criterio inconclusivo entra no denominador, mas nao recebe pontos
    assert resultado["soma_pesos"] == 2.0
    assert resultado["soma_pontos"] == 1.0
    assert resultado["pontuacao"] == 50.0


def test_conteudo_curto_gera_inconclusivo(app, executar_auditoria):
    from auditoria_suporte.services import atendimento_service, cliente_service, criterio_service

    with app.app_context():
        cliente = cliente_service.criar_cliente({"nome": "Cliente Curto", "codigo": "CURTO"})
        criterio_service.criar_criterio(
            cliente, {"nome": "Saudacao", "peso": 1, "termos_esperados": "bom dia"}
        )
        atendimento = atendimento_service.criar_atendimento(
            cliente,
            {
                "atendente": "Teste Curto",
                "data_atendimento": date.today().strftime("%Y-%m-%d"),
                "conteudo": "Atendimento muito curto, sem contexto.",
            },
        )
        atendimento_id = atendimento.id

    resultado = executar_auditoria(atendimento_id)
    assert resultado["resultados"]["Saudacao"] == "inconclusivo"
    assert resultado["situacao"] == "pendente_revisao"


def test_criterio_nao_aplicavel_sai_do_calculo(app, executar_auditoria):
    from auditoria_suporte.services import atendimento_service, cliente_service, criterio_service

    with app.app_context():
        cliente = cliente_service.criar_cliente({"nome": "Cliente NA", "codigo": "NAPL"})
        criterio_service.criar_criterio(
            cliente, {"nome": "Saudacao", "peso": 1, "termos_esperados": "bom dia"}
        )
        criterio_service.criar_criterio(
            cliente,
            {
                "nome": "Tratativa de cobranca",
                "peso": 4,
                "termos_esperados": "estorno, segunda via",
                "termos_contexto": "fatura, cobranca, boleto",
                "permite_nao_aplicavel": "1",
            },
        )
        atendimento = atendimento_service.criar_atendimento(
            cliente,
            {
                "atendente": "Teste NA",
                "data_atendimento": date.today().strftime("%Y-%m-%d"),
                "conteudo": CONTEUDO_BOM,
            },
        )
        atendimento_id = atendimento.id

    resultado = executar_auditoria(atendimento_id)
    assert resultado["resultados"]["Tratativa de cobranca"] == "nao_aplicavel"
    assert resultado["soma_pesos"] == 1.0  # peso 4 desconsiderado
    assert resultado["pontuacao"] == 100.0
    assert resultado["situacao"] == "aprovado"


def test_termo_proibido_reprova_criterio(app, executar_auditoria, cenario):
    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Cliente
    from auditoria_suporte.services import criterio_service

    with app.app_context():
        cliente = db.session.get(Cliente, cenario["cliente_a"])
        criterio_service.criar_criterio(
            cliente,
            {
                "nome": "Cordialidade",
                "peso": 2,
                "obrigatorio": "1",
                "termos_esperados": "por favor, obrigado",
                "termos_proibidos": "nao e problema meu",
            },
        )

    resultado = executar_auditoria(cenario["atendimento_ruim"])
    assert resultado["resultados"]["Cordialidade"] == "nao_atendido"
    assert resultado["situacao"] == "reprovado"


def test_reauditoria_cria_nova_versao_e_preserva_historico(executar_auditoria, cenario, app):
    primeira = executar_auditoria(cenario["atendimento_bom"])
    segunda = executar_auditoria(cenario["atendimento_bom"])

    assert primeira["versao"] == 1 and segunda["versao"] == 2
    assert primeira["id"] != segunda["id"]
    assert primeira["arquivos"] != segunda["arquivos"]

    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Auditoria

    with app.app_context():
        total = db.session.scalar(
            db.select(db.func.count(Auditoria.id)).where(
                Auditoria.atendimento_id == cenario["atendimento_bom"]
            )
        )
        assert total == 2


def test_alteracao_do_criterio_nao_muda_auditoria_antiga(executar_auditoria, cenario, app):
    resultado = executar_auditoria(cenario["atendimento_bom"])

    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Auditoria, Criterio
    from auditoria_suporte.services import criterio_service

    with app.app_context():
        criterio = db.session.get(Criterio, cenario["criterio_confirmacao"])
        criterio_service.atualizar_criterio(
            criterio,
            {
                "nome": "Confirmacao de dados (revisada)",
                "peso": "9",
                "obrigatorio": "",
                "ativo": "1",
                "minimo_termos": "1",
                "termos_esperados": "cpf",
            },
        )

        auditoria = db.session.get(Auditoria, resultado["id"])
        snapshot = {r.criterio_nome: (r.peso, r.obrigatorio) for r in auditoria.resultados}
        assert snapshot["Confirmacao de dados"] == (3.0, True)
        assert auditoria.soma_pesos == 5.0
        assert auditoria.pontuacao_final == 100.0


def test_fluxo_web_de_auditoria(autenticado, app, cenario):
    url = f"/auditorias/executar/{cenario['atendimento_bom']}"
    pagina = autenticado.get(url)
    texto = pagina.get_data(as_text=True)
    assert pagina.status_code == 200
    assert "Pontuacao sugerida" in texto
    assert "Saudacao inicial" in texto

    token = obter_csrf(autenticado, url)
    dados = {"_csrf_token": token, "observacoes": "Auditoria realizada via interface."}
    for chave in ("criterio_saudacao", "criterio_confirmacao", "criterio_protocolo"):
        dados[f"status_{cenario[chave]}"] = "atendido"
        dados[f"justificativa_{cenario[chave]}"] = "Evidencia confirmada pelo auditor."

    resposta = autenticado.post(url, data=dados, follow_redirects=True)
    corpo = resposta.get_data(as_text=True)
    assert "registrada" in corpo
    assert "100,00%" in corpo or "100.0" in corpo

    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Auditoria

    with app.app_context():
        auditoria = db.session.scalar(db.select(Auditoria))
        assert auditoria.situacao == "aprovado"
        assert auditoria.observacoes == "Auditoria realizada via interface."
        assert auditoria.ajustada_manualmente is True


def test_reauditoria_exige_confirmacao_explicita(autenticado, executar_auditoria, cenario):
    executar_auditoria(cenario["atendimento_bom"])
    url = f"/auditorias/executar/{cenario['atendimento_bom']}"

    pagina = autenticado.get(url).get_data(as_text=True)
    assert "ja foi auditado" in pagina
    assert "Reauditar atendimento" in pagina

    pagina = autenticado.get(url + "?reauditar=1").get_data(as_text=True)
    assert "Criterios avaliados" in pagina


def test_justificativa_obrigatoria_para_nao_atendido(autenticado, cenario):
    url = f"/auditorias/executar/{cenario['atendimento_bom']}"
    token = obter_csrf(autenticado, url)
    dados = {"_csrf_token": token}
    for chave in ("criterio_saudacao", "criterio_confirmacao", "criterio_protocolo"):
        dados[f"status_{cenario[chave]}"] = "nao_atendido"
        dados[f"justificativa_{cenario[chave]}"] = ""

    resposta = autenticado.post(url, data=dados)
    assert "Informe a justificativa para o criterio nao atendido" in resposta.get_data(as_text=True)


def test_auditoria_sem_criterios_ativos_e_bloqueada(autenticado, app, cenario):
    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Criterio

    with app.app_context():
        for criterio_id in (
            cenario["criterio_saudacao"],
            cenario["criterio_confirmacao"],
            cenario["criterio_protocolo"],
        ):
            db.session.get(Criterio, criterio_id).ativo = False
        db.session.commit()

    resposta = autenticado.get(
        f"/auditorias/executar/{cenario['atendimento_bom']}", follow_redirects=True
    )
    assert "nao possui criterios de auditoria ativos" in resposta.get_data(as_text=True)
