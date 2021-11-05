from bnf import NonLeftRecursiveGrammar, Terminal, Nonterminal
try:
    import ruamel_yaml as yaml
except ImportError:
    from ruamel import yaml


def L(l):
    ret = yaml.comments.CommentedSeq(l)
    ret.fa.set_flow_style()
    return ret


def branch_name(nt_name, indices):
    indices_str = ','.join([str(i) for i in sorted(indices)])
    return f'{nt_name}!{indices_str}'


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
            'fail!': [{'match': r'(?=\S)', 'pop': 1}],
            'fail_forever!': [{'match': r'\S', 'scope': 'invalid.illegal'}],
            'main': [{'match': '', 'push': L([
                'fail_forever!', 'fail_forever!', grammar.start.name
            ])}]
        }
        self._terminals = {}

        for nt in grammar.rules:
            alternation = grammar.rules[nt]
            table = grammar.table[nt]
            follow_set = grammar.follow[nt]
            self.contexts.update(
                self._generate_contexts_for_nt(nt, alternation, table, follow_set)
            )

        for name, context in self._terminals.values():
            self.contexts[name] = context

        for context in self.contexts.values():
            for match in context:
                for key, value in match.items():
                    if key in ('scope', 'meta_scope'):
                        match[key] = f'{value}.{scope}'

    def dump(self):
        return yaml.round_trip_dump({
            'version': 2,
            'name': self.syntax_name,
            'file_extensions': self.file_extensions,
            'scope': f'source.{self.scope}',
            'contexts': self.contexts,
        }, version='1.2')

    def _generate_contexts_for_nt(self, nt, alternation, table, follow_set):
        contexts = {}
        if alternation.meta_scope is not None:
            nt_context_name = f'{nt.name}"'
            nt_meta_name = f'{nt.name}"meta'
            contexts[nt.name] = [
                {'match': '', 'set': ([nt_meta_name, 'pop2!', nt_context_name])},
            ]
            contexts[nt_meta_name] = [
                {'meta_scope': alternation.meta_scope},
                {'match': '', 'pop': 2},
            ]
        else:
            nt_context_name = nt.name

        nt_context = []
        contexts[nt_context_name] = nt_context

        # follow set: no-op if any of the follow terminals are passive
        if any(t is not None and t.passive for t in follow_set):
            follow_check_name = 'pop2!'
        else:
            follow_check_name = f'{nt_context_name}@follow'
            contexts[follow_check_name] = [
                {'match': f'(?={t.regex})', 'pop': 2}
                for t in follow_set if t is not None
            ]
            contexts[follow_check_name].append({'include': 'fail!'})

        sorted_table = sorted(
            table.items(),
            key=lambda kv: tuple() if kv[0] == r'\S' else tuple(sorted(kv[1])[::-1]),
            reverse=True,
        )
        branch_contexts_todo = set()
        for t, indices in sorted_table:
            if len(indices) == 1:
                nt_context.append({
                    'match': f'(?={t})',
                    'set': f'{nt_context_name}@{list(indices)[0]}'
                })
            else:
                branch_context_name = branch_name(nt_context_name, indices)
                nt_context.append({
                    'match': f'(?={t})',
                    'set': branch_context_name,
                })
                branch_contexts_todo.add(tuple(sorted(indices)))
        if r'\S' not in table:
            nt_context.append({'include': 'fail!'})

        for indices in branch_contexts_todo:
            branch_context_name = branch_name(nt_context_name, indices)
            sorted_indices = sorted(indices)
            contexts[branch_context_name] = [{
                'match': '',
                'branch_point': branch_context_name,
                'branch': L([f'{branch_context_name}@{i}' for i in sorted_indices])
            }]
            fail_name = f'{branch_context_name}@fail'
            contexts[fail_name] = [{'match': '', 'fail': branch_context_name}]
            for i in sorted_indices[:-1]:
                contexts[f'{branch_context_name}@{i}'] = [{
                    'match': '',
                    'set': L(['pop3!', fail_name, follow_check_name, 'pop2!', f'{nt_context_name}@{i}']),
                }]
            contexts[f'{branch_context_name}@{sorted_indices[-1]}'] = [{
                'match': '',
                'set': L(['pop3!', 'pop3!', follow_check_name, 'pop2!', f'{nt_context_name}@{sorted_indices[-1]}']),
            }]

        for i, production in enumerate(alternation.productions):
            contexts[f'{nt_context_name}@{i}'] = [{
                'match': '',
                'set': L(self._production_stack(production))
            }]

        return contexts

    def _get_terminal_context(self, terminal):
        if terminal not in self._terminals:
            match = {'match': terminal.regex, 'pop': 2}
            if terminal.scope is not None:
                match['scope'] = terminal.scope
            matches = [match]
            if not terminal.passive:
                matches.append({'include': 'fail!'})
            self._terminals[terminal] = (
                f'T.{len(self._terminals)}',
                matches
            )
        return self._terminals[terminal]

    def _get_symbol_context_name(self, symbol):
        if isinstance(symbol, Nonterminal):
            return symbol.name
        name, _ = self._get_terminal_context(symbol)
        return name

    def _production_stack(self, production):
        if len(production.concats) == 0:
            return ['pop2!']
        production_stack = [
            self._get_symbol_context_name(production.concats[-1])
        ]
        for symbol in production.concats[:-1][::-1]:
            production_stack.append('pop2!')
            production_stack.append(self._get_symbol_context_name(symbol))
        return production_stack
