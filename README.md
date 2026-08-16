# erp-big

Skill do Claude com a base de conhecimento do **ERP Big** (BigPharma / Big Sistemas) — ERP de
varejo farmacêutico, banco **MariaDB**, base `gerente`.

Serve para atendimento de suporte e consultoria: quando alguém pede um relatório, questiona um
número ou pergunta "de onde sai esse campo", o Claude passa a responder a partir do que já foi
validado contra bancos reais, em vez de deduzir pelo nome das colunas.

## Conteúdo

```
SKILL.md                        instruções e índice das referências
references/
  01-visao-geral.md             convenções, flags, PKs compostas, filiais, tabela `relatorio`
  02-vendas-movment.md          movment, oper, cupom, devolução, transferência x remanejo
  03-produto-estoque.md         produto, barras, grupo, estoques, lote/validade, curva ABC
  04-precos-ofertas.md          hierarquia de preço, promoções, desconto à vista
  05-clientes-crm.md            clientes, CPF duplicado, RFV, WhatsApp, entrega e troco
  06-financeiro-caixa.md        caixas, pagamentos, sangria, conferência, tela 302
  07-consultas-e-performance.md índices, FORCE INDEX, fan-out, BigInt, fuso
  08-armadilhas.md              catálogo de bugs reais: sintoma → causa → correção → prevenção
  09-glossario.md               vocabulário do gestor ↔ tabela/coluna/valor
scripts/
  consultar_big.py              consulta somente leitura no MariaDB
```

## Instalar

Empacote e envie o `.skill` para o Claude, ou copie a pasta para o diretório de skills:

```bash
zip -r erp-big.skill . -x '.git/*'
```

## Consultar o banco

```bash
pip install pymysql
export BIG_HOST=... BIG_PORT=3306 BIG_USER=usuario_leitura BIG_PASSWORD=... BIG_DATABASE=gerente
python scripts/consultar_big.py "SELECT filial_id, reduz FROM filial WHERE apagado='N'"
python scripts/consultar_big.py --tabelas movment
```

O script abre a sessão em `TRANSACTION READ ONLY` e recusa qualquer comando que não seja leitura.
Use sempre um usuário com permissão apenas de `SELECT` — nunca o `root` do ERP.

## Manter viva

Esta base vale pelo que tem de específico. Quando aparecer uma armadilha nova, registre em
`references/08-armadilhas.md` no mesmo formato, **com o caso concreto** (produto, filial, valor,
data). É o exemplo real que faz a regra grudar; a regra abstrata sozinha é esquecida na próxima
query.

Áreas ainda vazias por falta de fonte: SNGPC, controlados, convênios/PBM e Farmácia Popular; os
valores de `movment.oper` além de 2/3/8/9/10; as letras de `status_conf`. Estão marcadas como
lacuna no glossário.

## Origem e privacidade

Destilado de documentação de projeto real de uma rede de farmácias. Nomes de pessoas foram
substituídos por "o gestor"; não há credenciais, hosts nem IPs nos arquivos. Os IDs de exemplo
(produto, cupom, caixa) foram mantidos porque são o que torna cada armadilha reproduzível.
