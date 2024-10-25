## Code structure

`xpk` package consists of three packages
- `parsers` - user-facing code that parses commands: `xpk cluster`, `xpk workload`, `xpk inspector`
- `commands` - code responsible for handling parsed commands
- `core` - building blocks for `commands` package with all of the `gcloud` invocations
- `utils` - contains utility modules shared across the whole codebase

Additionally there are modules
- `main.py` - serves as an entrypoint to the xpk