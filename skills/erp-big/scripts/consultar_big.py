#!/usr/bin/env python3
"""
Consulta somente leitura no ERP Big (MariaDB, base `gerente`).

Existe para que uma hipótese sobre o dado seja verificada em vez de afirmada de memória.
Recusa qualquer comando que não seja SELECT/SHOW/EXPLAIN/DESCRIBE — o ERP é a fonte de
verdade da operação do cliente e não deve ser alterado por engano.

Configuração (variáveis de ambiente ou --dsn):
    BIG_HOST      host do MariaDB           (default: localhost)
    BIG_PORT      porta                     (default: 3306)
    BIG_USER      usuário somente leitura
    BIG_PASSWORD  senha
    BIG_DATABASE  base                      (default: gerente)

Uso:
    python consultar_big.py "SELECT * FROM filial WHERE apagado='N'"
    python consultar_big.py -f consulta.sql --json
    python consultar_big.py --tabelas movment          # colunas + índices da tabela
    echo "SELECT 1" | python consultar_big.py -
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from decimal import Decimal
from datetime import date, datetime, timedelta

COMANDOS_PERMITIDOS = ("select", "show", "explain", "describe", "desc", "with")


def carregar_driver():
    try:
        import pymysql  # type: ignore

        return "pymysql", pymysql
    except ImportError:
        pass
    try:
        import mysql.connector as mysqlconn  # type: ignore

        return "mysql-connector", mysqlconn
    except ImportError:
        sys.exit(
            "Nenhum driver MySQL/MariaDB encontrado.\n"
            "Instale um deles:  pip install pymysql   (ou)   pip install mysql-connector-python"
        )


def validar_somente_leitura(sql: str) -> None:
    """Bloqueia qualquer coisa que não seja leitura, inclusive escondida em statement múltiplo."""
    limpo = re.sub(r"/\*.*?\*/", " ", sql, flags=re.S)
    limpo = re.sub(r"--[^\n]*", " ", limpo)
    limpo = re.sub(r"#[^\n]*", " ", limpo)

    statements = [s.strip() for s in limpo.split(";") if s.strip()]
    if not statements:
        sys.exit("Consulta vazia.")

    for stmt in statements:
        primeira = stmt.split(None, 1)[0].lower()
        if primeira not in COMANDOS_PERMITIDOS:
            sys.exit(
                f"Bloqueado: '{primeira.upper()}' não é comando de leitura.\n"
                "Este script só executa SELECT / WITH / SHOW / EXPLAIN / DESCRIBE.\n"
                "Alteração no ERP precisa de confirmação explícita do cliente e de outro caminho."
            )
    if len(statements) > 1:
        sys.exit("Envie um comando por vez — statement múltiplo não é aceito.")


def conectar(args):
    """Devolve (conexao, nome_do_driver) — o nome decide como se abre o cursor de dict."""
    nome, driver = carregar_driver()
    cfg = dict(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        database=args.database,
    )
    if nome == "pymysql":
        conn = driver.connect(
            **cfg,
            charset="utf8mb4",
            cursorclass=driver.cursors.DictCursor,
            read_timeout=args.timeout,
            connect_timeout=15,
            init_command="SET SESSION TRANSACTION READ ONLY, time_zone = '-03:00'",
        )
    else:
        conn = driver.connect(**cfg, charset="utf8mb4", connection_timeout=15, time_zone="-03:00")
    return conn, nome


def abrir_cursor(conn, nome_driver):
    """pymysql já vem com DictCursor da conexão; mysql-connector precisa do flag."""
    return conn.cursor() if nome_driver == "pymysql" else conn.cursor(dictionary=True)


def serializar(valor):
    """BigInt, Decimal, data e timedelta não sobrevivem a json.dumps sem tradução."""
    if isinstance(valor, Decimal):
        return float(valor)
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    if isinstance(valor, timedelta):
        return str(valor)
    if isinstance(valor, bytes):
        return valor.decode("utf-8", "replace")
    if isinstance(valor, int) and abs(valor) > 2**53:
        return str(valor)
    return valor


def imprimir_tabela(linhas, limite_col=48):
    if not linhas:
        print("(nenhuma linha)")
        return
    colunas = list(linhas[0].keys())

    def celula(v):
        s = "" if v is None else str(v)
        return s[: limite_col - 1] + "…" if len(s) > limite_col else s

    larguras = {
        c: max(len(c), *(len(celula(l.get(c))) for l in linhas)) for c in colunas
    }
    sep = "-+-".join("-" * larguras[c] for c in colunas)
    print(" | ".join(c.ljust(larguras[c]) for c in colunas))
    print(sep)
    for l in linhas:
        print(" | ".join(celula(l.get(c)).ljust(larguras[c]) for c in colunas))
    print(f"\n({len(linhas)} linha(s))")


def main() -> None:
    p = argparse.ArgumentParser(description="Consulta somente leitura no ERP Big (MariaDB).")
    p.add_argument("sql", nargs="?", help="SQL a executar, ou '-' para ler do stdin")
    p.add_argument("-f", "--arquivo", help="arquivo .sql a executar")
    p.add_argument("--tabelas", metavar="TABELA", help="descreve colunas e índices da tabela")
    p.add_argument("--json", action="store_true", help="saída em JSON em vez de tabela")
    p.add_argument("--limite", type=int, default=200, help="máximo de linhas exibidas (0 = tudo)")
    p.add_argument("--timeout", type=int, default=120, help="timeout de leitura em segundos")
    p.add_argument("--host", default=os.getenv("BIG_HOST", "localhost"))
    p.add_argument("--port", type=int, default=int(os.getenv("BIG_PORT", "3306")))
    p.add_argument("--user", default=os.getenv("BIG_USER"))
    p.add_argument("--password", default=os.getenv("BIG_PASSWORD"))
    p.add_argument("--database", default=os.getenv("BIG_DATABASE", "gerente"))
    args = p.parse_args()

    if not args.user:
        sys.exit("Defina BIG_USER/BIG_PASSWORD (ou passe --user/--password). Use um usuário somente leitura.")

    if args.tabelas:
        if not re.fullmatch(r"[A-Za-z0-9_]+", args.tabelas):
            sys.exit("Nome de tabela inválido.")
        consultas = [
            f"SHOW FULL COLUMNS FROM `{args.tabelas}`",
            f"SHOW INDEX FROM `{args.tabelas}`",
        ]
    else:
        if args.arquivo:
            sql = open(args.arquivo, encoding="utf-8").read()
        elif args.sql == "-" or (args.sql is None and not sys.stdin.isatty()):
            sql = sys.stdin.read()
        elif args.sql:
            sql = args.sql
        else:
            p.error("informe a SQL, -f arquivo, --tabelas, ou envie por stdin")
        validar_somente_leitura(sql)
        consultas = [sql.strip().rstrip(";")]

    conn, nome_driver = conectar(args)
    try:
        for q in consultas:
            cur = abrir_cursor(conn, nome_driver)
            try:
                cur.execute(q)
                colunas = [d[0] for d in cur.description] if cur.description else []
                brutas = cur.fetchall()
            finally:
                cur.close()

            linhas = [
                {c: serializar(v) for c, v in (r.items() if isinstance(r, dict) else zip(colunas, r))}
                for r in brutas
            ]
            if args.limite and len(linhas) > args.limite:
                truncado = len(linhas) - args.limite
                linhas = linhas[: args.limite]
            else:
                truncado = 0

            if len(consultas) > 1:
                print(f"\n== {q} ==")
            if args.json:
                print(json.dumps(linhas, ensure_ascii=False, indent=2, default=str))
            else:
                imprimir_tabela(linhas)
            if truncado:
                print(f"… {truncado} linha(s) omitida(s) — use --limite 0 para ver tudo.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
