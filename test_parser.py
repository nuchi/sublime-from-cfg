from parse_sbnf import SbnfParser
from sublime_generator import SublimeSyntax

text = """
main : <>  # sbnf syntax extension: <> is the empty production
     | line main
     ;

line : xs ca-or-cb
     | string
     ;

string{string.quoted} :
    QUOTE{punctuation.definition.string.begin}
    ~QUOTE{punctuation.definition.string.end}
    ;

QUOTE = `"`

xs : 'x'{keyword.operator}
   | ~'x'{entity.name} xs
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
