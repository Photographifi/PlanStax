import sys

CLI_COMMANDS = {"stack", "batch", "wavelets", "presets", "demo", "-h", "--help", "--version"}


def main() -> int:
    # `python -m planstax [files…]` opens the GUI; `python -m planstax stack …` is the CLI.
    if len(sys.argv) > 1 and sys.argv[1] in CLI_COMMANDS:
        from .cli import main as cli_main
        return cli_main()
    from .gui.app import main as gui_main
    return gui_main()


if __name__ == "__main__":
    sys.exit(main())
