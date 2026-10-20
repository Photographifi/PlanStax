import os
import sys

CLI_COMMANDS = {"stack", "batch", "mosaic", "wavelets", "presets", "demo", "-h", "--help", "--version"}


def _without_language(args: list[str]) -> tuple[list[str], str | None]:
    """The arguments without a leading --lang option, and the language it gives."""
    if args and args[0].startswith("--lang="):
        return args[1:], args[0].split("=", 1)[1]
    if len(args) > 1 and args[0] == "--lang":
        return args[2:], args[1]
    return args, None


def main() -> int:
    # `python -m planstax [files…]` opens the GUI; `python -m planstax stack …` is the CLI.
    # Either may start with --lang fr|en|es.
    rest, code = _without_language(sys.argv[1:])
    if rest and rest[0] in CLI_COMMANDS:
        from .cli import main as cli_main
        return cli_main()
    if code:
        os.environ["PLANSTAX_LANG"] = code
    from .gui.app import main as gui_main
    return gui_main([sys.argv[0]] + rest)


if __name__ == "__main__":
    sys.exit(main())
