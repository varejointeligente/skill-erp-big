---
name: erp-big
description: Base de conhecimento do ERP Big (BigPharma / Big Sistemas), ERP de farmácia com banco MariaDB na base `gerente`. Use SEMPRE que aparecer "ERP Big", "BigPharma", "base gerente", ou tabelas desse ERP — `movment`, `numlanc`, `oper`, `estoque_minimo2`, `grupo_preco_produto`, `lote_novo`, `precosfilial`, `caixas`, `conf_caixa_loja`, `tipospgto`, `curvaabc`, `produtos_suspensos_compra`. Use também, mesmo sem o ERP ser nomeado, quando a tarefa for escrever ou revisar SQL/relatório de farmácia sobre faturamento, cupons, ticket médio, margem, CMV, curva ABC, ruptura, demanda, estoque por filial, validade/lote, preço e oferta, desconto à vista, conferência e diferença de fechamento de caixa, sangria e suprimento, transferência x remanejo, RFV de clientes ou entregas — e o banco for MariaDB. Consulte antes de escrever a query, não depois — a maior parte dos erros nesse ERP vem de armadilhas conhecidas (fan-out de JOIN, IDs não únicos entre filiais, soft delete, hierarquia de preço) catalogadas aqui.
---

# ERP Big — base de conhecimento

Este skill carrega o que já foi aprendido, a duras penas, sobre o banco do ERP Big. Ele existe
porque quase toda query nesse ERP que parece certa está errada de um jeito silencioso: o número
sai, ninguém desconfia, e a diferença só aparece quando o gestor confere contra o papel.

## Como usar

**Leia a referência da área antes de escrever SQL.** Não tente reconstruir a regra de memória —
as regras desse ERP não são deriváveis do nome das colunas.

| Você precisa de… | Leia |
| --- | --- |
| Convenções, flags, filiais, PKs compostas, tabela `relatorio` | `references/01-visao-geral.md` |
| Venda, cupom, `oper`, devolução, transferência/remanejo, faturamento, margem | `references/02-vendas-movment.md` |
| Produto, código de barras, grupo, estoque, lote/validade, curva ABC, demanda | `references/03-produto-estoque.md` |
| Preço de venda, promoção, desconto à vista, oferta | `references/04-precos-ofertas.md` |
| Cliente, CPF duplicado, RFV, WhatsApp, entrega e troco | `references/05-clientes-crm.md` |
| Caixa, pagamento, sangria/suprimento, conferência, fechamento | `references/06-financeiro-caixa.md` |
| Performance, índices, `FORCE INDEX`, fan-out, BigInt, fuso | `references/07-consultas-e-performance.md` |
| "Por que esse número está errado?" | `references/08-armadilhas.md` |
| O gestor usou um termo que você não reconhece | `references/09-glossario.md` |

Quando a tarefa cruza áreas (ex.: margem por filial no fechamento do mês), leia as duas —
a interseção é justamente onde moram os erros.

## As cinco regras que valem para qualquer query

Estas se aplicam sempre; o detalhe e o porquê estão nas referências.

1. **Soft delete é regra, não exceção.** Praticamente toda tabela tem `apagado` (`'S'`/`'N'`) e as
   transacionais têm `cancelado`. Sem `apagado = 'N'` você está somando lixo. São strings `'S'`/`'N'`,
   não booleanos.

2. **ID sozinho não identifica nada.** O ERP é multi-filial e vários IDs se repetem entre filiais:
   cupom é `(filial_id, numlanc)`, caixa é `(filial_id, caixas_id)`, entrada é
   `(entradas_id, produto_id, filial_id)`. Casar por um lado só produz fan-out silencioso —
   o `SUM` infla e nada acusa erro.

3. **JOIN em tabela filha antes de agregar duplica linha.** `barras`, `entradas` e afins têm N
   linhas por produto. Se a query tem `SUM`/`COUNT`, use subquery escalar em vez de `LEFT JOIN`.

4. **Venda válida tem filtro canônico.** `apagado='N' AND cancelado='N' AND oper IN (2,3)`, mais a
   exclusão do produto de arredondamento e das filiais não operacionais. Faltando qualquer pedaço,
   o faturamento sai diferente do ERP.

5. **Preço não sai da tabela `produto`.** A fonte é `grupo_preco_produto`, com uma hierarquia de
   quatro níveis e promoções com janela de validade. `produto.preco_cmp_un × margem` é fallback
   defasado, não resposta.

## Antes de dar um número como certo

O ERP tem relatórios próprios com o SQL guardado na tabela `relatorio`. Antes de reconstruir uma
regra de negócio complexa (giro, cobertura, sugestão de compra, lucratividade com impostos),
procure ali primeiro:

```sql
SELECT relatorio_id, descricao, finalidade, sql
FROM relatorio
WHERE descricao LIKE '%termo%';
```

Reaproveitar o SQL do próprio ERP é mais seguro do que deduzir a regra — e é o que garante que o
seu número bata com o que o cliente vê na tela dele. Os SQLs usam placeholders (`{vl_bruto}`,
`<opcao_custo>`) substituídos em runtime; troque por valores concretos ao adaptar.

## Ao validar contra o cliente

Quando o cliente disser que um número está errado, resista ao impulso de culpar cache, ordenação
ou arredondamento. Vá ao dado cru: rode a query isolando **uma** linha que ele apontou, e compare
campo a campo. Praticamente toda divergência já registrada tinha causa estrutural — fan-out,
filtro faltando, fuso, ID ambíguo — e nenhuma era "coisa do cache".

Ao encontrar uma causa nova, registre em `references/08-armadilhas.md` no mesmo formato
(sintoma → causa → correção → como evitar), com o caso concreto. O caso concreto é o que ensina;
a regra abstrata sozinha não gruda.

## Consultando o banco

`scripts/consultar_big.py` abre conexão **somente leitura** no MariaDB e imprime o resultado em
tabela ou JSON. Use-o para validar hipóteses em vez de afirmar de memória — e leia
`references/07-consultas-e-performance.md` antes de rodar qualquer coisa que varra `movment`
num período longo.

Consulta de leitura para conferir dado é livre. Qualquer coisa que **escreva** no ERP precisa de
confirmação explícita do cliente antes — o ERP é a fonte de verdade da operação dele.
