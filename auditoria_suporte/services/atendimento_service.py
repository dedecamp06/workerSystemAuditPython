"""Cadastro manual e importacao (CSV/TXT) de atendimentos."""
import csv
import io
import re

from ..extensions import db
from ..models.atendimento import Atendimento
from .utilitarios import converter_data, slug, texto_limpo

TAMANHO_MINIMO_CONTEUDO = 20

# Nomes aceitos para cada coluna do CSV (sem acento, em minusculas)
COLUNAS = {
    "protocolo": ("protocolo", "identificador", "id", "codigo", "ticket", "chamado"),
    "atendente": ("atendente", "agente", "operador", "responsavel"),
    "data_atendimento": ("data_atendimento", "data", "dt_atendimento", "data_do_atendimento"),
    "canal": ("canal", "meio", "origem_contato"),
    "conteudo": ("conteudo", "transcricao", "conversa", "historico", "texto", "descricao"),
}

CABECALHO_CSV = "protocolo;atendente;data_atendimento;canal;conteudo"


class ErroImportacao(Exception):
    """Falha que impede o processamento do arquivo de importacao."""


def gerar_protocolo(cliente) -> str:
    """Gera um protocolo unico para o cliente (ex.: ATD-ACME-0007)."""
    prefixo = f"ATD-{slug(cliente.codigo).upper().replace('-', '')[:10]}"
    total = db.session.scalar(
        db.select(db.func.count(Atendimento.id)).where(Atendimento.cliente_id == cliente.id)
    ) or 0
    sequencia = total + 1
    while True:
        protocolo = f"{prefixo}-{sequencia:04d}"
        existe = db.session.scalar(
            db.select(Atendimento.id).where(
                Atendimento.cliente_id == cliente.id, Atendimento.protocolo == protocolo
            )
        )
        if not existe:
            return protocolo
        sequencia += 1


def protocolo_duplicado(cliente_id, protocolo, ignorar_id=None) -> bool:
    consulta = db.select(Atendimento.id).where(
        Atendimento.cliente_id == cliente_id, Atendimento.protocolo == protocolo
    )
    if ignorar_id:
        consulta = consulta.where(Atendimento.id != ignorar_id)
    return bool(db.session.scalar(consulta))


def validar_dados(cliente, dados, ignorar_id=None):
    """Valida os campos de um atendimento. Retorna ``(limpos, erros)``."""
    erros = []
    limpos = {
        "protocolo": texto_limpo(dados.get("protocolo"), 60),
        "atendente": texto_limpo(dados.get("atendente"), 120),
        "canal": texto_limpo(dados.get("canal"), 40) or None,
        "conteudo": (dados.get("conteudo") or "").strip(),
        "data_atendimento": None,
    }

    if not limpos["atendente"]:
        erros.append("Informe o atendente responsavel.")

    try:
        limpos["data_atendimento"] = converter_data(dados.get("data_atendimento"))
    except ValueError as erro:
        erros.append(str(erro))

    if not limpos["conteudo"]:
        erros.append("Informe o conteudo do atendimento.")
    elif len(limpos["conteudo"]) < TAMANHO_MINIMO_CONTEUDO:
        erros.append(
            f"O conteudo do atendimento deve ter ao menos {TAMANHO_MINIMO_CONTEUDO} caracteres."
        )

    if limpos["protocolo"]:
        if not re.fullmatch(r"[A-Za-z0-9._\-/]{2,60}", limpos["protocolo"]):
            erros.append(
                "O protocolo deve conter apenas letras, numeros, ponto, barra, hifen "
                "ou sublinhado (2 a 60 caracteres)."
            )
        elif protocolo_duplicado(cliente.id, limpos["protocolo"], ignorar_id):
            erros.append(
                f"Ja existe um atendimento com o protocolo '{limpos['protocolo']}' "
                "para este cliente."
            )
    elif ignorar_id is None:
        limpos["protocolo"] = gerar_protocolo(cliente)

    return limpos, erros


def criar_atendimento(cliente, dados, origem="manual"):
    """Cria e persiste um atendimento. Lanca ``ValueError`` com os erros."""
    limpos, erros = validar_dados(cliente, dados)
    if erros:
        raise ValueError(erros)

    atendimento = Atendimento(cliente_id=cliente.id, origem=origem, **limpos)
    db.session.add(atendimento)
    db.session.commit()
    return atendimento


def atualizar_atendimento(atendimento, dados):
    limpos, erros = validar_dados(atendimento.cliente, dados, ignorar_id=atendimento.id)
    if erros:
        raise ValueError(erros)
    if not limpos["protocolo"]:
        limpos["protocolo"] = atendimento.protocolo
    for campo, valor in limpos.items():
        setattr(atendimento, campo, valor)
    db.session.commit()
    return atendimento


# ---------------------------------------------------------------- importacao

def _decodificar(conteudo_bytes) -> str:
    for codificacao in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return conteudo_bytes.decode(codificacao)
        except UnicodeDecodeError:
            continue
    raise ErroImportacao("Nao foi possivel ler o arquivo: codificacao nao suportada.")


def _mapear_colunas(cabecalho):
    """Relaciona os nomes do arquivo com os campos internos."""
    mapa = {}
    for original in cabecalho or []:
        chave = slug(original or "").replace("-", "_")
        for campo, aliases in COLUNAS.items():
            if chave in aliases and campo not in mapa:
                mapa[campo] = original
    return mapa


def _detectar_delimitador(texto: str) -> str:
    amostra = "\n".join(texto.splitlines()[:5])
    try:
        return csv.Sniffer().sniff(amostra, delimiters=";,\t|").delimiter
    except csv.Error:
        return ";" if amostra.count(";") >= amostra.count(",") else ","


def importar_csv(cliente, texto, atendente_padrao=None, data_padrao=None):
    delimitador = _detectar_delimitador(texto)
    leitor = csv.DictReader(io.StringIO(texto), delimiter=delimitador)
    mapa = _mapear_colunas(leitor.fieldnames)

    if "conteudo" not in mapa:
        raise ErroImportacao(
            "O arquivo CSV precisa de uma coluna de conteudo. Colunas aceitas: "
            + ", ".join(COLUNAS["conteudo"])
            + ". Cabecalho esperado: "
            + CABECALHO_CSV
        )

    registros = []
    erros = []
    protocolos_no_arquivo = set()
    total_linhas = 0

    for numero, linha in enumerate(leitor, start=2):
        if not any((valor or "").strip() for valor in linha.values()):
            continue
        total_linhas += 1
        dados = {
            campo: (linha.get(coluna) or "").strip() for campo, coluna in mapa.items()
        }
        dados.setdefault("atendente", "")
        if not dados.get("atendente"):
            dados["atendente"] = texto_limpo(atendente_padrao, 120)
        if not dados.get("data_atendimento"):
            dados["data_atendimento"] = data_padrao or ""

        limpos, erros_linha = validar_dados(cliente, dados)
        protocolo = limpos["protocolo"]
        if protocolo and protocolo in protocolos_no_arquivo:
            erros_linha.append(f"Protocolo '{protocolo}' repetido no arquivo.")
        if erros_linha:
            erros.append(f"Linha {numero}: " + " ".join(erros_linha))
            continue

        protocolos_no_arquivo.add(protocolo)
        registros.append(limpos)

    return registros, erros, total_linhas


_SEPARADOR_TXT = re.compile(r"^\s*-{3,}\s*$", re.MULTILINE)
_MARCADOR_CONTEUDO = re.compile(r"^\s*(conteudo|transcricao|conversa)\s*:\s*(.*)$", re.IGNORECASE)
_CABECALHO_TXT = re.compile(
    r"^\s*(protocolo|identificador|atendente|agente|data|data_atendimento|canal)\s*:\s*(.*)$",
    re.IGNORECASE,
)


def importar_txt(cliente, texto, atendente_padrao=None, data_padrao=None, nome_arquivo=""):
    """Importa atendimentos de um arquivo TXT.

    Formatos aceitos:

    1. Varios atendimentos separados por uma linha com tres ou mais hifens.
       Para que os cabecalhos ``chave: valor`` (protocolo, atendente, data,
       canal) sejam lidos, o bloco precisa conter a linha marcadora
       ``conteudo:`` antes da transcricao.
    2. Bloco sem a linha ``conteudo:``: todo o texto do bloco e tratado como
       conteudo do atendimento, usando o atendente e a data informados no
       formulario. Isso evita confundir falas da transcricao
       (por exemplo "Atendente: bom dia...") com cabecalhos.
    """
    blocos = [bloco for bloco in _SEPARADOR_TXT.split(texto) if bloco.strip()]
    if not blocos:
        raise ErroImportacao("O arquivo TXT esta vazio.")

    registros = []
    erros = []

    for indice, bloco in enumerate(blocos, start=1):
        dados = {
            "protocolo": "",
            "atendente": texto_limpo(atendente_padrao, 120),
            "data_atendimento": data_padrao or "",
            "canal": "",
            "conteudo": "",
        }
        linhas = bloco.strip().splitlines()
        posicao_marcador = None
        primeira_linha_conteudo = ""

        for posicao, linha in enumerate(linhas):
            achado = _MARCADOR_CONTEUDO.match(linha)
            if achado:
                posicao_marcador = posicao
                primeira_linha_conteudo = achado.group(2).strip()
                break

        if posicao_marcador is None:
            dados["conteudo"] = bloco.strip()
        else:
            for linha in linhas[:posicao_marcador]:
                achado = _CABECALHO_TXT.match(linha)
                if not achado:
                    continue
                chave, valor = achado.group(1).lower(), achado.group(2).strip()
                if chave in ("protocolo", "identificador"):
                    dados["protocolo"] = valor
                elif chave in ("atendente", "agente"):
                    dados["atendente"] = valor or dados["atendente"]
                elif chave in ("data", "data_atendimento"):
                    dados["data_atendimento"] = valor or dados["data_atendimento"]
                elif chave == "canal":
                    dados["canal"] = valor
            corpo = linhas[posicao_marcador + 1:]
            if primeira_linha_conteudo:
                corpo = [primeira_linha_conteudo] + corpo
            dados["conteudo"] = "\n".join(corpo).strip()

        if not dados["protocolo"] and len(blocos) == 1 and nome_arquivo:
            dados["protocolo"] = slug(nome_arquivo.rsplit(".", 1)[0], 50).upper()

        limpos, erros_bloco = validar_dados(cliente, dados)
        if erros_bloco:
            erros.append(f"Bloco {indice}: " + " ".join(erros_bloco))
            continue
        registros.append(limpos)

    return registros, erros, len(blocos)


def importar_arquivo(cliente, arquivo, extensoes_aceitas, atendente_padrao=None, data_padrao=None):
    """Processa o arquivo enviado e grava os atendimentos validos.

    Retorna ``{"importados": int, "erros": [str], "total": int}``.
    Registros invalidos nao sao gravados; os validos sao gravados em uma
    unica transacao.
    """
    nome = (getattr(arquivo, "filename", "") or "").strip()
    if not nome:
        raise ErroImportacao("Selecione um arquivo para importar.")

    extensao = ("." + nome.rsplit(".", 1)[-1].lower()) if "." in nome else ""
    if extensao not in extensoes_aceitas:
        raise ErroImportacao(
            f"Formato de arquivo nao suportado ({extensao or 'sem extensao'}). "
            "Utilize arquivos .csv ou .txt."
        )

    conteudo = arquivo.read()
    if not conteudo:
        raise ErroImportacao("O arquivo enviado esta vazio.")
    texto = _decodificar(conteudo)

    if extensao == ".csv":
        registros, erros, total = importar_csv(cliente, texto, atendente_padrao, data_padrao)
        origem = "importacao_csv"
    else:
        registros, erros, total = importar_txt(
            cliente, texto, atendente_padrao, data_padrao, nome
        )
        origem = "importacao_txt"

    importados = 0
    if registros:
        try:
            for limpos in registros:
                db.session.add(Atendimento(cliente_id=cliente.id, origem=origem, **limpos))
            db.session.commit()
            importados = len(registros)
        except Exception as erro:  # integridade/banco: nada e gravado
            db.session.rollback()
            raise ErroImportacao(
                f"Nenhum atendimento foi importado devido a uma falha no banco de dados: {erro}"
            )

    return {"importados": importados, "erros": erros, "total": total}
