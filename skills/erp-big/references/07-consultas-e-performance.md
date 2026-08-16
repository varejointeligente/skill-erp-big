# Consultas ao ERP — Padrões, Índices e Performance

Sumário:

- [Regras gerais de consulta](#regras-gerais-de-consulta)
- [Índices conhecidos e `FORCE INDEX`](#índices-conhecidos-e-force-index)
- [Fan-out: JOINs que multiplicam agregados](#fan-out-joins-que-multiplicam-agregados)
- [Quebrar a consulta em várias — quando e como](#quebrar-a-consulta-em-várias--quando-e-como)
- [Pool de conexões e timeout](#pool-de-conexões-e-timeout)
- [Diagnóstico de query travada](#diagnóstico-de-query-travada)
- [Consumindo o ERP via aplicação](#consumindo-o-erp-via-aplicação)
  - [Serialização de BigInt](#serialização-de-bigint)
  - [Fuso horário −03:00 nos filtros de data](#fuso-horário-0300-nos-filtros-de-data)
  - [Data montada como texto para embutir no SQL](#data-montada-como-texto-para-embutir-no-sql)
  - [Cláusulas `IN` dinâmicas](#cláusulas-in-dinâmicas)

---

## Regras gerais de consulta

- **Somente leitura.** Consultas de busca/validação diretamente no ERP são autorizadas. Qualquer
  ação que altere dados exige confirmação — e, na prática, o ERP nunca é escrito.
- **Antes de recriar regra complexa, consultar a tabela `relatorio`** (SQLs prontos do ERP), e
  substituir manualmente os placeholders (`{vl_bruto}`, `<opcao_custo>`,
  `{filtro_somente_prod}`, `{vl_custo_automatico_v2}`).
- **Nunca concatenar string do usuário no SQL** — usar parâmetros vinculados. A exceção
  controlada é a cláusula `IN` com números **já validados** (ver adiante).
- Toda query de venda leva o filtro canônico de venda válida + exclusão de `ARREDOND` + exclusão
  de `filial_id IN (1, 999)` (ver `02-vendas-movment.md`).
- **Nunca usar funções específicas de outro driver** (`TYPEOF`, `datetime()`, `strftime()` do
  SQLite) contra o ERP — o ERP é **sempre** MariaDB.

---

## Índices conhecidos e `FORCE INDEX`

| Tabela | Índices conhecidos | Observação |
| --- | --- | --- |
| `movment` | `clientes_id`, `prod_id` | Ver hints abaixo |
| `pagamentos` | `oper` (composto com `filial_id`/`datahora`/`apagado`/`troco_entrega`), `filial_id`, `datahora`, `tipospgto_id` | **Não existe índice em `numcaixa`** |

### `FORCE INDEX (clientes_id)` — obrigatório ao filtrar por cliente

```sql
FROM movment m FORCE INDEX (clientes_id)
WHERE m.clientes_id = ?
```

Sem o hint o otimizador ignora o índice e faz full scan: **42s → 60ms** com o hint.

### `FORCE INDEX (oper)` em `pagamentos`

Necessário nas consultas de caixa que filtram `filial_id` + janela de `datahora` (ver o padrão de
uma-query-por-filial abaixo).

### `FORCE INDEX (prod_id)` — cuidado: pode duplicar linhas

`FORCE INDEX (prod_id)` em `movment` combinado com um `IN()` grande de `produto_id` pode devolver
**a mesma venda mais de uma vez**, mesmo com a lista de `produto_id` 100% sem repetição.

Reproduzido isolando a variável: lista de ~40 `produto_id` garantidamente única, combinada com
`mov.data_hora BETWEEN`, `mov.oper IN (2,3)` e `mov.filial_id NOT IN (1,999)` num período de 2
meses → 7 `movment_id` duplicados (sempre exatamente 2×). É comportamento real do plano de
execução do MariaDB para esse combo (range grande no índice forçado + múltiplas outras condições
de range), não erro de escrita da query.

**Correção:** deduplicar por `movment_id` (a PK real da venda) do lado da aplicação, logo após
mapear as linhas — `movment_id` nunca repete de verdade, então deduplicar por ele nunca descarta
uma venda legítima.

**Regra:** qualquer rota que use `FORCE INDEX (prod_id)` com `IN()` de **múltiplos** `produto_id`
deve deduplicar por `movment_id` antes de retornar.

---

## Fan-out: JOINs que multiplicam agregados

| JOIN | Por que faz fan-out | Correção |
| --- | --- | --- |
| `LEFT JOIN barras b ON b.produto_id = ... AND b.apagado='N'` | Produto pode ter **várias** linhas ativas em `barras` (códigos alternativos/de caixa) | Subquery escalar `MIN(b2.barras)`; nunca joinar numa query com `SUM`/`COUNT`/`MAX` |
| `JOIN entradas e ON e.entradas_id = mov.entradas_id` | `entradas_id` é reaproveitado entre produtos/filiais diferentes | Completar com `AND e.produto_id = mov.produto_id AND e.filial_id = mov.filial_id` |
| JOIN de `caixas`/`pagamentos` só por `caixas_id` | `caixas_id` repete entre filiais | Sempre usar o par `(filial_id, caixas_id)` |

Casos reais medidos: entrada de 3 unidades exibida como 12 (produto com 4 códigos de barras);
entrada de 1 unidade exibida como 2 (`entradas_id = 133876` casando com 2 produtos); caixa da
FILIAL 2 mostrando "Sobrou R$ 32,29" quando o real era "Faltou R$ 0,22" (pagamentos de caixas de
outras 2 filiais com o mesmo `caixas_id` sendo somados junto).

---

## Quebrar a consulta em várias — quando e como

**`pagamentos` não tem índice em `numcaixa`.** Um `JOIN pagamentos p ON p.filial_id = ... AND
p.numcaixa = ... AND p.datahora BETWEEN ...` só fica rápido quando `filial_id` e o intervalo de
`datahora` chegam ao otimizador como **literais concretos de UMA linha** — isso permite
constant-propagation e o MariaDB usa `type: range` no índice `oper` (~1–2 ms).

Assim que a query envolve **múltiplos** caixas de filiais/períodos diferentes ao mesmo tempo — via
`(filial_id, caixas_id) IN (...)` (tupla) ou uma tabela derivada única cruzando tudo — o
otimizador **não consegue mais propagar as constantes**, cai para `ref` só em `filial_id`
(~478 mil linhas candidatas por filial) e a query pode travar (testado: >2 min sem terminar com
~700 caixas).

**Padrão validado:** agrupar os caixas por `filial_id` em memória e rodar **uma query por filial**
— não uma geral, não uma por caixa. Dentro de cada query:

- `p.filial_id = <literal>`
- `p.datahora BETWEEN '<min literal>' AND '<max literal>'` (intervalo cobrindo todos os caixas
  daquela filial no lote)
- `FORCE INDEX (oper)`
- junção com uma tabela derivada (`UNION ALL` de `SELECT` literais) só com os caixas daquela
  filial, para resolver `numcaixa`/janela exata por linha.

Resultados medidos: 695 caixas, 0 divergências contra a query de referência por caixa, **1,78s**;
1356 caixas (1 mês, todas as filiais), **2,5s** — contra travamento indefinido da versão anterior.

**Nunca** resolver isso com uma única query cruzando tudo (`IN` de tuplas ou tabela derivada
geral), nem concluir que "funcionou rápido para 1 caixa" significa que escala — **sempre testar
com o volume real** (semana/mês inteiro, todas as filiais) antes de dar como resolvido.

O mesmo princípio vale para lotes grandes de outra natureza: o cálculo de R.F.V. da rede inteira
processa **filial por filial, sequencialmente**, nunca uma query cruzando a rede toda.

### Quando o problema é a contenção, não a query

Um contador derivado pode ser calculado **em memória, a partir de dados já carregados**, em vez de
ganhar uma rota/query própria. Caso real: um contador de "falta real" ganhou primeiro uma rota
dedicada que rodava até 4 round-trips por filial, em todas as filiais da rede; mesmo depois de
reduzida a "só quem tem caixa no período", ela variou de **3,6s a 6,7 minutos** dependendo do que
mais estivesse rodando
(contenção do pool). A solução definitiva foi eliminar a rota e derivar o número dos dados já em
memória — zero query nova.

---

## Pool de conexões e timeout

- O acesso ao ERP costuma ter um **pool pequeno (5 conexões)**. Cada query travada prende uma
  conexão e derruba relatórios sem nenhuma relação com ela.
- **Sempre configurar timeout de query** (validado: **45s**). Sem timeout, uma consulta órfã
  segura o slot do pool para sempre.
- **Nunca rodar uma fórmula pesada sem limite de período.** Caso real: 6 queries travadas, uma há
  mais de 4h27min, processando caixas de 2010/2016/2022/2023 — sinal de que alguém rodou a fórmula
  com o histórico completo, gerando uma tabela derivada (`UNION ALL`) gigantesca.
- Considerar teto máximo de dias no período (ex.: 90–120 dias) para rotas que rodam fórmulas de
  agregação por caixa.

---

## Diagnóstico de query travada

Consultas **somente leitura** para diagnóstico:

```sql
SHOW PROCESSLIST;
SELECT * FROM information_schema.INNODB_TRX;
```

- `INNODB_TRX` traz o id da thread MySQL para eventual `KILL`, e `trx_is_read_only` confirma que a
  consulta é read-only (matar não afeta dado nenhum).
- **Nunca executar `KILL` sem confirmação humana** — é ação no banco de produção do ERP,
  compartilhado por toda a rede de lojas.
- Antes de teorizar sobre cache/reinício, olhar: (1) o que o servidor loga, (2) o **JSON cru** da
  resposta da API, (3) o resultado da mesma SQL rodada direto no banco. Esse trio elimina a grande
  maioria das hipóteses falsas em segundos.

---

## Consumindo o ERP via aplicação

### Serialização de BigInt

O driver devolve **BigInt** para `COUNT` e IDs grandes — `JSON.stringify` não serializa BigInt
nativamente. Padrão obrigatório:

```ts
JSON.parse(JSON.stringify(rows, (_, v) => (typeof v === "bigint" ? v.toString() : v)))
```

**O replacer exige DOIS parâmetros `(key, value)`, não um.** Bug real: o replacer foi escrito como
`(v) => typeof v === 'bigint' ? v.toString() : v`. Como `JSON.stringify` chama o replacer com
`(key, value)`, o `v` recebia a **chave**; na raiz a chave é `""`, o replacer devolvia `""`, e o
array inteiro virava string vazia — a API respondia `{"top20":"","empresa79":""}` em vez de
arrays. Sempre escrever:

```ts
(_: string, v: unknown) => (typeof v === "bigint" ? v.toString() : v)
```

Campos que costumam vir BigInt: contagens (`COUNT`), códigos longos (GTIN, ids externos).

### Fuso horário −03:00 nos filtros de data

O servidor de produção roda em **UTC**; o driver MySQL configurado com `timezone: '-03:00'`
converte um `Date` de JS **subtraindo 3h** antes de enviar ao banco. Sem offset explícito na
construção do `Date`, o filtro chega ao banco 3h antes do pretendido e inclui registros do dia
anterior.

**Padrão correto ao montar o intervalo:**

```ts
new Date(`${data_inicio}T${hora_inicio}-03:00`)
new Date(`${data_fim}T${hora_fim}-03:00`)

// Hora fixa cobrindo o dia inteiro:
new Date(`${data_inicio}T00:00:00-03:00`)
new Date(`${data_fim}T23:59:59-03:00`)
```

**Bug real (2026-06-26):** sangrias do dia 25/06 às 22h–23h apareciam numa busca do dia 26/06
00h–12h, porque o filtro chegava ao banco como 25/06 21:00:00.

Regras relacionadas:

- O pool do ERP deve manter `timezone: '-03:00'` — nunca remover.
- Toda formatação de data/hora no servidor deve usar
  `Intl.DateTimeFormat` com `timeZone: "America/Sao_Paulo"` — nunca sem `timeZone` (o servidor é
  UTC).
- No cliente, não reformatar com o fuso local: devolver do servidor a **string já formatada** para
  exibição + um **timestamp numérico** para ordenação.
- Ao corrigir fuso num módulo, procurar **todas** as cópias do helper de formatação (rotas
  auxiliares costumam duplicar em vez de importar) — corrigir só a rota "principal" não basta.
- **Nunca validar fuso apenas em ambiente local:** a máquina de desenvolvimento normalmente já
  está no fuso de Brasília e mascara exatamente esse tipo de bug.

### Data montada como texto para embutir no SQL

Quando o filtro de data é montado como string `'YYYY-MM-DD HH:MM:SS'` e embutido na query, uma
hora fora da faixa `00`–`23` (ex.: `'2026-07-21 24:59:19'`) faz o MariaDB **não casar nada**: sem
erro, sem log, o `BETWEEN` simplesmente devolve zero linhas.

**Bug real (2026-08-04):** a coluna "Diferença Fechamento" saía em branco em produção **só** para
os caixas que fecham entre 00:00 e 00:59 — a hora da meia-noite estava sendo formatada como `"24"`
em vez de `"00"` na hora de montar a string.

**Como evitar:** conferir a string gerada antes de culpar o dado (validar a hora em `00`–`23`), ou
passar a data como parâmetro vinculado em vez de texto. Um sintoma que atinge só uma faixa de
horário é quase sempre a string do filtro, não o registro no ERP.

### Cláusulas `IN` dinâmicas

Quando o cliente de acesso ao ERP é um wrapper sobre o driver MySQL (e não um ORM completo),
helpers de composição de SQL do ORM (`Prisma.join`, `Prisma.sql`) **falham silenciosamente**: cada
`${...}` do template vira **um único** parâmetro `?`. O array serializado chega como um parâmetro
só e, com a coerção implícita string→número do MySQL (que pega só o prefixo numérico), a query
casa **apenas com o primeiro ID da lista** — sem erro, sem log, resultado incompleto.

Bug real: busca de nomes em lote com `usuario_id IN (${Prisma.join(idsUsuarios)})` retornava **1
nome entre 7 IDs pedidos**.

**Padrão correto** para lista de IDs numéricos **já validados**:

```ts
// $queryRawUnsafe com os números embutidos no texto da query
`SELECT ... WHERE usuario_id IN (${ids.join(",")})`
`... WHERE mov.filial_id IN (${filialList.join(",")})`
```

Nunca embutir string vinda do usuário sem sanitizar. E nunca usar helpers de composição do ORM
contra o cliente do ERP.
