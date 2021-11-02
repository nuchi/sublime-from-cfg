# Context-free grammar to Sublime-syntax file

This project produces sublime-syntax highlighting files from a description of a context-free grammar.

It implements a "Generalised Recursive Descent Parser" as described in [_Generalised recursive descent parsing and follow-determinism_](https://link.springer.com/content/pdf/10.1007%2FBFb0026420.pdf) by Adrian Johnstone and Elizabeth Scott. It's essentially a non-deterministic [LL(1)](https://en.wikipedia.org/wiki/LL_parser) parser. If the grammar happens to be LL(1) then no backtracking will happen and it's just an LL(1) parser. If the grammar is not LL(1), then alternatives will be tried in sequence, backtracking until one succeeds.

IMPORTANT: The grammar must be non-left-recursive, and also must be follow-determined. If the grammar is left-recursive then the program will complain and alert the user, but I don't know an algorithm to detect whether the grammar is follow-determined. **IF THE GRAMMAR IS _NOT_ FOLLOW-DETERMINED, THEN THE LANGUAGE RECOGNIZED BY THE GENERATED SYNTAX WILL SIMPLY NOT MATCH THE INPUT GRAMMAR.**

A grammar is _follow-determined_ if whenever a nonterminal X produces both `<string>` and `<string> y <...>`, then y is not in the follow set of X. Intuitively, a grammar is follow-determined whenever a single lookahead token is enough to tell us whether it's okay to pop out of the context for X or if we should keep going within X. (i.e. if we've just consumed the prefix `<string>` and need to decide whether to finish with X or to keep consuming, then the presence or absence of the next token in the follow set of X had better be enough to tell us which option to take, because once we pop out of X then we can't backtrack to try other options anymore.)

## Implementation

Sublime syntax files allow one to define _contexts_; within each context one can match against any number of regular expressions (including lookaheads) and then perform actions like pushing other contexts onto the context stack, pop out of the context, set the scope of the consumed tokens (i.e. instruct Sublime Text that a token is e.g. a function definition and highlight it appropriately), and others. One can also set a branch point and try multiple branches in sequence; if an action taken is to `fail` that branch point, then the syntax engine backtracks and tries the next branch in the sequence.

See [the Wikipedia page on LL parsers](https://en.wikipedia.org/wiki/LL_parser) for more details on how LL parsers work in general. What I do here is always indicate "success" by `pop: 2`; i.e. popping twice out of the current context, and failure by `pop: 1`. Contexts for a given production are pushed onto the stack interleaved by a `pop2!` context which always pops 2 contexts off the stack. Therefore a failure, which pops once, moves into the "always pop 2" stream until it hits a failure context (to backtrack and try a different branch) or pops all the way out of the current stack.

## TO-DO:

- [ ] Detect whether the input grammar is follow-determined. This may be undecidable for all I know.
- [ ] Accept a convenient text description of a grammar rather than require constructing a Python object by hand. [Benjamin Schaaf's sbnf](https://github.com/BenjaminSchaaf/sbnf/) is a project with essentially the same goals as this one, and has a very nice syntax for defining grammars so it'd be nice to allow inputs in that format.
- [ ] Also add other conveniences from sbnf such as a prototype context, and embedding other grammars.
