"""Testes do armazenamento automatico dos resultados (JSON/TXT no banco)."""
import hashlib
import json

import pytest


def _conteudo(app, caminho):
    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import ArquivoAuditoria

    with app.app_context():
        arquivo = db.session.scalar(
            db.select(ArquivoAuditoria).where(ArquivoAuditoria.caminho_relativo == caminho)
        )
        return arquivo.conteudo if arquivo else None


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
    prefixo = f"{auditoria_registrada['pasta_cliente']}/{auditoria_registrada['pasta_atendimento']}"
    arquivos = auditoria_registrada["arquivos"]

    assert arquivos["json"] == f"{prefixo}/resultado_auditoria.json"
    assert arquivos["txt"] == f"{prefixo}/resultado_auditoria.txt"

    for tipo, relativo in arquivos.items():
        conteudo = _conteudo(app, relativo)
        assert conteudo
        dados = conteudo.encode("utf-8")
        assert len(dados) == auditoria_registrada["tamanhos"][tipo]
        assert hashlib.sha256(dados).hexdigest() == auditoria_registrada["sha"][tipo]


def test_conteudo_do_json_tem_todos_os_campos(app, auditoria_registrada):
    dados = json.loads(_conteudo(app, auditoria_registrada["arquivos"]["json"]))

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
    texto = _conteudo(app, auditoria_registrada["arquivos"]["txt"])
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

    assert novos["json"].endswith("resultado_auditoria_v2.json")
    assert _conteudo(app, novos["json"])
    assert _conteudo(app, auditoria_registrada["arquivos"]["json"])  # o anterior continua


def test_falha_de_armazenamento_nao_registra_a_auditoria(app, cenario, monkeypatch):
    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Atendimento, Auditoria, ResultadoCriterio, Usuario
    from auditoria_suporte.services import armazenamento_service, auditoria_service

    def falhar(caminho, conteudo):
        raise armazenamento_service.ErroArmazenamento("conferencia falhou (simulado)")

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


def test_arquivos_legados_em_disco_sao_copiados_para_o_banco(app, auditoria_registrada):
    """Bancos da versao antiga: o conteudo estava so em disco e e importado no inicio."""
    from auditoria_suporte import create_app
    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import ArquivoAuditoria

    relativo = auditoria_registrada["arquivos"]["json"]
    original = _conteudo(app, relativo)
    with app.app_context():
        db.session.execute(db.update(ArquivoAuditoria).values(conteudo=None))
        db.session.commit()

    pasta = app.config["PASTA_LEGADA_AUDITORIAS"]
    destino = pasta / relativo
    destino.parent.mkdir(parents=True)
    destino.write_text(original, encoding="utf-8")

    create_app({k: app.config[k] for k in (
        "TESTING", "SECRET_KEY", "INSTANCE_DIR", "PASTA_LEGADA_AUDITORIAS", "SQLALCHEMY_DATABASE_URI"
    )})

    assert _conteudo(app, relativo) == original


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
