from sublime_from_cfg import sublime_from_cfg
from sublime_from_cfg.types import SublimeSyntaxOptions

text = r'''
[A, B]
NAME = 'blah'
EXTENSIONS = 'a b c'
FIRST_LINE = '#[A]#[B]'
SCOPE = 'source.heeeey'
SCOPE_POSTFIX = 'hey'
HIDDEN = 'true'

main : 'a'{keyword.operator} ;
'''

ss = sublime_from_cfg(text, [r'\#\!', r'.*'], SublimeSyntaxOptions('test'))
print(ss.dump())




