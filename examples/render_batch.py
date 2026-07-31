"""Render multiple ASE-readable structures with the same default settings.

Shell-expanded and quoted wildcards both work:

    python -m examples.render_batch *.vasp
    python -m examples.render_batch "structures/*.vasp" --view c --up b

``-m`` takes a module name, so omit the ``.py`` suffix.
"""

from __future__ import annotations

from argparse import ArgumentParser
from glob import glob
from pathlib import Path
from warnings import warn

try:
    from .render_file import (
        StructureReadError,
        add_camera_arguments,
        parse_arguments,
        render_file,
        resolve_povray_executable,
    )
except ImportError:  # Support copying both scripts elsewhere and running directly.
    from render_file import (
        StructureReadError,
        add_camera_arguments,
        parse_arguments,
        render_file,
        resolve_povray_executable,
    )


def expand_inputs(inputs: list[str]) -> list[Path]:
    """Expand wildcard patterns while retaining shell-expanded file names."""

    expanded: list[Path] = []
    seen: set[Path] = set()
    for item in inputs:
        matches = [Path(match) for match in glob(item)]
        if not matches and not any(character in item for character in "*?["):
            matches = [Path(item)]
        if not matches:
            raise ValueError(f"input pattern matched no files: {item}")
        for path in sorted(matches):
            if not path.is_file():
                raise ValueError(f"input is not a file: {path}")
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                expanded.append(path)
    return expanded


def build_parser() -> ArgumentParser:
    """Create the batch-render command-line parser."""

    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "inputs",
        nargs="+",
        help="structure files or wildcard patterns",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="output directory (default: beside each input file)",
    )
    add_camera_arguments(parser)
    return parser


def main() -> None:
    """Run the batch renderer."""

    parser = build_parser()
    arguments = parse_arguments(parser)
    try:
        inputs = expand_inputs(arguments.inputs)
        executable = resolve_povray_executable(arguments.povray)
        if arguments.output_dir is not None:
            arguments.output_dir.mkdir(parents=True, exist_ok=True)

        print(f"Rendering {len(inputs)} structure(s)")
        for input_path in inputs:
            output = (
                arguments.output_dir / f"{input_path.stem}.png"
                if arguments.output_dir is not None
                else input_path.with_suffix(".png")
            )
            try:
                render_file(
                    input_path,
                    output=output,
                    view=arguments.view,
                    up=arguments.up,
                    povray=executable,
                )
            except StructureReadError as error:
                warn(str(error), stacklevel=1)
    except (RuntimeError, ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
