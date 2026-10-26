# Auditoria Automatizada de Atendimentos

Sistema web local para auditoria de qualidade de atendimentos de suporte: cadastro de
clientes, cadastro e importação de atendimentos, critérios de avaliação configuráveis
**por cliente**, execução das auditorias com pontuação percentual ponderada e
armazenamento automático dos resultados em pastas organizadas por cliente.

Aplicação funcional, com backend Flask, banco SQLite persistente, regras de negócio,
validações no servidor, autenticação e testes automatizados.

---

## 1. Tecnologias

| Camada | Tecnologia |
|---|---|
| Linguagem | Python 3.10+ |
| Framework web | Flask 3 |
| ORM | SQLAlchemy 2 + Flask-SQLAlchemy |
| Banco de dados | SQLite (arquivo `instance/auditoria.db`) |
| Templates | Jinja2 |
| Senhas / segurança | Werkzeug (hash PBKDF2) |
| Frontend | HTML5, CSS3 e JavaScript (sem dependências externas) |
| Testes | pytest |

Não há serviços pagos, APIs externas ou dependências de rede: tudo roda localmente.

---

## 2. Estrutura do projeto

```
trabalhoAna/
├── app.py                     # ponto de entrada (cria a aplicação)
├── requirements.txt
├── pytest.ini
├── README.md
├── instance/                  # banco de dados e chave secreta (gerados na 1ª execução)
│   ├── auditoria.db
│   └── secret_key
├── auditorias/                # resultados gravados, organizados por cliente
│   └── cliente_1_demo/
│       └── atendimento_1/
│           ├── resultado_auditoria.json
│           └── resultado_auditoria.txt
├── auditoria_suporte/
│   ├── __init__.py            # fábrica da aplicação, filtros, tratamento de erros
│   ├── config.py              # configuração e chave secreta local
│   ├── extensions.py          # instância do SQLAlchemy (+ PRAGMA foreign_keys)
│   ├── seguranca.py           # sessão autenticada, login_required e CSRF
│   ├── cli.py                 # comandos de terminal (criar-admin, dados-exemplo...)
│   ├── models/                # Usuario, Cliente, Atendimento, Criterio, Auditoria,
│   │                          # ResultadoCriterio, ArquivoAuditoria
│   ├── routes/                # auth, dashboard, clientes, atendimentos, criterios,
│   │                          # auditorias, resultados
│   ├── services/              # regras de negócio (separadas das telas)
│   │   ├── motor_avaliacao.py      # motor de regras da auditoria
│   │   ├── auditoria_service.py    # consolidação, pontuação e registro
│   │   ├── armazenamento_service.py# gravação dos arquivos JSON/TXT
│   │   ├── atendimento_service.py  # cadastro e importação CSV/TXT
│   │   ├── cliente_service.py
│   │   ├── criterio_service.py
│   │   ├── autenticacao_service.py
│   │   └── utilitarios.py
│   ├── templates/             # base, login, dashboard, clientes/, atendimentos/,
│   │                          # criterios/, auditorias/, resultados/
│   └── static/css/style.css, static/js/script.js
└── tests/                     # testes automatizados (pytest)
```

---

## 3. Instalação (Windows)

No **Prompt de Comando** ou **PowerShell**, dentro da pasta do projeto:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

---

## 3.1. Instalação (Ubuntu / Linux)

```bash
sudo apt install python3-venv python3-pip     # apenas na primeira vez
cd "/caminho/para/trabalhoAna"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Com o ambiente virtual ativo, os comandos passam a ser `python` e `flask`
(sem o sufixo `3`). Para sair do ambiente virtual: `deactivate`.

Atalho pronto no projeto:

```bash
chmod +x iniciar.sh     # apenas na primeira vez
./iniciar.sh
```

O script cria o `.venv` se não existir, instala as dependências, avisa caso
ainda não exista nenhum usuário e sobe o servidor.

---

## 4. Primeiro acesso: criar o administrador

O banco e as tabelas são criados automaticamente na primeira execução.
**Não existe senha fixa no código**: o primeiro usuário é criado pelo terminal.

```bat
flask --app app criar-admin
```

O comando solicita nome, login, e-mail e a senha (digitada de forma oculta, mínimo de
8 caracteres) e grava a senha com hash. Também é possível informar tudo em uma linha:

```bat
flask --app app criar-admin --nome "Ana Souza" --usuario ana --email ana@empresa.com
```

Outros comandos disponíveis:

| Comando | Função |
|---|---|
| `flask --app app criar-admin` | cria o primeiro administrador |
| `flask --app app criar-usuario` | cria usuários adicionais (`--perfil admin` ou `auditor`) |
| `flask --app app listar-usuarios` | lista os usuários cadastrados |
| `flask --app app init-db` | garante a criação do banco e das tabelas |
| `flask --app app dados-exemplo` | cria **dados de demonstração** (cliente DEMO, 5 critérios e 3 atendimentos) |

> Os dados de demonstração são opcionais, ficam identificados com o prefixo `DEMO` e
> nenhuma auditoria é executada automaticamente por eles.

---

## 5. Executar o sistema

```bat
python app.py
```

ou

```bat
flask --app app run
```

Acesse no navegador: **http://127.0.0.1:5000**

Faça login com o usuário criado no passo anterior. Não há credenciais de teste
embutidas no sistema — as únicas contas existentes são as que você criar.

Para encerrar, pressione `Ctrl + C` no terminal.

---

## 6. Fluxo de uso

1. **Clientes** → cadastre o cliente (identificador, contato, nota mínima de aprovação).
2. **Critérios** → cadastre os critérios daquele cliente (peso, obrigatoriedade e os
   termos que servem de evidência). Critérios de um cliente nunca são usados em outro.
3. **Atendimentos** → cadastre manualmente ou importe um arquivo CSV/TXT.
4. **Executar auditoria** → selecione o atendimento; o sistema identifica o cliente,
   carrega somente os critérios ativos dele, aplica as regras e apresenta a avaliação
   sugerida. Revise os status/justificativas e confirme para registrar.
5. **Resultados** → consulte, filtre, abra os detalhes e baixe os arquivos JSON/TXT.

---

## 7. Importação de atendimentos

### CSV

Primeira linha com o cabeçalho; separador `;` ou `,` (detectado automaticamente).

```
protocolo;atendente;data_atendimento;canal;conteudo
ATD-2026-001;Maria Souza;2026-10-20;telefone;"Atendente: bom dia, meu nome e Maria..."
ATD-2026-002;Joao Lima;20/10/2026;chat;"Cliente: minha fatura veio duplicada..."
```

| Coluna | Obrigatória | Observações |
|---|---|---|
| `protocolo` | não | se vazio, o sistema gera um identificador único (`ATD-<CLIENTE>-0001`) |
| `atendente` | sim | pode vir do arquivo ou do campo "atendente padrão" da tela |
| `data_atendimento` | sim | `AAAA-MM-DD` ou `DD/MM/AAAA` (também aceita o campo "data padrão") |
| `canal` | não | telefone, chat, e-mail etc. |
| `conteudo` | sim | transcrição integral, mínimo de 20 caracteres |

Nomes alternativos aceitos: `identificador`/`id`/`ticket`/`chamado` (protocolo),
`agente`/`operador`/`responsavel` (atendente), `data` (data_atendimento),
`transcricao`/`conversa`/`historico`/`texto`/`descricao` (conteúdo).

Um modelo pronto pode ser baixado na própria tela de importação.

### TXT

Vários atendimentos separados por uma linha com três ou mais hifens. Para que os
cabeçalhos sejam lidos, o bloco precisa conter a linha marcadora `conteudo:`:

```
protocolo: ATD-2026-010
atendente: Maria Souza
data: 2026-10-20
canal: telefone
conteudo:
Atendente: bom dia, meu nome e Maria...
Cliente: bom dia...
---
protocolo: ATD-2026-011
atendente: Joao Lima
data: 20/10/2026
conteudo:
Atendente: boa tarde...
```

Um arquivo TXT **sem** a linha `conteudo:` é importado como um único atendimento: todo
o texto vira o conteúdo, o atendente e a data vêm do formulário e o nome do arquivo é
usado como protocolo. (Essa regra evita confundir falas da transcrição, como
"Atendente: bom dia", com cabeçalhos.)

Registros inválidos **nunca são gravados**: a tela informa quantos foram importados e
detalha o erro de cada linha ou bloco recusado.

---

## 8. Como a auditoria é avaliada

O motor (`services/motor_avaliacao.py`) é **baseado em regras configuráveis**, sem
inteligência artificial e sem serviços externos. Para cada critério ativo do cliente:

1. Termo **proibido** encontrado → `Não atendido` (evidência registrada).
2. Critério **sem termos esperados** cadastrados → `Inconclusivo` (revisão humana).
3. Critério com **termos de contexto** cadastrados, nenhum encontrado e opção
   "pode ser não aplicável" ativa → `Não aplicável` (fora do cálculo, com justificativa).
4. Quantidade de termos esperados encontrados ≥ mínimo exigido → `Atendido` (peso integral).
5. Evidência **parcial** (abaixo do mínimo) ou conteúdo curto demais (< 120 caracteres)
   → `Inconclusivo`.
6. Nenhuma evidência em conteúdo suficiente → `Não atendido`.

### Cálculo da pontuação

```
pontuação final = (soma dos pontos obtidos / soma dos pesos aplicáveis) x 100
```

- Critérios `Não aplicável` saem do numerador **e** do denominador.
- Critérios `Inconclusivo` permanecem no denominador e **não** recebem pontos.
- Situação geral:
  - qualquer critério **obrigatório não atendido** → **Reprovado** (destaque na tela e no arquivo);
  - qualquer critério **inconclusivo** (ou nenhum peso aplicável) → **Pendente de revisão**
    (nunca aprovação automática);
  - caso contrário: **Aprovado** se a pontuação ≥ nota mínima do cliente, senão **Reprovado**.

Cada auditoria grava o resumo do cálculo, o peso, o status, a pontuação, a justificativa
e as evidências de cada critério.

**Limitação declarada:** a verificação é **lexical** (busca dos termos configurados, sem
acentos e sem diferenciar maiúsculas) e não é análise semântica. Por isso, a tela de
execução permite revisar e ajustar cada status antes de registrar, e toda avaliação sem
evidência confiável é marcada como inconclusiva.

### Histórico

- Os dados do critério (nome, descrição, peso, obrigatoriedade) são **copiados** para o
  resultado da auditoria. Alterar ou desativar um critério depois **não modifica**
  auditorias já realizadas.
- Atendimentos já auditados não podem ser editados nem excluídos.
- Reauditar é uma ação explícita e confirmada: gera uma nova versão, com arquivos
  próprios, preservando as execuções anteriores.

---

## 9. Armazenamento dos resultados

Ao concluir a auditoria, dois arquivos são gravados automaticamente:

```
auditorias/
└── cliente_<id>_<identificador>/
    └── atendimento_<id>/
        ├── resultado_auditoria.json      (1ª auditoria)
        ├── resultado_auditoria.txt
        ├── resultado_auditoria_v2.json   (reauditoria)
        └── resultado_auditoria_v2.txt
```

O JSON contém: identificador da auditoria e versão, cliente (id, código e nome),
atendimento (id, protocolo, atendente, data, canal), data/hora da auditoria, todos os
critérios utilizados com peso, status, pontuação, justificativa e evidências, soma dos
pesos e dos pontos, fórmula, pontuação final, situação geral e indicação de revisão
humana. O TXT traz as mesmas informações em formato legível.

A auditoria **só é confirmada no banco depois que os arquivos são gravados e relidos**.
Se a gravação falhar, nada é salvo e o usuário recebe a mensagem de erro. O banco
guarda o caminho, o tamanho e o hash SHA-256 de cada arquivo.

---

## 10. Segurança

- Páginas internas protegidas por sessão autenticada (`login_required`).
- Senhas armazenadas apenas como hash (Werkzeug/PBKDF2); nunca em texto puro.
- Proteção CSRF em todos os formulários que alteram dados (token por sessão).
- Validação de todas as entradas no backend, mesmo quando já validadas no navegador.
- Consultas via ORM/parametrizadas (proteção contra SQL Injection).
- Download de arquivos somente pelo caminho registrado no banco, validado contra a
  pasta do cliente da auditoria e contra travessia de diretório (`..`).
- Chave secreta gerada automaticamente em `instance/secret_key` (ou pela variável de
  ambiente `AUDITORIA_SECRET_KEY`); nenhum valor fixo no código.
- Erros tratados em páginas amigáveis, sem expor rastreamento interno.
- Chaves estrangeiras ativadas no SQLite, garantindo a integridade dos vínculos.

---

## 11. Testes

```bat
python -m pytest
```

Os testes usam banco e diretório de auditorias **temporários** — os dados reais nunca
são lidos, alterados ou apagados. Cobrem: login válido/inválido, bloqueio sem
autenticação, CSRF, cadastro e consulta de clientes, validações obrigatórias, cadastro e
importação (CSV e TXT) de atendimentos, vínculo com o cliente correto, cadastro e
isolamento dos critérios por cliente, execução da auditoria, cálculo ponderado,
critérios obrigatórios não atendidos, avaliações inconclusivas e não aplicáveis,
gravação dos arquivos, falha de armazenamento, consulta e download dos resultados,
preservação do histórico e renderização de todas as telas.

---

## 12. Limitações conhecidas

- A avaliação automática é **lexical**, não semântica (ver seção 8).
- Servidor de desenvolvimento do Flask, para uso local; para rede/produção seria
  necessário um servidor WSGI (waitress, gunicorn) e HTTPS.
- Perfis de acesso existem (`admin` e `auditor`), mas todas as telas operacionais estão
  liberadas para usuários autenticados; não há separação de permissões por cliente.
- A exclusão de um cliente com vínculos apenas o desativa (preservando o histórico).
- Não há exportação consolidada (planilha/PDF) dos resultados além dos arquivos
  JSON e TXT por auditoria.
- A importação lê arquivos de até 5 MB por envio.
