"""
Merge da camada MCB sobre o dataset_lpf.json.

Regras:
  * Join por `slug` binomial (gênero_epíteto), com fallback pelos sinônimos.
  * O LPF é a fonte para: taxonomia, caracteres gerais, propriedades, imagem.
  * O MCB é a fonte para: domínio fitogeográfico e os descritores anatômicos
    (vasos, parênquima, raios, tiloses) — que o LPF não publica.
  * Conflito em `aneis_crescimento` / `cor_madeira`: o MCB vence (é o
    vocabulário controlado do app) e o valor do LPF fica em `*_lpf` para
    auditoria; a divergência é registrada em `conflitos`.
  * Todo valor é validado contra data/mcb_taxonomy.json — código inválido
    aborta o merge com mensagem apontando a espécie e o campo.

Uso:
    python -m scraper.mcb_merge --stub          # gera esqueleto do overlay
    python -m scraper.mcb_merge                 # aplica o overlay
    python -m scraper.mcb_merge --strict-157    # falha se != 157 espécies MCB
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

log = logging.getLogger("xiloscan.mcb")

CAMPOS_MCB_MULTI = {
    "dominio_fitogeografico", "vasos_agrupamento", "tiloses_substancias",
    "parenquima_apotraqueal", "parenquima_paratraqueal", "raios_visibilidade",
}
CAMPOS_MCB_SINGLE = {
    "cor_madeira", "aneis_crescimento", "vasos_porosidade",
    "vasos_obstrucao", "parenquima_axial",
}
CAMPOS_MCB = CAMPOS_MCB_MULTI | CAMPOS_MCB_SINGLE

# peso de cada campo no cálculo de completeness (soma = 1.0)
PESOS = {
    "dominio_fitogeografico": 0.10, "cor_madeira": 0.10, "aneis_crescimento": 0.08,
    "vasos_porosidade": 0.13, "vasos_agrupamento": 0.13, "vasos_obstrucao": 0.08,
    "tiloses_substancias": 0.08, "parenquima_axial": 0.10,
    "parenquima_apotraqueal": 0.06, "parenquima_paratraqueal": 0.08,
    "raios_visibilidade": 0.06,
}


def load_taxonomy(path: Path) -> dict[str, set[str]]:
    tax = json.loads(path.read_text(encoding="utf-8"))
    return {
        cat["chave"]: {op["codigo"] for op in cat["opcoes"]}
        for cat in tax["categorias"]
    }


def validate(slug: str, campo: str, valor, validos: set[str]) -> list[str]:
    erros: list[str] = []
    itens = valor if isinstance(valor, list) else ([valor] if valor else [])
    for v in itens:
        if v not in validos:
            erros.append(
                f"{slug}.{campo}: código '{v}' não existe em mcb_taxonomy.json "
                f"(válidos: {sorted(validos)})"
            )
    return erros


def build_index(dataset: dict) -> dict[str, dict]:
    """slug (e sinônimos) -> entrada do dataset."""
    idx: dict[str, dict] = {}
    for esp in dataset["especies"]:
        idx.setdefault(esp["id"], esp)
        for syn in esp["taxonomia"].get("sinonimos", []):
            from .normalize import parse_scientific_name
            s = parse_scientific_name(syn).slug
            if s:
                idx.setdefault(s, esp)
    return idx


def completeness(anat: dict) -> float:
    score = 0.0
    for campo, peso in PESOS.items():
        v = anat.get(campo)
        if (isinstance(v, list) and v) or (not isinstance(v, list) and v):
            score += peso
    return round(score, 3)


def merge(dataset: dict, overlay: dict, taxonomy: dict[str, set[str]]) -> dict:
    idx = build_index(dataset)
    erros: list[str] = []
    conflitos: list[dict] = []
    aplicados = 0
    nao_encontrados: list[str] = []

    for slug, dados in overlay.get("especies", {}).items():
        alvo = idx.get(slug)
        if alvo is None:
            nao_encontrados.append(slug)
            continue

        anat = alvo["anatomia_macroscopica"]
        for campo in CAMPOS_MCB:
            if campo not in dados:
                continue
            valor = dados[campo]
            if campo == "dominio_fitogeografico":
                validos = taxonomy["dominio_fitogeografico"]
            else:
                validos = taxonomy.get(campo, set())
            erros += validate(slug, campo, valor, validos)
            if not valor:
                continue

            if campo == "dominio_fitogeografico":
                alvo["procedencia"]["dominio_fitogeografico"] = valor
                continue

            antigo = anat.get(campo)
            if antigo and antigo != valor:
                conflitos.append(
                    {"id": slug, "campo": campo, "lpf": antigo, "mcb": valor}
                )
                anat[f"{campo}_lpf"] = antigo
            anat[campo] = valor

        if dados.get("nome_cientifico_mcb"):
            alvo["taxonomia"]["nome_cientifico_mcb"] = dados["nome_cientifico_mcb"]
        if dados.get("nomes_populares_mcb"):
            alvo["taxonomia"]["nomes_populares_mcb"] = dados["nomes_populares_mcb"]

        alvo["proveniencia"]["mcb"] = True
        aplicados += 1

    if erros:
        for e in erros:
            log.error(e)
        raise SystemExit(f"merge abortado: {len(erros)} código(s) inválido(s)")

    for esp in dataset["especies"]:
        anat = dict(esp["anatomia_macroscopica"])
        anat["dominio_fitogeografico"] = esp["procedencia"]["dominio_fitogeografico"]
        esp["completeness"] = completeness(anat)
        esp["apto_treino_metric_learning"] = bool(
            esp["imagens"] and any(i.get("arquivo") for i in esp["imagens"])
        )

    dataset["meta"]["mcb"] = {
        "especies_com_overlay": aplicados,
        "slugs_nao_encontrados": nao_encontrados,
        "conflitos": conflitos,
        "completeness_media": round(
            sum(e["completeness"] for e in dataset["especies"]) / max(len(dataset["especies"]), 1), 3
        ),
    }
    log.info("overlay aplicado a %d espécies; %d sem correspondência; %d conflitos",
             aplicados, len(nao_encontrados), len(conflitos))
    if nao_encontrados:
        log.warning("sem correspondência no LPF: %s", nao_encontrados)
    return dataset


def make_stub(dataset: dict) -> dict:
    vazio = {
        "nome_cientifico_mcb": "", "nomes_populares_mcb": [],
        "dominio_fitogeografico": [], "cor_madeira": None, "aneis_crescimento": None,
        "vasos_porosidade": None, "vasos_agrupamento": [], "vasos_obstrucao": None,
        "tiloses_substancias": [], "parenquima_axial": None,
        "parenquima_apotraqueal": [], "parenquima_paratraqueal": [],
        "raios_visibilidade": [],
    }
    return {
        "meta": {
            "descricao": "Esqueleto gerado por `mcb_merge --stub`. Preencha apenas as espécies presentes no app MCB (157).",
            "versao": "0.1.0-stub",
        },
        "especies": {
            esp["id"]: {**vazio, "nome_cientifico_mcb": esp["taxonomia"]["nome_cientifico"]}
            for esp in dataset["especies"]
        },
    }


def _console_utf8() -> None:
    """Ver a nota em scraper/lpf_scraper.py: console cp1252 do Windows."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    _console_utf8()
    p = argparse.ArgumentParser(description="Merge da camada MCB sobre o dataset LPF")
    p.add_argument("--dataset", default="data/dataset_lpf.json")
    p.add_argument("--overlay", default="data/mcb_overlay.json")
    p.add_argument("--taxonomy", default="data/mcb_taxonomy.json")
    p.add_argument("--out", default="data/dataset_lpf.json")
    p.add_argument("--stub", action="store_true", help="gerar esqueleto do overlay e sair")
    p.add_argument("--strict-157", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s")

    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))

    if args.stub:
        out = Path(args.overlay).with_suffix(".stub.json")
        out.write_text(json.dumps(make_stub(dataset), ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("esqueleto escrito em %s (%d espécies)", out, len(dataset["especies"]))
        return 0

    overlay = json.loads(Path(args.overlay).read_text(encoding="utf-8"))
    taxonomy = load_taxonomy(Path(args.taxonomy))
    merged = merge(dataset, overlay, taxonomy)

    n_mcb = merged["meta"]["mcb"]["especies_com_overlay"]
    if args.strict_157 and n_mcb != 157:
        log.error("esperadas 157 espécies MCB, encontradas %d", n_mcb)
        return 2

    Path(args.out).write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("✔ %s — completeness média %.3f", args.out, merged["meta"]["mcb"]["completeness_media"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
