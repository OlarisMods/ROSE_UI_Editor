"""ROSE UI Editor -- your ROSE Online interface, in your colours.

Three steps: find the game, pick two colours (or let the dice pick), apply.
Undo and Remove put everything back exactly as it was.
"""

import os
import queue
import random
import shutil
import sys
import tempfile
import threading
import traceback

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

HERE = os.path.dirname(sys.executable if getattr(sys, 'frozen', False) else os.path.abspath(__file__))
sys.path.insert(0, HERE)

import engine
import installer
import preview
import theme_picker

# The neutral base travels with the app. Packaged as an exe, PyInstaller puts
# data in its own folder (sys._MEIPASS); run as a script, it sits beside us.
BASE = next((p for p in (os.path.join(getattr(sys, '_MEIPASS', HERE), 'base'),
                         os.path.join(HERE, 'base')) if os.path.isdir(p)),
            os.path.join(HERE, 'base'))

BG, PANEL, INK, DIM, LINE = '#15151b', '#1e1e26', '#e8e8f0', '#9a9aab', '#2c2c38'
GOOD, WARN = '#6fd38a', '#f0b252'

# One click away in the picker: colours that make good themes.
SUGGEST = ['#2a9d8f', '#e9c46a', '#b3263a', '#f4a261', '#7b4fd6', '#c3a6ff', '#2d6a4f', '#95d5b2',
           '#1d3557', '#8ecae6', '#e56b8f', '#6d2e5a', '#4a5568', '#c8c8d0', '#e76f51', '#5a2ea6']


def hexc(c):
    return '#%02x%02x%02x' % tuple(c)


def parse(h):
    h = h.strip().lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


class App:
    def __init__(self, root):
        self.root = root
        self.jobs = queue.Queue()
        self.busy = False
        self.pending = None
        self.images = []
        self.history = installer.History()
        s = self.history.settings()
        self.main = parse(s.get('main', '#2a9d8f'))
        self.accent = parse(s.get('accent', '#e9c46a'))
        self.mode = tk.StringVar(value=s.get('mode', 'classic'))
        self.chat = tk.StringVar(value=s.get('chat', 'classic'))
        self.game = tk.StringVar(value=s.get('game') or installer.find_game() or '')
        self.seed = tk.StringVar(value=str(s.get('seed', '')))
        self.scheme = ''
        self.preview = preview.Preview(BASE)

        root.title('ROSE UI Editor')
        root.configure(bg=BG)
        root.minsize(760, 760)
        self.style()
        self.build()
        self.check_game()
        self.refresh()
        self.poll()
        if installer.recover(self.history):
            messagebox.showinfo('ROSE UI Editor',
                                'The last apply was interrupted -- the game folder has been put '
                                'back exactly as it was before it.')
        self.update_history()

    # ------------------------------------------------------------ look

    def style(self):
        st = ttk.Style(self.root)
        st.theme_use('clam')
        st.configure('.', background=BG, foreground=INK, fieldbackground=PANEL,
                     bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, font=('Segoe UI', 10))
        st.configure('TButton', background=PANEL, padding=(12, 6))
        st.map('TButton', background=[('active', '#2a2a36'), ('disabled', BG)],
               foreground=[('disabled', '#55556a')])
        st.configure('Big.TButton', font=('Segoe UI', 11, 'bold'), padding=(18, 9))
        st.configure('Go.TButton', font=('Segoe UI', 10, 'bold'))
        st.configure('TRadiobutton', background=BG)
        st.map('TRadiobutton', background=[('active', BG)])
        st.configure('Step.TLabel', font=('Segoe UI', 12, 'bold'))
        st.configure('Dim.TLabel', foreground=DIM)
        st.configure('TEntry', padding=5)
        st.configure('Horizontal.TProgressbar', troughcolor=PANEL, background='#7c7ce0')

    def step(self, parent, number, title):
        f = ttk.Frame(parent)
        f.pack(fill='x', pady=(14, 4))
        badge = tk.Canvas(f, width=26, height=26, bg=BG, highlightthickness=0)
        badge.create_oval(2, 2, 24, 24, fill='#34344a', outline='')
        badge.create_text(13, 13, text=str(number), fill=INK, font=('Segoe UI', 10, 'bold'))
        badge.pack(side='left', padx=(0, 10))
        ttk.Label(f, text=title, style='Step.TLabel').pack(side='left')

    # ------------------------------------------------------------ layout

    def build(self):
        page = ttk.Frame(self.root, padding=(22, 8, 22, 18))
        page.pack(fill='both', expand=True)

        # 1 -- the game
        self.step(page, 1, 'Your game')
        row = ttk.Frame(page)
        row.pack(fill='x', padx=(36, 0))
        e = ttk.Entry(row, textvariable=self.game)
        e.pack(side='left', fill='x', expand=True)
        e.bind('<FocusOut>', lambda _e: self.check_game())
        e.bind('<Return>', lambda _e: self.check_game())
        ttk.Button(row, text='Browse...', command=self.browse).pack(side='left', padx=(8, 0))
        self.game_note = ttk.Label(page, text='', style='Dim.TLabel')
        self.game_note.pack(anchor='w', padx=(36, 0), pady=(4, 0))

        # 2 -- the colours
        self.step(page, 2, 'Your colours')
        pick = ttk.Frame(page)
        pick.pack(fill='x', padx=(36, 0))
        self.main_btn = self.swatch(pick, 'Main', 'panels, glass, frames', lambda: self.choose('main'))
        self.accent_btn = self.swatch(pick, 'Accent', 'edges, highlights, text', lambda: self.choose('accent'))

        dice = ttk.Frame(page)
        dice.pack(fill='x', padx=(36, 0), pady=(10, 0))
        ttk.Button(dice, text='Surprise me', command=self.surprise).pack(side='left')
        ttk.Label(dice, text='   seed', style='Dim.TLabel').pack(side='left')
        se = ttk.Entry(dice, textvariable=self.seed, width=9)
        se.pack(side='left', padx=(6, 4))
        se.bind('<Return>', lambda _e: self.use_seed())
        ttk.Button(dice, text='Use', width=5, command=self.use_seed).pack(side='left')
        self.scheme_note = ttk.Label(dice, text='', style='Dim.TLabel')
        self.scheme_note.pack(side='left', padx=10)

        bars = ttk.Frame(page)
        bars.pack(fill='x', padx=(36, 0), pady=(10, 0))
        ttk.Label(bars, text='Health and mana bars').pack(side='left')
        for text, value in (('Classic -- red and blue', 'classic'), ('Match my theme', 'match')):
            ttk.Radiobutton(bars, text=text, value=value, variable=self.mode,
                            command=self.refresh).pack(side='left', padx=(14, 0))
        chat = ttk.Frame(page)
        chat.pack(fill='x', padx=(36, 0), pady=(8, 0))
        ttk.Label(chat, text='Chat colours').pack(side='left')
        for text, value in (('Classic -- the game\'s own', 'classic'), ('Match my theme', 'match')):
            ttk.Radiobutton(chat, text=text, value=value, variable=self.chat,
                            command=self.refresh).pack(side='left', padx=(14, 0))
        ttk.Label(page, text='Error messages and staff names always keep their own colours, so '
                             'nobody can be mistaken for a GM.', style='Dim.TLabel',
                  wraplength=640).pack(
            anchor='w', padx=(36, 0), pady=(2, 0))
        self.warn = ttk.Label(page, text='', foreground=WARN, wraplength=640)
        self.warn.pack(anchor='w', padx=(36, 0), pady=(6, 0))

        # the preview
        self.canvas = tk.Canvas(page, width=680, height=300, bg=BG, highlightthickness=0)
        self.canvas.pack(pady=(8, 0))

        # 3 -- apply
        self.step(page, 3, 'Apply')
        acts = ttk.Frame(page)
        acts.pack(fill='x', padx=(36, 0))
        self.apply_btn = ttk.Button(acts, text='Apply theme', style='Big.TButton', command=self.apply)
        self.apply_btn.pack(side='left')
        self.undo_btn = ttk.Button(acts, text='Undo last change', command=self.undo)
        self.undo_btn.pack(side='left', padx=(10, 0))
        self.remove_btn = ttk.Button(acts, text='Remove theme', command=self.remove)
        self.remove_btn.pack(side='left', padx=(10, 0))
        self.bar = ttk.Progressbar(page, mode='determinate', maximum=10)
        self.bar.pack(fill='x', padx=(36, 0), pady=(12, 0))
        self.status = ttk.Label(page, text='', style='Dim.TLabel', wraplength=640)
        self.status.pack(anchor='w', padx=(36, 0), pady=(6, 0))

    def swatch(self, parent, name, hint, command):
        f = ttk.Frame(parent)
        f.pack(side='left', padx=(0, 34))
        ttk.Label(f, text=name).grid(row=0, column=0, sticky='w')
        ttk.Label(f, text=hint, style='Dim.TLabel').grid(row=1, column=0, columnspan=3, sticky='w')
        c = tk.Canvas(f, width=54, height=26, highlightthickness=1, highlightbackground=LINE,
                      cursor='hand2')
        c.grid(row=0, column=1, padx=(10, 6))
        c.bind('<Button-1>', lambda _e: command())
        lab = ttk.Label(f, text='')
        lab.grid(row=0, column=2)
        return c, lab

    # ------------------------------------------------------------ step 1

    def browse(self):
        d = filedialog.askdirectory(title='Where is ROSE Online installed?',
                                    initialdir=self.game.get() or 'C:\\')
        if d:
            self.game.set(os.path.normpath(d))
            self.check_game()

    def check_game(self):
        g = self.game.get().strip()
        if installer.is_game(g):
            self.game_note.configure(text='Found ROSE Online.', foreground=GOOD)
            self.save()
            ok = True
        elif g:
            self.game_note.configure(text="That folder doesn't have ROSE in it -- look for the one "
                                          'with trose.exe.', foreground=WARN)
            ok = False
        else:
            self.game_note.configure(text="Couldn't find ROSE automatically -- use Browse.",
                                     foreground=WARN)
            ok = False
        self.game_ok = ok
        self.update_buttons()
        return ok

    # ------------------------------------------------------------ step 2

    def choose(self, which):
        """The app's own dark picker. The preview follows as you drag; Cancel puts
        the old colour back."""
        before = self.main if which == 'main' else self.accent

        def live(hx):
            self.set_colour(which, parse(hx))
            self.refresh(save=False)
        got = theme_picker.ask_colour(self.root, hexc(before), 'Pick your %s colour' % which,
                                      swatches=SUGGEST, on_change=live)
        if got:
            self.set_colour(which, parse(got))
            self.scheme = ''
            self.seed.set('')           # a hand-picked colour is no longer that seed's pair
        else:
            self.set_colour(which, before)
        self.refresh()

    def set_colour(self, which, c):
        if which == 'main':
            self.main = c
        else:
            self.accent = c

    def surprise(self):
        now = preview.seed_key(self.seed.get())
        word = preview.surprise_word()
        while word == now:
            word = preview.surprise_word()
        self.seed.set(word)
        self.use_seed()

    def use_seed(self):
        """Any word, name or number is a seed -- 'pumpkin' is always the same theme."""
        text = preview.seed_key(self.seed.get())
        if not text:
            self.say('Type any word as a seed -- or press Surprise me.')
            return
        self.seed.set(text)
        self.main, self.accent, self.scheme = preview.random_pair(text)
        self.refresh()

    def refresh(self, save=True):
        for (canvas, label), c in ((self.main_btn, self.main), (self.accent_btn, self.accent)):
            canvas.configure(bg=hexc(c))
            label.configure(text=hexc(c))
        self.scheme_note.configure(text=('a %s pair' % self.scheme) if self.scheme else '')
        close = preview.too_close(self.main, self.accent)
        if close and self.mode.get() == 'match':
            self.warn.configure(text='These two are too close: health and mana would look alike. '
                                     'Pick more different colours, or use Classic bars.')
        elif close:
            self.warn.configure(text='These two are very close -- the theme will look nearly one colour.')
        else:
            self.warn.configure(text='')
        if save:
            self.save()
        self.update_buttons()
        if self.pending:
            self.root.after_cancel(self.pending)
        self.pending = self.root.after(60, self.draw)

    def draw(self):
        self.pending = None
        out = self.preview.render(self.main, self.accent, self.mode.get(), self.chat.get())
        col = out['colours']
        cv = self.canvas
        cv.delete('all')
        self.images = []

        def img(data, zoom=1):
            p = tk.PhotoImage(data=data)
            if zoom > 1:
                p = p.zoom(zoom)
            self.images.append(p)
            return p
        cv.create_rectangle(2, 2, 678, 298, fill=col['background'], outline=col['main'])
        cv.create_image(22, 24, image=img(out['minimap']), anchor='nw')
        x = 160
        cv.create_text(x, 30, text='Party Finder', fill=col['accent'], anchor='w',
                       font=('Segoe UI', 13, 'bold'))
        cv.create_text(x, 54, text='Crystal Defenders  --  Level 231 to 250', fill=col['text'],
                       anchor='w', font=('Segoe UI', 10))
        for i, (who, key, line) in enumerate((('Remfera:', 'say', 'hi all!'),
                                             ('[Party]', 'party', 'anyone for Crystal Defenders?'),
                                             ('[Clan]', 'clan', 'gg all, nice run'),
                                             ('[Trade]', 'trade', 'selling Void armour'))):
            y = 78 + i * 16
            cv.create_text(x, y, text='04:%02d' % (12 + i), fill=col['accent-dim'], anchor='w',
                           font=('Segoe UI', 9))
            cv.create_text(x + 40, y, text='%s %s' % (who, line), fill=col[key], anchor='w',
                           font=('Segoe UI', 9))
        for i, (kind, data) in enumerate(out['bars']):
            y = 146 + i * 30
            cv.create_text(x, y + 11, text={'hp': 'HP', 'mp': 'MP', 'exp': 'EXP'}[kind],
                           fill=col['text'], anchor='w', font=('Segoe UI', 9, 'bold'))
            cv.create_image(x + 38, y, image=img(data), anchor='nw')
        bx = 440
        for i, data in enumerate(out['buttons'][:3]):
            cv.create_image(bx + i * 40, 146, image=img(data), anchor='nw')
        if len(out['buttons']) > 3:
            cv.create_image(bx + 130, 140, image=img(out['buttons'][3]), anchor='nw')
        cv.create_text(bx, 184, text='normal  hover  pressed', fill=col['accent-dim'], anchor='w',
                       font=('Segoe UI', 8))
        for i, data in enumerate(out['icons']):
            cv.create_image(22 + i * 44, 246, image=img(data, 2), anchor='nw')
        cv.create_text(430, 266, text='class buffs keep their own colours', fill=col['accent-dim'],
                       anchor='w', font=('Segoe UI', 8))

    # ------------------------------------------------------------ step 3

    def update_buttons(self):
        can = not self.busy and getattr(self, 'game_ok', False)
        block = preview.too_close(self.main, self.accent) and self.mode.get() == 'match'
        self.apply_btn.state(['!disabled'] if can and not block else ['disabled'])
        have = bool(self.history.entries) and not self.busy
        for b in (self.undo_btn, self.remove_btn):
            b.state(['!disabled'] if have else ['disabled'])

    def update_history(self):
        if self.history.entries:
            e = self.history.entries[-1]
            n = len(self.history.entries)
            self.say('Current theme: main %s, accent %s, %s bars, %s chat -- applied %s.  %d %s '
                     'can be undone.' % (e.get('main'), e.get('accent'), e.get('mode'),
                                        e.get('chat', 'classic'),
                                 e.get('when', '').replace('T', ' at '), n,
                                 'change' if n == 1 else 'changes'))
        else:
            self.say('No theme applied yet -- the game is as it was.')
        self.update_buttons()

    def run(self, label, work, done):
        """Run slow work off the window's thread. busy is ALWAYS cleared, and any
        failure goes on screen -- a thread that dies in tkinter prints nowhere."""
        self.busy = True
        self.update_buttons()
        self.bar.configure(value=0)
        self.say(label)

        def worker():
            try:
                result = work(lambda n, total, what: self.jobs.put(('progress', n, total, what)))
                self.jobs.put(('done', done, result))
            except installer.InstallError as e:
                self.jobs.put(('error', str(e)))
            except Exception:
                self.jobs.put(('error', 'Something went wrong:\n\n' + traceback.format_exc()))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            while True:
                job = self.jobs.get_nowait()
                if job[0] == 'progress':
                    _k, n, total, what = job
                    self.bar.configure(maximum=total, value=n)
                    self.say('Working -- %s' % what)
                elif job[0] == 'done':
                    self.busy = False
                    job[1](job[2])
                    self.bar.configure(value=0)
                elif job[0] == 'error':
                    self.busy = False
                    self.bar.configure(value=0)
                    messagebox.showerror('ROSE UI Editor', job[1])
                    self.update_history()
        except queue.Empty:
            pass                    # nothing waiting -- the normal case, every 80ms
        finally:
            self.update_buttons()
            self.root.after(80, self.poll)

    def apply(self):
        if not self.check_game():
            return
        if preview.too_close(self.main, self.accent) and self.mode.get() == 'match':
            return
        game, main, accent, mode = self.game.get().strip(), self.main, self.accent, self.mode.get()
        chat = self.chat.get()
        info = {'main': hexc(main), 'accent': hexc(accent), 'mode': mode, 'chat': chat,
                'seed': self.seed.get().strip() if self.scheme else ''}
        history = self.history

        def work(progress):
            installer.check_game(game)
            tmp = tempfile.mkdtemp(prefix='build-', dir=installer.data_dir())
            try:
                out = os.path.join(tmp, 'theme')
                engine.build(BASE, out, main, accent, mode, progress, chat=chat)
                progress(10, 10, 'installing')
                installer.apply(history, game, out, info)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

        def done(_r):
            self.update_history()
            messagebox.showinfo('ROSE UI Editor', 'Your theme is in. Start (or restart) ROSE to see it.')
        self.run('Building your theme...', work, done)

    def undo(self):
        def work(_p):
            return installer.undo_last(self.history)

        def done(_r):
            self.update_history()
            messagebox.showinfo('ROSE UI Editor', 'Undone. Restart ROSE to see the change.')
        self.run('Undoing...', work, done)

    def remove(self):
        if not messagebox.askyesno('ROSE UI Editor', 'Put the game folder back exactly as it was before '
                                                 'this app first changed it?'):
            return

        def work(_p):
            return installer.remove_all(self.history)

        def done(n):
            self.update_history()
            messagebox.showinfo('ROSE UI Editor', 'Removed -- %d change(s) undone. The game folder is '
                                              'as it was. Restart ROSE to see it.' % n)
        self.run('Removing...', work, done)

    # ------------------------------------------------------------ helpers

    def say(self, text):
        self.status.configure(text=text)

    def save(self):
        s = self.history.settings()
        s.update({'main': hexc(self.main), 'accent': hexc(self.accent), 'mode': self.mode.get(),
                  'chat': self.chat.get(),
                  'game': self.game.get().strip(), 'seed': self.seed.get().strip()})
        try:
            self.history.save()
        except OSError:
            pass


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == '__main__':
    main()
