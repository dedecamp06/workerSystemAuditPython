"""Testes da consulta dos resultados e do acesso aos arquivos."""
import json

import pytest


@pytest.fixture
def auditorias(app, cenario):
    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Atendimento, Usuario
    from auditoria_suporte.services import auditoria_service

    registradas = {}
    with app.app_context():
        usuario = db.session.scalar(db.select(Usuario))
        for chave in ("atendimento_bom", "atendimento_ruim"):
            atendimento = db.session.get(Atendimento, cenario[chave])
            avaliacoes = auditoria_service.preparar_avaliacao(atendimento)
            auditoria = auditoria_service.registrar_auditoria(atendimento, usuario, avaliacoes)
            registradas[chave] = auditoria.id
    return registradas


def test_listagem_exibe_dados_reais(autenticado, auditorias):
    texto = autenticado.get("/resultados/").get_data(as_text=True)
    assert "Cliente Alfa" in texto
    assert "ALFA-001" in texto and "ALFA-002" in texto
    assert "Maria Souza" in texto and "Carla Dias" in texto
    assert "100.0%" in texto
    assert "Aprovado" in texto and "Reprovado" in texto


def test_filtros_da_listagem(autenticado, auditorias, cenario):
    texto = autenticado.get("/resultados/?situacao=aprovado").get_data(as_text=True)
    assert "ALFA-001" in texto and "ALFA-002" not in texto

    texto = autenticado.get("/resultados/?busca=Carla").get_data(as_text=True)
    assert "ALFA-002" in texto and "ALFA-001" not in texto

    texto = autenticado.get(f"/resultados/?cliente_id={cenario['cliente_b']}").get_data(as_text=True)
    assert "ALFA-001" not in texto

    texto = autenticado.get("/resultados/?busca=ALFA-001").get_data(as_text=True)
    assert "ALFA-001" in texto


def test_detalhe_mostra_criterios_e_justificativas(autenticado, auditorias):
    texto = autenticado.get(f"/resultados/{auditorias['atendimento_ruim']}").get_data(as_text=True)
    assert "Saudacao inicial" in texto
    assert "Confirmacao de dados" in texto
    assert "Criterios obrigatorios nao atendidos" in texto
    assert "Nenhum dos termos esperados" in texto
    assert "Como a pontuacao foi calculada" in texto
    assert "resultado_auditoria.json" in texto


def test_download_dos_arquivos(autenticado, auditorias):
    auditoria_id = auditorias["atendimento_bom"]

    resposta = autenticado.get(f"/resultados/{auditoria_id}/arquivo/json")
    assert resposta.status_code == 200
    dados = json.loads(resposta.get_data(as_text=True))
    assert dados["auditoria"]["id"] == auditoria_id
    assert "attachment" in resposta.headers["Content-Disposition"]

    resposta = autenticado.get(f"/resultados/{auditoria_id}/arquivo/txt")
    assert resposta.status_code == 200
    assert "RESULTADO DA AUDITORIA" in resposta.get_data(as_text=True)

    assert autenticado.get(f"/resultados/{auditoria_id}/arquivo/exe").status_code == 404
    assert autenticado.get("/resultados/9999/arquivo/json").status_code == 404


def test_download_exige_autenticacao(client, auditorias):
    resposta = client.get(f"/resultados/{auditorias['atendimento_bom']}/arquivo/json")
    assert resposta.status_code == 302
    assert "/login" in resposta.headers["Location"]


def test_arquivo_ausente_em_disco_informa_erro(app, autenticado, auditorias):
    from pathlib import Path

    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Auditoria

    auditoria_id = auditorias["atendimento_bom"]
    with app.app_context():
        auditoria = db.session.get(Auditoria, auditoria_id)
        relativo = auditoria.arquivo("json").caminho_relativo
    Path(app.config["AUDIT_STORAGE_DIR"], relativo).unlink()

    resposta = autenticado.get(f"/resultados/{auditoria_id}/arquivo/json", follow_redirects=True)
    assert "nao encontrado em disco" in resposta.get_data(as_text=True)


def test_dashboard_reflete_auditorias(autenticado, auditorias):
    texto = autenticado.get("/").get_data(as_text=True)
    assert "Ultimas auditorias executadas" in texto
    assert "ALFA-001" in texto
