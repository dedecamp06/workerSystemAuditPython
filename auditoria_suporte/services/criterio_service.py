"""Cadastro e validacao dos criterios de auditoria."""
from sqlalchemy import func

from ..extensions import db
from ..models.criterio import Criterio
from .utilitarios import converter_decimal, texto_limpo


def validar_dados(cliente, dados, criterio=None):
    erros = []
    limpos = {
        "nome": texto_limpo(dados.get("nome"), 160),
        "descricao": texto_limpo(dados.get("descricao"), 2000) or None,
        "termos_esperados": texto_limpo(dados.get("termos_esperados"), 2000) or None,
        "termos_proibidos": texto_limpo(dados.get("termos_proibidos"), 2000) or None,
        "termos_contexto": texto_limpo(dados.get("termos_contexto"), 2000) or None,
        "obrigatorio": str(dados.get("obrigatorio", "")) in ("1", "on", "true", "True"),
        "permite_nao_aplicavel": str(dados.get("permite_nao_aplicavel", "")) in ("1", "on", "true", "True"),
        "ativo": str(dados.get("ativo", "1")) in ("1", "on", "true", "True"),
        "peso": None,
        "minimo_termos": 1,
    }

    if not limpos["nome"]:
        erros.append("Informe o nome do criterio.")

    try:
        peso = converter_decimal(dados.get("peso"), "peso")
        if peso <= 0:
            erros.append("O peso do criterio deve ser maior que zero.")
        else:
            limpos["peso"] = peso
    except ValueError as erro:
        erros.append(str(erro))

    bruto_minimo = str(dados.get("minimo_termos") or "1").strip()
    if not bruto_minimo.isdigit() or int(bruto_minimo) < 1:
        erros.append("O minimo de termos deve ser um numero inteiro maior ou igual a 1.")
    else:
        limpos["minimo_termos"] = int(bruto_minimo)

    if limpos["permite_nao_aplicavel"] and not limpos["termos_contexto"]:
        erros.append(
            "Para permitir 'nao aplicavel' e necessario informar os termos de contexto "
            "que indicam quando o criterio se aplica."
        )

    if limpos["nome"]:
        consulta = db.select(Criterio.id).where(
            Criterio.cliente_id == cliente.id,
            func.lower(Criterio.nome) == limpos["nome"].lower(),
        )
        if criterio is not None:
            consulta = consulta.where(Criterio.id != criterio.id)
        if db.session.scalar(consulta):
            erros.append(
                f"O cliente {cliente.nome} ja possui um criterio chamado '{limpos['nome']}'."
            )

    return limpos, erros


def criar_criterio(cliente, dados) -> Criterio:
    limpos, erros = validar_dados(cliente, dados)
    if erros:
        raise ValueError(erros)
    criterio = Criterio(cliente_id=cliente.id, **limpos)
    db.session.add(criterio)
    db.session.commit()
    return criterio


def atualizar_criterio(criterio, dados) -> Criterio:
    limpos, erros = validar_dados(criterio.cliente, dados, criterio=criterio)
    if erros:
        raise ValueError(erros)
    for campo, valor in limpos.items():
        setattr(criterio, campo, valor)
    db.session.commit()
    return criterio


def excluir_ou_desativar(criterio):
    """Preserva o historico: criterios ja usados em auditorias sao desativados."""
    if criterio.utilizado_em_auditorias:
        criterio.ativo = False
        db.session.commit()
        return "desativado"
    db.session.delete(criterio)
    db.session.commit()
    return "excluido"
