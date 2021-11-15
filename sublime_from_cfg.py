from dataclasses import replace

from bnf import NonLeftRecursiveGrammar, Nonterminal
from parse_sbnf import SbnfParser
from transform_grammar import transform_grammar
from sublime_generator import SublimeSyntax


def sublime_from_cfg(text):
    parser = SbnfParser(text)

    main_rules = parser.actual_rules['main']
    proto_rules = parser.actual_rules['prototype']

    transformed_main_rules = transform_grammar(main_rules)

    if proto_rules:
        transformed_proto_rules = transform_grammar(proto_rules)
    else:
        transformed_proto_rules = {}

    combined_rules = {**transformed_main_rules, **transformed_proto_rules}
    grammar = NonLeftRecursiveGrammar(combined_rules, start=Nonterminal('main'))
    ss = SublimeSyntax(grammar, 'test', ['test'], 'test')
    return ss
