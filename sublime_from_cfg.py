from bnf import NonLeftRecursiveGrammar, Nonterminal
from parse_sbnf import SbnfParser
from simplify_grammar import process_alternation_items
from transform_grammar import transform_grammar, apply_prototype
from sublime_generator import SublimeSyntax


def sublime_from_cfg(text):
    parser = SbnfParser(text)

    main_rules = parser.actual_rules['main']
    proto_rules = parser.actual_rules['prototype']

    if proto_rules:
        transformed_main_rules = transform_grammar(
            main_rules, (process_alternation_items,)# apply_prototype)
        )
        transformed_proto_rules = transform_grammar(
            proto_rules, (process_alternation_items,))
    else:
        transformed_main_rules = transform_grammar(
            main_rules, (process_alternation_items,))
        transformed_proto_rules = {}

    combined_rules = {**transformed_main_rules, **transformed_proto_rules}

    grammar = NonLeftRecursiveGrammar(combined_rules, start=Nonterminal('main'))
    ss = SublimeSyntax(grammar, 'test', ['test'], 'test')
    return ss
