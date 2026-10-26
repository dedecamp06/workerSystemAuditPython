"""Testes de cadastro, consulta, edicao e desativacao de clientes."""
from conftest import obter_csrf


def test_cadastro_de_cliente(autenticado, app):
    token = obter_csrf(autenticado, "/clientes/novo")
    resposta = autenticado.post(
        "/clientes/novo",
        data={
            "nome": "Empresa Teste",
            "codigo": "TESTE",
            "contato": "Qualidade",
            "email": "qa@teste.local",
            "nota_minima": "75",
            "_csrf_token": token,
        },
        follow_redirects=True,
    )
    texto = resposta.get_data(as_text=True)
    assert "cadastrado com sucesso" in texto
    assert "Empresa Teste" in texto

    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Cliente

    with app.app_context():
        cliente = db.session.scalar(db.select(Cliente).where(Cliente.codigo == "TESTE"))
        assert cliente is not None
        assert cliente.nota_minima == 75
        assert cliente.pasta.startswith(f"cliente_{cliente.id}_")


def test_cadastro_sem_nome_e_rejeitado(autenticado, app):
    token = obter_csrf(autenticado, "/clientes/novo")
    resposta = autenticado.post(
        "/clientes/novo", data={"nome": "", "nota_minima": "70", "_csrf_token": token}
    )
    assert "Informe o nome do cliente." in resposta.get_data(as_text=True)

    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Cliente

    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Cliente.id))) == 0


def test_codigo_duplicado_e_rejeitado(autenticado, cenario):
    token = obter_csrf(autenticado, "/clientes/novo")
    resposta = autenticado.post(
        "/clientes/novo",
        data={"nome": "Outro Alfa", "codigo": "ALFA", "nota_minima": "70", "_csrf_token": token},
    )
    assert "Ja existe um cliente com o identificador" in resposta.get_data(as_text=True)


def test_nota_minima_invalida_e_rejeitada(autenticado):
    token = obter_csrf(autenticado, "/clientes/novo")
    resposta = autenticado.post(
        "/clientes/novo",
        data={"nome": "Nota Errada", "nota_minima": "150", "_csrf_token": token},
    )
    assert "A nota minima deve estar entre 0 e 100." in resposta.get_data(as_text=True)


def test_listagem_e_consulta_de_clientes(autenticado, cenario):
    lista = autenticado.get("/clientes/").get_data(as_text=True)
    assert "Cliente Alfa" in lista and "Cliente Beta" in lista

    detalhe = autenticado.get(f"/clientes/{cenario['cliente_a']}").get_data(as_text=True)
    assert "Cliente Alfa" in detalhe
    assert "Pasta de resultados" in detalhe

    filtrado = autenticado.get("/clientes/?busca=Beta").get_data(as_text=True)
    assert "Cliente Beta" in filtrado and "Cliente Alfa" not in filtrado


def test_edicao_de_cliente(autenticado, app, cenario):
    url = f"/clientes/{cenario['cliente_a']}/editar"
    token = obter_csrf(autenticado, url)
    resposta = autenticado.post(
        url,
        data={
            "nome": "Cliente Alfa Renomeado",
            "codigo": "ALFA",
            "nota_minima": "90",
            "ativo": "1",
            "_csrf_token": token,
        },
        follow_redirects=True,
    )
    assert "atualizado com sucesso" in resposta.get_data(as_text=True)

    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Cliente

    with app.app_context():
        cliente = db.session.get(Cliente, cenario["cliente_a"])
        assert cliente.nome == "Cliente Alfa Renomeado"
        assert cliente.nota_minima == 90


def test_cliente_com_vinculos_e_desativado_e_nao_excluido(autenticado, app, cenario):
    url = f"/clientes/{cenario['cliente_a']}/excluir"
    token = obter_csrf(autenticado, f"/clientes/{cenario['cliente_a']}")
    resposta = autenticado.post(url, data={"_csrf_token": token}, follow_redirects=True)
    assert "foi desativado" in resposta.get_data(as_text=True)

    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Atendimento, Cliente

    with app.app_context():
        cliente = db.session.get(Cliente, cenario["cliente_a"])
        assert cliente is not None
        assert cliente.ativo is False
        # os atendimentos vinculados continuam existindo
        assert db.session.scalar(
            db.select(db.func.count(Atendimento.id)).where(
                Atendimento.cliente_id == cenario["cliente_a"]
            )
        ) == 2


def test_cliente_sem_vinculos_pode_ser_excluido(autenticado, app):
    token = obter_csrf(autenticado, "/clientes/novo")
    autenticado.post(
        "/clientes/novo",
        data={"nome": "Sem Vinculos", "codigo": "SEMV", "nota_minima": "70", "_csrf_token": token},
        follow_redirects=True,
    )

    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Cliente

    with app.app_context():
        cliente_id = db.session.scalar(db.select(Cliente.id).where(Cliente.codigo == "SEMV"))

    token = obter_csrf(autenticado, f"/clientes/{cliente_id}")
    resposta = autenticado.post(
        f"/clientes/{cliente_id}/excluir", data={"_csrf_token": token}, follow_redirects=True
    )
    assert "excluido" in resposta.get_data(as_text=True)

    with app.app_context():
        assert db.session.get(Cliente, cliente_id) is None
