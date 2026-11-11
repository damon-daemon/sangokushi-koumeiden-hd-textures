# Sangokushi Koumeiden — HD texture pack builder (DuckStation)

**Sangokushi Koumeiden** (三國志孔明伝, Koei) came out in Japan for the PlayStation and for
Windows 95. The Windows version has the same art drawn at a higher resolution. This repository
holds a script that builds a set of [DuckStation](https://www.duckstation.org/) texture
replacements from that art, so the PlayStation game shows the PC portraits (64x80 instead of
48x64), battle map units (2x), battle maps (6x), and hall and town pictures (2x).

> **This repository contains no game data.** No pictures, palettes or other content from either
> release are included here or in any download. The script reads **your own PC disc and your own
> PlayStation disc** and writes the PNG files on your machine. You need both discs.

It is a companion to the
[English translation patch](https://github.com/damon-daemon/sangokushi-koumeiden-english) but
does not contain it.

## What you need

- An image of the Windows 95 disc (raw `.img`/`.bin` or `.iso`), or a folder with its files
- Track 1 of the PlayStation disc (serial `SLPS-00688`), Japanese original or English-patched
- Python 3.10+
- DuckStation with a hardware renderer

To see every battle map in full, play the **English patch v0.9.4 or later**. On the unpatched
Japanese disc and on older patch versions the right part of some battle maps stays at the
original resolution, because of how the game draws the map; v0.9.4 changes that drawing.
Everything else works on any version.

## Building the pack

```
python -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python hdpack.py "/path/to/pc_disc.img" "/path/to/Sangokushi Koumeiden (Japan) (Track 1).bin" -o "<DuckStation folder>/textures/SLPM-86205/replacements"
```

This writes 564 PNG files and takes about a minute. Without `-o` they go to `out/`; copy them
to the `replacements` folder yourself. DuckStation lists this disc as `SLPM-86205`.

In DuckStation's graphics settings choose a hardware renderer and turn on the texture cache and
texture replacements.

Options: `--pc-colours` (hall pictures keep the PC palette instead of the PlayStation
picture's colours), `--keep-work` (keep the files taken from the discs in `work/`).

## What is replaced and what is not

Only art that exists on the PC disc is used; nothing is upscaled or generated. What stays at
PlayStation resolution:

- **Portraits**: 15 portraits were drawn new for the PlayStation version and have no PC
  counterpart: the Rattan Armor soldiers, Zhuge Xuan, Kongming's mother, Zhuge Ming, Pang Degong,
  Pang Shanmin, Meng Gongwei, the older Sima Yi, Empress Fu, Fu Wan, Empress Zhang, Sun
  Shangxiang, Huang Yueying and two more. Hat tops and plumes that reach above the PC portrait
  frame also stay PlayStation pixels (103 portraits).
- **Battle map units**: the effects (ships, fire ship, fire, confusion cloud, splash, arrows,
  starburst, boulder, slash) were redrawn for the PlayStation and look different on the PC. The
  Chief Strategist unit is a PlayStation-only sprite. Zhang Fei and Zhao Yun have
  their own sprites on the PlayStation only; with the pack they show the PC's Light Cavalry sprite
  (their unit class).
- **Battle maps**: two maps (43 and 44) are not on the PC disc.
- **Halls**: the PC picture covers the middle 200 of the PlayStation's 240 rows; the top and
  bottom 20 rows stay at PlayStation resolution, and the PC part is shown in the PlayStation
  picture's colours so the two join cleanly (`--pc-colours` keeps the PC colours). The PC's red
  exit arrow is painted into its pictures; that spot stays PlayStation pixels. Four halls show a
  person or moved furniture on the PlayStation only; those areas stay as they are. The gate hall
  has no PC picture.
- **Town overviews**: the stone frame above and below the picture is PlayStation-only. One town
  shows another hill on the PlayStation, which is kept, and a few colours (water) are taken from
  the PlayStation picture. Two overviews have no PC picture.
- **No PC picture at all**: the world map (the PC's is another picture), the title, loading and
  settings screens, the terrain strips of the attack close-up, the icons and stat plates, and the
  town and hall character sprites (same size on the PC).

## Repository layout

| Path | Contents |
|---|---|
| `hdpack.py` | The script: reads both discs, runs the generators, writes the PNGs |
| `gen/hdfaces.py`, `hdunits.py`, `hdmaps.py`, `hdbacks.py` | Portraits, battle map units, battle maps, halls and town overviews |
| `gen/ls11.py`, `timdump.py`, `disc.py` | PC archive format, PlayStation TIM pictures, disc image reader |

Tested with DuckStation (OpenGL renderer) on Linux.

## Credits

- Tools: [damon-daemon](https://github.com/damon-daemon)
- Sangokushi Koumeiden © Koei Tecmo. This is an unofficial fan project, not affiliated with
  or endorsed by Koei Tecmo. Please support the official releases.

## License

The tools and documentation in this repository are released under the [MIT License](LICENSE).
This covers only original work in this repository: the game itself and all of its content
(code, text, graphics, audio) are copyright Koei Tecmo and are not included or licensed here.
