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
- `MAX_UPLOAD_BYTES`: limite do arquivo enviado. Padrao: 40 MB.

## Midia

O formulario aceita:

- texto livre
- imagem: JPG, PNG, WebP, GIF
- video: MP4, WebM, MOV
- audio: MP3, M4A, WAV, WebM, OGG

Os inputs usam `capture` para abrir camera/microfone em celulares quando o
navegador permitir. O botao de gravar audio usa `MediaRecorder`; em producao,
microfone e camera normalmente exigem HTTPS.

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

## Banco

A versao atual usa SQLite sem dependencias externas, boa para um deploy simples
no Railway com volume persistente. O schema ja separa `books` e `submissions`;
se o volume de acessos crescer, a proxima troca natural e adicionar um adapter
Postgres mantendo esse mesmo modelo.
