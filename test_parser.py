from parse_sbnf import SbnfParser
from simplify_grammar import simplify_grammar
from sublime_generator import SublimeSyntax

text = """
main : line* ;

line : xs ca-or-cb
     | string
     ;

string{string.quoted} :
    `"`{punctuation.definition.string.begin}
    ~`"`{punctuation.definition.string.end}
    ;

xs : (~'x'{entity.name})* ;

ca-or-cb : ca
         | cb
         ;

ca{variable.function}  : 'c'{ac} '(x)(y)(z)'{1: region.redish, 2: region.bluish, 3: region.greenish} ;
cb{variable.parameter} : 'c'{bc} 'b' ;
"""

parser = SbnfParser(text)
grammar = simplify_grammar(parser.actual_rules)
ss = SublimeSyntax(grammar, 'test', ['test'], 'test')
print(ss.dump())




