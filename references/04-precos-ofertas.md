# Preços, Promoções e Descontos

> Estas regras valem para **todos os módulos** que exibam preço de produto — leitor de preço,
> caderno de ofertas, relatórios de venda, etiquetas, comparativos de mercado. Ignorar qualquer
> uma delas causa exibição de preço errado.

---

## 1. Fonte do preço de venda — `grupo_preco_produto.preco_vnd`

**`grupo_preco_produto.preco_vnd` é a única fonte verdadeira do preço de venda atual.**

A tabela `produto` tem `preco_cmp_un` e `margem`, mas esses campos **podem ficar defasados**. A
fórmula `preco_cmp_un × (1 + margem/100)` **não deve ser usada como preço final** — só como
fallback quando `grupo_preco_produto` não tiver linha para o produto.

```sql
-- Preço de tabela correto:
COALESCE(NULLIF(gpp.preco_vnd, 0), ROUND(p.preco_cmp_un * (1 + p.margem / 100), 2)) AS preco_venda
```

> **Bug real (2026-07-06):** CITALOPRAM 20MG mostrava R$ 86,67 (fórmula defasada de `produto`) em
> vez de R$ 105,24 (`grupo_preco_produto.preco_vnd`).

`preco_vnd = 0` deve ser tratado como ausente (daí o `NULLIF(preco_vnd, 0)`).

---

## 2. Desconto à vista ("Clube do Pedrinho") — `grupo_preco_produto.desconto`

O percentual de desconto à vista vem de **`grupo_preco_produto.desconto`** — **não** de
`produto.desconto_avista` (esse campo costuma ser `0`).

**Fórmula:**

```
preco_com_desconto = preco_vnd × (1 − desconto / 100)
```

- Exemplo: `preco_vnd = 105,24` · `desconto = 74,45%` → **R$ 26,89**.
- O desconto **sempre incide sobre `preco_vnd`** (preço de tabela) — nunca sobre custo, nunca
  sobre preço promocional.

---

## 3. Promoção por Data — `grupo_preco_produto.preco_pro`

Campos:

| Coluna | Descrição |
| --- | --- |
| `preco_pro` | Valor promocional **já calculado** |
| `dtiniciopromocao` | Início da promoção |
| `valid_pro` | Fim da promoção |

**Regra de validade:** só exibir/usar `preco_pro` se `dtiniciopromocao ≤ hoje ≤ valid_pro`. Se a
promoção expirou ou ainda não começou, ignorar e usar `preco_vnd` normalmente.

```sql
CASE
  WHEN COALESCE(gpp.preco_pro, 0) > 0
    AND gpp.dtiniciopromocao IS NOT NULL
    AND gpp.valid_pro IS NOT NULL
    AND NOW() BETWEEN gpp.dtiniciopromocao AND gpp.valid_pro
  THEN gpp.preco_pro
  ELSE COALESCE(NULLIF(gpp.preco_vnd, 0), <formula_produto>)
END AS preco_final
```

---

## 4. Promoção por Data **e** Desconto à Vista ativos ao mesmo tempo

**Usar o preço da Promoção por Data. O desconto à vista é ignorado.**

Não somar, não combinar, não mostrar os dois. A promoção por data tem prioridade total sobre o
desconto à vista enquanto estiver dentro do período válido.

| Situação | Preço exibido | Clube do Pedrinho |
| --- | --- | --- |
| Só `preco_vnd` (sem mais nada) | `preco_vnd` | — |
| Promoção por data **ativa** | `preco_pro` | — (ignorar desconto à vista) |
| Promoção por data **expirada/futura** + desconto à vista | `preco_vnd` (tachado) | `preco_vnd × (1 − desconto/100)` |
| Promoção por data **ativa** + desconto à vista | `preco_pro` | — (desconto à vista ignorado) |

---

## 5. Hierarquia completa de preço (do mais para o menos prioritário)

1. **`precosfilial.preco_promo`** — preço especial **por filial**
   (ativo quando `NOW() BETWEEN inicio_promocao AND final_promocao`)
2. **`grupo_preco_produto.preco_pro`** — promoção por data
   (ativo quando `NOW() BETWEEN dtiniciopromocao AND valid_pro`)
3. **`grupo_preco_produto.preco_vnd`** — preço de tabela da rede
4. **`ROUND(produto.preco_cmp_un × (1 + produto.margem / 100), 2)`** — fallback (defasado, usar
   só se `grupo_preco_produto` não tiver linha)

O **desconto à vista** (`grupo_preco_produto.desconto`) só entra quando **nenhum dos itens 1 e 2**
está ativo.

---

## 6. Sem filial conhecida

Quando não há filial identificada (acesso local / IP não identificado), usar uma CTE que agrega
`grupo_preco_produto` **sem filtro de filial**, pegando o preço do grupo disponível:

```sql
WITH grupo_padrao AS (
  SELECT produto_id, MAX(NULLIF(preco_vnd, 0)) AS preco_vnd
  FROM grupo_preco_produto
  GROUP BY produto_id
)
```

---

## Tabelas envolvidas

### `grupo_preco_produto`

| Coluna | Papel |
| --- | --- |
| `preco_vnd` | Preço de tabela da rede — **fonte de verdade do preço de venda** |
| `desconto` | Percentual de desconto à vista (Clube do Pedrinho) |
| `preco_pro` | Preço da promoção por data (já calculado) |
| `dtiniciopromocao` | Início da promoção por data |
| `valid_pro` | Fim da promoção por data |

### `precosfilial`

| Coluna | Papel |
| --- | --- |
| `preco_promo` | Preço especial **por filial** — nível mais alto da hierarquia |
| `inicio_promocao` | Início da vigência do preço por filial |
| `final_promocao` | Fim da vigência do preço por filial |
| `preco_custo` | Custo (entra na cascata de custo — ver `02-vendas-movment.md`) |
| `comprasuspensa` | Reflete a suspensão de compra (sincronizada de `produtos_suspensos_compra`) |

### `produto` (campos de preço — apenas fallback)

| Coluna | Papel |
| --- | --- |
| `preco_cmp_un` | Preço de compra unitário — pode estar defasado |
| `margem` | Margem % — pode estar defasada |
| `desconto_avista` | **Não usar** — costuma ser 0 |
