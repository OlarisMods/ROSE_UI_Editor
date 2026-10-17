# ROSE UI Editor -- how it works

The player-facing guide is `READ ME FIRST.txt`. This is the other half: how it
does what it does, and what not to break. Built 22 September 2026.

```
ROSE UI Editor.pyw   the window
engine.py        themes the base from two colours
installer.py     apply / undo / remove -- backups, the record, rollback
preview.py       the live preview, the randomiser, the too-close check
theme_core.py    from Theme Studio (with the comment and byte-exact fixes)
base/game/       the neutral base -- the ONLY files that ever enter the game
base/meta/       base_roles.json (which value is which role), gauge_rects.json
```

## The base

The Spooky UI rebuilt so it can be recoloured reliably -- see
NEUTRAL_BASE_MAP.md for every decision. The one rule everything rests on:

> **Every colour value belongs to exactly one role.**

The app recolours BY VALUE, so a value that meant two things could never be
given two answers. 60 roles, 60 values. Meaning colours take the stock game's
own values and are never themed.

`base/` is split into `game/` and `meta/` so the installer can only ever copy
game files. The prototype kept the manifest beside the game files; a plain copy
would have installed it into ROSE.

## The engine

Blend by brightness, measured **per element**: each element's own darker parts
take main, its own brightest take accent. Across a whole sheet, lighter elements
came out all accent. Named elements come from the stylesheets; unnamed shapes
are found as islands and measured one by one. Colour keeps lightness and takes
hue and saturation, so shading survives. The library produces output
byte-identical to the prototype that was tested in game.

## The installer -- what not to break

1. **Back up before writing**, into the app's own folder, outside the game.
2. **Record every file** and whether it existed.
3. **Save the record BEFORE copying**, marked unfinished. A failure while
   running rolls back on the spot; a crash is found and rolled back on the
   next start. The game folder is never left half-themed.
4. Undo restores FOLDERS too: a folder a theme created is removed if empty.
5. Paths are checked: nothing absolute, nothing climbing out with `..`.

Tested on a fake game folder with unrelated files and overlapping mods: apply,
apply, undo, undo; remove from two deep; a failure after 12 copies; a crash
after 20 (the rollback itself killed); unsafe paths. All exact, by SHA-1 of
every file and the folder list.

## The preview

A full build takes about five seconds. The preview themes a few real pieces
of the base in memory; everything independent of colour -- brightness, and how
much of each pixel goes to main versus accent -- is worked out once. A colour
change is a table lookup per pixel: 0.02 seconds.

## Chat colours, matched

Off by default; a toggle like the bars. Say becomes a near-white tinted by the
accent; the other channels step round the wheel from the accent's hue by the
golden angle -- the most even spread for any number -- and each takes the
nearest colour that is readable and clear of everything else.

**Never themed: error red and the five staff colours.** In chat a player's
whole line, name included, takes the channel colour -- so a channel on the GM
violet would make an ordinary player look like a GM. Every channel is kept
clear of every one of those.

**The limits are set against the stock game, measured:**

```
                          limit    stock's own
channel to channel          16       13   (party / quest)
channel to error or staff   24       8.4  (GROUP / DEV)
lightness, Lab              55       53.7 (group leader)
```

That 8.4 is a real finding: in the STOCK game, group chat (#9caff3) and the Dev
name colour (#91acff) are all but identical. Matched chat is safer than stock.

**The first version held every channel at one lightness** -- one ring of the
colour wheel has no room for 13 channels and 6 protected colours. Tested across
400 themes it put two channels on the SAME colour and one within 5.5 of a
protected one, because it quietly took its last try. Lightness tiers gave the
search a second dimension; it now RAISES instead of accepting a bad colour; and
across 2,005 themes -- including black, white, grey, pure red, and an accent set
to the GM violet itself -- every channel places, at 5 milliseconds.

## Seeds are words

Any text: `random.Random` seeds from a string the same way every time, so
"pumpkin" is always pumpkin. Case and spacing are ignored. Surprise me draws
from 72 evocative words -- easier to remember and share than a number -- and
none of them gives a too-close pair.

## The picker

Theme Studio's own, in this app's colours: Windows' chooser is a white box that
tkinter cannot restyle. It calls back as you drag, so the main preview shows the
whole theme changing; Cancel restores. It is placed over the colour controls,
never over the preview -- with no window manager it opened top-left, and on
Windows it could have landed on the very preview it exists to feed.

## Too close

CIE Lab distance under 28 -- "clearly two colours at a glance" -- blocks Apply
in Match mode, where health would take main and mana accent. The randomiser
never returns such a pair (checked over 500 seeds).

## Bugs worth remembering

**`poll()` threw every 80ms.** Reading an empty queue raises `queue.Empty`;
the loop had `finally` without `except`. It still worked, because the finally
kept it polling -- which is exactly why it would have gone unnoticed.

**A stale seed.** Picking a colour by hand left the old seed and "a triad
pair" beside colours that were no longer that seed's.

Both were caught by running the real window on a virtual display and
screenshotting it -- the same lesson as Theme Studio's "Generate latched dead":
a GUI that has never been driven has not been tested.

## Building an exe (later)

    py -m PyInstaller --noconfirm --windowed --onedir --name "ROSE UI Editor" ^
        --add-data "base;base" "ROSE UI Editor.pyw"

One folder, not one file: single-file builds unpack themselves at launch, which
antivirus tools distrust. The app finds `base` through `sys._MEIPASS`.
Unsigned, it will show SmartScreen's "More info, then Run anyway".

## Known gaps

- The clan badge plate is stock: Spooky never shipped its texture.
- Staff name colours come from stock but have not been seen in game yet.

## The 16 October 2026 patch -- what changed here, and why

Rednim published the whole RmlUi theme (`rednimgames/rose-public`) and moved
some window art. The base was brought across without losing the tested look:

- **Official stylesheets are READ, never shipped.** They live in
  `base/meta/sheets/`; the engine and the preview take sprite rectangles from
  there. An unchanged copy in the game would override the next patch's.
- **Art the patch did not move keeps our pixels byte for byte.** `glassui_00`,
  `02`, `03`, `04` and `gauge` are unchanged -- the six "new" sprites on
  `glassui_00` were art already on the sheet, only newly named.
- **Art it moved is relocated, not regenerated** (`relayout.py`). On
  `glassui_0` one sprite moved and the eight window-frame pieces were redrawn
  at a new size; only those, plus unnamed new art in empty space, come from
  the stock sheet -- greyed, then tone-matched to our base.
- **Colours: the official file plus our roles** (`transplant.py`). Each role
  is carried to the same selector and property; merged selectors match part
  by part; a stock colour that collides with a role value is nudged one step
  so it can never be themed by accident.
- **New sheets themed:** `glassui_01` (equipment slots, chat tabs, quickbar),
  `party_controls`, `group_manager`.
- **Presets are seeds:** void, crimson, moldie, ancient (`preview.PRESETS`).
- **The installer retires `spritesheet_glassui.css`** -- backed up and
  recorded, so Undo and Remove restore it exactly. Tested: apply, undo,
  apply twice and remove, failure mid-copy -- all byte-identical.

Bug caught on the way: the preview read rectangles only from `base/game`, so
with the stylesheet moved every button and bar would have VANISHED from the
preview without an error. It reads `base/meta/sheets` too now.
