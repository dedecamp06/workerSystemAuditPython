"""Testes dos criterios de auditoria e do isolamento por cliente."""
from conftest import obter_csrf


def test_cadastro_de_criterio(autenticado, app, cenario):
    token = obter_csrf(autenticado, "/criterios/novo")
    resposta = autenticado.post(
        "/criterios/novo",
        data={
            "cliente_id": cenario["cliente_a"],
            "nome": "Encerramento cordial",
            "descricao": "Agradecer e se despedir.",
            "peso": "2,5",
            "obrigatorio": "1",
            "ativo": "1",
            "minimo_termos": "1",
            "termos_esperados": "obrigado, as ordens",
            "_csrf_token": token,
        },
        follow_redirects=True,
    )
    assert "cadastrado para o cliente" in resposta.get_data(as_text=True)

    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Criterio

    with app.app_context():
        criterio = db.session.scalar(
            db.select(Criterio).where(Criterio.nome == "Encerramento cordial")
        )
        assert criterio.cliente_id == cenario["cliente_a"]
        assert criterio.peso == 2.5
        assert criterio.obrigatorio is True
        assert criterio.lista_esperados == ["obrigado", "as ordens"]


def test_peso_invalido_e_rejeitado_no_backend(autenticado, cenario):
    token = obter_csrf(autenticado, "/criterios/novo")
    for peso, mensagem in (("0", "maior que zero"), ("-3", "maior que zero"), ("abc", "numerico")):
        resposta = autenticado.post(
            "/criterios/novo",
            data={
                "cliente_id": cenario["cliente_a"],
                "nome": f"Criterio {peso}",
                "peso": peso,
                "minimo_termos": "1",
                "_csrf_token": token,
            },
        )
        assert mensagem in resposta.get_data(as_text=True)


def test_nome_obrigatorio_e_duplicidade_por_cliente(autenticado, cenario):
    token = obter_csrf(autenticado, "/criterios/novo")
    resposta = autenticado.post(
        "/criterios/novo",
        data={"cliente_id": cenario["cliente_a"], "nome": "", "peso": "1", "_csrf_token": token},
    )
    assert "Informe o nome do criterio." in resposta.get_data(as_text=True)

    resposta = autenticado.post(
        "/criterios/novo",
        data={
            "cliente_id": cenario["cliente_a"],
            "nome": "Saudacao inicial",
            "peso": "1",
            "minimo_termos": "1",
            "_csrf_token": token,
        },
    )
    assert "ja possui um criterio chamado" in resposta.get_data(as_text=True)


def test_mesmo_nome_e_permitido_em_clientes_diferentes(autenticado, cenario):
    token = obter_csrf(autenticado, "/criterios/novo")
    resposta = autenticado.post(
        "/criterios/novo",
        data={
            "cliente_id": cenario["cliente_b"],
            "nome": "Saudacao inicial",
            "peso": "1",
            "minimo_termos": "1",
            "ativo": "1",
            "termos_esperados": "bom dia",
            "_csrf_token": token,
        },
        follow_redirects=True,
    )
    assert "cadastrado para o cliente" in resposta.get_data(as_text=True)


def test_filtro_por_cliente_isola_criterios(autenticado, cenario):
    texto = autenticado.get(f"/criterios/?cliente_id={cenario['cliente_a']}").get_data(as_text=True)
    assert "Saudacao inicial" in texto
    assert "Criterio exclusivo do Beta" not in texto

    texto = autenticado.get(f"/criterios/?cliente_id={cenario['cliente_b']}").get_data(as_text=True)
    assert "Criterio exclusivo do Beta" in texto
    assert "Confirmacao de dados" not in texto


def test_auditoria_usa_somente_criterios_do_proprio_cliente(app, cenario):
    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Atendimento
    from auditoria_suporte.services import auditoria_service

    with app.app_context():
        atendimento = db.session.get(Atendimento, cenario["atendimento_bom"])
        avaliacoes = auditoria_service.preparar_avaliacao(atendimento)
        nomes = {a.nome for a in avaliacoes}
        assert nomes == {"Saudacao inicial", "Confirmacao de dados", "Informou protocolo"}
        assert "Criterio exclusivo do Beta" not in nomes


def test_registro_recusa_criterio_de_outro_cliente(app, cenario):
    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Atendimento, Criterio, Usuario
    from auditoria_suporte.services import auditoria_service, motor_avaliacao

    with app.app_context():
        atendimento = db.session.get(Atendimento, cenario["atendimento_bom"])
        criterio_beta = db.session.get(Criterio, cenario["criterio_beta"])
        usuario = db.session.scalar(db.select(Usuario))

        intrusas = motor_avaliacao.avaliar([criterio_beta], atendimento.conteudo)
        try:
            auditoria_service.registrar_auditoria(atendimento, usuario, intrusas)
            assert False, "A auditoria deveria ter sido recusada."
        except auditoria_service.ErroAuditoria as erro:
            assert "outro cliente" in str(erro)


def test_criterio_usado_em_auditoria_e_apenas_desativado(autenticado, app, cenario):
    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Atendimento, Criterio, Usuario
    from auditoria_suporte.services import auditoria_service

    with app.app_context():
        atendimento = db.session.get(Atendimento, cenario["atendimento_bom"])
        usuario = db.session.scalar(db.select(Usuario))
        avaliacoes = auditoria_service.preparar_avaliacao(atendimento)
        auditoria_service.registrar_auditoria(atendimento, usuario, avaliacoes)

    token = obter_csrf(autenticado, f"/criterios/?cliente_id={cenario['cliente_a']}")
    resposta = autenticado.post(
        f"/criterios/{cenario['criterio_saudacao']}/excluir",
        data={"_csrf_token": token},
        follow_redirects=True,
    )
    assert "foi desativado" in resposta.get_data(as_text=True)

    with app.app_context():
        criterio = db.session.get(Criterio, cenario["criterio_saudacao"])
        assert criterio is not None
        assert criterio.ativo is False


def test_criterio_sem_auditoria_pode_ser_excluido(autenticado, app, cenario):
    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Criterio

    token = obter_csrf(autenticado, "/criterios/")
    resposta = autenticado.post(
        f"/criterios/{cenario['criterio_protocolo']}/excluir",
        data={"_csrf_token": token},
        follow_redirects=True,
    )
    assert "excluido" in resposta.get_data(as_text=True)
    with app.app_context():
        assert db.session.get(Criterio, cenario["criterio_protocolo"]) is None


def test_nao_aplicavel_exige_termos_de_contexto(autenticado, cenario):
    token = obter_csrf(autenticado, "/criterios/novo")
    resposta = autenticado.post(
        "/criterios/novo",
        data={
            "cliente_id": cenario["cliente_a"],
            "nome": "Criterio condicional",
            "peso": "1",
            "minimo_termos": "1",
            "permite_nao_aplicavel": "1",
            "termos_esperados": "estorno",
            "_csrf_token": token,
        },
    )
    assert "termos de contexto" in resposta.get_data(as_text=True)
