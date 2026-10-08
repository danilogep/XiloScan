"""
O relatório de cobertura é o "deu certo?" — precisa REPROVAR o dataset velho.

Regressão de 2026-08-30: o scrape terminou anunciando "271 registros, 0 falhas"
com 0% de cor, grã, textura e anéis. Contar registros não é validar.
"""
import io
import json
import sys

import pytest

from scraper.relatorio import CRITICOS, ESSENCIAIS, main


def especie(**over):
    base = {
        "id": "alexa_grandiflora",
        "taxonomia": {"nome_cientifico": "Alexa grandiflora", "familia": "Fabaceae",
                      "nomes_populares": ["Melancieira"]},
        "procedencia": {"local_coleta": "Santarém-PA"},
        "caracteres_gerais": {"cor_descricao": "amarelo", "gra": "cruzada",
                              "textura": "média", "cerne_alburno": "indistintos"},
        "anatomia_macroscopica": {"aneis_crescimento": "POUCO_DISTINTOS",
                                  "aneis_crescimento_texto": "pouco distintos",
                                  "cor_madeira": "AMARELA"},
        "propriedades": {f"p{i}": float(i) for i in range(30)},
        "propriedades_chave": {"densidade_basica": 0.60},
        "imagens": [{"arquivo": "images/x/x_01.jpg"}],
    }
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            base[k] = {**base[k], **v}
        else:
            base[k] = v
    return base


def escrever(tmp_path, especies, meta=None):
    p = tmp_path / "d.json"
    p.write_text(json.dumps({"meta": meta or {"total_falhas": 0}, "especies": especies}),
                 encoding="utf-8")
    return p


def rodar(caminho, capsys):
    codigo = main(["--dataset", str(caminho)])
    return codigo, capsys.readouterr().out


def test_dataset_bom_sai_zero(tmp_path, capsys):
    codigo, saida = rodar(escrever(tmp_path, [especie()]), capsys)
    assert codigo == 0
    assert "RESULTADO: OK" in saida


def test_dataset_do_parser_velho_e_reprovado(tmp_path, capsys):
    """Exatamente o dataset que estava em disco: taxonomia ok, anatomia vazia."""
    velho = especie(
        caracteres_gerais={"cor_descricao": "", "gra": "", "textura": "", "cerne_alburno": ""},
        anatomia_macroscopica={"aneis_crescimento": None, "aneis_crescimento_texto": "",
                               "cor_madeira": "AMARELA"},
        propriedades={"Tempo de secagem (dias)": 21.0},
        propriedades_chave={},
    )
    codigo, saida = rodar(escrever(tmp_path, [velho] * 5), capsys)
    assert codigo == 1
    assert "DATASET INCOMPLETO" in saida
    assert "--offline" in saida          # diz o que fazer
    for campo in ("cor (descrição)", "grã", "textura"):
        assert campo in saida


def test_reprova_no_limiar(tmp_path, capsys):
    """70% é o piso de 'cor (descrição)': 6/10 reprova, 7/10 passa."""
    vazio = especie(caracteres_gerais={"cor_descricao": ""})
    codigo, _ = rodar(escrever(tmp_path, [especie()] * 6 + [vazio] * 4), capsys)
    assert codigo == 1
    codigo, _ = rodar(escrever(tmp_path, [especie()] * 7 + [vazio] * 3), capsys)
    assert codigo == 0


def test_avisa_quando_merge_mcb_nao_foi_aplicado(tmp_path, capsys):
    _, saida = rodar(escrever(tmp_path, [especie()]), capsys)
    assert "camada MCB: NÃO aplicada" in saida
    assert "scraper.mcb_merge" in saida


def test_mostra_resumo_do_merge(tmp_path, capsys):
    meta = {"total_falhas": 0, "mcb": {"especies_com_overlay": 157, "completeness_media": 0.91}}
    _, saida = rodar(escrever(tmp_path, [especie()], meta), capsys)
    assert "157 espécies com overlay" in saida
    assert "0.91" in saida


def test_dataset_inexistente(tmp_path, capsys):
    codigo, saida = rodar(tmp_path / "nao_existe.json", capsys)
    assert codigo == 2
    assert "não existe" in saida


def test_dataset_sem_especies(tmp_path, capsys):
    codigo, saida = rodar(escrever(tmp_path, []), capsys)
    assert codigo == 2
    assert "sem espécies" in saida


def test_criticos_sao_subconjunto_dos_essenciais():
    nomes = {n for n, _ in ESSENCIAIS}
    assert set(CRITICOS) <= nomes


# ────────────────────────────────────────── console cp1252 (Windows)

@pytest.mark.parametrize("modulo", ["scraper.lpf_scraper", "scraper.mcb_merge"])
def test_console_utf8_nao_explode_em_stream_sem_reconfigure(modulo, monkeypatch):
    """
    O console do Windows abre em cp1252 e quebra em '✔', '—', '→'.
    _console_utf8 tem de ser tolerante: streams sem .reconfigure (um StringIO
    de teste, um pipe redirecionado) não podem derrubar o programa.
    """
    import importlib
    mod = importlib.import_module(modulo)
    monkeypatch.setattr(sys, "stdout", io.StringIO())
    monkeypatch.setattr(sys, "stderr", io.StringIO())
    mod._console_utf8()      # não levanta


def test_mensagens_com_simbolos_sobrevivem_a_cp1252():
    """Com errors='replace', '✔' vira '?' em vez de derrubar o log."""
    bruto = io.BytesIO()
    stream = io.TextIOWrapper(bruto, encoding="cp1252", errors="replace")
    stream.write("✔ dataset — 271 espécies → OK")
    stream.flush()
    assert b"dataset" in bruto.getvalue()
