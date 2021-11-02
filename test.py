from bnf import (
    Nonterminal,
    Terminal,
    Alternation,
    Concatenation,
    EMPTY,
    NonLeftRecursiveGrammar
)
from sublime_generator import SublimeSyntax

# n1 = Nonterminal('S')
# n2 = Nonterminal('A')
# n3 = Nonterminal('B')
# t1 = Terminal('a', 'region.yellowish')
# t2 = Terminal('a', 'region.bluish')
# z1 = Terminal('b', 'region.yellowish')
# z2 = Terminal('b', 'region.bluish')
# d1 = Alternation([Concatenation([n2]), Concatenation([n3])], None)
# d2 = Alternation([Concatenation([t1, n2, z1]), EMPTY], 'scope_A')
# d3 = Alternation([Concatenation([t2, n3, z2, z2]), EMPTY], 'scope_B')
# g = NonLeftRecursiveGrammar({n1: d1, n2: d2, n3: d3}, n1)

# S = Nonterminal('S')
# Sl = Nonterminal('Sl')
# Sr = Nonterminal('Sr')
# F = Nonterminal('F')
# a = Terminal('a', None)
# lpar = Terminal(r'\(', None)
# rpar = Terminal(r'\)', None)
# plus = Terminal(r'\+', None)
# g = NonLeftRecursiveGrammar({
#     S: Alternation([
#             Concatenation([F]),
#             Concatenation([lpar, Sl, plus, Sr, rpar]),
#         ]),
#     F: Alternation([Concatenation([a])]),
#     Sl: Alternation([Concatenation([S])], 'region.yellowish'),
#     Sr: Alternation([Concatenation([S])], 'region.bluish'),
# }, S)

# START = Nonterminal('S')
# AB = Nonterminal('AB')
# AC = Nonterminal('AC')
# AB_or_AC = Nonterminal('AB_or_AC')
# a = Terminal('a')
# b = Terminal('b')
# c = Terminal('c')
# g = NonLeftRecursiveGrammar({
#     START: Alternation([
#         EMPTY,
#         Concatenation([AB_or_AC, START])
#     ]),
#     AB_or_AC: Alternation([
#         Concatenation([AB]),
#         Concatenation([AC]),
#     ]),
#     AB: Alternation([Concatenation([a, b])], 'region.yellowish'),
#     AC: Alternation([Concatenation([a, c])], 'region.bluish'),
# }, start=START)

START = Nonterminal('S')
a = Terminal('a')
b = Terminal('b')
c = Terminal('c')
g = NonLeftRecursiveGrammar({
    START: Alternation([
        Concatenation([a, b]),
        Concatenation([a, c]),
    ]),
}, start=START)

s = SublimeSyntax(g, 'test', ['test'], 'test')
print(s.dump())
