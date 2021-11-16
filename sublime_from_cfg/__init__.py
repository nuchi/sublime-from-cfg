from dataclasses import dataclass, replace

from .bnf import NonLeftRecursiveGrammar, Nonterminal
from .parse_sbnf import SbnfParser
from .transform_grammar import transform_grammar
from .sublime_generator import SublimeSyntax


def sublime_from_cfg(text, global_args, options):
    parser = SbnfParser(text, global_args)
    combined_rules = parser.combined_rules
    options = replace(options, **parser.options)
    grammar = NonLeftRecursiveGrammar(combined_rules, start=Nonterminal('main'))
    ss = SublimeSyntax(grammar, options)
    return ss
