# Modelo, embeddings e busca

> Parte da documentação do [XiloScan](../README.md). Esta página cobre o
> treino por metric learning, o pré-processamento, o índice vetorial, o filtro
> híbrido e o contrato da API.

## Etapa 2 — Modelo, embeddings e busca

### Por que ArcFace e não softmax

Com 157 classes e poucas imagens por espécie, não queremos um classificador
fechado: queremos um **espaço métrico** onde amostras da mesma espécie fiquem
próximas e espécies novas entrem sem retreinar. ArcFace impõe margem angular
aditiva na hiperesfera — separa classes visualmente próximas (Lauraceae,
Sapotaceae) melhor que softmax, e sem a engenharia de mineração de tripletas do
Triplet Loss.

Arquitetura: `EfficientNet-B4 → GeM pooling → BNNeck → Linear(512) → L2-norm`.
GeM em vez de average pooling porque o sinal aqui é **textura**, não forma.

### Pré-processamento (o que mais move a agulha em campo)

1. EXIF-transpose, RGB
2. corte central 85% — **a guia visual do frontend mostra exatamente essa região**
3. **gray-world white balance** — luz quente joga toda espécie para o bin "amarela",
   e cor é atributo diagnóstico
4. **CLAHE no canal L do LAB** — equaliza iluminação local sem mexer na cromaticidade
5. resize Lanczos → 380 px, normalização ImageNet
6. **TTA de 8 vistas** (4 rotações × flip): o corte transversal não tem orientação
   canônica; a média L2-normalizada é o embedding final

### Índice vetorial

`IndexFlatIP` sobre vetores L2-normalizados = cosseno exato. Com ~157 espécies ×
8 vistas são poucos milhares de vetores: busca exata custa microssegundos e evita
a perda de recall do IVF/PQ (o caminho `ivf_pq` já está pronto para quando entrarem
fotos de campo dos usuários).

O score de uma espécie é o **máximo** entre seus vetores, não a média — uma amostra
que casa com uma das vistas não deve ser penalizada pelas outras.

`notebooks/02_modelo_e_api.ipynb`, com runtime **GPU (T4)** no Colab, *Executar tudo*.
Ele consome o `xiloscan_dataset.zip` do notebook 01, treina, monta o índice, sobe a API
e expõe a URL via ngrok para o frontend local. Roda localmente também — usa o
`data/` que já estiver na pasta e dispensa o zip; sem GPU funciona, só mais devagar.

Local:

```bash
pip install -r backend/requirements.txt
python -m backend.scripts.train --epochs 40 --batch-size 24   # precisa de >1 img/espécie
python -m backend.scripts.build_index --augment 8
uvicorn backend.app.main:app --reload --port 8000
```

Sem checkpoint treinado o sistema **roda** com features ImageNet e avisa no log e
em `/health` — útil para desenvolver a interface, insuficiente para produção.

### Filtro híbrido hierárquico

```
score_final = 0.70 · score_visual + 0.30 · score_atributos
```

O `score_atributos` é média ponderada por campo (pesos em `mcb_taxonomy.json`).
Duas regras que evitam os erros clássicos:

- **campo não informado é neutro**, não divergente — sai do denominador. Marcar só
  "cor = amarela" corretamente dá 1.0, não 1/11.
- **lacuna no dataset também é neutra** — se a espécie não tem raios preenchidos,
  o usuário não é punido por uma falha nossa.
- atributos **reordenam**, não eliminam: o usuário erra ao observar, e uma
  eliminação dura esconderia a espécie certa.

Quando o 1º e o 2º colocados ficam a menos de 0,05, a resposta traz
`top1_ambiguo: true` e a interface exige comparação visual antes de concluir.

### API

| Rota | O quê |
|---|---|
| `GET /health` | modelo, índice, nº de espécies e vetores, device |
| `GET /taxonomy` | vocabulário controlado — o frontend monta os filtros daqui |
| `GET /species`, `/species/{id}` | catálogo, com busca por nome |
| `POST /quality-check` | foco, brilho, saturação — avisos acionáveis, antes de gastar inferência |
| `POST /identify` | imagem + atributos → `ComparisonResult` |

---
