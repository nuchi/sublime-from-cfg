from collections import defaultdict
from contextlib import contextmanager
from dataclasses import replace
import functools

from .types import Terminal, Nonterminal, Alternation


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
        self.first = {
            nt: self._get_first_sets(nt)
            for nt_ in self.rules
            for nt in (nt_, Nonterminal(nt_.symbol, nt_.args, passive=True))
        }
        self.follow = self._generate_follow_sets()
        self.table = {
            nt: self._generate_tables(
                self.first[nt],
                self.follow[nt],
            )
            for nt_ in self.rules
            for nt in (nt_, Nonterminal(nt_.symbol, nt_.args, passive=True))
        }
        self.sort_table = {}
        for t in self.terminals:
            if 'sort' in t.option_kv:
                value = t.option_kv['sort']
                try:
                    sort_value = int(value)
                except ValueError:
                    raise ValueError(f'"sort" option should specify an integer, found {value}')
                self.sort_table[t.regex] = sort_value

    def _generate_tables(self, first_sets, follow_set):
        table = defaultdict(set)
        passives_table = defaultdict(set)
        first_plus_follow = [
            fs if None not in fs else fs.union(follow_set).difference({None})
            for fs in first_sets
        ]
        for i, first_set in enumerate(first_plus_follow):
            for s in first_set:
                if s.passive:
                    passives_table[s.regex].add(i)
                else:
                    table[s.regex].add(i)
        return (table, passives_table)

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
                non_passive_nt = replace(symbol, passive=False)
                first_sets = self._get_first_sets(non_passive_nt)
                first_sets = [
                    set([
                        None if t is None else Terminal(t.regex, passive=True)
                        for t in fs
                    ])
                    for fs in first_sets
                ]
                return first_sets

            first_sets = [
                self._get_first_set_for_string(production.concats)
                for production in self.rules[symbol].productions
            ]

            return first_sets

    def _generate_follow_sets(self):
        nonpassive_and_passive = set(self.rules)
        for nt in self.rules:
            passive_nt = replace(nt, passive=True)
            nonpassive_and_passive.add(passive_nt)

        follow_sets = {nt: set() for nt in nonpassive_and_passive}

        old_sum = -1
        new_sum = 0
        while old_sum != new_sum:
            old_sum = new_sum

            for nt in nonpassive_and_passive:
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
