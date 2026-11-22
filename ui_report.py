# -*- coding: utf-8 -*-
"""Janela do relatório de aprendizado (xpreport): o texto inteiro para o jogador ler, com Copiar e Salvar. O
programa não envia nada: quem quiser ajudar copia ou salva e manda para quem quiser."""

import datetime
import tkinter as tk
from tkinter import filedialog, ttk

import xpreport
from i18n import _
from version import VERSION

_OPEN = {}


def refresh():
    """Refaz o texto da janela aberta (a leitura da pasta terminou, por exemplo)."""
    win = _OPEN.get("win")
    if win is not None:
        try:
            _fill(win)
        except tk.TclError:
            _OPEN.pop("win", None)


def open_report(root, cfg, colors=None, font=None, status_fn=None):
    """Abre (ou traz para a frente) a janela do relatório. `colors`: {"panel", "tile", "fg", "muted", "btn"}.
    `status_fn()`: linha de andamento (a leitura das gravações que já estavam na pasta), "" quando não há."""
    win = _OPEN.get("win")
    if win is not None:
        try:
            win.deiconify()
            win.lift()
            _fill(win)
            return win
        except tk.TclError:
            _OPEN.pop("win", None)
    c = dict(panel="#1b1f2a", tile="#232838", fg="#e5e7eb", muted="#94a3b8", btn="#2d3446")
    c.update(colors or {})
    win = tk.Toplevel(root)
    win.title(_("Relatório de aprendizado"))
    win.configure(bg=c["panel"])
    win.geometry("980x640")
    win.minsize(560, 320)
    top = tk.Frame(win, bg=c["panel"], padx=12, pady=10)
    top.pack(fill="x")
    tk.Label(top, text=_("O que o Replay Master aprendeu sobre XP e drops nas suas gravações. Nada é enviado: se "
                         "quiser ajudar a melhorar o programa, copie ou salve e mande para quem desenvolve (ou para "
                         "quem você quiser). Não há nada pessoal no texto."),
             bg=c["panel"], fg=c["muted"], justify="left", anchor="w", wraplength=940,
             font=font).pack(fill="x")
    note = tk.Label(top, text="", bg=c["panel"], fg="#f59e0b", justify="left", anchor="w", wraplength=940, font=font)
    note.pack(fill="x")

    def poll():
        try:
            note.configure(text=(status_fn() if status_fn else "") or "")
            win.after(2000, poll)
        except tk.TclError:                       # a janela fechou
            pass
    box = tk.Frame(win, bg=c["panel"], padx=12)
    box.pack(fill="both", expand=True)
    txt = tk.Text(box, wrap="none", bg=c["tile"], fg=c["fg"], insertbackground=c["fg"], relief="flat",
                  font=("Consolas", 10), padx=8, pady=6)
    ys = ttk.Scrollbar(box, orient="vertical", command=txt.yview)
    xs = ttk.Scrollbar(box, orient="horizontal", command=txt.xview)
    txt.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
    txt.grid(row=0, column=0, sticky="nsew")
    ys.grid(row=0, column=1, sticky="ns")
    xs.grid(row=1, column=0, sticky="ew")
    box.rowconfigure(0, weight=1)
    box.columnconfigure(0, weight=1)
    bar = tk.Frame(win, bg=c["panel"], padx=12, pady=10)
    bar.pack(fill="x")
    status = tk.Label(bar, text="", bg=c["panel"], fg=c["muted"], font=font)
    status.pack(side="left")

    def copy():
        win.clipboard_clear()
        win.clipboard_append(txt.get("1.0", "end-1c"))
        status.configure(text=_("Copiado!"))
        win.after(2000, lambda: status.configure(text=""))

    def save():
        path = filedialog.asksaveasfilename(
            parent=win, title=_("Salvar relatório"), defaultextension=".txt",
            # com a hora: relatórios de jogadores diferentes no mesmo dia vinham com o mesmo nome
            initialfile="replay-master-relatorio-%s.txt" % datetime.datetime.now().strftime("%Y-%m-%d-%Hh%M"),
            filetypes=[(_("Texto"), "*.txt")])
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(txt.get("1.0", "end-1c") + "\n")
            status.configure(text=_("Salvo."))
            win.after(2000, lambda: status.configure(text=""))
    ttk.Button(bar, text=_("Fechar"), command=win.destroy).pack(side="right")
    ttk.Button(bar, text=_("Salvar como…"), command=save).pack(side="right", padx=6)
    ttk.Button(bar, text=_("Copiar tudo"), command=copy).pack(side="right")
    win.report_text, win.report_cfg, win.report_note = txt, cfg, note
    win.protocol("WM_DELETE_WINDOW", lambda: (_OPEN.pop("win", None), win.destroy()))
    _OPEN["win"] = win
    _fill(win)
    poll()
    return win


def _fill(win):
    """Escreve o relatório na janela (só leitura: o texto pode ser selecionado e copiado)."""
    txt = win.report_text
    txt.configure(state="normal")
    txt.delete("1.0", "end")
    txt.insert("1.0", xpreport.text(win.report_cfg, VERSION))
    txt.configure(state="disabled")
