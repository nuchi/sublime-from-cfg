from bnf import (
    Nonterminal as NT,
    Terminal as T,
    Alternation,
    Concatenation,
    EMPTY,
    NonLeftRecursiveGrammar
)
from sublime_generator import SublimeSyntax

g = NonLeftRecursiveGrammar({
    NT('START'): Alternation([
        EMPTY,
        Concatenation([T('x', 'entity.name'), NT('CA_or_CB'), NT('START')])
    ]),
    NT('CA_or_CB'): Alternation([
        Concatenation([NT('CA')]),
        Concatenation([NT('CB')]),
    ]),
    NT('CA'): Alternation([Concatenation([T('c', 'ac'), T('a')])], 'variable.function'),
    NT('CB'): Alternation([Concatenation([T('c', 'bc'), T('b')])], 'variable.parameter'),
}, start=NT('START'))

s = SublimeSyntax(g, 'test', ['test'], 'test')
print(s.dump())
