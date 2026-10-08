"""
Os notebooks precisam rodar no Colab E localmente, sem edição.

Regressões que estes testes travam:
  * `source` com linhas sem "\\n" -> o Colab colapsa a célula numa linha só;
  * `%%writefile` fora da primeira linha -> a magic não roda;
  * `os.chdir('/content/...')` incondicional -> no Windows vira C:\\content\\...,
    fora do projeto e longe do cache;
  * `!python` / `!pip` -> no Windows `python` pode abrir a Microsoft Store;
  * `from google.colab import ...` sem proteção -> ImportError na máquina local;
  * célula %%writefile fora de sincronia com o arquivo real do repositório.
"""
import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
NOTEBOOKS = sorted((RAIZ / "notebooks").glob("*.ipynb"))


def celulas(nb_path: Path):
    d = json.loads(nb_path.read_text(encoding="utf-8"))
    return [(i, c["cell_type"], "".join(c["source"])) for i, c in enumerate(d["cells"])]


def codigo(nb_path: Path):
    return [(i, s) for i, t, s in celulas(nb_path) if t == "code"]


def test_existem_dois_notebooks():
    assert [p.name for p in NOTEBOOKS] == ["01_catalogo_lpf.ipynb", "02_modelo_e_api.ipynb"]


@pytest.mark.parametrize("nb", NOTEBOOKS, ids=lambda p: p.name)
def test_json_valido_e_linhas_terminam_em_newline(nb):
    d = json.loads(nb.read_text(encoding="utf-8"))
    assert d["nbformat"] == 4
    for i, c in enumerate(d["cells"]):
        src = c["source"]
        assert src, f"célula {i} vazia"
        for ln in src[:-1]:
            assert ln.endswith("\n"), f"célula {i}: linha sem '\\n' — o Colab colapsa a célula"


@pytest.mark.parametrize("nb", NOTEBOOKS, ids=lambda p: p.name)
def test_writefile_e_sempre_a_primeira_linha(nb):
    for i, s in codigo(nb):
        linhas = s.split("\n")
        for k, ln in enumerate(linhas):
            if ln.lstrip().startswith("%%writefile"):
                assert k == 0, f"célula {i}: %%writefile na linha {k}, tem de ser a 0"


@pytest.mark.parametrize("nb", NOTEBOOKS, ids=lambda p: p.name)
def test_nao_ha_chamada_a_python_ou_pip_pelo_PATH(nb):
    """Tudo tem de usar {PYQ} = sys.executable, o mesmo interpretador do notebook."""
    for i, s in codigo(nb):
        if s.startswith("%%writefile"):
            continue                      # o corpo é código-fonte, não comandos do notebook
        for ln in s.split("\n"):
            t = ln.strip()
            assert not t.startswith("!python "), f"célula {i}: use !{{PYQ}} em vez de !python"
            assert not t.startswith("!pip "), f"célula {i}: use !{{PYQ}} -m pip em vez de !pip"


@pytest.mark.parametrize("nb", NOTEBOOKS, ids=lambda p: p.name)
def test_google_colab_sempre_protegido(nb):
    """Import do google.colab só dentro de `if EH_COLAB` ou try/except."""
    for i, s in codigo(nb):
        if s.startswith("%%writefile") or "google.colab" not in s:
            continue
        assert "EH_COLAB" in s or "try:" in s, (
            f"célula {i}: importa google.colab sem proteção — quebra na máquina local"
        )


@pytest.mark.parametrize("nb", NOTEBOOKS, ids=lambda p: p.name)
def test_caminhos_do_colab_nunca_incondicionais(nb):
    """'/content/...' só pode aparecer em célula que também decide o ambiente."""
    for i, s in codigo(nb):
        if s.startswith("%%writefile") or "/content/" not in s:
            continue
        assert "EH_COLAB" in s or "try:" in s, (
            f"célula {i}: caminho /content/ sem checar o ambiente — "
            f"no Windows viraria C:\\content\\..."
        )


@pytest.mark.parametrize("nb", NOTEBOOKS, ids=lambda p: p.name)
def test_ambiente_e_definido_no_inicio(nb):
    """EH_COLAB / PROJETO / os.chdir têm de sair de uma das 3 primeiras células."""
    inicio = "\n".join(s for _, s in codigo(nb)[:3])
    for token in ("EH_COLAB", "PROJETO", "os.chdir", "sys.executable"):
        assert token in inicio, f"{nb.name}: {token} não aparece nas 3 primeiras células"


@pytest.mark.parametrize("nb", NOTEBOOKS, ids=lambda p: p.name)
def test_PROJETO_nao_e_usado_antes_de_ser_definido(nb):
    cels = codigo(nb)
    definicao = next(i for i, (_, s) in enumerate(cels) if "PROJETO = " in s)
    for k, (_, s) in enumerate(cels[:definicao]):
        assert "PROJETO" not in s, f"célula de código {k} usa PROJETO antes da definição"


def test_notebook_01_tem_guarda_de_hashes():
    nb = RAIZ / "notebooks" / "01_catalogo_lpf.ipynb"
    guardas = [s for _, s in codigo(nb) if "@sync:hashes" in s]
    assert len(guardas) == 1
    g = guardas[0]
    assert "FONTES_ESPERADAS" in g
    assert "raise RuntimeError" in g, "a guarda tem de interromper o 'Executar tudo'"
    assert "sync_notebooks.py" in g, "a guarda tem de dizer como resolver"


def test_notebooks_em_sincronia_com_o_repositorio():
    """Equivale a `python notebooks/sync_notebooks.py --check`."""
    import subprocess
    import sys

    r = subprocess.run(
        [sys.executable, str(RAIZ / "notebooks" / "sync_notebooks.py"), "--check"],
        capture_output=True, text=True, cwd=RAIZ,
    )
    assert r.returncode == 0, (
        "notebooks fora de sincronia com o código-fonte:\n"
        + r.stdout + r.stderr
        + "\nrode: python notebooks/sync_notebooks.py"
    )
