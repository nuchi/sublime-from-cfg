from sublime_from_cfg import sublime_from_cfg

text = r'''
[A, B]

A = ':::'

main : A b[B] ;

b[X] : '#[X]' ;

'''

ss = sublime_from_cfg(text, ['```', '```'])
print(ss.dump())




