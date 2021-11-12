from functools import wraps

from bnf import (
    Terminal, Nonterminal, Concatenation, Alternation,
)
from parse_sbnf import (
    Repetition, OptionalExpr, Passive
)

NO_PROTO = 'include-prototype: false'


def process_alternation_items(nt, alt, to_do):
    proto = alt.option_kv.get('include-prototype') != 'false'
    return Alternation(
        productions=[
            Concatenation([
                process_item(concat, to_do, proto)
                for concat in production.concats
            ])
            for production in alt.productions
        ],
        options=alt.options,
    )


def unwrap_alternation(alt):
    if (
        not isinstance(alt, Alternation)
        or len(alt.productions) != 1
        or len((s := alt.productions[0].concats)) != 1
        or (isinstance(s[0], Terminal) and s[0].passive)
    ):
        return alt
    return unwrap_alternation(alt.productions[0].concats[0])


def check_type(f):
    @wraps(f)
    def new_f(item, to_do, proto):
        if isinstance(item, Alternation):
            item = unwrap_alternation(item)

        if not isinstance(item,
            (Terminal, Nonterminal, Passive, Repetition, OptionalExpr, Alternation)
        ):
            raise ValueError(f'Bad type for {repr(item)}')
        return f(item, to_do, proto)
    return new_f


@check_type
def process_item(item, to_do, proto):
    if isinstance(item, (Terminal, Nonterminal)):
        return item

    if isinstance(item, Passive):
        return process_passive(item.sub, to_do, proto)

    if isinstance(item, Repetition):
        return process_repetition(item.sub, to_do, proto)

    if isinstance(item, OptionalExpr):
        return process_optional(item.sub, to_do, proto)

    if isinstance(item, Alternation):
        return process_alternation(item, to_do, proto)


@check_type
def process_alternation(item, to_do, proto):
    new_nt = Nonterminal(item.name)
    to_do.append((new_nt, item))
    return new_nt


@check_type
def process_repetition(item, to_do, proto):
    if isinstance(item, (OptionalExpr, Repetition)):
        return process_repetition(item.sub, to_do, proto)

    if isinstance(item, (Terminal, Nonterminal, Alternation, Passive)):
        repetition_nt = Nonterminal(f'/*{item.name}')
        new_rule = Alternation(
            [
                Concatenation([item, repetition_nt]),
                Concatenation([]),
            ],
            None if proto else NO_PROTO
        )
        to_do.append((repetition_nt, new_rule))
        return repetition_nt


@check_type
def process_optional(item, to_do, proto):
    if isinstance(item, OptionalExpr):
        return process_optional(item.sub, to_do, proto)

    if isinstance(item, Repetition):
        return process_repetition(item.sub, to_do, proto)

    if isinstance(item, Passive):
        processed_subitem = process_passive(item.sub, to_do, proto)
        return process_optional(processed_subitem, to_do, proto)

    if isinstance(item, (Terminal, Nonterminal)):
        opt_nt = Nonterminal(f'/opt/{item.name}')
        new_rule = Alternation(
            [
                Concatenation([item]),
                Concatenation([]),
            ],
            None if proto else NO_PROTO
        )
        to_do.append((opt_nt, new_rule))
        return opt_nt

    if isinstance(item, Alternation):
        if any(len(prod.concats) == 0 for prod in item.productions):
            return process_alternation(item, to_do, proto)
        new_alt = Alternation(
            item.productions + [Concatenation([])],
            item.options
        )
        return process_item(new_alt, to_do, proto)


@check_type
def process_passive(item, to_do, proto):
    if isinstance(item, (OptionalExpr, Repetition)):
        return process_passive(process_item(item, to_do, proto), to_do, proto)

    if isinstance(item, Passive):
        return process_passive(item.sub, to_do, proto)

    if isinstance(item, Terminal):
        item = Terminal(item.regex, item.options, True, embed=item.embed, include=item.include)
        return process_passive(
            Alternation(
                [Concatenation([item])],
                None if proto else NO_PROTO,
            ), to_do, proto)

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
        return process_passive(process_item(item, to_do, proto), to_do, proto)
