from functools import wraps

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
                    process_item(concat, to_do)
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


def unwrap_alternation(alt):
    if (not isinstance(alt, Alternation) or len(alt.productions) != 1 or len(alt.productions[0].concats) != 1):
        return alt
    return unwrap_alternation(alt.productions[0].concats[0])


def check_type(f):
    @wraps(f)
    def new_f(item, to_do):
        if isinstance(item, Alternation):
            item = unwrap_alternation(item)

        if not isinstance(item,
            (Terminal, Nonterminal, Passive, Repetition, OptionalExpr, Alternation)
        ):
            raise ValueError(f'Bad type for {repr(item)}')
        return f(item, to_do)
    return new_f


@check_type
def process_item(item, to_do):
    if isinstance(item, (Terminal, Nonterminal)):
        return item

    if isinstance(item, Passive):
        return process_passive(item.sub, to_do)

    if isinstance(item, Repetition):
        return process_repetition(item.sub, to_do)

    if isinstance(item, OptionalExpr):
        return process_optional(item.sub, to_do)

    if isinstance(item, Alternation):
        return process_alternation(item, to_do)


@check_type
def process_alternation(item, to_do):
    new_nt = Nonterminal(item.name)
    to_do.append((new_nt, item))
    return new_nt


@check_type
def process_repetition(item, to_do):
    if isinstance(item, (OptionalExpr, Repetition)):
        return process_repetition(item.sub, to_do)

    if isinstance(item, (Terminal, Nonterminal, Alternation, Passive)):
        repetition_nt = Nonterminal(f'/*{item.name}')
        new_rule = Alternation([Concatenation([]), Concatenation([item, repetition_nt])])
        to_do.append((repetition_nt, new_rule))
        return repetition_nt


@check_type
def process_optional(item, to_do):
    if isinstance(item, OptionalExpr):
        return process_optional(item.sub, to_do)

    if isinstance(item, Repetition):
        return process_repetition(item.sub, to_do)

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
            return process_alternation(item, to_do)
        new_alt = Alternation([Concatenation([])] + item.concats, item.meta_scope)
        return process_item(new_alt, to_do)


@check_type
def process_passive(item, to_do):
    if isinstance(item, (OptionalExpr, Repetition)):
        return process_passive(process_item(item, to_do), to_do)

    if isinstance(item, Passive):
        return process_passive(item.sub, to_do)

    if isinstance(item, Terminal):
        return Terminal(item.regex, item.scope, True)

    if isinstance(item, Nonterminal):
        if item.passive:
            return item
        # Note that we do *not* add to the to_do list because we don't need
        # a new rule for the new nonterminal -- we only treat it differently
        # when it appears inside a production.
        return Nonterminal(
            item.name,
            item.args,
            passive=True
        )

    if isinstance(item, Alternation):
        return process_passive(process_item(item, to_do), to_do)
