import re
import subprocess
from functools import reduce
from pathlib import Path
from typing import Iterator

import typer
from rich.console import Console

console = Console()
app = typer.Typer(help="Manage VSCode theme colors with pastel")


def extract_colors(content: str) -> list[str]:
    colors = list(set(re.findall(r'"(#[0-9a-fA-F]+?)"', content)))
    if not colors:
        return []

    process = subprocess.run(
        ["pastel", "sort-by", "hue"],
        input="\n".join(colors),
        text=True,
        capture_output=True,
        check=True,
    )

    hue_sorted = process.stdout.strip().split("\n")

    process = subprocess.run(
        ["pastel", "sort-by", "luminance"],
        input="\n".join(hue_sorted),
        text=True,
        capture_output=True,
        check=True,
    )

    return [
        subprocess.run(
            ["pastel", "format", "hex"],
            input=color,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        for color in process.stdout.strip().split("\n")
        if color
    ]


def get_paths(theme_file: Path) -> tuple[Path, Path]:
    og_file = theme_file.parent / f"og_{theme_file.name}"
    replacements_file = theme_file.parent / f"replacements_{theme_file.stem}.txt"
    return og_file, replacements_file


def read_replacements(replacements_file: Path) -> Iterator[tuple[str, str]]:
    for line in replacements_file.read_text().strip().split("\n"):
        if line and " " in line:
            old, new = line.split(" ", 1)
            yield old.strip(), new.strip()


def apply_color_replacement(content: str, old: str, new: str) -> str:
    if old == new:
        return content

    console.print(f"replacing {old} with {new}")

    return re.sub(re.escape(old), new, content, flags=re.IGNORECASE)


def run_pastel_command(color: str, command: str) -> str:
    try:
        cmd_parts = command.split()

        result = subprocess.run(
            ["pastel"] + cmd_parts + [color],
            capture_output=True,
            text=True,
            check=True,
        )

        formatted = subprocess.run(
            ["pastel", "format", "hex"],
            input=result.stdout.strip(),
            capture_output=True,
            text=True,
            check=True,
        )

        return formatted.stdout.strip()
    except subprocess.CalledProcessError as e:
        console.print(f"[red]ERROR: pastel {command} failed for {color}: {e}[/red]")
        return color


@app.command()
def init(theme_file: Path = typer.Argument(..., help="Theme JSON file")):
    if not theme_file.exists():
        raise typer.BadParameter(f"Theme file '{theme_file}' not found")

    og_file, replacements_file = get_paths(theme_file)

    if not og_file.exists():
        og_file.write_text(theme_file.read_text())
        console.print(f"Saved original theme as {og_file}")

    colors = extract_colors(og_file.read_text())
    replacements_content = "\n".join(f"{color} {color}" for color in colors)
    replacements_file.write_text(replacements_content)

    console.print(f"Initialized replacements file: {replacements_file}")


@app.command()
def apply(theme_file: Path = typer.Argument(..., help="Theme JSON file")):
    if not theme_file.exists():
        raise typer.BadParameter(f"Theme file '{theme_file}' not found")

    og_file, replacements_file = get_paths(theme_file)

    if not replacements_file.exists():
        raise typer.BadParameter(f"{replacements_file} not found. Run init first.")

    content = og_file.read_text()

    final_content = reduce(
        lambda acc, replacement: apply_color_replacement(acc, *replacement),
        read_replacements(replacements_file),
        content,
    )

    theme_file.write_text(final_content)
    console.print(f"Applied replacements to {theme_file}")


@app.command()
def run(
    theme_file: Path = typer.Argument(..., help="Theme JSON file"),
    pastel_commands: list[str] = typer.Argument(..., help="Pastel commands to run"),
):
    og_file, replacements_file = get_paths(theme_file)

    if not replacements_file.exists():
        raise typer.BadParameter(f"{replacements_file} not found. Run init first.")

    console.print(f"Reading from: {replacements_file}")
    console.print(f"Processing {len(pastel_commands)} pastel command(s)")

    new_replacements = []
    for old, current in read_replacements(replacements_file):
        console.print(f"Processing {old}", end="")

        final_color = reduce(
            lambda color, cmd: (
                lambda result: (console.print(f" -> {result}", end=""), result)[1]
            )(run_pastel_command(color, cmd)),
            pastel_commands,
            current,
        )

        console.print()
        new_replacements.append(f"{old} {final_color}")

    replacements_file.write_text("\n".join(new_replacements))
    apply(theme_file)


if __name__ == "__main__":
    app()
