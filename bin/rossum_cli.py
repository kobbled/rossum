import os
import subprocess
import sys
import textwrap
from contextlib import contextmanager
from dataclasses import dataclass

try:
    from rich.console import Console as RichConsole
    from rich.panel import Panel
    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
    from rich.table import Table
    from rich.theme import Theme
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
except Exception:
    RichConsole = None
    Panel = None
    BarColumn = None
    Progress = None
    SpinnerColumn = None
    Table = None
    Theme = None
    Text = None
    TextColumn = None
    TimeElapsedColumn = None
    install_rich_traceback = None


class CliError(Exception):
    def __init__(self, title, detail=None, hints=None, exit_code=1):
        super().__init__(title)
        self.title = title
        self.detail = detail
        self.hints = hints or []
        self.exit_code = exit_code


@dataclass
class CommandResult:
    args: list
    returncode: int
    stdout: str
    stderr: str

    @property
    def output(self):
        return "\n".join([x for x in (self.stdout, self.stderr) if x])


class Console:
    def __init__(self, *, no_color=False, quiet=False, verbose=False):
        self.no_color = no_color or bool(os.environ.get("NO_COLOR"))
        self.quiet = quiet
        self.verbose = verbose
        encoding = (getattr(sys.stdout, "encoding", "") or "").lower()
        stdout_isatty = getattr(sys.stdout, "isatty", lambda: False)()
        rich_supported = RichConsole and not self.no_color and ("utf" in encoding or stdout_isatty)
        theme = Theme({
            "info": "cyan",
            "success": "green",
            "warning": "yellow",
            "error": "bold red",
            "muted": "dim",
        }) if Theme else None
        self.rich = RichConsole(
            safe_box=True,
            theme=theme,
            color_system="auto",
            highlight=False,
        ) if rich_supported else None

    def _print(self, message="", style=None):
        if self.quiet:
            return
        if self.rich:
            self.rich.print(message, style=style)
        else:
            print(_strip_rich_markup(str(message)))

    def print(self, message="", style=None):
        self._print(message, style=style)

    def info(self, message):
        self._print("[cyan]INFO[/cyan]  " + message)

    def success(self, message):
        self._print("[green]OK[/green]    " + message)

    def warning(self, message):
        self._print("[yellow]WARN[/yellow]  " + message)

    def error(self, message):
        self._print("[red]ERROR[/red] " + message)

    def debug(self, message):
        if self.verbose:
            self._print("[dim]DEBUG[/dim] " + message)

    def rule(self, title):
        if self.quiet:
            return
        if self.rich:
            self.rich.rule(title)
        else:
            print("\n" + title)
            print("-" * len(title))

    def table(self, title, columns, rows):
        if self.quiet:
            return
        if self.rich and Table:
            table = Table(title=title, show_lines=False)
            for column in columns:
                table.add_column(column)
            for row in rows:
                table.add_row(*[str(x) for x in row])
            self.rich.print(table)
            return

        if title:
            print(title)
        widths = [len(c) for c in columns]
        for row in rows:
            for idx, value in enumerate(row):
                widths[idx] = max(widths[idx], len(str(value)))
        print("  ".join(c.ljust(widths[idx]) for idx, c in enumerate(columns)))
        print("  ".join("-" * width for width in widths))
        for row in rows:
            print("  ".join(str(value).ljust(widths[idx]) for idx, value in enumerate(row)))

    def panel(self, title, body, style=None):
        if self.quiet:
            return
        if self.rich and Panel:
            self.rich.print(Panel(body, title=title, border_style=style or "cyan"))
        else:
            print(_strip_rich_markup(str(title)))
            print(textwrap.indent(_strip_rich_markup(str(body)), "  "))

    def print_error(self, error):
        if self.rich and Panel:
            body = []
            if error.detail:
                body.append(str(error.detail))
            if error.hints:
                body.append("")
                body.append("[bold]Fix:[/bold]")
                body.extend(["  - " + hint for hint in error.hints])
            self.rich.print(Panel("\n".join(body), title="[red]ERROR[/red] " + error.title, border_style="red"))
            return

        lines = ["ERROR: " + error.title]
        if error.detail:
            lines.extend(["", str(error.detail)])
        if error.hints:
            lines.extend(["", "Fix:"])
            lines.extend(["  - " + hint for hint in error.hints])
        print_box(lines, stream=sys.stderr)

    @contextmanager
    def status(self, message):
        if self.rich and not self.quiet:
            with self.rich.status(message, spinner="dots12"):
                yield
        else:
            self.info(_strip_rich_markup(message))
            yield


def _strip_rich_markup(value):
    for token in (
        "[red]", "[/red]", "[green]", "[/green]", "[yellow]", "[/yellow]",
        "[cyan]", "[/cyan]", "[dim]", "[/dim]", "[muted]", "[/muted]",
        "[bold]", "[/bold]", "[bold red]", "[/bold red]",
        "[bold cyan]", "[/bold cyan]",
        "[line]", "[/line]"
    ):
        value = value.replace(token, "")
    return value


def install_tracebacks(show_locals=False):
    if install_rich_traceback:
        install_rich_traceback(show_locals=show_locals)


def print_error_panel(title, body, *, no_color=False):
    no_color = no_color or bool(os.environ.get("NO_COLOR"))
    encoding = (getattr(sys.stderr, "encoding", "") or getattr(sys.stdout, "encoding", "") or "").lower()
    stderr_isatty = getattr(sys.stderr, "isatty", lambda: False)()
    stdout_isatty = getattr(sys.stdout, "isatty", lambda: False)()
    rich_supported = RichConsole and Panel and not no_color and ("utf" in encoding or stderr_isatty or stdout_isatty)
    if rich_supported:
        theme = Theme({
            "error": "bold red",
            "warning": "yellow",
            "muted": "dim",
            "path": "cyan",
            "line": "bold cyan",
        }) if Theme else None
        console = RichConsole(
            stderr=True,
            safe_box=True,
            theme=theme,
            color_system="auto",
            highlight=False,
        )
        console.print(Panel(str(body), title="[error]{}[/error]".format(title), border_style="error"))
        return

    print_box([
        _strip_rich_markup(str(title)),
        "",
        _strip_rich_markup(str(body)),
    ], stream=sys.stderr)


def run_command(args, *, cwd=None, timeout=None):
    try:
        proc = subprocess.run(
            args,
            cwd=cwd,
            timeout=timeout,
            capture_output=True,
            text=True,
            errors="replace",
        )
    except FileNotFoundError:
        raise CliError(
            "Command not found",
            detail="Could not find executable: {}".format(args[0]),
            hints=["Verify it is installed and available on PATH."],
        )
    except subprocess.TimeoutExpired as exc:
        raise CliError(
            "Command timed out",
            detail="Command exceeded {} seconds:\n{}".format(timeout, " ".join(args)),
            hints=["Check the robot/network/tool process, then retry."],
        ) from exc

    return CommandResult(args=list(args), returncode=proc.returncode, stdout=proc.stdout or "", stderr=proc.stderr or "")


def run_command_live(args, *, cwd=None, timeout=None, console=None, label=None):
    console = console or Console()
    output_lines = []
    status_message = label or "Running {}".format(args[0])

    try:
        proc = subprocess.Popen(
            args,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
        )
    except FileNotFoundError:
        raise CliError(
            "Command not found",
            detail="Could not find executable: {}".format(args[0]),
            hints=["Verify it is installed and available on PATH."],
        )

    def consume(status=None):
        for line in proc.stdout:
            line = line.rstrip()
            output_lines.append(line)
            if status:
                status.update("{}\n[muted]{}[/muted]".format(status_message, shorten(line, 100)))
            elif line:
                console.info(shorten(line, 140))

    try:
        if console.rich and Progress and not console.quiet:
            progress = Progress(
                SpinnerColumn("dots12", style="cyan"),
                TextColumn("[cyan]{task.description}[/cyan]"),
                BarColumn(bar_width=26, pulse_style="cyan", complete_style="cyan"),
                TimeElapsedColumn(),
                console=console.rich,
                transient=True,
            )
            with progress:
                task_id = progress.add_task(status_message, total=None)

                class ProgressStatus:
                    def update(self, message):
                        progress.update(task_id, description=shorten(_strip_rich_markup(message), 90))

                consume(ProgressStatus())
                returncode = proc.wait(timeout=timeout)
        else:
            console.info(status_message)
            consume()
            returncode = proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        raise CliError(
            "Command timed out",
            detail="Command exceeded {} seconds:\n{}".format(timeout, " ".join(args)),
            hints=["Check the robot/network/tool process, then retry."],
        ) from exc

    return CommandResult(args=list(args), returncode=returncode, stdout="\n".join(output_lines), stderr="")


def shorten(value, limit):
    value = value or ""
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 3)] + "..."


def print_box(lines, stream=None):
    stream = stream or sys.stdout
    text_lines = []
    for item in lines:
        text_lines.extend(str(item).splitlines() or [""])
    width = min(110, max([len(line) for line in text_lines] + [5]) + 4)
    border = "+" + "-" * width + "+"
    print(border, file=stream)
    for line in text_lines:
        if len(line) > width - 2:
            chunks = [line[i:i + width - 2] for i in range(0, len(line), width - 2)]
        else:
            chunks = [line]
        for chunk in chunks:
            print("| " + chunk.ljust(width - 2) + " |", file=stream)
    print(border, file=stream)


def read_text(path):
    with open(path, "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def fail_missing_file(path, purpose):
    raise CliError(
        "{} not found".format(purpose),
        detail="Missing file:\n  {}".format(os.path.abspath(path)),
        hints=["Run rossum configure/build first.", "Check that you are in the correct build directory."],
    )


def main_guard(func, *, tool_name=None):
    try:
        return func()
    except CliError as exc:
        Console().print_error(exc)
        return exc.exit_code
    except KeyboardInterrupt:
        Console().warning("{} cancelled.".format(tool_name or "Command"))
        return 130
    except Exception as exc:
        if os.environ.get("ROSSUM_DEBUG"):
            raise
        Console().print_error(CliError(
            "Internal {} error".format(tool_name or "command"),
            detail=str(exc),
            hints=["Set ROSSUM_DEBUG=1 and rerun to see a full traceback."],
            exit_code=1,
        ))
        return 1
