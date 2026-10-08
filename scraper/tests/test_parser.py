"""
Parser testado contra o HTML REAL do LPF.

As fixtures são páginas servidas por lpf.florestal.gov.br, capturadas em
2026-08-30 e guardadas sem edição:

  real_detalhe_284_alexa_grandiflora.html  template A ("Cor: ...", "Figura: ...")
  real_detalhe_002_acioa_edulis.html       template B ("Cor do cerne: ...",
                                           "Camadas de crescimento: ...",
                                           "Figura tangencial/radial: ...")
  real_listagem_start0.html                primeira página da listagem

Os dois templates convivem no site: a primeira versão do parser só entendia
linhas de tabela "rótulo | valor" e extraiu 0% de cor/grã/textura/anéis nas
271 espécies. O que o LPF usa de verdade são BLOCOS
`<p><span class="font-weight-bold">Rótulo:</span> sub: v; sub: v; ...</p>`
e tabelas-matriz com colspan/rowspan.
"""
from pathlib import Path

import pytest

from scraper.lpf_scraper import (
    expandir_tabela,
    parse_bloco_composto,
    parse_detail,
    parse_listing,
    record_to_dataset_entry,
    total_from_listing,
)
from scraper.normalize import map_aneis_crescimento, map_cor_cerne, parse_scientific_name, to_float

FX = Path(__file__).parent / "fixtures"


def carregar(nome: str) -> str:
    return (FX / nome).read_text(encoding="utf-8", errors="replace")


@pytest.fixture(scope="module")
def alexa():
    return parse_detail(carregar("real_detalhe_284_alexa_grandiflora.html"), 284, "http://x/284")


@pytest.fixture(scope="module")
def acioa():
    return parse_detail(carregar("real_detalhe_002_acioa_edulis.html"), 2, "http://x/2")


# ────────────────────────────────────────────────────────────────── listagem

def test_listagem_real_traz_20_especies():
    itens = parse_listing(carregar("real_listagem_start0.html"))
    assert len(itens) == 20
    ids = {i["lpf_id"] for i in itens}
    assert {2, 3, 148, 284} <= ids

    alexa = next(i for i in itens if i["lpf_id"] == 284)
    assert alexa["nome_cientifico_raw"] == "Alexa grandiflora"
    assert alexa["nome_popular_listagem"] == "Melancieira"
    assert "especieestudadaid=284" in alexa["url"]


def test_listagem_preserva_sinonimo_com_igual():
    itens = parse_listing(carregar("real_listagem_start0.html"))
    alb = next(i for i in itens if i["lpf_id"] == 148)
    assert alb["nome_cientifico_raw"] == "Albizia pedicellaris = Macrosamanea pedicellaris"


def test_total_da_listagem_e_limite_superior_util():
    total = total_from_listing(carregar("real_listagem_start0.html"))
    assert total is not None and 260 <= total <= 320   # o catálogo tem 271


# ───────────────────────────────────────────── template A (Alexa grandiflora)

def test_taxonomia_A(alexa):
    assert alexa.nome_cientifico == "Alexa grandiflora"
    assert alexa.familia == "Fabaceae"
    assert alexa.slug == "alexa_grandiflora"
    assert alexa.local_coleta == "Santarém-PA"
    assert alexa.nomes_populares == ["Melancieira", "Sucupira-pepino"]


def test_caracteres_gerais_A(alexa):
    """Estes seis campos vinham TODOS vazios antes da correção."""
    assert alexa.cerne_alburno == "indistintos"
    assert alexa.cor == "amarelo-amarronzado a marrom-claro"
    assert alexa.aneis_crescimento == "pouco distintos"
    assert alexa.gra == "cruzada ondulada"
    assert alexa.textura == "média a grossa"
    assert alexa.figura == "ausente"
    assert alexa.brilho == "fraco"


def test_bloco_arvore_A(alexa):
    assert alexa.altura_comercial == "12m"          # sem dois-pontos no HTML
    assert alexa.dap == "79 cm"
    assert alexa.tronco == "reto, cilíndrico"
    assert "0,5 - 1,0" in alexa.casca_espessura


def test_trabalhabilidade_A(alexa):
    assert alexa.trabalhabilidade["Serragem"] == "média"
    assert alexa.trabalhabilidade["Aplainamento"].startswith("médio")


def test_codigos_mcb_A(alexa):
    assert map_aneis_crescimento(alexa.aneis_crescimento) == "POUCO_DISTINTOS"
    assert alexa.classificacao_cor_cerne == "Amarela"
    assert map_cor_cerne(alexa.classificacao_cor_cerne) == "AMARELA"


def test_imagem_real_tem_sufixo_numerico(alexa):
    """O arquivo é 'Alexa grandiflora3.jpg', não 'Alexa grandiflora.jpg'."""
    assert len(alexa.imagens) >= 1
    assert alexa.imagens[0]["url"].endswith("/images/madeirasbrasileiras/Alexa grandiflora3.jpg")


# ──────────────────────────────────────────────── template B (Acioa edulis)

def test_taxonomia_B(acioa):
    assert acioa.nome_cientifico == "Acioa edulis"
    assert acioa.familia == "Chrysobalanaceae"
    assert acioa.local_coleta == "Juruá-Solimões-AM"


def test_cor_do_cerne_nao_e_capturada_como_do_alburno(acioa):
    """
    'Cor do cerne: X; Cor do alburno: Y' — o prefixo mais longo vence, senão
    'Cor' engolia 'do alburno: ...' e a cor do CERNE (a diagnóstica) se perdia.
    """
    assert acioa.cor.startswith("marrom a marrom-avermelhado")
    assert acioa.cor_alburno.startswith("marrom-claro")


def test_camadas_de_crescimento_vira_aneis(acioa):
    assert acioa.aneis_crescimento == "pouco distintas"
    assert map_aneis_crescimento(acioa.aneis_crescimento) == "POUCO_DISTINTOS"


def test_figura_tangencial_e_radial_separadas(acioa):
    assert "fibroso" in acioa.figura
    assert "linhas vasculares" in acioa.figura_radial


def test_demais_caracteres_B(acioa):
    assert acioa.cerne_alburno == "distintos"
    assert acioa.gra == "revessa"
    assert acioa.textura == "média"
    assert acioa.brilho == "ausente"
    assert acioa.cheiro == "imperceptível"


# ───────────────────────────────────────── blocos compostos (unidade)

def test_bloco_composto_separa_por_ponto_e_virgula():
    out = parse_bloco_composto(
        "Cerne/Alburno: indistintos; Cor: amarelo; Grã: cruzada; Textura: média a grossa;",
        "caracteristicas gerais")
    assert out == {"Cerne/Alburno": "indistintos", "Cor": "amarelo",
                   "Grã": "cruzada", "Textura": "média a grossa"}


def test_bloco_composto_sem_dois_pontos():
    out = parse_bloco_composto("Altura comercial 12m; Diâmetro (DAP) 79 cm", "arvore")
    assert out == {"Altura comercial": "12m", "Diâmetro (DAP)": "79 cm"}


def test_bloco_composto_guarda_sobra_em_texto():
    out = parse_bloco_composto("Madeira média-pesada - não aceita prego", "trabalhabilidade")
    assert out["_texto"] == "Madeira média-pesada - não aceita prego"


def test_bloco_composto_vazio():
    assert parse_bloco_composto("", "arvore") == {}
    assert parse_bloco_composto("   ;  ; ", "arvore") == {}


# ──────────────────────────────────── tabelas-matriz (colspan/rowspan)

def test_expandir_tabela_resolve_colspan_e_rowspan():
    from bs4 import BeautifulSoup
    html = """<table>
      <tr><td rowspan="2">Condição</td><td colspan="2">Flexão (MPa)</td></tr>
      <tr><td>Ruptura</td><td>Elasticidade</td></tr>
      <tr><td>Verde</td><td>68,25</td><td>9,61</td></tr>
    </table>"""
    g = expandir_tabela(BeautifulSoup(html, "lxml").find("table"))
    assert g[0] == ["Condição", "Flexão (MPa)", "Flexão (MPa)"]
    assert g[1] == ["Condição", "Ruptura", "Elasticidade"]     # rowspan propagado
    assert g[2] == ["Verde", "68,25", "9,61"]


def test_propriedades_mecanicas_com_valores_reais(alexa):
    p = alexa.propriedades
    assert p["Flexão Estática (kgf/cm²) · Módulo de Ruptura · Seca"] == pytest.approx(1114.0)
    assert p["Flexão Estática (kgf/cm²) · Módulo de Ruptura · Verde"] == pytest.approx(696.0)
    assert p["Dureza Janka (kgf) · Paralelas às Fibras · Seca"] == pytest.approx(768.0)
    assert p["Flexão Estática (MPa) · Módulo de Ruptura · Seca"] == pytest.approx(109.25)


def test_atalhos_numericos(alexa, acioa):
    assert alexa.atalhos["densidade_basica"] == pytest.approx(0.60)
    assert alexa.atalhos["contracao_volumetrica"] == pytest.approx(14.50)
    # template B: a linha de densidade começa por número, não por 'Verde'/'Seca'
    assert acioa.atalhos["densidade_basica"] == pytest.approx(0.82)
    assert acioa.atalhos["contracao_tangencial"] == pytest.approx(10.28)


def test_tabela_de_acabamento_nao_vira_propriedade(alexa):
    """'Número de Amostras: 13 12 28 31' tem números mas é cabeçalho, não dado."""
    assert not any("Amostras" in k for k in alexa.propriedades)
    assert not any("Resultados" in k for k in alexa.propriedades)


def test_valor_ausente_vira_none_e_nao_zero(alexa):
    secos = [v for k, v in alexa.propriedades.items() if "Aparente" in k]
    assert secos and all(v is None for v in secos)


def test_ambas_as_fichas_tem_o_mesmo_numero_de_propriedades(alexa, acioa):
    assert len(alexa.propriedades) == len(acioa.propriedades) == 52


def test_rodape_institucional_nao_vira_campo(alexa):
    assert not any("Telefone" in k or "Email" in k for k in alexa.campos_brutos)


# ─────────────────────────────────────────────────────── normalização

@pytest.mark.parametrize(
    "raw,slug,binomial",
    [
        ("Alexa grandiflora Ducke", "alexa_grandiflora", "Alexa grandiflora"),
        ("Albizia pedicellaris (DC.) L. Rico", "albizia_pedicellaris", "Albizia pedicellaris"),
        ("Allantoma decandra (Ducke) S.A. Mori, Ya Y.Huang & Pr.", "allantoma_decandra", "Allantoma decandra"),
        ("Amburana cearensis (Allemão) A.C. Sm.", "amburana_cearensis", "Amburana cearensis"),
    ],
)
def test_parse_nome_com_autor(raw, slug, binomial):
    sn = parse_scientific_name(raw)
    assert sn.slug == slug
    assert sn.binomial == binomial


def test_sinonimos_viram_aliases():
    sn = parse_scientific_name("Albizia pedicellaris = Macrosamanea pedicellaris")
    assert sn.slug == "albizia_pedicellaris"
    assert sn.synonyms == ["Macrosamanea pedicellaris"]
    assert "macrosamanea_pedicellaris" in sn.all_slugs()


def test_especie_indeterminada():
    sn = parse_scientific_name("Acioa sp.")
    assert sn.indeterminate is True
    assert sn.slug == "acioa_sp"


def test_folder_sem_acento():
    assert parse_scientific_name("Aniba canelilla").folder == "Aniba_canelilla"


@pytest.mark.parametrize(
    "raw,esperado",
    [("1.114,00", 1114.0), ("0,60", 0.60), ("21.00", 21.0), ("", None), ("-", None), ("79 cm", 79.0)],
)
def test_to_float_ptbr(raw, esperado):
    assert to_float(raw) == (pytest.approx(esperado) if esperado is not None else None)


@pytest.mark.parametrize(
    "raw,codigo",
    [("distintos", "DISTINTOS"), ("distintas", "DISTINTOS"), ("pouco distintos", "POUCO_DISTINTOS"),
     ("pouco distintas", "POUCO_DISTINTOS"), ("indistintos", "INDISTINTOS"),
     ("ausentes", "INDISTINTOS"), ("", None)],
)
def test_map_aneis(raw, codigo):
    assert map_aneis_crescimento(raw) == codigo


@pytest.mark.parametrize("raw,codigo",
                         [("Amarela", "AMARELA"), ("Marrom", "MARROM_ESCURA"),
                          ("Rosa", "ROSA_AVERMELHADA"), ("Branca", "BRANCA_BEGE")])
def test_map_cor(raw, codigo):
    assert map_cor_cerne(raw) == codigo


# ────────────────────────────────────────────────────── schema de saída

def test_entrada_do_dataset_tem_schema_completo(alexa):
    e = record_to_dataset_entry(alexa)
    assert e["id"] == "alexa_grandiflora"
    assert e["taxonomia"]["nome_cientifico"] == "Alexa grandiflora"
    cg = e["caracteres_gerais"]
    assert cg["cor_descricao"] == "amarelo-amarronzado a marrom-claro"
    assert cg["gra"] == "cruzada ondulada"
    am = e["anatomia_macroscopica"]
    assert am["aneis_crescimento"] == "POUCO_DISTINTOS"
    assert am["cor_madeira"] == "AMARELA"
    # campos MCB nascem vazios e são preenchidos pelo merge
    assert am["vasos_porosidade"] is None
    assert am["parenquima_paratraqueal"] == []
    assert e["propriedades_chave"]["densidade_basica"] == pytest.approx(0.60)
    assert "Características Gerais" in e["blocos_lpf"]
    assert e["proveniencia"]["lpf"] is True and e["proveniencia"]["mcb"] is False
