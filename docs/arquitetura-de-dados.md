# Arquitetura de dados do XiloScan

> Parte da documentação do [XiloScan](../README.md). Esta página cobre de onde
> vêm os dados, por que eles precisam ser mesclados de duas fontes e como o
> dataset é regerado.

## Nomenclatura

**MCB** = app *Madeiras Comerciais do Brasil* v1.12.1 (LPF/SFB + UFS/LAVD), o guia de
identificação por caracteres gerais e macroscópicos com 157 espécies. É de onde vem o
vocabulário anatômico deste projeto. Não confundir com **EFV**, que é outro programa e
serviu apenas como referência de direção para o produto.

## O achado que define a arquitetura de dados

O site do LPF e o app MCB **não publicam o mesmo conjunto de campos**:

| | LPF/SFB (web, ~271 registros) | App MCB (157 espécies) |
|---|---|---|
| Nome científico, autor, família, sinônimos | ✅ | ✅ |
| Nomes populares | ✅ | ✅ |
| Local de coleta | ✅ | — |
| **Cor**, **anéis de crescimento**, grã, textura, figura, brilho, cerne/alburno | ✅ | ✅ |
| Densidades, contrações, propriedades mecânicas | ✅ | — |
| Imagem do corte transversal macroscópico | ✅ | ✅ |
| **Domínio fitogeográfico** | — | ✅ |
| **Vasos** (poros, agrupamento, obstrução) | — | ✅ |
| **Tiloses e substâncias** | — | ✅ |
| **Parênquima axial** (apotraqueal / paratraqueal) | — | ✅ |
| **Raios** (visibilidade) | — | ✅ |

Por isso o `dataset_lpf.json` é um **merge com proveniência por campo**:

```
scraper/lpf_scraper.py  ──►  dataset_lpf.json (base LPF)
                                    │
data/mcb_overlay.json   ──► scraper/mcb_merge.py ──► dataset_lpf.json (completo)
data/mcb_taxonomy.json  ──►   valida todo código
```

Cada espécie carrega `proveniencia: {lpf, mcb}` e `completeness` (0–1: fração dos
descritores anatômicos preenchidos). O filtro híbrido usa `completeness` para não
punir uma espécie por uma lacuna **nossa**.

### Estado da taxonomia

`data/mcb_taxonomy.json` tem 11 categorias e 46 opções. Os **nomes das categorias**
e a **cardinalidade** foram lidos literalmente das telas "Filtrar Espécies" do app
(`confianca: "confirmado"`). Vários **rótulos de opção** seguem a terminologia
macroscópica padrão LPF/IAWA e estão marcados `confianca: "inferido"` — confira-os
contra o Glossário do app e corrija **só esse arquivo**: backend e frontend leem
dali (o frontend marca opções inferidas com `*`).

---

---

## Etapa 1 — Dataset

### Notebooks: Colab **e** local, sem editar nada

Abra `notebooks/01_catalogo_lpf.ipynb` e mande **Executar tudo**.

A primeira célula detecta o ambiente e se ajusta:

| | Colab | Local (Windows / Linux / macOS) |
|---|---|---|
| pasta de trabalho | `/content/xiloscan` | a raiz do projeto que contém `scraper/` |
| interpretador | o do runtime | `sys.executable` — o mesmo que abriu o notebook |
| fontes | gravadas pelas células `%%writefile` | preservadas se já existirem e forem iguais |
| resultado | `xiloscan_dataset.zip` para baixar | direto em `data/`, na sua pasta |

Os notebooks são **autocontidos**: as células `%%writefile` carregam uma cópia do
código-fonte, então no Colab não é preciso subir nada para o Drive nem clonar
repositório. `notebooks/sync_notebooks.py` mantém essas cópias iguais aos arquivos
do repositório, e um teste falha se divergirem.

Rodando **localmente dentro do projeto**, uma célula de guarda compara os hashes
antes: se você editou um fonte à mão, ela **interrompe** o "Executar tudo" em vez
de sobrescrever seu trabalho em silêncio.

Nada de `!python` nem `!pip` nos notebooks — tudo passa por `sys.executable`, senão
no Windows `python` abre a Microsoft Store.

### Local

```bash
pip install -r scraper/requirements.txt

# a rede alcança o LPF? 1 segundo, e diz exatamente o que está errado se não alcançar
python -m scraper.lpf_scraper --check

# smoke test: 2 espécies, sem imagens — confirma que o parser casa com o HTML atual
python -m scraper.lpf_scraper --only-ids 2,284 --no-images --out data_smoke -v

# catálogo completo (~271 espécies + imagens), 10–25 min
python -m scraper.lpf_scraper --out data --workers 6 --delay 0.35

# aplicar a camada MCB
python -m scraper.mcb_merge

# gerar o esqueleto para preencher as 157 espécies do app
python -m scraper.mcb_merge --stub
```

O scraper tem cache em disco (`data/.cache`), retry com backoff exponencial e
jitter, rate limit de 0,35 s e detecção de dois templates de página do Joomla.
Reexecuções são quase instantâneas.

### Estrutura real da ficha do LPF

A página **não** é uma tabela "rótulo | valor". Ela tem blocos:

```html
<p><span class="font-weight-bold">Características Gerais:</span>
   Cerne/Alburno: indistintos; Cor: amarelo-amarronzado a marrom-claro;
   Anéis de crescimento: pouco distintos; Grã: cruzada ondulada; ...
</p>
```

e **dois templates convivem** no acervo:

| | Template A (ex.: *Alexa grandiflora*) | Template B (ex.: *Acioa edulis*) |
|---|---|---|
| cor | `Cor:` | `Cor do cerne:` + `Cor do alburno:` |
| anéis | `Anéis de crescimento:` | `Camadas de crescimento:` |
| figura | `Figura:` | `Figura tangencial:` + `Figura radial:` |
| densidade | linha começa vazia | linha começa pelo número |

As propriedades vêm em **tabelas-matriz** com `colspan`/`rowspan` cruzados
(`Condição` rowspan=3, `Flexão Estática (kgf/cm²)` colspan=2), que só fazem
sentido depois de expandidas numa grade. As chaves saem achatadas:
`"Flexão Estática (kgf/cm²) · Módulo de Ruptura · Seca": 1114.0`, e os números
que o backend consulta pelo nome ficam em `propriedades_chave`
(`densidade_basica`, `contracao_volumetrica`, …).

> Isto foi descoberto rodando o scraper de verdade: a primeira versão extraía
> taxonomia e imagens corretamente mas devolvia **0%** de cor, grã, textura e
> anéis nas 271 espécies, porque procurava linhas de tabela. As fixtures de
> teste hoje são páginas reais do LPF, não HTML sintético.

### Quando dá errado

O scraper **falha rápido e diz o porquê**, em vez de tentar 5 vezes por URL e gravar um
dataset vazio com cara de sucesso. Códigos de saída: `0` extraiu, `2` não extraiu nada.

| Sintoma | O que é | O que fazer |
|---|---|---|
| `Temporary failure in name resolution` / `O nome '…' não resolve` | sem DNS: ambiente sem internet, sandbox, VM isolada | rodar no Colab, ou `export HTTPS_PROXY=…` se for proxy corporativo |
| `ProxyError: 403 Forbidden` | egress bloqueado por política da rede/organização | rodar no Colab |
| `NENHUMA espécie foi extraída` com rede OK | o template do Joomla mudou | célula 3b do notebook lista os rótulos reais; ajuste `_FIELD_MAP` |
| `UnicodeEncodeError: 'charmap' codec` no cmd | console do Windows em cp1252 | já corrigido — o programa reconfigura stdout para UTF-8 ao iniciar |
| `No module named scraper` | `cd` na pasta errada | rode da raiz do projeto, com `-m` |
| campos vazios em algumas espécies | ficha incompleta no próprio LPF | normal; olhe `campos_brutos_lpf` |

### Refazer o dataset sem baixar nada

O cache (`data/.cache`) guarda o HTML das 271 páginas. Depois de corrigir o parser,
`--offline` reprocessa tudo em segundos, sem nenhuma requisição.

**Windows — o caminho mais simples:** dê dois cliques em `refazer_dataset.bat`
na raiz do projeto. Ele acha o Python, confere a pasta e o cache, instala o que
faltar, reprocessa, aplica a camada MCB e imprime o relatório de cobertura.

**Windows, no cmd, passo a passo:**

```bat
cd /d D:\Documents\CIENCIA-DA-COMPUTACAO\DIO\xiloscan
py -3 -m pip install -r scraper\requirements.txt
py -3 -m scraper.lpf_scraper --offline --out data
py -3 -m scraper.mcb_merge
py -3 -m scraper.relatorio
```

Três detalhes que fazem o comando falhar no Windows:

1. **`cd` tem de ser na RAIZ** do projeto (onde ficam `scraper\`, `backend\`, `data\`).
   `python -m scraper.lpf_scraper` de dentro de `scraper\` dá
   `No module named scraper`.
2. **Use `py -3`**, não `python`. Sem o Python instalado com "Add to PATH",
   `python` abre a Microsoft Store e não roda nada.
3. **Sem `-m` não funciona**: é `py -3 -m scraper.lpf_scraper`, não
   `py -3 scraper\lpf_scraper.py` — o segundo quebra os imports relativos do pacote.

**Linux / macOS / Colab:**

```bash
python -m scraper.lpf_scraper --offline --out data
python -m scraper.mcb_merge
python -m scraper.relatorio
```

### Conferir se deu certo

`python -m scraper.relatorio` mede **cobertura por campo** e sai com código 1 se
os caracteres gerais estiverem vazios:

```
  campo                    preenchido        %
  ---------------------------------------------
  cor (descrição)          268/271     98.9%  OK
  grã                      271/271    100.0%  OK
  anéis (código MCB)       265/271     97.8%  OK
  propriedades (>=20)      270/271     99.6%  OK

RESULTADO: OK — todos os campos críticos preenchidos.
```

Contar registros não valida nada: o scrape de 30/08 terminou anunciando
"271 registros, 0 falhas" com **0%** de cor, grã, textura e anéis.

Erro de DNS **não é repetido**: resolução de nome não é falha transitória, e insistir
só troca uma mensagem clara por um minuto de espera. Se a rede cair no meio de um crawl
longo, o que já foi baixado fica no cache (`data/.cache`) e é só rodar de novo.

**Se o LPF mudar o template**, o smoke test acusa campos vazios e diz isso na tela.
A célula 3b do notebook imprime os rótulos reais da página; ajuste `_FIELD_MAP` em
`scraper/lpf_scraper.py` e os testes continuam valendo.

### Schema de saída

```jsonc
{
  "meta": { "total_registros": 271, "mcb": { "completeness_media": 0.41, "conflitos": [] } },
  "especies": [{
    "id": "alexa_grandiflora",
    "lpf_id": 284,
    "taxonomia": { "nome_cientifico": "Alexa grandiflora", "autor": "Ducke",
                   "familia": "Fabaceae", "sinonimos": [], "nomes_populares": ["Melancieira"] },
    "procedencia": { "local_coleta": "Santarém-PA", "dominio_fitogeografico": ["AMAZONIA"] },
    "caracteres_gerais": { "cor_descricao": "amarelo-amarronzado a marrom-claro",
                           "gra": "cruzada ondulada", "textura": "média a grossa" },
    "anatomia_macroscopica": {
      "cor_madeira": "AMARELA", "aneis_crescimento": "POUCO_DISTINTOS",
      "vasos_porosidade": "DIFUSA", "vasos_agrupamento": ["SOLITARIOS"],
      "parenquima_axial": "PARATRAQUEAL", "parenquima_paratraqueal": ["ALIFORME_CONFLUENTE"],
      "raios_visibilidade": ["SOB_LENTE"]
    },
    "propriedades": { "Densidade Básica (g/cm³)": 0.60, "...": 0 },
    "imagens": [{ "url": "...", "arquivo": "images/Alexa_grandiflora/Alexa_grandiflora_01.jpg",
                  "sha256": "..." }],
    "campos_brutos_lpf": { "…todo par rótulo:valor, para não perder nada": "" },
    "proveniencia": { "lpf": true, "mcb": true },
    "completeness": 0.94
  }]
}
```

---
