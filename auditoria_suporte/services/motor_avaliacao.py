"""Motor de avaliacao baseado em regras configuraveis.

Este modulo e intencionalmente independente do Flask e do banco de dados:
ele recebe o conteudo do atendimento e os criterios do cliente e devolve uma
avaliacao por criterio. Isso permite substituir ou ampliar o mecanismo
(por exemplo, por um modelo de linguagem) sem alterar telas ou rotas.

LIMITACAO CONHECIDA E DECLARADA: a verificacao e lexical (busca de termos
configurados, sem acentos e sem diferenciar maiusculas). Nao se trata de
analise semantica. Quando a evidencia e parcial, ausente de contexto ou o
conteudo e curto demais, o criterio e marcado como INCONCLUSIVO e encaminhado
para revisao humana, em vez de receber aprovacao automatica.
"""
import re
from dataclasses import dataclass, field

from ..models.auditoria import ATENDIDO, INCONCLUSIVO, NAO_APLICAVEL, NAO_ATENDIDO
from .utilitarios import normalizar_texto

VERSAO_MOTOR = "regras_v1"
TAMANHO_MINIMO_CONTEUDO = 120
JANELA_EVIDENCIA = 70


@dataclass
class AvaliacaoCriterio:
    """Resultado da avaliacao de um criterio (ainda nao persistido)."""

    criterio_id: int
    nome: str
    descricao: str
    peso: float
    obrigatorio: bool
    status: str
    pontuacao: float
    considerado_no_calculo: bool
    justificativa: str
    confianca: str = "media"
    evidencias: list = field(default_factory=list)
    ajustado_manualmente: bool = False

    @property
    def evidencias_texto(self) -> str:
        return "\n".join(self.evidencias)


def _localizar(texto_normalizado: str, termo: str):
    """Retorna a posicao do termo no texto ou -1.

    Termos de uma unica palavra usam limites de palavra para evitar falsos
    positivos (por exemplo, 'ola' dentro de 'olaria').
    """
    termo_norm = normalizar_texto(termo).strip()
    if not termo_norm:
        return -1
    if " " in termo_norm:
        return texto_normalizado.find(termo_norm)
    padrao = re.compile(rf"(?<![0-9a-z]){re.escape(termo_norm)}(?![0-9a-z])")
    encontrado = padrao.search(texto_normalizado)
    return encontrado.start() if encontrado else -1


def _evidencia(texto_original: str, posicao: int, termo: str) -> str:
    inicio = max(0, posicao - JANELA_EVIDENCIA)
    fim = min(len(texto_original), posicao + len(termo) + JANELA_EVIDENCIA)
    trecho = " ".join(texto_original[inicio:fim].split())
    prefixo = "..." if inicio > 0 else ""
    sufixo = "..." if fim < len(texto_original) else ""
    return f'"{termo}" -> {prefixo}{trecho}{sufixo}'


def _buscar_termos(texto_original, texto_normalizado, termos):
    encontrados, evidencias = [], []
    for termo in termos:
        posicao = _localizar(texto_normalizado, termo)
        if posicao >= 0:
            encontrados.append(termo)
            evidencias.append(_evidencia(texto_original, posicao, termo))
    return encontrados, evidencias


def avaliar_criterio(criterio, conteudo: str, tamanho_minimo: int = TAMANHO_MINIMO_CONTEUDO):
    """Avalia um unico criterio contra o conteudo do atendimento."""
    conteudo = conteudo or ""
    normalizado = normalizar_texto(conteudo)

    base = dict(
        criterio_id=criterio.id,
        nome=criterio.nome,
        descricao=criterio.descricao or "",
        peso=float(criterio.peso),
        obrigatorio=bool(criterio.obrigatorio),
    )

    esperados = criterio.lista_esperados
    proibidos = criterio.lista_proibidos
    contexto = criterio.lista_contexto

    # 1) Termos proibidos encontrados => criterio nao atendido (evidencia direta)
    achados_proibidos, evidencias_proibidas = _buscar_termos(conteudo, normalizado, proibidos)
    if achados_proibidos:
        return AvaliacaoCriterio(
            status=NAO_ATENDIDO,
            pontuacao=0.0,
            considerado_no_calculo=True,
            confianca="alta",
            justificativa=(
                "Foram localizados termos que violam o criterio: "
                + ", ".join(achados_proibidos)
                + "."
            ),
            evidencias=evidencias_proibidas,
            **base,
        )

    # 2) Criterio sem regras configuradas => nao ha como decidir automaticamente
    if not esperados:
        return AvaliacaoCriterio(
            status=INCONCLUSIVO,
            pontuacao=0.0,
            considerado_no_calculo=True,
            confianca="baixa",
            justificativa=(
                "Criterio sem termos esperados configurados: a verificacao automatica "
                "nao e possivel. Necessaria revisao humana."
            ),
            **base,
        )

    # 3) Contexto ausente e criterio aceita 'nao aplicavel'
    if contexto:
        achados_contexto, _ = _buscar_termos(conteudo, normalizado, contexto)
        if not achados_contexto and criterio.permite_nao_aplicavel:
            return AvaliacaoCriterio(
                status=NAO_APLICAVEL,
                pontuacao=0.0,
                considerado_no_calculo=False,
                confianca="media",
                justificativa=(
                    "Nenhum termo de contexto ("
                    + ", ".join(contexto)
                    + ") foi localizado no atendimento: o criterio foi considerado "
                    "nao aplicavel e desconsiderado do calculo."
                ),
                **base,
            )

    achados, evidencias = _buscar_termos(conteudo, normalizado, esperados)
    minimo = max(1, min(int(criterio.minimo_termos or 1), len(esperados)))

    # 4) Evidencia suficiente => atendido
    if len(achados) >= minimo:
        return AvaliacaoCriterio(
            status=ATENDIDO,
            pontuacao=float(criterio.peso),
            considerado_no_calculo=True,
            confianca="alta" if len(achados) == len(esperados) else "media",
            justificativa=(
                f"Evidencia localizada para {len(achados)} de {len(esperados)} termos "
                f"esperados (minimo exigido: {minimo})."
            ),
            evidencias=evidencias,
            **base,
        )

    # 5) Evidencia parcial => inconclusivo
    if achados:
        return AvaliacaoCriterio(
            status=INCONCLUSIVO,
            pontuacao=0.0,
            considerado_no_calculo=True,
            confianca="baixa",
            justificativa=(
                f"Evidencia parcial: {len(achados)} de {minimo} termos exigidos "
                "foram localizados. Verificacao lexical insuficiente para decidir; "
                "necessaria revisao humana."
            ),
            evidencias=evidencias,
            **base,
        )

    # 6) Conteudo curto demais para uma conclusao confiavel
    if len(conteudo.strip()) < tamanho_minimo:
        return AvaliacaoCriterio(
            status=INCONCLUSIVO,
            pontuacao=0.0,
            considerado_no_calculo=True,
            confianca="baixa",
            justificativa=(
                "Conteudo do atendimento curto demais ("
                f"{len(conteudo.strip())} caracteres) para uma conclusao confiavel. "
                "Necessaria revisao humana."
            ),
            **base,
        )

    # 7) Nenhuma evidencia encontrada em conteudo suficiente => nao atendido
    return AvaliacaoCriterio(
        status=NAO_ATENDIDO,
        pontuacao=0.0,
        considerado_no_calculo=True,
        confianca="media",
        justificativa=(
            "Nenhum dos termos esperados ("
            + ", ".join(esperados)
            + ") foi localizado no conteudo do atendimento."
        ),
        **base,
    )


def avaliar(criterios, conteudo: str, tamanho_minimo: int = TAMANHO_MINIMO_CONTEUDO):
    """Avalia uma lista de criterios e devolve as avaliacoes correspondentes."""
    return [avaliar_criterio(criterio, conteudo, tamanho_minimo) for criterio in criterios]
