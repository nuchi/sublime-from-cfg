from sublime_from_cfg import sublime_from_cfg

text = """
main : line*;

line : xs ca-or-cb
     | string
     ;

string{string.quoted, include-prototype: false} :
    `"`{punctuation.definition.string.begin}
    ~`"`{punctuation.definition.string.end}
    ;

xs : <> | 'x'{entity.name} xs ;

ca-or-cb : ca
         | cb
         ;

ca{variable.function}  : 'c'{ac} 'a' ;
cb{variable.parameter} : 'c'{bc} 'b' ;

prototype : comment* ;
comment{comment.line.number-sign} : '#+'{punctuation.definition.comment}
                                    ~'$\n?'
                                  ;
"""

ss = sublime_from_cfg(text)
print(ss.dump())




