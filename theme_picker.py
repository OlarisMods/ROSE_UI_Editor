"""theme_picker.py -- a colour picker that belongs to this app.

Windows' own chooser is a white box in the middle of a dark window, and tkinter
cannot restyle it -- it is the operating system's dialog, not ours. So this is
ours: Theme Studio's picker, in this app's colours.

It does three things the system one cannot:

    SUGGESTIONS -- colours that make good themes, one click away.
    RECENT COLOURS -- what you picked earlier this session.
    LIVE -- on_change is called as you drag, so the app's own preview shows the
    whole theme changing while you choose. Cancel puts the old colour back.
"""

import os
import sys

try:
    import tkinter as tk
    from tkinter import ttk
except ImportError:
    sys.exit("This needs tkinter.")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import theme_core as core

BG = "#15151b"
PANEL = "#1e1e26"
INK = "#e8e8f0"
DIM = "#9a9aab"
ACCENT = "#7c7ce0"

RECENT = []                 # shared across every picker in the session


def ask_colour(parent, start='#ff7100', title="Pick a colour", swatches=None,
               on_change=None):
    """Open the picker and return a hex string, or None if cancelled."""
    dialog = Picker(parent, start, title, swatches or [], on_change)
    parent.wait_window(dialog.top)
    return dialog.result


class Picker(object):

    SQUARE = 190            # the saturation/value square
    STRIP = 24              # the hue strip

    def __init__(self, parent, start, title, swatches, on_change=None):
        self.result = None
        self.on_change = on_change
        self.hue, self.sat, self.val = self._from_hex(start)

        top = tk.Toplevel(parent)
        self.top = top
        top.title(title)
        top.configure(bg=BG)
        top.resizable(False, False)
        top.transient(parent)
        top.grab_set()

        body = ttk.Frame(top)
        body.pack(padx=14, pady=14)

        # ---- the square: saturation across, brightness down
        self.square = tk.Canvas(body, width=self.SQUARE, height=self.SQUARE,
                                highlightthickness=1,
                                highlightbackground="#3a3a46", bg=PANEL)
        self.square.grid(row=0, column=0, rowspan=2)
        self.square.bind('<Button-1>', self.on_square)
        self.square.bind('<B1-Motion>', self.on_square)

        # ---- the hue strip
        self.strip = tk.Canvas(body, width=self.STRIP, height=self.SQUARE,
                               highlightthickness=1,
                               highlightbackground="#3a3a46", bg=PANEL)
        self.strip.grid(row=0, column=1, rowspan=2, padx=(10, 14))
        self.strip.bind('<Button-1>', self.on_strip)
        self.strip.bind('<B1-Motion>', self.on_strip)

        side = ttk.Frame(body)
        side.grid(row=0, column=2, sticky='n')

        self.preview = tk.Canvas(side, width=90, height=52,
                                 highlightthickness=1,
                                 highlightbackground="#3a3a46")
        self.preview.pack()

        row = ttk.Frame(side)
        row.pack(pady=(8, 0))
        ttk.Label(row, text="hex", style='Dim.TLabel').pack(side='left')
        self.box = ttk.Entry(row, width=10)
        self.box.pack(side='left', padx=4)
        self.box.bind('<Return>', lambda _e: self.from_box())
        ttk.Button(row, text="set", width=4,
                   command=self.from_box).pack(side='left')

        if swatches:
            ttk.Label(side, text="suggestions", style='Dim.TLabel'
                      ).pack(anchor='w', pady=(12, 2))
            self._swatch_row(side, swatches[:16])
        if RECENT:
            ttk.Label(side, text="recent", style='Dim.TLabel'
                      ).pack(anchor='w', pady=(10, 2))
            self._swatch_row(side, RECENT[:16])

        foot = ttk.Frame(top)
        foot.pack(fill='x', padx=14, pady=(0, 14))
        ttk.Button(foot, text="Cancel", command=top.destroy).pack(side='right')
        ttk.Button(foot, text="Use it", style='Go.TButton',
                   command=self.accept).pack(side='right', padx=8)

        self._draw_strip()
        self.redraw()
        # Placed deliberately: over the colour controls, never over the app's
        # preview -- which updates live as you drag, and is the point of it.
        top.update_idletasks()
        top.geometry('+%d+%d' % (parent.winfo_rootx() + 290, parent.winfo_rooty() + 40))
        top.bind('<Return>', lambda _e: self.accept())
        top.bind('<Escape>', lambda _e: top.destroy())

    # ------------------------------------------------------------- swatches

    def _swatch_row(self, parent, colours):
        holder = ttk.Frame(parent)
        holder.pack(anchor='w')
        for index, colour in enumerate(colours):
            cell = tk.Canvas(holder, width=18, height=18, bg=colour,
                             highlightthickness=1,
                             highlightbackground="#3a3a46")
            cell.grid(row=index // 8, column=index % 8, padx=1, pady=1)
            cell.bind('<Button-1>', lambda _e, c=colour: self.take(c))

    def take(self, colour):
        self.hue, self.sat, self.val = self._from_hex(colour)
        self.redraw()

    # ---------------------------------------------------------------- maths

    @staticmethod
    def _from_hex(text):
        rgb = core.parse_colour(text if text.startswith('#') else '#' + text)
        if not rgb:
            return 0.08, 1.0, 1.0
        return core._rgb_to_hsv(*rgb)

    def hex(self):
        r, g, b = core._hue_to_rgb(self.hue, self.sat, self.val)
        return '#%02x%02x%02x' % (r, g, b)

    # -------------------------------------------------------------- drawing

    def _draw_strip(self):
        """The hue strip only has to be drawn once -- it never changes."""
        step = 3
        for y in range(0, self.SQUARE, step):
            r, g, b = core._hue_to_rgb(y / float(self.SQUARE), 1.0, 1.0)
            self.strip.create_rectangle(0, y, self.STRIP, y + step,
                                        fill='#%02x%02x%02x' % (r, g, b),
                                        width=0)

    def redraw(self):
        """The square is redrawn per hue, in blocks -- per pixel would crawl."""
        self.square.delete('field')
        step = 10
        for y in range(0, self.SQUARE, step):
            value = 1.0 - y / float(self.SQUARE)
            for x in range(0, self.SQUARE, step):
                sat = x / float(self.SQUARE)
                r, g, b = core._hue_to_rgb(self.hue, sat, value)
                self.square.create_rectangle(x, y, x + step, y + step,
                                             fill='#%02x%02x%02x' % (r, g, b),
                                             width=0, tags='field')
        cx = self.sat * self.SQUARE
        cy = (1.0 - self.val) * self.SQUARE
        self.square.create_oval(cx - 6, cy - 6, cx + 6, cy + 6,
                                outline='white', width=2, tags='field')
        self.square.create_oval(cx - 7, cy - 7, cx + 7, cy + 7,
                                outline='black', width=1, tags='field')

        self.strip.delete('mark')
        y = self.hue * self.SQUARE
        self.strip.create_rectangle(0, y - 2, self.STRIP, y + 2,
                                    outline='white', width=2, tags='mark')

        colour = self.hex()
        self.preview.configure(bg=colour)
        self.box.delete(0, 'end')
        self.box.insert(0, colour)
        if self.on_change:
            self.on_change(colour)

    # --------------------------------------------------------------- events

    def on_square(self, event):
        self.sat = max(0.0, min(1.0, event.x / float(self.SQUARE)))
        self.val = max(0.0, min(1.0, 1.0 - event.y / float(self.SQUARE)))
        self.redraw()

    def on_strip(self, event):
        self.hue = max(0.0, min(0.999, event.y / float(self.SQUARE)))
        self.redraw()

    def from_box(self):
        text = self.box.get().strip()
        if core.parse_colour(text if text.startswith('#') else '#' + text):
            self.take(text)

    def accept(self):
        self.result = self.hex()
        if self.result in RECENT:
            RECENT.remove(self.result)
        RECENT.insert(0, self.result)
        del RECENT[24:]
        self.top.destroy()
