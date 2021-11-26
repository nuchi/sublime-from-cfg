from dataclasses import replace
from typing import Callable

from .types import (
    Nonterminal, Alternation, Concatenation, Skip,
    Repetition, OptionalExpr, Passive
)

NO_PROTO = 'include-prototype: false'


def transform_grammar(
    grammar: dict[Nonterminal, Alternation],
) -> dict[Nonterminal, Alternation]:
    """
    Applies a number of "compiler passes" to the input grammar
    """
    generated_rules = {}
    to_do = list(grammar.items())

    while to_do:
        nt, alternation = to_do.pop(0)
        for transform in (
            expand_passives,
            rewrite_optional,
            rewrite_repetition,
            rewrite_alternation,
            collapse_passives,
        ):
            alternation = transform(nt, alternation, to_do)
        generated_rules[nt] = alternation

    # Rewrite names:
    # rewrite x : y
    #         y : ... y ...
    #         z : ... y ...
    #         w : ... x ...
    # as:
    #         x : ... x ...
    #         z : ... x ...
    #         w : ... x ...
    # when x doesn't have meta scope
    to_change = {}
    for x, alt in generated_rules.items():
        if (alt.options is None
                and len((prods := alt.productions)) == 1
                and len((concats := prods[0].concats)) == 1
                and isinstance((y := concats[0]), Nonterminal)
                and not y.passive):
            to_change[y] = x
    for y, x in to_change.items():
        generated_rules[x] = generated_rules[y]
        del generated_rules[y]
        for alternation in generated_rules.values():
            for production in alternation.productions:
                for i in range(len(production.concats)):
                    if isinstance(production.concats[i], Nonterminal) \
                            and production.concats[i] == y:
                        production.concats[i] = x

    return generated_rules


def expand_passives(nt, alt, to_do):
    def expand(expr):
        if not isinstance(expr, Passive):
            return [expr]
        return [Skip(), expr.sub]

    return replace(alt, productions=[
        Concatenation([item for old_item in production.concats for item in expand(old_item)])
        for production in alt.productions
    ])


def rewrite_optional(nt, alt, to_do):
    def expand(expr):
        if not isinstance(expr, OptionalExpr):
            return expr
        opt_nt = Nonterminal(f'/opt/{expr.name}')
        to_do.append((opt_nt, Alternation([
            Concatenation([]), Concatenation([expr.sub])],
            None if alt.proto else NO_PROTO)))
        return opt_nt

    return replace(alt, productions=[
        Concatenation([expand(item) for item in production.concats])
        for production in alt.productions
    ])


def rewrite_repetition(nt, alt, to_do):
    num = 0
    productions = []
    for prod in alt.productions:
        new_prod = []
        for i, concat in enumerate(prod.concats):
            if not isinstance(concat, Repetition):
                new_prod.append(concat)
            else:
                sub = concat.sub
                while isinstance(sub, Repetition):
                    sub = sub.sub
                new_nt = Nonterminal(f'/*-{num}/{nt.name}')
                num += 1
                new_prod.append(new_nt)
                to_do.append((new_nt, Alternation(
                    [
                        Concatenation(prod.concats[i+1:]),
                        Concatenation([sub, new_nt])
                    ],
                    None if alt.proto else NO_PROTO
                )))
                break
        productions.append(Concatenation(new_prod))
    return replace(alt, productions=productions)


def rewrite_alternation(nt, alt, to_do):
    def replace_alt(expr):
        nonlocal num
        if not isinstance(expr, Alternation):
            return expr
        new_nt = Nonterminal(f'/alt-{num}/{nt.name}')
        to_do.append((new_nt, replace(
            expr, options=None if alt.proto else NO_PROTO)))
        num += 1
        return new_nt

    num = 0
    return replace(alt, productions=[
        Concatenation([replace_alt(c) for c in production.concats])
        for production in alt.productions
    ])


def collapse_passives(nt, alt, to_do):
    productions = []
    for prod in alt.productions:
        new_prod = []
        for concat in prod.concats[::-1]:
            if isinstance(concat, Skip):
                new_prod[0] = replace(new_prod[0], passive=True)
            else:
                new_prod.insert(0, concat)
        productions.append(Concatenation(new_prod))
    return replace(alt, productions=productions)
