from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
import functools
from hashlib import sha256
from typing import Optional, Union


class Expression:
    @property
    def name(self):
        self_hash = sha256(
            repr(self).encode('utf8')).hexdigest()[:7]
        return f'{self._name}/{self_hash}'


class Symbol(Expression):
    pass


class OptionsHaver:
    @property
    def _options_list(self):
        if self.options is None:
            return []
        return [o.strip() for o in self.options.split(',')]

    @property
    def option_kv(self):
        ret = {}
        for kv in self._options_list:
            if ':' not in kv:
                continue
            k, v = kv.split(':', 1)
            ret[k.strip()] = v.strip()
        return ret

    @property
    def option_list(self):
        return [o for o in self._options_list if ':' not in o]


@dataclass(frozen=True)
class Terminal(Symbol, OptionsHaver):
    regex: str
    options: Optional[str] = None
    passive: bool = False
    embed: tuple[str, str] = None
    include: tuple[str, str] = None

    def __str__(self):
        return ('~' if self.passive else '') \
            + (f"'{self.regex}'") \
            + (f'{{{self.scope}}}' if self.scope else '')

    @property
    def _name(self):
        return '/T'


@dataclass(frozen=True)
class Nonterminal(Symbol):
    symbol: str
    args: tuple[Union['Nonterminal', str]] = tuple()
    passive: bool = False

    @property
    def name(self):
        if len(self.args) == 0 and not self.passive:
            if self.symbol in ('main', 'prototype'):
                return f'{self.symbol}/'
            return self.symbol
        return super().name

    @property
    def _name(self):
        return self.symbol

    def __str__(self):
        return self.name


@dataclass(frozen=True)
class Concatenation(Expression):
    concats: list[Symbol]

    def __str__(self):
        if len(self.concats) == 0:
            return '<empty>'
        return ' '.join([str(sub) for sub in self.concats])

    @property
    def _name(self):
        return '/cat'


EMPTY = Concatenation([])


@dataclass(frozen=True)
class Alternation(Expression, OptionsHaver):
    productions: list[Concatenation]
    options: Optional[str] = None

    def __str__(self):
        return '\n    | '.join([str(sub) for sub in self.productions])

    @property
    def _name(self):
        return '/alt'


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
        self._recursion_guard_list = []
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
                    if s.passive:
                        table[r'\S'].add(i)
                else:
                    for t in follow_set:
                        if t is not None:
                            table[t.regex].add(i)
                            if t.passive:
                                table[r'\S'].add(i)
        return table

    def _get_first_set_for_string(self, symbols):
        symbols = symbols[:]
        first_set = set()
        possible_empty = True
        while len(symbols) > 0:
            next_symbol = symbols.pop(0)
            next_first_sets = self._get_first_sets(next_symbol)
            next_first_set = set.union(*next_first_sets)
            first_set.update(next_first_set)
            if None not in first_set:
                possible_empty = False
                break
            first_set.discard(None)
        if possible_empty:
            first_set.add(None)

        return first_set

    @contextmanager
    def _recursion_guard(self, symbol):
        if symbol in self._recursion_guard_list:
            recursed_symbols = ", ".join([repr(t) for t in self._recursion_guard_list])
            raise ValueError(f'Left recursion detected on {repr(symbol)}: {recursed_symbols}')
        try:
            self._recursion_guard_list.append(symbol)
            yield
        finally:
            self._recursion_guard_list = [t for t in self._recursion_guard_list if t != symbol]

    @functools.lru_cache()
    def _get_first_sets(self, symbol):
        with self._recursion_guard(symbol):
            if isinstance(symbol, Terminal):
                return [set([Terminal(symbol.regex, passive=symbol.passive)])]

            if symbol.passive:
                non_passive_nt = Nonterminal(symbol.symbol, symbol.args, False)
                first_sets = self._get_first_sets(non_passive_nt)
                first_set = set.union(*first_sets)
                first_set.add(Terminal(r'\S', passive=True))
                return [first_set]

            first_sets = [
                self._get_first_set_for_string(production.concats)
                for production in self.rules[symbol].productions
            ]

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
