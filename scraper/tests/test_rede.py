"""
Comportamento do scraper quando a rede não está disponível.

Regressão do relato de 2026-09-02: sem rede, o scraper fazia 5 retries por URL
(≈60 s), gravava um dataset vazio e imprimia "✔ 0 espécies" — parecia sucesso.
"""
import socket
from pathlib import Path

import httpx
import pytest

from scraper.lpf_scraper import (
    RedeIndisponivel,
    _e_erro_de_dns,
    build_argparser,
    main,
    preflight,
    proxy_configurado,
)

# ─────────────────────────────────────────────── classificação do erro de DNS

def test_detecta_gaierror_direto():
    assert _e_erro_de_dns(socket.gaierror(-3, "Temporary failure in name resolution"))


def test_detecta_gaierror_encadeado_como_httpx_connecterror():
    """É exatamente a forma que o httpx entrega: ConnectError(gaierror(-3, ...))."""
    try:
        try:
            raise socket.gaierror(-3, "Temporary failure in name resolution")
        except socket.gaierror as raiz:
            raise httpx.ConnectError("[Errno -3] Temporary failure in name resolution") from raiz
    except httpx.ConnectError as exc:
        assert _e_erro_de_dns(exc)


def test_detecta_pela_mensagem_sem_gaierror():
    assert _e_erro_de_dns(httpx.ConnectError("[Errno -3] Temporary failure in name resolution"))


def test_nao_confunde_timeout_com_dns():
    assert not _e_erro_de_dns(httpx.ReadTimeout("timed out"))
    assert not _e_erro_de_dns(httpx.HTTPStatusError("500", request=None, response=None))


def test_ciclo_de_causas_nao_trava():
    a = ValueError("a")
    b = ValueError("b")
    a.__cause__ = b
    b.__cause__ = a
    assert _e_erro_de_dns(a) is False   # termina, não pendura


# ─────────────────────────────────────────────────────────────────── preflight

def test_preflight_falha_rapido_em_host_inexistente():
    with pytest.raises(RedeIndisponivel) as ei:
        preflight("host.que.nao.existe.invalid", timeout=3)
    msg = str(ei.value)
    assert "não resolve" in msg
    assert "Colab" in msg                     # caminho de saída acionável
    assert "HTTPS_PROXY" in msg               # diagnóstico de proxy
    assert "Nada foi baixado" in msg          # promete que não sujou o disco


def test_preflight_ok_quando_dns_e_http_respondem(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [("AF_INET",)])

    class ClienteFake:
        def __init__(self, **_): pass
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def get(self, url):
            return httpx.Response(200, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "Client", ClienteFake)
    preflight("qualquer.host", timeout=1)     # não levanta


@pytest.mark.parametrize("status,trecho", [(403, "egress"), (503, "fora do ar")])
def test_preflight_classifica_status_http(monkeypatch, status, trecho):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [("AF_INET",)])

    class ClienteFake:
        def __init__(self, **_): pass
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def get(self, url):
            return httpx.Response(status, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "Client", ClienteFake)
    with pytest.raises(RedeIndisponivel, match=trecho):
        preflight("qualquer.host", timeout=1)


def test_proxy_configurado_le_o_ambiente(monkeypatch):
    for v in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(v, raising=False)
    assert proxy_configurado() is None
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy:3128")
    assert proxy_configurado() == "HTTPS_PROXY=http://proxy:3128"


# ────────────────────────────────────────────────────────── integração do CLI

def test_run_aborta_com_codigo_2_e_nao_grava_nada(monkeypatch, tmp_path, caplog):
    """Sem rede: sai em segundos, código 2, e o diretório de saída nem é criado."""
    import scraper.lpf_scraper as mod

    def sem_rede(*_a, **_k):
        raise RedeIndisponivel("sem rede (teste)")

    monkeypatch.setattr(mod, "preflight", sem_rede)
    saida = tmp_path / "data"
    codigo = main(["--out", str(saida), "--only-ids", "2", "--no-images"])

    assert codigo == 2
    assert not saida.exists(), "nada deve ser gravado quando a rede falha"
    assert "sem rede (teste)" in caplog.text


def test_check_sai_zero_quando_a_rede_esta_ok(monkeypatch):
    import scraper.lpf_scraper as mod
    monkeypatch.setattr(mod, "preflight", lambda *a, **k: None)
    assert main(["--check"]) == 0


def test_flag_check_existe_no_parser():
    args = build_argparser().parse_args(["--check"])
    assert args.check is True
    assert build_argparser().parse_args([]).check is False


def test_dataset_vazio_por_parse_retorna_2(monkeypatch, tmp_path, caplog):
    """Rede OK mas todas as páginas falham no parse: código 2, não 'sucesso vazio'."""
    import scraper.lpf_scraper as mod
    monkeypatch.setattr(mod, "preflight", lambda *a, **k: None)

    async def nada(fetcher, item):
        return None

    monkeypatch.setattr(mod, "fetch_species", nada)
    saida = tmp_path / "data"
    codigo = main(["--out", str(saida), "--only-ids", "2,284", "--no-images"])

    assert codigo == 2
    assert not (saida / "dataset_lpf.json").exists()
    assert "NENHUMA espécie foi extraída" in caplog.text
    assert "_FIELD_MAP" in caplog.text        # diz o que fazer se for parse


# ──────────────────────────────────────────────────────────── modo offline

def test_offline_nao_chama_preflight_nem_a_rede(monkeypatch, tmp_path):
    """
    --offline reprocessa o que já está em data/.cache. É o caminho para
    corrigir o parser e refazer o dataset sem baixar nada de novo.
    """
    import scraper.lpf_scraper as mod

    chamou = {"preflight": False}

    def nao_deveria(*_a, **_k):
        chamou["preflight"] = True
        raise AssertionError("preflight não deve ser chamado em --offline")

    monkeypatch.setattr(mod, "preflight", nao_deveria)
    codigo = main(["--offline", "--out", str(tmp_path / "d"), "--only-ids", "284", "--no-images"])

    assert chamou["preflight"] is False
    assert codigo == 2                      # cache vazio neste tmp: nada a processar


def test_offline_le_do_cache_sem_rede(tmp_path, monkeypatch):
    """Com a página no cache, --offline extrai a espécie sem tocar em httpx."""
    import hashlib

    import scraper.lpf_scraper as mod

    url = mod.DETAIL_URL.format(id=284)
    cache = tmp_path / "d" / ".cache"
    cache.mkdir(parents=True)
    nome = hashlib.sha256(url.encode()).hexdigest()[:24] + ".html"
    fixture = Path(__file__).parent / "fixtures" / "real_detalhe_284_alexa_grandiflora.html"
    (cache / nome).write_bytes(fixture.read_bytes())

    def sem_rede(*_a, **_k):
        raise AssertionError("nenhuma requisição deveria sair em --offline")

    monkeypatch.setattr(httpx.AsyncClient, "get", sem_rede)

    assert main(["--offline", "--out", str(tmp_path / "d"), "--only-ids", "284", "--no-images"]) == 0

    import json
    ds = json.loads((tmp_path / "d" / "dataset_lpf.json").read_text(encoding="utf-8"))
    assert ds["meta"]["total_registros"] == 1
    esp = ds["especies"][0]
    assert esp["id"] == "alexa_grandiflora"
    assert esp["caracteres_gerais"]["cor_descricao"] == "amarelo-amarronzado a marrom-claro"
    assert esp["propriedades_chave"]["densidade_basica"] == 0.60
