from collections import defaultdict
from dataclasses import dataclass
import functools
from typing import Optional


class Symbol:
    pass


@dataclass(frozen=True)
class Terminal(Symbol):
    regex: str
    scope: Optional[str] = None
    passive: bool = False

    def __str__(self):
        return ('~' if self.passive else '') \
            + (f"'{self.regex}'") \
            + (f'{{{self.scope}}}' if self.scope else '')


@dataclass(frozen=True)
class Nonterminal(Symbol):
    symbol: str

    def __str__(self):
        return self.symbol


@dataclass
class Concatenation:
    concats: list[Symbol]

    def __str__(self):
        if len(self.concats) == 0:
            return '<empty>'
        return ' '.join([str(sub) for sub in self.concats])

EMPTY = Concatenation([])


@dataclass
class Alternation:
    productions: list[Concatenation]
    meta_scope: Optional[str] = None

    def __str__(self):
        return '\n    | '.join([str(sub) for sub in self.productions])


class NonLeftRecursiveGrammar:
    def __init__(self, rules: dict[Nonterminal, Alternation], start: Nonterminal):
        self.rules = rules
        self.start = start
        self.terminals = set([
            symbol
            for alternation in rules.values()
            for concatenation in alternation.productions
            for symbol in concatenation.concats
            if isinstance(symbol, Terminal)
        ])
        self.recursion_guard = set()
        self.first = {nt: self._get_first_sets(nt) for nt in rules}
        self.follow = self._generate_follow_sets()
        self.table = {
            nt: self._generate_table(
                self.first[nt],
                self.follow[nt],
            )
            for nt in self.rules
        }

    def _generate_table(self, first_sets, follow_set):
        table = defaultdict(set)
        for i, first_set in enumerate(first_sets):
            for s in first_set:
                if s is not None:
                    table[s.regex].add(i)
                else:
                    for t in follow_set:
                        if t is not None:
                            table[t.regex].add(i)
        return table

    def _get_first_set_for_string(self, symbols):
        symbols = symbols[:]
        first_set = set()
        possible_empty = True
        while symbols:
            next_first_sets = self._get_first_sets(symbols.pop(0))
            next_first_set = set.union(*next_first_sets)
            first_set.update(next_first_set)
            if None not in first_set:
                possible_empty = False
                break
        if possible_empty:
            first_set.add(None)
        return first_set

    @functools.lru_cache()
    def _get_first_sets(self, symbol):
        if symbol in self.recursion_guard:
            recursed_symbols = ", ".join([t.symbol for t in self.recursion_guard])
            raise ValueError(f'Left recursion detected: {recursed_symbols}')
        self.recursion_guard.add(symbol)

        if isinstance(symbol, Terminal):
            return [set([Terminal(symbol.regex, None)])]

        first_sets = [
            self._get_first_set_for_string(production.concats)
            for production in self.rules[symbol].productions
        ]

        self.recursion_guard.discard(symbol)
        return first_sets

    def _generate_follow_sets(self):
        follow_sets = {nt: set() for nt in self.rules}
        old_sum = -1
        new_sum = 0
        while old_sum != new_sum:
            old_sum = new_sum

            for nt in self.rules:
                follow_set = follow_sets[nt]
                if nt == self.start:
                    follow_set.add(None)
                productions = [
                    (symbol, production)
                    for symbol, alternation in self.rules.items()
                    for production in alternation.productions
                    if nt in production.concats
                ]
                for symbol, production in productions:
                    for i, concat in enumerate(production.concats):
                        if concat != nt:
                            continue
                        remainder = production.concats[i+1:]
                        remainder_first_set = self._get_first_set_for_string(remainder)
                        follow_set.update(remainder_first_set.difference([None]))
                        if None in remainder_first_set:
                            follow_set.update(follow_sets[symbol])

            new_sum = sum(len(s) for s in follow_sets.values())
        return follow_sets
