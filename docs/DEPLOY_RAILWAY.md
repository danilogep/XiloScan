# Deploy no Railway (PWA público + cadastro)

O XiloScan sobe como **um único serviço**: o `Dockerfile` builda o frontend (PWA)
e o backend serve, na mesma origem, a **API**, as **imagens** (`/static/images`) e o
**app** (SPA). Mesma origem é o que o service worker do PWA precisa para ser instalável.

## Passo a passo

1. **Crie o projeto**
   - Railway → *New Project* → *Deploy from GitHub repo* (ele detecta o `Dockerfile`),
     ou no terminal: `railway up`.

2. **Banco do cadastro** (Postgres)
   - No projeto, *New* → *Database* → **PostgreSQL**.
   - O Railway injeta `DATABASE_URL` automaticamente no serviço. O backend cria a
     tabela `usuarios` sozinho no primeiro start (não precisa migração).
   - Sem Postgres, o cadastro cai em SQLite local (`xiloscan_users.db`) — some a cada
     redeploy, então **use o Postgres em produção**.

3. **Variáveis de ambiente** (aba *Variables*)
   | Variável | Valor | Obrigatória |
   |---|---|---|
   | `XILOSCAN_AUTH_SECRET` | um segredo aleatório longo (assina os tokens) | **sim** |
   | `XILOSCAN_TOKEN_TTL` | validade do login em segundos (padrão 2592000 = 30 dias) | não |
   | `DATABASE_URL` | fornecida pelo plugin Postgres | automática |
   | `PORT` | injetada pelo Railway | automática |

4. **Artefatos do modelo** (para o `/identify` funcionar de verdade)
   - Rode o **notebook 02** no Colab (GPU) com o `xiloscan_dataset.zip`. Ele gera:
     - `backend/artifacts/arcface_b4.pt` (modelo treinado)
     - `backend/artifacts/xiloscan.faiss` (+ `.meta.json`) (índice)
   - Coloque esses arquivos em `backend/artifacts/` **antes do deploy** (commit no repo
     ou upload). O `Dockerfile` já copia `backend/` inteiro.
   - Sem eles, a API sobe em **modo degradado**: `/health` avisa, o app abre e o
     cadastro funciona, mas `/identify` responde 503 até existir um índice.

5. **Publicar**
   - *Deploy*. Ao terminar, o Railway dá uma URL pública (`https://…up.railway.app`).
   - Abra no celular → menu do navegador → **Adicionar à tela inicial** (o PWA instala
     com o ícone do XiloScan).

## O que fica exposto

| Rota | O quê |
|---|---|
| `/` | o app (PWA) |
| `/auth/register`, `/auth/login`, `/auth/me`, `/auth/instituicoes` | cadastro simples |
| `/health`, `/taxonomy`, `/species`, `/identify`, `/quality-check` | API de identificação |
| `/static/images/…` | fotos das espécies (galeria) |

## Notas

- **Inferência em CPU**: a B4 + TTA roda em segundos por foto no Railway — ok para
  poucos usuários simultâneos. Para volume, use um serviço com GPU ou reduza o TTA.
- **Segurança do cadastro**: senhas em `pbkdf2_sha256`; token de sessão assinado por
  HMAC. É um cadastro simples (self-service, sem aprovação), como pedido — não um IdP.
- **Atualizar o app**: novo deploy → o service worker troca o shell no próximo acesso.
