"""preview.py -- small real pieces of the UI, themed in memory, instantly.

A full build takes seconds, which is fine for Apply and useless for dragging a
colour. So the preview themes a few real pieces of the base -- the minimap frame,
buttons in three states, the character-sheet bars, our class icons -- using the
engine's own rules. What makes it instant: everything that does NOT depend on
the colours is worked out once, when the app opens -- each pixel's brightness,
and how much of it goes to main versus accent. A colour change is then a table
lookup per pixel.

Also here: the randomiser, and the check that stops two colours being too close.
"""

import base64
import colorsys
import json
import os
import random
import struct
import zlib

import engine
import theme_core as core

MINIMAP = ('3ddata/control/Res/glassui_03.dds', (221, 221, 219, 219))
BUTTONS = ['button-settings_-n', 'button-settings_-h', 'button-settings_-a', 'button-scoreboard-n']
BARS = [('GEN_GAUGE02', 'hp'), ('GEN_GAUGE03', 'mp'), ('GEN_GAUGE01', 'exp')]
ICONS = [2, 3, 4, 5, 14, 15, 16, 30, 117]


class Piece:
    """A crop of the base: per pixel (brightness, alpha, how-much-accent)."""

    def __init__(self, sheet, rect, kind='blend', scale=1, only_grey=False):
        x0, y0, w, h = rect
        self.kind = kind
        self.w, self.h = w // scale, h // scale
        raw = []
        for y in range(self.h):
            for x in range(self.w):
                vs, alphas, keep = [], [], None
                for dy in range(scale):
                    for dx in range(scale):
                        r, g, b, a = sheet.get(x0 + x * scale + dx, y0 + y * scale + dy)
                        vs.append(r)
                        alphas.append(a)
                        if only_grey and not (r == g == b) and a:
                            keep = (r, g, b, a)
                raw.append((sum(vs) // len(vs), sum(alphas) // len(alphas), keep))
        self.px = raw
        vals = sorted(v / 255.0 for v, a, keep in raw if a > 40 and keep is None)
        if vals and kind == 'blend':
            lo = vals[int(0.10 * (len(vals) - 1))]
            hi = vals[int(0.97 * (len(vals) - 1))]
            span = hi - lo
        else:
            lo = span = 0
        self.k = [(engine.smooth(0.55, 0.92, (v / 255.0 - lo) / span) if span > 0.02
                   else engine.smooth(0.45, 0.78, v / 255.0)) for v, a, keep in raw]

    def render(self, main_lut, accent_lut):
        out = bytearray()
        for (v, a, keep), k in zip(self.px, self.k):
            if keep is not None:
                out += bytes(keep)
                continue
            m = main_lut[v]
            if self.kind == 'fill':
                out += bytes((m[0], m[1], m[2], a))
                continue
            c = accent_lut[v]
            out += bytes((int(m[0] * (1 - k) + c[0] * k), int(m[1] * (1 - k) + c[1] * k),
                          int(m[2] * (1 - k) + c[2] * k), a))
        return bytes(out)


def lut(target):
    """colourize() for all 256 brightness levels, once per colour."""
    return [tuple(int(round(x * 255)) for x in engine.colourize(v / 255.0, target))
            for v in range(256)]


class Preview:
    def __init__(self, base_dir):
        game = os.path.join(base_dir, 'game')
        self.meta = engine.load_meta(base_dir)
        rects = {}
        # official rectangles live in base/meta/sheets since the 16 October
        # patch; reading only base/game here found nothing, and every button and
        # bar quietly vanished from the preview instead of failing loudly
        for s in core.read_sheets(self.meta['sheets_dir']) + core.read_sheets(game):
            for name, r in s['sprites'].items():
                rects.setdefault(name, (s['src'], r))
        mm = engine.Sheet(os.path.join(game, MINIMAP[0]))
        self.minimap = Piece(mm, MINIMAP[1], scale=2)
        g0 = engine.Sheet(os.path.join(game, 'data/ui/themes/rose/imgs/glassui_0.dds'))
        self.buttons = [Piece(g0, rects[n][1]) for n in BUTTONS if n in rects]
        g2 = engine.Sheet(os.path.join(game, '3ddata/control/Res/glassui_02.dds'))
        self.bars = [(kind, Piece(g2, rects[n][1], kind='fill')) for n, kind in BARS if n in rects]
        spec = self.meta['roles']['stateicon']
        st = engine.Sheet(os.path.join(game, spec['files'][0]))
        p, c, cols = spec['grid']['pitch'], spec['grid']['cell'], spec['grid']['columns']
        self.icons = [Piece(st, ((i % cols) * p, (i // cols) * p, c, c), only_grey=True)
                      for i in ICONS]
        self.meaning = self.meta['roles']['meaning']
        self.chrome = self.meta['roles']['chrome']

    def render(self, main, accent, mode, chat='classic'):
        """Everything the window needs to draw: images as PNG, and text colours."""
        ml, al = lut(main), lut(accent)
        out = {'minimap': png(self.minimap.w, self.minimap.h, self.minimap.render(ml, al)),
               'buttons': [png(b.w, b.h, b.render(ml, al)) for b in self.buttons],
               'icons': [png(i.w, i.h, i.render(ml, al)) for i in self.icons],
               'bars': []}
        for kind, bar in self.bars:
            t = lut(engine.bar_target(kind, main, accent, mode))
            out['bars'].append((kind, png(bar.w, bar.h, bar.render(t, t))))
        hexc = lambda c: '#%02x%02x%02x' % c
        out['colours'] = {
            'background': hexc(engine.role_colour('main-dark', main, accent)),
            'accent': hexc(accent), 'accent-dim': hexc(engine.role_colour('accent-dim', main, accent)),
            'main': hexc(main), 'text': self.chrome['text'],
            'party': self.meaning['chat.party'], 'clan': self.meaning['chat.clan'],
            'shout': self.meaning['chat.shout'], 'whisper': self.meaning['chat.whisper'],
            'say': self.meaning['chat.say'], 'trade': self.meaning['chat.trade']}
        if chat == 'match':
            pal = engine.chat_palette(main, accent, self.meaning)
            for key in ('party', 'clan', 'shout', 'whisper', 'say', 'trade'):
                out['colours'][key] = hexc(pal['chat.' + key])
        return out


def png(w, h, rgba):
    """A PNG, base64 -- what tkinter's PhotoImage takes. Standard library only."""
    rows = b''.join(b'\x00' + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))

    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data +
                struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff))
    raw = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>2I5B', w, h, 8, 6, 0, 0, 0)) +
           chunk(b'IDAT', zlib.compress(rows, 6)) + chunk(b'IEND', b''))
    return base64.b64encode(raw).decode('ascii')


# ---------------------------------------------------------------- randomiser

SCHEMES = [('complementary', 0.5), ('split', 0.42), ('split', 0.58),
           ('triad', 1 / 3.0), ('triad', 2 / 3.0), ('square', 0.25)]

# What "Surprise me" draws from: a word is easier to remember and pass on than a
# number. Any word, name or number typed in works as a seed too.
WORDS = ("pumpkin ember tidepool moonlight thornwood saltmarsh cinder lantern foxglove "
         "wisteria nightshade copper harbor glacier sandstone bramble velvet twilight "
         "starfall driftwood marigold obsidian heather rainforest aurora cobalt lichen "
         "sunset juniper mistral orchid quartz saffron tundra willow cascade ironwood "
         "peony stormcloud honeycomb seafoam wildfire duskrose frostbite goldleaf "
         "hollow ivory kelp lavender meadow nebula opal pepper riverstone shadow "
         "thistle umber vesper whisper yarrow zephyr bonfire candlewick daybreak "
         "eclipse fennel graphite hearth indigo jadeite kingfisher larkspur").split()


def seed_key(text):
    """Seeds are TEXT: a word, a name, a number. Case and spaces do not matter,
    so "Pumpkin" and " pumpkin " are the same theme."""
    return ' '.join(str(text).lower().split())


# The released themes, by name. Typing one as a seed gives its colours, so
# they live in the app without a single new button -- and every other word
# still rolls a random pair exactly as before. Colours measured from each
# pack's own artwork: the median of its dark panels and of its brightest hue.
PRESETS = {
    'void':    ((59, 28, 70), (150, 82, 213)),
    'moldie':  ((32, 54, 74), (82, 145, 213)),
    'crimson': ((80, 27, 20), (204, 72, 80)),
    'ancient': ((42, 48, 54), (121, 208, 169)),
}


def random_pair(seed):
    """Two colours from a SEED, so a good accident can be kept and shared.

    Not confetti: a base hue and a scheme that is reliably not ugly. Main is
    deeper (it fills panels and glass); accent is brighter (it lights edges and
    text). Rerolled internally until the pair is clearly two colours."""
    if seed_key(seed) in PRESETS:
        main, accent = PRESETS[seed_key(seed)]
        return main, accent, 'preset'
    r = random.Random(seed_key(seed))
    for _ in range(50):
        base = r.random()
        name, offset = r.choice(SCHEMES)
        main = tuple(int(v * 255) for v in colorsys.hsv_to_rgb(
            base, r.uniform(0.45, 0.85), r.uniform(0.50, 0.80)))
        accent = tuple(int(v * 255) for v in colorsys.hsv_to_rgb(
            (base + offset) % 1.0, r.uniform(0.40, 0.80), r.uniform(0.82, 1.0)))
        if not too_close(main, accent):
            return main, accent, name
    return main, accent, name


def surprise_word():
    return random.choice(WORDS)


# ---------------------------------------------------------------- too close?

difference = engine.difference
too_close = engine.too_close
