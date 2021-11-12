from functools import wraps

from bnf import NonLeftRecursiveGrammar, Terminal, Nonterminal
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
                    print('new:' , _f_context)
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
        _ = self._nonpassive_name(grammar.start)
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

    def _nonpassive_context(self, nt):
        nonpassive_table, passive_table = self.np_table[nt], self.p_table[nt]
        passives = bool(passive_table)
        np_nt = np(nt)

        context = []
        if self.grammar.rules[np_nt].option_list:
            meta = [self._meta_name(nt), 'pop2!']
        else:
            meta = []

        if len(self.grammar.rules[np_nt].productions) == 1 and nonpassive_table:
            target = meta + self._production_stack(self.grammar.rules[np_nt].productions[0])
            if len(target) == 0:
                return [{'match': '', 'pop': 2}]
            return [{'match': '', 'set': L(target)}]

        for regex, indices in nonpassive_table:
            sorted_indices = sorted(indices)
            if passives or len(sorted_indices) > 1:
                context.append({
                    'match': f'(?={regex})',
                    'set': L(meta + [self._nonpassive_branch_name(nt, sorted_indices)]),
                })
            else:
                context.append({
                    'match': f'(?={regex})',
                    'set': L(meta + [self._production_name(nt, sorted_indices[0], False)]),
                })
        if passives:
            pattern = r'(?=\S)' if nonpassive_table else ''
            context.append({
                'match': pattern,
                'set': L(meta + [self._passive_branch_wrapper_name(nt)]),
            })
        else:
            context.append({'include': 'fail!'})
        return context

    @enqueue_todo(_nonpassive_context)
    def _nonpassive_name(self, nt):
        return nt.name

    # ---

    def _nonpassive_branch_context(self, nt, indices):
        passive_table = self.p_table[nt]
        passives = bool(passive_table)

        branch_name = self._nonpassive_branch_name(nt, indices)
        branches = [
            self._nonpassive_branch_tree_name(
                nt, indices, i, not passives and i == len(indices) - 1)
            for i in indices
        ]

        if passives:
            branches.append(self._passive_branch_wrapper_wrapper_name(nt))

        match = {
            'match': '',
            'branch_point': branch_name,
            'branch': L(branches),
        }

        return [match]

    @enqueue_todo(_nonpassive_branch_context)
    def _nonpassive_branch_name(self, nt, indices):
        return f'{self._nonpassive_name(nt)}@{",".join([str(i) for i in indices])}'

    # ---

    def _passive_branch_wrapper_wrapper_context(self, nt):
        return [{
            'match': '',
            'pop': 1,
            'set': self._passive_branch_wrapper_name(nt),
        }]

    @enqueue_todo(_passive_branch_wrapper_wrapper_context)
    def _passive_branch_wrapper_wrapper_name(self, nt):
        return f'{self._passive_branch_wrapper_name(nt)}@wrap!'

    # ---

    def _passive_branch_wrapper_context(self, nt):
        # If the passive nonterminal ultimately expands to the empty string,
        # then we actually want to wind back the current character to before
        # we started consuming characters, so that the consumed characters don't
        # get the meta scope of the passive nonterminal.
        return [{
            'match': '',
            'branch_point': self._passive_branch_wrapper_name(nt),
            'branch': L([self._passive_version_name(nt), 'pop3!'])
        }]

    @enqueue_todo(_passive_branch_wrapper_context)
    def _passive_branch_wrapper_name(self, nt):
        return f'{self._passive_version_name(nt)}@b!'

    # ---

    def _passive_branch_fail_context(self, nt):
        return [{'match': '', 'fail': self._passive_branch_wrapper_name(nt)}]

    @enqueue_todo(_passive_branch_fail_context)
    def _passive_branch_fail_name(self, nt):
        return f'{self._passive_branch_wrapper_name(nt)}@wfail!'

    # ---

    def _nonpassive_branch_tree_context(self, nt, indices, i, last):
        fail_name = 'pop3!' if last else \
            self._nonpassive_branch_fail_name(nt, indices)
        passive_in_follow = any(
            t.passive for t in self.grammar.follow[nt] if t is not None
        )
        if not passive_in_follow:
            follow = [self._nonpassive_follow_name(nt), 'pop2!']
        else:
            follow = []
        return [{
            'match': '',
            'set': L(['pop3!', fail_name] + follow + [self._production_name(nt, i, False)]),
        }]

    @enqueue_todo(_nonpassive_branch_tree_context)
    def _nonpassive_branch_tree_name(self, nt, indices, i, last):
        return f'{self._nonpassive_branch_name(nt, indices)}!{i}'

    # ---

    def _nonpassive_follow_context(self, nt):
        follow = self.grammar.follow[nt]
        if follow == {None}:
            return [{'include': 'fail!'}]
        context = []
        for t in follow:
            if t is None:
                continue
            if t.passive:
                return [{'match': '', 'pop': 2}]
            context.append({'match': f'(?={t.regex})', 'pop': 2})
        context.append({'include': 'fail!'})
        return context

    @enqueue_todo(_nonpassive_follow_context)
    def _nonpassive_follow_name(self, nt):
        return f'{self._nonpassive_name(nt)}@follow'

    # ---

    # def _passive_follow_context(self, nt):
    #     passive_nt = Nonterminal(nt.symbol, nt.args, True)
    #     return self._nonpassive_follow_context(passive_nt)

    @enqueue_todo(_nonpassive_follow_context)
    def _passive_follow_name(self, nt):
        return f'{self._passive_version_name(nt)}@follow'

    # ---

    def _nonpassive_branch_fail_context(self, nt, indices):
        return [{'match': '', 'fail': self._nonpassive_branch_name(nt, indices)}]

    @enqueue_todo(_nonpassive_branch_fail_context)
    def _nonpassive_branch_fail_name(self, nt, indices):
        return f'{self._nonpassive_branch_name(nt, indices)}@fail!'

    # ---

    def _production_stack(self, production):
        if len(production.concats) == 0:
            raise ValueError('This method should not be called on an empty production')

        production_stack = []
        for symbol in production.concats[::-1]:
            production_stack.extend([self._symbol_name(symbol), 'pop2!'])
        return production_stack[:-1]

    def _production_context(self, nt, index, passive):
        np_nt = np(nt)
        production = self.grammar.rules[np_nt].productions[index]

        # can assume production is not empty
        return [{'match': '', 'set': L(self._production_stack(production))}]

    @enqueue_todo(_production_context)
    def _production_name(self, nt, index, passive):
        np_nt = np(nt)
        production = self.grammar.rules[np_nt].productions[index]
        if len(production.concats) == 0:
            if not passive:
                return 'pop2!', False
            return self._passive_branch_fail_name(nt), False
            # return 'pop2!', False
        return f'{self._nonpassive_name(nt)}|{index}'

    # ---

    def _passive_branch_tree_context(self, nt, indices, i):
        fail_branch_name = self._passive_branch_part_fail_name(nt, indices)
        passive_in_follow = any(
            t.passive for t in self.grammar.follow[nt] if t is not None
        )
        if not passive_in_follow:
            follow = [self._passive_follow_name(nt), 'pop2!']
        else:
            follow = []
        return [{
            'match': '',
            'set': L(['pop5!', fail_branch_name] + follow + [self._production_name(nt, i, True)]),
        }]

    @enqueue_todo(_passive_branch_tree_context)
    def _passive_branch_tree_name(self, nt, indices, i):
        return f'{self._passive_part_branch_name(nt, indices)}!{i}'

    # ---

    def _passive_branch_part_fail_context(self, nt, indices):
        return [{'match': '', 'fail': self._passive_part_branch_name(nt, indices)}]

    @enqueue_todo(_passive_branch_part_fail_context)
    def _passive_branch_part_fail_name(self, nt, indices):
        str_indices = ','.join([str(i) for i in sorted(indices)])
        return f'{self._passive_version_name(nt)}@{str_indices}@fail!'

    # ---

    def _passive_part_branch_context(self, nt, indices):
        branch_name = self._passive_part_branch_name(nt, indices)
        branches = [
            self._passive_branch_tree_name(nt, indices, i)
            for i in indices
        ] + ['consume!']

        match = {
            'match': '',
            'branch_point': branch_name,
            'branch': L(branches)
        }

        return [match]

    @enqueue_todo(_passive_part_branch_context)
    def _passive_part_branch_name(self, nt, indices):
        indices = indices + ['c']
        return f'{self._passive_version_name(nt)}@{",".join([str(i) for i in indices])}'

    # ---

    def _passive_version_context(self, nt):
        passive_table = self.p_table[nt]
        # print('_passive_version_context:', nt.symbol, passive_table)
        context = []

        for regex, indices in passive_table:
            sorted_indices = sorted(indices)
            context.append({
                'match': f'(?={regex})',
                'push': self._passive_part_branch_name(nt, sorted_indices)
            })

        return context

    @enqueue_todo(_passive_version_context)
    def _passive_version_name(self, nt):
        return f'{self._nonpassive_name(nt)}@p!'

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
        return f'{self._nonpassive_name(nt)}@meta!'

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
                'with_prototype': [{'include': self._nonpassive_name(include_symbol)}],
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
            return self._nonpassive_name(symbol)
        return self._terminal_name(symbol)
