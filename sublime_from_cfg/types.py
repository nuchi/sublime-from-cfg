from dataclasses import dataclass
from hashlib import sha256
from typing import Optional, Union


class Expression:
    @property
    def name(self):
        self_hash = sha256(
            repr(self).encode('utf8')).hexdigest()[:7]
        return f'{self._name}/{self_hash}'


class Symbol(Expression):
    pass


class OptionsHaver:
    @property
    def _options_list(self):
        if self.options is None:
            return []
        return [o.strip() for o in self.options.split(',')]

    @property
    def option_kv(self):
        ret = {}
        for kv in self._options_list:
            if ':' not in kv:
                continue
            k, v = kv.split(':', 1)
            ret[k.strip()] = v.strip()
        return ret

    @property
    def option_list(self):
        return [o for o in self._options_list if ':' not in o]


class Skip(Symbol):
    pass


@dataclass(frozen=True)
class Terminal(Symbol, OptionsHaver):
    regex: str
    options: Optional[str] = None
    passive: bool = False
    embed: tuple[str, str] = None
    include: tuple[str, str] = None

    @property
    def _name(self):
        return '/T'

    def __post_init__(self):
        if not isinstance(self.regex, str):
            raise ValueError(f'was assigned: {repr(self.regex)}')


@dataclass(frozen=True)
class Nonterminal(Symbol):
    symbol: str
    args: tuple[Union['Nonterminal', str]] = tuple()
    passive: bool = False

    @property
    def name(self):
        if len(self.args) == 0 and not self.passive:
            if self.symbol in ('main',):# 'prototype'):
                return f'{self.symbol}/'
            return self.symbol
        return super().name

    @property
    def _name(self):
        return self.symbol


@dataclass(frozen=True)
class Concatenation(Expression):
    concats: list[Symbol]

    @property
    def _name(self):
        return '/cat'


EMPTY = Concatenation([])


@dataclass(frozen=True)
class Alternation(Expression, OptionsHaver):
    productions: list[Concatenation]
    options: Optional[str] = None

    @property
    def _name(self):
        return '/alt'

    @property
    def proto(self):
        return self.option_kv.get('include-prototype', 'true') == 'true'


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

    @property
    def _name(self):
        return '/~'


@dataclass
class SublimeSyntaxOptions:
    NAME: str
    EXTENSIONS: Optional[str] = None
    FIRST_LINE: Optional[str] = None
    SCOPE: Optional[str] = None
    SCOPE_POSTFIX: Optional[str] = None
    HIDDEN: Optional[str] = None

    @property
    def name(self):
        return self.NAME

    @property
    def extensions(self):
        return self.EXTENSIONS and self.EXTENSIONS.split(' ')

    @property
    def first_line(self):
        return self.FIRST_LINE

    @property
    def scope(self):
        return self.SCOPE or f'source.{self.name.lower()}'

    @property
    def scope_postfix(self):
        if self.SCOPE_POSTFIX is None:
            return f'.{self.name.lower()}'
        elif self.SCOPE_POSTFIX == '':
            return ''
        return f'.{self.SCOPE_POSTFIX}'

    @property
    def hidden(self):
        return self.HIDDEN == 'true'
