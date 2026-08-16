# Produto, Estoque, Lotes e Reposição

Sumário:

- [`produto`](#produto)
- [`barras` — códigos de barras alternativos](#barras--códigos-de-barras-alternativos)
- [`grupo` — categoria do produto](#grupo--categoria-do-produto)
- [`classe_terapeutica`](#classe_terapeutica)
- [`fabricantes`](#fabricantes)
- [`estoque_minimo` — estoque atual por filial](#estoque_minimo--estoque-atual-por-filial)
- [`estoque_minimo2` — mínimo/máximo/demanda](#estoque_minimo2--mínimomáximodemanda)
- [`lote` x `lote_novo`](#lote-x-lote_novo)
- [`curvaabc`](#curvaabc)
- [`preco_medio_custo`](#preco_medio_custo)
- [`produtos_suspensos_compra` — suspensão de compra](#produtos_suspensos_compra--suspensão-de-compra)
- [Demanda e reposição](#demanda-e-reposição)

---

## `produto`

Cadastro de produtos. **A PK é `Produto_id` com P maiúsculo** — em todas as outras tabelas a
referência é `produto_id` minúsculo.

| Coluna | Descrição |
| --- | --- |
| `Produto_id` | PK (**P maiúsculo**) |
| `descricao` | Descrição do produto |
| `labora` | Fabricante legado — **pode ser NULL** |
| `fabricantes_id` | FK para `fabricantes` |
| `barras` | Código de barras principal do cadastro |
| `controla_validade` | Flag de controle de validade |
| `receita` | Campo de **receituário** (`'N'`/`'S'`) — **nunca usar como grupo/categoria** |
| `grupo_id` | FK para `grupo` |
| `classe_terapeutica_id` | FK para `classe_terapeutica` |
| `espec_id` | Especificação; `257001` = marca própria "SUPRA ENERGY" |
| `preco_cmp_un` | Preço de compra unitário — **pode estar defasado** |
| `margem` | Margem % — **pode estar defasada** |
| `desconto_avista` | Desconto à vista — **na prática costuma ser 0**, não usar (ver `04-precos-ofertas.md`) |

> `produto.preco_cmp_un × (1 + produto.margem/100)` **não é o preço de venda final** — só
> fallback. Ver `04-precos-ofertas.md`.

---

## `barras` — códigos de barras alternativos

Um produto pode ter **vários** códigos de barras ativos (códigos alternativos / de caixa).

| Coluna | Descrição |
| --- | --- |
| `produto_id` | FK |
| `barras` | Código de barras (cod_barras) |
| `apagado` | `'S'`/`'N'` |

**Nunca fazer `LEFT JOIN barras` numa query que tenha `SUM`/`COUNT`/`MAX` agregados** — o JOIN faz
fan-out (1 linha de `movment` vira N linhas, uma por código ativo) e infla todos os agregados.
Caso real: produto 5728 (TINT KOLESTON 6.0 LOUR ESCURO) tem 4 códigos de barra ativos; uma entrada
real de 3 unidades aparecia como 12 (3 × 4).

Padrão correto — subquery escalar:

```sql
COALESCE(
  (SELECT MIN(b2.barras) FROM barras b2
    WHERE b2.produto_id = p.Produto_id AND b2.apagado = 'N'),
  p.barras
) AS cod_barras
```

(Quando o JOIN for inevitável, agrupar por `produto_id` com `MIN(barras)` antes de juntar.)

---

## `grupo` — categoria do produto

| Coluna | Descrição |
| --- | --- |
| `grupo_id` | PK |
| `descricao` | Nome do grupo |
| `desc_arvore` | Caminho hierárquico, ex.: `"3. CONVENIENCIA - 3.02 CONV. - BEBIDAS"` |
| `minA` / `maxA` | Min/Max dias para curva A |
| `minB` / `maxB` | Min/Max dias para curva B |
| `minC` / `maxC` | Min/Max dias para curva C |
| `minD` / `maxD` | Min/Max dias para curva D |

Join: `produto.grupo_id = grupo.grupo_id`.

**Nunca usar `produto.receita` para grupo** — `receita` é campo de receituário (`'N'`/`'S'`).

Inicial da categoria pai (ex.: "C" para Conveniência, "P" para Perfumaria):

```sql
LEFT(REGEXP_SUBSTR(g.desc_arvore, '[A-Za-z]+'), 1)
```

**Min. Dias / Max. Dias:** quando não estiverem no cadastro do produto, buscar no grupo do
produto, nos campos por curva (`minA/maxA`, `minB/maxB`, `minC/maxC`, `minD/maxD`).

---

## `classe_terapeutica`

| Coluna | Descrição |
| --- | --- |
| `classe_terapeutica_id` | PK |
| `descricao` | Ex.: `"HIPERTENSÃO / CARDIOVASCULAR / USO CONTINUO"` |

Join via `produto.classe_terapeutica_id`.

**A classificação de uso fica sempre após a 2ª barra** da descrição: `"USO CONTINUO"` ou
`"USO RECORRENTE"`.

---

## `fabricantes`

| Coluna | Descrição |
| --- | --- |
| `fabricantes_id` | PK |
| `descricao` | Nome do fabricante — **sempre preenchido** |

Preferir `fabricantes.descricao` a `produto.labora` (legado, pode ser NULL).

---

## `estoque_minimo` — estoque atual por filial

Fonte do **estoque atual por produto/filial** — é o que a aba "Estoque Filiais" do cadastro do
produto exibe.

| Coluna | Descrição |
| --- | --- |
| `produto_id` | FK |
| `filial_id` | Filial |
| `estoque` | **Estoque atual** |
| `estoque_reserva` | Estoque reservado |
| `minimo` | Mínimo |
| `precoee` | Preço de entrada (usado na cascata de custo) |
| `compra_suspensa` | **Existe, mas na prática fica sempre `'N'` — não é mantida nesta base. Não usar** |
| `apagado` | `'S'`/`'N'` |

---

## `estoque_minimo2` — mínimo/máximo/demanda

Parâmetros de reposição por filial, também na aba "Estoque Filiais". **Fonte da demanda.**

| Coluna | Descrição |
| --- | --- |
| `produto_id` | FK |
| `filial_id` | Filial |
| `minimo` | Mínimo |
| `faceamento` | **Corresponde à coluna visual "Min. Abs." (Mínimo Absoluto) do ERP** |
| `maximo` | Máximo |
| `maximo_abs` | Máximo absoluto |
| `demanda` | **Demanda diária por produto/filial** |
| `desviopadrao` | Desvio padrão da demanda |
| `apagado` | `'S'`/`'N'` |

Histórico de alteração do Mínimo Absoluto: tabela `logs` com
`tabela = 'estoque_minimo2'`, `campo IN ('faceamento', 'Minimo Absoluto')`,
`chavepri = produto_id`, mais `filial_id`, `valor_ant`, `valor_pos`, `usuario_id`, `data_hora`.

---

## `lote` x `lote_novo`

| Tabela | Situação |
| --- | --- |
| `lote` | **Tabela antiga.** Dados históricos até 2015, com `estoque` e `qtde` **zerados**. Não usar para consultas de estoque atual |
| `lote_novo` | **Tabela ativa** (BigPharma) — usar sempre esta |

`lote_novo`:

| Coluna | Descrição |
| --- | --- |
| `lote_novo_id` | PK |
| `fillogica_id` | **= `filial_id`** |
| `produto_id` | FK |
| `lote` | Número do lote |
| `validade` | DATE de vencimento |
| `estoque` | Quantidade atual do lote |
| `fabricacao` | Data de fabricação |
| `apagado` | `'S'`/`'N'` |

Regras:

- Join com filial: `ln.fillogica_id = fil.filial_id`.
- Campo de validade: `validade`; campo de quantidade: `estoque`.
- **Filtrar datas inválidas:** `ln.validade < '2100-01-01'`.

---

## `curvaabc`

Curva ABC **calculada sobre vendas**, por produto/filial.

| Coluna | Descrição |
| --- | --- |
| `produto_id` | FK |
| `filial_id` | Filial |
| `curvaabc` | Curva por venda |
| `curvaabc_est` | Curva por estoque |

**Não usar `entradas.curvaabc`** para relatórios de estoque/compras: ali a curva fica gravada
historicamente no momento da entrada e pode divergir da curva atual por venda.

---

## `preco_medio_custo`

Custo médio de cada produto por filial, mantido pelo ERP.

| Coluna | Descrição |
| --- | --- |
| `fillogica_id` | **= `filial_id`** |
| `produto_id` | FK |
| `pmc_atual` | Custo médio atual |
| `apagado` | `'S'`/`'N'` |

Entra na cascata de custo (ver `02-vendas-movment.md`).

---

## `produtos_suspensos_compra` — suspensão de compra

**Fonte de verdade da suspensão de compra por produto/filial.** Tabela dedicada, usada pelo setor
de Compras. Uma suspensão pode valer **só para algumas filiais** do produto, não todas.

| Coluna | Descrição |
| --- | --- |
| `produto_id` | FK |
| `filial_id` | Filial |
| `compra_suspensa` | `'S'`/`'N'` |
| `data_inicio_bloqueio` | Início da vigência (pode ser `NULL` = indefinido) |
| `data_fim_bloqueio` | Fim da vigência (pode ser `NULL` = indefinido) |
| `justificativa_susp_compra_id` | FK para `justificativa_susp_compra` |
| `apagado` | `'S'`/`'N'` — **sempre filtrar `'N'`** |

Consulta respeitando o período de vigência:

```sql
WHERE psc.apagado = 'N'
  AND psc.compra_suspensa = 'S'
  AND (psc.data_inicio_bloqueio IS NULL OR psc.data_inicio_bloqueio <= CURDATE())
  AND (psc.data_fim_bloqueio    IS NULL OR psc.data_fim_bloqueio    >= CURDATE())
```

Comparação entre as três colunas parecidas:

| Coluna | Vale? |
| --- | --- |
| `produtos_suspensos_compra.compra_suspensa` | **Sim — fonte de verdade**, com justificativa e período |
| `precosfilial.comprasuspensa` | Reflete o mesmo dado (sincronizado), mas sem justificativa/período |
| `estoque_minimo.compra_suspensa` | **Não** — na prática sempre `'N'`, não é mantida nesta base |

Caso real: um produto exibido como "abaixo da demanda" estava, na verdade, com compra suspensa em
uma das filiais — `estoque_minimo.compra_suspensa = 'N'` em todas as filiais, mas
`produtos_suspensos_compra.compra_suspensa = 'S'` (`apagado = 'N'`) na filial em questão.

---

## Demanda e reposição

- **Estoque atual** por produto/filial: `estoque_minimo.estoque`.
- **Demanda diária** por produto/filial: `estoque_minimo2.demanda`.
- **Mínimo absoluto** exibido como "Min. Abs.": `estoque_minimo2.faceamento`.
- **Min. Dias / Max. Dias** por curva: no cadastro do produto ou, na falta, no `grupo`
  (`minA/maxA` … `minD/maxD`).
- **Curva** para classificação: `curvaabc.curvaabc` (por venda) / `curvaabc.curvaabc_est`
  (por estoque).
- **Suspensão de compra**: `produtos_suspensos_compra` (nunca `estoque_minimo.compra_suspensa`).
- Antes de recriar regra de giro, cobertura, sugestão de compra ou classificação — **consultar a
  tabela `relatorio`**; muita coisa já está modelada nos SQLs padrão do ERP.
