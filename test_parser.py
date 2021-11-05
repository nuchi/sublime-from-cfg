from parse_sbnf import SbnfParser
from sublime_generator import SublimeSyntax

text = """
main : <>
     | xs ca-or-cb main
     ;

xs : 'x'{entity.name}
   | 'x'{entity.name} xs
   ;

ca-or-cb : ca
         | cb
         ;

ca{variable.function}  : 'c'{ac} 'a' ;
cb{variable.parameter} : 'c'{bc} 'b' ;
"""

parser = SbnfParser(text)
ss = SublimeSyntax(parser.grammar, 'test', ['test'], 'test')
print(ss.dump())
