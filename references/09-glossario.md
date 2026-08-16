# Glossário — vocabulário do gestor ↔ técnico

Termos como o gestor/usuário do ERP fala, e o que significam no banco `gerente`.

## Caixa e financeiro

| O gestor diz | Significado técnico |
| --- | --- |
| **"Caixa importado"** | `caixas.finprocescritorio = 'S'` — o escritório já rodou a **tela 302 (Geração da Movimentação Financeira de Caixas)** para aquele caixa. Casar sempre por `filial_id` + `caixas_id` |
| **"Caixa não importado"** | `caixas.finprocescritorio = 'N'` |
| **"Tela 302"** | Geração da Movimentação Financeira de Caixas — grava `finprocescritorio` |
| **"N.Caixa Dia" / "Fechamento de Caixa: N"** (papel) | `caixas.caixa_dia` — contador sequencial por **filial + dia comercial** (todos os terminais juntos), pode divergir ±1 do papel |
| **"Caixa"** (número do terminal) | `caixas.caixa` |
| **"Sessão de caixa"** | Uma linha de `caixas` (`dtinicial` = abertura, `dtfinal` = fechamento) |
| **"Sangria"** | `pagamentos` com `oper = 8` e `supsang = 'S'` |
| **"Suprimento"** | `pagamentos` com `oper = 8` e `supsang = 'E'` |
| **"Diferença de Fechamento"** | `SUM(valor_computado - valor_apurado)` de `conf_caixa_loja_tipospgto` da conferência mais recente não-apagada do caixa |
| **"Apurado"** | `conf_caixa_loja_tipospgto.valor_apurado` (o que foi contado) |
| **"Computado"** | `conf_caixa_loja_tipospgto.valor_computado` (o que o sistema esperava) |
| **"Faltou"** | Diferença **positiva** |
| **"Sobrou"** | Diferença **negativa** |
| **"Fechou certo"** | Diferença exatamente 0 (`\|valor\| < 0,005`) |
| **"Conferência do caixa"** | `conf_caixa_loja` (+ detalhe por forma em `conf_caixa_loja_tipospgto`); status em `status_conf` (`P`/`E`/`F`/`X` — significado exato não documentado) |
| **"Quem conferiu"** | `conf_caixa_loja.usuario_conf` |
| **"Forma de pagamento"** | `pagamentos.tipospgto_id` → `tipospgto.descricao` (`1` = DINHEIRO) |
| **"Fiado" / "Crediário"** | `movment.oper = 9`; forma `CREDIARIO` em `tipospgto` |
| **"Troco a levar"** (entrega) | `pagamentos.troco_entrega = 'S'` com valor negativo (pendente); zera na confirmação da chegada |
| **"Gestor" / "Gerente da filial"** | `usuario` com `num_carteira = 'GESTOR'` (convenção manual); a vinculação por período é mantida fora do ERP |
| **"Operador de caixa"** | `caixas.usuario_id` → `usuario.nome`; papel marcado por `num_carteira = 'OPERADOR CAIXA'` |
| **"Caixa errado"** | Caixa com diferença (em módulo) ≥ tolerância de erro (padrão R$ 1,70), ou com ajuste de auditoria ativo |

## Vendas

| O gestor diz | Significado técnico |
| --- | --- |
| **"Cupom" / "Lançamento"** | Par `(movment.filial_id, movment.numlanc)`; contar com `COUNT(DISTINCT filial_id, numlanc)` |
| **"Venda"** (válida) | `movment` com `apagado='N' AND cancelado='N' AND oper IN (2,3)`, sem `ARREDOND`, sem filial 1/999 |
| **"Venda com receita"** | `movment.oper = 3` |
| **"Venda normal"** | `movment.oper = 2` |
| **"Venda bruta"** | `preco_cad * quanti_uni` |
| **"Venda líquida" / "Venda"** | `valor_tot` |
| **"Desconto"** | `(preco_cad * quanti_uni) - valor_tot`; **desconto manual** = linhas com `tipo_desc = 'M'` |
| **"Custo"** | `precoee * quanti_uni` (com cascata de fallback quando `precoee = 0`) |
| **"Lucro bruto"** | `valor_tot - (precoee * quanti_uni)` |
| **"Margem"** | `((valor_tot - precoee*quanti_uni) / valor_tot) * 100` |
| **"CMV"** | custo ÷ venda líquida |
| **"Ticket médio"** | venda líquida ÷ cupons |
| **"Unidades"** (por atendimento) | itens vendidos ÷ cupons |
| **"IPC"** | Indicador de itens por cliente/cupom — **deve excluir `ARREDOND`** (definição exata não documentada na fonte) |
| **"Arredondamento" / "ARREDOND"** | Produto técnico de ajuste de troco (`produto.descricao LIKE '%ARREDOND%'`) — excluir de todo KPI |
| **"Vendas não identificadas" / "N.I."** | `movment.clientes_id = 0` |
| **"Devolução"** | Ver `cancelamento_movment` (e relatório ERP `1216` quando a devolução deve contar no período em que ocorreu) |
| **"Transferência"** | `movment.oper = 10` com `transferencia.remanejamento_id` nulo/0 |
| **"Remanejo"** | `movment.oper = 10` com `transferencia.remanejamento_id > 0` (pedido feito pela tela de compras) |
| **"De filial" / "Para filial"** | `transferencia.defilial_id` / `transferencia.parafilial_id` |
| **"Entrada"** | `movment.E_S = 'E'` com `entradas_id` preenchido (o campo `estoque` é o saldo **antes**) |
| **"Marca própria"** | `produto.espec_id = 257001` — "SUPRA ENERGY" |
| **"Tele" / "Tele-entrega"** | `movment.entrega = 'S'`; entra no relatório só com `dtchegada_entrega` preenchido |

## Loja WhatsApp

| O gestor diz | Significado técnico |
| --- | --- |
| **"Loja WhatsApp"** | Não é filial. Vendas da **FILIAL 10 (`filial_id = 14`)** com `orcament.msgcaixa` ∈ (`wt`,`wr`,`ct`,`cr`) normalizado, `orcament.status IN ('F','N')`, `numlanc <> 0`, com 2 dias de folga na busca do orçamento |
| **"F 10 - WHATS"** | Recorte **diferente**, mais antigo: só `msgcaixa LIKE '%WT%'` |
| **"F 10 - L. FISICA"** | O complemento da FILIAL 10 (venda física), nos relatórios que separam os dois recortes |

## Produto e estoque

| O gestor diz | Significado técnico |
| --- | --- |
| **"Estoque atual"** | `estoque_minimo.estoque` (por produto/filial) |
| **"Demanda"** | `estoque_minimo2.demanda` (diária, por produto/filial) |
| **"Min. Abs." / "Mínimo Absoluto"** | `estoque_minimo2.faceamento` (histórico de alteração em `logs`) |
| **"Mínimo" / "Máximo"** | `estoque_minimo2.minimo` / `maximo` (e `maximo_abs`) |
| **"Min. Dias / Max. Dias"** | Cadastro do produto ou, na falta, `grupo.minA/maxA` … `minD/maxD` por curva |
| **"Curva"** (ABC) | `curvaabc.curvaabc` (por venda) / `curvaabc.curvaabc_est` (por estoque) — **não** `entradas.curvaabc` |
| **"Custo médio" / "PMC"** | `preco_medio_custo.pmc_atual` (`fillogica_id` = filial) |
| **"Compra suspensa"** | `produtos_suspensos_compra` (`compra_suspensa='S'`, `apagado='N'`, com período) — **por filial**; nunca `estoque_minimo.compra_suspensa` |
| **"Lote" / "Validade"** | `lote_novo` (`lote`, `validade`, `estoque`, `fillogica_id`) — nunca a tabela `lote` (antiga) |
| **"Categoria" / "Grupo"** | `grupo.descricao` / `grupo.desc_arvore` — nunca `produto.receita` |
| **"Classe terapêutica"** | `classe_terapeutica.descricao`; "USO CONTINUO"/"USO RECORRENTE" ficam após a 2ª barra |
| **"Fabricante" / "Laboratório"** | `fabricantes.descricao` (preferir a `produto.labora`, que é legado e pode ser NULL) |
| **"Código de barras"** | `barras.barras` (produto pode ter vários ativos) + `produto.barras` |
| **"Receituário"** | `produto.receita` (`'S'`/`'N'`) |

## Preço

| O gestor diz | Significado técnico |
| --- | --- |
| **"Preço de tabela" / "Preço de venda"** | `grupo_preco_produto.preco_vnd` (fonte de verdade) |
| **"Clube do Pedrinho" / "Desconto à vista"** | `grupo_preco_produto.desconto` (%), aplicado sobre `preco_vnd` |
| **"Promoção" / "Promoção por data"** | `grupo_preco_produto.preco_pro`, válida entre `dtiniciopromocao` e `valid_pro` |
| **"Preço da filial" / "Oferta da loja"** | `precosfilial.preco_promo`, válido entre `inicio_promocao` e `final_promocao` — **prioridade máxima** |
| **"Caderno de Ofertas"** | Recorte de produtos em oferta (relatório); usa a mesma hierarquia de preço |

## Cliente / CRM

| O gestor diz | Significado técnico |
| --- | --- |
| **"Cliente"** (pessoa) | CPF normalizado (11 dígitos, sem sequência repetida) — **não** `clientes_id`, que é o cadastro |
| **"Cadastro duplicado"** | Vários `clientes_id` com o mesmo `clientes.cpf` |
| **"Etiqueta RFV" / "Segmento"** | Um dos 11 segmentos derivados de Recência/Frequência/Valor (Campeão, Fidelizado, Promissor, Potencial para ser fidelizado, Recente, Em risco, Não pode perder, Precisa de atenção, Quase hibernando, Hibernando, Perdido) |
| **"Dias sem comprar"** | Recência (dias desde a última compra) |
| **"Fiel"** | Tempo de relacionamento ≥ 180 dias, ≥ 4 vendas em 6 meses, recência ≤ 60 dias, gasto 6 meses ≥ R$ 300 (limiares configuráveis) |
| **"Potencial"** | Recência ≤ 45 dias e gasto 6 meses ≥ R$ 200 (só se não for Fiel) |
| **"Loja favorita" / "Vendedor favorito"** | Maior número de transações (`filial_id` / `usuario_id`), desempate por valor gasto |

## Estrutura e organização

| O gestor diz | Significado técnico |
| --- | --- |
| **"Filial"** | `filial.reduz` (nome abreviado) + `filial_id`; `1` = ESCRITORIO e `999` = técnico, sempre excluídos |
| **"MATRIZ"** | `filial_id = 2` |
| **"Rede"** | Todas as filiais operacionais (todas exceto `filial_id = 1`) — 11 filiais |
| **"Relatório do ERP"** | Linha da tabela `relatorio` (`descricao`, `finalidade`, `sql`, `parametros`) |
| **"Usuário" / "Operador"** | `usuario` (`usuario_id`, `nome`, `filial_id`, `num_carteira`, `status`, `apagado`) |
| **"Número da Carteira"** | `usuario.num_carteira` — texto livre usado por convenção para marcar `GESTOR` / `OPERADOR CAIXA` |
| **"Apagado"** | Soft delete (`apagado = 'S'`) — o registro continua na tabela |

## Termos sem base documentada (lacunas)

| Termo | Situação |
| --- | --- |
| **PBM** | Aparece só como flag `'S'`/`'N'` em relatórios; tabela/coluna de origem **não documentada** |
| **Farmácia Popular** | Aparece só como `motivo_alteracao = 'popular'` em `conf_caixa_loja_tipospgto`; **sem tabela dedicada documentada** |
| **SNGPC / controlados** | **Nenhuma** tabela documentada na fonte |
| **Convênio** | **Nenhuma** tabela documentada na fonte (o mais próximo é o crediário, `oper = 9`) |
| **`status_conf` (`P`/`E`/`F`/`X`)** | Valores conhecidos, significado de cada letra **não documentado** (`F`/`X` = conferido, nos cálculos de premiação) |
| **Demais valores de `movment.oper`** | Só `2`, `3`, `8`, `9`, `10` estão documentados; existem outros |
