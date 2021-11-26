from collections import defaultdict
from copy import deepcopy
from dataclasses import fields
from functools import partial
import re
from typing import Union

from sly import Lexer, Parser

from .types import (
    Terminal,
    Nonterminal,
    Alternation,
    Concatenation,
    Repetition,
    OptionalExpr,
    Passive,
    SublimeSyntaxOptions,
)
from .transform_grammar import transform_grammar


class _PrintLineNumber:
    def error(self, t):
        print(f'Error at line {t.lineno}')
        return super().error(t)


def _expand(key, context):
    val = context[key]
    while callable(val):
        val = val(**context)
    return val


def _format(s, context):
    class _Context(dict):
        def __getitem__(self, k):
            ret = _expand(k, {**self})
            if isinstance(ret, Terminal):
                return ret.regex
            elif isinstance(ret, Nonterminal):
                raise ValueError(f'Tried to interpolate a string with rule {ret.symbol}')
            raise ValueError(f'Unknown thing in context: {repr(ret)}')
    _context = _Context(**context)
    return s.format_map(_context)


class SbnfLexer(_PrintLineNumber, Lexer):
    tokens = {
        'EMBED',
        'INCLUDE',
        'IDENT',
        'U_IDENT',
        'IDENT_DEF',
        'RULE_DEF',
        'RULE_END',
        'ALT',
        'PASSIVE',
        'STAR',
        'QUESTION',
        'LPAR',
        'RPAR',
        'BTICK',
        'QUOTE',
        'LBRACE',
        'RBRACE',
        'LBRACK',
        'RBRACK',
        'COMMA',
        'PERC',
        'EMPTY',
    }
    ignore = ' \t'
    ignore_comment = r'#.*'
    ignore_newline = r'\n+'

    IDENT = r'[a-z0-9\-\.]+'
    U_IDENT = r'[A-Z0-9_\.]+'
    IDENT_DEF = '='
    RULE_DEF = ':'
    RULE_END = ';'
    ALT = r'\|'
    PASSIVE = '~'
    STAR = r'\*'
    QUESTION = r'\?'
    LPAR = r'\('
    RPAR = r'\)'
    BTICK = '`'
    QUOTE = "'"
    LBRACE = '{'
    RBRACE = '}'
    LBRACK = r'\['
    RBRACK = r'\]'
    COMMA = ','
    PERC = '%'
    EMBED = 'embed'
    INCLUDE = 'include'
    EMPTY = r'<>'

    def ignore_newline(self, t):
        self.lineno += t.value.count('\n')

    def IDENT(self, t):
        if t.value == self.EMBED:
            t.type = 'EMBED'
        elif t.value == self.INCLUDE:
            t.type = 'INCLUDE'
        return t

    def BTICK(self, t):
        self.push_state(LiteralLexer)
        return t

    def QUOTE(self, t):
        self.push_state(RegexLexer)
        return t

    def LBRACE(self, t):
        self.push_state(OptionsLexer)
        return t


class LiteralLexer(_PrintLineNumber, Lexer):
    tokens = { 'LITERAL', 'BTICK' }
    BTICK = '`'
    LITERAL = r'[^`]+'

    def LITERAL(self, t):
        self.lineno += t.value.count('\n')
        return t

    def BTICK(self, t):
        self.pop_state()
        return t


class RegexLexer(_PrintLineNumber, Lexer):
    tokens = { 'REGEX', 'QUOTE' }
    REGEX = r"(\\.|[^'])+"
    QUOTE = "'"

    def REGEX(self, t):
        pattern = r'(\\.)|#\[([\w\-\.]+)\]'
        def repl(m):
            a, b = m.groups()
            if a is not None:
                if a == r'\'':
                    return "'"
                return a
            return f'{{{b}}}'
        t.value = re.sub(
            pattern,
            repl,
            t.value.replace('{', '{{').replace('}', '}}'),
        )
        self.lineno += t.value.count('\n')
        return t

    def QUOTE(self, t):
        self.pop_state()
        return t


class OptionsLexer(_PrintLineNumber, Lexer):
    tokens = { 'OPTIONS', 'RBRACE' }
    OPTIONS = r'[^}]+'
    RBRACE = '}'

    def OPTIONS(self, t):
        pattern = r'(\\.)|#\[([\w\-\.]+)\]'
        def repl(m):
            a, b = m.groups()
            if a is not None:
                return a
            return f'{{{b}}}'
        t.value = re.sub(
            pattern,
            repl,
            t.value.replace('{', '{{').replace('}', '}}'),
        )
        self.lineno += t.value.count('\n')
        return t

    def RBRACE(self, t):
        self.pop_state()
        return t


class SbnfParser(Parser):
    tokens = SbnfLexer.tokens \
           | LiteralLexer.tokens \
           | RegexLexer.tokens \
           | OptionsLexer.tokens

    def __init__(self, text, global_args):
        self.variables = {}
        self.to_do = set()
        self.zero_arg_rules = {}
        self.parameterized_rules = {}
        self.global_params = []
        self.make_grammar(text, global_args)


    @_('[ parameters ] { variable_or_rule }')
    def main(self, p):
        if p.parameters is not None:
            for nt in p.parameters():
                self.global_params.append(nt.symbol)
        return p

    @_('variable', 'rule')
    def variable_or_rule(self, p):
        return p

    @_('U_IDENT IDENT_DEF variable_defn')
    def variable(self, p):
        var_defn = p.variable_defn
        self.variables[p.U_IDENT] = lambda **context: var_defn(**context)
        return p

    @_('literal_or_regex')
    def variable_defn(self, p):
        p0 = p[0]
        return lambda **context: p0(**context)

    @_('U_IDENT')
    def variable_defn(self, p):
        p0 = p[0]
        return p0 # lambda **context: self.variables[p0](**context)

    @_('IDENT [ parameters ] [ options ] RULE_DEF alternates RULE_END')
    def rule(self, p):
        alternates = p.alternates
        options = (lambda **context: None) if p.options is None else p.options
        parameters = (lambda **context: tuple()) if p.parameters is None else p.parameters
        def ret(**context):
            return Alternation(alternates(**context), options(**context))
        self.parameterized_rules[(p.IDENT, tuple(parameters()))] = ret
        if p.parameters is None:
            self.zero_arg_rules[p.IDENT] = lambda **context: Nonterminal(p.IDENT)
        return p

    @_('LBRACK parameter { COMMA parameter } RBRACK')
    def parameters(self, p):
        params = [p.parameter0] + p.parameter1
        return lambda **context: [param(**context) for param in params]

    @_('LBRACK argument { COMMA argument } RBRACK')
    def arguments(self, p):
        arguments = [p.argument0] + p.argument1
        return lambda **context: [arg(**context) for arg in arguments]

    @_('literal_or_regex')
    def parameter(self, p):
        lit_or_reg = p.literal_or_regex
        return lambda **context: Terminal(lit_or_reg(**context))

    @_('IDENT')
    def parameter(self, p):
        IDENT = p.IDENT
        return lambda **context: Nonterminal(IDENT)

    @_('U_IDENT')
    def parameter(self, p):
        U_IDENT = p.U_IDENT
        return lambda **context: context.get(U_IDENT, Nonterminal(U_IDENT))

    @_('literal_or_regex')
    def argument(self, p):
        lit_or_reg = p.literal_or_regex
        return lambda **context: Terminal(lit_or_reg(**context))

    @_('IDENT')
    def argument(self, p):
        IDENT = p.IDENT
        return lambda **context: Nonterminal(IDENT)

    @_('U_IDENT')
    def argument(self, p):
        U_IDENT = p.U_IDENT
        return lambda **context: _expand(U_IDENT, context)

    @_('production { ALT production }')
    def alternates(self, p):
        productions = [p.production0] + p.production1
        return lambda **context: [prod(**context) for prod in productions]

    @_('pattern_element { pattern_element }')
    def production(self, p):
        elements = [p.pattern_element0] + p.pattern_element1
        return lambda **context: Concatenation([element(**context) for element in elements])

    @_('EMPTY')
    def production(self, p):
        return lambda **context: Concatenation([])

    @_('[ PASSIVE ] pattern_item [ star_or_question ]')
    def pattern_element(self, p):
        pattern_item = p.pattern_item
        ret = lambda **context: pattern_item(**context)

        if p.star_or_question is not None:
            op = Repetition if p.star_or_question == '*' else OptionalExpr
            ret = partial((lambda r, **context: op(r(**context))), ret)

        if p.PASSIVE is not None:
            ret = partial((lambda r, **context: Passive(r(**context))), ret)

        return ret

    @_('STAR', 'QUESTION')
    def star_or_question(self, p):
        return p[0]

    @_('literal_or_regex [ options ] [ embed_include ]')
    def pattern_item(self, p):
        lit_or_reg = p.literal_or_regex
        options = (lambda **context: None) if p.options is None else p.options
        embed_include = p.embed_include
        if embed_include is not None:
            ei, ei_args, ei_options = p.embed_include
            ei_kwarg = lambda **context: {ei: (tuple(ei_args(**context)), ei_options(**context))}
        else:
            ei_kwarg = lambda **context: {}
        def make_terminal(**context):
            regex = lit_or_reg(**context)
            options_ = options(**context)
            ei_kwarg_ = ei_kwarg(**context)
            if ei_kwarg:
                if 'include' in ei_kwarg_:
                    new_nt = ei_kwarg_['include'][0][0]
                    self.to_do.add(new_nt)
            return Terminal(
                regex,
                options_,
                **ei_kwarg_
            )
        return make_terminal

    @_('LPAR alternates RPAR')
    def pattern_item(self, p):
        alternates = p.alternates
        return lambda **context: Alternation(alternates(**context))

    @_('IDENT [ arguments ]')
    def pattern_item(self, p):
        arguments = p.arguments or (lambda **context: [])
        IDENT = p.IDENT
        def make_symbol(i, **context):
            args = tuple([arg for arg in arguments(**context)])
            if i in context:
                symbol = context[i]
                if isinstance(symbol, Terminal):
                    if len(args) > 0:
                        raise ValueError('Tried to apply args to terminal')
                    return symbol
                i = symbol.symbol
            nt = Nonterminal(i, args=args)
            self.to_do.add(nt)
            return nt
        return partial(make_symbol, IDENT)

    @_('U_IDENT [ options ]')
    def pattern_item(self, p):
        U_IDENT = p.U_IDENT
        options = p.options or (lambda **context: None)
        return lambda **context: Terminal(_expand(U_IDENT, context), options(**context))

    @_('LBRACE [ OPTIONS ] RBRACE')
    def options(self, p):
        OPTIONS = p.OPTIONS if p.OPTIONS is not None else ''
        return lambda **context: _format(OPTIONS, context)

    @_('PERC embed_or_include_token arguments options')
    def embed_include(self, p):
        return (p.embed_or_include_token, p.arguments, p.options)

    @_('EMBED', 'INCLUDE')
    def embed_or_include_token(self, p):
        return p[0]

    @_('literal', 'regex')
    def literal_or_regex(self, p):
        return p[0]

    @_('QUOTE [ REGEX ] QUOTE')
    def regex(self, p):
        reg = p.REGEX if p.REGEX is not None else ''
        return lambda **context: _format(reg, context)

    @_('BTICK [ LITERAL ] BTICK')
    def literal(self, p):
        LITERAL = p.LITERAL if p.LITERAL is not None else ''
        as_regex = re.escape(LITERAL).replace('{', '{{').replace('}', '}}')
        return lambda **context: _format(as_regex, context)

    def error(self, token):
        super().error(token)
        raise ValueError('Syntax error; aborting.')

    def find_matching_rule(self, name, args):
        for (ident, params), rule in self.parameterized_rules.items():
            if name != ident:
                continue
            if len(args) != len(params):
                continue
            match = True
            rule_context = {}
            for param, arg in zip(params, args):
                if isinstance(param, Terminal) and not (arg.regex == param.regex):
                    match = False
                    break
                if isinstance(param, Nonterminal) \
                        and param.symbol in self.zero_arg_rules \
                        and arg != param:
                    match = False
                    break

                if isinstance(param, Nonterminal):
                    rule_context[param.symbol] = arg
            if match:
                return rule, rule_context
        raise ValueError(f'No matching rule found for {name}, {args}')

    def make_actualized_rules(self, start, context):
        self.to_do.add(start)
        actual_rules = {}
        while self.to_do:
            to_do, self.to_do = self.to_do, set()
            for nt in to_do:
                if nt in actual_rules:
                    continue
                name = nt.symbol
                args = nt.args
                rule, rule_context = self.find_matching_rule(name, args)
                new_context = {**context, **rule_context}
                actual_rules[nt] = rule(**new_context)
        return actual_rules

    def make_grammar(self, text, global_args):
        lexer = SbnfLexer()
        self.parse(lexer.tokenize(text))
        context = {}
        for param, arg in zip(self.global_params, global_args):
            context[param] = arg
        context.update(self.variables)
        main_rules = self.make_actualized_rules(Nonterminal('main'), context)
        main_rules = transform_grammar(main_rules)

        if ('prototype', tuple()) in self.parameterized_rules:
            proto_rules = self.make_actualized_rules(Nonterminal('prototype'), context)
            proto_rules = transform_grammar(proto_rules)
        else:
            proto_rules = {}

        self.options = {}
        for field in fields(SublimeSyntaxOptions):
            if field.name in self.variables:
                self.options[field.name] = _expand(field.name, context)

        self.combined_rules = {**main_rules, **proto_rules}
