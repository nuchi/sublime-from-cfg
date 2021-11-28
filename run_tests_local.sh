#!/usr/bin/env bash

set -e

# find ... | xargs instead of find -exec so that errors get propagated
find tests -name '*.sbnf' -print0 \
    | xargs -0 -n1 ./venv/bin/sublime-from-cfg

docker run --rm \
    -v "$(pwd)"/syntax_tests:/home/syntax_tests \
    -v "$(pwd)"/tests:/home/Data/Packages/tests \
    ubuntu \
    /home/syntax_tests
