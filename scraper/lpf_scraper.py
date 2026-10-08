"""
XiloScan — Etapa 1: scraper do catálogo LPF/SFB "Madeiras Brasileiras".

Estrutura real do alvo (verificada em 2026-08):
  * Listagem  : https://lpf.florestal.gov.br/pt-br/madeiras-brasileiras?start=N   (N = 0,20,40,...)
  * Detalhe   : https://lpf.florestal.gov.br/index.php?option=com_madeirasbrasileiras
                &view=especieestudada&especieestudadaid=<ID>
  * Imagem    : https://lpf.florestal.gov.br/images/madeirasbrasileiras/<Nome Cientifico>.jpg
  * ~271 registros no site (o app MCB expõe um subconjunto de 157 espécies).

O que o LPF publica: nome científico, família, local de coleta, nomes comuns,
caracteres gerais (cerne/alburno, COR, ANÉIS DE CRESCIMENTO, grã, textura,
figura, brilho), secagem, trabalhabilidade, densidades, contrações,
propriedades mecânicas, classificação da cor do cerne e 1 imagem macroscópica.

O que o LPF NÃO publica e vem da camada MCB (ver mcb_merge.py):
vasos/poros, agrupamento, obstrução, tiloses, parênquima axial e raios.

Uso:
    python -m scraper.lpf_scraper --out data --workers 6
    python -m scraper.lpf_scraper --only-ids 2,284 --no-images   # smoke test
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import random
import re
import socket
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from .normalize import (
    ScientificName,
    clean_text,
    map_aneis_crescimento,
    map_cor_cerne,
    parse_scientific_name,
    strip_accents,
    to_float,
)

BASE = "https://lpf.florestal.gov.br"
LIST_URL = f"{BASE}/pt-br/madeiras-brasileiras"
DETAIL_URL = (
    f"{BASE}/index.php?option=com_madeirasbrasileiras"
    f"&view=especieestudada&especieestudadaid={{id}}"
)
IMG_DIR_HINT = "/images/madeirasbrasileiras/"
PAGE_SIZE = 20

# Identificar o robo e o contato e boa pratica de scraping educado: o
# administrador do site consegue falar com quem esta coletando. O endereco vem
# do ambiente para que um e-mail pessoal nao fique gravado no repositorio
# publico; defina XILOSCAN_SCRAPER_CONTATO antes de coletar.
_CONTATO = os.getenv("XILOSCAN_SCRAPER_CONTATO", "").strip()

USER_AGENT = (
    "XiloScan/1.0 (pesquisa academica; identificacao macroscopica de madeiras"
    + (f"; contato: {_CONTATO}" if _CONTATO else "")
    + ")"
)

log = logging.getLogger("xiloscan.scraper")


# ═════════════════════════════════════════════════════════ diagnóstico de rede

class RedeIndisponivel(RuntimeError):
    """O host do LPF não é alcançável — não adianta repetir a requisição."""


def _e_erro_de_dns(exc: BaseException) -> bool:
    """socket.gaierror em qualquer ponto da cadeia de causas."""
    vista: set[int] = set()
    atual: BaseException | None = exc
    while atual is not None and id(atual) not in vista:
        vista.add(id(atual))
        if isinstance(atual, socket.gaierror):
            return True
        if "name resolution" in str(atual).lower() or "nodename nor servname" in str(atual).lower():
            return True
        atual = atual.__cause__ or atual.__context__
    return False


def proxy_configurado() -> str | None:
    for var in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        valor = os.environ.get(var)
        if valor:
            return f"{var}={valor}"
    return None


def preflight(host: str = "lpf.florestal.gov.br", timeout: float = 15.0) -> None:
    """
    Verifica UMA vez que o host resolve e responde, antes de disparar centenas
    de requisições. Sem isto, uma rede indisponível vira 5 retries por URL,
    minutos de espera e um dataset vazio com cara de sucesso.

    Levanta RedeIndisponivel com um diagnóstico acionável.
    """
    prox = proxy_configurado()
    if prox:
        log.info("proxy detectado no ambiente: %s", prox)

    # 1) DNS
    try:
        socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise RedeIndisponivel(
            f"O nome '{host}' não resolve neste ambiente ({exc}).\n"
            "\n"
            "Isto é falta de rede/DNS, não um problema do site nem do parser.\n"
            "Causas comuns, na ordem em que valem ser checadas:\n"
            "  1. O ambiente não tem internet (sandbox, VM isolada, container sem egress).\n"
            "     → Rode no Google Colab: notebooks/01_catalogo_lpf.ipynb.\n"
            "  2. Você está atrás de um proxy corporativo e ele não está configurado.\n"
            "     → export HTTPS_PROXY=http://usuario:senha@proxy:porta\n"
            f"     → proxy visto agora: {prox or 'nenhum'}\n"
            "  3. A máquina está offline ou o DNS caiu.\n"
            "     → teste: getent hosts lpf.florestal.gov.br   (ou nslookup)\n"
            "\n"
            "Nada foi baixado. Nenhum arquivo foi sobrescrito."
        ) from exc

    # 2) conexão + resposta HTTP
    try:
        with httpx.Client(
            headers={"User-Agent": USER_AGENT}, timeout=timeout, follow_redirects=True
        ) as cli:
            r = cli.get(LIST_URL)
        if r.status_code >= 500:
            raise RedeIndisponivel(
                f"O LPF respondeu {r.status_code} em {LIST_URL}. O site pode estar fora do ar; "
                "tente de novo mais tarde."
            )
        if r.status_code >= 400:
            raise RedeIndisponivel(
                f"O LPF respondeu {r.status_code} em {LIST_URL}. Se for 403, é bloqueio de "
                "egress/WAF neste ambiente — rode no Colab."
            )
    except httpx.HTTPError as exc:
        if isinstance(exc, RedeIndisponivel):
            raise
        raise RedeIndisponivel(
            f"Não foi possível conectar a {host} ({type(exc).__name__}: {exc}).\n"
            f"Proxy visto: {prox or 'nenhum'}.\n"
            "Se este ambiente não tem saída para a internet, rode no Colab: "
            "notebooks/01_catalogo_lpf.ipynb."
        ) from exc

    log.info("preflight OK — %s alcançável", host)


# ═══════════════════════════════════════════════════════════ modelo de dados

@dataclass(slots=True)
class LPFRecord:
    lpf_id: int
    url: str
    nome_cientifico: str
    nome_cientifico_raw: str
    autor: str = ""
    sinonimos: list[str] = field(default_factory=list)
    familia: str = ""
    nomes_populares: list[str] = field(default_factory=list)
    local_coleta: str = ""
    slug: str = ""

    # caracteres gerais (macroscópicos) publicados pelo LPF
    cerne_alburno: str = ""
    cor: str = ""
    cor_alburno: str = ""
    classificacao_cor_cerne: str = ""
    aneis_crescimento: str = ""
    gra: str = ""
    textura: str = ""
    figura: str = ""
    figura_radial: str = ""
    brilho: str = ""
    cheiro: str = ""

    # dendrometria
    altura_comercial: str = ""
    dap: str = ""
    tronco: str = ""
    casca_espessura: str = ""

    # físicas / mecânicas (numéricas)
    propriedades: dict[str, float | None] = field(default_factory=dict)

    # texto livre
    secagem: str = ""
    trabalhabilidade: dict[str, str] = field(default_factory=dict)
    preservacao: str = ""
    usos: str = ""

    # imagens
    imagens: list[dict] = field(default_factory=list)

    # blocos compostos já quebrados em subcampos
    blocos: dict[str, dict[str, str]] = field(default_factory=dict)
    # números canônicos (densidade_basica, contracao_*) extraídos das matrizes
    atalhos: dict[str, float | None] = field(default_factory=dict)
    # todos os pares label:valor crus, para não perder nada
    campos_brutos: dict[str, str] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════ HTTP client

class Fetcher:
    """Cliente com retry exponencial, jitter, rate-limit e cache em disco."""

    def __init__(
        self,
        cache_dir: Path,
        concurrency: int = 6,
        min_interval: float = 0.35,
        timeout: float = 45.0,
        max_retries: int = 5,
        use_cache: bool = True,
        offline: bool = False,
    ):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.use_cache = use_cache
        self.offline = offline
        self.max_retries = max_retries
        self.min_interval = min_interval
        self._sem = asyncio.Semaphore(concurrency)
        self._last = 0.0
        self._lock = asyncio.Lock()
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": USER_AGENT,
                "Accept-Language": "pt-BR,pt;q=0.9",
                "Accept": "text/html,application/xhtml+xml,image/*;q=0.8,*/*;q=0.5",
            },
            timeout=timeout,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=concurrency + 2),
        )

    def _cache_path(self, url: str, suffix: str) -> Path:
        h = hashlib.sha256(url.encode()).hexdigest()[:24]
        return self.cache_dir / f"{h}{suffix}"

    async def _throttle(self) -> None:
        async with self._lock:
            delta = time.monotonic() - self._last
            if delta < self.min_interval:
                await asyncio.sleep(self.min_interval - delta)
            self._last = time.monotonic()

    async def get_bytes(self, url: str, suffix: str = ".bin") -> bytes | None:
        cp = self._cache_path(url, suffix)
        if self.use_cache and cp.exists() and cp.stat().st_size > 0:
            return cp.read_bytes()
        if self.offline:
            log.debug("offline: %s não está no cache", url)
            return None

        async with self._sem:
            for attempt in range(1, self.max_retries + 1):
                await self._throttle()
                try:
                    r = await self._client.get(url)
                    if r.status_code == 404:
                        log.warning("404 %s", url)
                        return None
                    if r.status_code in (429, 500, 502, 503, 504):
                        raise httpx.HTTPStatusError(
                            f"status {r.status_code}", request=r.request, response=r
                        )
                    r.raise_for_status()
                    data = r.content
                    if self.use_cache:
                        cp.write_bytes(data)
                    return data
                except (httpx.HTTPError, httpx.TimeoutException) as exc:
                    # DNS não é falha transitória: repetir 5x só desperdiça tempo
                    # e transforma "sem rede" num dataset vazio com cara de sucesso.
                    if _e_erro_de_dns(exc):
                        raise RedeIndisponivel(
                            f"Resolução de nome falhou para {urlparse(url).hostname} durante o "
                            f"crawl ({exc}). A rede caiu no meio da execução — o cache em disco "
                            "preserva o que já foi baixado, então basta rodar de novo quando "
                            "voltar."
                        ) from exc
                    if attempt == self.max_retries:
                        log.error("falha definitiva %s (%s)", url, exc)
                        return None
                    backoff = min(2 ** attempt, 30) + random.uniform(0, 1.5)
                    log.warning(
                        "retry %d/%d em %.1fs — %s (%s)",
                        attempt, self.max_retries, backoff, url, exc,
                    )
                    await asyncio.sleep(backoff)
        return None

    async def get_html(self, url: str) -> str | None:
        data = await self.get_bytes(url, ".html")
        if data is None:
            return None
        # o Joomla do LPF declara utf-8 mas às vezes serve latin-1
        for enc in ("utf-8", "iso-8859-1", "cp1252"):
            try:
                return data.decode(enc)
            except UnicodeDecodeError:
                continue
        return data.decode("utf-8", errors="replace")

    async def aclose(self) -> None:
        await self._client.aclose()


# ═══════════════════════════════════════════════════════════════════ parsing

_ID_RE = re.compile(r"especieestudadaid=(\d+)")
_LABEL_SPLIT = re.compile(r"^\s*([^:]{2,90}?)\s*:\s*(.*)$", re.S)


def parse_listing(html: str) -> list[dict]:
    """Extrai (id, nome_cientifico_raw, nome_popular) de uma página de listagem."""
    soup = BeautifulSoup(html, "lxml")
    out: list[dict] = []
    seen: set[int] = set()

    for a in soup.select("a[href*='especieestudadaid=']"):
        href = a.get("href", "")
        m = _ID_RE.search(href)
        if not m:
            continue
        lpf_id = int(m.group(1))
        if lpf_id in seen:
            continue
        seen.add(lpf_id)

        nome = clean_text(a.get_text(" "))
        popular = ""
        row = a.find_parent("tr")
        if row:
            cells = [clean_text(td.get_text(" ")) for td in row.find_all("td")]
            cells = [c for c in cells if c]
            if len(cells) >= 2:
                nome = nome or cells[0]
                popular = next((c for c in cells[1:] if c != nome), "")
        out.append(
            {
                "lpf_id": lpf_id,
                "nome_cientifico_raw": nome,
                "nome_popular_listagem": popular,
                "url": urljoin(BASE, href),
            }
        )
    return out


def total_from_listing(html: str) -> int | None:
    """Lê o contador de resultados do Joomla ('271') se presente."""
    soup = BeautifulSoup(html, "lxml")
    txt = soup.get_text(" ")
    m = re.search(r"(?:Total|de)\s+(\d{2,4})\s+(?:registros|resultados|itens)", txt, re.I)
    if m:
        return int(m.group(1))
    offsets = [
        int(v[0])
        for a in soup.select("a[href*='start=']")
        for v in [parse_qs(urlparse(a.get("href", "")).query).get("start", [])]
        if v and v[0].isdigit()
    ]
    return max(offsets) + PAGE_SIZE if offsets else None


# ───────────────────────────────────────────── blocos "<span bold>Rótulo:</span> valor"

_BOLD = re.compile(r"font-weight-bold|fw-bold|font-bold")


def _iter_label_value(soup: BeautifulSoup):
    """
    Percorre os pares rótulo/valor da ficha do LPF.

    Estrutura real (verificada no HTML servido em 2026-08):

        <p><span class="font-weight-bold">Características Gerais:</span>
           Cerne/Alburno: indistintos; Cor: amarelo-...; Grã: cruzada ondulada; ...
        </p>

    ou seja, um punhado de BLOCOS, cada um com vários subcampos separados por
    ';' — e não uma linha de tabela por campo. As duas heurísticas antigas
    (tabela rótulo|valor e parágrafo "Rótulo: valor") continuam como fallback
    para o caso de o template mudar de novo.
    """
    vistos: set[tuple[str, str]] = set()

    def emitir(label: str, value: str):
        label, value = clean_text(label).rstrip(":"), clean_text(value)
        chave = (label, value)
        if label and value and chave not in vistos:
            vistos.add(chave)
            return (label, value)
        return None

    # 1) forma canônica: <p><span bold>Rótulo:</span> valor</p>
    for tag in soup.select("p, li, div, h4, h5"):
        span = tag.find(["span", "strong", "b"], class_=_BOLD) or tag.find(["strong", "b"])
        if span is None or span.parent is not tag:
            continue
        rotulo = span.get_text(" ", strip=True)
        if not rotulo.rstrip().endswith(":"):
            continue
        inteiro = clean_text(tag.get_text(" "))
        rot_limpo = clean_text(rotulo)
        valor = inteiro[len(rot_limpo):] if inteiro.startswith(rot_limpo) else inteiro
        par = emitir(rot_limpo, valor)
        if par:
            yield par

    # 2) fallback: linha de tabela com 2+ células
    for row in soup.select("tr"):
        cells = [clean_text(td.get_text(" ")) for td in row.find_all(["td", "th"])]
        cells = [c for c in cells if c]
        if len(cells) >= 2:
            par = emitir(cells[0], " ".join(cells[1:]))
            if par:
                yield par

    # 3) fallback: parágrafo "Rótulo: valor" sem marcação
    for tag in soup.select("p, li, dt, span.campo"):
        txt = clean_text(tag.get_text(" "))
        if not txt or len(txt) > 400:
            continue
        m = _LABEL_SPLIT.match(txt)
        if m:
            par = emitir(m.group(1), m.group(2))
            if par:
                yield par


def _norm_label(label: str) -> str:
    return strip_accents(label).lower().strip().rstrip(":")


# rótulos de BLOCO (nível 1) -> campo do LPFRecord
_FIELD_MAP = {
    "nome cientifico": "nome_cientifico_raw",
    "familia": "familia",
    "local de coleta": "local_coleta",
    "nomes comuns": "_nomes_comuns",
    "nome comum": "_nomes_comuns",
    "nomes vulgares": "_nomes_comuns",
    "secagem em estufa": "secagem",
    "secagem": "secagem",
    "preservacao": "preservacao",
    "usos": "usos",
    "utilizacao": "usos",
    "uso final": "usos",
    "classificacao da cor do cerne": "classificacao_cor_cerne",
}

# SUBcampos (nível 2, dentro de 'Características Gerais', 'Árvore', 'Trabalhabilidade')
_SUBCAMPO_MAP = {
    "cerne/alburno": "cerne_alburno",
    "cerne": "cerne_alburno",
    "cor": "cor",
    "cor do cerne": "cor",
    "cor do alburno": "cor_alburno",
    "figura tangencial": "figura",
    "figura radial": "figura_radial",
    "aneis de crescimento": "aneis_crescimento",
    "camadas de crescimento": "aneis_crescimento",
    "gra": "gra",
    "textura": "textura",
    "figura": "figura",
    "brilho": "brilho",
    "cheiro": "cheiro",
    "odor": "cheiro",
    "altura comercial": "altura_comercial",
    "altura": "altura_comercial",
    "diametro (dap)": "dap",
    "diametro": "dap",
    "dap": "dap",
    "tronco": "tronco",
    "casca": "casca_espessura",
}


# subcampos conhecidos de cada bloco composto (ordem importa: prefixo mais longo primeiro)
SUBCAMPOS = {
    # Dois templates convivem no LPF:
    #   A) "Cor: amarelo-...; Anéis de crescimento: pouco distintos; Figura: ausente"
    #   B) "Cor do cerne: marrom...; Cor do alburno: ...; Camadas de crescimento: ...;
    #       Figura tangencial: ...; Figura radial: ..."
    # O prefixo mais LONGO é testado primeiro, então "Cor do alburno" nunca cai em "Cor".
    "caracteristicas gerais": [
        "Cerne/Alburno", "Cerne/alburno", "Espessura do alburno",
        "Cor do cerne", "Cor do alburno", "Cor",
        "Anéis de crescimento", "Camadas de crescimento",
        "Grã", "Textura",
        "Figura tangencial", "Figura radial", "Figura",
        "Brilho", "Cheiro", "Odor", "Gosto", "Densidade",
        "Resistência ao corte manual",
    ],
    "arvore": ["Altura comercial", "Altura", "Diâmetro (DAP)", "Diâmetro", "DAP", "Tronco", "Casca"],
    "trabalhabilidade": [
        "Serragem", "Aplainamento", "Torneamento", "Furação", "Lixamento",
        "Fresagem", "Encaixe", "Colagem", "Pregagem", "Acabamento",
    ],
}


def parse_bloco_composto(texto: str, chave_bloco: str) -> dict[str, str]:
    """
    'Cerne/Alburno: indistintos; Cor: amarelo-...; Grã: cruzada ondulada;'
        -> {'Cerne/Alburno': 'indistintos', 'Cor': 'amarelo-...', 'Grã': 'cruzada ondulada'}

    Também resolve subcampos SEM dois-pontos, que o LPF usa em 'Árvore':
        'Altura comercial 12m'  ->  {'Altura comercial': '12m'}
    """
    conhecidos = SUBCAMPOS.get(chave_bloco, [])
    ordenados = sorted(conhecidos, key=len, reverse=True)
    out: dict[str, str] = {}

    for parte in re.split(r"\s*;\s*", texto or ""):
        parte = clean_text(parte).rstrip(".;")
        if not parte:
            continue

        casou = False
        alvo = strip_accents(parte).lower()
        for sub in ordenados:
            pref = strip_accents(sub).lower()
            if alvo.startswith(pref):
                valor = clean_text(parte[len(sub):].lstrip(": "))
                if valor:
                    out[sub] = valor
                casou = True
                break

        if not casou:
            m = _LABEL_SPLIT.match(parte)
            if m and clean_text(m.group(2)):
                out[clean_text(m.group(1))] = clean_text(m.group(2))
            elif parte:
                out.setdefault("_texto", "")
                out["_texto"] = clean_text(f"{out['_texto']} {parte}")
    return out


# ─────────────────────────────────────────── tabelas de propriedades (matriz)

def expandir_tabela(table) -> list[list[str]]:
    """
    Expande colspan/rowspan numa grade retangular.

    As tabelas do LPF têm 2-3 linhas de cabeçalho com colspan e rowspan
    cruzados ('Condição' rowspan=3, 'Flexão Estática (kgf/cm²)' colspan=2).
    Sem expandir, as colunas saem desalinhadas dos valores — foi o que fez a
    primeira versão gravar '1,17' como se fosse um rótulo.
    """
    grade: list[list[str | None]] = []
    for r, tr in enumerate(table.find_all("tr")):
        while len(grade) <= r:
            grade.append([])
        col = 0
        for cel in tr.find_all(["td", "th"]):
            while col < len(grade[r]) and grade[r][col] is not None:
                col += 1
            texto = clean_text(cel.get_text(" "))
            try:
                cspan = max(1, int(cel.get("colspan", 1)))
                rspan = max(1, int(cel.get("rowspan", 1)))
            except (TypeError, ValueError):
                cspan = rspan = 1
            for dr in range(rspan):
                while len(grade) <= r + dr:
                    grade.append([])
                linha = grade[r + dr]
                while len(linha) < col + cspan:
                    linha.append(None)
                for dc in range(cspan):
                    linha[col + dc] = texto if (dr == 0 and dc == 0) else texto
            col += cspan

    largura = max((len(linha) for linha in grade), default=0)
    return [
        [(c or "") for c in linha] + [""] * (largura - len(linha))
        for linha in grade
    ]


_COND_RE = re.compile(r"^(verde|seca|seco)$", re.I)


def _e_linha_de_dados(linha: list[str]) -> bool:
    """
    Linha de valores, não de cabeçalho.

    Três formas no LPF: começa por 'Verde'/'Seca' (mecânicas), começa vazia
    (densidade do template A) ou já começa por um número (densidade do
    template B). Uma linha cujo 1º campo é texto e o resto é número — caso de
    'Número de Amostras: 13 12 28 31' — NÃO é linha de dados.
    """
    if not any(c and to_float(c) is not None for c in linha):
        return False
    primeiro = strip_accents(linha[0]).strip()
    return bool(_COND_RE.match(primeiro)) or not primeiro or to_float(linha[0]) is not None


def parse_tabela_matriz(table) -> dict[str, float | None]:
    """
    Converte uma tabela cabeçalho-multinível em {rótulo achatado: número}.

    'Flexão Estática (kgf/cm²) · Módulo de Ruptura · Seca' -> 1114.0
    """
    grade = expandir_tabela(table)
    if len(grade) < 2:
        return {}

    dados = [i for i, linha in enumerate(grade) if _e_linha_de_dados(linha)]
    if not dados:
        return {}
    primeiro = dados[0]
    cabecalhos = grade[:primeiro]
    if not cabecalhos:
        return {}

    nomes: list[str] = []
    for c in range(len(grade[0])):
        partes: list[str] = []
        for linha in cabecalhos:
            v = linha[c] if c < len(linha) else ""
            if v and v not in partes and not _COND_RE.match(strip_accents(v).strip()):
                partes.append(v)
        nomes.append(" · ".join(partes))

    out: dict[str, float | None] = {}
    for i in dados:
        linha = grade[i]
        cond = clean_text(linha[0]) if _COND_RE.match(strip_accents(linha[0]).strip()) else ""
        for c, valor in enumerate(linha):
            if c == 0 and cond:
                continue
            nome = nomes[c] if c < len(nomes) else ""
            if not nome:
                continue
            chave = f"{nome} · {cond}" if cond else nome
            num = to_float(valor)
            if num is not None or chave not in out:
                out[chave] = num
    return out


def parse_tabelas_propriedades(soup: BeautifulSoup) -> dict[str, float | None]:
    props: dict[str, float | None] = {}
    for table in soup.select("table"):
        grade = expandir_tabela(table)
        if not grade:
            continue
        titulo = strip_accents(grade[0][0]).lower() if grade[0] else ""
        if titulo.startswith("resultados"):     # acabamento superficial: texto, não número
            continue
        props.update(parse_tabela_matriz(table))
    return props


# atalhos canônicos usados pelo backend e pelo frontend
_ATALHOS = {
    "densidade_basica": ("densidade", "basica"),
    "densidade_verde": ("densidade", "verde"),
    "densidade_seca": ("densidade", "seca"),
    "densidade_aparente": ("densidade", "aparente"),
    "contracao_tangencial": ("contracao", "tangencial"),
    "contracao_radial": ("contracao", "radial"),
    "contracao_volumetrica": ("contracao", "volumetrica"),
}


def extrair_atalhos(props: dict[str, float | None]) -> dict[str, float | None]:
    """Puxa da matriz achatada os números que o resto do sistema consulta pelo nome."""
    out: dict[str, float | None] = {}
    for destino, (grupo, sub) in _ATALHOS.items():
        achado = None
        for chave, valor in props.items():
            k = strip_accents(chave).lower()
            if grupo in k and sub in k and valor is not None:
                achado = valor
                break
        out[destino] = achado
    return out


def parse_detail(html: str, lpf_id: int, url: str) -> LPFRecord | None:
    soup = BeautifulSoup(html, "lxml")

    for sel in ("header", "footer", "nav", "script", "style", "#footer", ".moduletable"):
        for tag in soup.select(sel):
            tag.decompose()

    rec = LPFRecord(lpf_id=lpf_id, url=url, nome_cientifico="", nome_cientifico_raw="")

    for label, value in _iter_label_value(soup):
        nl = _norm_label(label)
        rec.campos_brutos[label.rstrip(":")] = value

        # blocos compostos: um rótulo, vários subcampos separados por ';'
        if nl in SUBCAMPOS:
            subs = parse_bloco_composto(value, nl)
            rec.blocos[label.rstrip(":")] = subs
            for sub, sval in subs.items():
                alvo = _SUBCAMPO_MAP.get(_norm_label(sub))
                if alvo:
                    setattr(rec, alvo, sval)
                elif nl == "trabalhabilidade" and not sub.startswith("_"):
                    rec.trabalhabilidade[sub] = sval
            continue

        target = _FIELD_MAP.get(nl)
        if target == "_nomes_comuns":
            rec.nomes_populares = [
                clean_text(x) for x in re.split(r"[;,/]", value) if clean_text(x)
            ]
        elif target:
            setattr(rec, target, value)
        elif nl.startswith("tempo de secagem"):
            rec.propriedades["Tempo de secagem (dias)"] = to_float(value)

    rec.propriedades.update(parse_tabelas_propriedades(soup))
    rec.atalhos = extrair_atalhos(rec.propriedades)

    if not rec.nome_cientifico_raw:
        for sel in ("h1", "h2", "h3", ".page-header", "title"):
            node = soup.select_one(sel)
            if node:
                t = clean_text(node.get_text(" "))
                t = re.sub(r"^LPF\s*-\s*.*?-\s*", "", t)
                if t and len(t.split()) <= 8:
                    rec.nome_cientifico_raw = t
                    break

    if not rec.nome_cientifico_raw:
        log.warning("id=%s sem nome cientifico — pagina fora do padrao", lpf_id)
        return None

    sn: ScientificName = parse_scientific_name(rec.nome_cientifico_raw)
    rec.nome_cientifico = sn.binomial
    rec.autor = sn.author
    rec.sinonimos = sn.synonyms
    rec.slug = sn.slug

    rec.imagens = _extract_images(soup, sn)
    return rec


def _extract_images(soup: BeautifulSoup, sn: ScientificName) -> list[dict]:
    urls: list[str] = []
    for img in soup.select("img[src]"):
        src = img.get("src", "")
        if IMG_DIR_HINT in src:
            full = urljoin(BASE, src)
            if full not in urls:
                urls.append(full)
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if IMG_DIR_HINT in href and href.lower().endswith((".jpg", ".jpeg", ".png")):
            full = urljoin(BASE, href)
            if full not in urls:
                urls.append(full)

    # convenção do LPF: a imagem tem o nome científico como filename
    if not urls and sn.binomial:
        urls.append(f"{BASE}{IMG_DIR_HINT}{sn.binomial}.jpg")

    return [
        {"url": u, "tipo": "corte_transversal_macroscopico", "arquivo": None}
        for u in urls
    ]


# ══════════════════════════════════════════════════════════════ orquestração

async def crawl_ids(fetcher: Fetcher, max_pages: int = 40) -> list[dict]:
    """Percorre a paginação e devolve a lista de espécies (id + nome)."""
    first = await fetcher.get_html(f"{LIST_URL}?start=0")
    if first is None:
        raise RedeIndisponivel(
            f"A listagem {LIST_URL}?start=0 não retornou conteúdo mesmo com o preflight OK. "
            "O site pode estar instável — tente de novo em alguns minutos."
        )

    total = total_from_listing(first) or 0
    log.info("total anunciado pela listagem: %s", total or "desconhecido")

    items = {it["lpf_id"]: it for it in parse_listing(first)}
    page = 1
    while page < max_pages:
        start = page * PAGE_SIZE
        if total and start >= total:
            break
        html = await fetcher.get_html(f"{LIST_URL}?start={start}")
        if html is None:
            break
        page_items = parse_listing(html)
        new = [it for it in page_items if it["lpf_id"] not in items]
        if not new:
            log.info("página start=%d sem itens novos — fim da paginação", start)
            break
        for it in new:
            items[it["lpf_id"]] = it
        log.info("start=%-4d  +%d espécies (acumulado %d)", start, len(new), len(items))
        page += 1

    return sorted(items.values(), key=lambda d: d["lpf_id"])


async def fetch_species(fetcher: Fetcher, item: dict) -> LPFRecord | None:
    html = await fetcher.get_html(item["url"])
    if html is None:
        return None
    rec = parse_detail(html, item["lpf_id"], item["url"])
    if rec and not rec.nomes_populares and item.get("nome_popular_listagem"):
        rec.nomes_populares = [item["nome_popular_listagem"]]
    return rec


async def download_images(fetcher: Fetcher, rec: LPFRecord, img_root: Path) -> None:
    sn = parse_scientific_name(rec.nome_cientifico_raw)
    folder = img_root / sn.folder
    for i, img in enumerate(rec.imagens, start=1):
        data = await fetcher.get_bytes(img["url"], ".img")
        if not data or len(data) < 1024:
            log.warning("imagem vazia/ausente: %s", img["url"])
            img["arquivo"] = None
            continue
        ext = Path(urlparse(img["url"]).path).suffix.lower() or ".jpg"
        if ext not in {".jpg", ".jpeg", ".png", ".webp"}:
            ext = ".jpg"
        folder.mkdir(parents=True, exist_ok=True)
        dest = folder / f"{sn.folder}_{i:02d}{ext}"
        dest.write_bytes(data)
        img["arquivo"] = str(dest.relative_to(img_root.parent)).replace("\\", "/")
        img["bytes"] = len(data)
        img["sha256"] = hashlib.sha256(data).hexdigest()


def record_to_dataset_entry(rec: LPFRecord) -> dict:
    """Converte o registro cru no schema final do dataset_lpf.json."""
    return {
        "id": rec.slug,
        "lpf_id": rec.lpf_id,
        "fonte_url": rec.url,
        "taxonomia": {
            "nome_cientifico": rec.nome_cientifico,
            "autor": rec.autor,
            "familia": rec.familia,
            "sinonimos": rec.sinonimos,
            "nomes_populares": rec.nomes_populares,
            "grafia_original_lpf": rec.nome_cientifico_raw,
        },
        "procedencia": {
            "local_coleta": rec.local_coleta,
            "dominio_fitogeografico": [],  # preenchido pela camada MCB
        },
        "caracteres_gerais": {
            "cerne_alburno": rec.cerne_alburno,
            "cor_descricao": rec.cor,
            "cor_alburno": rec.cor_alburno,
            "cor_classificacao_lpf": rec.classificacao_cor_cerne,
            "gra": rec.gra,
            "textura": rec.textura,
            "figura": rec.figura,
            "figura_radial": rec.figura_radial,
            "brilho": rec.brilho,
            "cheiro": rec.cheiro,
        },
        "anatomia_macroscopica": {
            # do LPF
            "aneis_crescimento": map_aneis_crescimento(rec.aneis_crescimento),
            "aneis_crescimento_texto": rec.aneis_crescimento,
            "cor_madeira": map_cor_cerne(rec.classificacao_cor_cerne or rec.cor),
            # da camada MCB (mcb_merge.py preenche)
            "vasos_porosidade": None,
            "vasos_agrupamento": [],
            "vasos_obstrucao": None,
            "tiloses_substancias": [],
            "parenquima_axial": None,
            "parenquima_apotraqueal": [],
            "parenquima_paratraqueal": [],
            "raios_visibilidade": [],
        },
        "dendrometria": {
            "altura_comercial": rec.altura_comercial,
            "dap": rec.dap,
            "tronco": rec.tronco,
            "casca_espessura": rec.casca_espessura,
        },
        "propriedades": rec.propriedades,
        "propriedades_chave": rec.atalhos,
        "blocos_lpf": rec.blocos,
        "tecnologia": {
            "secagem": rec.secagem,
            "trabalhabilidade": rec.trabalhabilidade,
            "preservacao": rec.preservacao,
            "usos": rec.usos,
        },
        "imagens": rec.imagens,
        "campos_brutos_lpf": rec.campos_brutos,
        "proveniencia": {
            "lpf": True,
            "mcb": False,
            "coletado_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        },
    }


async def run(args: argparse.Namespace) -> int:
    # antes de qualquer coisa: a rede está de pé?
    if args.offline:
        log.info("modo --offline: só o cache em disco será lido, nada de rede")
    try:
        if not args.offline:
            preflight()
    except RedeIndisponivel as exc:
        log.error("\n%s\n%s\n%s", "=" * 72, exc, "=" * 72)
        return 2
    if args.check:
        log.info("--check: rede OK, nada mais a fazer")
        return 0

    out_dir = Path(args.out)
    img_root = out_dir / "images"
    out_dir.mkdir(parents=True, exist_ok=True)

    fetcher = Fetcher(
        cache_dir=out_dir / ".cache",
        concurrency=args.workers,
        min_interval=args.delay,
        use_cache=not args.no_cache,
        offline=args.offline,
    )

    try:
        if args.only_ids:
            ids = [int(x) for x in args.only_ids.split(",") if x.strip()]
            items = [
                {"lpf_id": i, "url": DETAIL_URL.format(id=i), "nome_cientifico_raw": ""}
                for i in ids
            ]
            log.info("modo --only-ids: %d espécies", len(items))
        else:
            items = await crawl_ids(fetcher)
            log.info("listagem concluída: %d espécies", len(items))

        sem = asyncio.Semaphore(args.workers)
        records: list[LPFRecord] = []
        falhas: list[dict] = []

        async def worker(item: dict) -> None:
            async with sem:
                try:
                    rec = await fetch_species(fetcher, item)
                except RedeIndisponivel:
                    raise
                except Exception as exc:  # noqa: BLE001
                    log.exception("erro em id=%s", item["lpf_id"])
                    falhas.append({"lpf_id": item["lpf_id"], "erro": repr(exc)})
                    return
                if rec is None:
                    falhas.append({"lpf_id": item["lpf_id"], "erro": "parse vazio"})
                    return
                if not args.no_images:
                    await download_images(fetcher, rec, img_root)
                records.append(rec)
                log.info("[%3d] %-40s id=%s", len(records), rec.nome_cientifico, rec.lpf_id)

        try:
            await asyncio.gather(*(worker(it) for it in items))
        except RedeIndisponivel as exc:
            log.error("\n%s\n%s\n%s", "=" * 72, exc, "=" * 72)
            if not records:
                return 2
            log.warning("salvando parcialmente as %d espécies obtidas antes da queda", len(records))

        records.sort(key=lambda r: r.nome_cientifico)

        dataset = {
            "meta": {
                "nome": "dataset_lpf",
                "versao": "1.0.0",
                "gerado_em": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "fonte_primaria": LIST_URL,
                "licenca": "Dados públicos LPF/Serviço Florestal Brasileiro — uso acadêmico, citar a fonte.",
                "total_registros": len(records),
                "total_falhas": len(falhas),
                "campos_anatomicos_pendentes_mcb": [
                    "vasos_porosidade", "vasos_agrupamento", "vasos_obstrucao",
                    "tiloses_substancias", "parenquima_axial",
                    "parenquima_apotraqueal", "parenquima_paratraqueal",
                    "raios_visibilidade", "dominio_fitogeografico",
                ],
            },
            "especies": [record_to_dataset_entry(r) for r in records],
            "falhas": falhas,
        }

        if not records:
            log.error(
                "\n%s\nNENHUMA espécie foi extraída (%d falhas). Nada foi gravado.\n"
                "Se as falhas forem de rede, veja o diagnóstico acima. Se forem de parse, "
                "rode:\n"
                "    python -m scraper.lpf_scraper --only-ids 284 --no-images -v\n"
                "e compare os rótulos da página com _FIELD_MAP neste arquivo.\n%s",
                "=" * 72, len(falhas), "=" * 72,
            )
            return 2

        out_json = out_dir / "dataset_lpf.json"
        out_json.write_text(
            json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        log.info("✔ %s — %d espécies, %d falhas", out_json, len(records), len(falhas))
        if falhas:
            log.warning("falhas: %s", [f["lpf_id"] for f in falhas])
        return 0
    finally:
        await fetcher.aclose()


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Scraper do catálogo LPF/SFB")
    p.add_argument("--out", default="data", help="diretório de saída (default: data)")
    p.add_argument("--workers", type=int, default=6, help="requisições simultâneas")
    p.add_argument("--delay", type=float, default=0.35, help="intervalo mínimo entre requisições (s)")
    p.add_argument("--no-images", action="store_true", help="não baixar imagens")
    p.add_argument("--no-cache", action="store_true", help="ignorar cache em disco")
    p.add_argument("--only-ids", default="", help="lista de IDs LPF separados por vírgula")
    p.add_argument("--check", action="store_true",
                   help="só testar a conectividade com o LPF e sair")
    p.add_argument("--offline", action="store_true",
                   help="reprocessar apenas o que já está em data/.cache, sem tocar a rede "
                        "(use depois de corrigir o parser)")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def _console_utf8() -> None:
    """
    O console do Windows abre em cp1252 e explode em qualquer acento ou símbolo
    ('✔', '—', '→'), transformando as mensagens do scraper num despejo de
    'UnicodeEncodeError'. Reconfigurar para UTF-8 com errors='replace' resolve
    sem depender de `chcp 65001` nem de variável de ambiente.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    _console_utf8()
    args = build_argparser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
