#!/usr/bin/env python3
"""
Mantém os notebooks em sincronia com o código-fonte do repositório.

Os notebooks são autocontidos: cada célula `%%writefile <caminho>` carrega uma
cópia de um arquivo do projeto. Este script reescreve o corpo dessas células a
partir do arquivo real, e atualiza o dicionário de hashes usado pela célula de
guarda (que impede o notebook de sobrescrever, numa execução local, um fonte
que você editou à mão).

    python notebooks/sync_notebooks.py           # aplica
    python notebooks/sync_notebooks.py --check   # só verifica (CI); sai 1 se divergir

Também valida o formato do .ipynb:
  * toda linha de `source` termina em "\\n", exceto a última
    (sem isso o Colab renderiza a célula inteira numa única linha);
  * `%%writefile` é a PRIMEIRA linha da célula (magic não aceita nada antes).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
MARCA_HASH = "# @sync:hashes"
RE_DICT = re.compile(r"^FONTES_ESPERADAS = \{.*?^\}\n", re.S | re.M)


def como_linhas(texto: str) -> list[str]:
    texto = texto.strip("\n")
    partes = texto.split("\n")
    return [p + "\n" for p in partes[:-1]] + [partes[-1]]


def sha(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()[:16]


def alvos_writefile(nb: dict) -> list[str]:
    out = []
    for cel in nb["cells"]:
        origem = cel.get("source") or []
        if origem and origem[0].startswith("%%writefile"):
            out.append(origem[0].rstrip("\n").split(maxsplit=1)[1].strip())
    return out


def sincronizar(nb_path: Path, apenas_checar: bool) -> list[str]:
    problemas: list[str] = []
    nb = json.loads(nb_path.read_text(encoding="utf-8"))
    mudou = False

    for i, cel in enumerate(nb["cells"]):
        origem = cel.get("source") or []
        if not origem:
            problemas.append(f"{nb_path.name}: célula {i} está vazia")
            continue

        for ln in origem[:-1]:
            if not ln.endswith("\n"):
                problemas.append(
                    f"{nb_path.name}: célula {i} tem linha sem '\\n' — o Colab vai "
                    f"colapsar a célula numa linha só"
                )
                break

        primeira = origem[0].rstrip("\n")
        if not primeira.startswith("%%writefile"):
            if any(l.lstrip().startswith("%%writefile") for l in origem[1:]):
                problemas.append(
                    f"{nb_path.name}: célula {i} tem %%writefile fora da primeira linha"
                )
            continue

        alvo = RAIZ / primeira.split(maxsplit=1)[1].strip()
        if not alvo.exists():
            problemas.append(f"{nb_path.name}: célula {i} aponta para {alvo} (não existe)")
            continue

        novo = como_linhas(f"{primeira}\n{alvo.read_text(encoding='utf-8').rstrip(chr(10))}")
        if novo != origem:
            if apenas_checar:
                problemas.append(
                    f"{nb_path.name}: célula {i} desatualizada em relação a "
                    f"{alvo.relative_to(RAIZ)}"
                )
            else:
                cel["source"] = novo
                mudou = True
                print(f"  fonte atualizada: {alvo.relative_to(RAIZ)}")

    # célula de guarda: dicionário {caminho: sha256[:16]}
    alvos = alvos_writefile(nb)
    for i, cel in enumerate(nb["cells"]):
        texto = "".join(cel.get("source") or [])
        if MARCA_HASH not in texto:
            continue
        faltando = [a for a in alvos if not (RAIZ / a).exists()]
        if faltando:
            problemas.append(f"{nb_path.name}: guarda referencia arquivos ausentes: {faltando}")
            continue
        corpo = "FONTES_ESPERADAS = {\n" + "".join(
            f'    "{a}": "{sha(RAIZ / a)}",\n' for a in alvos
        ) + "}\n"
        if not RE_DICT.search(texto):
            problemas.append(f"{nb_path.name}: célula {i} tem {MARCA_HASH} mas não FONTES_ESPERADAS")
            continue
        novo_texto = RE_DICT.sub(corpo, texto)
        if novo_texto != texto:
            if apenas_checar:
                problemas.append(f"{nb_path.name}: hashes da célula de guarda desatualizados")
            else:
                cel["source"] = como_linhas(novo_texto)
                mudou = True
                print(f"  guarda atualizada: {len(alvos)} hashes")

    if mudou and not apenas_checar:
        nb_path.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    return problemas


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="não escreve; sai 1 se algo divergir")
    args = ap.parse_args(argv)

    todos: list[str] = []
    for nb in sorted((RAIZ / "notebooks").glob("*.ipynb")):
        print(f"{nb.name}:")
        todos += sincronizar(nb, args.check)

    if todos:
        print("\nproblemas:")
        for p in todos:
            print("  -", p)
        return 1
    print("\ntudo em sincronia")
    return 0


if __name__ == "__main__":
    sys.exit(main())
