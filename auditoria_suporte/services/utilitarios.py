"""Funcoes utilitarias compartilhadas."""
import re
import unicodedata
from datetime import date, datetime

_FORMATOS_DATA = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%Y/%m/%d")


def normalizar_texto(texto: str) -> str:
    """Minusculas e sem acentos, preservando o tamanho original do texto.

    O tamanho e preservado para que os indices encontrados no texto
    normalizado possam ser usados para extrair evidencias do texto original.
    """
    if not texto:
        return ""
    saida = []
    for caractere in texto:
        decomposto = unicodedata.normalize("NFD", caractere)
        base = decomposto[0] if decomposto else caractere
        saida.append(base.lower())
    return "".join(saida)


def slug(valor: str, tamanho_maximo: int = 60) -> str:
    """Converte um texto em um identificador seguro para nomes de arquivos."""
    texto = normalizar_texto(valor or "")
    texto = re.sub(r"[^a-z0-9]+", "-", texto).strip("-")
    texto = re.sub(r"-{2,}", "-", texto)
    return texto[:tamanho_maximo] or "sem-nome"


def converter_data(valor) -> date:
    """Converte string/date em ``date``. Lanca ValueError se invalido."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = (valor or "").strip()
    if not texto:
        raise ValueError("Data nao informada.")
    for formato in _FORMATOS_DATA:
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    raise ValueError(f"Data invalida: '{texto}'. Use o formato AAAA-MM-DD ou DD/MM/AAAA.")


def converter_decimal(valor, campo: str = "valor") -> float:
    texto = str(valor if valor is not None else "").strip().replace(",", ".")
    if not texto:
        raise ValueError(f"O campo {campo} e obrigatorio.")
    try:
        return float(texto)
    except ValueError:
        raise ValueError(f"O campo {campo} deve ser numerico.")


def texto_limpo(valor, tamanho_maximo: int = None) -> str:
    texto = (valor or "").strip()
    if tamanho_maximo:
        texto = texto[:tamanho_maximo]
    return texto


def email_valido(valor: str) -> bool:
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", (valor or "").strip()))
