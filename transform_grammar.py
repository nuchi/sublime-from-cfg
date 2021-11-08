from typing import Callable

from bnf import Nonterminal, Alternation, Concatenation


def transform_grammar(
    grammar: dict[Nonterminal, Alternation],
    transforms: Callable[
        [Nonterminal, Alternation, list[tuple[Nonterminal, Alternation]]],
        Alternation
    ],
) -> dict[Nonterminal, Alternation]:
    """
    Applies a number of "compiler passes" to the input grammar
    """
    for transform in transforms:
        generated_rules = {}
        to_do = list(grammar.items())
        while to_do:
            nt, alternation = to_do.pop(0)
            generated_rules[nt] = transform(nt, alternation, to_do)
        grammar = generated_rules

    return grammar


def apply_prototype(nt, alt, to_do):
    if alt.option_kv.get('include-prototype') == 'false':
        return alt

    new_productions = []
    for prod in alt.productions:
        new_prod = []
        if nt == Nonterminal('main'):
            new_prod.append(Nonterminal('prototype'))
        for concat in prod.concats:
            new_prod.extend([concat, Nonterminal('prototype')])
        new_productions.append(Concatenation(new_prod))
    return Alternation(new_productions, options=alt.options)
