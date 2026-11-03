#!/usr/bin/env python3
"""Draft shiny palettes for the walking Pokémon's overworld sprites, from their battle sprites' palettes.

    overworld_shiny_palettes.py generate res [--force]
    overworld_shiny_palettes.py preview res OUTPUT_DIR

The game has no shiny overworld sprites: each walking Pokémon of res/field/actors/pokemon/<code>/ has one palette,
sprite.pal, drawn apart from its battle sprite's, with other colors in another order. generate writes a first draft of
a shiny one beside it, sprite_shiny.pal, which a hack can load for a shiny Pokémon and which is meant to be touched up
by hand: for each overworld color it finds the nearest color that the battle sprite draws with in its normal.pal, by
CIELAB distance, and moves it as far as that color moves in shiny.pal, so the overworld sprite keeps its own shading.
Colors are rounded to the 5 bits per channel that the DS shows. Index 0, transparent, is copied. The battle palettes
are the species' res/pokemon/<species>/, or its form_<n>/ where the form has its own; a female sprite uses the
species'. An existing sprite_shiny.pal is kept, as it may have been edited, unless --force is given.

preview writes PNG sheets of every walking Pokémon's first frame, normal and draft shiny side by side at twice their
size, ten rows of eight per sheet, with preview.txt naming each place, to judge the drafts. The build doesn't read
sprite_shiny.pal yet.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tools.data.nitro_2d import (color5, palette_indices, read_indexed_png, read_palette,  # noqa: E402
                                 write_palette, write_rgba_png)

SHINY_PALETTE = "sprite_shiny.pal"
COLUMNS, ROWS, SCALE, CELL = 8, 10, 2, 64
BACKGROUND = (160, 168, 176)


def linear(axis):
    value = axis / 255
    return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4


def gamma(value):
    value = max(0.0, min(1.0, value))
    return 255 * (value * 12.92 if value <= 0.0031308 else 1.055 * value ** (1 / 2.4) - 0.055)


def to_lab(color):
    r, g, b = map(linear, color)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t):
        return t ** (1 / 3) if t > 216 / 24389 else (24389 / 27 * t + 16) / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def from_lab(lab):
    l, a, b = lab
    fy = (l + 16) / 116
    fx, fz = fy + a / 500, fy - b / 200

    def f(t):
        return t ** 3 if t ** 3 > 216 / 24389 else (116 * t - 16) / (24389 / 27)

    x, y, z = f(fx) * 0.95047, f(fy), f(fz) * 1.08883
    r = 3.2406 * x - 1.5372 * y - 0.4986 * z
    g = -0.9689 * x + 1.8758 * y + 0.0415 * z
    b = 0.0557 * x - 0.2040 * y + 1.0570 * z
    return tuple(round(gamma(v)) for v in (r, g, b))


def ds_color(color):
    """Returns the color as the DS shows it, 5 bits a channel, written back in 8 bits as the palettes are."""
    return tuple(axis * 255 // 31 for axis in color5(color))


def battle_folder(res: Path, entry: dict) -> Path:
    species = res / "pokemon" / entry["species"].removeprefix("SPECIES_").lower()
    form = species / f"form_{entry['form']}"
    return form if entry["form"] and (form / "normal.pal").is_file() else species


def used_colors(folder: Path, normal: list) -> list[int]:
    """Returns the indices of the battle palette that the front and back sprites draw with, but 0."""
    used = set()
    for name in ("front.png", "back.png"):
        if (folder / name).is_file():
            _, _, pixels, png_colors = read_indexed_png(folder / name)
            used |= set(palette_indices(folder / name, pixels, png_colors, normal))
    return sorted(used - {0}) or list(range(1, len(normal)))


def draft(overworld: list, normal: list, shiny: list, candidates: list[int]) -> list:
    normal_lab = {i: to_lab(normal[i]) for i in candidates}
    result = [overworld[0]]
    for color in overworld[1:]:
        lab = to_lab(color)
        nearest = min(candidates, key=lambda i: sum((p - q) ** 2 for p, q in zip(lab, normal_lab[i])))
        moved = tuple(p + s - n for p, s, n in zip(lab, to_lab(shiny[nearest]), normal_lab[nearest]))
        result.append(ds_color(from_lab(moved)))
    return result


def walking_pokemon(res: Path):
    for path in sorted((res / "field" / "actors" / "pokemon").iterdir()):
        if (path / "pokemon.json").is_file():
            yield path, json.loads((path / "pokemon.json").read_text())


def generate(res: Path, force: bool):
    written = kept = 0
    for path, entry in walking_pokemon(res):
        target = path / SHINY_PALETTE
        if target.exists() and not force:
            kept += 1
            continue
        folder = battle_folder(res, entry)
        normal, shiny = read_palette(folder / "normal.pal"), read_palette(folder / "shiny.pal")
        overworld = read_palette(path / "sprite.pal")
        target.write_text(write_palette(draft(overworld, normal, shiny, used_colors(folder, normal))))
        written += 1
    print(f"wrote {written} shiny palettes, kept {kept} that exist")


def first_frame(path: Path, palette: list):
    width, height, pixels, png_colors = read_indexed_png(path / "sprite.png")
    indices = palette_indices(path / "sprite.png", pixels, png_colors, read_palette(path / "sprite.pal"))
    return height, [[palette[indices[y * width + x]] if indices[y * width + x] else None for x in range(height)]
                    for y in range(height)]


def preview(res: Path, output: Path):
    output.mkdir(parents=True, exist_ok=True)
    entries = [path for path, _ in walking_pokemon(res) if (path / SHINY_PALETTE).is_file()]
    per_sheet = COLUMNS * ROWS
    cell_width, cell_height = (2 * CELL + 8) * SCALE, (CELL + 8) * SCALE
    legend = []
    for sheet, start in enumerate(range(0, len(entries), per_sheet)):
        width, height = COLUMNS * cell_width, ROWS * cell_height
        image = bytearray(bytes((*BACKGROUND, 255)) * width * height)
        for place, path in enumerate(entries[start:start + per_sheet]):
            row, column = divmod(place, COLUMNS)
            legend.append(f"sheet {sheet:02} row {row} column {column}: {path.name}")
            for side, name in enumerate(("sprite.pal", SHINY_PALETTE)):
                size, frame = first_frame(path, read_palette(path / name))
                left = column * cell_width + (side * (CELL + 8) + (CELL - size) // 2) * SCALE
                top = row * cell_height + (4 + CELL - size) * SCALE
                for y, line in enumerate(frame):
                    for x, color in enumerate(line):
                        if color is None:
                            continue
                        for dy in range(SCALE):
                            offset = ((top + y * SCALE + dy) * width + left + x * SCALE) * 4
                            image[offset:offset + 4 * SCALE] = bytes((*color, 255)) * SCALE
        (output / f"preview_{sheet:02}.png").write_bytes(write_rgba_png(width, height, bytes(image)))
    (output / "preview.txt").write_text("\n".join(legend) + "\n")
    print(f"wrote {len(entries)} Pokémon to {output}")


def main():
    if len(sys.argv) in (3, 4) and sys.argv[1] == "generate" and sys.argv[3:] in ([], ["--force"]):
        generate(Path(sys.argv[2]), sys.argv[3:] == ["--force"])
    elif len(sys.argv) == 4 and sys.argv[1] == "preview":
        preview(Path(sys.argv[2]), Path(sys.argv[3]))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
