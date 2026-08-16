# ERP Big — Visão Geral e Convenções

O **ERP Big** (também chamado **BigPharma** / **Big Sistemas**) é o ERP usado por uma rede de
farmácias. Todo o dado operacional (vendas, produtos, estoque, preços, clientes, caixa,
financeiro) vive num banco **MariaDB**, base **`gerente`**.

> Todo acesso descrito aqui é **somente leitura**. Nunca existe caminho de escrita no ERP —
> qualquer correção/auditoria feita por sistemas externos vive fora dele (no banco da própria
> aplicação), nunca sobrepondo o dado do ERP.

## Índice dos arquivos de referência

| Arquivo | Conteúdo |
| --- | --- |
| `01-visao-geral.md` | Este arquivo: convenções gerais, flags, filiais, valores sentinela, tabela `relatorio` |
| `02-vendas-movment.md` | `movment`, `oper`, cupons, devoluções, transferência/remanejo, entradas, fórmulas de faturamento/custo/margem |
| `03-produto-estoque.md` | `produto`, `barras`, `grupo`, `classe_terapeutica`, `fabricantes`, estoques, lotes, curva ABC, demanda, suspensão de compra |
| `04-precos-ofertas.md` | Hierarquia de preço, `grupo_preco_produto`, `precosfilial`, promoções, desconto à vista |
| `05-clientes-crm.md` | `clientes`, duplicidade por CPF, R.F.V., WhatsApp (`orcament.msgcaixa`), entregas e troco |
| `06-financeiro-caixa.md` | `caixas`, `pagamentos`, `tipospgto`, sangria/suprimento, conferência, tela 302, `conf_caixa_loja_tipospgto` |
| `07-consultas-e-performance.md` | Índices, `FORCE INDEX`, fan-out, particionamento de consultas, BigInt, fuso horário |
| `08-armadilhas.md` | Catálogo de armadilhas e bugs reais (sintoma → causa → correção → como evitar) |
| `09-glossario.md` | Vocabulário do gestor ↔ tabela/coluna/valor |

---

## Convenções gerais do banco

### Flags de exclusão e cancelamento

- **`apagado`** — `char(1)` `'S'`/`'N'`. Presente em quase todas as tabelas transacionais e de
  cadastro (`movment`, `pagamentos`, `barras`, `caixas`, `filial`, `produtos_suspensos_compra`,
  `lote_novo`, `preco_medio_custo`, `estoque_minimo`, `estoque_minimo2`, `transferencia`,
  `usuario`, `conf_caixa_loja_tipospgto`...). **Sempre filtrar `apagado = 'N'`** — o ERP faz
  soft delete, o registro continua na tabela.
- **`cancelado`** — `char(1)` `'S'`/`'N'` em `movment` e `pagamentos`. Cancelamento de venda /
  lançamento. Filtrar `cancelado = 'N'` para movimento válido.
- **`status`** — em `usuario`, `'S'`/`'N'` (ativo).
- Flags binárias em geral são texto `'S'`/`'N'`, **não** booleano. Ao ordenar/comparar no lado da
  aplicação, converter para 1/0 em vez de comparar string.

### Chaves primárias compostas por `filial_id`

O ERP é multi-filial e vários IDs **não são globalmente únicos** — repetem entre filiais:

- **`caixas`** — a PK real é **`(filial_id, caixas_id)`**. O mesmo `caixas_id` existe em filiais
  diferentes com dados completamente distintos (ex.: `caixas_id = 24653` existe simultaneamente
  nas filiais 2, 4 e 6). Nunca filtrar/casar caixa só por `caixas_id`.
- **`entradas`** — `entradas_id` **não** é único por produto/filial; é reaproveitado entre itens
  de lotes de importação distintos. A chave de fato é `(entradas_id, produto_id, filial_id)`.
- **Cupom de venda** — a identidade de um cupom é o par **`(filial_id, numlanc)`**, nunca
  `numlanc` sozinho. Contagem correta: `COUNT(DISTINCT mov.filial_id, mov.numlanc)`.
- **`conf_caixa_loja_tipospgto`** — chave `filfisica_id + conf_caixa_loja_id + tipospgto_id`.

Consultar por par no MariaDB (row constructor suportado):

```sql
WHERE (cx.filial_id, cx.caixas_id) IN ((2,24653),(4,24653),(6,24653))
```

### Nomenclatura de colunas (inconsistente — preservar exatamente)

- **`produto.Produto_id`** — com **P maiúsculo** na tabela `produto`. Em `movment` e nas demais
  tabelas o campo referente é `produto_id` (minúsculo).
- **`fillogica_id`** — em `preco_medio_custo` e `lote_novo`, é o mesmo que `filial_id`.
- **`filfisica_id`** — em `conf_caixa_loja_tipospgto`, também equivale à filial.
- `pagamentos` usa **`datahora`** (sem underscore); `movment` usa **`data_hora`** (com underscore).
- `caixas` usa `dtinicial` (abertura) / `dtfinal` (fechamento).

### Valores sentinela e exclusões obrigatórias

| Onde | Valor sentinela | O que fazer |
| --- | --- | --- |
| `filial_id` | `1` (ESCRITORIO) e `999` (registro técnico, nome nulo) | `mov.filial_id NOT IN (1, 999)` em toda query de venda |
| `produto.descricao` | contém `ARREDOND` | excluir sempre de faturamento/clientes/IPC/qualquer KPI — é produto de ajuste de troco |
| `clientes.dtcadastro` | `1000-01-01` (4.294 clientes) | tratar qualquer data anterior a `1990-01-01` como ausente/`NULL` |
| `lote_novo.validade` | datas absurdas | filtrar `ln.validade < '2100-01-01'` |
| `clientes.cpf` | CPFs de dígito repetido (`00000000000`, `11111111111`) | tratar como "sem CPF" |
| `clientes_id` | `0` | "cliente não identificado" (venda N.I.) |
| `usuario_id` do caixa | ausente/`NULL` | tratado como sentinela "Sem operador identificado" (`usuario_id = 0` em rotas de drill-down) |
| `grupo_preco_produto.preco_vnd` | `0` | tratar como ausente (`NULLIF(preco_vnd, 0)`) |

> Regra geral: **nunca assumir que uma data do ERP é plausível.** Colunas de data sem constraint
> de mínimo conhecida podem trazer sentinelas de migração. Aplicar guarda de faixa sempre.

### Filiais cadastradas no ERP

| filial_id | reduz | Observação |
| --- | --- | --- |
| 1 | ESCRITORIO | Não é filial de venda — excluir sempre das queries |
| 2 | MATRIZ | Filial principal |
| 3 | FILIAL 1 | |
| 4 | FILIAL 2 | |
| 5 | FILIAL 3 | |
| 6 | FILIAL 4 | |
| 8 | FILIAL 5 | |
| 9 | FILIAL 6 | |
| 11 | FILIAL 7 | |
| 12 | FILIAL 8 | |
| 13 | FILIAL 9 | |
| 14 | FILIAL 10 | Filial das vendas "Loja WhatsApp" (ver `05-clientes-crm.md`) |
| 15 | FILIAL 11 | |
| 999 | (nulo) | Registro técnico — excluir sempre das queries |

- **Atenção:** `filial_id = 12` é FILIAL 8 e `filial_id = 13` é FILIAL 9 — a numeração do nome
  **não** acompanha o id.
- **Nome de filial em relatórios:** usar sempre o nome abreviado **`filial.reduz`** (máx. 11
  chars). Não prefixar com `filial_id` na exibição. Para nome completo existem `filial.nome`
  (com razão social), `filial.psi_nomest` e `filial.menstit`.
- São **11 filiais operacionais** (todas exceto `filial_id = 1`).

### Tabela `filial`

| Coluna | Descrição |
| --- | --- |
| `filial_id` | PK |
| `reduz` | Nome abreviado da empresa — **usar este em relatórios** |
| `nome` | Nome completo com razão social |
| `psi_nomest` | Nome completo (alternativa) |
| `menstit` | Nome completo (alternativa) |
| `apagado` | `'S'`/`'N'` |

### Tabela `usuario` (operador do ERP)

Cadastro da tela "Usuários" do sistema.

| Coluna | Descrição |
| --- | --- |
| `usuario_id` | PK |
| `nome` | Nome do operador |
| `filial_id` | Filial de lotação |
| `num_carteira` | Campo "Número da Carteira" — texto livre, mas usado por **convenção manual do gestor** para marcar papel: valor exato `GESTOR` ou `OPERADOR CAIXA` |
| `apagado` | `'S'`/`'N'` |
| `status` | `'S'`/`'N'` (ativo) |

Consulta usada para sugerir papéis por filial:

```sql
SELECT usuario_id, nome, filial_id
FROM usuario
WHERE UPPER(TRIM(num_carteira)) = 'GESTOR'      -- ou = 'OPERADOR CAIXA'
  AND apagado = 'N' AND status = 'S'
```

> Não guardar snapshot do nome do usuário em sistemas externos — buscar sempre ao vivo no ERP,
> para não ficar desatualizado se o funcionário mudar de nome.

---

## Tabela `relatorio` — SQLs prontos do ERP

O ERP guarda os relatórios padrão (SQL + parâmetros) na tabela **`relatorio`**:

| Coluna | Descrição |
| --- | --- |
| `relatorio_id` | PK |
| `descricao` | Nome do relatório |
| `finalidade` | Para que serve |
| `sql` | O SQL completo, com placeholders |
| `parametros` | Parâmetros esperados |
| `legenda` | Legenda/observações |

**Antes de recriar qualquer regra complexa do ERP** (giro, sugestão de compra, cobertura,
classificações, lucratividade), consultar essa tabela — muita regra de negócio já está modelada
ali:

```sql
SELECT relatorio_id, descricao, finalidade, sql
FROM relatorio
WHERE descricao LIKE '%termo%'
```

Os SQLs do ERP usam **placeholders substituídos em runtime** pelo próprio ERP — por exemplo
`{vl_bruto}`, `<opcao_custo>`, `{filtro_somente_prod}`, `{vl_custo_automatico_v2}`. Ao adaptar um
SQL do `relatorio`, substituir manualmente cada placeholder pelo valor concreto.

### Relatórios ERP de referência

| relatorio_id | descricao | Quando usar como referência |
| --- | --- | --- |
| 1013 | Lucratividade por Filial | Base para lucratividade por filial com impostos |
| 1216 | Lucratividade por Filial - PlugPharma BI | Base quando devoluções precisam ser tratadas no período em que ocorreram (não na venda original) |
| 28 | Lucratividade por Produto | Base para lucratividade por produto |
| 483 | Lucratividade por Fabricante | Base para lucratividade por fabricante |
| 623 | Lucratividade por Grupo | Base para lucratividade por grupo de produto |
| 12 | Ticket Médio, Cupons e Clientes por Filial | Base para relatórios de performance de atendimento |

---

## Telas do ERP citadas

| Tela / local no ERP | Reflexo no banco |
| --- | --- |
| **Tela 302 — Geração da Movimentação Financeira de Caixas** | Ao clicar OK para um caixa fechado, o ERP grava `caixas.finprocescritorio = 'S'`. Enquanto não gerado, fica `'N'`. Vocabulário do gestor: "**caixa importado**" |
| **Caixas Fechados > Detalhes da Conferência de Caixa** | Lê `conf_caixa_loja` + `conf_caixa_loja_tipospgto` — **não recalcula nada** |
| **Relatório de Caixa — Apurado X Computado** (impresso) | Mesma fonte: `conf_caixa_loja_tipospgto` (`valor_apurado`/`valor_computado`) |
| **Comprovante físico de Fechamento de Caixa** | "N.Caixa Dia" = `caixas.caixa_dia` (com margem de ±1, ver `06-financeiro-caixa.md`). Sangrias/Suprimentos/Diferença **não têm coluna própria** — são somados na hora da impressão a partir de `pagamentos` |
| **Cadastro do produto → aba "Estoque Filiais"** | `estoque_minimo` (estoque atual) + `estoque_minimo2` (mínimo/máximo/demanda). Coluna visual "Min. Abs." = `estoque_minimo2.faceamento` |
| **Tela "Usuários"** | `usuario`, campo "Número da Carteira" = `usuario.num_carteira` |
| **Tela de Compras (solicitação de remanejo)** | `transferencia.remanejamento_id > 0` |

## Tabela `logs` — histórico de alteração

Alterações de campos do ERP costumam ficar em **`logs`**. Exemplo para o Mínimo Absoluto:

```sql
SELECT * FROM logs
WHERE tabela = 'estoque_minimo2'
  AND campo IN ('faceamento', 'Minimo Absoluto')
  AND chavepri = <produto_id>
```

Colunas úteis: `tabela`, `campo`, `chavepri`, `filial_id`, `valor_ant`, `valor_pos`,
`usuario_id`, `data_hora`.

---

## Regra de documentação contínua

Sempre que uma tabela, coluna, relacionamento ou padrão de query novo do ERP for descoberto,
documentá-lo imediatamente. Regra do projeto de origem: **um bug corrigido mas não documentado
volta a ser reintroduzido ou re-diagnosticado do zero.** Formato mínimo de registro:
sintoma → causa raiz confirmada (não suposta) → correção → como evitar → data/contexto.

**Em caso de dúvida sobre regra de negócio, PERGUNTAR antes de inventar.** Definição de métrica,
escopo de filtro, tipo de agregação (bruto x líquido, cupons x linhas), ordenação padrão e
comportamento de vazio nunca devem ser chutados.
