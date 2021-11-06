from parse_sbnf import SbnfParser
from simplify_grammar import simplify_grammar
from sublime_generator import SublimeSyntax

# text = """
# main : <>  # sbnf syntax extension: <> is the empty production
#      | line main
#      ;

# line : xs ca-or-cb
#      | string
#      ;

# string{string.quoted} :
#     `"`{punctuation.definition.string.begin}
#     ~`"`{punctuation.definition.string.end}
#     ;

# xs : 'x'{keyword.operator}
#    | ~'x'{entity.name} xs
#    ;

# ca-or-cb : ca
#          | cb
#          ;

# ca{variable.function}  : 'c'{ac} 'a' ;
# cb{variable.parameter} : 'c'{bc} 'b' ;
# """

text = """
main :  `d`? xxxx* (`e` | `f`);

xxxx : `a`{keyword.operator}
     | `b`{variable.function}
     | `c`{variable.parameter}
     ;
"""

parser = SbnfParser(text)
grammar = simplify_grammar(parser.actual_rules)
ss = SublimeSyntax(grammar, 'test', ['test'], 'test')
print(ss.dump())




