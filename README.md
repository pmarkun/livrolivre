# Livro Livre - Rastros dos leitores

Micro pagina mobile first para leitores enviarem texto, foto, audio ou video
sobre livros distribuidos pelo Livro Livre.

O primeiro livro configurado e *Detetive Chapeuzinho e o Misterio da Sombra
Digital*.

## Rodar localmente

```bash
python3 app.py
```

Acesse:

- Publico: http://localhost:8000/detetive-chapeuzinho
- Moderacao: http://localhost:8000/admin

Senha local padrao: `chapeuzinho`

## Livros

Cada livro vive em `books/<slug>.json`, com textos, paleta, imagem de capa e
subdominios aceitos. A aplicacao resolve o livro por:

- caminho: `/detetive-chapeuzinho`
- subdominio: `detetive-chapeuzinho.livrolivre.sabichinho.com.br`

Para criar outro deploy/livro, copie `books/detetive-chapeuzinho.json`, altere
`slug`, textos, paleta e assets. As respostas ficam no mesmo banco, vinculadas
ao `book_id`.

## Variaveis de ambiente

- `PORT`: porta HTTP. O Railway define automaticamente.
- `ADMIN_PASSWORD`: senha da area de moderacao.
- `APP_SECRET`: segredo para assinar o cookie de sessao e anonimizar IPs.
- `DATA_DIR`: pasta persistente para SQLite e uploads. Padrao: `./data`.
- `DATABASE_PATH`: caminho do arquivo SQLite. Padrao: `./data/livrolivre.sqlite3`.
- `DEFAULT_BOOK_SLUG`: livro padrao quando a URL nao explicita slug.
- `MAX_UPLOAD_BYTES`: limite do arquivo enviado. Padrao: 100 MB (`104857600` bytes).
- `FORM_MIN_AGE_SECONDS`: tempo minimo antes de aceitar o envio. Padrao: 2.
- `PUBLIC_BASE_URL`: URL publica do deploy, sem barra final. Exemplo: `https://livrolivre.sabichinho.com.br`.
- `TELEGRAM_BOT_TOKEN`: token do bot criado no BotFather.
- `TELEGRAM_CHAT_ID`: chat, grupo ou canal que recebe os pedidos de moderacao.
- `TELEGRAM_WEBHOOK_SECRET`: segredo enviado pelo Telegram no webhook.
- `TELEGRAM_TIMEOUT_SECONDS`: timeout das chamadas para o Telegram. Padrao: 8.

## Midia

O formulario aceita:

- texto livre
- imagem: JPG, PNG, WebP, GIF
- video: MP4, WebM, MOV
- audio: MP3, M4A, WAV, WebM, OGG

Os inputs usam `capture` para abrir camera/microfone em celulares quando o
navegador permitir. O botao de gravar audio usa `MediaRecorder`; em producao,
microfone e camera normalmente exigem HTTPS.

Se `MAX_UPLOAD_BYTES` estiver configurado no Railway, esse valor sobrescreve o
padrao do codigo. Para 100 MB, use `104857600`.

## Railway

1. Crie o projeto no Railway apontando para este repositorio.
2. Configure `ADMIN_PASSWORD` e `APP_SECRET`.
3. Adicione um volume persistente e configure `DATA_DIR` para o caminho montado.
4. Configure `DEFAULT_BOOK_SLUG` se o deploy for dedicado a um livro especifico.
5. Use o comando de start:

```bash
python3 app.py
```

Por seguranca, rastros publicos ficam pendentes ate aprovacao. Rastros privados aparecem
somente na moderacao.

O painel `/admin` tambem tem um controle por livro para abrir ou fechar a caixa
de recados temporariamente. Quando fechada, a pagina publica continua exibindo o
mural, mas nao aceita novos envios.

## Anti-spam simples

Sem CAPTCHA por enquanto. A aplicacao usa duas barreiras leves contra bots
automaticos:

- um campo invisivel de honeypot que humanos nao preenchem
- um token assinado com tempo minimo de permanencia no formulario

Isso nao substitui rate limit de borda, mas segura parte do spam automatico sem
atrapalhar criancas e leitores reais.

## Telegram

A moderacao por Telegram roda no mesmo servico web, sem outro deploy. Quando um
recado chega, a aplicacao manda uma mensagem para `TELEGRAM_CHAT_ID` com botoes
inline:

- Aprovar
- Esconder
- Pendente
- Apagar

Para configurar:

1. Crie um bot no Telegram pelo BotFather e copie o token para `TELEGRAM_BOT_TOKEN`.
2. Envie uma mensagem para o bot, ou adicione o bot ao grupo de moderacao.
3. Descubra o `chat_id` e coloque em `TELEGRAM_CHAT_ID`.
4. Defina `PUBLIC_BASE_URL` com a URL do Railway ou do dominio final.
5. Defina um valor aleatorio para `TELEGRAM_WEBHOOK_SECRET`.
6. Registre o webhook:

```bash
curl "https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/setWebhook" \
  -d "url=$PUBLIC_BASE_URL/telegram/webhook" \
  -d "secret_token=$TELEGRAM_WEBHOOK_SECRET"
```

O endpoint `/telegram/webhook` valida `X-Telegram-Bot-Api-Secret-Token` quando
`TELEGRAM_WEBHOOK_SECRET` esta definido. As acoes do Telegram usam a mesma regra
do painel `/admin`.

## Banco

A versao atual usa SQLite sem dependencias externas, boa para um deploy simples
no Railway com volume persistente. O schema ja separa `books` e `submissions`;
se o volume de acessos crescer, a proxima troca natural e adicionar um adapter
Postgres mantendo esse mesmo modelo.
