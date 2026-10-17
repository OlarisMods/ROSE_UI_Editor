"""engine.py -- theme the neutral base from two colours.

The method, proven in game before any window was built:

ARTWORK -- blend by brightness, MEASURED PER ELEMENT
    Each element's own darker parts take MAIN and its own brightest parts take
    ACCENT, blended smoothly. Measured across a whole sheet instead, an element
    that is simply lighter overall comes out all accent. Named elements come from
    the stylesheets; everything else is split into its separate shapes, each
    measured on its own. Colour keeps each pixel's lightness and takes hue and
    saturation from the target, so shading survives any colour.

THE BARS -- one colour each
    classic   health red, mana blue, experience gold
    match     health = main, mana = accent, experience = silver

COLOURS -- every chrome role set relative to the chosen colours; text, outline,
    disabled and every meaning colour never touched.

STATE ICONS -- only our bordered class cells, only their exactly-grey pixels.

The base is never written to: build() copies it first.
"""

import colorsys
import json
import os
import shutil

import theme_core as core

CHROME_SHEETS = ['data/ui/themes/rose/imgs/glassui_0.dds',
                 '3ddata/control/Res/glassui_00.dds', '3ddata/control/Res/glassui_01.dds',
                 '3ddata/control/Res/glassui_02.dds',
                 '3ddata/control/Res/glassui_03.dds', '3ddata/control/Res/glassui_04.dds',
                 '3ddata/control/Res/ui06_2.dds', 'data/ui/themes/rose/imgs/gauge.dds',
                 # new with the 16 October 2026 patch -- the party window's
                 # buttons and the HUD's group manager button
                 'data/ui/themes/rose/imgs/party_controls.dds',
                 'data/ui/themes/rose/imgs/group_manager.dds']

# the character sheet's bars -- confirmed in game: 01 EXP, 02 HP, 03 MP
CHAR_SHEET = {'GEN_GAUGE01': 'exp', 'GEN_GAUGE02': 'hp', 'GEN_GAUGE03': 'mp'}

CLASSIC = {'hp': (214, 54, 54), 'mp': (60, 112, 232), 'exp': (232, 186, 60),
           'green': (72, 200, 92), 'pink': (236, 110, 190), 'purple': (160, 92, 232)}
SILVER = (196, 198, 206)


# ---------------------------------------------------------------- colour maths

def hls(c):
    return colorsys.rgb_to_hls(*(v / 255.0 for v in c))


def rgb(h, l, s):
    return tuple(int(round(v * 255)) for v in colorsys.hls_to_rgb(h, l, s))


def colourize(v, target):
    """Keep lightness v (0..1); take hue and saturation from the target."""
    h, _l, s = hls(target)
    return colorsys.hls_to_rgb(h, v, s)


def smooth(e0, e1, x):
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    return tuple(int(round(a[i] * (1 - t) + b[i] * t)) for i in range(3))


def role_colour(role, main, accent):
    """A chrome role's colour, relative to the two chosen colours."""
    white = (255, 255, 255)
    if role == 'main':
        return main
    if role == 'main-bright':
        return mix(main, white, 0.35)
    if role == 'main-dark':
        h, _l, s = hls(main)
        return rgb(h, 0.045, min(s, 0.5))
    if role == 'accent':
        return accent
    if role == 'accent-bright':
        return mix(accent, white, 0.40)
    if role == 'accent-dim':
        h, l, s = hls(accent)
        return rgb(h, l * 0.72, s * 0.6)
    return None


# ---------------------------------------------------------------- how different?

def _lab(c):
    def lin(v):
        v /= 255.0
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (lin(v) for v in c)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = (0.2126 * r + 0.7152 * g + 0.0722 * b)
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
    f = lambda t: t ** (1 / 3.0) if t > 0.008856 else 7.787 * t + 16 / 116.0
    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def difference(a, b):
    """How different two colours LOOK -- CIE Lab distance; about 2 is just visible."""
    import math
    return math.dist(_lab(a), _lab(b))


def too_close(a, b, limit=28):
    """28 in Lab is 'clearly two colours' at a glance, even on a small bar."""
    return difference(a, b) < limit


# ---------------------------------------------------------------- chat, matched

# Themed in Match mode. NOT here, and never themed: chat.error, and the staff
# names -- in chat a player's whole line, name included, takes the channel's
# colour, so a channel landing on the GM violet would make an ordinary player
# LOOK like a GM. Channels are kept clear of every one of those.
CHAT_CHANNELS = ['chat.say', 'chat.party', 'chat.clan', 'chat.whisper', 'chat.trade',
                 'chat.shout', 'chat.group', 'chat.system', 'chat.notice', 'chat.social',
                 'chat.quest', 'chat.quest-reward', 'chat.group-leader']
# Limits set against the STOCK game's own chat colours, measured: its closest
# two channels are 13 apart (party / quest), its darkest is 53.7 (group leader),
# and -- the reason protection matters -- GROUP chat sits just 8.4 from the DEV
# staff colour (#9caff3 against #91acff): in stock, a player talking in group
# has a name all but indistinguishable from a developer's. Every limit here is
# stricter than stock; the staff gap nearly three times over.
CHANNEL_GAP = 16           # between any two channels   (stock's closest: 13)
PROTECTED_GAP = 24         # from error red and staff   (stock's closest: 8.4)
READABLE = 55              # Lab lightness              (stock's darkest: 53.7)
GOLDEN = 0.3819660112501051

# Lightness tiers, most preferred first. The first version held every channel at
# ONE lightness, so channels could differ only by hue -- and one ring of the
# colour wheel has no room for 13 channels and 6 protected colours with safe gaps
# between them all. Across 400 random themes it put two channels on the SAME
# colour, one within 5.5 of a protected colour, and one too dark to read. Tiers
# give the search a second dimension.
TIERS = (0.72, 0.80, 0.64, 0.86, 0.58)


def _pick(want_hue, sat, taken, protected, tiers=TIERS, gap=CHANNEL_GAP):
    """The first colour, searching outward from want_hue through the tiers, that
    is readable and clear of everything already taken or protected."""
    for step in range(0, 51):
        for sign in ((1,) if step == 0 else (1, -1)):
            h = (want_hue + sign * step * 0.01) % 1.0
            for light in tiers:
                for s in (sat, sat * 0.8, min(1.0, sat * 1.15)):
                    c = rgb(h, light, s)
                    lab = _lab(c)
                    if lab[0] < READABLE:
                        continue
                    if all(_dist(lab, t) >= gap for t in taken) and \
                            all(_dist(lab, p) >= PROTECTED_GAP for p in protected):
                        return c, lab
    return None, None


def _dist(a, b):
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2) ** 0.5


def chat_palette(main, accent, meaning):
    """A colour per channel that suits the theme and can never be mistaken.

    Say is the commonest line: near-white, tinted by the accent. The rest step
    round the wheel from the accent's hue by the golden angle -- the most even
    spread for any number of colours -- and each takes the nearest colour that
    is readable on a dark chat box and clear of every other channel, of error
    red and of every staff colour. Group leader looks for its own shade near
    group's hue, as in stock. If a channel truly cannot be placed, this RAISES
    rather than quietly accepting a colour that breaks the rules."""
    protected = [_lab(tuple(int(v[i:i + 2], 16) for i in (1, 3, 5)))
                 for k, v in meaning.items() if k == 'chat.error' or k.startswith('staff.')]
    ah, _al, asat = hls(accent)
    sat = max(0.45, min(0.80, asat))
    say = mix((255, 255, 255), accent, 0.12)
    out, taken = {'chat.say': say}, [_lab(say)]
    hue = ah
    for name in CHAT_CHANNELS:
        if name in ('chat.say', 'chat.group-leader'):
            continue
        c, lab = _pick(hue, sat, taken, protected)
        if c is None:
            raise ValueError('no clear colour for %s' % name)
        out[name] = c
        taken.append(lab)
        hue = (hue + GOLDEN) % 1.0
    c, lab = _pick(hls(out['chat.group'])[0], sat, taken, protected,
                   tiers=(0.58, 0.64, 0.72, 0.80, 0.86))
    if c is None:
        raise ValueError('no clear colour for chat.group-leader')
    out['chat.group-leader'] = c
    return out


def bar_target(kind, main, accent, mode):
    if mode == 'match':
        if kind == 'hp':
            return main
        if kind == 'mp':
            return accent
        if kind == 'exp':
            return SILVER
    return CLASSIC[kind]


def gauge_kind(name):
    """What a HUD bar sprite MEANS, from its name -- None for the empty tracks."""
    n = name.lower()
    if '-bg' in n or n.startswith('gauge-bg') or n.startswith('glowgauge-bg'):
        return None
    for word, kind in (('red', 'hp'), ('blue', 'mp'), ('yellow', 'exp'),
                       ('green', 'green'), ('pink', 'pink'), ('purple', 'purple')):
        if word in n:
            return kind
    return None


# ---------------------------------------------------------------- textures

class Sheet:
    """An uncompressed 32-bit texture, read and written in its own byte order."""

    def __init__(self, path):
        import struct
        self.path = path
        self.data = bytearray(open(path, 'rb').read())
        self.h, self.w = struct.unpack_from('<2I', self.data, 12)
        if struct.unpack_from('<I', self.data, 80)[0] & 4:
            raise ValueError('%s is compressed' % path)
        self.bgra = struct.unpack_from('<I', self.data, 92)[0] == 0x00ff0000

    def get(self, x, y):
        i = 128 + (y * self.w + x) * 4
        d = self.data
        if self.bgra:
            return d[i + 2], d[i + 1], d[i], d[i + 3]
        return d[i], d[i + 1], d[i + 2], d[i + 3]

    def put(self, x, y, c):
        i = 128 + (y * self.w + x) * 4
        r, g, b = (max(0, min(255, int(round(v * 255)))) for v in c)
        if self.bgra:
            self.data[i], self.data[i + 1], self.data[i + 2] = b, g, r
        else:
            self.data[i], self.data[i + 1], self.data[i + 2] = r, g, b

    def save(self):
        open(self.path, 'wb').write(bytes(self.data))


def blend(sheet, points, main, accent):
    """Per element: this element's own darker parts main, brightest accent."""
    vals = sorted(sheet.get(x, y)[0] / 255.0 for x, y in points if sheet.get(x, y)[3] > 40)
    if not vals:
        vals = [sheet.get(x, y)[0] / 255.0 for x, y in points]
    lo = vals[int(0.10 * (len(vals) - 1))]
    hi = vals[int(0.97 * (len(vals) - 1))]
    span = hi - lo
    for x, y in points:
        v = sheet.get(x, y)[0] / 255.0
        k = smooth(0.55, 0.92, (v - lo) / span) if span > 0.02 else smooth(0.45, 0.78, v)
        m = colourize(v, main)
        a = colourize(v, accent)
        sheet.put(x, y, tuple(m[i] * (1 - k) + a[i] * k for i in range(3)))


def fill(sheet, points, target):
    for x, y in points:
        sheet.put(x, y, colourize(sheet.get(x, y)[0] / 255.0, target))


def islands(sheet, taken):
    """Every separate shape of visible pixels no stylesheet names."""
    seen = set(taken)
    out = []
    for y in range(sheet.h):
        for x in range(sheet.w):
            if (x, y) in seen or sheet.get(x, y)[3] <= 8:
                continue
            stack, shape = [(x, y)], []
            seen.add((x, y))
            while stack:
                cx, cy = stack.pop()
                shape.append((cx, cy))
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < sheet.w and 0 <= ny < sheet.h and (nx, ny) not in seen \
                            and sheet.get(nx, ny)[3] > 8:
                        seen.add((nx, ny))
                        stack.append((nx, ny))
            out.append(shape)
    return out


def rects_for(rel, sheets, meta):
    base = os.path.basename(rel).lower()
    out = []
    for s in sheets:
        if s['atlas'].lower() == base:
            out += list(s['sprites'].items())
    if base == 'gauge.dds':
        out += [(r[0], tuple(r[1:])) for r in meta['gauge']['rects']]
    return out


# ---------------------------------------------------------------- the steps

def theme_art(out, meta, main, accent, mode):
    # Sprite rectangles come from the OFFICIAL stylesheets kept in base/meta/
    # sheets -- never shipped, because an unchanged copy in the game would
    # override the next patch's version -- plus any the theme itself carries.
    sheets = core.read_sheets(meta['sheets_dir']) + core.read_sheets(out)
    for rel in CHROME_SHEETS:
        path = os.path.join(out, rel)
        if not os.path.exists(path):
            continue
        sheet = Sheet(path)
        done = set()
        for name, (x0, y0, rw, rh) in rects_for(rel, sheets, meta):
            pts = [(x, y) for y in range(y0, min(sheet.h, y0 + rh))
                   for x in range(x0, min(sheet.w, x0 + rw)) if (x, y) not in done]
            if not pts:
                continue
            kind = CHAR_SHEET.get(name) if rel.endswith('glassui_02.dds') else \
                gauge_kind(name) if rel.endswith('gauge.dds') else None
            if kind:
                fill(sheet, pts, bar_target(kind, main, accent, mode))
            else:
                blend(sheet, pts, main, accent)
            done.update(pts)
        for shape in islands(sheet, done):
            blend(sheet, shape, main, accent)
        sheet.save()
        yield os.path.basename(rel)


def theme_colours(out, meta, main, accent):
    mapping = {}
    for role, hexv in meta['roles']['chrome'].items():
        c = role_colour(role, main, accent)
        if c is not None:
            mapping[hexv.lower()] = c
    changed, _files = core.apply_colours(out, mapping)
    return changed


def theme_chat(out, meta, main, accent):
    """Match mode only: every chat channel to its themed colour, by value."""
    meaning = meta['roles']['meaning']
    mapping = {meaning[k].lower(): v for k, v in chat_palette(main, accent, meaning).items()}
    changed, _files = core.apply_colours(out, mapping)
    return changed


def theme_cursors(out, accent):
    n = 0
    for c in core.cursors(out):
        cur = core.read_cursor(c['path'])
        data, s, cnt = cur['data'], cur['start'], cur['count']
        for i in range(s, s + cnt * 4, 4):
            v = data[i + 2] / 255.0
            r, g, b = (max(0, min(255, int(round(x * 255)))) for x in colourize(v, accent))
            data[i], data[i + 1], data[i + 2] = b, g, r
        open(c['path'], 'wb').write(bytes(data))
        n += 1
    return n


def theme_state_icons(out, meta, main, accent):
    spec = meta['roles'].get('stateicon')
    if not spec:
        return 0
    pitch, size, cols = spec['grid']['pitch'], spec['grid']['cell'], spec['grid']['columns']
    done = 0
    for rel in spec['files']:
        path = os.path.join(out, rel)
        if not os.path.exists(path):
            continue
        sheet = Sheet(path)
        for cell in spec['cells']:
            r, c = divmod(cell, cols)
            pts = [(x, y) for y in range(r * pitch, r * pitch + size)
                   for x in range(c * pitch, c * pitch + size)
                   if sheet.get(x, y)[3] and len(set(sheet.get(x, y)[:3])) == 1]
            if pts:
                blend(sheet, pts, main, accent)
        sheet.save()
        done += 1
    return done


def load_meta(base_dir):
    meta_dir = os.path.join(base_dir, 'meta')
    return {'roles': json.load(open(os.path.join(meta_dir, 'base_roles.json'))),
            'gauge': json.load(open(os.path.join(meta_dir, 'gauge_rects.json'))),
            'sheets_dir': os.path.join(meta_dir, 'sheets')}


def build(base_dir, out_dir, main, accent, mode='classic', progress=None, chat='classic'):
    """Theme a COPY of base/game into out_dir. Returns out_dir.

    progress(step, total, label) is called as it goes, for the window."""
    game = os.path.join(base_dir, 'game')
    a, b = os.path.abspath(out_dir), os.path.abspath(base_dir)
    if a == b or a.startswith(b + os.sep):
        raise ValueError('the output must not be inside the base')
    meta = load_meta(base_dir)
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    shutil.copytree(game, out_dir)
    steps = len(CHROME_SHEETS) + 3
    say = progress or (lambda *_: None)
    n = 0
    for label in theme_art(out_dir, meta, main, accent, mode):
        n += 1
        say(n, steps, 'artwork: ' + label)
    theme_colours(out_dir, meta, main, accent)
    if chat == 'match':
        theme_chat(out_dir, meta, main, accent)
    say(n + 1, steps, 'colours')
    theme_cursors(out_dir, accent)
    say(n + 2, steps, 'cursors')
    theme_state_icons(out_dir, meta, main, accent)
    say(n + 3, steps, 'state icons')
    return out_dir
