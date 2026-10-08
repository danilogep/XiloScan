"""
Relatório de cobertura do dataset — o "deu certo?" depois de rodar o scraper.

Contar registros não é validar: o scrape de 2026-08-30 terminou anunciando
"271 registros, 0 falhas" com 0% de cor, grã, textura e anéis. Este relatório
mede COBERTURA POR CAMPO e sai com código 1 se os caracteres gerais estiverem
vazios — que é o sintoma de parser quebrado.

    python -m scraper.relatorio
    python -m scraper.relatorio --dataset data/dataset_lpf.json
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

# campos que o LPF publica e que precisam estar preenchidos
ESSENCIAIS = [
    ("nome científico", lambda e: e["taxonomia"]["nome_cientifico"]),
    ("família", lambda e: e["taxonomia"]["familia"]),
    ("nomes populares", lambda e: e["taxonomia"]["nomes_populares"]),
    ("local de coleta", lambda e: e["procedencia"]["local_coleta"]),
    ("cor (descrição)", lambda e: e["caracteres_gerais"].get("cor_descricao")),
    ("grã", lambda e: e["caracteres_gerais"].get("gra")),
    ("textura", lambda e: e["caracteres_gerais"].get("textura")),
    ("cerne/alburno", lambda e: e["caracteres_gerais"].get("cerne_alburno")),
    ("anéis (texto)", lambda e: e["anatomia_macroscopica"].get("aneis_crescimento_texto")),
    ("anéis (código MCB)", lambda e: e["anatomia_macroscopica"].get("aneis_crescimento")),
    ("cor (código MCB)", lambda e: e["anatomia_macroscopica"].get("cor_madeira")),
    ("densidade básica", lambda e: (e.get("propriedades_chave") or {}).get("densidade_basica")),
    ("propriedades (≥20)", lambda e: len(e.get("propriedades") or {}) >= 20),
    ("imagem baixada", lambda e: [i for i in e["imagens"] if i.get("arquivo")]),
]

# se qualquer um destes ficar abaixo do limite, o parser está quebrado
CRITICOS = {"cor (descrição)": 0.70, "grã": 0.70, "textura": 0.70,
            "anéis (código MCB)": 0.60, "propriedades (≥20)": 0.70}


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass

    ap = argparse.ArgumentParser(description="Cobertura do dataset_lpf.json")
    ap.add_argument("--dataset", default="data/dataset_lpf.json")
    args = ap.parse_args(argv)

    caminho = Path(args.dataset)
    if not caminho.exists():
        print(f"ERRO: {caminho} não existe. Rode o scraper primeiro.")
        return 2

    d = json.loads(caminho.read_text(encoding="utf-8"))
    esp = d.get("especies") or []
    if not esp:
        print("ERRO: dataset sem espécies.")
        return 2

    meta = d.get("meta", {})
    print(f"arquivo   : {caminho}")
    print(f"gerado em : {meta.get('gerado_em', '?')}")
    print(f"espécies  : {len(esp)}   falhas: {meta.get('total_falhas', '?')}")
    print()
    print(f"  {'campo':<22} {'preenchido':>12}   {'%':>6}")
    print("  " + "-" * 45)

    problemas: list[str] = []
    for nome, f in ESSENCIAIS:
        n = sum(1 for e in esp if f(e))
        frac = n / len(esp)
        limite = CRITICOS.get(nome)
        marca = ""
        if limite is not None:
            marca = "  OK" if frac >= limite else "  <<< FALHOU"
            if frac < limite:
                problemas.append(f"{nome}: {frac:.1%} (esperado >= {limite:.0%})")
        print(f"  {nome:<22} {n:>5}/{len(esp):<6} {frac:>6.1%}{marca}")

    mcb = meta.get("mcb")
    print()
    if mcb:
        print(f"  camada MCB: {mcb['especies_com_overlay']} espécies com overlay "
              f"(meta 157) | completeness média {mcb['completeness_media']}")
    else:
        print("  camada MCB: NÃO aplicada — rode `python -m scraper.mcb_merge`")

    cores = collections.Counter(e["anatomia_macroscopica"].get("cor_madeira") for e in esp)
    print("  cor da madeira:", dict(cores))

    print()
    if problemas:
        print("RESULTADO: DATASET INCOMPLETO")
        for p in problemas:
            print("  -", p)
        print()
        print("Provável causa: o dataset foi gerado por uma versão antiga do parser,")
        print("ou o template do LPF mudou. Reprocesse a partir do cache, sem rede:")
        print("    python -m scraper.lpf_scraper --offline --out data")
        print("    python -m scraper.mcb_merge")
        return 1

    print("RESULTADO: OK — todos os campos críticos preenchidos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
