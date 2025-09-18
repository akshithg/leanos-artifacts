#!/usr/bin/env python3
# pip install python-sat[pblib,aiger]
#
# Usage:
#   echo -e "CONFIG_A\nCONFIG_B || CONFIG_C\nCONFIG_C && CONFIG_D" | python config_solver_maxsat.py
#   # or from a file:
#   python config_solver_maxsat.py -f exprs.txt

import argparse
import re
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional

from pysat.examples.rc2 import RC2
from pysat.formula import WCNF

# ---- Lexer / Parser ----

TOK_VAR = re.compile(r"CONFIG_[A-Za-z0-9_]+")
WHITESPACE = set(" \t\r\n")


def tokenize(s: str) -> List[str]:
    out = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c in WHITESPACE:
            i += 1
            continue
        if s.startswith("&&", i):
            out.append("&&")
            i += 2
            continue
        if s.startswith("||", i):
            out.append("||")
            i += 2
            continue
        if c in "!()":
            out.append(c)
            i += 1
            continue
        m = TOK_VAR.match(s, i)
        if m:
            out.append(m.group(0))
            i = m.end()
            continue
        raise ValueError(f"Unexpected token near: {s[i : i + 16]!r}")
    return out


# Grammar:
#   expr  := term ( '||' term )*
#   term  := factor ( '&&' factor )*
#   factor:= '!' factor | '(' expr ')' | VAR


@dataclass
class Node:
    pass


@dataclass
class Var(Node):
    name: str


@dataclass
class Not(Node):
    a: Node


@dataclass
class And(Node):
    a: Node
    b: Node


@dataclass
class Or(Node):
    a: Node
    b: Node


class Parser:
    def __init__(self, tokens: List[str]):
        self.toks = tokens
        self.i = 0

    def peek(self) -> Optional[str]:
        return self.toks[self.i] if self.i < len(self.toks) else None

    def eat(self, t: str = None) -> str:
        if self.i >= len(self.toks):
            raise ValueError("Unexpected end")
        tok = self.toks[self.i]
        if t is not None and tok != t:
            raise ValueError(f"Expected {t}, got {tok}")
        self.i += 1
        return tok

    def parse(self) -> Node:
        node = self.expr()
        if self.peek() is not None:
            raise ValueError(f"Extra tokens at end: {self.peek()}")
        return node

    def expr(self) -> Node:
        n = self.term()
        while self.peek() == "||":
            self.eat("||")
            n = Or(n, self.term())
        return n

    def term(self) -> Node:
        n = self.factor()
        while self.peek() == "&&":
            self.eat("&&")
            n = And(n, self.factor())
        return n

    def factor(self) -> Node:
        t = self.peek()
        if t == "!":
            self.eat("!")
            return Not(self.factor())
        if t == "(":
            self.eat("(")
            n = self.expr()
            self.eat(")")
            return n
        if t and TOK_VAR.fullmatch(t):
            return Var(self.eat())
        raise ValueError(f"Bad factor at {t!r}")


# ---- Tseitin CNF ----


class Tseitin:
    def __init__(self):
        self.var_ids: Dict[str, int] = {}
        self.rev: Dict[int, str] = {}
        self._next = 1
        self.clauses: List[List[int]] = []

    def lit(self, name: str) -> int:
        if name not in self.var_ids:
            vid = self._next
            self._next += 1
            self.var_ids[name] = vid
            self.rev[vid] = name
        return self.var_ids[name]

    def fresh(self) -> int:
        vid = self._next
        self._next += 1
        return vid

    def encode(self, node: Node) -> int:
        if isinstance(node, Var):
            return self.lit(node.name)
        if isinstance(node, Not):
            a = self.encode(node.a)
            y = self.fresh()
            # y <-> ~a  ==  (¬y ∨ ¬a) ∧ (y ∨ a)
            self.clauses += [[-y, -a], [y, a]]
            return y
        if isinstance(node, And):
            a = self.encode(node.a)
            b = self.encode(node.b)
            y = self.fresh()
            # y <-> (a & b) == (¬y ∨ a) ∧ (¬y ∨ b) ∧ (y ∨ ¬a ∨ ¬b)
            self.clauses += [[-y, a], [-y, b], [y, -a, -b]]
            return y
        if isinstance(node, Or):
            a = self.encode(node.a)
            b = self.encode(node.b)
            y = self.fresh()
            # y <-> (a | b) == (¬y ∨ a ∨ b) ∧ (y ∨ ¬a) ∧ (y ∨ ¬b)
            self.clauses += [[-y, a, b], [y, -a], [y, -b]]
            return y
        raise TypeError(node)


# ---- Building and solving ----


def main():
    ap = argparse.ArgumentParser(
        description="Min-true CONFIG solver via MaxSAT (PySAT RC2)."
    )
    ap.add_argument(
        "-f",
        "--file",
        help="file with expressions (one per line). Use stdin if omitted.",
    )
    ap.add_argument(
        "--show-model",
        action="store_true",
        help="print full truth assignment, not just true vars",
    )
    args = ap.parse_args()

    lines = []
    if args.file:
        with open(args.file, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
    else:
        lines = sys.stdin.readlines()

    exprs = []
    for raw in lines:
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        exprs.append(s)

    if not exprs:
        print("No expressions supplied.", file=sys.stderr)
        sys.exit(1)

    ts = Tseitin()
    tops = []
    for e in exprs:
        rpn = tokenize(e)
        ast = Parser(rpn).parse()
        top = ts.encode(ast)
        tops.append(top)

    # Build WCNF: hard clauses = Tseitin constraints + [top] for each expression
    w = WCNF()
    for c in ts.clauses:
        w.append(c)  # hard
    for t in tops:
        w.append([t])  # enforce each expression is true

    # Soft clauses: prefer each CONFIG var to be False => add (¬X) with weight 1
    for name, vid in sorted(ts.var_ids.items(), key=lambda kv: kv[0]):
        w.append([-vid], weight=1)

    # Solve
    with RC2(w) as rc2:
        model = rc2.compute()  # list of ints with signs

    if model is None:
        print("UNSAT — no assignment satisfies all expressions")
        sys.exit(2)

    # Extract assignment for the named CONFIG variables (exclude Tseitin aux vars)
    mset = set(model)
    true_vars = []
    full = []
    max_vid_named = max(ts.var_ids.values()) if ts.var_ids else 0
    for name, vid in sorted(ts.var_ids.items(), key=lambda kv: kv[0]):
        val = vid in mset
        full.append((name, val))
        if val:
            true_vars.append(name)

    print(f"Minimal #true = {len(true_vars)}")
    print("True CONFIGs:", " ".join(true_vars) if true_vars else "(none)")
    if args.show_model:
        print("Assignment:")
        for name, val in full:
            print(f"  {name} = {int(val)}")


if __name__ == "__main__":
    main()
