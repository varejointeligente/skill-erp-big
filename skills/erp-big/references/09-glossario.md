# Glossário — vocabulário de quem usa o ERP ↔ técnico

Termos como o gestor/usuário do ERP fala, e o que significam no banco (normalmente chamado
`gerente` — confirmar com `SHOW DATABASES`).

> **Vocabulário varia por cliente.** Nomes comerciais (programa de fidelidade, apelido de loja),
> ids de filial e parâmetros de negócio mudam de rede para rede. Aqui ficam os termos e a coluna
> correspondente; os valores concretos de uma instalação estão em `01-visao-geral.md`,
> "Exemplo de uma instalação".

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
| **"Fechou certo"** | **Não é diferença exata.** Desde 2026-07-22 só é "certo" o caixa com ajuste de auditoria cujo motivo está marcado "caixa considerado como certo"; sem ajuste e dentro da tolerância o status fica **indefinido**, nunca "certo" (ver `06-financeiro-caixa.md`) |
| **"Conferência do caixa"** | `conf_caixa_loja` (+ detalhe por forma em `conf_caixa_loja_tipospgto`); status em `status_conf` — só `F` e `X` estão comprovados ("conferido"), os demais valores possíveis são **desconhecidos** |
| **"Quem conferiu"** | `conf_caixa_loja.usuario_conf` |
| **"Forma de pagamento"** | `pagamentos.tipospgto_id` → `tipospgto.descricao` (`1` = DINHEIRO) |
| **"Fiado" / "Crediário"** | `movment.oper = 9`; forma `CREDIARIO` em `tipospgto` |
| **"Troco a levar"** (entrega) | `pagamentos.troco_entrega = 'S'` com valor negativo (pendente); zera na confirmação da chegada |
| **"Gestor" / "Gerente da filial"** | **Não existe no ERP.** Alguns clientes marcam o papel no campo livre `usuario.num_carteira`; a vinculação por período é mantida fora do ERP |
| **"Operador de caixa"** | `caixas.usuario_id` → `usuario.nome` (isso é do ERP); *marcar* o papel é convenção do cliente |
| **"Caixa errado"** | Caixa com diferença (em módulo) ≥ a tolerância de erro configurada pelo cliente, ou com ajuste de auditoria ativo |

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
| **"Marca própria"** | `produto.espec_id` correspondente à marca própria da rede — **o valor é cadastro do cliente**, conferir na base |
| **"Tele" / "Tele-entrega"** | `movment.entrega = 'S'`; entra no relatório só com `dtchegada_entrega` preenchido |

## Loja WhatsApp

| O gestor diz | Significado técnico |
| --- | --- |
| **"Loja WhatsApp"** | Não é filial. Vendas de uma filial de origem definida pelo cliente, com `orcament.msgcaixa` **normalizado** batendo com os códigos combinados naquela rede, `orcament.status IN ('F','N')`, `numlanc <> 0`, com 2 dias de folga na busca do orçamento. Filial e códigos: confirmar na base |
| Recorte **legado** de venda por WhatsApp | Só `msgcaixa LIKE '%<código>%'` — sem os demais códigos, sem folga de 2 dias, sem filtro de `status`. É **outro** recorte, não substituto |
| Complemento ("venda física" da mesma filial) | O que sobra da filial de origem depois de tirar o recorte de WhatsApp, nos relatórios que separam os dois |

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
| **"Desconto à vista"** (cada rede tem um nome comercial próprio para o programa de fidelidade) | `grupo_preco_produto.desconto` (%), aplicado sobre `preco_vnd` — o nome comercial não existe no banco |
| **"Promoção" / "Promoção por data"** | `grupo_preco_produto.preco_pro`, válida entre `dtiniciopromocao` e `valid_pro` |
| **"Preço da filial" / "Oferta da loja"** | `precosfilial.preco_promo`, válido entre `inicio_promocao` e `final_promocao` — **prioridade máxima** |
| **"Caderno de Ofertas"** | Recorte de produtos em oferta (relatório); usa a mesma hierarquia de preço |

## Cliente / CRM

| O gestor diz | Significado técnico |
| --- | --- |
| **"Cliente"** (pessoa) | CPF normalizado (11 dígitos, sem sequência repetida) — **não** `clientes_id`, que é o cadastro |
| **"Cadastro duplicado"** | Vários `clientes_id` com o mesmo `clientes.cpf` |
| **"Etiqueta RFV" / "Segmento"** | Calculado fora do ERP. Um dos 11 segmentos derivados de Recência/Frequência/Valor (Campeão, Fidelizado, Promissor, Potencial para ser fidelizado, Recente, Em risco, Não pode perder, Precisa de atenção, Quase hibernando, Hibernando, Perdido) |
| **"Dias sem comprar"** | Recência (dias desde a última compra) |
| **"Fiel"** | Regra derivada, **fora do ERP**. Limiares de uma instalação (configuráveis): relacionamento ≥ 180 dias, ≥ 4 vendas em 6 meses, recência ≤ 60 dias, gasto 6 meses ≥ R$ 300 |
| **"Potencial"** | Regra derivada, **fora do ERP**. Limiares de uma instalação: recência ≤ 45 dias e gasto 6 meses ≥ R$ 200 (só se não for Fiel) |
| **"Loja favorita" / "Vendedor favorito"** | Maior número de transações (`filial_id` / `usuario_id`), desempate por valor gasto |

## Estrutura e organização

| O gestor diz | Significado técnico |
| --- | --- |
| **"Filial"** | `filial.reduz` (nome abreviado) + `filial_id`; `1` costuma ser o escritório e `999` é registro técnico, ambos sempre excluídos |
| **"MATRIZ"** | Um valor de `filial.reduz`; o `filial_id` correspondente **varia por cliente** — resolver com `SELECT filial_id, reduz FROM filial WHERE apagado='N'` |
| **"Rede"** | Todas as filiais operacionais (`filial` com `apagado='N'`, menos `1` e `999`); a quantidade é dado da instalação |
| **"Relatório do ERP"** | Linha da tabela `relatorio` (`descricao`, `finalidade`, `sql`, `parametros`) |
| **"Usuário" / "Operador"** | `usuario` (`usuario_id`, `nome`, `filial_id`, `num_carteira`, `status`, `apagado`) |
| **"Número da Carteira"** | `usuario.num_carteira` — **texto livre sem semântica no ERP**; se um cliente o usa para marcar papel, é convenção dele |
| **"Apagado"** | Soft delete (`apagado = 'S'`) — o registro continua na tabela |

## Termos sem base documentada (lacunas)

| Termo | Situação |
| --- | --- |
| **PBM** | Aparece só como flag `'S'`/`'N'` em relatórios; tabela/coluna de origem **não documentada** |
| **Farmácia Popular** | Aparece só como `motivo_alteracao = 'popular'` em `conf_caixa_loja_tipospgto`; **sem tabela dedicada documentada** |
| **SNGPC / controlados** | **Nenhuma** tabela documentada na fonte |
| **Convênio** | **Nenhuma** tabela documentada na fonte (o mais próximo é o crediário, `oper = 9`) |
| **`status_conf`** | Só `F` e `X` estão comprovados (= conferido). O significado das letras e **quais outros valores existem** são desconhecidos — levantar com `SELECT status_conf, COUNT(*) FROM conf_caixa_loja GROUP BY status_conf` |
| **Demais valores de `movment.oper`** | Só `2`, `3`, `8`, `9`, `10` estão documentados; existem outros |
