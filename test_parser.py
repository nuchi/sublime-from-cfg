from sublime_from_cfg import sublime_from_cfg

# text = r"""
# main : pattern ;
# line : pattern `;` ;
# pattern : pes (`|`{keyword.operator} pes)*;
# pes : pe pe* ;
# pe : pi `*`{keyword.operator}? ;
# pi : '\w+'{variable.function} | group ;
# group : `(` pattern `)` ;

# prototype : ( ~comment )* ;

# comment{comment.line.number-sign, include-prototype: false} : '#+'{punctuation.definition.comment}
#                                     ~'$\n?'
#                                   ;

# """

text = r"""
main : ~'a' | 'b' ;
"""



ss = sublime_from_cfg(text)
print(ss.dump())




