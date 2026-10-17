"""theme_core.py -- recolour a ROSE pack, one interface element at a time.

Standard library only, like everything else here.

WHAT AN ELEMENT IS
    A stylesheet declares an atlas and the rectangles inside it:

        @spritesheet theme {
            src: /data/ui/themes/rose/imgs/gauge.dds;
            gauge-bg-sm-md:   1px  1px  99px 11px;
            gauge-red-sm-md:  1px 30px  99px 11px;
        }

    So "the health bar" is not a file -- it is a named rectangle inside one.
    That is what makes tinting one element without touching its neighbour
    possible at all.

    Families are derived from the sheets in the PACK, not from a saved list.
    A saved list of particle names once covered 62 per cent of what was really
    there and sent a search off for days; the same mistake is available here.

WHAT IS PROTECTED, AND WHY
    Health red, fuel mint, party cyan, error red. Every pack keeps these,
    because they carry meaning that outranks a theme: a red bar is low health
    in any palette, and sixteen chat channels are only tellable apart while
    they differ in hue. Recolouring them photographs well and plays badly.

    The sprite names say which is which -- gauge-red-sm-md, gauge-blue-sm-sm --
    so this is read off the names rather than kept in a list that would go
    stale the moment a pack added something.

WHAT IT DOES NOT TOUCH
    Meshes, motions, particle files, effect wrappers. Colour in Kye's packs
    lives in the textures; his particle files carry no colour events at all.
"""

import bisect
import os
import re
import struct

# name: Xpx Ypx Wpx Hpx
SPRITE = re.compile(r'([A-Za-z0-9_\-]+)\s*:\s*(\d+)px\s+(\d+)px\s+(\d+)px\s+(\d+)px')
SOURCE = re.compile(r'src\s*:\s*([^;]+);', re.I)
SHEET = re.compile(r'@spritesheet\s+[A-Za-z0-9_\-]*\s*\{', re.I)

# Colour words that mean something in this game, wherever they turn up in a
# sprite name. A theme that recolours these has broken the interface.
MEANINGFUL = ('red', 'green', 'blue', 'yellow', 'cyan', 'mint', 'purple',
              'pink', 'orange', 'white', 'black', 'grey', 'gray')


def read_sheets(folder):
    """Every @spritesheet in every stylesheet under this folder.

    Returns a list of {'src', 'atlas', 'sprites': {name: (x, y, w, h)}}.
    """
    sheets = []
    for root, _dirs, names in os.walk(folder):
        for name in names:
            if not name.lower().endswith(('.css', '.rcss')):
                continue
            path = os.path.join(root, name)
            try:
                text = open(path, encoding='utf-8', errors='replace').read()
            except OSError:
                continue
            for match in SHEET.finditer(text):
                block = _block_at(text, match.end() - 1)
                if not block:
                    continue
                src = SOURCE.search(block)
                if not src:
                    continue
                source = src.group(1).strip()
                sprites = {}
                for sprite in SPRITE.finditer(block):
                    sprites[sprite.group(1)] = tuple(
                        int(sprite.group(i)) for i in (2, 3, 4, 5))
                if sprites:
                    sheets.append({'src': source,
                                   'atlas': os.path.basename(
                                       source.replace('\\', '/')),
                                   'stylesheet': path,
                                   'sprites': sprites})
    return sheets


def _block_at(text, brace):
    """The text between this opening brace and its match."""
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == '{':
            depth += 1
        elif text[index] == '}':
            depth -= 1
            if depth == 0:
                return text[brace:index + 1]
    return None


def family_of(name):
    """The element a sprite belongs to.

    gauge-bg-sm-md and gauge-bg-sm-sm are the same element at two sizes, so
    the trailing size words are dropped. What is left is what a person would
    point at and call a thing.
    """
    parts = name.split('-')
    while len(parts) > 1 and parts[-1].lower() in (
            'sm', 'md', 'lg', 'xs', 'xl', 'markers') or (
            len(parts) > 1 and parts[-1].isdigit()):
        parts.pop()
    return '-'.join(parts) or name


def is_meaningful(name):
    """Does this sprite's name say it carries a meaning a theme must not move?"""
    words = set(part.lower() for part in re.split(r'[-_]', name))
    return bool(words & set(MEANINGFUL))


def elements(sheets):
    """Group every sprite into named elements, ready to be listed.

    Returns [{'name', 'atlas', 'sprites': [(name, rect)...], 'protected'}].
    """
    groups = {}
    for sheet in sheets:
        for name, rect in sheet['sprites'].items():
            key = (sheet['atlas'], family_of(name))
            entry = groups.setdefault(key, {'name': family_of(name),
                                            'atlas': sheet['atlas'],
                                            'sprites': [],
                                            'protected': False})
            # The same sprite can be declared in more than one stylesheet.
            # Applying it twice would double every adjustment.
            if (name, rect) not in entry['sprites']:
                entry['sprites'].append((name, rect))
            if is_meaningful(name):
                entry['protected'] = True
    for entry in groups.values():
        entry['pixels'] = sum(r[2] * r[3] for _n, r in entry['sprites'])
        entry['biggest'] = max((r[2], r[3]) for _n, r in entry['sprites'])
    return [groups[k] for k in sorted(groups)]


# ------------------------------------------------ colours written as text
#
# Half a theme is not in the artwork at all. Chat channels, quest names, gauge
# tints, tooltips and window backgrounds are colour VALUES in the stylesheets
# and pages -- and a pack that recolours only the textures comes out half new
# and half stock, which is worse than either.
#
# Three notations are in use and all of them matter:
#
#     #E7AD4B          hex, 3 4 6 or 8 digits
#     rgb(155, 48, 217)
#     rgba(14,7,22,220)
#
# In the Regal theme there are more rgb() than hex. Each is rewritten in its
# OWN notation so an rgba keeps its alpha.

COLOUR_TEXT = re.compile(
    r'#[0-9a-fA-F]{8}\b|#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{4}\b|#[0-9a-fA-F]{3}\b'
    r'|rgba?\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*(?:,\s*[\d.]+\s*)?\)')
TEXT_FILES = ('.css', '.rcss', '.html', '.htm', '.rml')


# The handful of named colours a stylesheet actually uses. Not the full CSS
# list -- these are the ones that turn up, and an unknown name returning None
# is the right answer anyway.
NAMED = {
    'black': (0, 0, 0), 'white': (255, 255, 255), 'red': (255, 0, 0),
    'green': (0, 128, 0), 'blue': (0, 0, 255), 'yellow': (255, 255, 0),
    'cyan': (0, 255, 255), 'magenta': (255, 0, 255), 'grey': (128, 128, 128),
    'gray': (128, 128, 128), 'silver': (192, 192, 192), 'orange': (255, 165, 0),
    'purple': (128, 0, 128), 'transparent': None,
}


def parse_colour(text):
    """Any of the notations to (r, g, b), or None.

    NAMED COLOURS USED TO CRASH THIS. outline(1dp black) has no bracket to
    find, so looking for one raised -- and because the exception came out of a
    sweep running over every row, the whole operation died before changing
    anything, without a word on screen. It looked like the button did nothing.
    """
    if not text:
        return None
    text = text.strip()
    low = text.lower()
    if low in NAMED:
        return NAMED[low]
    if not text.startswith('#') and '(' not in text:
        return None
    if text.startswith('#'):
        digits = text[1:]
        if len(digits) in (3, 4):
            return tuple(int(c * 2, 16) for c in digits[:3])
        if len(digits) in (6, 8):
            return tuple(int(digits[i:i + 2], 16) for i in (0, 2, 4))
        return None
    try:
        inside = text[text.index('(') + 1:text.rindex(')')]
    except ValueError:
        return None
    parts = [p.strip() for p in inside.split(',')]
    try:
        return tuple(max(0, min(255, int(float(p)))) for p in parts[:3])
    except (ValueError, IndexError):
        return None


def write_colour(original, rgb):
    """The new colour in the same notation the original used.

    A named colour becomes a hex, because there is rarely a name for where it
    has moved to.
    """
    r, g, b = (max(0, min(255, int(v))) for v in rgb)
    original = original.strip()
    if original.lower() in NAMED or ('(' not in original
                                     and not original.startswith('#')):
        return '#%02x%02x%02x' % (r, g, b)
    if original.startswith('#'):
        digits = original[1:]
        if len(digits) in (3, 4):
            # keep it short only if it survives being short
            short = '#%x%x%x' % (r >> 4, g >> 4, b >> 4)
            if parse_colour(short) == (r, g, b):
                return short + (digits[3] if len(digits) == 4 else '')
        if len(digits) == 8:
            return '#%02x%02x%02x%s' % (r, g, b, digits[6:])
        return '#%02x%02x%02x' % (r, g, b)
    inside = original[original.index('(') + 1:original.rindex(')')]
    parts = [p.strip() for p in inside.split(',')]
    if len(parts) >= 4:
        return 'rgba(%d, %d, %d, %s)' % (r, g, b, parts[3])
    return 'rgb(%d, %d, %d)' % (r, g, b)


EFFECT_LINE = re.compile(r'font-effect\s*:\s*([^;]+);', re.I)


# ------------------------------------------------ comments are not colours
#
# A colour written inside a comment is text: the game never reads it. The first
# version listed them anyway, and on the Spooky pack that was 22 of 208 uses --
# ten colours that exist ONLY in comments, left there by earlier sessions as
# notes ("sliderbar #00b033 -> ..."). Changing them showed "no change", and they
# were chased as unknowns. Both CSS comments and HTML comments are skipped; an
# unterminated one runs to the end of the file, as the formats themselves say.

COMMENT = re.compile(r'/\*.*?(?:\*/|\Z)|<!--.*?(?:-->|\Z)', re.S)


def comment_spans(text):
    """Where the comments are in this text, as sorted (start, end) pairs."""
    return [m.span() for m in COMMENT.finditer(text)]


def in_comment(spans, position):
    """Is this character position inside one of those comments?"""
    index = bisect.bisect_right(spans, (position, float('inf'))) - 1
    return index >= 0 and spans[index][0] <= position < spans[index][1]


def _line_starts(text):
    starts = [0]
    for i, ch in enumerate(text):
        if ch == '\n':
            starts.append(i + 1)
    return starts


# Files that are REWRITTEN are read and written byte for byte. errors='replace'
# turned any byte that is not UTF-8 -- a curly quote, an accented letter -- into
# U+FFFD and wrote that back, permanently; and text mode let Windows rewrite the
# line endings. surrogateescape carries undecodable bytes through untouched, and
# newline='' leaves every line ending exactly as it was.
_EXACT = dict(encoding='utf-8', errors='surrogateescape', newline='')
def _split_effects(text):
    """Split a font-effect value into its top-level parts.

    A regex cannot do this: outline(1dp rgba(14,7,22,220)) has brackets inside
    brackets, and any pattern that stops at the first ')' eats the rgba's own
    one and quietly corrupts the colour. So the brackets are counted.
    """
    parts = []
    depth = 0
    token = ''
    for char in text:
        if char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
        if char == ',' and depth == 0:
            if token.strip():
                parts.append(token.strip())
            token = ''
        else:
            token += char
    if token.strip():
        parts.append(token.strip())
    return parts


def parse_effect(text):
    """Break a font-effect value into its parts.

        glow(1dp 2dp #E7AD4B), outline(1dp rgba(14,7,22,220))

    becomes [('glow', [1, 2], '#E7AD4B'), ('outline', [1], 'rgba(14,7,22,220)')].

    The numbers are the bloom -- how far it spreads and how soft it is -- and
    they are the whole reason this exists. A theme can have exactly the right
    colours and still look flat because the glow is one device-pixel wide.
    """
    parts = []
    for piece in _split_effects(text):
        if '(' not in piece:
            continue
        kind = piece[:piece.index('(')].strip().lower()
        inside = piece[piece.index('(') + 1:piece.rindex(')')]
        numbers = []
        colour = None
        depth = 0
        token = ''
        tokens = []
        for char in inside:
            if char == '(':
                depth += 1
            elif char == ')':
                depth -= 1
            if char == ' ' and depth == 0:
                if token:
                    tokens.append(token)
                token = ''
            else:
                token += char
        if token:
            tokens.append(token)
        for item in tokens:
            low = item.lower()
            if low.endswith(('dp', 'px')):
                try:
                    numbers.append(float(item[:-2]))
                    continue
                except ValueError:
                    pass
            if item.startswith('#') or low.startswith('rgb') or low.isalpha():
                colour = item
        parts.append((kind, numbers, colour))
    return parts


def build_effect(parts, unit='dp'):
    """Put the parts back together the way the stylesheet writes them."""
    out = []
    for kind, numbers, colour in parts:
        bits = ['%g%s' % (n, unit) for n in numbers]
        if colour:
            bits.append(colour)
        out.append('%s(%s)' % (kind, ' '.join(bits)))
    return ', '.join(out)


def read_effects(folder):
    """Every font-effect in the pack, one entry per distinct declaration."""
    found = {}
    for root, _dirs, names in os.walk(folder):
        for name in names:
            if not name.lower().endswith(TEXT_FILES):
                continue
            path = os.path.join(root, name)
            try:
                text = open(path, encoding='utf-8', errors='replace').read()
            except OSError:
                continue
            spans = comment_spans(text)
            starts = _line_starts(text)
            lines = text.split('\n')
            for match in EFFECT_LINE.finditer(text):
                if in_comment(spans, match.start()):
                    continue
                value = match.group(1).strip()
                if value.lower() == 'none':
                    continue
                parts = parse_effect(value)
                if not parts:
                    continue
                number = bisect.bisect_right(starts, match.start())
                entry = found.setdefault(value, {'value': value,
                                                 'parts': parts,
                                                 'uses': []})
                entry['uses'].append((path, number, lines[number - 1].strip()[:90]))
    return sorted(found.values(), key=lambda e: -len(e['uses']))


def apply_effects(folder, mapping):
    """Rewrite font-effect declarations. mapping is {old value: new value}."""
    changed = files = 0
    for root, _dirs, names in os.walk(folder):
        for name in names:
            if not name.lower().endswith(TEXT_FILES):
                continue
            path = os.path.join(root, name)
            try:
                text = open(path, **_EXACT).read()
            except OSError:
                continue
            spans = comment_spans(text)
            hits = [0]

            def swap(match):
                if in_comment(spans, match.start()):
                    return match.group()
                value = match.group(1).strip()
                if value not in mapping:
                    return match.group()
                hits[0] += 1
                return match.group().replace(value, mapping[value])

            new = EFFECT_LINE.sub(swap, text)
            if hits[0]:
                with open(path, 'w', **_EXACT) as handle:
                    handle.write(new)
                changed += hits[0]
                files += 1
    return changed, files


def read_colours(folder):
    """Every colour written as text, and everywhere it is used.

    Returns [{'key', 'rgb', 'uses': [(path, line, context, literal)]}]
    keyed on the colour itself, because the same value in four files is one
    decision, not four.
    """
    found = {}
    for root, _dirs, names in os.walk(folder):
        for name in names:
            if not name.lower().endswith(TEXT_FILES):
                continue
            path = os.path.join(root, name)
            try:
                text = open(path, encoding='utf-8', errors='replace').read()
            except OSError:
                continue
            spans = comment_spans(text)
            starts = _line_starts(text)
            lines = text.split('\n')
            for match in COLOUR_TEXT.finditer(text):
                if in_comment(spans, match.start()):
                    continue
                literal = match.group()
                rgb = parse_colour(literal)
                if rgb is None:
                    continue
                number = bisect.bisect_right(starts, match.start())
                key = '#%02x%02x%02x' % rgb
                entry = found.setdefault(key, {'key': key, 'rgb': rgb,
                                               'uses': []})
                entry['uses'].append((path, number, lines[number - 1].strip()[:90],
                                      literal))
    return sorted(found.values(), key=lambda e: -len(e['uses']))


def apply_colours(folder, mapping):
    """Rewrite text colours. mapping is {key: (r, g, b)}.

    Every occurrence of a colour is rewritten wherever it appears, in its own
    notation. Files are read and written whole so nothing else moves.
    """
    changed = files = 0
    for root, _dirs, names in os.walk(folder):
        for name in names:
            if not name.lower().endswith(TEXT_FILES):
                continue
            path = os.path.join(root, name)
            try:
                text = open(path, **_EXACT).read()
            except OSError:
                continue
            spans = comment_spans(text)
            hits = [0]

            def swap(match):
                if in_comment(spans, match.start()):
                    return match.group()
                rgb = parse_colour(match.group())
                if rgb is None:
                    return match.group()
                key = '#%02x%02x%02x' % rgb
                if key not in mapping:
                    return match.group()
                hits[0] += 1
                return write_colour(match.group(), mapping[key])

            new = COLOUR_TEXT.sub(swap, text)
            if hits[0]:
                with open(path, 'w', **_EXACT) as handle:
                    handle.write(new)
                changed += hits[0]
                files += 1
    return changed, files


def shift_colour(rgb, hue, saturation=1.0, brightness=1.0, keep_grey=False):
    """Move one colour to a new hue, keeping how light and how strong it was."""
    r, g, b = rgb
    h, sat, val = _rgb_to_hsv(r, g, b)
    if sat < 0.02 and not keep_grey:
        return rgb                         # a grey stays a grey unless asked
    if sat < 0.02:
        sat = 0.45
    return _hue_to_rgb(hue, min(1.0, sat * saturation),
                       min(1.0, val * brightness))


def leftovers(sheets, atlases):
    """One element per atlas for everything NO sprite declares.

    A stylesheet only names the rectangles the HTML layer uses. The same atlas
    usually holds a great deal more -- on glassui_00 the declared sprites cover
    about a third of it, and the rest is the older windows, which are drawn
    without any stylesheet at all.

    Recolouring only the declared sprites leaves a pack a third themed. This is
    the other two thirds.
    """
    by_atlas = {}
    for sheet in sheets:
        by_atlas.setdefault(sheet['atlas'].lower(), []).extend(
            sheet['sprites'].values())
    out = []
    for key, rects in sorted(by_atlas.items()):
        path = atlases.get(key)
        if not path:
            continue
        head = read_dds(path)
        if not head:
            continue
        covered = sum(w * h for _x, _y, w, h in set(rects))
        total = head['width'] * head['height']
        out.append({'name': '(everything else on this sheet)',
                    'atlas': os.path.basename(path),
                    'path': path,
                    'sprites': [('rest', (0, 0, head['width'], head['height']))],
                    'skip_rects': list(set(rects)),
                    'biggest': (head['width'], head['height']),
                    'pixels': max(0, total - covered),
                    'leftover': True,
                    'declared_fraction': covered / float(total) if total else 0,
                    'protected': False})
    return out


def read_cursor(path):
    """A .CUR as pixels, or None.

    A cursor is an ICO-family container: a short directory, then a DIB. The
    pixel rows are BOTTOM-UP and BGRA, and there is an AND mask after them that
    must be left exactly alone -- it is what makes the transparent parts
    transparent, and a cursor with a mangled mask draws as a black square.
    """
    try:
        data = bytearray(open(path, 'rb').read())
    except OSError:
        return None
    if len(data) < 22 or struct.unpack_from('<HHH', data, 0)[:2] != (0, 2):
        return None
    width = data[6] or 256
    height = data[7] or 256
    size, offset = struct.unpack_from('<II', data, 14)
    if offset + 40 > len(data):
        return None
    header = struct.unpack_from('<I', data, offset)[0]
    bits = struct.unpack_from('<H', data, offset + 14)[0]
    if header != 40 or bits != 32:
        return None                       # only the plain 32-bit kind
    start = offset + header
    count = width * height
    if start + count * 4 > len(data):
        return None
    return {'data': data, 'start': start, 'width': width, 'height': height,
            'count': count, 'path': path}


def adjust_cursor(cursor, hue=None, saturation=1.0, brightness=1.0,
                  floor=0.12, grey_strength=0.55):
    """Recolour a cursor's pixels, leaving its transparency mask alone."""
    data = cursor['data']
    start = cursor['start']
    moved = 0
    for index in range(cursor['count']):
        at = start + index * 4
        b, g, r, a = data[at], data[at + 1], data[at + 2], data[at + 3]
        high, low = max(r, g, b), min(r, g, b)
        if high == 0:
            continue
        sat = (high - low) / float(high)
        if sat <= floor and not (floor <= 0 and high > 8):
            continue
        if sat < 0.02:
            sat = grey_strength
        use = hue if hue is not None else _rgb_to_hsv(r, g, b)[0]
        nr, ng, nb = _hue_to_rgb(use, min(1.0, sat * saturation),
                                 min(1.0, (high / 255.0) * brightness))
        data[at], data[at + 1], data[at + 2] = nb, ng, nr
        moved += 1
    return moved


def write_cursor(cursor, path):
    with open(path, 'wb') as handle:
        handle.write(bytes(cursor['data']))


def cursors(folder):
    """Every cursor in the pack, as elements the list can show."""
    out = []
    for root, _dirs, names in os.walk(folder):
        for name in names:
            if not name.lower().endswith('.cur'):
                continue
            path = os.path.join(root, name)
            got = read_cursor(path)
            if not got:
                continue
            out.append({'name': name, 'atlas': 'cursors', 'path': path,
                        'relative': os.path.relpath(path, folder),
                        'sprites': [(name, (0, 0, got['width'], got['height']))],
                        'biggest': (got['width'], got['height']),
                        'pixels': got['count'], 'is_cursor': True,
                        'whole_file': True, 'protected': False})
    return sorted(out, key=lambda e: e['name'].lower())


def loose_textures(folder, sheets):
    """Textures in the pack that NO stylesheet mentions.

    Not everything in ROSE's interface goes through the HTML layer. The older
    windows -- character, skill, inventory, item mall -- are drawn from
    textures with no stylesheet at all, and so are every effect texture and the
    buff icon sheet.

    Without this they are invisible to the tool, and a pack comes out with half
    its windows themed and half stock. There are no sprite rectangles for them,
    so the whole file is treated as one thing.
    """
    named = set()
    for sheet in sheets:
        named.add(sheet['atlas'].lower())
    loose = []
    for root, _dirs, names in os.walk(folder):
        for name in names:
            if not name.lower().endswith('.dds'):
                continue
            if name.lower() in named:
                continue
            path = os.path.join(root, name)
            head = read_dds(path)
            if not head:
                continue
            loose.append({'name': name,
                          'atlas': name,
                          'path': path,
                          'relative': os.path.relpath(path, folder),
                          'width': head['width'],
                          'height': head['height'],
                          'sprites': [(name, (0, 0, head['width'], head['height']))],
                          'biggest': (head['width'], head['height']),
                          'pixels': head['width'] * head['height'],
                          'whole_file': True,
                          'protected': False})
    return sorted(loose, key=lambda e: e['relative'].lower())


# ------------------------------------------------------------------ textures

def read_dds(path):
    """Pixels as a bytearray of RGBA, plus the header to write back."""
    data = open(path, 'rb').read()
    if data[:4] != b'DDS ':
        return None
    height, width = struct.unpack_from('<II', data, 12)
    flags = struct.unpack_from('<I', data, 80)[0]
    if flags & 0x4:
        return None                       # compressed; nothing here decodes it
    rmask = struct.unpack_from('<I', data, 92)[0]
    pixels = bytearray(data[128:128 + width * height * 4])
    if len(pixels) < width * height * 4:
        return None
    return {'width': width, 'height': height, 'header': data[:128],
            'pixels': pixels, 'bgra': rmask == 0x00ff0000}


def write_dds(path, image):
    folder = os.path.dirname(os.path.abspath(path))
    if folder and not os.path.isdir(folder):
        os.makedirs(folder)
    with open(path, 'wb') as handle:
        handle.write(image['header'] + bytes(image['pixels']))


def _hue_to_rgb(hue, sat, val):
    """HSV to RGB, written out rather than called, because this runs per pixel."""
    if sat <= 0:
        v = int(val * 255)
        return v, v, v
    sector = int(hue * 6.0) % 6
    offset = hue * 6.0 - int(hue * 6.0)
    p = val * (1.0 - sat)
    q = val * (1.0 - sat * offset)
    t = val * (1.0 - sat * (1.0 - offset))
    r, g, b = ((val, t, p), (q, val, p), (p, val, t),
               (p, q, val), (t, p, val), (val, p, q))[sector]
    return int(r * 255), int(g * 255), int(b * 255)


def retint_rect(image, rect, hue, saturation=1.0, brightness=1.0, floor=0.12):
    """Move one rectangle of a texture to a new hue, keeping its shading.

    Only pixels that HAVE a colour are moved. Greys, whites and blacks are left
    alone, so highlights stay white and shadows stay dark -- which is what keeps
    a shape looking three-dimensional afterwards.

    This is a rotation of the artist's own pixels, not a redraw. Every attempt
    at redrawing an effect on this project went wrong at least once, because a
    redraw is a new thing wearing the old name.
    """
    x0, y0, w, h = rect
    width = image['width']
    pixels = image['pixels']
    bgra = image['bgra']
    moved = 0
    for y in range(y0, min(y0 + h, image['height'])):
        row = y * width
        for x in range(x0, min(x0 + w, width)):
            at = (row + x) * 4
            if bgra:
                b, g, r = pixels[at], pixels[at + 1], pixels[at + 2]
            else:
                r, g, b = pixels[at], pixels[at + 1], pixels[at + 2]
            high = max(r, g, b)
            low = min(r, g, b)
            if high == 0:
                continue
            sat = (high - low) / float(high)
            if sat <= floor:
                continue                  # a grey, a highlight or a shadow
            value = min(1.0, (high / 255.0) * brightness)
            nr, ng, nb = _hue_to_rgb(hue, min(1.0, sat * saturation), value)
            if bgra:
                pixels[at], pixels[at + 1], pixels[at + 2] = nb, ng, nr
            else:
                pixels[at], pixels[at + 1], pixels[at + 2] = nr, ng, nb
            moved += 1
    return moved


def dominant_hue(image, rects, sample=4):
    """The hue this element is mostly made of, and how much colour it has.

    Returns (hue, strength, coloured pixels). Greys report strength 0 -- an
    element made of grey has no hue to belong to, and pretending otherwise puts
    every plate and frame into one meaningless family.

    Sampled rather than exhaustive. A quarter of the pixels in each direction
    is plenty to find what a sprite is mostly made of, and doing it properly
    across three hundred elements would take minutes.
    """
    buckets = [0] * 36
    strength = 0.0
    counted = 0
    for x0, y0, w, h in rects:
        for y in range(y0, min(y0 + h, image['height']), sample):
            base = y * image['width']
            for x in range(x0, min(x0 + w, image['width']), sample):
                at = (base + x) * 4
                if image['pixels'][at + 3] < 32:
                    continue
                if image['bgra']:
                    b, g, r = (image['pixels'][at], image['pixels'][at + 1],
                               image['pixels'][at + 2])
                else:
                    r, g, b = (image['pixels'][at], image['pixels'][at + 1],
                               image['pixels'][at + 2])
                hue, sat, _val = _rgb_to_hsv(r, g, b)
                if sat < 0.15:
                    continue
                buckets[int(hue * 36) % 36] += 1
                strength += sat
                counted += 1
    if not counted:
        return 0.0, 0.0, 0
    best = max(range(36), key=lambda i: buckets[i])
    return (best + 0.5) / 36.0, strength / counted, counted


def cursor_as_image(cursor):
    """A cursor's pixels in the same shape a texture uses, so the rest of the
    code does not need to know it is a cursor."""
    return {'width': cursor['width'], 'height': cursor['height'],
            'pixels': cursor['data'][cursor['start']:
                                     cursor['start'] + cursor['count'] * 4],
            'bgra': True, 'header': b''}


def hue_families(elements, atlas_image, width=0.06, progress=None):
    """Group elements by the hue they are mostly made of.

    A theme is not three hundred independent decisions. It is two or three
    colours -- Regal is gold and violet -- used over and over. Finding those
    families turns "recolour everything" into "the gold becomes orange and the
    violet becomes green", which is the decision actually being made.

    Elements with no real colour in them are put in their own group rather than
    forced into one, because a grey plate belongs to no palette.
    """
    families = []
    greys = []
    for index, element in enumerate(elements):
        if progress and index % 20 == 0:
            progress(index, len(elements))
        # CURSORS HAVE NO ATLAS. Asking for one by name returned nothing, so
        # all nineteen were dropped before they reached a family and stayed
        # stock while the interface around them moved.
        if element.get('is_cursor'):
            got = read_cursor(element['path'])
            image = cursor_as_image(got) if got else None
        else:
            image = atlas_image(element['atlas'])
        if not image:
            greys.append(element)
            continue
        hue, strength, counted = dominant_hue(image, [r for _n, r in element['sprites']])
        if counted < 8 or strength < 0.12:
            greys.append(element)
            continue
        for family in families:
            gap = abs(family['hue'] - hue)
            gap = min(gap, 1.0 - gap)            # hue wraps around
            if gap <= width:
                family['members'].append(element)
                family['weight'] += counted
                # keep the family centred on where its weight actually is
                family['hue'] += (hue - family['hue']) * (counted / float(family['weight']))
                break
        else:
            families.append({'hue': hue, 'weight': counted,
                             'members': [element]})
    families.sort(key=lambda f: -f['weight'])
    return families, greys


def hue_to_hex(hue, saturation=0.85, value=0.95):
    r, g, b = _hue_to_rgb(hue % 1.0, saturation, value)
    return '#%02x%02x%02x' % (r, g, b)


def coverage(image, rects):
    """A map of which pixels a set of rectangles already covers.

    Built once as a flat bytearray rather than testing every pixel against
    every rectangle -- 512x512 against 145 sprites is 38 million checks, which
    is far too slow in Python. This is one pass over the rectangles and then
    one lookup per pixel.
    """
    mask = bytearray(image['width'] * image['height'])
    for x0, y0, w, h in rects:
        for y in range(max(0, y0), min(image['height'], y0 + h)):
            start = y * image['width']
            lo = max(0, x0)
            hi = min(image['width'], x0 + w)
            if hi > lo:
                mask[start + lo:start + hi] = b'\x01' * (hi - lo)
    return mask


def adjust_rect(image, rect, hue=None, saturation=1.0, brightness=1.0,
                alpha=1.0, glow=0.0, glow_radius=3, floor=0.12,
                grey_strength=0.55, skip=None,
                hue_dark=None, split=0.5, dark_sat=1.0, dark_bright=1.0,
                dark_solid=None, dark_keep=0.25):
    """Every per-element change, applied to one rectangle in one pass.

    TWO COLOURS, SPLIT BY LIGHTNESS. The defining feature of these packs is a
    glowing trim around a dark interior -- and the trim is not a separate
    sprite. It is the BRIGHT PIXELS of the same artwork, with the glass being
    the dark ones. Some of it is inside a named sprite and some only exists in
    the undeclared part of the sheet, which is why hunting for a sprite that
    owns "the border" never worked.

    So: pixels lighter than `split` take `hue`, pixels darker take `hue_dark`.
    One pass, one element, a lit edge and a dark fill. Leave hue_dark unset and
    it behaves as it always did.

    DARK_SOLID IS A DIFFERENT OPERATION, and it is the one that gets a black
    panel. Tinting keeps a pixel's own saturation, so a dark PURPLE tinted
    toward black lands on grey-brown and never on black -- there is still
    purple in it. Solid REPLACES the colour outright.

    `dark_keep` is how much of the original shading survives: 0 is perfectly
    flat, and a little (0.2 or so) keeps the gentle gradient a glass panel
    wants without letting the old colour back in.

    Separate passes over the same pixels would be slower and would compound
    rounding -- two round trips through HSV lose a little each time.

    GLOW IS CLIPPED TO THE RECTANGLE, and that is not a limitation that can be
    lifted. Sprites are packed tight in an atlas, often edge to edge, so a bloom
    that spread outward would bleed into the neighbouring sprite and quietly
    corrupt it. So it blooms INWARD from the shape's own edges: the light
    gathers along the inside. On a frame or a bar that reads well. It cannot
    halo outward the way glow usually does.
    """
    x0, y0, w, h = rect
    width, height = image['width'], image['height']
    pixels = image['pixels']
    bgra = image['bgra']
    x1, y1 = min(x0 + w, width), min(y0 + h, height)
    touched = 0

    # Glow needs to know where the shape IS before anything is changed, so the
    # brightness map is taken first.
    lit = None
    if glow > 0:
        lit = []
        for y in range(y0, y1):
            row = []
            for x in range(x0, x1):
                at = (y * width + x) * 4
                row.append((max(pixels[at], pixels[at + 1], pixels[at + 2])
                            * pixels[at + 3]) // 255)
            lit.append(row)

    for y in range(y0, y1):
        base = y * width
        for x in range(x0, x1):
            if skip is not None and skip[base + x]:
                continue                  # already covered by a named sprite
            at = (base + x) * 4
            if bgra:
                b, g, r = pixels[at], pixels[at + 1], pixels[at + 2]
            else:
                r, g, b = pixels[at], pixels[at + 1], pixels[at + 2]
            a = pixels[at + 3]
            high, low = max(r, g, b), min(r, g, b)

            lightness = high / 255.0
            use_sat, use_bright = saturation, brightness
            target = hue
            is_dark = lightness < split

            # Replace outright, rather than tint. The only way to reach a flat
            # panel: a dark purple TINTED toward black keeps its own saturation
            # and stops at grey-brown, because there is still purple in it.
            if is_dark and dark_solid is not None:
                sr, sg, sb = dark_solid
                if dark_keep > 0:
                    # a touch of the original shading, so a glass panel keeps
                    # its gradient without the old hue coming back with it
                    lift = (lightness / max(split, 0.001)) * dark_keep
                    sr = min(255, int(sr * (1 - dark_keep) + sr * lift * 2))
                    sg = min(255, int(sg * (1 - dark_keep) + sg * lift * 2))
                    sb = min(255, int(sb * (1 - dark_keep) + sb * lift * 2))
                if bgra:
                    pixels[at], pixels[at + 1], pixels[at + 2] = sb, sg, sr
                else:
                    pixels[at], pixels[at + 1], pixels[at + 2] = sr, sg, sb
                if alpha != 1.0:
                    pixels[at + 3] = max(0, min(255, int(a * alpha)))
                touched += 1
                continue

            if hue_dark is not None and is_dark:
                target = hue_dark
                use_sat, use_bright = dark_sat, dark_bright

            if high > 0:
                sat = (high - low) / float(high)
                # floor=0 means TINT GREYS TOO. The default leaves them alone so
                # highlights stay white and shadows stay dark, which is right for
                # recolouring coloured art -- and wrong for interface chrome,
                # which is mostly grey and is the thing you most want to tint.
                if sat > floor or (floor <= 0 and high > 8):
                    if sat < 0.02:
                        sat = grey_strength
                    if target is None:
                        use_hue, _sat, _val = _rgb_to_hsv(r, g, b)
                    else:
                        use_hue = target
                    value = min(1.0, lightness * use_bright)
                    nr, ng, nb = _hue_to_rgb(use_hue,
                                             min(1.0, sat * use_sat), value)
                    touched += 1
                elif use_bright != 1.0:
                    nr = min(255, int(r * use_bright))
                    ng = min(255, int(g * use_bright))
                    nb = min(255, int(b * use_bright))
                else:
                    nr, ng, nb = r, g, b
            else:
                nr, ng, nb = r, g, b

            if glow > 0 and lit is not None:
                near = _neighbourhood(lit, x - x0, y - y0, glow_radius)
                if near:
                    lift = int(near * glow)
                    nr = min(255, nr + lift)
                    ng = min(255, ng + lift)
                    nb = min(255, nb + lift)
                    if a > 0:
                        a = min(255, a + lift // 2)

            if alpha != 1.0:
                a = max(0, min(255, int(a * alpha)))

            if bgra:
                pixels[at], pixels[at + 1], pixels[at + 2] = nb, ng, nr
            else:
                pixels[at], pixels[at + 1], pixels[at + 2] = nr, ng, nb
            pixels[at + 3] = a
    return touched


def _neighbourhood(lit, x, y, radius):
    """Average brightness around a point, for the inward bloom."""
    total = count = 0
    for dy in range(-radius, radius + 1):
        row = y + dy
        if row < 0 or row >= len(lit):
            continue
        line = lit[row]
        for dx in range(-radius, radius + 1):
            col = x + dx
            if 0 <= col < len(line):
                total += line[col]
                count += 1
    if not count:
        return 0
    return (total // count) // 6          # gentle by default


def _rgb_to_hsv(r, g, b):
    """Hue, saturation, value -- in that order, like everything else here."""
    high, low = max(r, g, b), min(r, g, b)
    if high == low:
        return 0.0, 0.0, high / 255.0
    span = high - low
    if high == r:
        hue = ((g - b) / float(span)) % 6
    elif high == g:
        hue = (b - r) / float(span) + 2
    else:
        hue = (r - g) / float(span) + 4
    return (hue / 6.0) % 1.0, span / float(high), high / 255.0


def crop_png(image, rect, zoom=1, background=(26, 26, 32)):
    """A PNG of one sprite, ready for tkinter, with alpha flattened.

    THE POINT OF THIS IS SCALE. Interface sprites are often one to three pixels
    -- a 9-slice box has a 1x1 centre that the game stretches across a whole
    window. Eight such elements are about twenty pixels between them, which
    looks like nothing happened when it is actually correct.

    Seeing the thing at size answers that in a glance.
    """
    import zlib
    x0, y0, w, h = rect
    w = max(1, min(w, image['width'] - x0))
    h = max(1, min(h, image['height'] - y0))
    zoom = max(1, int(zoom))
    rows = bytearray()
    for y in range(y0, y0 + h):
        line = bytearray()
        for x in range(x0, x0 + w):
            at = (y * image['width'] + x) * 4
            if image['bgra']:
                b, g, r = image['pixels'][at], image['pixels'][at+1], image['pixels'][at+2]
            else:
                r, g, b = image['pixels'][at], image['pixels'][at+1], image['pixels'][at+2]
            a = image['pixels'][at + 3] / 255.0
            px = bytes((int(r * a + background[0] * (1 - a)),
                        int(g * a + background[1] * (1 - a)),
                        int(b * a + background[2] * (1 - a))))
            line += px * zoom
        for _ in range(zoom):
            rows += b'\x00' + line

    def chunk(tag, data):
        body = tag + data
        return (struct.pack('>I', len(data)) + body
                + struct.pack('>I', zlib.crc32(body) & 0xffffffff))
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', w * zoom, h * zoom, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(bytes(rows), 6))
            + chunk(b'IEND', b''))


def atlas_png(image, rect=None, across=230, background=(26, 26, 32),
              marker=(255, 120, 40)):
    """The whole sheet, small, with one sprite ringed on it.

    Seeing a sprite at 40x tells you WHAT it is. It does not tell you WHERE it
    came from, and on a packed atlas that is the more useful question -- a
    3x3 corner means nothing until you can see it is the top-left of the frame
    two rows down from the buttons.

    The ring is never smaller than a few pixels. A 1x1 sprite marked exactly
    would be one pixel on a thumbnail, which is no mark at all.
    """
    import zlib
    width, height = image['width'], image['height']
    step = max(1, width // max(1, across))
    out_w = width // step
    out_h = height // step

    ring = None
    if rect:
        x0, y0, w, h = rect
        rx0, ry0 = x0 // step, y0 // step
        rx1, ry1 = max(rx0 + 3, (x0 + w) // step), max(ry0 + 3, (y0 + h) // step)
        ring = (max(0, rx0 - 2), max(0, ry0 - 2),
                min(out_w - 1, rx1 + 2), min(out_h - 1, ry1 + 2))

    rows = bytearray()
    for oy in range(out_h):
        line = bytearray()
        y = oy * step
        for ox in range(out_w):
            x = ox * step
            at = (y * width + x) * 4
            if image['bgra']:
                b, g, r = image['pixels'][at], image['pixels'][at+1], image['pixels'][at+2]
            else:
                r, g, b = image['pixels'][at], image['pixels'][at+1], image['pixels'][at+2]
            a = image['pixels'][at + 3] / 255.0
            red = int(r * a + background[0] * (1 - a))
            green = int(g * a + background[1] * (1 - a))
            blue = int(b * a + background[2] * (1 - a))
            if ring:
                gx0, gy0, gx1, gy1 = ring
                on_edge = ((gy0 <= oy <= gy1 and ox in (gx0, gx1))
                           or (gx0 <= ox <= gx1 and oy in (gy0, gy1)))
                if on_edge:
                    red, green, blue = marker
            line += bytes((red, green, blue))
        rows += b'\x00' + line

    def chunk(tag, data):
        body = tag + data
        return (struct.pack('>I', len(data)) + body
                + struct.pack('>I', zlib.crc32(body) & 0xffffffff))
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', out_w, out_h, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(bytes(rows), 6))
            + chunk(b'IEND', b''))


def sub_image(image, rect, pad=8):
    """A small image holding just this sprite and a little around it.

    Previewing used to copy the WHOLE atlas -- a megabyte -- on every slider
    movement, which is most of why the app got slower the more you did. A
    sprite is usually a few hundred bytes.

    Returns (small image, rect within it).
    """
    x0, y0, w, h = rect
    sx = max(0, x0 - pad)
    sy = max(0, y0 - pad)
    ex = min(image['width'], x0 + w + pad)
    ey = min(image['height'], y0 + h + pad)
    sw, sh = ex - sx, ey - sy
    pixels = bytearray(sw * sh * 4)
    for row in range(sh):
        source = ((sy + row) * image['width'] + sx) * 4
        target = row * sw * 4
        pixels[target:target + sw * 4] = image['pixels'][source:source + sw * 4]
    small = {'width': sw, 'height': sh, 'header': image['header'],
             'pixels': pixels, 'bgra': image['bgra']}
    return small, (x0 - sx, y0 - sy, w, h)


def read_png(path):
    """A PNG back into pixels, so a sheet can go out to a real art program and
    come home again.

    Only the plain kind: 8-bit RGB or RGBA, not interlaced. That is what every
    art program writes by default, and handling the exotic variants would be a
    lot of code for cases nobody will hit.
    """
    import zlib
    data = open(path, 'rb').read()
    if data[:8] != b'\x89PNG\r\n\x1a\n':
        return None, "not a PNG"
    at = 8
    width = height = depth = kind = None
    body = bytearray()
    while at + 8 <= len(data):
        length = struct.unpack_from('>I', data, at)[0]
        tag = data[at + 4:at + 8]
        chunk = data[at + 8:at + 8 + length]
        if tag == b'IHDR':
            width, height, depth, kind = struct.unpack_from('>IIBB', chunk, 0)
            if struct.unpack_from('>B', chunk, 12)[0] != 0:
                return None, "interlaced PNGs are not read here"
        elif tag == b'IDAT':
            body += chunk
        elif tag == b'IEND':
            break
        at += 12 + length
    if depth != 8 or kind not in (2, 6):
        return None, "needs an 8-bit RGB or RGBA PNG"

    per = 3 if kind == 2 else 4
    raw = zlib.decompress(bytes(body))
    stride = width * per
    out = bytearray(width * height * 4)
    previous = bytearray(stride)
    pos = 0
    for y in range(height):
        filter_kind = raw[pos]
        pos += 1
        line = bytearray(raw[pos:pos + stride])
        pos += stride
        # PNG filtering: each row is stored as a difference from its
        # neighbours, so it has to be undone before the pixels mean anything.
        if filter_kind == 1:
            for i in range(per, stride):
                line[i] = (line[i] + line[i - per]) & 0xFF
        elif filter_kind == 2:
            for i in range(stride):
                line[i] = (line[i] + previous[i]) & 0xFF
        elif filter_kind == 3:
            for i in range(stride):
                left = line[i - per] if i >= per else 0
                line[i] = (line[i] + ((left + previous[i]) >> 1)) & 0xFF
        elif filter_kind == 4:
            for i in range(stride):
                left = line[i - per] if i >= per else 0
                up = previous[i]
                upleft = previous[i - per] if i >= per else 0
                guess = left + up - upleft
                da, db, dc = (abs(guess - left), abs(guess - up),
                              abs(guess - upleft))
                best = left if (da <= db and da <= dc) else (up if db <= dc
                                                             else upleft)
                line[i] = (line[i] + best) & 0xFF
        previous = line
        for x in range(width):
            source = x * per
            target = (y * width + x) * 4
            out[target] = line[source + 2]        # DDS here is BGRA
            out[target + 1] = line[source + 1]
            out[target + 2] = line[source]
            out[target + 3] = line[source + 3] if per == 4 else 255
    return {'width': width, 'height': height, 'pixels': out,
            'bgra': True, 'header': b''}, None


def dds_header(width, height):
    """A plain uncompressed BGRA header, matching what the game's own use."""
    head = bytearray(128)
    head[0:4] = b'DDS '
    struct.pack_into('<I', head, 4, 124)
    struct.pack_into('<I', head, 8, 0x1 | 0x2 | 0x4 | 0x1000 | 0x8 | 0x20000)
    struct.pack_into('<I', head, 12, height)
    struct.pack_into('<I', head, 16, width)
    struct.pack_into('<I', head, 20, width * 4)
    struct.pack_into('<I', head, 28, 1)
    struct.pack_into('<I', head, 76, 32)
    struct.pack_into('<I', head, 80, 0x1 | 0x40)
    struct.pack_into('<I', head, 88, 32)
    struct.pack_into('<I', head, 92, 0x00FF0000)
    struct.pack_into('<I', head, 96, 0x0000FF00)
    struct.pack_into('<I', head, 100, 0x000000FF)
    struct.pack_into('<I', head, 104, 0xFF000000)
    struct.pack_into('<I', head, 108, 0x1000)
    return bytes(head)


def export_png(image, path):
    """The whole sheet as a PNG, alpha intact, for a real art program."""
    import zlib
    width, height = image['width'], image['height']
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        base = y * width * 4
        line = image['pixels'][base:base + width * 4]
        if image['bgra']:
            for i in range(0, len(line), 4):
                rows += bytes((line[i + 2], line[i + 1], line[i], line[i + 3]))
        else:
            rows += line

    def chunk(tag, payload):
        body = tag + payload
        return (struct.pack('>I', len(payload)) + body
                + struct.pack('>I', zlib.crc32(body) & 0xffffffff))
    with open(path, 'wb') as handle:
        handle.write(b'\x89PNG\r\n\x1a\n'
                     + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height,
                                                  8, 6, 0, 0, 0))
                     + chunk(b'IDAT', zlib.compress(bytes(rows), 6))
                     + chunk(b'IEND', b''))
    return path


def import_png(path, into):
    """Read a PNG back over a texture, keeping its size.

    Refuses a different size rather than stretching. Every sprite rectangle in
    the stylesheet is measured in pixels, so a resized sheet silently moves
    every one of them and the interface comes apart in ways that are very hard
    to trace back here.
    """
    got, trouble = read_png(path)
    if not got:
        return None, trouble
    if (got['width'], got['height']) != (into['width'], into['height']):
        return None, ("that PNG is %dx%d and the sheet is %dx%d -- every sprite "
                      "is measured in pixels, so a resized sheet moves all of "
                      "them" % (got['width'], got['height'],
                                into['width'], into['height']))
    into['pixels'] = got['pixels']
    into['bgra'] = True
    into['header'] = dds_header(into['width'], into['height'])
    return into, None


def copy_image(image):
    return {'width': image['width'], 'height': image['height'],
            'header': image['header'], 'bgra': image['bgra'],
            'pixels': bytearray(image['pixels'])}


def target_of(text):
    """What a picked colour actually asks for.

    A hex carries hue, saturation and lightness, and only the hue was being
    used -- so picking BLACK gave bright red. Black has no hue; its hue field
    reads as zero, and zero is red. White and any grey did the same.

    Returns (hue, saturation scale, brightness scale). A grey target says "take
    the colour out and go this light", which is a real thing to want and was
    impossible to ask for.
    """
    hue, sat = hex_to_hue(text)
    rgb = parse_colour(text if text.startswith('#') else '#' + text)
    value = (max(rgb) / 255.0) if rgb else 1.0
    if sat < 0.10:
        # No hue in there. Treat it as "go grey, and go this light."
        return None, 0.0, max(0.15, value * 1.6)
    return hue, 1.0, 1.0


def hex_to_hue(text):
    """The hue of a hex colour, 0..1, plus its saturation."""
    text = text.lstrip('#')
    r, g, b = (int(text[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    high, low = max(r, g, b), min(r, g, b)
    if high == low:
        return 0.0, 0.0
    span = high - low
    if high == r:
        hue = ((g - b) / span) % 6
    elif high == g:
        hue = (b - r) / span + 2
    else:
        hue = (r - g) / span + 4
    return (hue / 6.0) % 1.0, span / high
