from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from functools import partial
import re
from typing import Optional, Union

from sly import Lexer, Parser

from bnf import (
    Expression,
    Terminal,
    Nonterminal,
    Alternation,
    Concatenation,
    NonLeftRecursiveGrammar,
)


@dataclass(frozen=True)
class Repetition(Expression):
    sub: Expression

    @property
    def _name(self):
        return '/*'


@dataclass(frozen=True)
class OptionalExpr(Expression):
    sub: Expression

    @property
    def _name(self):
        return '/opt'


@dataclass(frozen=True)
class Passive(Expression):
    sub: Expression


class SbnfLexer(Lexer):
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


class LiteralLexer(Lexer):
    tokens = { 'LITERAL', 'BTICK' }
    BTICK = '`'
    LITERAL = r'[^`]+'

    def BTICK(self, t):
        self.pop_state()
        return t


class RegexLexer(Lexer):
    tokens = { 'REGEX', 'QUOTE' }
    REGEX = r"(\\.|[^'])+"
    QUOTE = "'"

    def REGEX(self, t):
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
        return t

    def QUOTE(self, t):
        self.pop_state()
        return t


class OptionsLexer(Lexer):
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
        return t

    def RBRACE(self, t):
        self.pop_state()
        return t


class SbnfParser(Parser):
    tokens = SbnfLexer.tokens \
           | LiteralLexer.tokens \
           | RegexLexer.tokens \
           | OptionsLexer.tokens

    def __init__(self, text):
        self.variables = {}
        self.to_do = set()
        self.zero_arg_rules = {}
        self.actual_rules = {}
        self.parameterized_rules = {}

        self.make_grammar(text)

    @_('{ parameters } { variable|rule }')
    def main(self, p):
        if len(p.parameters) > 0:
            raise NotImplementedError('Global parameters not yet supported.')
        return p

    @_('U_IDENT IDENT_DEF variable_defn')
    def variable(self, p):
        var_defn = p.variable_defn
        self.variables[p.U_IDENT] = lambda: var_defn()
        return p

    @_('literal_or_regex')
    def variable_defn(self, p):
        p0 = p[0]
        return lambda: p0()

    @_('U_IDENT')
    def variable_defn(self, p):
        p0 = p[0]
        return lambda: self.variables[p0]()

    @_('IDENT [ parameters ] [ options ] RULE_DEF alternates RULE_END')
    def rule(self, p):
        if p.IDENT == 'prototype':
            raise NotImplementedError('prototype rule not yet supported.')
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
        def get_u_ident_param(**context):
            if U_IDENT in self.variables:
                return self.variables[U_IDENT]()
            return Nonterminal(U_IDENT)
        return get_u_ident_param
        # return lambda **context: Terminal(self.variables[U_IDENT]())

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
        return lambda **context: Terminal(self.variables[U_IDENT]())

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

    # Restore this when passives are implemented for things other than terminals
    # @_('pattern_item [ star_or_question ]')
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
        # print(p[0])
        # raise NotImplementedError(f'{p[0]} not yet supported.')
        return p[0]

    @_('literal_or_regex [ options ] [ embed_include ]')
    def pattern_item(self, p):
        lit_or_reg = p.literal_or_regex
        options = (lambda **context: None) if p.options is None else p.options
        return lambda **context: Terminal(
            lit_or_reg(**context),
            options(**context),
        )

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
            nt = Nonterminal(i, args)
            self.to_do.add(nt)
            return nt
        return partial(make_symbol, IDENT)

    @_('U_IDENT [ options ]')
    def pattern_item(self, p):
        U_IDENT = p.U_IDENT
        options = p.options or (lambda **context: None)
        def expand_u_ident(**context):
            if U_IDENT in self.variables:
                regex = self.variables[U_IDENT]()
            else:
                regex = context[U_IDENT].regex
            return Terminal(regex, options(**context))
        return expand_u_ident


    @_('LBRACE OPTIONS RBRACE')
    def options(self, p):
        OPTIONS = p.OPTIONS
        return lambda **context: OPTIONS.format(**context)

    @_('PERC embed_or_include_token arguments options')
    def embed_include(self, p):
        raise NotImplementedError(
            f'Line {p._slice[0].lineno}: {p[1]} not supported yet.')
        return (p.embed_or_include_token, p.arguments, p.options)

    @_('EMBED', 'INCLUDE')
    def embed_or_include_token(self, p):
        return p[0]

    @_('literal', 'regex')
    def literal_or_regex(self, p):
        return p[0]

    @_('QUOTE REGEX QUOTE')
    def regex(self, p):
        reg = p.REGEX
        return lambda **context: reg.format(**context)

    @_('BTICK LITERAL BTICK')
    def literal(self, p):
        as_regex = re.escape(p.LITERAL).replace('{', '{{').replace('}', '}}')
        return lambda **context: as_regex.format(**context)

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
                if isinstance(param, Terminal) and arg != param.regex:
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

    def make_actualized_rules(self, context):
        self.to_do.add(Nonterminal('main'))
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

    def make_grammar(self, text):
        lexer = SbnfLexer()
        self.parse(lexer.tokenize(text))
        self.actual_rules = self.make_actualized_rules({})
