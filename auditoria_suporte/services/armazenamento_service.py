"""Armazenamento automatico dos resultados em pastas por cliente.

Estrutura gerada dentro de ``auditorias/``:

    auditorias/
        cliente_1_acme/
            atendimento_1/
                resultado_auditoria.json
                resultado_auditoria.txt
                resultado_auditoria_v2.json   (reauditoria)
                resultado_auditoria_v2.txt

Nenhum arquivo e sobrescrito: cada execucao tem o seu proprio nome.
A gravacao so e considerada concluida depois da releitura e da conferencia
do tamanho do arquivo em disco.
"""
import hashlib
import json
from datetime import datetime
from pathlib import Path

from flask import current_app

from ..models.auditoria import NAO_APLICAVEL
from .utilitarios import slug


class ErroArmazenamento(Exception):
    """Falha ao gravar ou localizar um arquivo de resultado."""


def diretorio_base() -> Path:
    base = Path(current_app.config["AUDIT_STORAGE_DIR"])
    base.mkdir(parents=True, exist_ok=True)
    return base.resolve()


def nome_pasta_cliente(cliente) -> str:
    """Nome de pasta unico e seguro para o cliente."""
    return f"cliente_{cliente.id}_{slug(cliente.codigo or cliente.nome)}"


def garantir_pasta_cliente(cliente) -> Path:
    if not cliente.pasta:
        cliente.pasta = nome_pasta_cliente(cliente)
    caminho = caminho_seguro(cliente.pasta)
    caminho.mkdir(parents=True, exist_ok=True)
    return caminho


def caminho_seguro(relativo: str) -> Path:
    """Resolve um caminho relativo garantindo que ele fique dentro da base.

    Protege contra travessia de diretorio (``..``) e caminhos absolutos.
    """
    base = diretorio_base()
    relativo = str(relativo or "").replace("\\", "/").strip("/")
    if not relativo:
        raise ErroArmazenamento("Caminho de arquivo nao informado.")
    destino = (base / relativo).resolve()
    if destino != base and base not in destino.parents:
        raise ErroArmazenamento("Caminho de arquivo fora do diretorio de auditorias.")
    return destino


def caminho_absoluto(arquivo) -> Path:
    """Caminho em disco de um ``ArquivoAuditoria`` ja registrado."""
    destino = caminho_seguro(arquivo.caminho_relativo)
    if not destino.is_file():
        raise ErroArmazenamento(
            f"Arquivo de resultado nao encontrado em disco: {arquivo.caminho_relativo}"
        )
    return destino


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


def _nome_base(auditoria, pasta_atendimento: Path) -> str:
    base = "resultado_auditoria" if auditoria.versao <= 1 else f"resultado_auditoria_v{auditoria.versao}"
    nome = base
    sufixo = 1
    while (pasta_atendimento / f"{nome}.json").exists() or (
        pasta_atendimento / f"{nome}.txt"
    ).exists():
        sufixo += 1
        nome = f"{base}_{sufixo}"
    return nome


def _gravar_e_conferir(destino: Path, conteudo: str) -> dict:
    destino.write_text(conteudo, encoding="utf-8")
    if not destino.is_file():
        raise ErroArmazenamento(f"O arquivo {destino.name} nao foi criado.")
    gravado = destino.read_text(encoding="utf-8")
    if gravado != conteudo:
        raise ErroArmazenamento(f"O conteudo gravado em {destino.name} nao confere.")
    tamanho = destino.stat().st_size
    if tamanho <= 0:
        raise ErroArmazenamento(f"O arquivo {destino.name} foi criado vazio.")
    return {
        "tamanho_bytes": tamanho,
        "sha256": hashlib.sha256(conteudo.encode("utf-8")).hexdigest(),
    }


def gravar_resultado(auditoria) -> list:
    """Grava os arquivos JSON e TXT da auditoria.

    Retorna uma lista de dicionarios com os dados de cada arquivo gravado.
    Lanca ``ErroArmazenamento`` quando a gravacao nao pode ser confirmada.
    """
    cliente = auditoria.cliente
    atendimento = auditoria.atendimento

    if atendimento.cliente_id != cliente.id:
        raise ErroArmazenamento(
            "Inconsistencia de vinculo: o atendimento nao pertence ao cliente da auditoria."
        )

    try:
        pasta_cliente = garantir_pasta_cliente(cliente)
        pasta_atendimento = caminho_seguro(f"{cliente.pasta}/{atendimento.pasta}")
        pasta_atendimento.mkdir(parents=True, exist_ok=True)
    except ErroArmazenamento:
        raise
    except OSError as erro:
        raise ErroArmazenamento(f"Nao foi possivel criar as pastas do cliente: {erro}")

    payload = montar_payload(auditoria)
    nome_base = _nome_base(auditoria, pasta_atendimento)

    arquivos = []
    gravados = []
    try:
        for tipo, conteudo in (
            ("json", json.dumps(payload, ensure_ascii=False, indent=2)),
            ("txt", montar_texto(payload)),
        ):
            destino = pasta_atendimento / f"{nome_base}.{tipo}"
            info = _gravar_e_conferir(destino, conteudo)
            gravados.append(destino)
            arquivos.append(
                {
                    "tipo": tipo,
                    "caminho_relativo": (
                        f"{cliente.pasta}/{atendimento.pasta}/{destino.name}"
                    ),
                    **info,
                }
            )
    except (OSError, ErroArmazenamento) as erro:
        for parcial in gravados:  # nao deixa resultado incompleto em disco
            try:
                parcial.unlink(missing_ok=True)
            except OSError:
                pass
        raise ErroArmazenamento(f"Falha ao gravar o resultado da auditoria: {erro}")

    _ = pasta_cliente  # pasta garantida acima
    return arquivos


def contar_arquivos_cliente(cliente) -> int:
    try:
        pasta = caminho_seguro(cliente.pasta) if cliente.pasta else None
    except ErroArmazenamento:
        return 0
    if not pasta or not pasta.is_dir():
        return 0
    return sum(1 for _ in pasta.rglob("*") if _.is_file())


__all__ = [
    "ErroArmazenamento",
    "caminho_absoluto",
    "caminho_seguro",
    "contar_arquivos_cliente",
    "diretorio_base",
    "garantir_pasta_cliente",
    "gravar_resultado",
    "montar_payload",
    "montar_texto",
    "nome_pasta_cliente",
    "NAO_APLICAVEL",
]
