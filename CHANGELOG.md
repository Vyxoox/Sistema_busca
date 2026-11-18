# CHANGELOG — Patch do Sistema de Busca (2026-10-30)

Pacote com todos os arquivos alterados durante a varredura guiada (Lotes 1 a 5).
Validação: 38/38 testes + pyright 0 erros/0 avisos (mesmo motor do Pylance) +
smoke tests (IDOR, bloqueio de IP, XFF) + boot real do servidor.

---

## Lote 1 — Segurança crítica (sessão anterior)

| Arquivo | Correção |
|---|---|
| `services/alertas_seguranca.py` | Bloqueio de IP por brute-force não gravava o evento `SEC_BLOQUEIO_IP_LOGIN` (AttributeError engolido). Corrigido; desbloqueio manual funcional. |
| `routes/verfunc.py` | IDOR em `/funcionario/<id>`: usuário fora da coordenadoria agora recebe 404. |
| `app.py` | `load_user` com cookie de sessão corrompido retornava 500; agora trata `TypeError`/`ValueError`. |
| `tests/test_criacao_rotas_allowlist.py` | Mock de `salvar_foto` ajustado (`return_value=None`). |

## Lote 2 — Higiene, LGPD e portabilidade

| Arquivo | Correção |
|---|---|
| `.gitignore` | Adicionados: `*.db` na raiz, `dados/`, `documentos/`, `static/fotos_funcionarios/` (dados pessoais fora do versionamento). |
| `requirements.txt` | `python-magic-bin` agora só instala no Windows (`sys_platform == "win32"`); `python-magic` para Linux/macOS. Instalação não quebra mais em Linux. |
| `services/funcionario_service.py` | **REMOVIDO** — arquivo vazio, sem referências. |
| `teste lotação.py` | **MOVIDO** para `scripts/teste_lotacao.py` (rascunho de modelo `Lotacao` sem uso). |
| `routes/ouvidoria.py` | CSV de exportação sanitizado contra **formula injection** (células iniciando com `= + - @ TAB CR` recebem prefixo `'`); varredura duplicada de IPs bloqueados eliminada. |
| `routes/auth.py` | f-string sem placeholder removida (cosmético). |

## Lote 3 — IP de origem (X-Forwarded-For) + startup

Contexto: waitress exposto diretamente. O waitress 2+ já descarta XFF do cliente
por padrão, mas o app honraria XFF se esse default mudasse — e a lógica de IP
estava duplicada em 4 lugares (limiter, bloqueio, auditoria, healthz podiam
discordar sobre quem era o cliente).

| Arquivo | Correção |
|---|---|
| `core/extensions.py` | `ip_origem_requisicao()` agora é a **fonte única** (limiter + bloqueio + auditoria + healthz). `TRUST_XFF=false`: usa `remote_addr` e ignora XFF. `TRUST_XFF=true`: usa o **último** hop do XFF (adicionado pelo proxy da própria infra). |
| `core/config.py` | Novo `TRUST_XFF` (default `false` — cenário atual). |
| `services/alertas_seguranca.py` | Cópia local da função removida; re-exporta a canônica. |
| `services/auditoria_services.py` | `_ip_origem()` delega para a fonte única. |
| `app.py` | `healthz` usa a fonte única; bloco `__main__` com waitress configurável por env (`HOST`, `WAITRESS_THREADS`, `WAITRESS_CONNECTION_LIMIT`, `WAITRESS_CHANNEL_TIMEOUT`), `clear_untrusted_proxy_headers=True` explícito e hooks comentados para proxy reverso futuro (`trusted_proxy`, `url_scheme`). |
| `.env.example` | `TRUST_XFF` e variáveis do waitress documentadas. |

## Lote 4 — Modernização e revisões dos blueprints

| Arquivo | Correção |
|---|---|
| `routes/verfunc.py`, `routes/ouvidoria.py`, `routes/funcionarios.py`, `routes/editfunc.py` | `Model.query.get_or_404(id)` (API legada do SQLAlchemy 2.0, sairá em 2.1) → `db.get_or_404(Model, id)`. |
| `routes/usuarios.py` | 1) Corrida na criação de admin: `IntegrityError` agora tratado no `salvar()` (antes virava 500); 2) parsing duplicado de form removido; 3) evento `USUARIO_CRIAR_ADMIN_SUCESSO` agora é gravado (a ouvidoria e os alertas já esperavam esse evento); 4) f-string sem placeholder. |
| `routes/editfunc.py` | Debug removido (`logger.warning("INICIO POST")`, `CONTENT_LENGTH`, `print(repr(...))`); erro bruto do banco não é mais exibido ao usuário (flash genérico + log completo do servidor). |
| `routes/criacao.py` | Revisado — sem alterações (allowlist, auditoria e tratamento de duplicados corretos). Sugestões futuras: extrair helper comum dos 2 fluxos; restringir `/preview/form-errors` a admins. |

---

## Lote 5 — Tipagem estática (Pylance/mypy) — 2026-10-30

Motivação: o Pylance (VS Code) acusava 37 erros no projeto. Nenhum era bug de
runtime — os 38 testes já passavam — mas todos foram eliminados com mudanças
mínimas. Validado com pyright 1.1.414 (mesmo motor do Pylance): 0 erros/0 avisos.

| Arquivo | Correção |
|---|---|
| `models.py` | Mixin `_ConstrutorDeclarativo` (declarado só em `TYPE_CHECKING`): o SQLAlchemy injeta o construtor `__init__(**kw)` nos models apenas em runtime e o verificador estático não o enxergava — essa era a causa raiz dos "No parameter named ..." em toda instanciação de model (`app.py:863`, `routes/usuarios.py`, `routes/criacao.py`, `services/auditoria_services.py`). Runtime inalterado (classe vazia). |
| `app.py` | 1) `login_manager.login_view = 'auth.login'` com supressão pontual (stub do Flask-Login tipa o atributo como `None`); 2) métricas: `_METRICAS: dict[str, float]` + supressão na atribuição (o typeshed tipa `Counter` com valores `int`, mas a latência acumulada é `float`) e `_LATENCIA_HIST` volta ao original; 3) `_normalizar_json_auditoria`: a variável `saida` era reusada como dict num ramo e como lista nos ramos seguintes — os ramos de list/tuple agora usam `lista_saida: list[Any]`. |
| `core/audit_policy.py` | `wrapper.__audit_required__` / `__audit_meta__` → `setattr(wrapper, ...)` (o functools tipa o wrapper como `_Wrapped`, que não declara atributos dinâmicos). Mesmo comportamento em runtime. |
| `routes/criacao.py` | 1) `request.form.get(campo_invalido or '')` nos 2 fluxos (o verificador tipa `campo_invalido` como `str | None`); 2) acesso a `e.orig` em `IntegrityError` → `orig = getattr(e, 'orig', None)` — mesma semântica, sem atributo dinâmico fora do tipo. |
| `routes/planilha.py` | `val.strftime(...)` → `cast(Any, val).strftime(...)` (o guard `hasattr` já protegia em runtime; o verificador tipava `val` como `str`). |

---

## Lote 6 — Resiliência a indisponibilidade do banco — 2026-10-30

Cenário real observado: SQL Server inacessível fazia o serviço subir "meio
vivo" — waitress no ar, mas erro criptico em toda tela que usa o banco, com
12s+ por requisição (cada tentativa de auditoria pagava o timeout de conexão).

| Arquivo | Correção |
|---|---|
| `app.py` | 1) **Gate de boot** `_verificar_conexao_banco()`: testa `SELECT 1` (3 tentativas, 2s de intervalo) antes do bootstrap. Em produção, banco inacessível **aborta o start** com mensagem clara no console e no log (`DB_BOOT_CHECK=true` é o padrão; `false` desativa). Em desenvolvimento, alerta e segue em modo degradado. 2) **Handler `OperationalError`**: página 503 amigável no lugar do 500 do waitress, com header `Retry-After`; `/healthz`, `/readyz` e `/metrics` respondem JSON. |
| `services/auditoria_services.py` | **Disjuntor** no `registrar_evento_seguro`: após uma falha de gravação, as gravações são puladas por 30s (sem pagar timeout de conexão a cada requisição). Assim que o banco volta, a auditoria retoma automaticamente. |
| `templates/indisponivel.html` | Novo — página "Sistema temporariamente indisponível" (autocontida, sem assets externos). |
| `.env.example` | `DB_BOOT_CHECK` documentado. |

Validação: 38/38 testes + gate validado em produção (aborta, exit 1) e em
desenvolvimento (degrada e continua) + 503 amigável + disjuntor (2ª chamada
pulada) + pyright 0 erros.

---

## Lote 7 — Operação: timeout de query, watchdog e higiene — 2026-11-03

Foco em operação contínua. O código já estava maduro após os Lotes 1–6; este
lote cobre os cantos que só aparecem com o sistema rodando todos os dias.

| Arquivo | Correção |
|---|---|
| `core/config.py` + `app.py` | **Timeout de execução de query** (`DB_STATEMENT_TIMEOUT`, padrão 300s, 0 desativa): em `app.py`, no evento `connect` do engine, via `cnxn.timeout` do pyodbc — mecanismo em que o **próprio pyodbc** aplica `SQL_ATTR_QUERY_TIMEOUT` a cada statement (`SQLSetStmtAttr`, verificado no fonte do pyodbc 5.3.0). Sem isso, uma query presa segurava uma thread do waitress indefinidamente. **Não** vai em `connect_args`/`attrs_before` (ver correção urgente abaixo). |
| `scripts/watchdog_health.py` | **Novo** — watchdog standalone (só stdlib) que verifica `/healthz` e envia e-mail de alerta pelo SMTP do `.env`. Alarme só após 2 falhas consecutivas (`WATCHDOG_FALHAS_CONSECUTIVAS`), reaviso a cada 30 min (`WATCHDOG_COOLDOWN_MIN`), e-mail de recuperação quando volta ao ar, estado em `logs/watchdog_estado.json`. Agendar no Task Scheduler a cada 5 min. |
| `app.py` | 1) Rota stub `/migrar` removida (flashava aviso e redirecionava; nenhum template apontava para ela — a importação em massa real fica nas rotas de planilha e nos scripts CLI). 2) Handler de erro de banco estendido de `OperationalError` para **`DBAPIError`** (classe base): erros de driver/config (ex.: HY092) que antes escapavam para o 500 do waitress agora viram a página amigável 503. |
| `tests/test_resiliencia_banco.py` | **Novo** — 9 testes: gate de boot (sucesso, falha, `DB_BOOT_CHECK=false`), handler 503 (OperationalError e DBAPIError genérico via `POST /login` real) e regressões do timeout de query. |
| `tests/test_*.py` (6 arquivos) | Estreitamento de `Optional` para o verificador estático (`assert x is not None`), mesma semântica — pyright agora cobre também a suíte de testes. |
| `.env.example` | `DB_STATEMENT_TIMEOUT` e `WATCHDOG_*` documentados. |

### Correção urgente do próprio Lote 7 (mesmo dia)

A primeira implementação do timeout de query usava `attrs_before` com o
atributo ODBC `13` em `connect_args`. Em campo isso **derrubava TODAS as
conexões pyodbc** com `HY092 — Identificador de atributo/opção inválido
(SQLSetConnectAttr)`, **mesmo com o banco perfeitamente saudável**:
`SQL_ATTR_QUERY_TIMEOUT` é atributo de **statement**, não de conexão, e
portanto é recusado pelo Driver Manager quando passado a `SQLSetConnectAttr`
(que é o que `attrs_before` faz, antes de conectar). Sintoma observado:
"BANCO INACESSIVEL apos 3 tentativa(s)" + 500 em toda tela — o gate de boot
apontou o erro com precisão, mas a causa era o próprio patch. Correção:
remoção completa do `attrs_before`; timeout aplicado pelo evento `connect`
via `cnxn.timeout` (pyodbc aplica por statement), + teste de regressão
impendo que `attrs_before` nunca volte a `_engine_options`. Bônus da
incidência: o handler 503 foi estendido a `DBAPIError`, então hoje até um
erro de configuração de driver mostra a página amigável em vez de 500.

Validação: 47/47 testes + pyright 0 erros (projeto inteiro, testes
incluídos) + E2E cold-start sem 500 + watchdog testado com app de pé
(exit 0), app caído (alarme após 2 falhas, cooldown) e recuperação.

---

## Lote 8 — Estética do relatório XLSX (`/export/xlsx`) — 2026-11-03

Escopo decidido com o usuário: apenas o relatório de funcionários (o CSV de
logs da ouvidoria permanece como está). Requisitos atendidos: título com
metadados visível na tela, datas como célula de data real, "Não se aplica"
discreto, paleta azul mantida (#2F5597) e coluna SITUAÇÃO colorida.

| Item | Mudança |
|---|---|
| Título na tela | Linha 1 mesclada com "RELATÓRIO DE FUNCIONÁRIOS" + linha 2 com "Emitido em … por … · Vínculo … · Busca … · Total: N registros", fechada por uma régua azul. Antes o arquivo abria direto numa parede de 36 cabeçalhos. |
| Datas reais | `DATA DE NASCIMENTO`, `INGRESSO NO DER`, `DATA INÍCIO`, `DATA ADMISSÃO` e `DATA DESLIGAMENTO` agora são células de data (dd/mm/aaaa) — ordenam e filtram por período no Excel. Valores não-data (ex.: `*`) seguem como texto. |
| "Não se aplica" | Itálico cinza-claro (#808080) — as dezenas de células de contrato/carreira vazias deixam de competir com os dados preenchidos. |
| SITUAÇÃO colorida | "Ativo" em verde-escuro (#006100) negrito; demais valores ("Inativo - …") em vermelho-escuro (#9C0006). |
| Larguras | Auto-ajustadas pelo conteúdo (mín. 11, máx. 42; nome ≥ 30) e limitadas pela maior palavra do cabeçalho — nada de quebrar "DESLIGAMENTO" no meio. |
| Linhas de grade | Ocultas — fora da tabela o fundo fica limpo; a tabela é delimitada pelas próprias bordas das células. |
| Triângulos verdes | Aviso "número armazenado como texto" suprimido via `ignore_errors` — matrícula/ramal/telefone continuam texto de propósito (zeros à esquerda, pontuação). |
| **Correção de impressão** | `repeat_rows` repetia a **1ª linha de dados** no topo de cada página impressa; agora repete o **cabeçalho** da tabela (linha 4). |
| Congelamento | Painel congelado abaixo do cabeçalho (título + metadados + cabeçalho ficam fixos ao rolar); autofiltro sobre a linha do cabeçalho. |
| Limpezas | Rótulo "LOTAÇÃO " tinha espaço final; alturas de linha mortas removidas; a rota deixou de usar pandas (gravação direta com XlsxWriter); `DATA DE NASCIMENTO` e `SITUAÇÃO` passaram a ser centralizadas. |
| Cabeçalho de impressão | Papel mantém logos + "CGR.9"; a linha "RELATÓRIO DE FUNCIONÁRIOS" saiu do papel (agora é título da própria planilha). |
| Estrutura interna | Formatação extraída para `_escrever_relatorio_xlsx()` (função pura, testável) e `ORDEM_EXPORTACAO` promovida a constante de módulo. |

**Como aplicar:** extraia `patch_formato_relatorio_2026-11-03.zip` por cima da
raiz do projeto (2 arquivos) e reinicie o serviço. Nenhuma variável nova,
nenhuma migração, nenhum requisito novo.

Validação: 59/59 testes (17 novos em `tests/test_export_xlsx_formatacao.py`:
título, metadados, datas reais, "Não se aplica" discreto, cores de SITUAÇÃO,
zebra, freeze/autofilter/repeat_rows, relatório vazio e a rota `/export/xlsx`
de ponta a ponta) + pyright 0 erros (projeto inteiro) + amostra renderizada
em PDF com os dados reais do usuário (`amostra_relatorio_novo_formato.xlsx`).

---

## Lote 8b — Logs da ouvidoria em XLSX + ajuste do Lote 8 — 2026-11-03

A pedido do usuário: a mesma identidade visual do relatório de funcionários
aplicada aos logs de auditoria. Como CSV é texto puro (sem cores, células de
data ou larguras de coluna), o caminho foi um NOVO botão "Exportar Excel" na
ouvidoria — o CSV permanece intacto para uso automatizado.

| Item | Mudança |
|---|---|
| Nova rota | `/ouvidoria/logs/exportar.xlsx` (superadmin): mesmos filtros da tela, mesmo teto de 5.000 registros do CSV, gera XLSX com o visual do relatório de funcionários. |
| Botão | "Exportar Excel" (primário) ao lado de "Exportar CSV" (secundário) na página de logs; ambos carregam os filtros ativos da tela. |
| Visual | Título "LOGS DE OUVIDORIA E SEGURANÇA" + linha "Emitido em … por … · Filtros: … · Total: N registros". Quando o filtro tem mais registros que o limite, o metadado avisa ("Total no filtro: N · Exportando os 5.000 mais recentes"). |
| Colunas | ID, DATA/HORA, USUÁRIO, AÇÃO, CATEGORIA, STATUS, RECURSO, ID DO RECURSO, IP DE ORIGEM, ROTA, DETALHES. DATA/HORA é célula de data/hora real (dd/mm/aaaa hh:mm) já convertida para o fuso local — igual ao CSV, mas ordenável. |
| STATUS colorido | "sucesso" em verde-escuro negrito; "falha" em vermelho-escuro negrito. |
| DETALHES | JSON reformatado com indentação (legível); texto que não é JSON permanece como veio. Altura de linha automática — a linha expande até o conteúdo ficar inteiro visível. |
| **Segurança** | O alerta `SEC_ALERTA_EXPORTACAO_MASSIVA` agora conta CSV **e** XLSX no mesmo limite por usuário — antes só o CSV contava e o Excel carregaria os mesmos dados fora do radar. O export do relatório de funcionários segue fora dessa regra, como antes. |
| Auditoria | Evento novo `OUVIDORIA_EXPORTAR_XLSX` (com descrição amigável na ouvidoria); CSV e XLSX compartilham a constante `LIMITE_EXPORTACAO_LOGS` (5.000). |
| Ajuste do Lote 8 | Relatório de funcionários: altura das linhas agora é automática (antes fixa em 22 — endereços e lotações longos tinham a 2ª linha cortada na exibição). |

**Como aplicar:** extraia `patch_relatorios_2026-11-03.zip` por cima da raiz
do projeto (6 arquivos: `routes/planilha.py`, `routes/ouvidoria.py`,
`services/alertas_seguranca.py`, `templates/ouvidoria_logs.html` e os 2
arquivos de teste) e reinicie o serviço. Nenhuma variável nova, migração ou
requisito. Se o Lote 8 já foi aplicado, os arquivos repetidos são
simplesmente sobrescritos com a versão mais nova.

Validação: 74/74 testes (15 novos em `tests/test_export_logs_xlsx.py`:
formatação, data/hora real com conversão de fuso, status colorido, JSON
legível, truncamento no limite, rota com filtros, bloqueio de não superadmin
e o alerta de exportação massiva contando ambos os formatos) + pyright 0
erros (projeto inteiro) + amostras renderizadas em PDF com os dados reais de
produção (`amostra_logs_ouvidoria_novo_formato.xlsx`, 382 registros).

---

## Como aplicar o patch

1. **Backup** do projeto atual (ou confie no git — veja item 4).
2. Extraia o zip de patch **mais recente** por cima da raiz do projeto
   (`Sistema de busca - Copia - Copia`), substituindo os arquivos existentes:
   - `patch_relatorios_2026-11-03.zip` — Lotes 8 e 8b (relatórios/exports)
   - (histórico) `patch_sistema_busca_2026-10-30.zip` — Lotes 1 a 7, se ainda
     não aplicados; a partir do Lote 8 ele foi incorporado ao pacote completo.
3. Exclua manualmente os 2 arquivos removidos:
   - `services/funcionario_service.py`
   - `teste lotação.py`
4. **Revisão dos lotes com git** (o projeto tem repositório): após aplicar, rode
   `git status` e `git diff` para conferir cada mudança, e commit:
   `git add -A && git commit -m "Lotes 1-7: correções, resiliência e operação"`
5. Instale dependências apenas se for ambiente novo (Linux: `pip install -r requirements.txt`
   + `apt install libmagic1`; Windows: nada muda).
6. Rode a suíte: `python -m pytest tests/ -q` (esperado: 74 passed).
7. Reinicie o serviço (`scripts/start_production.ps1`).
8. **(Recomendado)** Agende o watchdog no Task Scheduler — PowerShell como admin:

```powershell
$acao  = New-ScheduledTaskAction -Execute "python.exe" `
           -Argument "scripts\watchdog_health.py" `
           -WorkingDirectory "<raiz do projeto>"
$gatilho = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)
Register-ScheduledTask -TaskName "Watchdog SistemaBusca" -Action $acao -Trigger $gatilho -RunLevel Limited
```

## Variáveis novas (opcionais) no `.env`

```
TRUST_XFF=false              # false = waitress direto (atual); true = atrás de proxy confiável
DB_STATEMENT_TIMEOUT=300     # timeout de execução de query (s); 0 desativa
WATCHDOG_EMAIL_DESTINO=      # destino dos alertas do watchdog; vazio = SMTP_USER
WATCHDOG_COOLDOWN_MIN=30     # reaviso mínimo enquanto fora do ar
WATCHDOG_FALHAS_CONSECUTIVAS=2  # alarme só após N falhas seguidas
# HOST=0.0.0.0
# WAITRESS_THREADS=8
# WAITRESS_CONNECTION_LIMIT=100
# WAITRESS_CHANNEL_TIMEOUT=120
```
