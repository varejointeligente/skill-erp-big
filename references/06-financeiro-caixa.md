# Caixa, Pagamentos, Sangria e Conferência

Sumário:

- [Tabela `caixas`](#tabela-caixas)
- [`caixa_dia` — contador sequencial por filial+dia](#caixa_dia--contador-sequencial-por-filialdia)
- [`finprocescritorio` — tela 302 / "caixa importado"](#finprocescritorio--tela-302--caixa-importado)
- [Tabela `pagamentos`](#tabela-pagamentos)
- [`tipospgto` e `tipospgto_sangria`](#tipospgto-e-tipospgto_sangria)
- [Sangria e Suprimento](#sangria-e-suprimento)
- [Conferência de caixa — `conf_caixa_loja` e `status_conf`](#conferência-de-caixa--conf_caixa_loja-e-status_conf)
- [Diferença de Fechamento — fonte oficial](#diferença-de-fechamento--fonte-oficial)
- [Fórmula antiga (Movimentos + Suprimentos − Sangrias) e por que foi abandonada](#fórmula-antiga-movimentos--suprimentos--sangrias-e-por-que-foi-abandonada)
- [Convenção de sinal e vocabulário](#convenção-de-sinal-e-vocabulário)
- [Auditoria fora do ERP (ajustes)](#auditoria-fora-do-erp-ajustes)
- [Tolerâncias de negócio](#tolerâncias-de-negócio)

---

## Tabela `caixas`

Uma linha por **sessão de caixa** (abertura → fechamento).

| Coluna | Descrição |
| --- | --- |
| `caixas_id` | Identificador da sessão — **não é globalmente único** |
| `filial_id` | Filial — **compõe a PK real: `(filial_id, caixas_id)`** |
| `caixa` | Número do **terminal físico** |
| `caixa_dia` | Contador sequencial por filial+dia (ver abaixo) |
| `dtinicial` | Abertura |
| `dtfinal` | Fechamento |
| `usuario_id` | Operador do caixa |
| `apagado` | `'S'`/`'N'` |
| `finprocescritorio` | `char(1)` `'S'`/`'N'`, default `'N'` — flag da tela 302 (ver abaixo) |

> **`caixas_id` não é globalmente único.** O mesmo valor se repete em filiais diferentes (ex.:
> `caixas_id = 24653` existe simultaneamente nas filiais 2, 4 e 6, com dados distintos). Nunca
> filtrar/casar caixas usando só `caixas_id` (`FIND_IN_SET`, `IN (...)` sem `filial_id`) — o JOIN
> com `pagamentos`/`movment` faz **fan-out silencioso** e infla qualquer `SUM`. Sempre usar o par:
> `WHERE (cx.filial_id, cx.caixas_id) IN ((f1,c1),(f2,c2),...)` ou
> `cx.filial_id = X AND cx.caixas_id = Y`.

---

## `caixa_dia` — contador sequencial por filial+dia

Confirmado em 2026-07-15 consultando a MATRIZ (`filial_id = 2`) em 12–14/07/2026:

- `caixa_dia` reinicia em `1` a cada **"dia comercial"** — o primeiro caixa do dia costuma abrir
  por volta das **03h da manhã**, não à meia-noite.
- Sobe **+1 a cada abertura de caixa naquele dia, somando TODOS os terminais físicos da filial
  juntos** — não é contagem separada por `caixa`.
- Exemplo real (13/07): caixa 4→dia 1, caixa 5→dia 2, caixa 11→dia 3, caixa 7→dia 4, caixa 9→dia
  5, caixa 5→dia 6, caixa 7→dia 7, caixa 9→dia 8, caixa 5→dia 9, caixa 7→dia 10 — ordenado
  estritamente por `dtinicial`, misturando terminais.
- É o mesmo número impresso no comprovante físico como **"Fechamento de Caixa: N" / "N.Caixa Dia:
  N"**.

> **Cuidado — pode divergir em ±1 do papel impresso.** Confirmado com dois comprovantes reais da
> MATRIZ do mesmo dia (13/07/2026): a sessão `caixas_id = 55732` (caixa 5, usuário 1157, abertura
> 13:02:10 / fechamento 14:56:43 — horários batendo exatamente com o papel) está gravada como
> `caixa_dia = 6`, mas o comprovante mostra **"N.Caixa Dia: 5"**. Não há sessão com `apagado='S'`
> no meio que explique o furo — o contador impresso reflete o estado do ERP **naquele momento** e
> pode ficar 1 à frente se alguma abertura não deixou (ou não deixa mais) linha correspondente
> (abertura cancelada, hard delete posterior). **Usar `caixa_dia` para reconstruir a ordem
> relativa das sessões do dia, nunca como prova exata contra papel físico antigo.**

---

## `finprocescritorio` — tela 302 / "caixa importado"

`caixas.finprocescritorio` é a flag da tela **302 — Geração da Movimentação Financeira de
Caixas**. Quando o escritório abre a 302 para um caixa fechado e clica **OK**, o ERP grava
`finprocescritorio = 'S'`; enquanto não é gerado, fica `'N'`.

Confirmado com exemplos reais na FILIAL 4 (`filial_id = 6`): `caixas_id = 30168` (ainda não passou
pela 302) → `N`; `caixas_id = 30138` (já passou, "Finalizado") → `S`. Distribuição geral nos
últimos 30 dias, todas as filiais: **1122 `S` / 191 `N`**.

- **Vocabulário do gestor: "caixa importado" = `finprocescritorio = 'S'`;** "caixa não importado"
  = `'N'`.
- Ao casar essa flag, **usar `filial_id` + `caixas_id`** (o `caixas_id` não é único).
- **Não confundir com `status_conf`** — são dois processos diferentes: `status_conf` é a
  conferência interna feita por alguém da farmácia; `finprocescritorio` é o processamento
  financeiro feito pelo escritório na tela 302.

---

## Tabela `pagamentos`

Formas de pagamento por cupom/venda, e também os lançamentos de sangria/suprimento.

| Coluna | Descrição |
| --- | --- |
| `pagamentos_id` | Identificador do lançamento |
| `filial_id` | Filial |
| `numlanc` | Cupom (par com `filial_id`) |
| `tipospgto_id` | FK para `tipospgto` (`1` = DINHEIRO) |
| `datahora` | Data/hora (**sem underscore**, ao contrário de `movment.data_hora`) |
| `valor` | Valor do lançamento (pode ser negativo) |
| `oper` | Operação (`8` = sangria/suprimento) |
| `supsang` | `'S'` = sangria, `'E'` = suprimento |
| `numcaixa` | Número do caixa — **sem índice** (ver `07-consultas-e-performance.md`) |
| `troco_entrega` | `'S'`/`'N'` — troco pendente de entrega (ver `05-clientes-crm.md`) |
| `apagado` | `'S'`/`'N'` |
| `cancelado` | `'S'`/`'N'` |

Índices existentes: **`oper`** (composto com `filial_id`/`datahora`/`apagado`/`troco_entrega`),
`filial_id`, `datahora`, `tipospgto_id`. **Não existe índice em `numcaixa`.**

Join com a venda:

```sql
JOIN pagamentos pag
  ON mov.filial_id = pag.filial_id
 AND mov.numlanc  = pag.numlanc
JOIN tipospgto tp ON pag.tipospgto_id = tp.tipospgto_id
```

---

## `tipospgto` e `tipospgto_sangria`

**`tipospgto`** — cadastro das formas de pagamento:

| Coluna | Descrição |
| --- | --- |
| `tipospgto_id` | PK (`1` = DINHEIRO) |
| `descricao` | Nome da forma (ex.: DINHEIRO, CREDIARIO) |

**`tipospgto_sangria`** — marca quais formas de pagamento efetuam sangria:

| Coluna | Descrição |
| --- | --- |
| `efetua_sangria` | `'S'`/`'N'` |

> **Armadilha:** em algumas filiais o **CREDIARIO** também está marcado `efetua_sangria = 'S'` —
> ver "Fórmula antiga" abaixo.

---

## Sangria e Suprimento

- Ambos vivem em **`pagamentos` com `oper = 8`**, discriminados por `supsang`:
  - `supsang = 'S'` → **sangria** (retirada de dinheiro do caixa)
  - `supsang = 'E'` → **suprimento** (entrada de dinheiro no caixa)
- **Não existe contador/coluna própria** de Sangrias/Suprimentos/Diferença no comprovante físico
  de fechamento — o ERP soma na hora da impressão a partir de `pagamentos`. Para replicar, refazer
  esse cálculo em vez de procurar campo pronto.
- Uma listagem de sangrias/suprimentos é só uma consulta de lançamentos de `pagamentos`
  (`oper = 8`), filtrada por filial + período + forma de pagamento.

---

## Conferência de caixa — `conf_caixa_loja` e `status_conf`

- **`conf_caixa_loja`** — a conferência interna do caixa, feita por alguém da farmácia. Dela sai o
  **`status_conf`**. Também tem `usuario_conf` (quem fez a conferência física).
  - **Valores comprovados: `F` e `X`** — são os dois estados tratados como "caixa já conferido"
    (`status_conf IN ('F','X')` é o filtro usado para separar caixas conferidos).
  - **O significado de cada letra e o conjunto completo de valores possíveis são desconhecidos.**
    Não existe evidência de outros valores; não inventar letras. Para levantar numa base real:
    `SELECT status_conf, COUNT(*) FROM conf_caixa_loja GROUP BY status_conf`.
- Um caixa pode ter mais de uma conferência — a regra usada é pegar a **conferência mais recente
  não-apagada** daquele caixa (subquery de `conf_caixa_loja_id`).
- **`conf_caixa_loja_tipospgto`** — o detalhe da conferência **por forma de pagamento**:

| Coluna | Descrição |
| --- | --- |
| `filfisica_id` | Filial (parte da chave) |
| `conf_caixa_loja_id` | Conferência (parte da chave) |
| `tipospgto_id` | Forma de pagamento (parte da chave) |
| `valor_apurado` | Valor apurado (contado) |
| `valor_computado` | Valor computado (esperado pelo sistema) |
| `apurado_comparado` / `computado_comparado` | Bases da coluna "Diferença Comparado" do relatório impresso |
| `motivo_alteracao` | Motivo da correção manual feita pelo operador na conferência (ex.: `"nao sangrei"`, `"popular"` para Farmácia Popular) |
| `apagado` | `'S'`/`'N'` |

---

## Diferença de Fechamento — fonte oficial

**A tela nativa do ERP ("Caixas Fechados > Detalhes da Conferência de Caixa") e o "Relatório de
Caixa — Apurado X Computado" impresso não recalculam nada — eles leem
`conf_caixa_loja_tipospgto`**, que já contém os valores **por forma de pagamento**, revisados e
corrigidos manualmente pelo operador que fez a conferência.

Cálculo oficial da diferença de um caixa:

```
diferenca = SUM(valor_computado - valor_apurado)
            de todas as linhas de conf_caixa_loja_tipospgto
            com filfisica_id = <filial>, conf_caixa_loja_id = <conferência mais recente do caixa>,
            apagado = 'N'
```

Validado batendo 100% com o "Total Caixa: Diferença" e a "Totalização do Relatório: Diferença" do
papel impresso; `apurado_comparado - computado_comparado` bate com a coluna "Diferença Comparado"
do mesmo papel.

**Nunca mais recalcular Movimentos + Suprimentos − Sangrias direto de `pagamentos` para obter esse
número.**

**Caixa sem NENHUMA conferência rodada no ERP** (sem linha em `conf_caixa_loja`, ou conferência sem
linhas em `conf_caixa_loja_tipospgto`): a diferença fica **em branco**, nunca um valor estimado
pela fórmula antiga como fallback (opção explicitamente descartada pelo gestor).

---

## Fórmula antiga (Movimentos + Suprimentos − Sangrias) e por que foi abandonada

Fórmula historicamente usada: somar, por caixa, os movimentos + suprimentos − sangrias de
`pagamentos`, filtrando as formas marcadas `tipospgto_sangria.efetua_sangria = 'S'`, agrupando só
por `caixas_id`.

**Bug real (corrigido em 2026-08-08):** o Caixa ID 30242 (FILIAL 4, `filial_id = 6`) aparecia como
"Sobrou R$ 0,08" enquanto a tela nativa do ERP e o papel impresso mostravam "Sobrou R$ 15,05".

- **Causa raiz:** a fórmula somava **todas** as formas marcadas `efetua_sangria = 'S'`, sem separar
  por `tipospgto_id`. Na FILIAL 4, **CREDIARIO** também está marcado assim — uma venda fiado
  (`oper = 9`, R$ 14,97) sem a sangria/baixa correspondente contaminava a soma. DINHEIRO sozinho
  tinha −15,05 (Sobrou 15,05); CREDIARIO sozinho +14,97 (Faltou 14,97); a soma cega deu −0,08.
- **Correção:** ler sempre de `conf_caixa_loja_tipospgto` (fonte oficial).
- **Exceção mantida:** o **detalhamento por forma de pagamento** ("possível causa" de uma
  diferença, por lançamento) continua sendo calculado de `pagamentos`, porque não há equivalente
  em `conf_caixa_loja_tipospgto` (que só tem totais agregados por forma). É útil justamente para
  apontar uma forma como CREDIARIO desbalanceada. Só o **total** deve vir da fonte oficial.
- Rótulo correto na UI para o número oficial: **"Computado − Apurado"** (não mais
  "Mov. + Sup. − Sang.").

---

## Convenção de sinal e vocabulário

- **Positivo = "Faltou"** · **Negativo = "Sobrou"** — em toda a cadeia (diferença calculada, valor
  original de auditoria, valor ajustado).
- `diferenca = valor_computado - valor_apurado` preserva essa convenção.
- **"Fechou certo" não é diferença exatamente zero** — ver a regra vigente logo abaixo.
- Qualquer soma/subtração monetária feita fora do SQL deve ser **arredondada para 2 casas**
  (`Math.round(v * 100) / 100`) antes de exibir num campo editável ou persistir — somar valores
  `Decimal`/string do MariaDB convertidos para número gera ruído de ponto flutuante clássico
  (ex.: `9,940000000000055`). A formatação de exibição mascara o problema em alguns lugares e não
  em outros.

### "Caixa certo" / "caixa errado" — regra vigente (mudou em 2026-07-22)

> **Regra antiga, revogada:** até 2026-07-22 um caixa era considerado "fechou certo" quando o valor
> ajustado dava exatamente R$ 0,00. **Essa definição por valor exato foi substituída** e não deve
> mais ser usada. (O limiar `|valor| < 0,005` que às vezes aparece associado a ela é outra coisa:
> é a regra de **exibição** de um item de correção de valor R$ 0,00 — mostrado como caso neutro,
> em cinza, sem rótulo "Reduz"/"Aumenta". Não serve como critério de fechamento.)

Regra vigente, usada tanto na coluna "Caixa Errado" quanto no cálculo de premiação:

| Situação do caixa | Resultado |
| --- | --- |
| Tem ajuste de auditoria ativo com item cujo motivo está marcado **"caixa considerado como certo"** | **Certo** — é a única forma de afirmar "certo". Tem prioridade sobre tudo, inclusive sobre a tolerância |
| Tem qualquer outro ajuste de auditoria ativo | **Errado** (qualquer motivo, qualquer valor de correção) |
| Sem ajuste ativo, mas `ABS(diferença) ≥ tolerância de erro` | **Errado** |
| Sem ajuste ativo e diferença dentro da tolerância | **Indefinido** — fica vazio, **nunca** "certo" |

Dois pontos que fazem a diferença na prática:

- **"Sem problema detectado" não é o mesmo que "certo".** A coluna só rastreia problema; escrever
  "Não"/"certo" nesse caso sugeriria uma confirmação que ninguém deu.
- **O critério de exceção é sempre o motivo marcado, nunca o valor apurado.** Motivos são
  registros editáveis; casar por um **flag no banco** (ou pelo id do motivo), nunca comparando o
  texto do motivo contra uma lista fixa no código — renomear o motivo quebra a regra em silêncio.

---

## Auditoria fora do ERP (ajustes)

Como o ERP é somente leitura, correções de conferência (sangria esquecida, valor digitado errado,
diferença de fechamento divergente da contagem física) **nunca são gravadas no ERP** — vivem no
banco da aplicação, ao lado do valor do ERP:

- A coluna calculada pelo ERP **nunca é substituída** — o valor auditado entra numa coluna
  separada ("Valor após auditoria").
- Fórmula do ajuste: **`valor_ajustado = valor_original − soma(itens.valor)`**.
  Exemplo: diferença ERP "Faltou R$ 9,94" + 1 correção de R$ 10,00 → `9,94 − 10,00 = −0,06` →
  "Sobrou R$ 0,06".
- **Sinal do item depende do sinal do valor original:** subtrair um valor de **mesmo sinal** que
  `valor_original` sempre aproxima de zero (reduz a diferença); de **sinal oposto**, afasta
  (aumenta). Um mapeamento fixo "reduz = positivo" só funciona quando a diferença original é
  positiva (Faltou) e inverte o efeito quando é negativa (Sobrou).
- Um ajuste só pode ser criado quando o caixa **já tem conferência oficial** no ERP — sem
  `conf_caixa_loja_tipospgto` não há `valor_original` confiável.
- Registros financeiros usam **soft-cancel** (`cancelado_em`), nunca hard delete.

---

## Tolerâncias de negócio

> **Nada aqui é coluna nem parâmetro do ERP Big.** São regras de negócio de uma aplicação de
> auditoria, configuradas **por filial e por cliente**. O que se reaproveita é a **estrutura**; os
> valores concretos abaixo são de **uma** instalação e precisam ser confirmados com cada cliente.

O padrão estrutural que vale a pena copiar: **duas tolerâncias independentes que coexistem** —
nunca usar uma no lugar da outra.

| Parâmetro | Padrão numa instalação | Para que serve |
| --- | --- | --- |
| `tolerancia_erro_percentual` | R$ 1,70 | Decide se um caixa conta como **"caixa errado"** (% de acerto do operador, % de diferença do gerente, coluna "Caixa Errado"). Vale **em módulo** — falta **ou** sobra ≥ esse valor conta como erro |
| `tolerancia_desconto_caixa` | R$ 0,76 | Decide o **desconto em folha** do operador de caixa e os totais "Apurado". Só vale para **falta**; sobra nunca desconta. Falta ≥ o limite desconta o **valor total** da diferença (não só o excedente); sobra de um caixa **nunca compensa** falta de outro (sem netting no período) |

> Ao criar qualquer cálculo novo, decidir explicitamente: "isso é sobre **status de erro** ou sobre
> **dinheiro real apurado**?" — não existe tolerância única para a tela inteira. Usar a errada
> produz um número plausível e sistematicamente errado.

Regras associadas de premiação — **exemplo de uma instalação**, todas configuráveis, nada
hardcoded:

| Faixa | Percentual de acerto | Premiação |
| --- | --- | --- |
| Faixa 1 | de `faixa1_percentual_min` a `faixa1_percentual_max` (ex.: 90,00% a 99,99%) | `faixa1_valor_premio` (ex.: R$ 70,00) |
| Faixa 2 | ≥ `faixa2_percentual_min` (ex.: 100,00%) | `faixa2_valor_premio` (ex.: R$ 100,00) |

Abaixo do mínimo da Faixa 1, nenhuma premiação. Naquele cliente o **gerente não tem faixa/meta
configurável** — só o "% Diferença" (caixas errados ÷ total de caixas da filial), exibido sem meta.

**Papéis (gerente x operador de caixa):** o operador de um caixa é `caixas.usuario_id` → `usuario`
(isso é do ERP). Já *marcar* quem é gerente e quem é operador não existe no ERP — quando um cliente
faz isso pelo campo livre `usuario.num_carteira`, é convenção dele (ver `01-visao-geral.md`,
"Exemplo de uma instalação"). A vinculação por período (com transferência entre filiais) é mantida
fora do ERP, com o nome sempre resolvido ao vivo em `usuario.nome`.
