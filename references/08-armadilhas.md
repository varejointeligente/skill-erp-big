# Catálogo de Armadilhas e Bugs Reais do ERP Big

Cada item: **sintoma → causa → correção → como evitar**. Todos vieram de casos concretos, com dado
real do ERP — o caso é o que ensina.

Sumário por área:

- [Chaves e fan-out](#chaves-e-fan-out)
- [Semântica de colunas](#semântica-de-colunas)
- [Filtros e recortes de venda](#filtros-e-recortes-de-venda)
- [Preço](#preço)
- [Caixa e conferência](#caixa-e-conferência)
- [Cliente](#cliente)
- [Performance](#performance)
- [Camada de aplicação (BigInt, fuso, SQL dinâmico)](#camada-de-aplicação-bigint-fuso-sql-dinâmico)
- [Escrita e replicação](#escrita-e-replicação)

---

## Escrita e replicação

### 0. `UPDATE`/`INSERT` sem `lojas_leram = '*'` — a alteração nunca chega à loja

- **Sintoma:** o registro é alterado com sucesso, a retaguarda mostra o valor novo, e a loja
  continua operando com o valor antigo por tempo indeterminado. Chega como "mudei no sistema e o
  caixa continua cobrando o preço velho", normalmente horas ou dias depois da alteração.
- **Causa:** o ERP Big é distribuído entre retaguarda e lojas, e a replicação é controlada pela
  coluna `lojas_leram` **na própria linha alterada** — ela marca quais lojas já leram o registro.
  Uma escrita que não mexe nessa coluna deixa a linha marcada como "já lida por todos", então o
  mecanismo de comunicação simplesmente não a envia.
- **Correção:** marcar `lojas_leram = '*'` (nenhuma loja leu ainda) **na mesma operação** de
  escrita — inclusive em soft delete:

  ```sql
  UPDATE grupo_preco_produto
  SET    preco_vnd   = 105.24,
         lojas_leram = '*'
  WHERE  produto_id = 12345 AND grupo_preco_id = 7;
  ```

- **Como evitar:** tratar `lojas_leram = '*'` como parte obrigatória de qualquer `INSERT`,
  `UPDATE` ou `apagado='S'`, nunca como um segundo passo (um `UPDATE` separado abre janela em que
  parte das linhas propaga e parte não). Ao revisar script de escrita alheio, procurar essa coluna
  antes de qualquer outra coisa: é a omissão mais frequente e a de sintoma mais tardio, o que torna
  o diagnóstico caro. Se a tabela for incomum, confirmar que ela tem a coluna:
  `SHOW COLUMNS FROM <tabela> LIKE 'lojas_leram';`

---

## Chaves e fan-out

### 1. `caixas_id` tratado como globalmente único

- **Sintoma:** um caixa da FILIAL 2 (`caixas_id = 24653`) mostrava "Sobrou R$ 32,29"; o valor real,
  confirmado por outro relatório que filtra corretamente, era "Faltou R$ 0,22".
- **Causa:** a query em lote usava `FIND_IN_SET(cx.caixas_id, idsCsv)` sem `filial_id`. O mesmo
  `caixas_id` existe em outras filiais (2, 4 e 6 simultaneamente) — pagamentos de caixas de outras
  2 filiais entravam na soma.
- **Correção:** `(cx.filial_id, cx.caixas_id) IN ((f1,c1),(f2,c2),...)` (row constructor, suportado
  no MariaDB), ou `filial_id = X AND caixas_id = Y` para um único caixa.
- **Como evitar:** a PK real de `caixas` é **composta**. Nunca casar caixas só por `caixas_id`.

### 2. `entradas_id` reaproveitado entre produtos/filiais

- **Sintoma:** uma entrada real de 1 unidade (produto 828555, `entradas_id = 133876`) aparecia como
  2 na tela.
- **Causa:** `entradas.entradas_id` não é único por produto/filial — o mesmo valor apontava para o
  produto 828555 na filial 6 **e** o produto 812408 na filial 11. `JOIN entradas e ON e.entradas_id
  = mov.entradas_id` fazia fan-out.
- **Correção:** completar o JOIN com `AND e.produto_id = mov.produto_id AND e.filial_id =
  mov.filial_id`.
- **Como evitar:** tratar a chave de `entradas` como composta.

### 3. `LEFT JOIN barras` inflando agregados

- **Sintoma:** entrada real de 3 unidades exibida como 12.
- **Causa:** o produto 5728 (TINT KOLESTON 6.0 LOUR ESCURO) tem **4 códigos de barras ativos**
  (`apagado = 'N'`). O `LEFT JOIN barras` transforma 1 linha de `movment` em 4, multiplicando todos
  os `SUM`/`COUNT` da query.
- **Correção:** subquery escalar
  `COALESCE((SELECT MIN(b2.barras) FROM barras b2 WHERE b2.produto_id = p.Produto_id AND b2.apagado='N'), p.barras)`.
- **Como evitar:** nunca joinar `barras` numa query que tenha agregados.

---

## Semântica de colunas

### 4. `movment.estoque` em ENTRADA é o saldo ANTES, não depois

- **Sintoma:** relatório de reposição marcava como "estoque zerado antes da entrega" produtos que
  já tinham estoque positivo.
- **Causa:** a fórmula usada era `mov.estoque - mov.quanti_uni <= 0`. Em registros de entrada
  (`E_S = 'E'`, com `entradas_id`), `estoque` **já é** o saldo anterior à entrada — subtrair de
  novo cria saldo negativo artificial. Em vendas/saídas, `estoque` é o saldo **depois**.
- **Correção:** usar o valor da coluna diretamente, sem subtração. Confirmado com dado real:
  produto 106447, `movment_id` 13323679, entrada de 16 un. em 16/06 13:13, `estoque = 5` gravado,
  virando 21 depois.
- **Como evitar:** lembrar que a semântica de `estoque` inverte entre `E_S = 'E'` e `E_S = 'S'`.

### 5. `produto.receita` usado como grupo/categoria

- **Sintoma:** categorização de produto sem sentido.
- **Causa:** `produto.receita` é campo de **receituário** (`'N'`/`'S'`), não categoria.
- **Correção:** categoria vem de `grupo` (join `produto.grupo_id = grupo.grupo_id`), com
  `grupo.desc_arvore` para a hierarquia.
- **Como evitar:** nomes parecidos não indicam mesma semântica — confirmar no cadastro do ERP.

### 6. `estoque_minimo.compra_suspensa` como fonte de suspensão

- **Sintoma:** o setor de Compras reportou que um produto listado como "abaixo da demanda" estava
  na verdade com compra suspensa numa das filiais.
- **Causa:** `estoque_minimo.compra_suspensa` existe, mas **não é mantida** nesta base — fica
  sempre `'N'`. Confirmado: `'N'` em todas as filiais do produto, enquanto
  `produtos_suspensos_compra.compra_suspensa = 'S'` (`apagado = 'N'`) na filial do caso.
- **Correção:** usar `produtos_suspensos_compra` (tabela dedicada, com justificativa e período);
  `precosfilial.comprasuspensa` reflete o mesmo dado, sincronizado.
- **Como evitar:** suspensão de compra é **por filial** — verificar filial a filial, não o produto
  como um todo.

### 7. `entradas.curvaabc` usada como curva atual

- **Sintoma:** curva divergente da curva de venda atual.
- **Causa:** em `entradas`, a curva fica gravada **historicamente**, no momento da entrada.
- **Correção:** usar `curvaabc` (`produto_id`, `filial_id`, `curvaabc`, `curvaabc_est`).
- **Como evitar:** não usar `entradas.curvaabc` para relatórios de estoque/compras.

### 8. Tabela `lote` (antiga) usada para estoque atual

- **Sintoma:** quantidades zeradas / dados só até 2015.
- **Causa:** `lote` é a tabela antiga, com `estoque` e `qtde` zerados.
- **Correção:** usar `lote_novo` (join `ln.fillogica_id = fil.filial_id`, validade em `validade`,
  quantidade em `estoque`), filtrando `ln.validade < '2100-01-01'`.
- **Como evitar:** "existe uma tabela com esse nome" não significa que ela está viva.

---

## Filtros e recortes de venda

### 9. `oper` sem `IN (2,3)`

- **Sintoma:** faturamento inflado/deflacionado por movimentos que não são venda.
- **Causa:** `movment.oper` cobre devoluções, ajustes, transferências (`10`), fiado (`9`),
  sangria/suprimento (`8` em `pagamentos`).
- **Correção:** `mov.oper IN (2, 3)` junto de `apagado = 'N' AND cancelado = 'N'`.
- **Como evitar:** o filtro canônico de venda válida é indivisível — copiar inteiro.

### 10. Produto de arredondamento entrando nos KPIs

- **Sintoma:** faturamento, contagem de clientes e IPC ligeiramente errados.
- **Causa:** produtos com `descricao LIKE '%ARREDOND%'` existem só para ajustar troco.
- **Correção:** `AND mov.produto_id NOT IN (SELECT Produto_id FROM produto WHERE descricao LIKE '%ARREDOND%')`.
- **Como evitar:** incluir essa exclusão em **toda** query de vendas, sem exceção.

### 11. `orcament.msgcaixa` comparado com `IN`/`=` sem normalizar

- **Sintoma:** o lançamento 336301 da FILIAL 10 não aparecia no relatório; 9,4% da venda do
  recorte sumindo.
- **Causa:** `msgcaixa` é **texto livre digitado no caixa**. Parte dos registros vem com quebra de
  linha (`"WT\r\n"`, hex `57540D0A`) ou código repetido (`"wtwt"`). O padding automático do MySQL
  cobre **espaços**, não `\r`/`\n` — então `msgcaixa IN ('wt','wr','ct','cr')` devolve `0`.
  Medido (FILIAL 10, ano de 2026): **17.264 limpos vs. 236 perdidos** (211 `\r\n`, 18 `"wtwt"`,
  4 `"wyt"`, 3 `"wf"`). Num recorte de 6 dias: 129 cupons/R$ 16.669,83 vs. 145 cupons/R$ 18.395,50.
- **Correção:** `LOWER(TRIM(REPLACE(REPLACE(msgcaixa, '\r', ''), '\n', '')))` antes de comparar.
- **Como evitar:** todo campo de texto livre digitado no caixa precisa ser normalizado antes de
  comparação exata. (`LIKE '%WT%'` não sofre do `\r\n`, mas casa `"wtwt"` e ignora `wr`/`ct`/`cr` —
  é **outro recorte**, não um substituto.)

### 12. Somar a tabela por vendedor para obter o total de cupons

- **Sintoma:** total de cupons diferente do valor oficial (147 vs. 145 num recorte de 6 dias).
- **Causa:** um mesmo cupom pode ter itens lançados por **vendedores diferentes** — na visão por
  vendedor ele conta uma vez para cada um.
- **Correção:** rodar uma **segunda consulta** agregada para o total; nunca reduzir a lista de
  vendedores.
- **Como evitar:** o valor em R$ bate nas duas visões, só a contagem de cupons diverge — por isso o
  erro passa despercebido em conferência superficial.

### 13. Tele-entrega contabilizada antes da chegada

- **Sintoma:** venda aparecendo/sumindo do relatório entre duas execuções.
- **Causa:** a regra do recorte é `(mov.entrega = 'N' OR mov.dtchegada_entrega IS NOT NULL)` — a
  entrega só entra depois de confirmada a chegada.
- **Correção/como evitar:** manter a regra e explicá-la na tela, para não virar dúvida recorrente.

---

## Preço

### 14. Preço calculado por `preco_cmp_un × (1 + margem/100)`

- **Sintoma:** CITALOPRAM 20MG exibido a R$ 86,67 em vez de R$ 105,24 (2026-07-06).
- **Causa:** `produto.preco_cmp_un` e `produto.margem` podem estar defasados.
- **Correção:**
  `COALESCE(NULLIF(gpp.preco_vnd, 0), ROUND(p.preco_cmp_un * (1 + p.margem/100), 2))` — a fórmula
  do `produto` só como fallback.
- **Como evitar:** `grupo_preco_produto.preco_vnd` é a **única** fonte verdadeira do preço de
  venda atual.

### 15. Desconto à vista lido de `produto.desconto_avista`

- **Sintoma:** desconto sempre 0.
- **Causa:** `produto.desconto_avista` costuma ser 0 nesta base.
- **Correção:** usar `grupo_preco_produto.desconto`, aplicado **sempre sobre `preco_vnd`**:
  `preco_vnd × (1 − desconto/100)`.
- **Como evitar:** desconto nunca incide sobre custo nem sobre preço promocional.

### 16. Promoção expirada exibida como preço vigente

- **Sintoma:** preço promocional fora do período.
- **Causa:** uso de `preco_pro` sem checar `dtiniciopromocao`/`valid_pro`.
- **Correção:** exigir `NOW() BETWEEN gpp.dtiniciopromocao AND gpp.valid_pro` e
  `COALESCE(preco_pro,0) > 0`.
- **Como evitar:** quando promoção por data **e** desconto à vista estão ativos, vale a promoção —
  o desconto à vista é **ignorado**, nunca somado.

---

## Caixa e conferência

### 17. CREDIARIO contaminando a Diferença de Fechamento

- **Sintoma:** Caixa ID 30242 (FILIAL 4, `filial_id = 6`) exibido como "Sobrou R$ 0,08" enquanto a
  tela nativa do ERP e o relatório impresso mostravam "Sobrou R$ 15,05".
- **Causa:** a fórmula "Movimentos + Suprimentos − Sangrias" somava **todas** as formas marcadas
  `tipospgto_sangria.efetua_sangria = 'S'`, agrupando só por `caixas_id`. Na FILIAL 4 o CREDIARIO
  também está marcado assim; uma venda fiado (`oper = 9`, R$ 14,97) sem sangria pareada
  contaminava a soma (DINHEIRO: −15,05; CREDIARIO: +14,97; soma cega: −0,08).
- **Correção:** ler a diferença **oficial** de `conf_caixa_loja_tipospgto`
  (`SUM(valor_computado - valor_apurado)` da conferência mais recente não-apagada do caixa,
  `apagado = 'N'`). Bateu 100% com o papel impresso.
- **Como evitar:** **nunca** recalcular Mov.+Sup.−Sangrias sobre `pagamentos` para obter esse
  número. Caixa sem conferência rodada no ERP fica **em branco**, nunca com valor estimado. O
  detalhamento **por forma de pagamento** (diagnóstico de "possível causa") continua sendo
  calculado de `pagamentos`, porque não existe equivalente agregado.

### 18. `caixa_dia` usado como prova exata contra papel impresso

- **Sintoma:** sessão `caixas_id = 55732` (MATRIZ, 13/07/2026, horários batendo exatamente com o
  papel) gravada como `caixa_dia = 6`, mas o comprovante impresso mostra "N.Caixa Dia: 5".
- **Causa:** o contador impresso reflete o estado do ERP no momento do fechamento; se alguma
  abertura não deixou (ou não deixa mais) linha na tabela — abertura cancelada, hard delete —, o
  papel fica 1 à frente.
- **Correção/como evitar:** usar `caixa_dia` para reconstruir a **ordem relativa** das sessões do
  dia, com margem de ±1 contra papel antigo.

### 19. Sinal fixo em controle "reduz/aumenta" sobre valor já assinado

- **Sintoma:** caixa com "Sobrou R$ 9,87"; correção de R$ 10,00 marcada como "reduz a diferença"
  resultou em "Sobrou R$ 19,87" — a diferença **aumentou**.
- **Causa:** o mapeamento era fixo ("reduz" sempre positivo) e o servidor faz
  `valor_ajustado = valor_original − soma(itens)`. Subtrair positivo de um "Faltou" (positivo)
  reduz; subtrair positivo de um "Sobrou" (negativo) **afasta de zero**.
- **Correção:** o sinal do item depende do sinal do `valor_original`
  (`sinalOriginal = valor_original < 0 ? -1 : 1`) — subtrair valor de **mesmo sinal** sempre
  aproxima de zero. O rótulo exibido também passa a ser **derivado**, comparando os sinais.
  Validado: caixa com Sobrou R$ 9,87 + "reduz R$ 10,00" → `0,13` → "Faltou R$ 0,13".
- **Como evitar:** sempre testar o toggle nos **dois sentidos** do valor de referência (um caixa
  com Faltou e um com Sobrou).

### 20. Ruído de ponto flutuante em valor monetário somado fora do SQL

- **Sintoma:** campo pré-preenchido com `9,940000000000055` em vez de `9,94`.
- **Causa:** soma/subtração de `Decimal`/string do MariaDB convertidos para número em JS. A
  formatação de exibição arredondava e mascarava o problema onde havia formatação — mas não no
  input nem no valor persistido.
- **Correção:** arredondar para 2 casas (`Math.round(v * 100) / 100`) tanto no cálculo exibido
  quanto no valor gravado.
- **Como evitar:** nunca confiar que a formatação de exibição cobre todos os consumidores do valor
  cru.

---

## Cliente

### 21. Agregar por `clientes_id` sem consolidar CPF

- **Sintoma:** "Valor Total (365d)", "Ticket Médio (365d)" e "Cupons (365d)" subestimados.
- **Causa:** a mesma pessoa tem vários cadastros com o mesmo CPF. Confirmado no ERP: **4.818 CPFs
  válidos com mais de um `clientes_id`, 9.867 cadastros duplicados**. Exemplo: CPF `42959365020`
  com 4 cadastros — R$ 13.717,51/73 cupons somados, contra R$ 12.605,42/63 cupons do
  `clientes_id = 10294` sozinho.
- **Correção:** buscar os cadastros-irmãos pelo CPF normalizado
  (`SELECT clientes_id, cpf FROM clientes WHERE cpf IN (...)`), expandir a consulta para incluí-los
  (mesmo que não apareçam nas linhas do relatório) e somar por grupo de CPF antes de atribuir de
  volta.
- **Como evitar:** qualquer relatório novo que agregue por `clientes_id` tem esse risco.
  **Falso-positivo conhecido:** nem todo CPF compartilhado é a mesma pessoa (caso real:
  `02864824019` com nomes completamente diferentes — CPF genérico reaproveitado por atendentes).

### 22. `clientes.dtcadastro` com sentinela `1000-01-01`

- **Sintoma:** clientes com ~374.955 dias de relacionamento (mais de 1000 anos), classificados
  como "Fiel" indevidamente.
- **Causa:** **4.294 clientes** têm `dtcadastro = '1000-01-01'` — sentinela de "data desconhecida"
  (registros migrados).
- **Correção:** tratar `dtcadastro < '1990-01-01'` como ausente (`NULL`), o que reprova o teste de
  tempo de relacionamento.
- **Como evitar:** aplicar guarda de faixa em **qualquer** data do ERP sem constraint conhecida —
  mesmo padrão de `lote_novo.validade < '2100-01-01'`.

### 23. Troco de entrega medido só num estágio

- **Sintoma:** a coluna Valor/Troco bateu no teste (R$ 150,00) e, minutos depois, a mesma query
  voltou 0.
- **Causa:** `pagamentos.troco_entrega = 'S'` marca troco **pendente**; ao confirmar a chegada
  (`dtchegada_entrega`), o ERP grava a **reversão** (`+26.00, troco_entrega='S'`) que zera o
  `SUM(...WHERE troco_entrega='S')`, mais as duas linhas reais com `troco_entrega='N'`
  (`+150.00` recebido e `−26.00` troco dado). Lançamento real: 889722, "Filial 9" (nome como
  registrado na fonte, não confirmado se é `reduz` ou `filial_id`), 2026-07-23.
- **Correção:** usar o **maior** entre (a) pendente `ABS(SUM(valor) WHERE troco_entrega='S')`
  quando negativo e (b) liquidado
  `GREATEST(0, SUM(valor) WHERE tipospgto_id=1 AND troco_entrega='N' AND valor>0) - valor_tot_da_venda`.
- **Como evitar:** nunca validar com uma entrega ainda em andamento e considerar pronto.

---

## Performance

### 24. `FORCE INDEX (prod_id)` + `IN()` grande devolvendo a mesma venda 2×

- **Sintoma:** ordenação por "Ticket Médio (365d)" saindo fora de ordem (vazio, vazio, preenchido,
  preenchido…). Investigação no ERP: a mesma venda (LOSARTANA POTASSICA, lançamento 1028230035)
  aparecia 3×; outra (HIDROCLOROTIAZIDA, lançamento 1028230792) 2×.
- **Causa:** **não** era duplicação na lista de `produto_id` (testado: repetir um id de propósito
  não duplicou nada). Com lista garantidamente única de ~40 ids + `data_hora BETWEEN` +
  `oper IN (2,3)` + `filial_id NOT IN (1,999)` em 2 meses, o plano do MariaDB devolveu 7
  `movment_id` duplicados. É comportamento real do otimizador para esse combo.
- **Correção:** deduplicar por `movment_id` na aplicação
  (`Array.from(new Map(mov.map(m => [m.movment_id, m])).values())`).
- **Como evitar:** toda rota que use `FORCE INDEX (prod_id)` com `IN()` de **múltiplos**
  `produto_id` deve deduplicar por `movment_id`.

### 25. Query cruzando muitos caixas de filiais diferentes trava

- **Sintoma:** relatório preso em "Buscando…"; teste com ~700 caixas passou de 2 min sem terminar.
- **Causa:** `pagamentos` **não tem índice em `numcaixa`**. Com `filial_id` e a janela de `datahora`
  como literais de UMA linha, o MariaDB usa `type: range` no índice `oper` (~1–2 ms); com múltiplos
  caixas (tupla `IN` ou tabela derivada geral) a constant-propagation se perde e cai para `ref` só
  em `filial_id` (~478 mil linhas candidatas por filial).
- **Correção:** agrupar por `filial_id` em memória e rodar **uma query por filial**, com
  `p.filial_id = <literal>`, `p.datahora BETWEEN '<min>' AND '<max>'`, `FORCE INDEX (oper)` e uma
  tabela derivada (`UNION ALL` de literais) só com os caixas daquela filial. Medido: 695 caixas em
  1,78s com 0 divergências; 1356 caixas em 2,5s.
- **Como evitar:** nunca concluir que "funcionou rápido para 1 caixa" significa que escala.

### 26. Fórmula pesada rodada sem limite de período trava o pool

- **Sintoma:** relatório preso por horas mesmo sem query nova sendo disparada.
- **Causa:** `SHOW PROCESSLIST` / `information_schema.INNODB_TRX` revelaram **6 queries travadas**,
  uma há mais de 4h27min, processando caixas de 2010/2016/2022/2023 — alguém rodou a fórmula com
  período ilimitado, gerando tabela derivada (`UNION ALL`) gigantesca. Com pool de **5 conexões** e
  **nenhum timeout de query**, cada travada prendia um slot para sempre.
- **Correção:** timeout de query de **45s** no cliente (o driver destrói a conexão presa e libera o
  slot); as travadas foram identificadas por thread id para `KILL` manual (são `SELECT`s
  read-only).
- **Como evitar:** nunca remover o timeout; considerar teto de dias no período; diagnosticar com
  `SHOW PROCESSLIST`/`INNODB_TRX` antes de teorizar; **nunca `KILL` sem confirmação humana** — é o
  banco de produção compartilhado por toda a rede.

---

## Camada de aplicação (BigInt, fuso, SQL dinâmico)

### 27. Replacer de `JSON.stringify` com um parâmetro só

- **Sintoma:** a API respondia `{"top20":"","empresa79":""}` em vez de arrays; o servidor logava
  `top20=15`.
- **Causa:** replacer escrito como `(v) => typeof v === 'bigint' ? ...`. `JSON.stringify` chama o
  replacer com `(key, value)`; na raiz a chave é `""`, então o array inteiro virava string vazia.
- **Correção:** `(_: string, v: unknown) => (typeof v === "bigint" ? v.toString() : v)`.
- **Como evitar:** olhar o **JSON cru** da resposta antes de teorizar sobre cache — esse passo
  elimina 95% das hipóteses falsas.

### 28. Filtro de data sem offset `-03:00`

- **Sintoma:** sangrias do dia 25/06 às 22h–23h apareciam numa busca do dia 26/06 00h–12h.
- **Causa:** servidor em UTC + driver com `timezone: '-03:00'` subtrai 3h do `Date` de JS. Sem
  offset explícito, o filtro chegava ao banco como 25/06 21:00:00.
- **Correção:** `` new Date(`${data}T${hora}-03:00`) `` (e `T00:00:00-03:00` / `T23:59:59-03:00`
  para dia inteiro).
- **Como evitar:** manter `timezone: '-03:00'` no pool; formatar sempre com
  `timeZone: "America/Sao_Paulo"`; nunca validar fuso só em máquina local (que já está no fuso
  certo e mascara o bug).

### 29. Helper de composição de SQL do ORM contra o cliente do ERP

- **Sintoma:** busca de nomes em lote retornava **1 nome entre 7 IDs pedidos**, sem erro nem log.
- **Causa:** o cliente do ERP é um wrapper sobre o driver MySQL que trata cada `${...}` como **um
  único** parâmetro `?`. `WHERE usuario_id IN (${Prisma.join(ids)})` compila, mas o array chega
  serializado como um parâmetro só; com a coerção string→número do MySQL (prefixo numérico), casa
  apenas o primeiro ID.
- **Correção:** `$queryRawUnsafe` com os números **já validados** embutidos:
  `` `... WHERE usuario_id IN (${ids.join(",")})` ``.
- **Como evitar:** helpers de composição do ORM só valem contra um cliente ORM de verdade. E
  atenção: o mesmo padrão `${lista.join(",")}` dentro de um **tagged template** (`$queryRaw`, não
  `Unsafe`) tem o mesmo bug — filtra silenciosamente só pelo primeiro item.

### 30. Funções de outro dialeto no SQL

- **Sintoma:** erro 500 só em produção; funcionava localmente.
- **Causa:** uso de `TYPEOF`/`datetime()` (exclusivas do SQLite) num SQL que, em produção, roda
  contra MariaDB.
- **Correção:** helper que emite a expressão certa por dialeto.
- **Como evitar:** o ERP é **sempre** MariaDB — nunca usar função de outro driver ali; e nunca
  considerar validada uma tela que só rodou contra o banco de desenvolvimento.
