from functools import wraps

from bnf import NonLeftRecursiveGrammar, Terminal, Nonterminal, Concatenation
try:
    import ruamel_yaml as yaml
except ImportError:
    from ruamel import yaml


def L(l):
    ret = yaml.comments.CommentedSeq(l)
    ret.fa.set_flow_style()
    return ret


def enqueue_todo(_f_context):
    def decorator(_f_name):
        @wraps(_f_name)
        def new_f(self, *args):
            name = _f_name(self, *args)
            if isinstance(name, tuple):
                name, compute = name
            else:
                compute = True
            if compute:
                if (existing := self.seen_already.get(name, (_f_context, args))) != (_f_context, args):
                    print('repeated name with different context:', name)
                    print('existing:', existing)
                    print('new:' , (_f_context, args))
                    raise ValueError('already seen')
                self.seen_already[name] = (_f_context, args)
                self.to_do.append((name, _f_context, args))
            return name
        return new_f
    return decorator


def np(nt):
    return Nonterminal(nt.symbol, nt.args, False)


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
        syntax_name: str,
        file_extensions: list[str],
        scope: str,
    ):
        self.grammar = grammar
        self.syntax_name = syntax_name
        self.file_extensions = file_extensions
        self.scope = scope

        self.contexts = {
            'pop2!': [{'match': '', 'pop': 2}],
            'pop3!': [{'match': '', 'pop': 3}],
            'pop5!': [{'match': '', 'pop': 5}],
            'consume!': [{'match': r'\S', 'scope': f'region.redish.{self.scope}', 'pop': 2}],
            'fail!': [{'match': r'(?=\S)', 'pop': 1}],
            'fail_forever!': [{'match': r'\S', 'scope': f'invalid.illegal.{self.scope}'}],
            'main': [{'match': '', 'push': L([
                'fail_forever!', 'fail_forever!', grammar.start.name
            ])}]
        }
        self.np_table = {}
        self.p_table = {}
        for nt, (np_table, p_table) in grammar.table.items():
            sorted_np_table = sorted(
                np_table.items(),
                key=lambda kv: tuple(sorted(kv[1])[::-1]),
                reverse=True,
            )
            sorted_p_table = sorted(
                p_table.items(),
                key=lambda kv: tuple(sorted(kv[1])[::-1]),
                reverse=True,
            )
            self.np_table[nt] = sorted_np_table
            self.p_table[nt] = sorted_p_table

        self.to_do = []
        self.seen_already = {}
        _ = self._symbol_name(grammar.start)
        while self.to_do:
            name, _f_context, args = self.to_do.pop(-1)
            if name in self.contexts:
                continue
            ctx = _f_context(self, *args)
            self.contexts[name] = ctx

    def dump(self):
        return yaml.round_trip_dump({
            'version': 2,
            'name': self.syntax_name,
            'file_extensions': self.file_extensions,
            'scope': f'source.{self.scope}',
            'contexts': self.contexts,
        }, version='1.2')

    # ---

    def _nonterminal_np_np(self, np_nt, passive_exists):
        np_table = self.np_table[np_nt]
        if not np_table:
            if not passive_exists:
                raise ValueError('Neither p nor np table?', repr(np_nt))
            return self._nonterminal_np_p(np_nt)
        context = []
        prods = self.grammar.rules[np_nt].productions

        if len(prods) == 1:
            target = self._production_stack(prods[0])
            if len(target) == 0:
                return [{'match': '', 'pop': 2}]
            return [{'match': '', 'set': L(target)}]

        for regex, indices in np_table:
            sorted_indices = sorted(indices)
            if passive_exists or len(sorted_indices) > 1:
                context.append({
                    'match': f'(?={regex})',
                    'set': self._np_np_branch_name(np_nt, sorted_indices),
                })
            else:
                # go directly to this production
                match = {'match': f'(?={regex})'}
                production = self.grammar.rules[np_nt].productions[sorted_indices[0]]
                if (pc := production.concats) and pc[-1] == np_nt:
                    action = {
                        'push': L(['pop2!']
                            + self._production_stack(Concatenation(pc[:-1])))
                    }
                else:
                    action = {
                        'set': self._production_name(np_nt, sorted_indices[0]),
                    }
                match.update(**action)
                context.append(match)

        if passive_exists:
            context.append({'match': r'(?=\S)', 'set': self._nonterminal_np_p_name(np_nt)})
        else:
            context.append({'include': 'fail!'})
        return context

    def _nonterminal_np_p(self, np_nt):
        p_table = self.p_table[np_nt]
        context = []
        for regex, indices in p_table:
            sorted_indices = sorted(indices)
            context.append({
                'match': f'(?={regex})',
                'set': self._np_p_branch_name(np_nt, sorted_indices),
            })
        return context

    @enqueue_todo(_nonterminal_np_p)
    def _nonterminal_np_p_name(self, np_nt):
        return f'{self._nonterminal_name(np_nt)}@p!'

    def _nonterminal_p(self, p_nt):
        np_nt = np(p_nt)
        p_table = dict(self.p_table[np_nt])
        np_table = dict(self.np_table[np_nt])
        combined_table = {
            regex: set.union(p_table.get(regex, set()), np_table.get(regex, set()))
            for regex in set(p_table).union(set(np_table))
        }.items()
        context = []
        for regex, indices in combined_table:
            sorted_indices = sorted(indices)
            context.append({
                'match': f'(?={regex})',
                'set': self._p_branch_name(p_nt, sorted_indices),
            })
        return context

    def _nonterminal_context(self, nt):
        if not nt.passive:
            return self._nonterminal_np_np(nt, bool(self.p_table[nt]))
        return self._nonterminal_p(nt)

    @enqueue_todo(_nonterminal_context)
    def _nonterminal_name(self, nt):
        return nt.name

    # ---

    def _np_np_branch_context(self, np_nt, indices):
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
        return [{
            'match': '',
            'branch_point': branch_name,
            'branch': L(branches),
        }]


    @enqueue_todo(_np_np_branch_context)
    def _np_np_branch_name(self, np_nt, indices):
        return f'{self._nonterminal_name(np_nt)}@{",".join([str(i) for i in indices])}'

    # ---

    def _np_np_branch_to_p_context(self, np_nt):
        return [{'match': '', 'pop': 1, 'set': self._nonterminal_np_p_name(np_nt)}]

    @enqueue_todo(_np_np_branch_to_p_context)
    def _np_np_branch_to_p_name(self, np_nt):
        return f'{self._nonterminal_name(np_nt)}@to_p!'

    # ---

    def _np_p_branch_context(self, np_nt, indices):
        branch_name = self._np_p_branch_name(np_nt, indices)
        branches = [
            self._np_p_branch_item_name(np_nt, indices, i)
            for i in indices
        ]
        branches.append('consume!')
        return [{
            'match': '',
            'branch_point': branch_name,
            'branch': L(branches),
        }]

    @enqueue_todo(_np_p_branch_context)
    def _np_p_branch_name(self, np_nt, indices):
        return f'{self._nonterminal_np_p_name(np_nt)}@{",".join([str(i) for i in indices])}'

    # ---

    def _p_branch_context(self, p_nt, indices):
        branch_name = self._p_branch_name(p_nt, indices)
        branches = [
            self._p_branch_item_name(p_nt, indices, i)
            for i in indices
        ]
        branches.append('consume!')
        return [{
            'match': '',
            'branch_point': branch_name,
            'branch': L(branches),
        }]

    @enqueue_todo(_p_branch_context)
    def _p_branch_name(self, p_nt, indices):
        return f'{self._nonterminal_name(p_nt)}@{",".join([str(i) for i in indices])}'

    # ---

    def _np_np_branch_item_context(self, np_nt, indices, i, last):
        fail_name = 'pop3!' if last else \
            self._np_np_branch_fail_name(np_nt, indices)
        skip_follow = any(
            t.passive for t in self.grammar.follow[np_nt] if t is not None
        ) or self.grammar.follow[np_nt].difference({None}) == {}
        if not skip_follow:
            follow = [self._follow_name(np_nt), 'pop2!']
        else:
            follow = []
        return [{
            'match': '',
            'set': L(['pop3!', fail_name] + follow + [self._production_name(np_nt, i)])
        }]

    @enqueue_todo(_np_np_branch_item_context)
    def _np_np_branch_item_name(self, np_nt, indices, i, last):
        return f'{self._np_np_branch_name(np_nt, indices)}!{i}'

    # ---

    def _np_np_branch_fail_context(self, np_nt, indices):
        return [{'match': '', 'fail': self._np_np_branch_name(np_nt, indices)}]

    @enqueue_todo(_np_np_branch_fail_context)
    def _np_np_branch_fail_name(self, np_nt, indices):
        return f'{self._np_np_branch_name(np_nt, indices)}@fail!'

    # ---

    def _np_p_branch_item_context(self, np_nt, indices, i):
        fail_name = self._np_p_branch_fail_name(np_nt, indices)
        skip_follow = any(
            t.passive for t in self.grammar.follow[np_nt] if t is not None
        ) or self.grammar.follow[np_nt].difference({None}) == {}
        if not skip_follow:
            follow = [self._follow_name(np_nt), 'pop2!']
        else:
            follow = []
        return [{
            'match': '',
            'set': L(['pop3!', fail_name] + follow + [self._production_name(np_nt, i)])
        }]

    @enqueue_todo(_np_p_branch_item_context)
    def _np_p_branch_item_name(self, np_nt, indices, i):
        return f'{self._np_p_branch_name(np_nt, indices)}!{i}'

    # ---

    def _np_p_branch_fail_context(self, np_nt, indices):
        return [{'match': '', 'fail': self._np_p_branch_name(np_nt, indices)}]

    @enqueue_todo(_np_p_branch_fail_context)
    def _np_p_branch_fail_name(self, np_nt, indices):
        return f'{self._np_p_branch_name(np_nt, indices)}@fail!'

    # ---

    def _p_branch_item_context(self, p_nt, indices, i):
        fail_name = self._p_branch_fail_name(p_nt, indices)
        skip_follow = any(
            t.passive for t in self.grammar.follow[p_nt] if t is not None
        ) or self.grammar.follow[p_nt].difference({None}) == {}
        if not skip_follow:
            follow = [self._follow_name(p_nt), 'pop2!']
        else:
            follow = []
        return [{
            'match': '',
            'set': L(['pop3!', fail_name] + follow + [self._production_name(np(p_nt), i)])
        }]

    @enqueue_todo(_p_branch_item_context)
    def _p_branch_item_name(self, p_nt, indices, i):
        return f'{self._p_branch_name(p_nt, indices)}!{i}'

    # ---

    def _p_branch_fail_context(self, p_nt, indices):
        return [{'match': '', 'fail': self._p_branch_name(p_nt, indices)}]

    @enqueue_todo(_p_branch_fail_context)
    def _p_branch_fail_name(self, p_nt, indices):
        return f'{self._p_branch_name(p_nt, indices)}@fail!'

    # ---

    def _follow_context(self, nt):
        follow = self.grammar.follow[nt]
        context = []
        for t in follow:
            if t is None:
                continue
            if not t.passive:
                context.append({'match': f'(?={t.regex})', 'pop': 2})
        context.append({'include': 'fail!'})
        return context

    @enqueue_todo(_follow_context)
    def _follow_name(self, nt):
        return f'{self._nonterminal_name(nt)}@follow!'

    # ---

    def _fail_context(self, nt, indices):
        return [{'match': '', 'fail': self._nonpassive_branch_name(nt, indices)}]

    @enqueue_todo(_fail_context)
    def _fail_name(self, nt, indices):
        return f'{self._nonpassive_branch_name(nt, indices)}@fail!'

    # ---

    def _production_stack(self, production):
        if len(production.concats) == 0:
            raise ValueError('This method should not be called on an empty production')

        production_stack = []
        for symbol in production.concats[::-1]:
            production_stack.extend([self._symbol_name(symbol), 'pop2!'])
        return production_stack[:-1]

    def _production_context(self, np_nt, index):
        production = self.grammar.rules[np_nt].productions[index]
        # can assume production is not empty
        return [{'match': '', 'set': L(self._production_stack(production))}]

    @enqueue_todo(_production_context)
    def _production_name(self, np_nt, index):
        production = self.grammar.rules[np_nt].productions[index]
        if len(production.concats) == 0:
            return 'pop2!', False
        return f'{self._nonterminal_name(np_nt)}|{index}'

    # ---

    def _meta_context(self, nt):
        meta_scopes = self.grammar.rules[np(nt)].option_list
        meta_scope = ' '.join([f'{s}.{self.scope}' for s in meta_scopes])
        return [
            {'meta_scope': meta_scope},
            {'match': '', 'pop': 2},
        ]
        pass

    @enqueue_todo(_meta_context)
    def _meta_name(self, nt):
        return f'{self._nonterminal_name(nt)}@meta!'

    # ---

    def _meta_wrapper_context(self, nt):
        if not nt.passive:
            return [
                {'match': '', 'set': L([self._meta_name(nt), 'pop2!', self._nonterminal_name(nt)])},
            ]
        np_nt = np(nt)
        context = []
        for regex in set.union(set(self.np_table[np_nt]), set(self.p_table[np_nt])):
            context.append({
                'match': f'(?={regex})',
                'set': L([self._meta_name(np_nt), 'pop2!', self._nonterminal_name(nt)]),
            })


    @enqueue_todo(_meta_wrapper_context)
    def _meta_wrapper_name(self, nt):
        return f'{self._nonterminal_name(nt)}@wrap_meta!'

    # ---

    def _terminal_context(self, t):
        match = {'match': t.regex}
        matches = [match]

        if t.option_list:
            match['scope'] = ' '.join([f'{s}.{self.scope}' for s in t.option_list])

        if t.embed:
            raise NotImplementedError('embed terminal: not yet')
        elif t.include:
            (include_symbol,), include_options = t.include
            action = {
                'set': include_options,
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

    def _symbol_name(self, symbol):
        if isinstance(symbol, Nonterminal):
            if symbol.passive or not self.grammar.rules[np(symbol)].option_list:
                return self._nonterminal_name(symbol)
            return self._meta_wrapper_name(symbol)
        return self._terminal_name(symbol)
