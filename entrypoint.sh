#!/bin/bash

# Trigger an error if non-zero exit code is encountered
set -e

COMMAND="${1:-}"

# Dispatch the first argument to the CLI subcommand of the same name.
if [ "${COMMAND}" == "run" ]; then
    shift # consume "run"; remaining args are sources, e.g. "deezer"
    exec uv run /app/src/ha_yas105/main.py run "${@}"
else
    # An unknown command (debugging the container?): forward as is
    exec "${@}"
fi
