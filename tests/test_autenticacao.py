"""Testes de login, logout, protecao das paginas internas e CSRF."""
from conftest import SENHA_TESTE, obter_csrf


def test_login_com_credenciais_validas(client, usuario):
    token = obter_csrf(client, "/login")
    resposta = client.post(
        "/login",
        data={"identificador": usuario["usuario"], "senha": SENHA_TESTE, "_csrf_token": token},
        follow_redirects=True,
    )
    assert resposta.status_code == 200
    assert "Dashboard" in resposta.get_data(as_text=True)


def test_login_aceita_email(client, usuario):
    token = obter_csrf(client, "/login")
    resposta = client.post(
        "/login",
        data={"identificador": usuario["email"], "senha": SENHA_TESTE, "_csrf_token": token},
        follow_redirects=True,
    )
    assert "Dashboard" in resposta.get_data(as_text=True)


def test_login_com_senha_invalida(client, usuario):
    token = obter_csrf(client, "/login")
    resposta = client.post(
        "/login",
        data={"identificador": usuario["usuario"], "senha": "errada", "_csrf_token": token},
    )
    assert resposta.status_code == 401
    assert "Usuario ou senha invalidos" in resposta.get_data(as_text=True)


def test_login_com_campos_vazios(client, usuario):
    token = obter_csrf(client, "/login")
    resposta = client.post("/login", data={"identificador": "", "senha": "", "_csrf_token": token})
    texto = resposta.get_data(as_text=True)
    assert "Informe o usuario ou e-mail." in texto
    assert "Informe a senha." in texto


def test_senha_nao_e_armazenada_em_texto_puro(app, usuario):
    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Usuario

    with app.app_context():
        registro = db.session.get(Usuario, usuario["id"])
        assert SENHA_TESTE not in registro.senha_hash
        assert registro.verificar_senha(SENHA_TESTE)
        assert not registro.verificar_senha("outra-senha")


def test_paginas_internas_exigem_login(client):
    for url in (
        "/",
        "/clientes/",
        "/atendimentos/",
        "/criterios/",
        "/auditorias/",
        "/resultados/",
    ):
        resposta = client.get(url)
        assert resposta.status_code == 302, url
        assert "/login" in resposta.headers["Location"], url


def test_logout_encerra_sessao(autenticado):
    token = obter_csrf(autenticado, "/")
    resposta = autenticado.post("/logout", data={"_csrf_token": token}, follow_redirects=True)
    assert "Acessar o sistema" in resposta.get_data(as_text=True)
    assert autenticado.get("/").status_code == 302


def test_post_sem_token_csrf_e_rejeitado(autenticado):
    resposta = autenticado.post("/clientes/novo", data={"nome": "Sem token"})
    assert resposta.status_code == 400
    assert "token CSRF" in resposta.get_data(as_text=True)


def test_dashboard_mostra_indicadores_reais(autenticado, cenario):
    texto = autenticado.get("/").get_data(as_text=True)
    assert "Clientes cadastrados" in texto
    assert "Pendentes de auditoria" in texto


def _criar_app(app):
    from auditoria_suporte import create_app

    return create_app({k: app.config[k] for k in (
        "TESTING", "SECRET_KEY", "INSTANCE_DIR", "PASTA_LEGADA_AUDITORIAS", "SQLALCHEMY_DATABASE_URI"
    )})


def test_admin_inicial_criado_pelas_variaveis_de_ambiente(app, monkeypatch):
    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Usuario
    from auditoria_suporte.services.autenticacao_service import autenticar

    monkeypatch.setenv("AUDITORIA_ADMIN_USUARIO", "Ana")
    monkeypatch.setenv("AUDITORIA_ADMIN_SENHA", "senha-forte-123")
    _criar_app(app)

    with app.app_context():
        admin = db.session.scalar(db.select(Usuario))
        assert admin.usuario == "ana"
        assert admin.perfil == "admin"
        assert autenticar("ana", "senha-forte-123") is not None

    # com um administrador ja existente, as variaveis nao alteram nada
    monkeypatch.setenv("AUDITORIA_ADMIN_USUARIO", "outro")
    monkeypatch.setenv("AUDITORIA_ADMIN_SENHA", "outra-senha-456")
    _criar_app(app)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Usuario.id))) == 1
        assert autenticar("ana", "senha-forte-123") is not None


def test_admin_inicial_com_senha_curta_nao_derruba_o_sistema(app, monkeypatch):
    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Usuario

    monkeypatch.setenv("AUDITORIA_ADMIN_USUARIO", "ana")
    monkeypatch.setenv("AUDITORIA_ADMIN_SENHA", "curta")
    _criar_app(app)
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count(Usuario.id))) == 0
