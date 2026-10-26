"""Verifica se todas as telas do sistema abrem sem erro e com dados reais."""
from datetime import date

from conftest import CONTEUDO_BOM


def test_todas_as_telas_respondem(autenticado, app, cenario):
    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Atendimento, Usuario
    from auditoria_suporte.services import auditoria_service

    with app.app_context():
        atendimento = db.session.get(Atendimento, cenario["atendimento_bom"])
        usuario = db.session.scalar(db.select(Usuario))
        avaliacoes = auditoria_service.preparar_avaliacao(atendimento)
        auditoria_id = auditoria_service.registrar_auditoria(
            atendimento, usuario, avaliacoes
        ).id

    paginas = [
        "/",
        "/perfil",
        "/clientes/",
        "/clientes/novo",
        f"/clientes/{cenario['cliente_a']}",
        f"/clientes/{cenario['cliente_a']}/editar",
        "/atendimentos/",
        "/atendimentos/?situacao=pendentes",
        "/atendimentos/novo",
        f"/atendimentos/{cenario['atendimento_ruim']}",
        f"/atendimentos/{cenario['atendimento_ruim']}/editar",
        "/atendimentos/importar",
        "/atendimentos/modelo.csv",
        "/criterios/",
        "/criterios/?ativos=1",
        "/criterios/novo",
        f"/criterios/{cenario['criterio_saudacao']}/editar",
        "/auditorias/",
        "/auditorias/?exibir=todos",
        f"/auditorias/executar/{cenario['atendimento_ruim']}",
        "/resultados/",
        f"/resultados/{auditoria_id}",
    ]
    for pagina in paginas:
        resposta = autenticado.get(pagina)
        assert resposta.status_code == 200, f"{pagina} -> {resposta.status_code}"


def test_pagina_inexistente_mostra_erro_amigavel(autenticado):
    resposta = autenticado.get("/pagina-que-nao-existe")
    assert resposta.status_code == 404
    texto = resposta.get_data(as_text=True)
    assert "Pagina nao encontrada" in texto
    assert "Traceback" not in texto


def test_paginacao_das_listagens(autenticado, app, cenario):
    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Cliente
    from auditoria_suporte.services import atendimento_service

    with app.app_context():
        cliente = db.session.get(Cliente, cenario["cliente_a"])
        for numero in range(20):
            atendimento_service.criar_atendimento(
                cliente,
                {
                    "protocolo": f"PAG-{numero:03d}",
                    "atendente": "Paginacao",
                    "data_atendimento": date.today().strftime("%Y-%m-%d"),
                    "conteudo": CONTEUDO_BOM,
                },
            )

    texto = autenticado.get("/atendimentos/").get_data(as_text=True)
    assert "Pagina 1 de 2" in texto
    assert "22 registros" in texto

    texto = autenticado.get("/atendimentos/?pagina=2").get_data(as_text=True)
    assert "Pagina 2 de 2" in texto
