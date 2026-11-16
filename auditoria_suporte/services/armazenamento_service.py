"""Armazenamento automatico dos resultados da auditoria.

Os arquivos JSON e TXT de cada auditoria ficam guardados no proprio banco de
dados (tabela ``arquivos_auditoria``, coluna ``conteudo``). Assim o sistema
funciona em hospedagens sem disco permanente (Vercel, Heroku etc.).

Cada arquivo continua tendo um caminho logico organizado por cliente, usado
como nome no download e para manter a separacao entre clientes:

    cliente_1_acme/atendimento_1/resultado_auditoria.json
    cliente_1_acme/atendimento_1/resultado_auditoria_v2.json   (reauditoria)

Nenhum resultado e sobrescrito: cada execucao tem o seu proprio nome.
A gravacao so e considerada concluida depois da conferencia do conteudo,
do tamanho e do hash SHA-256.
"""
import hashlib
import json
from datetime import datetime

from ..extensions import db
from ..models.auditoria import NAO_APLICAVEL, ArquivoAuditoria, Auditoria
from .utilitarios import slug


class ErroArmazenamento(Exception):
    """Falha ao gravar ou localizar um arquivo de resultado."""


def nome_pasta_cliente(cliente) -> str:
    """Nome de pasta logica unico e seguro para o cliente."""
    return f"cliente_{cliente.id}_{slug(cliente.codigo or cliente.nome)}"


def garantir_pasta_cliente(cliente) -> str:
    """Garante que o cliente tenha o nome da sua pasta logica definido."""
    if not cliente.pasta:
        cliente.pasta = nome_pasta_cliente(cliente)
    return cliente.pasta


def conteudo_do_arquivo(arquivo) -> str:
    """Conteudo de um ``ArquivoAuditoria`` ja registrado."""
    if not arquivo.conteudo:
        raise ErroArmazenamento(
            f"Conteudo do arquivo de resultado nao encontrado: {arquivo.caminho_relativo}"
        )
    return arquivo.conteudo


def montar_payload(auditoria) -> dict:
    """Monta o conteudo do arquivo JSON do resultado."""
    atendimento = auditoria.atendimento
    cliente = auditoria.cliente
    return {
        "auditoria": {
            "id": auditoria.id,
            "versao": auditoria.versao,
            "executada_em": auditoria.executada_em.strftime("%Y-%m-%d %H:%M:%S"),
            "metodo_avaliacao": auditoria.metodo,
            "ajustada_manualmente": bool(auditoria.ajustada_manualmente),
            "executada_por": auditoria.usuario.nome if auditoria.usuario else None,
        },
        "cliente": {
            "id": cliente.id,
            "codigo": cliente.codigo,
            "nome": cliente.nome,
            "pasta": cliente.pasta,
        },
        "atendimento": {
            "id": atendimento.id,
            "protocolo": atendimento.protocolo,
            "atendente": atendimento.atendente,
            "data_atendimento": atendimento.data_atendimento.strftime("%Y-%m-%d"),
            "canal": atendimento.canal,
            "origem": atendimento.origem,
        },
        "criterios": [
            {
                "criterio_id": r.criterio_id,
                "nome": r.criterio_nome,
                "descricao": r.criterio_descricao,
                "peso": r.peso,
                "obrigatorio": bool(r.obrigatorio),
                "status": r.status,
                "status_rotulo": r.rotulo_status,
                "pontuacao_obtida": r.pontuacao,
                "considerado_no_calculo": bool(r.considerado_no_calculo),
                "confianca": r.confianca,
                "justificativa": r.justificativa,
                "evidencias": [e for e in (r.evidencias or "").split("\n") if e],
                "ajustado_manualmente": bool(r.ajustado_manualmente),
            }
            for r in auditoria.resultados
        ],
        "pontuacao": {
            "soma_pesos_aplicaveis": auditoria.soma_pesos,
            "soma_pontos_obtidos": auditoria.soma_pontos,
            "pontuacao_final_percentual": auditoria.pontuacao_final,
            "nota_minima_aplicada": auditoria.nota_minima_aplicada,
            "formula": "(soma dos pontos obtidos / soma dos pesos aplicaveis) * 100",
            "resumo_calculo": auditoria.resumo_calculo,
        },
        "situacao_geral": auditoria.situacao,
        "situacao_geral_rotulo": auditoria.rotulo_situacao,
        "requer_revisao_humana": bool(auditoria.requer_revisao_humana),
        "criterios_obrigatorios_nao_atendidos": [
            r.criterio_nome for r in auditoria.obrigatorios_nao_atendidos
        ],
        "criterios_inconclusivos": [r.criterio_nome for r in auditoria.inconclusivos],
        "observacoes": auditoria.observacoes,
        "gerado_em": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def montar_texto(payload: dict) -> str:
    """Versao legivel (TXT) do resultado da auditoria."""
    linha = "=" * 72
    partes = [
        linha,
        "RESULTADO DA AUDITORIA DE ATENDIMENTO",
        linha,
        f"Auditoria ........: #{payload['auditoria']['id']} (versao {payload['auditoria']['versao']})",
        f"Executada em .....: {payload['auditoria']['executada_em']}",
        f"Metodo ...........: {payload['auditoria']['metodo_avaliacao']}",
        f"Executada por ....: {payload['auditoria']['executada_por'] or '-'}",
        "",
        f"Cliente ..........: {payload['cliente']['nome']} ({payload['cliente']['codigo']})",
        f"Atendimento ......: #{payload['atendimento']['id']} - {payload['atendimento']['protocolo']}",
        f"Atendente ........: {payload['atendimento']['atendente']}",
        f"Data atendimento .: {payload['atendimento']['data_atendimento']}",
        f"Canal ............: {payload['atendimento']['canal'] or '-'}",
        "",
        linha,
        "CRITERIOS AVALIADOS",
        linha,
    ]

    for indice, criterio in enumerate(payload["criterios"], start=1):
        marcador = " [OBRIGATORIO]" if criterio["obrigatorio"] else ""
        partes.append(f"{indice}. {criterio['nome']}{marcador}")
        partes.append(f"   Status .......: {criterio['status_rotulo']} (confianca {criterio['confianca']})")
        partes.append(f"   Peso .........: {criterio['peso']:.2f}")
        partes.append(f"   Pontuacao ....: {criterio['pontuacao_obtida']:.2f}")
        if not criterio["considerado_no_calculo"]:
            partes.append("   Calculo ......: desconsiderado (nao aplicavel)")
        partes.append(f"   Justificativa : {criterio['justificativa'] or '-'}")
        if criterio["evidencias"]:
            partes.append("   Evidencias ...:")
            for evidencia in criterio["evidencias"]:
                partes.append(f"      - {evidencia}")
        if criterio["ajustado_manualmente"]:
            partes.append("   Observacao ...: status ajustado manualmente pelo auditor")
        partes.append("")

    pontuacao = payload["pontuacao"]
    final = pontuacao["pontuacao_final_percentual"]
    partes += [
        linha,
        "PONTUACAO",
        linha,
        f"Soma dos pesos aplicaveis : {pontuacao['soma_pesos_aplicaveis']:.2f}",
        f"Soma dos pontos obtidos   : {pontuacao['soma_pontos_obtidos']:.2f}",
        f"Formula                   : {pontuacao['formula']}",
        f"Pontuacao final           : {'--' if final is None else format(final, '.2f') + '%'}",
        f"Nota minima aplicada      : {pontuacao['nota_minima_aplicada']:.2f}%",
        "",
        f"SITUACAO GERAL            : {payload['situacao_geral_rotulo'].upper()}",
        f"Revisao humana necessaria : {'SIM' if payload['requer_revisao_humana'] else 'NAO'}",
    ]

    if payload["criterios_obrigatorios_nao_atendidos"]:
        partes += [
            "",
            "!! CRITERIOS OBRIGATORIOS NAO ATENDIDOS:",
        ]
        partes += [f"   - {nome}" for nome in payload["criterios_obrigatorios_nao_atendidos"]]

    if payload["criterios_inconclusivos"]:
        partes += [
            "",
            "** CRITERIOS INCONCLUSIVOS (pendentes de revisao humana):",
        ]
        partes += [f"   - {nome}" for nome in payload["criterios_inconclusivos"]]

    if payload.get("observacoes"):
        partes += ["", "OBSERVACOES:", payload["observacoes"]]

    partes += ["", f"Arquivo gerado em {payload['gerado_em']}", linha, ""]
    return "\n".join(partes)


def _caminho_existe(caminho: str) -> bool:
    return (
        db.session.scalar(
            db.select(db.func.count(ArquivoAuditoria.id)).where(
                ArquivoAuditoria.caminho_relativo == caminho
            )
        )
        or 0
    ) > 0


def _nome_base(auditoria, prefixo: str) -> str:
    base = "resultado_auditoria" if auditoria.versao <= 1 else f"resultado_auditoria_v{auditoria.versao}"
    nome = base
    sufixo = 1
    while _caminho_existe(f"{prefixo}/{nome}.json") or _caminho_existe(f"{prefixo}/{nome}.txt"):
        sufixo += 1
        nome = f"{base}_{sufixo}"
    return nome


def _gravar_e_conferir(caminho: str, conteudo: str) -> dict:
    """Confere o conteudo gerado e devolve os metadados do arquivo."""
    if not conteudo:
        raise ErroArmazenamento(f"O arquivo {caminho} foi gerado vazio.")
    dados = conteudo.encode("utf-8")
    if dados.decode("utf-8") != conteudo:
        raise ErroArmazenamento(f"O conteudo de {caminho} nao confere.")
    return {
        "conteudo": conteudo,
        "tamanho_bytes": len(dados),
        "sha256": hashlib.sha256(dados).hexdigest(),
    }


def gravar_resultado(auditoria) -> list:
    """Gera os arquivos JSON e TXT da auditoria.

    Retorna uma lista de dicionarios prontos para criar ``ArquivoAuditoria``.
    A persistencia acontece na mesma transacao da auditoria: se algo falhar,
    nada e salvo. Lanca ``ErroArmazenamento`` quando a gravacao nao pode ser
    confirmada.
    """
    cliente = auditoria.cliente
    atendimento = auditoria.atendimento

    if atendimento.cliente_id != cliente.id:
        raise ErroArmazenamento(
            "Inconsistencia de vinculo: o atendimento nao pertence ao cliente da auditoria."
        )

    prefixo = f"{garantir_pasta_cliente(cliente)}/{atendimento.pasta}"
    payload = montar_payload(auditoria)
    nome_base = _nome_base(auditoria, prefixo)

    arquivos = []
    try:
        for tipo, conteudo in (
            ("json", json.dumps(payload, ensure_ascii=False, indent=2)),
            ("txt", montar_texto(payload)),
        ):
            caminho = f"{prefixo}/{nome_base}.{tipo}"
            info = _gravar_e_conferir(caminho, conteudo)
            arquivos.append({"tipo": tipo, "caminho_relativo": caminho, **info})
    except (OSError, ValueError, ErroArmazenamento) as erro:
        raise ErroArmazenamento(f"Falha ao gravar o resultado da auditoria: {erro}")

    return arquivos


def contar_arquivos_cliente(cliente) -> int:
    return (
        db.session.scalar(
            db.select(db.func.count(ArquivoAuditoria.id))
            .join(Auditoria, ArquivoAuditoria.auditoria_id == Auditoria.id)
            .where(Auditoria.cliente_id == cliente.id)
        )
        or 0
    )


__all__ = [
    "ErroArmazenamento",
    "conteudo_do_arquivo",
    "contar_arquivos_cliente",
    "garantir_pasta_cliente",
    "gravar_resultado",
    "montar_payload",
    "montar_texto",
    "nome_pasta_cliente",
    "NAO_APLICAVEL",
]
