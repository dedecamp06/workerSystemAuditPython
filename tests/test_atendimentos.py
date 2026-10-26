"""Testes de cadastro, validacao, importacao e vinculo dos atendimentos."""
import io
from datetime import date

from conftest import CONTEUDO_BOM, obter_csrf


def _arquivo(conteudo: str, nome: str):
    return (io.BytesIO(conteudo.encode("utf-8")), nome)


def test_cadastro_manual_de_atendimento(autenticado, app, cenario):
    token = obter_csrf(autenticado, "/atendimentos/novo")
    resposta = autenticado.post(
        "/atendimentos/novo",
        data={
            "cliente_id": cenario["cliente_a"],
            "protocolo": "ALFA-100",
            "atendente": "Pedro Alves",
            "data_atendimento": "2026-10-20",
            "canal": "chat",
            "conteudo": CONTEUDO_BOM,
            "_csrf_token": token,
        },
        follow_redirects=True,
    )
    assert "cadastrado com sucesso" in resposta.get_data(as_text=True)

    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Atendimento

    with app.app_context():
        atendimento = db.session.scalar(
            db.select(Atendimento).where(Atendimento.protocolo == "ALFA-100")
        )
        assert atendimento.cliente_id == cenario["cliente_a"]
        assert atendimento.data_atendimento == date(2026, 10, 20)
        assert atendimento.origem == "manual"


def test_campos_obrigatorios_do_atendimento(autenticado, cenario):
    token = obter_csrf(autenticado, "/atendimentos/novo")
    resposta = autenticado.post(
        "/atendimentos/novo",
        data={
            "cliente_id": cenario["cliente_a"],
            "atendente": "",
            "data_atendimento": "",
            "conteudo": "curto",
            "_csrf_token": token,
        },
    )
    texto = resposta.get_data(as_text=True)
    assert "Informe o atendente responsavel." in texto
    assert "Data nao informada." in texto
    assert "ao menos 20 caracteres" in texto


def test_protocolo_duplicado_no_mesmo_cliente_e_rejeitado(autenticado, cenario):
    token = obter_csrf(autenticado, "/atendimentos/novo")
    resposta = autenticado.post(
        "/atendimentos/novo",
        data={
            "cliente_id": cenario["cliente_a"],
            "protocolo": "ALFA-001",
            "atendente": "Outro",
            "data_atendimento": "2026-10-20",
            "conteudo": CONTEUDO_BOM,
            "_csrf_token": token,
        },
    )
    assert "Ja existe um atendimento com o protocolo" in resposta.get_data(as_text=True)


def test_protocolo_gerado_automaticamente(autenticado, app, cenario):
    token = obter_csrf(autenticado, "/atendimentos/novo")
    autenticado.post(
        "/atendimentos/novo",
        data={
            "cliente_id": cenario["cliente_b"],
            "atendente": "Auto",
            "data_atendimento": "2026-10-21",
            "conteudo": CONTEUDO_BOM,
            "_csrf_token": token,
        },
        follow_redirects=True,
    )

    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Atendimento

    with app.app_context():
        atendimento = db.session.scalar(
            db.select(Atendimento).where(Atendimento.cliente_id == cenario["cliente_b"])
        )
        assert atendimento.protocolo.startswith("ATD-BETA-")


def test_importacao_csv_com_sucesso_e_com_erros(autenticado, app, cenario):
    csv = (
        "protocolo;atendente;data_atendimento;canal;conteudo\n"
        f'IMP-001;Ana Paula;2026-10-20;telefone;"{CONTEUDO_BOM}"\n'
        f'IMP-002;Bruno Lima;21/10/2026;chat;"{CONTEUDO_BOM}"\n'
        'IMP-003;Sem Data;;chat;"conteudo valido com mais de vinte caracteres aqui"\n'
        'IMP-004;Curto;2026-10-20;chat;"abc"\n'
        f'IMP-001;Repetido;2026-10-20;chat;"{CONTEUDO_BOM}"\n'
    )
    token = obter_csrf(autenticado, "/atendimentos/importar")
    resposta = autenticado.post(
        "/atendimentos/importar",
        data={
            "cliente_id": cenario["cliente_a"],
            "arquivo": _arquivo(csv, "atendimentos.csv"),
            "_csrf_token": token,
        },
        content_type="multipart/form-data",
    )
    texto = resposta.get_data(as_text=True)
    # IMP-003 (sem data), IMP-004 (conteudo curto) e IMP-001 repetido sao rejeitados
    assert "2 atendimento(s) importado(s)" in texto
    assert "3 registro(s) com erro" in texto
    assert "Data nao informada" in texto

    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Atendimento

    with app.app_context():
        importados = db.session.scalars(
            db.select(Atendimento).where(Atendimento.origem == "importacao_csv")
        ).all()
        protocolos = sorted(a.protocolo for a in importados)
        assert "IMP-001" in protocolos and "IMP-002" in protocolos
        assert "IMP-004" not in protocolos  # conteudo curto
        for atendimento in importados:
            assert atendimento.cliente_id == cenario["cliente_a"]


def test_importacao_csv_sem_coluna_conteudo(autenticado, cenario):
    token = obter_csrf(autenticado, "/atendimentos/importar")
    resposta = autenticado.post(
        "/atendimentos/importar",
        data={
            "cliente_id": cenario["cliente_a"],
            "arquivo": _arquivo("protocolo;atendente\nX;Y\n", "ruim.csv"),
            "_csrf_token": token,
        },
        content_type="multipart/form-data",
    )
    assert "precisa de uma coluna de conteudo" in resposta.get_data(as_text=True)


def test_importacao_de_formato_nao_suportado(autenticado, cenario):
    token = obter_csrf(autenticado, "/atendimentos/importar")
    resposta = autenticado.post(
        "/atendimentos/importar",
        data={
            "cliente_id": cenario["cliente_a"],
            "arquivo": _arquivo("conteudo", "planilha.xlsx"),
            "_csrf_token": token,
        },
        content_type="multipart/form-data",
    )
    assert "Formato de arquivo nao suportado" in resposta.get_data(as_text=True)


def test_importacao_txt_em_blocos(autenticado, app, cenario):
    txt = (
        "protocolo: TXT-001\n"
        "atendente: Clara Dias\n"
        "data: 2026-10-22\n"
        "canal: email\n"
        "conteudo:\n"
        f"{CONTEUDO_BOM}\n"
        "---\n"
        "protocolo: TXT-002\n"
        "atendente: Diego Reis\n"
        "data: 22/10/2026\n"
        "conteudo:\n"
        f"{CONTEUDO_BOM}\n"
    )
    token = obter_csrf(autenticado, "/atendimentos/importar")
    resposta = autenticado.post(
        "/atendimentos/importar",
        data={
            "cliente_id": cenario["cliente_b"],
            "arquivo": _arquivo(txt, "transcricoes.txt"),
            "_csrf_token": token,
        },
        content_type="multipart/form-data",
    )
    assert "2 atendimento(s) importado(s)" in resposta.get_data(as_text=True)

    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Atendimento

    with app.app_context():
        registros = db.session.scalars(
            db.select(Atendimento).where(Atendimento.origem == "importacao_txt")
        ).all()
        assert {r.protocolo for r in registros} == {"TXT-001", "TXT-002"}
        for registro in registros:
            assert registro.cliente_id == cenario["cliente_b"]
            assert registro.atendente in ("Clara Dias", "Diego Reis")


def test_importacao_txt_sem_cabecalho_usa_dados_do_formulario(autenticado, app, cenario):
    token = obter_csrf(autenticado, "/atendimentos/importar")
    resposta = autenticado.post(
        "/atendimentos/importar",
        data={
            "cliente_id": cenario["cliente_a"],
            "atendente": "Atendente Padrao",
            "data_atendimento": "2026-10-23",
            "arquivo": _arquivo(CONTEUDO_BOM, "conversa_unica.txt"),
            "_csrf_token": token,
        },
        content_type="multipart/form-data",
    )
    assert "1 atendimento(s) importado(s)" in resposta.get_data(as_text=True)

    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Atendimento

    with app.app_context():
        registro = db.session.scalar(
            db.select(Atendimento).where(Atendimento.atendente == "Atendente Padrao")
        )
        assert registro is not None
        assert registro.protocolo == "CONVERSA-UNICA"
        assert registro.data_atendimento == date(2026, 10, 23)


def test_atendimento_auditado_nao_pode_ser_editado(autenticado, app, cenario):
    from auditoria_suporte.extensions import db
    from auditoria_suporte.models import Atendimento, Usuario
    from auditoria_suporte.services import auditoria_service

    with app.app_context():
        atendimento = db.session.get(Atendimento, cenario["atendimento_bom"])
        usuario = db.session.scalar(db.select(Usuario))
        avaliacoes = auditoria_service.preparar_avaliacao(atendimento)
        auditoria_service.registrar_auditoria(atendimento, usuario, avaliacoes)

    resposta = autenticado.get(
        f"/atendimentos/{cenario['atendimento_bom']}/editar", follow_redirects=True
    )
    assert "nao pode mais ser alterado" in resposta.get_data(as_text=True)

    token = obter_csrf(autenticado, f"/atendimentos/{cenario['atendimento_bom']}")
    resposta = autenticado.post(
        f"/atendimentos/{cenario['atendimento_bom']}/excluir",
        data={"_csrf_token": token},
        follow_redirects=True,
    )
    assert "nao podem ser excluidos" in resposta.get_data(as_text=True)
