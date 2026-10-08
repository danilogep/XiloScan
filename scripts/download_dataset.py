"""Baixa e instala o dataset do XiloScan a partir de um release do GitHub.

    python scripts/download_dataset.py

O dataset (catálogo LPF + imagens macroscópicas) não é versionado no git: são
dezenas de megabytes de binário que mudam em bloco a cada recoleta, e o histórico
do repositório ficaria pesado sem ganho nenhum. Ele é publicado como *asset* de
release e instalado por este script.

Quem prefere regerar tudo da fonte primária usa o scraper em vez deste script:

    python -m scraper.lpf_scraper --saida data/dataset_lpf.json --imagens data/images

Origem dos dados
----------------
Laboratório de Produtos Florestais (LPF) do Serviço Florestal Brasileiro:
https://lpf.florestal.gov.br/pt-br/madeiras-brasileiras

Dados públicos, de uso acadêmico, com citação obrigatória da fonte. Este script
não redistribui nada: ele apenas baixa o pacote publicado no release deste
repositório e o descompacta em `data/`.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "data"

URL_PADRAO = (
    "https://github.com/danilogep/XiloScan/releases/download/dataset-v1/xiloscan_dataset.zip"
)

# Conteúdo esperado depois da extração — serve de verificação rápida de que o
# pacote baixado é mesmo o do projeto, e não um zip qualquer.
ESPERADOS = ("dataset_lpf.json", "images")


def baixar(url: str, alvo: Path) -> None:
    print(f"baixando {url}")
    with urllib.request.urlopen(url) as resposta, alvo.open("wb") as saida:  # noqa: S310
        total = int(resposta.headers.get("Content-Length") or 0)
        lidos = 0
        while bloco := resposta.read(1 << 20):
            saida.write(bloco)
            lidos += len(bloco)
            if total:
                print(f"\r  {lidos / 1048576:6.1f} / {total / 1048576:.1f} MB", end="")
        print()


def sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        while bloco := f.read(1 << 20):
            h.update(bloco)
    return h.hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--url", default=URL_PADRAO, help="URL do pacote .zip")
    ap.add_argument("--arquivo", type=Path, help="usa um .zip local em vez de baixar")
    ap.add_argument("--destino", type=Path, default=DESTINO)
    ap.add_argument("--forcar", action="store_true", help="sobrescreve um dataset já instalado")
    args = ap.parse_args(argv)

    destino: Path = args.destino
    ja_instalado = (destino / "dataset_lpf.json").exists()
    if ja_instalado and not args.forcar:
        print(f"dataset já instalado em {destino} — use --forcar para sobrescrever")
        return 0

    destino.mkdir(parents=True, exist_ok=True)
    temporario = destino / "_download.zip"

    try:
        if args.arquivo:
            shutil.copyfile(args.arquivo, temporario)
        else:
            baixar(args.url, temporario)

        print(f"sha256: {sha256(temporario)}")

        with zipfile.ZipFile(temporario) as z:
            nomes = z.namelist()
            # Um zip de origem desconhecida pode trazer caminhos absolutos ou
            # ".." e escrever fora de data/. Recusamos antes de extrair.
            for nome in nomes:
                caminho = Path(nome)
                if caminho.is_absolute() or ".." in caminho.parts:
                    print(f"ERRO: caminho suspeito no pacote: {nome}", file=sys.stderr)
                    return 1
            z.extractall(destino)
            print(f"extraídos {len(nomes)} itens em {destino}")
    finally:
        temporario.unlink(missing_ok=True)

    faltando = [e for e in ESPERADOS if not (destino / e).exists()]
    if faltando:
        print(f"AVISO: não encontrei em {destino}: {', '.join(faltando)}", file=sys.stderr)
        return 1

    print("pronto. Agora construa o índice:")
    print("  python -m backend.scripts.build_index --augment 8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
