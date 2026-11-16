# Publicar na Vercel

O sistema roda na Vercel com um banco **Postgres no Neon** (plano gratuito). Na
nuvem nada é gravado em disco: o banco e os arquivos de resultado (JSON/TXT)
ficam no Postgres.

| O quê | Onde fica na Vercel |
|---|---|
| Banco de dados | Postgres no Neon (variável `DATABASE_URL`) |
| Arquivos JSON/TXT das auditorias | Dentro do banco (tabela `arquivos_auditoria`) |
| Chave secreta da sessão | Variável `AUDITORIA_SECRET_KEY` |

Rodando no computador, sem `DATABASE_URL`, o sistema continua usando o SQLite
local em `instance/auditoria.db`, como antes.

---

## 1. Enviar o código para o GitHub

O deploy da Vercel parte do repositório. Confirme que as alterações estão no GitHub:

```bash
git push
```

## 2. Criar o projeto na Vercel

1. Acesse <https://vercel.com/new> e importe o repositório `workerSystemAuditPython`.
2. Em **Framework Preset**, deixe **Other**. O arquivo `vercel.json` já diz à
   Vercel para rodar o `app.py` com Python.
3. **Ainda não clique em Deploy.** Antes, configure o banco, a chave e o administrador (passos 3 a 5).
   Se já tiver clicado, não tem problema: o primeiro deploy vai falhar com uma
   mensagem pedindo as variáveis, e você faz um *Redeploy* depois.

## 3. Criar o banco Postgres (Neon)

1. No projeto da Vercel, abra a aba **Storage → Create Database → Neon** (Serverless Postgres).
2. Escolha o plano **Free** e uma região próxima (ex.: `São Paulo` ou `Washington, D.C.`).
3. Conecte o banco ao projeto, marcando os ambientes **Production** e **Preview**.

A Vercel cria a variável `DATABASE_URL` sozinha. Confira em
**Settings → Environment Variables**.

## 4. Configurar a chave secreta

Gere uma chave aleatória no seu computador:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Em **Settings → Environment Variables**, adicione:

| Nome | Valor |
|---|---|
| `AUDITORIA_SECRET_KEY` | o texto gerado acima |

Guarde essa chave. Se ela mudar, todos os usuários são deslogados (os dados não se perdem).

## 5. Configurar o administrador inicial

Na mesma tela (**Settings → Environment Variables**), adicione:

| Nome | Valor |
|---|---|
| `AUDITORIA_ADMIN_USUARIO` | o login, ex.: `ana` |
| `AUDITORIA_ADMIN_SENHA` | a senha (mínimo de 8 caracteres) |
| `AUDITORIA_ADMIN_EMAIL` | opcional |
| `AUDITORIA_ADMIN_NOME` | opcional, ex.: `Ana Souza` |

Na primeira vez que o sistema iniciar, ele cria as tabelas e esse administrador
sozinho. Isso só acontece **se ainda não existir um usuário com esse login ou
e-mail**. Se já existir, nada é alterado: trocar a senha pela tela **Perfil** não é
desfeito no próximo deploy. Se quiser, apague `AUDITORIA_ADMIN_SENHA` depois do primeiro login.

O arquivo `.env.example` na raiz do projeto lista todas as variáveis.

> **Alternativa pelo terminal:** com a URL do Neon, dá para criar usuários do seu
> computador:
>
> ```bash
> export DATABASE_URL='postgresql://...cole-a-url-aqui...'
> flask --app app criar-admin
> unset DATABASE_URL   # volta a usar o banco local
> ```

## 6. Fazer o deploy

Na aba **Deployments**, clique em **Redeploy**, ou clique em **Deploy** se ainda não
tiver feito. O endereço aparece no painel (ex.: `https://seu-projeto.vercel.app`).

A partir daqui, cada `git push` na branch `main` publica uma nova versão automaticamente.

---

## Manutenção

### Criar mais usuários

Pelo seu computador, com a `DATABASE_URL` do Neon:

```bash
export DATABASE_URL='postgresql://...'
flask --app app criar-usuario
flask --app app listar-usuarios
unset DATABASE_URL
```

### Backup

No painel do Neon, o plano gratuito guarda um histórico curto (*point-in-time restore*).
Para ter uma cópia sua, instale o cliente do Postgres (`sudo apt install postgresql-client`) e rode:

```bash
pg_dump 'postgresql://...' > backup_$(date +%Y%m%d).sql
```

### Limites que vale conhecer

- **Primeiro acesso lento:** depois de um tempo sem uso, a Vercel e o Neon "dormem".
  O primeiro acesso pode levar alguns segundos. Os seguintes são rápidos.
- **Importação de arquivos:** até 4 MB por envio (limite da Vercel).
- **Plano gratuito do Neon:** 0,5 GB de armazenamento, que é muito para este sistema.

### Deu erro?

Na Vercel, abra **Deployments → (o deploy) → Logs** (ou a aba **Logs** do projeto).
Os erros mais comuns são:

- `Configure a variavel de ambiente AUDITORIA_SECRET_KEY`: falta o passo 4.
  Depois de adicionar a variável, faça *Redeploy*.
- `Ambiente serverless detectado sem banco de dados externo`: falta a `DATABASE_URL`
  (passo 3). Faça *Redeploy* depois de conectar o banco.
- O login não aceita a senha: confira `AUDITORIA_ADMIN_USUARIO` e `AUDITORIA_ADMIN_SENHA`
  e faça *Redeploy*. Se já existia um usuário com esse login ou e-mail, a senha dele
  não é alterada. Nesse caso use a senha antiga ou escolha outro login.
  Senhas com menos de 8 caracteres são recusadas e o motivo aparece nos **Logs**.
