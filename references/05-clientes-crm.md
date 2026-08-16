# Clientes, R.F.V., WhatsApp, Entregas e Troco

Sumário:

- [Tabela `clientes`](#tabela-clientes)
- [Duplicidade de cadastro por CPF](#duplicidade-de-cadastro-por-cpf)
- [Vendas não identificadas](#vendas-não-identificadas)
- [Perfil R.F.V. (Recência, Frequência, Valor)](#perfil-rfv-recência-frequência-valor)
- [Vendas por WhatsApp — `orcament.msgcaixa`](#vendas-por-whatsapp--orcamentmsgcaixa)
- [Entregas](#entregas)
- [Troco de entrega — `pagamentos.troco_entrega`](#troco-de-entrega--pagamentostroco_entrega)
- [Convênios / PBM / Farmácia Popular / Crediário](#convênios--pbm--farmácia-popular--crediário)

---

## Tabela `clientes`

| Coluna | Descrição |
| --- | --- |
| `clientes_id` | PK do **cadastro** (não do cliente-pessoa — ver abaixo) |
| `nome` | Nome |
| `chapa` | Cartão |
| `cpf` | CPF (pode vir sentinela / repetido entre cadastros) |
| `celular` | Celular |
| `telefone1` | Telefone 1 |
| `telefone2` | Telefone 2 |
| `dtcadastro` | Data de cadastro — **usa sentinela `1000-01-01`** (ver abaixo) |

### `dtcadastro` com sentinela `1000-01-01`

Confirmado direto no ERP: **4.294 clientes** têm `dtcadastro = '1000-01-01'` — valor sentinela
para "data de cadastro desconhecida" (provavelmente registros migrados de sistema anterior).

Qualquer cálculo de "tempo de relacionamento" deve tratar **qualquer `dtcadastro` anterior a
`1990-01-01` como ausente (`NULL`)**. Sem essa guarda, o cliente aparece com ~374.955 dias de
relacionamento (mais de 1000 anos) e passa indevidamente em qualquer limiar de fidelidade.

---

## Duplicidade de cadastro por CPF

**`clientes.clientes_id` não é a mesma coisa que "cliente real".** A mesma pessoa pode ter vários
cadastros (`clientes_id` diferentes) com o mesmo CPF — cadastros feitos em filiais diferentes,
variações de grafia, cadastro familiar.

Números confirmados no ERP (2026-08-06): **4.818 CPFs válidos** (excluindo sentinelas tipo
`00000000000`) têm mais de um `clientes_id` — **9.867 cadastros duplicados** ao todo.

Exemplo real validado: CPF `42959365020` tem 4 cadastros (`10294`, `350622`, `350703`, `1440005`
— nomes com variações de grafia da mesma família). Somados nos últimos 365 dias: **R$ 13.717,51 e
73 cupons**. O `clientes_id = 10294` sozinho: R$ 12.605,42 e 63 cupons — **faltavam R$ 1.112,09 e
10 cupons** dos outros 3 cadastros.

**Consequência:** qualquer `SUM`/`COUNT`/`GROUP BY m.clientes_id` puro **subestima** o total da
pessoa. Padrão correto:

1. Para cada `clientes_id` das vendas do relatório, buscar os "cadastros-irmãos" que compartilham
   o mesmo CPF válido:
   ```sql
   SELECT clientes_id, cpf FROM clientes WHERE cpf IN (...)
   ```
2. Normalizar o CPF (11 dígitos; **nunca** considerar sentinela como `11111111111`).
3. Expandir a consulta de Valor Total / Ticket Médio / Cupons para incluir esses cadastros-irmãos
   (mesmo que eles nunca apareçam nas linhas do relatório — a pessoa pode ter comprado outro
   produto/filial sob o outro cadastro).
4. Somar por grupo de CPF antes de atribuir de volta a cada `clientes_id` original.

**Cuidado com falso-positivo:** nem todo CPF compartilhado é a mesma pessoa. Caso real: CPF
`02864824019` com nomes completamente diferentes entre si — provavelmente um CPF genérico
reaproveitado por atendentes para clientes sem CPF na mão. Essa é uma limitação aceita
conscientemente pelo gestor (o módulo R.F.V. já convive com ela) — replicá-la é consistente com o
resto do sistema, não um risco novo.

**Performance:** ao filtrar `movment` por cliente, usar sempre
`FROM movment m FORCE INDEX (clientes_id)` — sem o hint o otimizador faz full scan (42s → 60ms com
o hint).

---

## Vendas não identificadas

Venda sem cliente identificado = `movment.clientes_id = 0`. Antes de construir um indicador de
"vendas não identificadas", confirmar com o gestor: inclui devoluções? conta cupons ou produtos?
exclui `ARREDOND` (sim, sempre)? — não assumir.

---

## Perfil R.F.V. (Recência, Frequência, Valor)

**Nada disso é do ERP Big.** A regra foi obtida por engenharia reversa de um CRM externo e
validada com dados reais; o cálculo é **derivado** e vive fora do ERP. Os limiares e o
recorte são configuração de projeto — em outro cliente podem ser outros.

### Regra central: calculado em LOTE (rede toda), nunca ao vivo

- O cálculo roda para a **rede inteira de uma vez** e o resultado fica cacheado fora do ERP. A
  tela nunca recalcula ao abrir um cadastro — só lê o último resultado gravado.
- **Entidade de cliente = CPF normalizado** (11 dígitos, descartando sequências repetidas tipo
  `00000000000`). Dois `clientes_id` diferentes com o mesmo CPF, mesmo em filiais diferentes, são
  **o mesmo cliente** e têm o histórico somado. Sem CPF válido, cada `clientes_id` vira sua
  própria entidade isolada (chave `SEM_CPF_<clientes_id>`).
- **Processado filial por filial, sequencialmente** — nunca uma query cruzando a rede inteira de
  uma vez (mesmo padrão validado para a Diferença de Fechamento). Uma filial que falhar é pulada,
  sem abortar o lote.
- **Ordem de grandeza medida numa instalação real** (rede inteira, 12 filiais operacionais):
  ~**62.184 entidades ativas** (compraram nos últimos 365 dias); lote completo em **~16–40s**.
  Serve para dimensionar, não como número esperado em outro cliente.
- **Concorrência:** um novo disparo deve ser bloqueado enquanto houver execução em andamento há
  menos de 20 minutos — evita dois lotes simultâneos martelando o pool de conexões do ERP.

### Scores

Score por **quintil** implementado como `NTILE(6)` sobre a base ativa do lote — score `0` = pior
sexto, score `5` = melhor sexto.

> **Marcado como incerto na fonte:** a spec fala em "5 grupos de tamanho igual (quintis)", mas os
> exemplos concretos de corte (ex.: Recência `5 = até 11 dias` … `0 = mais de 263 dias`) e a tabela
> de classificação (que usa `R ∈ {4,5}` e `FM ≥ 4` como tetos) só fecham com **6 grupos**
> (score 0 a 5). A implementação usa 6 bandas; a leitura não foi validada contra o CRM original.

### Segmentos (conjunto fechado de 11)

`Campeão`, `Fidelizado`, `Promissor`, `Potencial para ser fidelizado`, `Recente`, `Em risco`,
`Não pode perder`, `Precisa de atenção`, `Quase hibernando`, `Hibernando`, `Perdido`.

O segmento **"Recente"** (R alto + FM baixo) foi implementado por simetria com "Promissor" e
**nunca foi validado** com um cliente real nesse segmento — incerto.

### Tags de fidelização — Fiel / Potencial (limiares editáveis)

Defaults de **uma** instalação (parâmetro de negócio do cliente, não regra do ERP):

| Tag | Critérios (todos) |
| --- | --- |
| **Fiel** | tempo de relacionamento ≥ **180 dias**, ≥ **4 vendas em 6 meses**, recência ≤ **60 dias**, gasto em 6 meses ≥ **R$ 300** |
| **Potencial** | recência ≤ **45 dias**, gasto em 6 meses ≥ **R$ 200** (só testado se não for Fiel) |

Os limiares nunca devem ficar hardcoded — são configuráveis, e cada cliente define os seus.

### Loja Favorita / Vendedor Favorito

Maior número de transações. **Desempate** (mesma quantidade): valor total gasto, depois
`filial_id`/`usuario_id` menor (determinístico) — **sem caso real testado, incerto**.

### Contagem de "venda/transação"

Implementada como `COUNT(DISTINCT numlanc)` **dentro de cada filial** (mesmo padrão de "contar
cupons"). Não foi comparada especificamente contra a definição do CRM de origem — incerto.

---

## Vendas por WhatsApp — `orcament.msgcaixa`

### O que é a "Loja WhatsApp"

**Não existe filial "WhatsApp" no ERP.** São vendas de uma filial específica cujo orçamento foi
marcado no caixa com um código combinado em **`orcament.msgcaixa`** — campo de **texto livre
digitado pelo operador**.

> **Específico do cliente:** tanto os códigos usados (`wt`, `wr`, `ct`, `cr` na instalação em que
> isso foi validado) quanto a filial de origem (`filial_id = 14`, `reduz` "FILIAL 10", naquela
> rede) são convenção da rede, não do ERP. Confirmar os dois na base do cliente:
> `SELECT DISTINCT msgcaixa FROM orcament WHERE msgcaixa <> ''`. O que é universal é o
> comportamento do campo — texto livre, sujo, que exige normalização.

Regras da consulta de origem (transformação Pentaho/Kettle, replicada e validada):

- Busca os `numlanc` com **2 dias de folga antes** do início do período (o orçamento pode ter sido
  aberto antes do fechamento da venda).
- Exige `orcament.status IN ('F','N')` e `numlanc <> 0`.

### `msgcaixa` é texto livre — nunca comparar sem normalizar

Como o operador digita e às vezes dá Enter, parte relevante dos registros vem com **quebra de
linha** no fim (`"WT\r\n"`, hex `57540D0A`) ou com o código repetido (`"wtwt"`). O padding
automático do MySQL cobre **espaços**, não `\r`/`\n` — então `msgcaixa IN ('wt','wr','ct','cr')`
devolve `0` para esses registros e a venda inteira desaparece.

Medido em 2026-08-07 na filial de origem daquela rede, ano de 2026: **17.264 registros limpos**
contra **236 perdidos** (211 com `\r\n`, 18 `"wtwt"`, 4 `"wyt"`, 3 `"wf"`). Num recorte de 6 dias
(01–06/08/2026): **129 cupons / R$ 16.669,83** (comparação exata) contra **145 cupons /
R$ 18.395,50** (normalizado) — **9,4% da venda sumindo**.

**Sempre normalizar antes de comparar:**

```sql
LOWER(TRIM(REPLACE(REPLACE(orc.msgcaixa, '\r', ''), '\n', '')))
```

### Dois recortes diferentes que convivem de propósito

Numa mesma instalação podem conviver dois recortes diferentes de "venda por WhatsApp", e trocar um
pelo outro muda o número:

| Recorte | Regra |
| --- | --- |
| Recorte **completo** | `msgcaixa` normalizado ∈ (todos os códigos combinados), `orcament.status IN ('F','N')`, `numlanc <> 0`, 2 dias de folga, filial de origem |
| Recorte **legado** (relatórios mais antigos) | só `msgcaixa LIKE '%<código>%'` — um código só, sem folga de 2 dias, sem filtro de `status` |

O `LIKE '%…%'` por acaso **não sofre** do problema do `\r\n` (o `%` absorve), mas em compensação
casa o código repetido (`"wtwt"`) e ignora os demais códigos. **São recortes diferentes — não
trocar um pelo outro sem confirmar com o cliente qual é o esperado naquele relatório.**

### Loja WhatsApp — colunas e fórmulas validadas

| Coluna | Fórmula |
| --- | --- |
| Desconto | desconto **manual** (`tipo_desc = 'M'`) ÷ venda bruta — **não** é `(bruto − líquido)/líquido` |
| Venda | `SUM(valor_tot)` (líquido) |
| Cupons | `COUNT(DISTINCT filial_id, numlanc)` |
| Ticket | venda líquida ÷ cupons |
| Referência / Perfumaria / Genérico / Outros | `SUM(valor_tot)` por listas fixas de `produto.grupo_id`, e o `%` sobre a venda líquida da própria linha |
| CMV | custo ÷ venda líquida, custo pela cascata `mov.pmc → mov.precoee → preco_medio_custo.pmc_atual → estoque_minimo.precoee → precosfilial.preco_custo → produto.preco_cmp_un` |
| Marca | `SUM(quanti_uni)` de produtos cujo `produto.espec_id` corresponde à marca própria da rede — **o valor do `espec_id` é cadastro do cliente** (ver `01-visao-geral.md`, "Exemplo de uma instalação") |
| Unidades | itens vendidos ÷ cupons |

**Duas consultas separadas** (vendedores e total) — nunca somar a tabela de vendedores para obter
o total (cupom compartilhado entre vendedores; ver `02-vendas-movment.md`).

---

## Entregas

Colunas em `movment`: `entrega` (`'S'`/`'N'`), `dtsaida_entrega` (despacho),
`dtchegada_entrega` (confirmação de chegada).

- Recorte padrão de venda com entrega: `(mov.entrega = 'N' OR mov.dtchegada_entrega IS NOT NULL)`
  — a tele-entrega só entra no relatório **depois** de a chegada ser confirmada.
- Enquanto `dtchegada_entrega IS NULL`, a entrega está a caminho.

---

## Troco de entrega — `pagamentos.troco_entrega`

**`pagamentos.troco_entrega = 'S'` marca um troco PENDENTE de entrega, e o valor negativo dessa
linha NETA A ZERO assim que a entrega é finalizada.** Nunca usar
`SUM(valor) WHERE troco_entrega = 'S'` sozinho para saber "quanto de troco tem essa venda".

Fluxo real observado (lançamento 889722, "Filial 9" como registrado na fonte — se é `reduz` ou
`filial_id` não está confirmado, 2026-07-23):

| Estágio | Linhas gravadas em `pagamentos` |
| --- | --- |
| **Despacho** (`dtsaida_entrega`) | 1 linha: `valor = -26.00`, `troco_entrega = 'S'` (o "troco a levar" declarado) |
| **Chegada confirmada** (`dtchegada_entrega` preenchido) | linha de reversão `valor = +26.00, troco_entrega = 'S'` (soma com a original e **zera** o `SUM(...WHERE troco_entrega='S')`), mais as duas linhas reais da transação com `troco_entrega = 'N'`: `valor = +150.00` (recebido em dinheiro) e `valor = -26.00` (troco efetivamente dado) |

Ou seja: **o mesmo lançamento tem sinais diferentes de troco dependendo do estágio da entrega.**

**Cálculo correto — pegar o maior entre os dois sinais:**

- (a) **Pendente:** `ABS(SUM(valor) WHERE troco_entrega = 'S')` quando essa soma for negativa.
- (b) **Liquidado:**
  `GREATEST(0, SUM(valor) WHERE tipospgto_id = 1 (DINHEIRO) AND troco_entrega = 'N' AND valor > 0) - valor_tot_da_venda`.

Usar `GREATEST` dos dois cobre a entrega em qualquer estágio, sem ramificar por
`dtchegada_entrega`.

**Como evitar recorrência:** ao usar `troco_entrega` em qualquer relatório novo, **nunca validar
só com uma entrega ainda em andamento** (`dtchegada_entrega IS NULL`) — o comportamento muda
depois que ela é confirmada. Testar os dois estágios antes de publicar.

---

## Convênios / PBM / Farmácia Popular / Crediário

A fonte tem pouca informação estruturada sobre esses temas — o que existe:

- **PBM** aparece como uma **flag `'S'`/`'N'`** em relatórios (junto de "Tele"), tratada como
  coluna binária. **Tabela/coluna de origem não documentada — incerto.**
- **Farmácia Popular** aparece como um **motivo de alteração manual** na conferência de caixa do
  ERP: `conf_caixa_loja_tipospgto.motivo_alteracao = 'popular'` (o operador corrige o valor
  apurado/computado daquela forma de pagamento na hora da conferência). Nenhuma tabela dedicada de
  Farmácia Popular está documentada na fonte — **lacuna**.
- **Crediário / fiado** = `movment.oper = 9`; existe como forma de pagamento `CREDIARIO` em
  `tipospgto` e, em algumas filiais, está marcado `tipospgto_sangria.efetua_sangria = 'S'` —
  o que contamina a fórmula antiga de diferença de caixa (ver `06-financeiro-caixa.md`).
- **Receituário / controlados:** o campo `produto.receita` (`'S'`/`'N'`) indica produto de
  receituário, e `movment.oper = 3` é "venda com receita". Nenhuma tabela de receituário,
  controlados ou **SNGPC** está documentada na fonte — **lacuna**.
