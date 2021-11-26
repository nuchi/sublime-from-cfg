from dataclasses import replace
from functools import wraps
from typing import Optional

try:
    import ruamel_yaml as yaml
except ImportError:
    from ruamel import yaml

from .bnf import NonLeftRecursiveGrammar
from .types import Terminal, Nonterminal, Concatenation, SublimeSyntaxOptions


def L(l):
    if len(l) == 1:
        return l[0]
    ret = yaml.comments.CommentedSeq(l)
    ret.fa.set_flow_style()
    return ret


def enqueue_todo(_f_context):
    def decorator(_f_name):
        @wraps(_f_name)
        def new_f(self, *args, compute=None, proto=True):
            name = _f_name(self, *args)

            if not proto:
                name = '^' + name

            if compute is None:
                if isinstance(name, tuple):
                    name, compute = name
                else:
                    compute = True

            if compute:
                triple = (_f_context, args, proto)
                if (existing := self.seen_already.get(name, triple)) != triple:
                    print('repeated name with different context:', name)
                    print('existing:', existing)
                    print('new:' , triple)
                    raise ValueError('already seen')
                self.seen_already[name] = (_f_context, args, proto)
                self.to_do.append((name, _f_context, args, proto))

            return name
        return new_f
    return decorator


def np(s):
    return replace(s, passive=False)


def _sorted(l, sort_table):
    def key(kv):
        return (sort_table.get(kv[0], 0), tuple(sorted(kv[1])), kv[0])
    return sorted(
        l,
        key=key,
    )


class SublimeSyntax:
    """
    Consume a context-free grammar and produce (via the `dump` method)
    a sublime-syntax yaml file.

    Implements a "Generalised Recursive Descent Parser" as described in
    _Generalised recursive descent parsing and follow-determinism_ by
    Adrian Johnstone and Elizabeth Scott. That's essentially a
    non-deterministic LL(1) parser. If the grammar happens to be LL(1) then
    no backtracking will happen and it's just an LL(1) parser. If the grammar
    is not LL(1) then alternatives will be tried in sequence, backtracking
    until one succeeds.

    IMPORTANT:
    The grammar must be non-left-recursive, and also must be follow-determined.
    If the grammar is left-recursive then the program will complain and alert
    the user, but I don't know an algorithm to detect whether the grammar is
    follow-determined. IF THE GRAMMAR IS *NOT* FOLLOW-DETERMINED, THEN THE
    LANGUAGE RECOGNIZED BY THE GENERATED SYNTAX WILL SIMPLY NOT MATCH THE INPUT
    GRAMMAR.

    A grammar is _follow-determined_ if whenever a nonterminal X produces both
    <string> and <string> y <...>, then y is not in the follow set of X.
    Intuitively, a grammar is follow-determined whenever a single lookahead token
    is enough to tell us whether it's okay to pop out of the context for X or if
    we should keep going within X. (i.e. if we've just consumed the prefix <string>
    and need to decide whether to finish with X or to keep consuming, then the
    presence or absence of the next token in the follow set of X had better be
    enough to tell us which option to take, because once we pop out of X then we
    can't backtrack to try other options anymore.)

    Everything happens in the `__init__` method, so really this could just be a
    collection of methods, but I wrapped it as a class so that I could use the
    `_terminals` instance variable as a cache without having to pass it as a
    parameter everywhere.
    """
    def __init__(
        self,
        grammar: NonLeftRecursiveGrammar,
        options: SublimeSyntaxOptions,
    ):
        self.grammar = grammar
        self.options = options
        self.scope_postfix = options.scope_postfix

        self.np_table = {}
        self.p_table = {}
        for nt, (np_table, p_table) in grammar.table.items():
            self.np_table[nt] = _sorted(np_table.items(), grammar.sort_table)
            self.p_table[nt] = _sorted(p_table.items(), grammar.sort_table)

        self.to_do = []
        self.seen_already = {}

        self.contexts = {
            'pop1!': [{'match': '', 'pop': 1}],
            'pop2!': [{'match': '', 'pop': 2}],
            'pop3!': [{'match': '', 'pop': 3}],
            'pop5!': [{'match': '', 'pop': 5}],
            'consume!': [{'match': r'\S', 'scope': f'meta.consume{self.scope_postfix}', 'pop': 3}],
            'fail!': [{'match': r'(?=\S)', 'pop': 1}],
            'fail1!': [{'match': r'\S', 'scope': f'invalid.illegal{self.scope_postfix}', 'set': 'reset1!'}],
            'reset1!': [
                {'match': r'\S', 'scope': f'invalid.illegal{self.scope_postfix}'},
                {'match': r'\n', 'set': L(['fail1!', 'fail2!', self._symbol_name(grammar.start)])}
            ],
            'fail2!': [{'match': r'\S', 'scope': f'invalid.illegal{self.scope_postfix}', 'set': 'reset2!'}],
            'reset2!': [
                {'match': r'\S', 'scope': f'invalid.illegal{self.scope_postfix}'},
                {'match': r'\n', 'set': L(['fail2!', self._symbol_name(grammar.start)])}
            ],
            'main': [{'match': '', 'push': L([
                'fail1!', 'fail2!', self._symbol_name(grammar.start)
            ])}]
        }

        if (proto := Nonterminal('prototype') in grammar.rules):
            _ = self._symbol_name(Nonterminal('prototype'))
        while self.to_do:
            name, _f_context, args, proto = self.to_do.pop(-1)
            if name in self.contexts:
                continue
            ctx = _f_context(self, *args)
            if not proto and 'meta_include_prototype' not in ctx[0]:
                ctx.insert(0, {'meta_include_prototype': False})
            self.contexts[name] = ctx

    def dump(self):
        out = {
            'version': 2,
            'name': self.options.name,
        }
        if self.options.extensions:
            out['file_extensions'] = self.options.extensions
        if self.options.first_line:
            out['first_line_match'] = self.options.first_line
        out['scope'] = self.options.scope
        if self.options.hidden:
            out['hidden'] = True
        out['contexts'] = self.contexts
        return yaml.round_trip_dump(out, version='1.2')

    # ---

    def _production_action(self, np_nt, production, proto):
        if len(production.concats) == 0:
            return {'pop': 2}
        production_stack = self._production_stack(production, proto=proto)
        if np(production.concats[-1]) == np_nt:
            return {'push': L(production_stack[1:])}
        return {'set': L(production_stack)}

    def _nonterminal_np_np(self, np_nt, passive_exists):
        np_table = self.np_table[np_nt]
        if not np_table:
            if not passive_exists:
                raise ValueError('Neither p nor np table?', repr(np_nt))
            return self._nonterminal_np_p(np_nt)
        prods = self.grammar.rules[np_nt].productions
        proto = self.grammar.rules[np_nt].proto
        skip_follow = self._skip_follow(np_nt)
        context = [] if proto else [{'meta_include_prototype': False}]

        if len(prods) == 1:
            match = {'match': ''}
            action = self._production_action(np_nt, prods[0], proto)
            return context + [{**match, **action}]

        for regex, indices in np_table:
            match = {'match': f'(?={regex})'}
            sorted_indices = sorted(indices)
            if len(sorted_indices) == 1:
                production = prods[sorted_indices[0]]
                if not passive_exists or (skip_follow and len(production.concats) == 0):
                    action = self._production_action(np_nt, production, proto)
                    context.append({**match, **action})
                    continue

            action = {'set': self._np_np_branch_name(np_nt, sorted_indices)}
            context.append({**match, **action})

        if passive_exists:
            context.append({'match': r'(?=\S)', 'set': self._nonterminal_np_p_name(np_nt)})
        else:
            context.append({'include': 'fail!'})
        return context

    def _nonterminal_np_p(self, np_nt):
        p_table = self.p_table[np_nt]
        proto = self.grammar.rules[np_nt].proto
        context = [] if proto else [{'meta_include_prototype': False}]
        skip_follow = self._skip_follow(np_nt)
        for regex, indices in p_table:
            match = {'match': f'(?={regex})'}
            sorted_indices = sorted(indices)
            if len(sorted_indices) == 1 \
                    and skip_follow \
                    and not self.grammar.rules[np_nt].productions[sorted_indices[0]].concats:
                action = {'pop': 2}
            else:
                action = {'push': L(['pop2!', self._np_p_branch_name(np_nt, sorted_indices)])}
            context.append({**match, **action})
        return context

    @enqueue_todo(_nonterminal_np_p)
    def _nonterminal_np_p_name(self, np_nt):
        return f'{self._nonterminal_name(np_nt, compute=False)}@p!'

    def _nonterminal_context(self, np_nt):
        return self._nonterminal_np_np(np_nt, bool(self.p_table[np_nt]))

    @enqueue_todo(_nonterminal_context)
    def _nonterminal_name(self, np_nt):
        return np_nt.name

    # ---

    def _nonterminal_p_preface_context(self, p_nt):
        p_table = dict(self.p_table[p_nt])
        np_table = dict(self.np_table[p_nt])
        combined_table = {
            regex: set.union(p_table.get(regex, set()), np_table.get(regex, set()))
            for regex in set(p_table).union(set(np_table))
        }
        proto = self.grammar.rules[np(p_nt)].proto
        context = [] if proto else [{'meta_include_prototype': False}]
        for regex, indices in _sorted(combined_table.items(), self.grammar.sort_table):
            sorted_indices = sorted(indices)
            context.append({
                'match': f'(?={regex})',
                'pop': 2,
            })
        return context

    @enqueue_todo(_nonterminal_p_preface_context)
    def _nonterminal_p_preface_name(self, p_nt):
        return f'{self._nonterminal_name(np(p_nt), compute=False)}@pp!'

    # ---

    def _terminal_p_preface_context(self, pt):
        return [{'match': f'(?={pt.regex})', 'pop': 2}]

    @enqueue_todo(_terminal_p_preface_context)
    def _terminal_p_preface_name(self, pt):
        return f'{self._terminal_name(np(pt), compute=False)}@pp!'

    # ---

    def _np_np_branch_context(self, np_nt, indices):
        proto = self.grammar.rules[np_nt].proto
        context = [] if proto else [{'meta_include_prototype': False}]
        passive_exists = bool(self.p_table[np_nt])
        branch_name = self._np_np_branch_name(np_nt, indices)
        branches = [
            self._np_np_branch_item_name(
                np_nt,
                indices,
                i,
                not passive_exists and i == len(indices) - 1
            )
            for i in indices
        ]
        if passive_exists:
            branches.append(self._np_np_branch_to_p_name(np_nt))
        return context + [{
            'match': '',
            'branch_point': branch_name,
            'branch': L(branches),
        }]

    @enqueue_todo(_np_np_branch_context)
    def _np_np_branch_name(self, np_nt, indices):
        return f'{self._nonterminal_name(np_nt, compute=False)}@{",".join([str(i) for i in indices])}'

    # ---

    def _np_np_branch_to_p_context(self, np_nt):
        return [{'match': '', 'pop': 1, 'set': self._nonterminal_np_p_name(np_nt)}]

    @enqueue_todo(_np_np_branch_to_p_context)
    def _np_np_branch_to_p_name(self, np_nt):
        return f'{self._nonterminal_name(np_nt, compute=False)}@to_p!'

    # ---

    def _np_p_branch_context(self, np_nt, indices):
        proto = self.grammar.rules[np_nt].proto
        context = [] if proto else [{'meta_include_prototype': False}]
        branch_name = self._np_p_branch_name(np_nt, indices)
        branches = [
            self._np_p_branch_item_name(np_nt, indices, i)
            for i in indices
        ]
        branches.append('consume!')
        return context + [{
            'match': '',
            'branch_point': branch_name,
            'branch': L(branches),
        }]

    @enqueue_todo(_np_p_branch_context)
    def _np_p_branch_name(self, np_nt, indices):
        return f'{self._nonterminal_np_p_name(np_nt, compute=False)}@{",".join([str(i) for i in indices])}'

    # ---

    def _np_np_branch_item_context(self, np_nt, indices, i, last):
        fail_name = 'pop3!' if last else \
            self._np_np_branch_fail_name(np_nt, indices)
        skip_follow = self._skip_follow(np_nt)
        production = self.grammar.rules[np_nt].productions[i]
        proto = self.grammar.rules[np_nt].proto
        context = [] if proto else [{'meta_include_prototype': False}]
        if not skip_follow:
            follow = [self._follow_name(np_nt), 'pop2!']
        else:
            follow = []
        if not production.concats:
            if not follow:
                raise ValueError(
                    f'Programming error; should not have empty follow and also '
                    f'empty production. {repr(np_nt)}, {indices}, {i}')
            else:
                follow = follow[:1]
                production_stack = []
        else:
            production_stack = self._production_stack(production, proto=proto)

        return context + [{
            'match': '',
            'set': L(['pop3!', fail_name] + follow + production_stack)
        }]

    @enqueue_todo(_np_np_branch_item_context)
    def _np_np_branch_item_name(self, np_nt, indices, i, last):
        if (self._skip_follow(np_nt) and not self.grammar.rules[np_nt].productions[i].concats):
            return 'pop3!', False

        return f'{self._np_np_branch_name(np_nt, indices, compute=False)}!{i}'

    # ---

    def _np_np_branch_fail_context(self, np_nt, indices):
        return [{'match': '', 'fail': self._np_np_branch_name(np_nt, indices)}]

    @enqueue_todo(_np_np_branch_fail_context)
    def _np_np_branch_fail_name(self, np_nt, indices):
        return f'{self._np_np_branch_name(np_nt, indices, compute=False)}@fail!'

    # ---

    def _np_p_branch_item_context(self, np_nt, indices, i):
        fail_name = self._np_p_branch_fail_name(np_nt, indices)
        skip_follow = self._skip_follow(np_nt)
        production = self.grammar.rules[np_nt].productions[i]
        proto = self.grammar.rules[np_nt].proto
        context = [] if proto else [{'meta_include_prototype': False}]
        if not skip_follow:
            follow = [self._follow_name(np_nt), 'pop2!']
        else:
            follow = []
        if not production.concats:
            if not follow:
                raise ValueError(
                    f'Programming error; should not have empty follow and also '
                    f'empty production. {repr(np_nt)}, {indices}, {i}')
            else:
                follow = follow[:1]
                production_stack = []
        else:
            production_stack = self._production_stack(production, proto=proto)

        if np(production.concats[-1]) == np_nt:
            return context + [{
                'match': '',
                'push': L(production_stack[2:]),
                'pop': 2
            }]

        return context + [{
            'match': '',
            'set': L(['pop5!', fail_name] + follow + production_stack)
        }]

    @enqueue_todo(_np_p_branch_item_context)
    def _np_p_branch_item_name(self, np_nt, indices, i):
        if (self._skip_follow(np_nt) and not self.grammar.rules[np_nt].productions[i].concats):
            return 'pop5!', False

        return f'{self._np_p_branch_name(np_nt, indices, compute=False)}!{i}'

    # ---

    def _np_p_branch_fail_context(self, np_nt, indices):
        proto = self.grammar.rules[np_nt].proto
        context = [] if proto else [{'meta_include_prototype': False}]
        return context + [{'match': '', 'fail': self._np_p_branch_name(np_nt, indices)}]

    @enqueue_todo(_np_p_branch_fail_context)
    def _np_p_branch_fail_name(self, np_nt, indices):
        return f'{self._np_p_branch_name(np_nt, indices, compute=False)}@fail!'

    # ---

    def _follow_context(self, nt):
        follow = self.grammar.follow[nt]
        sorted_follow = sorted([t.regex for t in follow if t is not None and not t.passive])
        proto = self.grammar.rules[np(nt)].proto
        context = [] if proto else [{'meta_include_prototype': False}]
        for regex in sorted_follow:
            context.append({'match': f'(?={regex})', 'pop': 2})
        context.append({'include': 'fail!'})
        return context

    @enqueue_todo(_follow_context)
    def _follow_name(self, nt):
        return f'{self._nonterminal_name(nt, compute=False)}@follow!'

    # ---

    def _fail_context(self, nt, indices):
        return [{'match': '', 'fail': self._nonpassive_branch_name(nt, indices)}]

    @enqueue_todo(_fail_context)
    def _fail_name(self, nt, indices):
        return f'{self._nonpassive_branch_name(nt, indices, compute=False)}@fail!'

    # ---

    def _production_stack(self, production, proto=True):
        if len(production.concats) == 0:
            raise ValueError('This method should not be called on an empty production')

        production_stack = []
        for symbol in production.concats[::-1]:
            if not symbol.passive:
                production_stack.extend([self._symbol_name(symbol, proto=proto), 'pop2!'])
            elif isinstance(symbol, Nonterminal):
                production_stack.extend([
                    self._symbol_name(np(symbol), proto=proto), 'pop2!',
                    self._nonterminal_p_preface_name(symbol, proto=proto), 'pop2!'
                ])
            else:
                production_stack.extend([
                    self._symbol_name(np(symbol), proto=proto), 'pop2!',
                    self._terminal_p_preface_name(symbol, proto=proto), 'pop2!'
                ])

        return production_stack[:-1]

    # ---

    def _meta_context(self, nt):
        proto = self.grammar.rules[np(nt)].proto
        context = [] if proto else [{'meta_include_prototype': False}]
        meta_scopes = self.grammar.rules[np(nt)].option_list
        meta_scope = ' '.join([f'{s}{self.scope_postfix}' for s in meta_scopes])
        return context + [
            {'meta_scope': meta_scope},
            {'match': '', 'pop': 2},
        ]

    @enqueue_todo(_meta_context)
    def _meta_name(self, nt):
        return f'{self._nonterminal_name(nt, compute=False)}@meta!'

    # ---

    def _meta_wrapper_context(self, nt):
        proto = self.grammar.rules[np(nt)].proto
        context = [] if proto else [{'meta_include_prototype': False}]
        if not nt.passive:
            return context + [
                {'match': '', 'set': L([self._meta_name(nt), 'pop2!', self._nonterminal_name(nt)])},
            ]
        for regex in set.union(set(self.np_table[np_nt]), set(self.p_table[np_nt])):
            context.append({
                'match': f'(?={regex})',
                'set': L([self._meta_name(np_nt), 'pop2!', self._nonterminal_name(nt)]),
            })
        return context


    @enqueue_todo(_meta_wrapper_context)
    def _meta_wrapper_name(self, nt):
        return f'{self._nonterminal_name(nt, compute=False)}@wrap_meta!'

    # ---

    def _terminal_context(self, t):
        match = {'match': t.regex}
        matches = [match]

        if t.option_list:
            match['scope'] = ' '.join([f'{s}{self.scope_postfix}' for s in t.option_list])

        if t.option_kv:
            captures = {}
            for k, v in t.option_kv.items():
                try:
                    int_k = int(k)
                except ValueError:
                    continue
                captures[int_k] = ' '.join([f'{s}{self.scope_postfix}' for s in v.split(' ')])
            if captures:
                match['captures'] = captures

        if t.embed:
            (embed_regex,), embed_options = t.embed
            embed_options = [o.strip() for o in embed_options.split(',')]
            embed = embed_options.pop(0)
            action = {'embed': embed, 'escape': embed_regex.regex}
            if embed_options:
                if ':' not in embed_options[0]:
                    action['embed_scope'] = embed_options.pop(0)
                action['escape_captures'] = {}
                for o in embed_options:
                    try:
                        k, v = o.split(':')
                        action['escape_captures'][int(k.strip())] = f'{v.strip()}{self.scope_postfix}'
                    except Exception:
                        raise ValueError(f'Bad capture group, expected <int>: <scope>. Found: {o}')
                if not action['escape_captures']:
                    del action['escape_captures']
            action['pop'] = 2
        elif t.include:
            (include_symbol,), include_options = t.include
            action = {
                'set': L(['pop2!', 'pop1!', include_options]),
                'with_prototype': [{'include': self._nonterminal_name(include_symbol)}],
            }
        else:
            action = {'pop': 2}

        match.update(**action)
        matches.append({'include': 'fail!'})
        return matches

    @enqueue_todo(_terminal_context)
    def _terminal_name(self, t):
        return t.name

    # ---

    # Called only from _production_stack and generating 'main'
    def _symbol_name(self, symbol, proto=True):
        if isinstance(symbol, Nonterminal):
            if symbol.passive or not self.grammar.rules[np(symbol)].option_list:
                return self._nonterminal_name(symbol, proto=proto)
            return self._meta_wrapper_name(symbol, proto=proto)
        return self._terminal_name(symbol, proto=proto)

    # ---

    def _skip_follow(self, nt):
        if len(self.grammar.follow[nt]) == 0:
            return True
        return any(
            t.passive for t in self.grammar.follow[nt] if t is not None
        )

    # ---
