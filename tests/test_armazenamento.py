"""Testes do armazenamento automatico dos resultados em arquivos."""
import json
from pathlib import Path

import pytest


@pytest.fixture
def auditoria_registrada(app, cenario):
    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Atendimento, Usuario
    from auditoria_suporte.services import auditoria_service

    with app.app_context():
        atendimento = db.session.get(Atendimento, cenario["atendimento_bom"])
        usuario = db.session.scalar(db.select(Usuario))
        avaliacoes = auditoria_service.preparar_avaliacao(atendimento)
        auditoria = auditoria_service.registrar_auditoria(
            atendimento, usuario, avaliacoes, observacoes="Teste de armazenamento"
        )
        return {
            "id": auditoria.id,
            "pasta_cliente": auditoria.cliente.pasta,
            "pasta_atendimento": atendimento.pasta,
            "arquivos": {a.tipo: a.caminho_relativo for a in auditoria.arquivos},
            "tamanhos": {a.tipo: a.tamanho_bytes for a in auditoria.arquivos},
            "sha": {a.tipo: a.sha256 for a in auditoria.arquivos},
        }


def test_arquivos_sao_gravados_na_pasta_do_cliente(app, auditoria_registrada):
    base = Path(app.config["AUDIT_STORAGE_DIR"])
    esperado = base / auditoria_registrada["pasta_cliente"] / auditoria_registrada["pasta_atendimento"]

    assert esperado.is_dir()
    assert (esperado / "resultado_auditoria.json").is_file()
    assert (esperado / "resultado_auditoria.txt").is_file()

    for tipo, relativo in auditoria_registrada["arquivos"].items():
        caminho = base / relativo
        assert caminho.is_file()
        assert caminho.stat().st_size == auditoria_registrada["tamanhos"][tipo]
        assert len(auditoria_registrada["sha"][tipo]) == 64


def test_conteudo_do_json_tem_todos_os_campos(app, auditoria_registrada):
    base = Path(app.config["AUDIT_STORAGE_DIR"])
    dados = json.loads((base / auditoria_registrada["arquivos"]["json"]).read_text(encoding="utf-8"))

    assert dados["auditoria"]["id"] == auditoria_registrada["id"]
    assert dados["cliente"]["nome"] == "Cliente Alfa"
    assert dados["atendimento"]["protocolo"] == "ALFA-001"
    assert dados["atendimento"]["atendente"] == "Maria Souza"
    assert dados["atendimento"]["data_atendimento"]
    assert dados["auditoria"]["executada_em"]
    assert dados["pontuacao"]["pontuacao_final_percentual"] == 100.0
    assert dados["pontuacao"]["formula"]
    assert dados["situacao_geral"] == "aprovado"
    assert dados["requer_revisao_humana"] is False
    assert dados["observacoes"] == "Teste de armazenamento"
    assert len(dados["criterios"]) == 3
    for criterio in dados["criterios"]:
        assert criterio["nome"]
        assert criterio["peso"] > 0
        assert criterio["status"]
        assert "pontuacao_obtida" in criterio
        assert criterio["justificativa"]


def test_conteudo_do_txt_e_legivel(app, auditoria_registrada):
    base = Path(app.config["AUDIT_STORAGE_DIR"])
    texto = (base / auditoria_registrada["arquivos"]["txt"]).read_text(encoding="utf-8")
    assert "RESULTADO DA AUDITORIA DE ATENDIMENTO" in texto
    assert "Cliente Alfa" in texto
    assert "SITUACAO GERAL            : APROVADO" in texto
    assert "Pontuacao final" in texto


def test_reauditoria_nao_sobrescreve_o_resultado_anterior(app, cenario, auditoria_registrada):
    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Atendimento, Usuario
    from auditoria_suporte.services import auditoria_service

    with app.app_context():
        atendimento = db.session.get(Atendimento, cenario["atendimento_bom"])
        usuario = db.session.scalar(db.select(Usuario))
        avaliacoes = auditoria_service.preparar_avaliacao(atendimento)
        nova = auditoria_service.registrar_auditoria(atendimento, usuario, avaliacoes)
        novos = {a.tipo: a.caminho_relativo for a in nova.arquivos}

    base = Path(app.config["AUDIT_STORAGE_DIR"])
    assert novos["json"].endswith("resultado_auditoria_v2.json")
    assert (base / novos["json"]).is_file()
    assert (base / auditoria_registrada["arquivos"]["json"]).is_file()  # o anterior continua


def test_falha_de_armazenamento_nao_registra_a_auditoria(app, cenario, monkeypatch):
    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Atendimento, Auditoria, ResultadoCriterio, Usuario
    from auditoria_suporte.services import armazenamento_service, auditoria_service

    def falhar(destino, conteudo):
        raise OSError("disco indisponivel (simulado)")

    monkeypatch.setattr(armazenamento_service, "_gravar_e_conferir", falhar)

    with app.app_context():
        atendimento = db.session.get(Atendimento, cenario["atendimento_bom"])
        usuario = db.session.scalar(db.select(Usuario))
        avaliacoes = auditoria_service.preparar_avaliacao(atendimento)

        with pytest.raises(armazenamento_service.ErroArmazenamento) as erro:
            auditoria_service.registrar_auditoria(atendimento, usuario, avaliacoes)
        assert "Falha ao gravar" in str(erro.value)

        # nada foi persistido
        assert db.session.scalar(db.select(db.func.count(Auditoria.id))) == 0
        assert db.session.scalar(db.select(db.func.count(ResultadoCriterio.id))) == 0


def test_caminho_fora_do_diretorio_base_e_recusado(app):
    from auditoria_suporte.services.armazenamento_service import ErroArmazenamento, caminho_seguro

    with app.app_context():
        for caminho in ("../fora.json", "../../etc/passwd", "cliente_1/../../fora.txt"):
            with pytest.raises(ErroArmazenamento):
                caminho_seguro(caminho)


def test_resultados_de_clientes_diferentes_ficam_em_pastas_diferentes(app, cenario):
    from datetime import date

    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Cliente, Usuario
    from auditoria_suporte.services import atendimento_service, auditoria_service, criterio_service

    with app.app_context():
        cliente_b = db.session.get(Cliente, cenario["cliente_b"])
        usuario = db.session.scalar(db.select(Usuario))
        criterio_service.criar_criterio(
            cliente_b, {"nome": "Saudacao Beta", "peso": 1, "termos_esperados": "bom dia"}
        )
        atendimento = atendimento_service.criar_atendimento(
            cliente_b,
            {
                "atendente": "Beta Atendente",
                "data_atendimento": date.today().strftime("%Y-%m-%d"),
                "conteudo": "Atendente: bom dia, aqui e o suporte do cliente beta falando com voce.",
            },
        )
        avaliacoes = auditoria_service.preparar_avaliacao(atendimento)
        auditoria = auditoria_service.registrar_auditoria(atendimento, usuario, avaliacoes)
        caminho_b = auditoria.arquivos[0].caminho_relativo
        pasta_b = cliente_b.pasta
        pasta_a = db.session.get(Cliente, cenario["cliente_a"]).pasta

    assert caminho_b.startswith(pasta_b + "/")
    assert not caminho_b.startswith(pasta_a + "/")
    assert pasta_a != pasta_b
