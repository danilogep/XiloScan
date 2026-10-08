"""
Normalização de nomes científicos e de valores textuais do LPF.

O catálogo do LPF usa grafias como:
    "Albizia pedicellaris = Macrosamanea pedicellaris"
    "Anacardium occidentale = Anacardium microcarpum"
    "Acioa sp."
O app MCB usa a forma aceita com autor:
    "Albizia pedicellaris (DC.) L. Rico"

O join entre as duas fontes é feito por `slug binomial` (gênero + epíteto,
sem autor, sem acento, minúsculo), com os sinônimos indexados como aliases.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# ---------------------------------------------------------------- texto base

def strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def squash_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def clean_text(text: str) -> str:
    """Limpa NBSP, espaços duplicados e traços soltos das células do LPF."""
    if text is None:
        return ""
    text = text.replace("\xa0", " ").replace("​", "")
    text = squash_ws(text)
    # células vazias do LPF vêm como "-", "--", "." ou "0"
    if text in {"-", "--", "---", ".", "", "0,00", "N/A", "n/a"}:
        return ""
    return text


def to_float(text: str) -> float | None:
    """'1.114,00' / '0,60' / '1114.00' -> float. Vazio -> None."""
    t = clean_text(text)
    if not t:
        return None
    t = re.sub(r"[^\d,.\-]", "", t)
    if not t:
        return None
    # formato pt-BR: milhar '.', decimal ','
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


# ------------------------------------------------------- nomes científicos

_AUTHOR_TOKENS = re.compile(
    r"\s*\((?!x\b)[^()]*\)|"          # (DC.), (Mart. & O. Berg)
    r"\s+(?:ex\s+)?[A-Z][\w.'-]*\.?"  # tokens de autor iniciados por maiúscula
    r"(?:\s*&\s*[A-Z][\w.'-]*\.?)*"
)
_RANK_TOKENS = re.compile(r"\b(?:var|subsp|ssp|f|cv|sp|spp)\.?\b", re.I)


@dataclass(slots=True)
class ScientificName:
    raw: str
    genus: str
    epithet: str
    author: str = ""
    synonyms: list[str] = field(default_factory=list)
    indeterminate: bool = False  # "sp." / "spp."

    @property
    def binomial(self) -> str:
        if self.indeterminate:
            return f"{self.genus} sp."
        return squash_ws(f"{self.genus} {self.epithet}")

    @property
    def slug(self) -> str:
        """Chave canônica de join: 'alexa_grandiflora'."""
        base = strip_accents(self.binomial).lower()
        base = re.sub(r"[^a-z0-9]+", "_", base).strip("_")
        return base

    @property
    def folder(self) -> str:
        """Nome de subpasta das imagens: 'Alexa_grandiflora'."""
        base = strip_accents(self.binomial)
        return re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_")

    def all_slugs(self) -> list[str]:
        out = [self.slug]
        for syn in self.synonyms:
            s = parse_scientific_name(syn)
            if s.slug and s.slug not in out:
                out.append(s.slug)
        return out


def parse_scientific_name(raw: str) -> ScientificName:
    """
    >>> parse_scientific_name("Albizia pedicellaris = Macrosamanea pedicellaris").slug
    'albizia_pedicellaris'
    >>> parse_scientific_name("Alexa grandiflora Ducke").binomial
    'Alexa grandiflora'
    >>> parse_scientific_name("Acioa sp.").indeterminate
    True
    """
    raw = clean_text(raw)
    parts = [p.strip() for p in re.split(r"\s*=\s*", raw) if p.strip()]
    head, synonyms = (parts[0], parts[1:]) if parts else ("", [])

    # separa autor (tudo após o epíteto que comece com maiúscula ou parêntese)
    author = ""
    m = _AUTHOR_TOKENS.search(head, pos=len(head.split(" ")[0]) if head else 0)
    tokens = head.split(" ")
    genus = tokens[0] if tokens else ""
    epithet = ""
    indeterminate = False

    if len(tokens) >= 2:
        second = tokens[1]
        if _RANK_TOKENS.fullmatch(second.rstrip(".") + ".") or second.lower().rstrip(".") in {"sp", "spp"}:
            indeterminate = True
            author = squash_ws(" ".join(tokens[2:]))
        else:
            epithet = second.strip(".,")
            author = squash_ws(" ".join(tokens[2:]))
    if m and not author:
        author = squash_ws(m.group(0))

    return ScientificName(
        raw=raw,
        genus=genus.capitalize() if genus else "",
        epithet=epithet.lower(),
        author=author,
        synonyms=synonyms,
        indeterminate=indeterminate,
    )


# ------------------------------------------------- mapeamento p/ taxonomia MCB

def map_aneis_crescimento(lpf_value: str) -> str | None:
    """Mapeia o texto livre do LPF para o código MCB."""
    v = strip_accents(clean_text(lpf_value)).lower()
    if not v:
        return None
    if "pouco" in v:
        return "POUCO_DISTINTOS"
    if "indistint" in v or "ausent" in v or "nao distint" in v:
        return "INDISTINTOS"
    if "distint" in v:
        return "DISTINTOS"
    return None


_COR_MAP = {
    "branca": "BRANCA_BEGE",
    "bege": "BRANCA_BEGE",
    "amarela": "AMARELA",
    "amarelo": "AMARELA",
    "rosa": "ROSA_AVERMELHADA",
    "rosada": "ROSA_AVERMELHADA",
    "vermelha": "ROSA_AVERMELHADA",
    "avermelhada": "ROSA_AVERMELHADA",
    "parda": "MARROM_AMARELADA",
    "marrom": "MARROM_ESCURA",
}


def map_cor_cerne(lpf_value: str) -> str | None:
    """Mapeia 'Classificação da Cor do Cerne' do LPF para o código MCB."""
    v = strip_accents(clean_text(lpf_value)).lower()
    if not v:
        return None
    for key, code in _COR_MAP.items():
        if key in v:
            return code
    return None
