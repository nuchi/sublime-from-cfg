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
        Concatenation([NT('LINE'), NT('START')])
    ]),
    NT('LINE'): Alternation([
        Concatenation([NT('XS'), NT('CA_or_CB')]),
        Concatenation([NT('STRING')]),
    ]),
    NT('STRING'): Alternation([
        Concatenation([T('"'), NT('PASS_QUOTE')]),
    ], 'string.quoted'),
    NT('PASS_QUOTE'): Alternation([
        Concatenation([T('"', passive=True)]),
    ]),
    NT('XS'): Alternation([
        Concatenation([T('x', 'keyword.operator')]),
        Concatenation([T('x', 'entity.name', passive=True), NT('XS')]),
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
