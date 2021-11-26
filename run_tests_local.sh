#!/usr/bin/env bash

set -e

find tests -name '*.sbnf' -exec ./venv/bin/sublime-from-cfg {} \;

docker run --rm \
    -v "$(pwd)"/syntax_tests:/home/syntax_tests \
    -v "$(pwd)"/tests:/home/Data/Packages/tests \
    ubuntu \
    /home/syntax_tests
