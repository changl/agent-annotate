"""The `annotate` console script. The UserPromptSubmit hook runs before every
prompt in every session, so `hook-check` never imports the full CLI."""
import sys


def hook_check() -> int:
    """Claude Code's payload on stdin. Never blocks a prompt; always 0."""
    from .hooks.check_comment_bus import main as hook_main

    try:
        hook_main()
    except SystemExit:
        pass
    except Exception:
        pass
    return 0


def main():
    if sys.argv[1:] == ["hook-check"]:
        sys.exit(hook_check())
    from .cli import main as cli_main

    cli_main()
