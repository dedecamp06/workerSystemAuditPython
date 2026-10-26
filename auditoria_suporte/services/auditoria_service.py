"""Execucao, consolidacao e registro das auditorias."""
from datetime import datetime

from ..extensions import db
from ..models.auditoria import (
    APROVADO,
    ATENDIDO,
    INCONCLUSIVO,
    NAO_APLICAVEL,
    NAO_ATENDIDO,
    PENDENTE_REVISAO,
    REPROVADO,
    STATUS_CRITERIO,
    ArquivoAuditoria,
    Auditoria,
    ResultadoCriterio,
)
from . import motor_avaliacao
from .armazenamento_service import ErroArmazenamento, gravar_resultado
from .utilitarios import texto_limpo


class ErroAuditoria(Exception):
    """Impedimento de negocio para executar ou registrar a auditoria."""


def criterios_do_cliente(cliente):
    """Criterios ativos do cliente, com validacao rigorosa do vinculo."""
    criterios = [c for c in cliente.criterios if c.ativo]
    for criterio in criterios:
        if criterio.cliente_id != cliente.id:  # defesa contra vinculo incorreto
            raise ErroAuditoria(
                f"O criterio '{criterio.nome}' nao pertence ao cliente {cliente.nome}."
            )
    return sorted(criterios, key=lambda c: (not c.obrigatorio, c.nome.lower()))


def preparar_avaliacao(atendimento, tamanho_minimo=None):
    """Executa o motor de regras e devolve a avaliacao sugerida por criterio."""
    cliente = atendimento.cliente
    if cliente is None:
        raise ErroAuditoria("O atendimento nao possui cliente vinculado.")
    if not cliente.ativo:
        raise ErroAuditoria(
            f"O cliente {cliente.nome} esta inativo. Reative-o para auditar."
        )

    criterios = criterios_do_cliente(cliente)
    if not criterios:
        raise ErroAuditoria(
            f"O cliente {cliente.nome} nao possui criterios de auditoria ativos. "
            "Cadastre os criterios antes de auditar."
        )

    if tamanho_minimo is None:
        tamanho_minimo = motor_avaliacao.TAMANHO_MINIMO_CONTEUDO
    return motor_avaliacao.avaliar(criterios, atendimento.conteudo, tamanho_minimo)


def consolidar(avaliacoes, nota_minima: float) -> dict:
    """Consolida as avaliacoes em pontuacao final e situacao geral."""
    aplicaveis = [a for a in avaliacoes if a.considerado_no_calculo]
    soma_pesos = round(sum(a.peso for a in aplicaveis), 4)
    soma_pontos = round(sum(a.pontuacao for a in aplicaveis), 4)

    obrigatorios_falhos = [a for a in avaliacoes if a.obrigatorio and a.status == NAO_ATENDIDO]
    inconclusivos = [a for a in avaliacoes if a.status == INCONCLUSIVO]
    nao_aplicaveis = [a for a in avaliacoes if a.status == NAO_APLICAVEL]

    if soma_pesos > 0:
        pontuacao = round((soma_pontos / soma_pesos) * 100, 2)
    else:
        pontuacao = None

    requer_revisao = bool(inconclusivos) or pontuacao is None

    if obrigatorios_falhos:
        situacao = REPROVADO
    elif pontuacao is None or inconclusivos:
        situacao = PENDENTE_REVISAO
    elif pontuacao >= float(nota_minima):
        situacao = APROVADO
    else:
        situacao = REPROVADO

    linhas = [
        f"Criterios avaliados: {len(avaliacoes)} "
        f"(aplicaveis no calculo: {len(aplicaveis)}; nao aplicaveis: {len(nao_aplicaveis)}).",
        f"Soma dos pesos aplicaveis: {soma_pesos:.2f}.",
        f"Soma dos pontos obtidos: {soma_pontos:.2f}.",
        "Formula: (pontos obtidos / pesos aplicaveis) x 100 = "
        + ("nao calculavel (nenhum peso aplicavel)." if pontuacao is None else f"{pontuacao:.2f}%."),
        f"Nota minima do cliente: {float(nota_minima):.2f}%.",
    ]
    if obrigatorios_falhos:
        linhas.append(
            "Criterios obrigatorios nao atendidos: "
            + ", ".join(a.nome for a in obrigatorios_falhos)
            + " (reprovacao independente da pontuacao)."
        )
    if inconclusivos:
        linhas.append(
            "Criterios inconclusivos encaminhados para revisao humana: "
            + ", ".join(a.nome for a in inconclusivos)
            + "."
        )
    linhas.append(f"Situacao atribuida: {situacao}.")

    return {
        "soma_pesos": soma_pesos,
        "soma_pontos": soma_pontos,
        "pontuacao_final": pontuacao,
        "situacao": situacao,
        "requer_revisao_humana": requer_revisao,
        "obrigatorios_nao_atendidos": obrigatorios_falhos,
        "inconclusivos": inconclusivos,
        "resumo_calculo": "\n".join(linhas),
    }


def aplicar_ajustes(avaliacoes, formulario, criterios_por_id):
    """Aplica revisao humana sobre a avaliacao sugerida pelo motor.

    ``formulario`` e o ``request.form``. Campos esperados por criterio:
    ``status_<id>`` e ``justificativa_<id>``.
    Retorna ``(avaliacoes, erros, houve_ajuste)``.
    """
    erros = []
    houve_ajuste = False

    for avaliacao in avaliacoes:
        chave = avaliacao.criterio_id
        status = texto_limpo(formulario.get(f"status_{chave}")) or avaliacao.status
        justificativa = texto_limpo(formulario.get(f"justificativa_{chave}"), 4000)

        if status not in STATUS_CRITERIO:
            erros.append(f"Status invalido informado para o criterio '{avaliacao.nome}'.")
            continue

        criterio = criterios_por_id.get(chave)
        if status == NAO_APLICAVEL:
            if criterio is not None and not criterio.permite_nao_aplicavel:
                erros.append(
                    f"O criterio '{avaliacao.nome}' nao permite o status "
                    "'Nao aplicavel'. Ajuste o cadastro do criterio."
                )
                continue
            if not justificativa:
                erros.append(
                    f"Informe a justificativa para considerar o criterio "
                    f"'{avaliacao.nome}' nao aplicavel."
                )
                continue
        if status == NAO_ATENDIDO and not justificativa:
            erros.append(
                f"Informe a justificativa para o criterio nao atendido '{avaliacao.nome}'."
            )
            continue

        if status != avaliacao.status or justificativa != avaliacao.justificativa:
            avaliacao.ajustado_manualmente = True
            houve_ajuste = True

        avaliacao.status = status
        avaliacao.justificativa = justificativa or avaliacao.justificativa
        avaliacao.pontuacao = float(avaliacao.peso) if status == ATENDIDO else 0.0
        avaliacao.considerado_no_calculo = status != NAO_APLICAVEL
        if avaliacao.ajustado_manualmente:
            avaliacao.confianca = "revisada"

    return avaliacoes, erros, houve_ajuste


def proxima_versao(atendimento) -> int:
    if not atendimento.auditorias:
        return 1
    return max(a.versao for a in atendimento.auditorias) + 1


def registrar_auditoria(
    atendimento,
    usuario,
    avaliacoes,
    observacoes=None,
    ajustada_manualmente=False,
    metodo=None,
):
    """Persiste a auditoria, os resultados por criterio e os arquivos gerados.

    A transacao somente e confirmada depois da gravacao dos arquivos em disco.
    Em caso de falha no armazenamento, nada e persistido e
    ``ErroArmazenamento`` e propagado.
    """
    cliente = atendimento.cliente
    if cliente is None:
        raise ErroAuditoria("O atendimento nao possui cliente vinculado.")
    if not avaliacoes:
        raise ErroAuditoria("Nenhum criterio foi avaliado.")

    ids_do_cliente = {c.id for c in cliente.criterios}
    for avaliacao in avaliacoes:
        if avaliacao.criterio_id not in ids_do_cliente:
            raise ErroAuditoria(
                "Criterio de outro cliente detectado na auditoria. Operacao cancelada."
            )

    consolidado = consolidar(avaliacoes, cliente.nota_minima)

    auditoria = Auditoria(
        atendimento_id=atendimento.id,
        cliente_id=cliente.id,
        usuario_id=usuario.id if usuario else None,
        versao=proxima_versao(atendimento),
        executada_em=datetime.now(),
        metodo=metodo or motor_avaliacao.VERSAO_MOTOR,
        soma_pesos=consolidado["soma_pesos"],
        soma_pontos=consolidado["soma_pontos"],
        pontuacao_final=consolidado["pontuacao_final"],
        nota_minima_aplicada=float(cliente.nota_minima),
        situacao=consolidado["situacao"],
        requer_revisao_humana=consolidado["requer_revisao_humana"],
        ajustada_manualmente=bool(ajustada_manualmente),
        observacoes=texto_limpo(observacoes, 4000) or None,
        resumo_calculo=consolidado["resumo_calculo"],
    )
    auditoria.atendimento = atendimento
    auditoria.cliente = cliente

    for ordem, avaliacao in enumerate(avaliacoes, start=1):
        auditoria.resultados.append(
            ResultadoCriterio(
                criterio_id=avaliacao.criterio_id,
                ordem=ordem,
                criterio_nome=avaliacao.nome,
                criterio_descricao=avaliacao.descricao,
                peso=float(avaliacao.peso),
                obrigatorio=bool(avaliacao.obrigatorio),
                status=avaliacao.status,
                pontuacao=float(avaliacao.pontuacao),
                considerado_no_calculo=bool(avaliacao.considerado_no_calculo),
                justificativa=avaliacao.justificativa,
                evidencias=avaliacao.evidencias_texto or None,
                confianca=avaliacao.confianca,
                ajustado_manualmente=bool(avaliacao.ajustado_manualmente),
            )
        )

    db.session.add(auditoria)
    try:
        db.session.flush()  # garante o id da auditoria para nomear os arquivos
        arquivos = gravar_resultado(auditoria)
        for dados in arquivos:
            auditoria.arquivos.append(ArquivoAuditoria(**dados))
        db.session.commit()
    except ErroArmazenamento:
        db.session.rollback()
        raise
    except Exception as erro:  # pragma: no cover - falhas inesperadas de banco
        db.session.rollback()
        raise ErroAuditoria(f"Nao foi possivel registrar a auditoria: {erro}")

    return auditoria
