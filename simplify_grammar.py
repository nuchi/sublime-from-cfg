from bnf import (
    Terminal, Nonterminal, Concatenation, Alternation,
    NonLeftRecursiveGrammar,
)
from parse_sbnf import (
    Repetition, OptionalExpr, Passive
)


def simplify_grammar(grammar):
    """
    Can be an "ebnf" grammar, where the alternates are still
    concatenations but the individual symbols might be Optionals
    or Repetitions or Passives or entire subexpressions.
    """
    generated_rules = {}
    to_do = list(grammar.items())
    while to_do:
        nt, alternation = to_do.pop(0)
        generated_rules[nt] = Alternation(
            productions=[
                Concatenation([
                    process_item(concat, grammar, to_do)
                    for concat in production.concats
                ])
                for production in alternation.productions
            ],
            meta_scope=alternation.meta_scope,
        )

    return NonLeftRecursiveGrammar(
        generated_rules,
        start=Nonterminal('main')
    )


def process_item(item, grammar, to_do):
    if isinstance(item, (Terminal, Nonterminal)):
        return item

    if isinstance(item, Passive):
        return process_passive(item.sub, grammar, to_do)

    if isinstance(item, Repetition):
        return process_repetition(item.sub, grammar, to_do)

    if isinstance(item, OptionalExpr):
        return process_optional(item.sub, grammar, to_do)

    if isinstance(item, Alternation):
        return process_alternation(item, grammar, to_do)

    raise ValueError(f"Can't handle {item.__class__.__name__} yet")


def process_alternation(item, grammar, to_do):
    new_nt = Nonterminal(item.name)
    to_do.append((new_nt, item))
    return new_nt


def process_repetition(item, grammar, to_do):
    if isinstance(item, (OptionalExpr, Repetition)):
        return process_repetition(item.sub, grammar, to_do)

    if isinstance(item, Passive):
        processed_subitem = process_passive(item.sub)
        return process_repetition(processed_subitem)

    if isinstance(item, (Terminal, Nonterminal)):
        repetition_nt = Nonterminal(f'/*/{item.name}')
        new_rule = Alternation([Concatenation([]), Concatenation([item, repetition_nt])])
        to_do.append((repetition_nt, new_rule))
        return repetition_nt

    if isinstance(item, Alternation):
        return process_repetition(process_alternation(item, to_do, grammar), to_do, grammar)

    raise ValueError(f"*: Can't handle {item.__class__.__name__} yet")


def process_optional(item, grammar, to_do):
    if isinstance(item, OptionalExpr):
        return process_optional(item.sub, grammar, to_do)

    if isinstance(item, Repetition):
        return process_repetition(item.sub, grammar, to_do)

    if isinstance(item, Passive):
        processed_subitem = process_passive(item.sub)
        return process_optional(processed_subitem)

    if isinstance(item, (Terminal, Nonterminal)):
        opt_nt = Nonterminal(f'/opt/{item.name}')
        new_rule = Alternation([Concatenation([]), Concatenation([item])])
        to_do.append((opt_nt, new_rule))
        return opt_nt

    if isinstance(item, Alternation):
        if any(len(prod.concats) == 0 for prod in item.productions):
            return process_alternation(item, grammar, to_do)
        new_alt = Alternation([Concatenation([])] + item.concats, item.meta_scope)
        return process_alternation(new_alt, grammar, to_do)


def process_passive(item, grammar, to_do):
    if isinstance(item, Passive):
        return process_passive(item.sub, grammar, to_do)

    if isinstance(item, Terminal):
        return Terminal(item.regex, item.scope, True)

    raise ValueError("Can't handle passives")
    # if isinstance(item, Nonterminal):
    #     if item.name.startswith('/~'):
    #         return item
    #     if (item.symbol, item.args) not in grammar:
    #         print(repr(item))
    #         raise ValueError('****************')
    #     rule = grammar[(item.symbol, item.args)]
    #     new_name = f'~{item.name}'

    # if isinstance(item, Alternation):
    #     return process_alternation(Alternation([
    #         Concatenation([Passive(productions.concats[0])] + production.concats[1:]) \
    #             if len(productions.concats) > 0 else Concatenation([])
    #         for production in item.productions
    #     ], item.meta_scope), grammar, to_do)

    # return process_passive(process_item(item, grammar, to_do), grammar, to_do)
