# Detetive Chapeuzinho - Rastros dos leitores

Micro pagina mobile first para leitores enviarem comentarios e fotos sobre o livro
*Detetive Chapeuzinho e o Misterio da Sombra Digital*.

## Rodar localmente

```bash
python3 app.py
```

Acesse:

- Publico: http://localhost:8000
- Moderacao: http://localhost:8000/admin

Senha local padrao: `chapeuzinho`

## Variaveis de ambiente

- `PORT`: porta HTTP. O Railway define automaticamente.
- `ADMIN_PASSWORD`: senha da area de moderacao.
- `APP_SECRET`: segredo para assinar o cookie de sessao e anonimizar IPs.
- `DATA_DIR`: pasta persistente para SQLite e uploads. Padrao: `./data`.
- `DATABASE_PATH`: caminho do arquivo SQLite. Padrao: `./data/detetive_chapeuzinho.sqlite3`.
- `MAX_UPLOAD_BYTES`: limite da foto. Padrao: 7 MB.

## Railway

1. Crie o projeto no Railway apontando para este repositorio.
2. Configure `ADMIN_PASSWORD` e `APP_SECRET`.
3. Adicione um volume persistente e configure `DATA_DIR` para o caminho montado.
4. Use o comando de start:

```bash
python3 app.py
```

Por seguranca, rastros publicos ficam pendentes ate aprovacao. Rastros privados aparecem
somente na moderacao.
