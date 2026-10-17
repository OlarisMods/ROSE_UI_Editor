"""installer.py -- put a theme into the game folder, and take it back out.

Theme Studio's golden rule was never to write to the folder you opened. This
app's whole job is to write into the game, so that rule is replaced by two
promises:

    1. EVERY FILE IT REPLACES IS BACKED UP FIRST, outside the game folder, where
       a game repair or reinstall cannot reach it.
    2. EVERY APPLY IS RECORDED -- each file, and whether it already existed.

Together they make undo exact rather than a guess: put back what was there,
delete what we added.

THE RECORD IS SAVED BEFORE COPYING, marked unfinished. If the app dies mid-copy
-- a crash, a power cut -- the next start finds an unfinished record and rolls
it back. If copying fails while the app is still running, it rolls back on the
spot. Either way the game folder is never left half-themed.

History is a stack: "Undo last change" pops one apply; "Remove theme" pops them
all, back to how the folder was before this app first touched it.
"""

import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys

# Where backups and the undo history live: %LOCALAPPDATA%\ROSE Theme.
# The app was called "ROSE Theme" before it became the ROSE UI Editor. The
# folder keeps that name ON PURPOSE: renaming it would orphan the backups of
# everyone who applied a theme with an earlier version, and Undo and Remove
# would no longer find them. People never see this name, so it stays.
APP = 'ROSE Theme'

GAME_MARKERS = ('trose.exe', 'rose.vfs')

CANDIDATES = [
    r'C:\Program Files\ROSE Online',
    r'C:\Program Files (x86)\ROSE Online',
    r'C:\Program Files\Rednim Games\ROSE Online',
    r'C:\Program Files (x86)\Rednim Games\ROSE Online',
    r'C:\Rednim Games\ROSE Online',
    r'C:\ROSE Online',
]


# Files a theme must NOT leave in the game, removed on apply if present.
#
# Before the 16 October 2026 patch, every UI pack -- and this app's own themes
# -- shipped spritesheet_glassui.css. After it, a copy in the game OVERRIDES the
# official one, and the official one is where the patch put its moved and newly
# named sprites. A stale copy silently loses the inventory weight icon, mall
# points and quest markers. So applying a theme retires it. It is backed up and
# recorded like any replaced file, so Undo and Remove put it back exactly.
RETIRE = ['data/ui/themes/rose/styles/spritesheet_glassui.css']


class InstallError(Exception):
    """Something the user needs to be told, in words they can act on."""


# ---------------------------------------------------------------- where things live

def data_dir():
    """The app's own folder for backups and history -- NOT the game folder."""
    base = os.environ.get('LOCALAPPDATA') or os.path.join(os.path.expanduser('~'), '.local', 'share')
    path = os.path.join(base, APP)
    os.makedirs(path, exist_ok=True)
    return path


def is_game(folder):
    return bool(folder) and any(os.path.isfile(os.path.join(folder, m)) for m in GAME_MARKERS)


def find_game():
    for c in CANDIDATES:
        if is_game(c):
            return c
    return None


def game_running():
    """Is ROSE open? Only answerable on Windows; elsewhere, assume not."""
    if not sys.platform.startswith('win'):
        return False
    try:
        out = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq trose.exe', '/NH'],
                             capture_output=True, text=True, timeout=10,
                             creationflags=0x08000000).stdout      # no console flash
        return 'trose.exe' in out.lower()
    except Exception:
        return False


def writable(folder):
    probe = os.path.join(folder, '.rose_theme_write_test')
    try:
        open(probe, 'w').close()
        os.remove(probe)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------- the record

class History:
    def __init__(self, root=None):
        self.root = root or data_dir()
        self.path = os.path.join(self.root, 'state.json')
        self.backups = os.path.join(self.root, 'backups')
        try:
            self.state = json.load(open(self.path))
        except (OSError, ValueError):
            self.state = {'version': 1, 'history': [], 'settings': {}}

    def save(self):
        tmp = self.path + '.tmp'
        with open(tmp, 'w') as f:
            json.dump(self.state, f, indent=1)
        os.replace(tmp, self.path)              # never a half-written record

    @property
    def entries(self):
        return self.state['history']

    def settings(self):
        return self.state.setdefault('settings', {})


def _safe_rel(rel):
    """A path inside the theme -- never absolute, never climbing out."""
    rel = rel.replace('\\', '/')
    parts = [p for p in rel.split('/') if p not in ('', '.')]
    if not parts or os.path.isabs(rel) or '..' in parts or ':' in parts[0]:
        raise InstallError('refusing an unsafe path in the theme: %r' % rel)
    return os.path.join(*parts)


def _theme_files(themed_dir):
    for root, _dirs, names in os.walk(themed_dir):
        for n in names:
            yield _safe_rel(os.path.relpath(os.path.join(root, n), themed_dir))


# ---------------------------------------------------------------- apply / undo

def check_game(game):
    if not is_game(game):
        raise InstallError("That folder doesn't look like ROSE Online -- there's no "
                           "trose.exe or rose.vfs in it.")
    if game_running():
        raise InstallError('ROSE is running. Close the game first, then apply.')
    if not writable(game):
        raise InstallError("Windows won't let this app write to the game folder. "
                           "Try running it as administrator.")


def apply(history, game, themed_dir, info, _fail_after=None):
    """Install every file in themed_dir into the game. Returns the new entry.

    _fail_after is for testing only: raise after that many copies, to prove the
    rollback works."""
    check_game(game)
    rels = sorted(_theme_files(themed_dir))
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    eid, n = stamp, 1
    while os.path.exists(os.path.join(history.backups, eid)):
        n += 1
        eid = '%s-%d' % (stamp, n)
    bdir = os.path.join(history.backups, eid)

    files, made_dirs = [], []
    for rel in rels:
        target = os.path.join(game, rel)
        existed = os.path.isfile(target)
        if existed:
            dst = os.path.join(bdir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(target, dst)
        files.append({'rel': rel, 'existed': existed})
        d = os.path.dirname(target)
        chain = []
        while d and not os.path.isdir(d) and os.path.abspath(d) != os.path.abspath(game):
            chain.append(d)
            d = os.path.dirname(d)
        for d in reversed(chain):
            if d not in made_dirs:
                made_dirs.append(d)

    for rel in RETIRE:
        target = os.path.join(game, rel)
        if rel in rels or not os.path.isfile(target):
            continue
        dst = os.path.join(bdir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(target, dst)
        files.append({'rel': rel, 'existed': True, 'retired': True})

    entry = dict(info, id=eid, game=game, files=files,
                 made_dirs=[os.path.relpath(d, game) for d in made_dirs],
                 when=datetime.datetime.now().isoformat(timespec='seconds'),
                 complete=False)
    history.entries.append(entry)
    history.save()                                   # BEFORE a single copy

    try:
        for i, rel in enumerate(rels):
            if _fail_after is not None and i >= _fail_after:
                raise OSError('simulated failure after %d copies' % i)
            target = os.path.join(game, rel)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(os.path.join(themed_dir, rel), target)
        for f in files:
            if f.get('retired'):
                os.remove(os.path.join(game, f['rel']))
    except Exception as e:
        _roll_back(history, entry)
        raise InstallError('Copying failed, and nothing was changed: %s' % e)

    entry['complete'] = True
    history.save()
    return entry


def _roll_back(history, entry):
    """Put the game folder back exactly as it was before this entry."""
    game = entry['game']
    bdir = os.path.join(history.backups, entry['id'])
    for f in entry['files']:
        target = os.path.join(game, f['rel'])
        if f['existed']:
            src = os.path.join(bdir, f['rel'])
            if os.path.isfile(src):
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(src, target)
        elif os.path.isfile(target):
            os.remove(target)
    for rel in sorted(entry.get('made_dirs', []), key=len, reverse=True):
        d = os.path.join(game, rel)
        if os.path.isdir(d) and not os.listdir(d):
            os.rmdir(d)
    shutil.rmtree(bdir, ignore_errors=True)
    history.entries.remove(entry)
    history.save()


def undo_last(history):
    if not history.entries:
        raise InstallError('Nothing to undo.')
    entry = history.entries[-1]
    if game_running():
        raise InstallError('ROSE is running. Close the game first, then undo.')
    _roll_back(history, entry)
    return entry


def remove_all(history):
    n = 0
    while history.entries:
        undo_last(history)
        n += 1
    return n


def recover(history):
    """An unfinished apply from a crash -- roll it back. Returns True if so."""
    if history.entries and not history.entries[-1].get('complete'):
        _roll_back(history, history.entries[-1])
        return True
    return False


def fingerprint(folder):
    """{relative path: sha1} of every file -- for tests and for trust."""
    out = {}
    for root, _dirs, names in os.walk(folder):
        for n in names:
            p = os.path.join(root, n)
            out[os.path.relpath(p, folder)] = hashlib.sha1(open(p, 'rb').read()).hexdigest()
    return out
