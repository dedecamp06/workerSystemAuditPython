"""Cadastro, validacao e desativacao de clientes."""
from sqlalchemy import func

from ..extensions import db
from ..models.cliente import Cliente
from .armazenamento_service import garantir_pasta_cliente, nome_pasta_cliente
from .utilitarios import converter_decimal, email_valido, slug, texto_limpo


def validar_dados(dados, cliente=None):
    erros = []
    limpos = {
        "nome": texto_limpo(dados.get("nome"), 160),
        "codigo": texto_limpo(dados.get("codigo"), 40).upper(),
        "descricao": texto_limpo(dados.get("descricao"), 2000) or None,
        "contato": texto_limpo(dados.get("contato"), 120) or None,
        "email": texto_limpo(dados.get("email"), 160).lower() or None,
        "nota_minima": None,
    }

    if not limpos["nome"]:
        erros.append("Informe o nome do cliente.")

    if not limpos["codigo"]:
        limpos["codigo"] = slug(limpos["nome"], 30).upper() if limpos["nome"] else ""
    if limpos["codigo"] and not slug(limpos["codigo"]):
        erros.append("O identificador do cliente e invalido.")

    if limpos["email"] and not email_valido(limpos["email"]):
        erros.append("Informe um e-mail valido ou deixe o campo em branco.")

    try:
        nota = converter_decimal(dados.get("nota_minima") or 70, "nota minima")
        if nota < 0 or nota > 100:
            erros.append("A nota minima deve estar entre 0 e 100.")
        limpos["nota_minima"] = nota
    except ValueError as erro:
        erros.append(str(erro))

    if limpos["codigo"]:
        consulta = db.select(Cliente.id).where(
            func.upper(Cliente.codigo) == limpos["codigo"].upper()
        )
        if cliente is not None:
            consulta = consulta.where(Cliente.id != cliente.id)
        if db.session.scalar(consulta):
            erros.append(f"Ja existe um cliente com o identificador '{limpos['codigo']}'.")

    return limpos, erros


def criar_cliente(dados) -> Cliente:
    limpos, erros = validar_dados(dados)
    if erros:
        raise ValueError(erros)

    cliente = Cliente(**limpos, ativo=True)
    db.session.add(cliente)
    db.session.flush()  # necessario para compor o nome da pasta com o id
    cliente.pasta = nome_pasta_cliente(cliente)
    garantir_pasta_cliente(cliente)
    db.session.commit()
    return cliente


def atualizar_cliente(cliente, dados) -> Cliente:
    limpos, erros = validar_dados(dados, cliente=cliente)
    if erros:
        raise ValueError(erros)
    for campo, valor in limpos.items():
        setattr(cliente, campo, valor)
    cliente.ativo = str(dados.get("ativo", "1")) in ("1", "true", "on", "True")
    if not cliente.pasta:
        cliente.pasta = nome_pasta_cliente(cliente)
    garantir_pasta_cliente(cliente)
    db.session.commit()
    return cliente


def excluir_ou_desativar(cliente):
    """Exclui o cliente apenas quando nao houver vinculos.

    Com atendimentos, criterios ou auditorias vinculados, o cliente e apenas
    desativado para preservar o historico. Retorna ``'excluido'`` ou
    ``'desativado'``.
    """
    if cliente.possui_vinculos:
        cliente.ativo = False
        db.session.commit()
        return "desativado"
    db.session.delete(cliente)
    db.session.commit()
    return "excluido"
