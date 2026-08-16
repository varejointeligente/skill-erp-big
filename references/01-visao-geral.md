# ERP Big — Visão Geral e Convenções

O **ERP Big** (também chamado **BigPharma** / **Big Sistemas**) é um ERP de varejo farmacêutico
usado por redes de farmácia. Todo o dado operacional (vendas, produtos, estoque, preços, clientes,
caixa, financeiro) vive num banco **MariaDB**, cuja base normalmente se chama **`gerente`**.

> **O nome da base pode variar por instalação.** `gerente` é o nome usual do ERP Big, mas não é
> garantido — confirmar com `SHOW DATABASES;` antes de assumir.

> Todo acesso descrito aqui é **somente leitura**. Nunca existe caminho de escrita no ERP —
> qualquer correção/auditoria feita por sistemas externos vive fora dele (no banco da própria
> aplicação), nunca sobrepondo o dado do ERP.

> **Universal x específico do cliente.** Este arquivo descreve o ERP Big em geral. Ids de filial,
> nomes comerciais, apelidos de campo livre e parâmetros de negócio **mudam de cliente para
> cliente** — o que é específico de uma instalação está isolado em
> [Exemplo de uma instalação](#exemplo-de-uma-instalação-confirmar-na-base-do-cliente), e vale só
> como ilustração de formato.

## Índice dos arquivos de referência

| Arquivo | Conteúdo |
| --- | --- |
| `01-visao-geral.md` | Este arquivo: convenções gerais, flags, filiais, valores sentinela, tabela `relatorio`, exemplo de uma instalação |
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
| `filial_id` | `1` (costuma ser o escritório) e `999` (registro técnico, nome nulo) | `mov.filial_id NOT IN (1, 999)` em toda query de venda |
| `produto.descricao` | contém `ARREDOND` | excluir sempre de faturamento/clientes/IPC/qualquer KPI — é produto de ajuste de troco |
| `clientes.dtcadastro` | `1000-01-01` (4.294 clientes) | tratar qualquer data anterior a `1990-01-01` como ausente/`NULL` |
| `lote_novo.validade` | datas absurdas | filtrar `ln.validade < '2100-01-01'` |
| `clientes.cpf` | CPFs de dígito repetido (`00000000000`, `11111111111`) | tratar como "sem CPF" |
| `clientes_id` | `0` | "cliente não identificado" (venda N.I.) |
| `usuario_id` do caixa | ausente/`NULL` | tratado como sentinela "Sem operador identificado" (`usuario_id = 0` em rotas de drill-down) |
| `grupo_preco_produto.preco_vnd` | `0` | tratar como ausente (`NULLIF(preco_vnd, 0)`) |

> Regra geral: **nunca assumir que uma data do ERP é plausível.** Colunas de data sem constraint
> de mínimo conhecida podem trazer sentinelas de migração. Aplicar guarda de faixa sempre.

### Filiais — o que é do ERP e o que é do cliente

**A lista de filiais é sempre específica da instalação** — quantidade, ids e nomes mudam de
cliente para cliente. Nunca reproduzir um mapa de filiais de memória; obter do banco:

```sql
SELECT filial_id, reduz FROM filial WHERE apagado = 'N' ORDER BY filial_id;
```

O que é convenção do ERP, e vale em qualquer instalação:

- **`filial_id = 1` costuma ser o escritório** (não é filial de venda) e **`filial_id = 999` é um
  registro técnico** (nome nulo). Os dois saem de toda query de venda:
  `mov.filial_id NOT IN (1, 999)`.
- **"Rede" / "filiais operacionais"** = as linhas de `filial` com `apagado = 'N'` menos esses dois
  sentinelas. O número de filiais operacionais é dado da instalação — contar, não decorar.
- **Nome de filial em relatórios:** usar sempre o nome abreviado **`filial.reduz`** (máx. 11
  chars). Não prefixar com `filial_id` na exibição. Para nome completo existem `filial.nome`
  (com razão social), `filial.psi_nomest` e `filial.menstit`.
- **O nome em `reduz` não acompanha o `filial_id`.** É comum uma rede ter `filial_id = 12` com
  `reduz = 'FILIAL 8'`. Traduzir id ↔ nome sempre pela tabela, nunca por aritmética.

Um mapa concreto, só como ilustração de formato, está em
[Exemplo de uma instalação](#exemplo-de-uma-instalação-confirmar-na-base-do-cliente).

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
| `num_carteira` | Campo "Número da Carteira" — **texto livre**, sem semântica própria no ERP |
| `apagado` | `'S'`/`'N'` |
| `status` | `'S'`/`'N'` (ativo) |

> **`num_carteira` não tem significado definido pelo ERP.** É um campo livre; se um cliente o usa
> para marcar papel de funcionário, isso é convenção manual daquela instalação (e pode estar vazio
> ou com outro conteúdo em outra rede). Antes de tratá-lo como papel, olhar que valores existem:
> `SELECT DISTINCT num_carteira FROM usuario WHERE apagado='N'`. Um exemplo de convenção real está
> em [Exemplo de uma instalação](#exemplo-de-uma-instalação-confirmar-na-base-do-cliente).

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

## Replicação entre loja e retaguarda — `lojas_leram`

O ERP Big é distribuído: a base central e as bases das lojas trocam alterações entre si. O
controle dessa troca vive na própria linha alterada, na coluna **`lojas_leram`** — ela marca quais
lojas já leram aquele registro. Enquanto a linha estiver marcada como já lida por todo mundo, o
mecanismo de comunicação não a envia de novo.

**Por isso, toda escrita direta no banco — `INSERT`, `UPDATE` ou soft delete via `apagado='S'` —
precisa marcar `lojas_leram = '*'` na mesma operação.** O `*` significa "nenhuma loja leu ainda",
e é o que faz a alteração ser propagada.

```sql
UPDATE grupo_preco_produto
SET    preco_vnd  = 105.24,
       lojas_leram = '*'          -- sem isto, a loja nunca recebe a alteração
WHERE  produto_id = 12345
  AND  grupo_preco_id = 7;
```

A falha aqui é silenciosa e cara de diagnosticar: **o `UPDATE` retorna sucesso, a retaguarda mostra
o valor novo, e a loja continua operando com o valor antigo indefinidamente.** Não há erro, não há
log, e o sintoma chega como "mudei o preço no sistema e o caixa continua cobrando o valor velho" —
horas ou dias depois, já sem ligação óbvia com a alteração.

Regras práticas:

- Vale para **qualquer** tabela que o ERP replique, não só as de preço. Na dúvida sobre uma tabela
  específica, confirme se ela tem a coluna antes de escrever:
  `SHOW COLUMNS FROM <tabela> LIKE 'lojas_leram';`
- Vale também para exclusão. O ERP faz soft delete — a linha marcada com `apagado='S'` só some da
  loja se ela for replicada, ou seja, se `lojas_leram` for reposto para `'*'` junto.
- Numa alteração em lote, inclua a coluna no mesmo `UPDATE`. Um segundo `UPDATE` só para marcar
  `lojas_leram` deixa uma janela em que parte das linhas propaga e parte não.
- Ao revisar um script de escrita de outra pessoa, procure `lojas_leram` antes de qualquer outra
  coisa — é a omissão mais comum e a de sintoma mais tardio.

> 📌 Lacuna: o formato completo aceito por `lojas_leram` (se além de `'*'` ela guarda lista de
> códigos de loja, e qual o delimitador) ainda não está documentado aqui. Para escrita, o `'*'` é o
> valor correto; para *interpretar* o conteúdo existente de uma linha, confirmar na base antes.

---

## Regra de documentação contínua

Sempre que uma tabela, coluna, relacionamento ou padrão de query novo do ERP for descoberto,
documentá-lo imediatamente. Regra do projeto de origem: **um bug corrigido mas não documentado
volta a ser reintroduzido ou re-diagnosticado do zero.** Formato mínimo de registro:
sintoma → causa raiz confirmada (não suposta) → correção → como evitar → data/contexto.

**Em caso de dúvida sobre regra de negócio, PERGUNTAR antes de inventar.** Definição de métrica,
escopo de filtro, tipo de agregação (bruto x líquido, cupons x linhas), ordenação padrão e
comportamento de vazio nunca devem ser chutados.

---

## Exemplo de uma instalação (confirmar na base do cliente)

> **Nada nesta seção é regra do ERP Big.** São valores de **uma** instalação, mantidos só para
> mostrar o **formato** do dado. Ids, nomes, quantidades e parâmetros mudam de cliente para
> cliente — sempre consultar o banco do cliente antes de usar qualquer valor daqui.

### Mapa de filiais de uma rede

| filial_id | reduz | Observação |
| --- | --- | --- |
| 1 | ESCRITORIO | Não é filial de venda — excluída das queries |
| 2 | MATRIZ | Filial principal dessa rede |
| 3 | FILIAL 1 | |
| 4 | FILIAL 2 | |
| 5 | FILIAL 3 | |
| 6 | FILIAL 4 | |
| 8 | FILIAL 5 | |
| 9 | FILIAL 6 | |
| 11 | FILIAL 7 | |
| 12 | FILIAL 8 | |
| 13 | FILIAL 9 | |
| 14 | FILIAL 10 | Filial de origem das vendas "Loja WhatsApp" nessa rede (ver `05-clientes-crm.md`) |
| 15 | FILIAL 11 | |
| 999 | (nulo) | Registro técnico — excluído das queries |

Serve para ilustrar dois pontos que se repetem em outras instalações: **há buracos na sequência de
`filial_id`** (7 e 10 não existem aqui) e **o número no `reduz` não bate com o id** (`filial_id =
12` é `FILIAL 8`). Nessa instalação são **12 filiais operacionais** (todas exceto `filial_id = 1`)
— em outro cliente esse número é outro; contar com a query da seção de filiais.

### Convenção de papéis em `usuario.num_carteira`

Nessa instalação o campo livre "Número da Carteira" é preenchido à mão com o texto exato `GESTOR`
ou `OPERADOR CAIXA` para marcar o papel do funcionário. **É convenção do cliente, não semântica do
ERP.** Consulta usada ali para sugerir papéis por filial:

```sql
SELECT usuario_id, nome, filial_id
FROM usuario
WHERE UPPER(TRIM(num_carteira)) = 'GESTOR'      -- ou = 'OPERADOR CAIXA'
  AND apagado = 'N' AND status = 'S'
```

Em outro cliente o campo pode estar vazio, ter número de carteira de verdade ou usar outros
rótulos — verificar os valores distintos antes de assumir.

### Marca própria — `produto.espec_id`

`produto.espec_id` é a especificação do produto (isso é do ERP). **Qual `espec_id` corresponde à
marca própria é cadastro do cliente.** Nessa instalação, `espec_id = 257001` agrupa os produtos da
marca própria da rede, e a métrica "Marca" dos relatórios é `SUM(quanti_uni)` desses produtos — o
que ilustra o formato: um único `espec_id` inteiro, não uma lista de descrições.

### Programa de fidelidade / desconto à vista

O percentual gravado em `grupo_preco_produto.desconto` (ver `04-precos-ofertas.md`) é vendido ao
consumidor sob um **nome comercial próprio de cada rede** ("clube", "cartão", etc.). O nome não
existe no banco — não procurar por ele, e não usá-lo em documentação genérica.

### Parâmetros de negócio de caixa (fora do ERP)

Tolerâncias e faixas de premiação descritas em `06-financeiro-caixa.md` (R$ 1,70 / R$ 0,76,
90%–99,99% → R$ 70, ≥ 100% → R$ 100) são **configuração de uma instalação**, mantida fora do ERP.
O que é reaproveitável é a **estrutura** (duas tolerâncias independentes, faixas por percentual de
acerto), não os números.
