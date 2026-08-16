# Vendas — `movment` e derivados

Sumário:

- [Tabela `movment`](#tabela-movment)
- [`oper` — códigos de operação](#oper--códigos-de-operação)
- [Filtro canônico de venda válida](#filtro-canônico-de-venda-válida)
- [Fórmulas canônicas](#fórmulas-canônicas)
- [Cupons e ticket médio](#cupons-e-ticket-médio)
- [Custo: cascata de fallback e CMV](#custo-cascata-de-fallback-e-cmv)
- [Devoluções e cancelamentos](#devoluções-e-cancelamentos)
- [Transferência x Remanejo (`oper = 10`)](#transferência-x-remanejo-oper--10)
- [Entradas (`E_S = 'E'`)](#entradas-e_s--e)
- [Entrega e tele-entrega](#entrega-e-tele-entrega)
- [Descontos: manual x automático](#descontos-manual-x-automático)
- [Agrupamentos de produto usados em vendas](#agrupamentos-de-produto-usados-em-vendas)
- [Relacionamentos frequentes](#relacionamentos-frequentes)
- [Acompanhamento do Produto (linha do tempo de `movment`)](#acompanhamento-do-produto-linha-do-tempo-de-movment)

---

## Tabela `movment`

Principal tabela de movimentação — **uma linha por item de venda/movimento**, não por cupom.

| Coluna | Descrição |
| --- | --- |
| `filial_id` | Filial (parte da chave lógica do cupom) |
| `movment_id` | Identificador da linha de movimento (PK real da venda-item) |
| `data_hora` | Data/hora do movimento |
| `produto_id` | FK para `produto.Produto_id` |
| `quanti_uni` | Quantidade |
| `preco_cad` | Preço de cadastro/tabela usado na linha (base do valor bruto) |
| `valor_tot` | Valor total **líquido** da linha (já com desconto) |
| `precoee` | Preço de entrada (custo) usado na venda |
| `pmc` | Preço médio de custo gravado na linha |
| `numlanc` | Número do lançamento (cupom) — único **por filial**, não global |
| `oper` | Código de operação (ver abaixo) |
| `cancelado` | `'S'`/`'N'` |
| `apagado` | `'S'`/`'N'` |
| `E_S` | `'E'` = entrada, `'S'` = saída (para vendas, `E_S = 'S'`) |
| `estoque` | Saldo de estoque — **depois** da operação em saídas, **antes** em entradas (ver adiante) |
| `clientes_id` | Cliente da venda (`0` = não identificado) |
| `entradas_id` | Preenchido em registros de entrada |
| `usuario_id` | Operador/vendedor |
| `numnota` | Número da nota |
| `entrega` | `'S'`/`'N'` — venda é tele-entrega |
| `dtsaida_entrega` | Despacho da entrega |
| `dtchegada_entrega` | Confirmação de chegada da entrega |
| `obs` | Observação |
| `tipo_desc` | Tipo de desconto (`'M'` = manual) |

`movment_id` **nunca repete de verdade** — é a chave segura para deduplicar linhas quando o
otimizador do MariaDB devolve duplicatas (ver `07-consultas-e-performance.md`).

---

## `oper` — códigos de operação

`movment.oper` **não filtra apenas vendas** — existem outros valores (devoluções, ajustes,
transferências, fiado). Valores conhecidos:

| `oper` | Significado |
| --- | --- |
| `2` | Venda normal |
| `3` | Venda com receita |
| `8` | Sangria / Suprimento (em `pagamentos`, discriminado por `supsang`) |
| `9` | Venda fiado / CREDIARIO |
| `10` | Transferência **ou** remanejo (distinção fica em `transferencia`) |

> Outros valores existem e não estão catalogados na fonte — **incerto**. Nunca assumir que
> `oper NOT IN (2,3)` significa devolução.

---

## Filtro canônico de venda válida

```sql
mov.apagado = 'N'
AND mov.cancelado = 'N'
AND mov.oper IN (2, 3)
AND mov.filial_id NOT IN (1, 999)
AND mov.produto_id NOT IN (
      SELECT Produto_id FROM produto WHERE descricao LIKE '%ARREDOND%'
    )
```

- `oper IN (2, 3)` — venda normal + venda com receita.
- Exclusão de filial `1` (costuma ser o escritório) e `999` (registro técnico).
- **Exclusão do produto de arredondamento é obrigatória** em qualquer query de vendas: produtos
  `ARREDOND` existem só para ajustar o troco e não devem entrar em faturamento, contagem de
  clientes, IPC nem em nenhum outro KPI.
- Para vendas, quando a query puder pegar entradas, acrescentar `mov.E_S = 'S'`.

---

## Fórmulas canônicas

| Métrica | Fórmula |
| --- | --- |
| **Valor bruto** | `mov.preco_cad * mov.quanti_uni` |
| **Valor líquido (com desconto)** | `mov.valor_tot` |
| **Desconto** | `(mov.preco_cad * mov.quanti_uni) - mov.valor_tot` |
| **Custo (preço de entrada na venda)** | `mov.precoee * mov.quanti_uni` |
| **Lucro bruto** | `mov.valor_tot - (mov.precoee * mov.quanti_uni)` |
| **Margem %** | `((mov.valor_tot - mov.precoee * mov.quanti_uni) / mov.valor_tot) * 100` |
| **Cupons** | `COUNT(DISTINCT mov.filial_id, mov.numlanc)` |
| **Ticket médio** | venda líquida ÷ cupons |
| **Unidades por cupom** | itens vendidos ÷ cupons |

Regra de cálculo de percentuais agregados: calcular o **percentual da soma**, nunca a média de
percentuais — derivar os `%` depois da agregação (em SQL sobre os totais ou no código após o
`SUM`), nunca dentro do próprio `SUM`.

---

## Cupons e ticket médio

- Um cupom é `(filial_id, numlanc)`. Contar `numlanc` sozinho mistura filiais.
- **Um mesmo cupom pode ter itens lançados por vendedores diferentes.** Numa visão por vendedor,
  esse cupom conta uma vez para cada vendedor; no total geral ele precisa contar uma vez só.
  Consequência prática: **nunca obter o total somando a tabela por vendedor** — rodar uma segunda
  consulta agregada. Medição real (01–06/08/2026, Loja WhatsApp): soma dos vendedores = **147
  cupons**, total real = **145 cupons**; o valor em R$ bate nos dois, só a contagem de cupons
  (e, por consequência, Ticket e Unidades) diverge.

---

## Custo: cascata de fallback e CMV

`movment.precoee` **pode ser zero** em alguns lançamentos; nesses casos o custo fica subestimado.
O próprio ERP tem uma lógica de fallback (placeholder `{vl_custo_automatico_v2}` nos SQLs da
tabela `relatorio`) que testa múltiplas colunas em ordem.

Cascata de custo usada e validada em relatório de CMV:

```
mov.pmc
  → mov.precoee
    → preco_medio_custo.pmc_atual
      → estoque_minimo.precoee
        → precosfilial.preco_custo
          → produto.preco_cmp_un
```

**CMV** = custo ÷ venda líquida (com o custo obtido pela cascata acima).

---

## Devoluções e cancelamentos

- `movment.cancelado = 'S'` marca o lançamento cancelado — filtrar fora das vendas.
- **`cancelamento_movment`** é a tabela usada para tratar devoluções que ocorrem em período
  diferente da venda original. Relacionamento: `movment` → `cancelamento_movment`.
- O **relatório ERP `relatorio_id = 1216`** ("Lucratividade por Filial - PlugPharma BI") é a
  referência quando as devoluções precisam ser contabilizadas **no período em que ocorreram**, e
  não no período da venda original.
- Se um indicador deve ou não incluir devoluções é decisão de negócio — perguntar, não assumir.

---

## Transferência x Remanejo (`oper = 10`)

No ERP, `movment.oper = 10` cobre **tanto transferências normais quanto remanejos** (solicitações
feitas pela tela de compras). A distinção está na tabela **`transferencia`**:

```sql
LEFT JOIN transferencia t
       ON t.movment_id = m.movment_id
      AND t.apagado = 'N'
```

| Condição | Tipo |
| --- | --- |
| `t.remanejamento_id IS NULL OR t.remanejamento_id = 0` | Transferência normal |
| `t.remanejamento_id > 0` | Remanejo |

CASE padrão:

```sql
CASE
  WHEN m.oper = 10 AND (t.remanejamento_id IS NULL OR t.remanejamento_id = 0) THEN 'Transf.'
  WHEN m.oper = 10 AND t.remanejamento_id > 0 THEN 'Remanejo'
END
```

Colunas úteis de `transferencia`: **`defilial_id`** (origem), **`parafilial_id`** (destino),
`remanejamento_id`, `movment_id`.

---

## Entradas (`E_S = 'E'`)

- **`movment.estoque` em registros de ENTRADA** (`E_S = 'E'`, com `entradas_id` preenchido) é o
  saldo **ANTES** de aplicar a entrada — ao contrário de vendas/saídas, onde `estoque` já é o
  saldo **DEPOIS** da operação.
  - Nunca calcular "estoque antes de uma entrada" como `mov.estoque - mov.quanti_uni`: o valor da
    coluna **já é a resposta direta**.
  - Caso real confirmado: produto 106447 (CO SEDA LISO PERFEITO), `movment_id` 13323679, entrada
    de 16 un. em 16/06 às 13:13 com `estoque = 5` gravado (saldo antes), virando 21 depois.
- **`entradas.entradas_id` não é único por produto/filial** — é reaproveitado entre itens de lotes
  de importação distintos (visto na prática: `entradas_id = 133876` apontando para o produto
  828555 na filial 6 **e** para o produto 812408 na filial 11). O JOIN sempre precisa da chave
  completa:

```sql
JOIN entradas e
  ON e.entradas_id = mov.entradas_id
 AND e.produto_id  = mov.produto_id
 AND e.filial_id   = mov.filial_id
```

  Sem as duas condições extras o JOIN faz **fan-out** e multiplica qualquer `SUM`/`COUNT`.
- `entradas.curvaabc` guarda a curva **histórica no momento da entrada** — não usar para
  relatórios de estoque/compras (ver `03-produto-estoque.md`).

---

## Entrega e tele-entrega

Colunas em `movment`: `entrega` (`'S'`/`'N'`), `dtsaida_entrega` (despacho),
`dtchegada_entrega` (confirmação de chegada).

Regra de recorte usada em relatórios de venda que respeitam entrega:

```sql
(mov.entrega = 'N' OR mov.dtchegada_entrega IS NOT NULL)
```

Ou seja: uma tele-entrega **só entra no relatório depois que a chegada é confirmada**. Enquanto
está a caminho, a venda não aparece.

O troco da entrega vive em `pagamentos.troco_entrega` e tem comportamento em dois estágios —
ver `05-clientes-crm.md` e `08-armadilhas.md`.

---

## Descontos: manual x automático

- Desconto genérico da linha: `(preco_cad * quanti_uni) - valor_tot`.
- **Desconto manual** é identificado por `tipo_desc = 'M'`. Num relatório replicado do Pentaho, a
  coluna "Desconto" é definida como **desconto manual (`tipo_desc = 'M'`) ÷ venda bruta** — e
  **não** como `(bruto − líquido) / líquido`. São definições diferentes; confirmar qual vale em
  cada relatório antes de implementar.

---

## Agrupamentos de produto usados em vendas

- Quebra por **Referência / Perfumaria / Genérico / Outros** é feita por listas fixas de
  `produto.grupo_id`, com o `%` calculado sobre a venda líquida da própria linha. **As listas em si
  são do cadastro de cada cliente** (`grupo`), não do ERP — levantar com
  `SELECT grupo_id, descricao, desc_arvore FROM grupo`.
- **As listas de `grupo_id` costumam divergir entre relatórios da mesma instalação** (um `grupo_id`
  que entra em "Referência" num relatório e não em outro; grupos que só existem em "Outros" de um
  deles). Quando o objetivo é bater número a número com um relatório de referência já existente, a
  divergência é proposital — **não "padronizar" listas de grupo entre relatórios sem pedido
  explícito do cliente.**
- **Marca própria da rede:** identificada por `produto.espec_id`. A métrica "Marca" é
  `SUM(quanti_uni)` dos produtos com esse `espec_id`. **Qual valor de `espec_id` é a marca própria
  é cadastro de cada cliente** — conferir na base antes de usar (exemplo de valor real em
  `01-visao-geral.md`, "Exemplo de uma instalação").

---

## Relacionamentos frequentes

```sql
-- Filial
movment mov JOIN filial fil ON mov.filial_id = fil.filial_id

-- Produto (atenção ao P maiúsculo do lado de produto)
movment mov JOIN produto prod ON mov.produto_id = prod.Produto_id

-- Pagamentos do cupom (chave composta!)
movment mov JOIN pagamentos pag
  ON mov.filial_id = pag.filial_id
 AND mov.numlanc  = pag.numlanc

-- Forma de pagamento
pagamentos pag JOIN tipospgto tp ON pag.tipospgto_id = tp.tipospgto_id

-- Devoluções em período diferente
movment → cancelamento_movment           -- ver relatório ERP id = 1216

-- Transferência/remanejo
movment m LEFT JOIN transferencia t ON t.movment_id = m.movment_id AND t.apagado = 'N'
```

---

## Acompanhamento do Produto (linha do tempo de `movment`)

Padrão de drill-down consolidado: buscar em `movment` por `filial_id` + `produto_id` + intervalo
de data/hora, retornando **todas** as operações ordenadas por `data_hora ASC`. Colunas do detalhe:

| Coluna | Dado |
| --- | --- |
| Hora | `data_hora` formatado como `HH:mm:ss` |
| Operação | nome da operação + `Oper X / Mov Y` |
| E/S | `E_S` |
| Qtde | `quanti_uni` |
| Estoque | saldo após a operação (atenção: em entradas é o saldo **antes**) |
| Lanc. | `numlanc` |
| Nota | `numnota` |
| Usuário | `usuario_id` + `usuario` |
| Cliente/Forn. | cliente ou fornecedor |
| De filial | `transferencia.defilial_id` |
| Para filial | `transferencia.parafilial_id` |
| Obs. | `obs` |
