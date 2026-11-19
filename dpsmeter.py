# -*- coding: utf-8 -*-
"""Medidor de DPS do Ragnarok: lê a gravação de replay (.rrf) enquanto ela é escrita.

No jogo, comece a gravar um replay; o medidor encontra o arquivo novo na pasta
Replay sozinho e mostra o dano em tempo real.

Tudo é feito com o mouse (sem teclas de atalho), e clicar no widget não tira o
foco do jogo: as teclas continuam indo para o Ragnarok. Passe o mouse sobre um
botão para ver o que ele faz no rodapé; o botão direito abre todas as opções.
"""

import collections
import ctypes
import faulthandler
import json
import math
import os
import random
import subprocess
import sys
import threading
import time
import traceback
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox

import analysis
import cards
import clientdata
import itemkind
import itemping
import learnfolder
import sprites
import meter
import quests
import session
import sounds
import testes
import xp
from analysis_ui import AnalysisWindow
from fmt import num, dur, dec
import i18n
from i18n import _
from version import VERSION

IS_WIN = os.name == "nt"
WS_EX_NOACTIVATE = 0x08000000

CONFIG_PATH = os.environ.get("RODPS_CONFIG") or os.path.join(
    os.environ.get("APPDATA") or os.path.expanduser("~"), "RODpsMeter", "config.json")
RES_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
# o registro de aprendizado (xp_learn) mora num arquivo próprio: passa de 1 MB, e a configuração é gravada a toda hora
LEARN_PATH = os.path.join(os.path.dirname(CONFIG_PATH), "aprendizado.json")

# Medidas de base (escala 100%, 96 dpi)
BASE_W = 300            # largura padrão (o usuário pode mudar arrastando o canto)
MIN_W, MAX_W = 230, 640
MIN_ROWS, MAX_ROWS = 2, 20
TOP_Y = 15
BIG_Y = 50
TABS_Y0, TABS_Y1 = 76, 96
ROWS_Y0, ROW_H = 102, 21
PIN_H = 22             # faixa das informações fixadas (abaixo das abas)
MAX_PINS = 2
FOOT_H = 28
MIN_SCALE, MAX_SCALE = 0.7, 2.5
FONT_PX = {"big": 30, "big_s": 23, "spaced": 13, "unit": 11, "title": 12, "text": 11, "small": 10, "num": 12, "icon": 11, "tab": 11}
MIN_FONT_PX = 8
ALERT_S = 7.0          # quanto tempo um aviso fica no rodapé
DROP_SCROLL_ROWS = 3   # itens que a roda do mouse rola na aba Drops
MIRACLE_FLASH_S = 9.0  # o widget brilha por esse tempo quando o Milagre ativa
MIRACLE_BANNER_S = 6.0
MIRACLE_COLORS = ("#fbbf24", "#fde68a", "#c084fc", "#f9a8d4", "#ffffff", "#a5b4fc")
POLL_MS = 150         # ler o pedaço novo do arquivo custa < 1 ms
# Com uma thread de leitura ocupada (desenhos do jogo, lista de itens), o Python só devolve a vez à tela a cada
# "intervalo de troca" (5 ms por padrão), e isso a cada chamada do Tk: um desenho do widget faz uma centena delas
# e montar uma aba da análise, milhares, então a tela parava por segundos. Com 0,5 ms ela continua andando.
SWITCH_S = 0.0005
STALL_S = 8.0          # laço parado por mais que isso: o erros.log ganha onde o programa estava (vigia)
XP_ROWS_S = 1.0       # as linhas da XP (aba e faixa fixa) são refeitas no máximo a cada tanto...
XP_ROWS_COST = 20     # ...ou a cada 20× o que a conta levou, se ela ficar cara (sessão de muitas horas)
DEATH_CARD_S = 10.0   # o resumo da morte fica no widget por esse tempo
BOSS_CARD_S = 5.0     # o aviso de chefe que mudou (propriedade, imunidade, tamanho) fica esse tempo
PING_CARD_S = 12.0    # o cartão do item marcado que caiu (com o lugar, para copiar o /navi) fica esse tempo
PING_SOUND_GAP_S = 0.35   # dois itens marcados caindo juntos tocam o som uma vez só
BOSS_MERGE_MS = 2000  # mudanças do mesmo chefe quase juntas viram um cartão só (ex.: volta a ser grande e vira Sombrio)
SUMMARY_CARD_S = 14.0     # o resumo do fim da luta (conclusões do Dedo Duro) fica esse tempo
SUMMARY_WAIT_MS = 2500    # depois da morte do chefe, espera os últimos pacotes da luta
SUMMARY_PHASE_MS = 14000  # chefe em fases que morreu antes da 3ª: espera para ver se vem outra fase
SESSION_CARD_S = 600.0    # o resumo da sessão fica até ser fechado, começar outra luta ou passar este tempo
SESSION_FX_S = 6.0        # a animação do destaque no começo do resumo da sessão
HOLD_QUIET_S = 1.0        # parado há isso, o widget pergunta se o jogo ainda está com o arquivo da gravação aberto
HOLD_CHECK_S = 1.0        # ...no máximo uma vez a cada tanto (a pergunta leva uns 10 ms)
HOLD_SEEN_MIN = 2         # vezes que o jogo precisa ter sido visto com o arquivo parado aberto (ele segura o arquivo)
SESSION_FX_MS = 50        # um quadro a cada tanto enquanto ela roda (o laço normal, de 150 ms, picota o confete)
CONFETTI = ("#fbbf24", "#4ade80", "#60a5fa", "#f472b6", "#c084fc", "#f87171")
# "Máquina de abates": Poring, Drops, Poporing e Marin fugindo (do data.grf; sem o jogo, desenhados nestas cores)
CHASE_MOBS = (1002, 1113, 1031, 1242)
CHASE_RIDER = {"job": 13, "sex": 1, "hair": 2, "hair_color": 0, "weapon": 5}   # Cavaleiro no Peco Peco, lança
LANCE_POSE = 4            # a pose "em guarda" do .act de jogador: a arma aparece (andando, o jogo não desenha a arma)
# as cenas de luta dos cartões de dano: o Mestre (Champion) com soqueira quando quem grava não é de uma classe de punho
FIGHTER = {"job": 4016, "sex": 1, "hair": 6, "hair_color": 0, "weapon": 12}
CAST, ATK1, ATK2, ATK3 = 12, 5, 10, 11      # ações do .act de jogador: conjurando e os três ataques
FIGHT_ACTS = {"combo": (ATK2, ATK3), "heavy": (CAST, ATK1), "asura": (CAST, ATK1), "boss_down": (ATK2, ATK3, ATK1)}
BOSS_FALL_S = 3.4         # "Chefe derrotado": o golpe final, o chefe cai e vem o confete
FIGHT_DUMMY = 1002        # o alvo quando o monstro da sessão não tem desenho: um Poring
# o palco: nas cenas com personagens o texto sobe e eles ficam numa faixa no pé do cartão (não passam por cima das
# linhas); acabada a animação, ela recolhe em STAGE_FOLD_S e as linhas voltam
SCENE_FX = ("combo", "heavy", "asura", "boss_down", "chase", "jabs", "one_punch", "deck", "mvp_card")
STAGE_H = 50              # altura do palco (pixels, no zoom 1)
STAGE_HS = {"mvp_card": 64, "deck": 58}   # a carta de MVP e o Coringa (uma carta gigante) pedem palco mais alto
STAGE_FOLD_S = 0.5
# "Mão de cartas": o Coringa do jogo embaralha (as metades do baralho se intercalam) e distribui as cartas da sessão
# num leque, cada uma virando no ar até mostrar a ilustração dela (do data.grf; sem o jogo, cartas desenhadas)
JOKER_MOB = 1131
DECK_SHOW = 7             # cartas no leque (as que mais vieram primeiro); com mais, a última leva um "+N"
DECK_CARD = (27, 36)      # tamanho das cartas do leque (zoom 1)
DECK_SHUFFLE = (0.35, 2.0)   # o embaralhar...
DECK_DEAL = (2.0, 4.4)       # ...e o distribuir (s do começo da animação)
CARD_BACK = ("#5b1a2e", "#fbbf24", "#2a0a14")   # o verso das cartas: vinho, filete dourado, sombra
# "Carta de MVP": por cima de tudo, o cartão escurece, um facho dourado desce e o MVP que deixou a carta cai nele; a
# carta sobe girando e se revela (MVP_BIG) com um clarão e raios; depois desce para o palco (MVP_SMALL), onde fica com
# os raios girando, o brilho holográfico passando por ela e fogos dos dois lados
MVP_BIG = (66, 88)
MVP_SMALL = (40, 53)
MVP_FLIPS = (0.14, 0.32, 0.5, 0.68, 0.84, 1.0)   # larguras montadas da carta girando (fração da largura)
MVP_SPIN = (1.0, 2.15)    # a carta gira subindo...
MVP_REVEAL_S = 2.75       # ...a revelação cobre o cartão até aqui...
MVP_LAND_S = 3.35         # ...e a carta desce para o palco até aqui
MVP_GOLD = ("#fbbf24", "#fde68a", "#ffffff", "#f59e0b")
CRIT_TINT, SHOT_TINT = (255, 228, 60), (255, 160, 48)   # números amarelos (crítico) e laranja (one shot)
STAR_JOBS = {4047, 4048, 4239, 4241, 4243, 4244, 4302, 4316}   # a linha estelar: estrelinhas no lugar das esferas
BIG_PART = (1.6, 2.5)     # peça maior que isto (altura, largura) vezes o corpo fica fora da cena (chapéu-aura etc.)
CHASE_COLORS = {1002: "#f9a8d4", 1113: "#fdba74", 1031: "#86efac", 1242: "#a5b4fc"}
# o punho de monge: pele, sombra da pele, contorno, faixa, sombra da faixa, contorno da faixa, conta do rosário
FIST = ("#f6d3b3", "#dfa983", "#6b4226", "#f6f0e4", "#d8cfbf", "#8a7f6e", "#9a3412")
GLASS_BG = "#1b2433"      # o fundo do cartão translúcido do "Intocável"
REC_OFF_S = 45.0          # jogo aberto e nada gravando há esse tempo: lembrete de gravação desligada
GAME_CHECK_S = 5.0        # de quanto em quanto tempo olha se o jogo está aberto
SIZE_NAMES = {"S": "pequeno", "M": "médio", "L": "grande"}
# Padrão único dos cartões (chefe mudou, mecânica, fim da luta), no formato do resumo da morte: moldura e título
# na cor da gravidade, desenho do chefe no alto e linhas centradas. Todos ocupam a mesma área do widget.
SEV_COLORS = {"grave": "#ef4444", "atencao": "#f59e0b", "bom": "#22c55e", "info": "#38bdf8"}
CARD_BG, CARD_DIM, CARD_WHITE = "#14161c", "#a3a8b5", "#ffffff"
# avisos de mecânica: (título, gravidade, [(linha, cor ou None)]); traduzidos na hora de desenhar
MECH_CARDS = {
    "maxpain_on": ("Dor Máxima ativa", "grave", [("Segure os golpes grandes", "#f87171"),
                                                 ("Ela devolve parte de cada golpe", None)]),
    "maxpain_off": ("Dor Máxima acabou", "bom", [("Pode soltar os golpes grandes", "#4ade80")]),
    "defense": ("modo defesa", "atencao", [("O dano quase não entra (99%)", None)]),
    "relief": ("Aliviar muito alto", "grave", []),        # as linhas (Almas ativas, redução) são montadas na hora
    "def_break": ("a defesa caiu", "bom", [("5 s de dano total: solte tudo", "#4ade80")]),
}
DEATH_RED = "#ef4444"
DEATH_CARD_BG = "#1f0606"   # cartão escuro no meio do widget
# título do resumo a cada morte no mesmo encontro (1ª, 2ª, ...); a última vale dali em diante, com o número
DEATH_TITLES = [_("VOCÊ MORREU"), _("MORREU DE NOVO"), _("DE NOVO?!"), _("MELHORE"), _("JÁ É HÁBITO"),
                _("O CHÃO TE CONHECE"), _("SALVOU NA KAFRA?"), _("MODO TAPETE ATIVADO"), _("%d MORTES. RESPEITO.")]
DEATH_DIM = 0.55            # o widget escurece (nas cores do tema) enquanto o resumo da morte aparece
# cor de cada propriedade de ataque no resumo da morte
ELEMENT_COLORS = analysis.ELEMENT_COLORS

THEMES = {
    "Grafite":    dict(bg="#1e1f24", btn="#2d2f37", fg="#f2f3f5", muted="#8b8f99", accent="#5b9cff", live="#ff5c5c"),
    "Meia-noite": dict(bg="#0f1729", btn="#1c2742", fg="#e8eefc", muted="#7d8bb0", accent="#38bdf8", live="#7dd3fc"),
    "Roxo":       dict(bg="#1d1430", btn="#2e2249", fg="#f3ecff", muted="#9a8bbd", accent="#a78bfa", live="#e879f9"),
    "Floresta":   dict(bg="#0f1f17", btn="#1c3427", fg="#e9f7ee", muted="#7fa58e", accent="#34d399", live="#bef264"),
    "Oceano":     dict(bg="#0b2129", btn="#153641", fg="#e6f6f8", muted="#79a3ab", accent="#2dd4bf", live="#67e8f9"),
    "Vinho":      dict(bg="#2a0f1a", btn="#421b2c", fg="#fdeef3", muted="#b58799", accent="#f472b6", live="#fb7185"),
    "Âmbar":      dict(bg="#24180a", btn="#3b2911", fg="#fff4e3", muted="#b39a78", accent="#f59e0b", live="#fde047"),
    "Neon":       dict(bg="#07070b", btn="#17171f", fg="#f5f5ff", muted="#7a7a99", accent="#22ff88", live="#ff2bd6"),
    "Claro":      dict(bg="#f6f7f9", btn="#e3e6eb", fg="#1d2129", muted="#6b7280", accent="#2563eb", live="#ef4444"),
}

SIZES = [(0.8, _("Pequeno")), (1.0, _("Médio")), (1.3, _("Grande")), (1.7, _("Muito grande"))]
ALPHAS = [1.0, 0.9, 0.8, 0.7, 0.6, 0.5]
ROW_CHOICES = [4, 6, 8, 10, 12]
WIDTHS = [(260, _("estreita")), (300, _("normal")), (380, _("larga")), (480, _("muito larga"))]
GAP_CHOICES = [(5, _("5 segundos sem dano")), (10, _("10 segundos sem dano")), (15, _("15 segundos sem dano")),
               (30, _("30 segundos sem dano")), (60, _("1 minuto sem dano"))]
XP_AGAIN_S = 15.0             # o jogo completa o cabeçalho da gravação ~9 s depois de ela começar
XP_LINK_S = 60.0              # a gravação nova que fica pronta até 1 min depois continua o ritmo da anterior
TARGET_CHOICES = [("all", _("Todos os monstros")), ("mvp", _("Só MVPs e bonecos de treino"))]
HINTS = {
    "pin": _("Fixar sempre por cima das outras janelas"), "chart": _("Análise completa (abre outra janela)"),
    "shot": _("Copiar a imagem do widget (cole com Ctrl+V)"),
    "summary": _("Clique: abrir o Dedo Duro · botão direito: desligar o resumo da luta"),
    "session": _("Clique: abrir a análise · botão direito: fechar, escolher o que mostrar ou desligar"),
    "more": _("Opções"), "min": _("Minimizar"), "close": _("Fechar o medidor"), "reset": _("Zerar: começa a contar de novo"),
    "view": _("Escolher o que mostrar: tudo ou uma luta"), "prev": _("Luta anterior"), "next": _("Próxima luta"),
    "group": _("Dano de cada jogador"), "skills": _("O seu dano por skill"), "targets": _("Em quem você bateu"),
    "drops": _("Itens que você pegou"), "xp": _("XP estimada dos seus abates e seu nível"),
    "grip": _("Arraste para mudar a largura e o número de linhas"),
    "where": _("Onde quem grava está (mapa e coordenadas). Clique para copiar o /navi"),
    "pinbar": _("Informação fixada · botão direito para desafixar"),
    "row": _("Botão direito: fixar no widget, ocultar..."),
    "death": _("Clique: fechar · botão direito: desligar o resumo da morte"),
    "bosscard": _("Clique: fechar · botão direito: desligar o aviso do chefe"),
    "tracker": _("Efeito acompanhado · botão direito: como mostrar ou parar de acompanhar"),
    "fxcard": _("Clique: fechar até o efeito acabar · botão direito: como mostrar"),
}
# o que dá para fixar na faixa abaixo das abas (além dos itens da aba Drops)
PIN_STATS = [("xp_min", _("XP por minuto")), ("xp_hour", _("XP por hora")), ("xp_total", _("XP estimada")),
             ("xp_eta", _("Até o próximo nível")), ("kills", _("Abates")), ("level", _("Nível"))]
TONE_NAMES = {"grave": "Grave", "medio": "Médio", "agudo": "Agudo", "bem agudo": "Bem agudo"}
PIN_LABELS = {"xp_min": _("XP/min"), "xp_hour": _("XP/h"), "xp_total": _("XP"), "xp_eta": _("Próx. nível"),
              "kills": _("Abates"), "level": _("Nível")}
TABS = [("group", _("Grupo")), ("skills", _("Skills")), ("targets", _("Alvos")), ("drops", _("Drops")),
        ("xp", _("XP"))]

ICONS = {
    "pin_on": ("\uE840", "📌"), "pin_off": ("\uE718", "📌"), "more": ("\uE712", "⋯"),
    "min": ("\uE921", "–"), "close": ("\uE8BB", "✕"), "reset": ("\uE72C", "↻"),
    "prev": ("\uE76B", "‹"), "next": ("\uE76C", "›"), "file": ("\uE8E5", "📂"),
    "chart": ("\uE9D2", "📊"),
    "where": ("\uE707", "📍"),
    "shot": ("\uE722", "📷"),
}

CONFIG_VERSION = 3
DEFAULTS = {
    "theme": "Grafite", "scale": 1.0, "alpha": 0.92, "pinned": True,
    "rows": 6, "gap_s": 15, "tab": "group", "session": True, "show_pct": False,
    "rate": "combat",      # DPS: "combat" = dano / tempo da luta; "active" = dano / tempo em que cada um bateu
    "folder": None, "x": None, "y": None, "v": CONFIG_VERSION, "width": BASE_W,
    "an_geometry": None, "an_zoomed": False, "an_tab": 0, "an_zoom": 1.0,
    "auto_tests": True, "alert_buffs": True, "alert_death": True, "alert_fusion": True, "alert_miracle": True, "miracle_sound": True,
    "miracle_volume": 40,  # volume do som do Milagre (%)
    "targets": "all",
    "lang": None,          # None = idioma do Windows
    "xp_corr": {},         # {personagem: {"samples": [[XP real ÷ lista, XP real, quando, arquivo#trecho, mapa]]}}
    "xp_spot": {},         # {mapa: {"pct", "when", "auto"}} mapas em spotlight (XP dos monstros × 1 + pct/100)
    "looks": {},           # {nome: look} guardados na aba Visuais (classe, sexo, cabelo, cores e os quatro visuais)
    "vis_ground": "",      # o chão da prévia na aba Visuais ("" = o primeiro terreno do jogo)
    "xp_levels": {},       # {classe: {nível: XP do nível}} visto no começo das gravações
    "xp_bonuses": {},      # {bônus: {"on", "pct"}} da lista de bônus de XP (xp.BONUSES)
    "xp_mode": "auto",     # "auto" (lista + correção medida + evento deduzido), "lista", "medido" ou "fixo"
    "xp_fixed": None,      # bônus fixo (%) do modo "fixo"
    "xp_manual_last": {},  # {personagem: % do último manual que o jogo mandou} (para o manual já ativo no começo)
    "xp_quests": {},       # {missão: {"base": XP sem bônus, "level"}} aprendido de trechos com XP exata
    "xp_event_off": [],    # itens de evento cujo bônus "[Durante o Evento]" não vale mais
    "drop_favs": [],       # itens favoritos (ficam no topo da aba Drops)
    "drop_hidden": [],     # itens que a pessoa ocultou para sempre (somem das listas de drops)
    "drop_colors": {},     # {categoria: "#rrggbb" ou ""} cores dos drops por categoria (itemkind)
    "pins": [],            # informações fixadas na faixa abaixo das abas (até 2): "xp_min", "item:984"...
    "fusion_sound": False,  # som curto quando o HP fica baixo com a União
    "fusion_volume": 40,
    "death_card": True,     # quando você morre, o widget mostra por 10 s o que te matou
    "alert_boss": True,     # cartão de 5 s: o chefe trocou de propriedade/tamanho, ou mecânica (Dor Máxima, defesa)
    "fight_summary": True,  # no fim da luta contra chefe, as principais conclusões do Dedo Duro por alguns segundos
    "session_card": True,   # quando a gravação para, o resumo da sessão com o que a pessoa escolheu (aba Cartões)
    "session_fields": list(session.DEFAULT),  # o que o resumo da sessão mostra (session.FIELDS), na ordem do cartão
    "session_anim": True,   # a animação do destaque do resumo da sessão (confete, moedinhas, as cenas de luta...)
    # (até a 1.11.0 estes três ficavam fora daqui: eram gravados, mas não voltavam ao abrir o programa)
    "session_hl_off": [],   # os destaques desligados na aba Cartões (session.hl_chosen)
    "session_records": {},  # os recordes de cada personagem ("Recorde pessoal": session.update_records)
    "ping_last_char": None,  # o último personagem visto (itens marcados "só neste personagem" sem gravação aberta)
    "alert_rec": True,      # lembrar quando o jogo está aberto e nenhum replay está sendo gravado
    "rec_sound": False,     # ...com um som curto (uma vez)
    "copy_hide_names": False,   # "copiar imagem" troca os nomes dos jogadores pela classe
    "ping_items": [],       # itens marcados para aviso: quando um cai, o widget mostra onde e toca um som curto
    "ping_sound": True,     # ...com o som (sem item marcado, nada toca)
    "ping_volume": 40,
    "ping_tone": itemping.DEFAULT_TONE,   # tom do som: "grave", "medio", "agudo" ou "bem agudo"
    "ping_snd": {},         # som de cada item marcado ({"4001": "sino" ou "file:moeda.wav"}); sem som = o padrão
    "sound_folder": "",     # pasta com os sons da pessoa (.wav e .mp3) para os efeitos e os itens marcados
    "ping_keep": "all",     # itens marcados valem: "all" (todos os personagens), "char" (cada um a sua lista) ou
                            # "session" (só até fechar o programa)
    "ping_chars": {},       # {personagem: [itens]} quando cada personagem tem a sua lista
    "cards_off": [],        # cartões do programa desligados no gerenciador de cartões (cards.SYSTEM)
    "trackers": [],         # efeitos acompanhados no widget: [{"kind": "status" | "area", "id", "where"}]
    "tracker_rows": cards.DEFAULT_ROWS,   # quantos contadores aparecem ao mesmo tempo
    "tracker_flash": True,  # o contador pisca "acabou" por alguns segundos
    "tracker_sound": False,  # ...com um som curto
    "tracker_volume": 40,
}


# ---------------------------------------------------------------- utilidades

def short_path(path, keep=2):
    """C:\Gravity\Ragnarok\Replay -> …\Ragnarok\Replay (cabe no widget)."""
    parts = os.path.normpath(path).split(os.sep)
    return path if len(parts) <= keep + 1 else "…" + os.sep + os.sep.join(parts[-keep:])


def _rgb(h):
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in rgb)


def merge_rgba(a, b, dx, dy):
    """Junta a imagem b por cima da a (as duas como sprites.compose devolve: w, h, pixels, x e y da origem), com a
    origem de b em (origem de a + dx, + dy)."""
    w1, h1, p1, ox1, oy1 = a
    w2, h2, p2, ox2, oy2 = b
    x0, y0 = min(-ox1, -ox2 + dx), min(-oy1, -oy2 + dy)
    x1, y1 = max(w1 - ox1, w2 - ox2 + dx), max(h1 - oy1, h2 - oy2 + dy)
    W, H = x1 - x0, y1 - y0
    px = [(0, 0, 0, 0)] * (W * H)
    for wi, hi, pi, oxi, oyi, ddx, ddy in ((w1, h1, p1, ox1, oy1, 0, 0), (w2, h2, p2, ox2, oy2, dx, dy)):
        left, top = -oxi + ddx - x0, -oyi + ddy - y0
        for yy in range(hi):
            row, src = (top + yy) * W + left, yy * wi
            for xx in range(wi):
                r, g, b_, al = pi[src + xx]
                if al == 0:
                    continue
                if al == 255:
                    px[row + xx] = (r, g, b_, 255)
                else:
                    br, bg_, bb, ba = px[row + xx]
                    k = al / 255.0
                    px[row + xx] = (int(r * k + br * (1 - k)), int(g * k + bg_ * (1 - k)), int(b_ * k + bb * (1 - k)),
                                    max(al, ba))
    return W, H, px, -x0, -y0


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return _hex([x + (y - x) * t for x, y in zip(_rgb(a), _rgb(b))])


def luminance(h):
    r, g, b = (v / 255 for v in _rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def on_color(h):
    return "#16181d" if luminance(h) > 0.55 else "#ffffff"


def shade(h, amount):
    return mix(h, "#ffffff" if luminance(h) < 0.5 else "#000000", amount)


_CHIME = {}
CHIME_VOLUMES = (10, 25, 40, 60, 80, 100)


def chime_wav(volume=40):
    """Arpejo curto e brilhante (dó-mi-sol-dó e um brilho no fim), WAV 16 bits mono gerado na hora.
    volume: 0–100 (100 = o volume da 1.2.0, que ficou alto demais)."""
    volume = max(0, min(100, int(volume)))
    if volume in _CHIME:
        return _CHIME[volume]
    import math
    import struct as st
    rate, length = 22050, 1.25
    n = int(rate * length)
    buf = [0.0] * n
    notes = [(1046.5, 0.00, 0.30), (1318.5, 0.08, 0.28), (1568.0, 0.16, 0.26), (2093.0, 0.24, 0.30),
             (2637.0, 0.40, 0.10), (3136.0, 0.46, 0.08), (4186.0, 0.52, 0.06)]
    for freq, start, vol in notes:
        i0 = int(start * rate)
        for i in range(i0, n):
            x = (i - i0) / float(rate)
            env = math.exp(-x * 5.0) * min(1.0, x * 200)       # ataque rápido, cauda que some
            w = 2 * math.pi * freq * x
            buf[i] += vol * env * (math.sin(w) + 0.25 * math.sin(2 * w) + 0.1 * math.sin(3 * w))
    peak = max(abs(v) for v in buf) or 1.0
    data = b"".join(st.pack("<h", int(32767 * 0.55 * volume / 100.0 * v / peak)) for v in buf)
    head = (b"RIFF" + st.pack("<I", 36 + len(data)) + b"WAVEfmt " + st.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + st.pack("<I", len(data)))
    _CHIME[volume] = head + data
    return _CHIME[volume]


def beep_wav(volume=40):
    """Aviso curto (dois toques descendo, ~0,35 s) para HP baixo com a União. WAV 16 bits mono."""
    volume = max(0, min(100, int(volume)))
    key = ("beep", volume)
    if key in _CHIME:
        return _CHIME[key]
    import math
    import struct as st
    rate = 22050
    n = int(rate * 0.36)
    buf = [0.0] * n
    for freq, start, length in ((1318.5, 0.00, 0.14), (987.8, 0.17, 0.17)):
        i0, i1 = int(start * rate), min(n, int((start + length) * rate))
        for i in range(i0, i1):
            x = (i - i0) / float(rate)
            env = min(1.0, x * 400) * min(1.0, (i1 - i) / (rate * 0.03))     # sem estalo no começo e no fim
            w = 2 * math.pi * freq * x
            buf[i] += env * (math.sin(w) + 0.3 * math.sin(2 * w))
    peak = max(abs(v) for v in buf) or 1.0
    data = b"".join(st.pack("<h", int(32767 * 0.5 * volume / 100.0 * v / peak)) for v in buf)
    head = (b"RIFF" + st.pack("<I", 36 + len(data)) + b"WAVEfmt " + st.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
            + b"data" + st.pack("<I", len(data)))
    _CHIME[key] = head + data
    return _CHIME[key]


def play_wav(make, volume=40):
    """Toca um som gerado (make(volume) -> WAV) sem travar o widget (Windows)."""
    if not IS_WIN or volume <= 0:
        return

    def run():
        try:
            import winsound
            winsound.PlaySound(make(volume), winsound.SND_MEMORY | winsound.SND_NODEFAULT)
        except (ImportError, RuntimeError, OSError):
            pass
    threading.Thread(target=run, daemon=True).start()


def play_chime(volume=40):
    """Toca o som do Milagre."""
    play_wav(chime_wav, volume)


def play_beep(volume=40):
    """Toca o aviso da União."""
    play_wav(beep_wav, volume)


def play_ping(volume=40, tone=None):
    """Toca o aviso de item marcado, no tom escolhido."""
    play_wav(lambda v: itemping.wav(v, tone), volume)


SOUND_FOLDER = [""]           # a pasta de sons da pessoa (cfg "sound_folder"), para os sons tocados de qualquer lugar


def sound_name(key):
    """O nome de um som para a tela: os do programa traduzidos; os da pasta, o nome do arquivo."""
    return _(sounds.NAMES[key]) if key in sounds.NAMES else sounds.label(key)


def set_sound_folder(path):
    SOUND_FOLDER[0] = path or ""


def play_sound(voice, volume=40):
    """Toca um dos sons dos efeitos acompanhados e dos itens marcados: voice = (som, tom). Um som da pasta da
    pessoa (WAV da memória, MP3 pelo Windows) que sumiu ou não abre toca o som padrão no lugar."""
    snd, tone = voice
    if sounds.is_custom(snd):
        path = sounds.custom_path(SOUND_FOLDER[0], snd)
        if path and path.lower().endswith(".mp3"):
            play_mp3(path, volume, tone)
            return
        if path:
            play_wav(lambda v: sounds.custom_wav(path, v) or sounds.wav(sounds.DEFAULT, tone, v), volume)
            return
        snd = sounds.DEFAULT
    play_wav(lambda v: sounds.wav(snd, tone, v), volume)


def play_mp3(path, volume=40, tone=None):
    """Toca um MP3 da pasta da pessoa sem travar o widget; se o Windows não abrir, toca o som padrão."""
    if not IS_WIN or volume <= 0:
        return

    def run():
        try:
            if not sounds.play_mp3(path, volume):
                import winsound
                winsound.PlaySound(sounds.wav(sounds.DEFAULT, tone or "medio", volume),
                                   winsound.SND_MEMORY | winsound.SND_NODEFAULT)
        except (ImportError, RuntimeError, OSError):
            pass
    threading.Thread(target=run, daemon=True).start()


def round_rect_pts(x1, y1, x2, y2, r):
    r = max(0.0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return [x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y1 + r,
            x2, y2 - r, x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1]


def load_learn(saved=None):
    """O registro de aprendizado, do arquivo dele. Sem o arquivo, vale o que estiver dentro da configuração antiga
    (as versões de teste guardavam lá; a configuração só recarrega as chaves de DEFAULTS e perdia o registro)."""
    try:
        with open(LEARN_PATH, encoding="utf-8") as f:
            lrn = json.load(f)
        if isinstance(lrn, dict):
            return lrn
    except (OSError, ValueError):
        pass
    old = saved.get("xp_learn") if isinstance(saved, dict) else None
    return old if isinstance(old, dict) else {}


def load_config():
    cfg = dict(DEFAULTS)
    saved = None
    try:
        with open(CONFIG_PATH, encoding="utf-8") as f:
            saved = json.load(f)
        if isinstance(saved, dict):
            cfg.update({k: v for k, v in saved.items() if k in DEFAULTS})
            if saved.get("v", 1) < 2:
                # v2: Sessão virou o padrão e a pausa padrão subiu para 15 s
                cfg["session"] = True
                if cfg["gap_s"] in (0, 10):
                    cfg["gap_s"] = 15
            if saved.get("v", 1) < 3 and cfg.get("xp_mode") == "lista":
                # v3: a XP sai de "pela lista" (o padrão antigo, que quase ninguém escolheu) para o automático
                cfg["xp_mode"] = "auto"
            cfg["v"] = CONFIG_VERSION
    except (OSError, ValueError):
        pass
    if cfg["theme"] not in THEMES:
        cfg["theme"] = DEFAULTS["theme"]
    if cfg["tab"] not in dict(TABS):
        cfg["tab"] = "group"
    if cfg["targets"] not in dict(TARGET_CHOICES):
        cfg["targets"] = "all"
    if not cfg["gap_s"]:
        cfg["gap_s"] = 15
    for k, kind in (("session_hl_off", list), ("session_records", dict)):
        v = cfg.get(k)                          # um objeto só desta configuração (não o do DEFAULTS), do tipo certo
        cfg[k] = v if isinstance(v, kind) and v is not DEFAULTS[k] else kind()
    cfg["xp_learn"] = load_learn(saved)
    return cfg


# ---------------------------------------------------------------- Windows

if IS_WIN:
    user32 = ctypes.windll.user32
    user32.GetParent.restype = ctypes.c_void_p
    user32.GetParent.argtypes = [ctypes.c_void_p]
    user32.GetWindowLongW.restype = ctypes.c_long
    user32.GetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.SetWindowLongW.restype = ctypes.c_long
    user32.SetWindowLongW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]
    user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]

    class _POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    user32.MonitorFromPoint.restype = ctypes.c_void_p
    user32.MonitorFromPoint.argtypes = [_POINT, ctypes.c_uint]


def dwm_set(hwnd, attr, value):
    if not IS_WIN or not hwnd:
        return False
    try:
        v = ctypes.c_uint(value)
        return ctypes.windll.dwmapi.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd), attr, ctypes.byref(v), ctypes.sizeof(v)) == 0
    except (OSError, AttributeError):
        return False


# ---------------------------------------------------------------- Tk só na thread principal

_TK_MAIN = threading.main_thread()
_TK_LATER = collections.deque()          # (finalizador original, objeto) que chegaram por outra thread


def _tk_deferred(orig):
    def __del__(self):
        if threading.current_thread() is _TK_MAIN:
            orig(self)
        else:
            _TK_LATER.append((orig, self))   # o objeto fica vivo até a thread principal rodar o finalizador
    __del__.on_main = True
    return __del__


def tk_finalize_on_main(root, every_ms=1000):
    """O coletor de lixo do Python solta uma análise fechada (variáveis, imagens e fontes do Tk) na thread que estiver
    rodando na hora, às vezes uma de segundo plano. Fora da thread principal o Tk não pode ser chamado: a thread fica
    esperando a principal (que pode estar esperando por ela: travaria), ou o finalizador falha e a imagem fica para
    sempre na memória do Tk. Os finalizadores chamados fora da principal ficam para ela, que os roda a cada segundo."""
    for cls in (tk.Variable, tk.Image, tkfont.Font):
        if not getattr(cls.__del__, "on_main", False):
            cls.__del__ = _tk_deferred(cls.__del__)

    def drain():
        while _TK_LATER:
            orig, obj = _TK_LATER.popleft()
            try:
                orig(obj)
            except Exception:  # noqa: BLE001 - o Tk já fechou ou o nome já não existe: nada a soltar
                pass
            obj = None
        try:
            root.after(every_ms, drain)
        except tk.TclError:
            pass
    drain()


# ---------------------------------------------------------------- app

class DpsApp:
    def __init__(self, root, open_path=None):
        self.root = root
        tk_finalize_on_main(root)
        self.cfg = load_config()
        set_sound_folder(self.cfg.get("sound_folder"))
        # o que já está no arquivo do registro (sem o arquivo, a 1ª gravação da configuração cria)
        self.learn_rev = self.cfg["xp_learn"].get("rev") if os.path.exists(LEARN_PATH) else None
        self.learn_check_at = 0.0
        self.watcher = meter.Watcher(self.cfg["folder"], self.gap_ms(), self.cfg["targets"])
        # nomes do jogo no idioma escolhido (da instalação; com o cache leva ~0,1 s, na 1ª vez alguns segundos)
        clientdata.NAMES.load()
        self.names_v = clientdata.NAMES.version
        self.xp_seen = None
        self.xp_again = None                # (gravação que ficou para trás, quando medir a XP dela de novo)
        self.xp_link = None                 # (gravação que ficou para trás, até quando a nova pode continuar dela)
        self.xp_auto_at = 0.0                  # última conferência automática da XP (manual lembrado, evento)
        self.xp_lvl_seen = None                # (gravação, nº de subidas de nível) já conferido
        self.miracle_at = -1e9                 # quando o Milagre ativou (o widget brilha por uns segundos)
        self.press_xy = None
        self.enc_back = 0                   # 0 = encontro atual, 1 = anterior...
        self.drop_scroll = 0                # primeira linha mostrada na aba Drops (roda do mouse)
        self.drop_view = (0, 0, 0)          # (primeira, linhas, total) para a barra de rolagem
        self.session_hidden = set()         # drops ocultos só até fechar o programa
        self.hover = self.pressed = self.drag = self.resize = None
        self.hwnd = None
        self.menu = None
        self.menu_refs = []
        self.last_draw = 0.0
        self.dirty = True
        self.phase = 0
        self.analysis = None
        self.tests = testes.Store(os.path.join(os.path.dirname(CONFIG_PATH), "testes.json"))
        self.tests_seen = set()       # encontros já avaliados para o salvamento automático
        self.tests_file = None        # a gravação que estava aberta na última leitura
        self.tests_left = testes.Left()   # as que ficaram para trás com luta contra o boneco ainda sem salvar
        self.last_autosave = 0.0
        self.alert = None             # (texto, tipo, quando apareceu)
        self.death_card = None        # (resumo da morte, quando apareceu)
        self.boss_card = None         # (o que mudou no chefe, quando apareceu)
        self.summary_card = None      # (resumo do fim da luta, quando apareceu)
        self.session_card = None      # (resumo da sessão que acabou, quando apareceu)
        self.session_waiting = False  # o resumo da sessão está atrás de outro cartão (session_wait)
        self.session_anim = None      # o after() dos quadros extras da animação do resumo da sessão
        self.last_session = None      # o último resumo da sessão (o menu do widget mostra de novo)
        self.live_combat = None       # a gravação que estava sendo escrita (quando ela para, vem o resumo da sessão)
        self.live_done = None         # (gravação, last_change) da que já acabou: só volta a valer se crescer de novo
        self.hold_seen = 0            # vezes que o jogo estava com o arquivo da gravação aberto com ele parado
        self.hold_now = None          # na última pergunta: alguém com o arquivo aberto (None: não deu para saber)
        self.hold_check_at = 0.0      # a última pergunta ao Windows sobre quem está com o arquivo
        self.hold_every = HOLD_CHECK_S
        self.summary_due = None       # (gravação, nº do aviso da morte do chefe) esperando os últimos pacotes
        self.game_on = False          # o jogo está aberto? (olhado a cada 5 s, para o lembrete de gravação)
        self.game_check_at = 0.0
        self.rec_seen_at = time.time()   # última vez em que havia gravação (ou em que o jogo não estava aberto)
        self.rec_warned = False       # o som do lembrete já tocou neste episódio
        self.sprite_photos = {}       # (monstro, largura, altura) -> PhotoImage do sprite
        self.press_target = None
        self.alert_seen = 0
        self._xp_rows = None          # (chave, até quando vale, linhas) da última conta da aba XP
        self.pings = itemping.Tracker()   # itens marcados para aviso: os que caíram e ainda estão no chão
        self.ping_card = None         # (item marcado que caiu e onde, quando apareceu)
        self.ping_played = 0.0
        self.ping_session = None      # itens marcados só até fechar o programa (ping_keep "session")
        self.watch = cards.Watch()    # efeitos acompanhados: o que estava ativo na leitura anterior
        self.watch_for = None
        self.fx_left = {}             # efeitos acompanhados: quanto faltava na leitura anterior (som "antes de acabar")
        self.fx_sound_at = 0.0
        self.tracker_rows = []        # contadores a desenhar no pé das linhas
        self.pinned_fx = {}           # contadores dos efeitos fixados na faixa fixa: chave -> linha
        self.fx_cards = []            # efeitos ativos que a pessoa escolheu ver como cartão
        self.fx_closed = set()        # ...os que ela fechou com um clique (voltam quando o efeito for aplicado de novo)
        self.fx_now = []              # ...os que o cartão mostra neste desenho
        self.tracker_n = 0            # quantos couberam no último desenho

        root.title(_("Replay Master"))
        root.report_callback_exception = self.log_error
        root.overrideredirect(True)
        self.dpi = root.winfo_fpixels("1i") / 96.0
        self.make_fonts()
        ico = os.path.join(RES_DIR, "dpsmeter.ico")
        if IS_WIN and os.path.isfile(ico):
            try:
                root.iconbitmap(default=ico)
            except tk.TclError:
                pass

        self.canvas = tk.Canvas(root, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        c = self.canvas
        c.bind("<ButtonPress-1>", self.on_press)
        c.bind("<B1-Motion>", self.on_drag)
        c.bind("<ButtonRelease-1>", self.on_release)
        c.bind("<Motion>", self.on_motion)
        c.bind("<Leave>", lambda e: self.set_hover(None))
        c.bind("<Button-3>", self.on_right_click)
        c.bind("<MouseWheel>", self.on_wheel)
        root.protocol("WM_DELETE_WINDOW", self.quit)

        w, h = self.size_px()
        x, y = self.initial_pos(w, h)
        root.geometry("%dx%d+%d+%d" % (w, h, x, y))
        root.attributes("-topmost", bool(self.cfg["pinned"]))
        root.attributes("-alpha", float(self.cfg["alpha"]))
        if open_path:
            self.watcher.open(open_path)
        self.draw()
        root.after(10, self.setup_native)
        root.after(50, self.tick)
        if learnfolder.enabled():
            # uma vez só: as gravações que já estavam na pasta, num processo à parte (os replays costumam ser apagados)
            root.after(learnfolder.DELAY_MS, self.learn_folder_start)

    # ------------------------------------------------------------ base

    @property
    def s(self):
        return self.cfg["scale"] * self.dpi

    def gap_ms(self):
        g = self.cfg["gap_s"]
        return int(g * 1000) if g else 10 ** 12

    def base_w(self):
        try:
            return max(MIN_W, min(MAX_W, int(self.cfg.get("width") or BASE_W)))
        except (TypeError, ValueError):
            return BASE_W

    def rows_y0(self):
        """Onde as linhas começam (sem escala): logo abaixo das abas, ou da faixa fixa quando há algo fixado."""
        return ROWS_Y0 + (PIN_H if self.cfg.get("pins") else 0)

    def size_px(self):
        h = self.rows_y0() + self.cfg["rows"] * ROW_H + 6 + FOOT_H
        return int(round(self.base_w() * self.s)), int(round(h * self.s))

    def icon(self, name):
        glyph, fallback = ICONS[name]
        return glyph if self.has_icons else fallback

    def make_fonts(self):
        fams = set(tkfont.families(self.root))

        def pick(*names):
            return next((n for n in names if n in fams), names[-1])

        icon_fam = pick("Segoe Fluent Icons", "Segoe MDL2 Assets")
        self.has_icons = icon_fam in fams
        semi = pick("Segoe UI Semibold", "Segoe UI", "Arial")
        ui = pick("Segoe UI", "Arial")
        nums = pick("Bahnschrift SemiBold", "Bahnschrift", "Segoe UI Semibold", "Arial")
        self.fonts = {
            "big": tkfont.Font(self.root, family=nums),
            "big_s": tkfont.Font(self.root, family=nums),
            "spaced": tkfont.Font(self.root, family=semi),
            "unit": tkfont.Font(self.root, family=semi),
            "title": tkfont.Font(self.root, family=semi),
            "text": tkfont.Font(self.root, family=ui),
            "small": tkfont.Font(self.root, family=ui),
            "num": tkfont.Font(self.root, family=nums),
            "icon": tkfont.Font(self.root, family=icon_fam),
            "tab": tkfont.Font(self.root, family=semi),
        }
        self.size_fonts()

    def size_fonts(self):
        for key, px in FONT_PX.items():
            self.fonts[key].configure(size=-max(MIN_FONT_PX, int(round(px * self.s))))

    def theme(self):
        t = dict(THEMES.get(self.cfg["theme"], THEMES["Grafite"]))
        dc = getattr(self, "death_card", None)
        k = time.time() - dc[1] if dc else -1.0
        if 0 <= k < DEATH_CARD_S:
            # resumo da morte: o widget escurece nas cores do tema (entra rápido, sai nos últimos instantes)
            a = min(1.0, k / 0.25) * min(1.0, (DEATH_CARD_S - k) / 0.6)
            t = {key: val if key == "fg" else mix(val, "#000000", DEATH_DIM * a) for key, val in t.items()}
        t["edge"] = mix(t["bg"], t["fg"], 0.10)
        t["track"] = mix(t["bg"], t["fg"], 0.07)
        t["bar"] = mix(t["bg"], t["muted"], 0.38)
        t["bar_me"] = mix(t["bg"], t["accent"], 0.62)
        k = time.time() - getattr(self, "miracle_at", -1e9)
        if 0 <= k < MIRACLE_FLASH_S:
            # Milagre: o widget brilha em dourado, lilás e branco, apagando aos poucos
            fade = 1.0 - k / MIRACLE_FLASH_S
            star = MIRACLE_COLORS[int(k * 6) % len(MIRACLE_COLORS)]
            t["accent"] = mix(t["accent"], star, 0.35 + 0.65 * fade)
            t["bar_me"] = mix(t["bar_me"], star, 0.75 * fade)
            t["bar"] = mix(t["bar"], "#7c3aed", 0.35 * fade)
            dark = sum(int(t["bg"][i:i + 2], 16) for i in (1, 3, 5)) < 384
            t["bg"] = mix(t["bg"], "#2e1065" if dark else "#fef3c7", 0.55 * fade)
            t["edge"] = mix(t["edge"], "#fbbf24", 0.8 * fade)
        return t

    def initial_pos(self, w, h):
        x, y = self.cfg.get("x"), self.cfg.get("y")
        ok = isinstance(x, int) and isinstance(y, int)
        if ok and IS_WIN:
            ok = bool(user32.MonitorFromPoint(_POINT(x + w // 2, y + h // 2), 0))
        if not ok:
            x = self.root.winfo_screenwidth() - w - int(40 * self.dpi)
            y = int(140 * self.dpi)
        return x, y

    def setup_native(self):
        if not IS_WIN:
            return
        try:
            self.hwnd = int(self.root.wm_frame(), 16)
        except (tk.TclError, ValueError):
            self.hwnd = user32.GetParent(self.root.winfo_id())
        # janela sem moldura, com botão na barra de tarefas, e que não fica ativa ao ser
        # clicada (WS_EX_NOACTIVATE): o teclado continua no jogo
        style = user32.GetWindowLongW(self.hwnd, -20)        # GWL_EXSTYLE
        user32.SetWindowLongW(self.hwnd, -20, (style & ~0x80) | 0x40000 | WS_EX_NOACTIVATE)
        self.root.withdraw()
        self.root.after(10, self.root.deiconify)
        dwm_set(self.hwnd, 33, 2)                            # cantos arredondados (Win 11)
        self.apply_border()

    def apply_border(self):
        if self.hwnd:
            r, g, b = _rgb(self.theme()["edge"])
            dwm_set(self.hwnd, 34, r | (g << 8) | (b << 16))  # DWMWA_BORDER_COLOR

    def save(self):
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            tmp = CONFIG_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({k: v for k, v in self.cfg.items() if k != "xp_learn"}, f, ensure_ascii=False, indent=2)
            os.replace(tmp, CONFIG_PATH)
            # o registro de aprendizado só quando mudou (xp.touch_learn)
            lrn = self.cfg.get("xp_learn")
            if isinstance(lrn, dict) and lrn and lrn.get("rev") != getattr(self, "learn_rev", None):
                tmp = LEARN_PATH + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(lrn, f, ensure_ascii=False, separators=(",", ":"))
                os.replace(tmp, LEARN_PATH)
                self.learn_rev = lrn.get("rev")
        except OSError:
            pass

    def save_position(self):
        self.cfg["x"], self.cfg["y"] = self.root.winfo_x(), self.root.winfo_y()
        self.save()

    def log_error(self, exc, val, tb):
        text = "".join(traceback.format_exception(exc, val, tb))
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(os.path.join(os.path.dirname(CONFIG_PATH), "erros.log"), "a", encoding="utf-8") as f:
                f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + text + "\n")
        except OSError:
            pass
        if sys.stderr:
            sys.stderr.write(text)

    # ------------------------------------------------------------ dados

    def watch_stalls(self):
        """Vigia numa thread: se o laço do widget ficar mais de STALL_S sem rodar (janela "não respondendo"),
        escreve no erros.log o que cada thread estava fazendo. Uma vez por parada; não mexe em mais nada."""
        self.beat = time.monotonic()

        def run():
            told = None
            while True:
                time.sleep(2.0)
                beat = self.beat
                late = time.monotonic() - beat
                if late < STALL_S or told == beat:
                    continue
                told = beat
                if late > STALL_S + 60:          # o computador estava dormindo ou hibernando: não é travamento
                    continue
                try:
                    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
                    with open(os.path.join(os.path.dirname(CONFIG_PATH), "erros.log"), "a", encoding="utf-8") as f:
                        f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + "tela parada há %d s (%s); o que cada thread fazia:\n"
                                % (late, VERSION))
                        f.flush()
                        faulthandler.dump_traceback(file=f, all_threads=True)
                        f.write("\n")
                except (OSError, ValueError, RuntimeError):
                    pass
        threading.Thread(target=run, daemon=True).start()

    def tick(self):
        """Laço do widget: lê o replay, desenha e se reagenda. Um erro em qualquer parte vai para o erros.log, mas
        nunca para o laço (antes, um erro ao desenhar congelava o DPS e os drops)."""
        self.beat = time.monotonic()
        try:
            self.step()
        except Exception:  # noqa: BLE001
            self.log_error(*sys.exc_info())
        finally:
            self.root.after(POLL_MS, self.tick)

    def step(self):
        now = time.time()
        grew_at = self.watcher.last_change       # da gravação que estava aberta até esta leitura
        try:
            if self.watcher.poll(now):
                self.dirty = True
        except Exception:  # noqa: BLE001 - um replay estranho nao pode derrubar o widget
            self.log_error(*sys.exc_info())
        if clientdata.NAMES.version != self.names_v:
            # os nomes dos monstros novos (lidos do próprio jogo) ficaram prontos
            self.names_v = clientdata.NAMES.version
            self.dirty = True
            if self.analysis is not None:
                self.analysis.refresh(force=True)
        f = self.watcher.file
        if f is not self.tests_file:
            # o widget passou para outra gravação (ou a pessoa abriu um replay): a que ficou para trás segue sendo
            # lida até parar, para a luta contra o boneco que ainda não tinha sido salva não se perder
            if self.cfg["auto_tests"]:
                self.tests_left.add(self.tests_file, grew_at)
            self.tests_file = f
        cur = f.combat if f is not None and f.ready else None
        if cur is not self.xp_seen:
            prev, self.xp_seen = self.xp_seen, cur
            if prev is not None and prev is self.live_combat:
                self.end_live(prev, now)          # começou outra gravação: a que estava sendo escrita acabou
            if prev is not None:
                self.xp_calibrate(prev)
                # a gravação nova acabou de começar e o começo dela (com a XP) ainda não dá para ler: mede de novo
                # daqui a pouco, senão a XP exata "até a gravação seguinte" nunca era guardada ao vivo
                self.xp_again = (prev, now + XP_AGAIN_S)
                self.xp_link = (prev, now + XP_LINK_S)
            if cur is not None and self.xp_link is not None:
                # reiniciou a gravação (para calibrar): a nova segue o ritmo da anterior, sem outros 10 min de
                # "calculando…" no "Até o próximo nível" (xp.carry_from confere o personagem e o intervalo)
                self.xp_link_now(cur, self.xp_link[0])
        if self.xp_again is not None and now >= self.xp_again[1]:
            prev, self.xp_again = self.xp_again[0], None
            self.xp_calibrate(prev)
            if self.xp_seen is not None:
                self.xp_link_now(self.xp_seen, prev)       # de novo, com a medida nova
        if self.xp_link is not None and now >= self.xp_link[1]:
            self.xp_link = None                      # a gravação anterior não fica presa na memória
        if now >= self.learn_check_at:
            # a leitura das gravações que já estavam na pasta terminou? (um arquivo: olhar custa quase nada)
            self.learn_check_at = now + 10.0
            self.learn_folder_take()
        if f is not None and f.ready:
            f.combat.finished = not self.watcher.recording(now)
            self.check_session(f, now)
            self.check_alerts(f, now)
            self.check_pings(f.combat, now)
            self.check_trackers(f.combat, now)
        self.session_wait(now)
        if f is not None and f.ready:
            if now - self.xp_auto_at >= 3.0:
                self.xp_auto_at = now
                self.xp_auto(f.combat)
        if now - self.last_autosave >= 2.0:
            self.last_autosave = now
            if not self.cfg["auto_tests"]:
                self.tests_left.items = []
            else:
                try:
                    self.tests_left.step(self.tests, self.tests_seen, now)
                    if f is not None and f.ready:
                        testes.auto_save(self.tests, f, self.tests_seen)
                except Exception:  # noqa: BLE001
                    self.log_error(*sys.exc_info())
        self.phase = (self.phase + 1) % 8
        self.check_recording(now)
        if (now - self.miracle_at < MIRACLE_FLASH_S + 0.3 or self.death_card or self.boss_card
                or self.summary_card or self.ping_card):     # o resumo da sessão fica no redesenho de 1 s
            self.dirty = True
        if self.dirty or now - self.last_draw >= 1.0:
            try:
                self.draw()
            except Exception:  # noqa: BLE001 - um erro ao desenhar não pode parar a leitura do replay
                self.log_error(*sys.exc_info())
        if self.analysis is not None and not (self.drag or self.resize):
            # arrastando ou redimensionando o widget, a análise espera: refazê-la prende a janela por um instante
            try:
                self.analysis.tick()
            except Exception:  # noqa: BLE001
                self.log_error(*sys.exc_info())

    def open_report(self):
        """O relatório do que o programa aprendeu (XP e drops): o jogador lê, copia ou salva e manda se quiser."""
        import ui_report
        t = self.t
        ui_report.open_report(self.root, self.cfg, dict(panel=t["bg"], tile=t["track"], fg=t["fg"], muted=t["muted"]),
                              self.fonts["small"], self.learn_folder_status)

    def learn_folder_start(self):
        """Uma vez só: lê num processo à parte as gravações que já estavam na pasta (learnfolder). Se uma leitura
        anterior terminou com o programa fechado, só junta o resultado."""
        try:
            cfg_dir = os.path.dirname(CONFIG_PATH)
            if self.learn_folder_take():
                return
            lrn = xp._learn(self.cfg)
            if not self.watcher.folders or not learnfolder.should_start(lrn, cfg_dir):
                return
            lrn["folder_tries"] = int(lrn.get("folder_tries") or 0) + 1
            xp.touch_learn(lrn)
            self.save()                              # a pasta da configuração existe antes do processo escrever nela
            learnfolder.start(cfg_dir, self.watcher.folders)
        except Exception:  # noqa: BLE001 - é um extra: não pode atrapalhar o widget
            self.log_error(*sys.exc_info())

    def learn_folder_take(self):
        """Junta o que a leitura da pasta aprendeu, quando ela termina (o relatório aberto se refaz). True se juntou."""
        try:
            if not learnfolder.take(self.cfg, os.path.dirname(CONFIG_PATH)):
                return False
            self.save()
            import ui_report
            ui_report.refresh()
            return True
        except Exception:  # noqa: BLE001
            self.log_error(*sys.exc_info())
            return False

    def learn_folder_status(self):
        """Linha da janela do relatório enquanto a pasta está sendo lida ("" fora disso)."""
        p = learnfolder.progress(os.path.dirname(CONFIG_PATH))
        if p is None:
            return ""
        return _("Lendo as gravações que já estavam na pasta (só desta vez): %d de %d. Pode continuar jogando; o "
                 "relatório se completa sozinho.") % p

    def xp_link_now(self, cur, prev):
        """Liga a gravação nova à anterior (xp.carry_from): o ritmo dos últimos minutos de farm segue valendo."""
        try:
            if xp.carry_from(cur, prev, self.cfg):
                self.dirty = True
        except Exception:  # noqa: BLE001 - é um extra: não pode parar a leitura
            self.log_error(*sys.exc_info())

    def xp_calibrate(self, c):
        """Fator de XP do personagem: XP exata até a próxima gravação ÷ XP estimada dos abates desta. No modo
        automático a mesma medida confere o evento do servidor e aprende a XP das missões."""
        try:
            def sig():
                # o registro de aprendizado (drops, monstros sem XP) muda até em gravação sem XP exata
                return json.dumps([self.cfg.get(k) for k in ("xp_bonuses", "xp_quests", "xp_manual_last")]
                                  + [(self.cfg.get("xp_learn") or {}).get("rev")], sort_keys=True)
            before = sig()
            server = xp.settings(self.cfg)["server"]
            done = xp.calibrate(c, self.cfg, meter.xp_after)
            now = xp.settings(self.cfg)["server"]
            if (server["on"], server["pct"]) != (now["on"], now["pct"]):
                self.xp_server_found(now["pct"] if now["on"] else 0)
            after = sig()
            if done or before != after:
                self.save()
                self.dirty = True
        except Exception:  # noqa: BLE001
            self.log_error(*sys.exc_info())

    def xp_auto(self, c):
        """Automático da XP durante a gravação: guarda o % do manual que o jogo mandou e, a cada subida de nível
        (XP exata), confere o evento do servidor e aprende a recompensa das missões do nível que fechou."""
        try:
            changed = xp.remember_manual(c, self.cfg)
            sig = (id(c), len(c.level_ups))
            if sig != self.xp_lvl_seen and xp.gear_ready():
                self.xp_lvl_seen = sig
                if c.level_ups:
                    changed = self.xp_server_found(xp.detect_server(c, self.cfg)) or changed
                    changed = xp.learn_levels(c, self.cfg) or changed
            if changed:
                self.save()
                self.dirty = True
        except Exception:  # noqa: BLE001
            self.log_error(*sys.exc_info())

    def xp_server_found(self, pct):
        """Avisa no rodapé que o evento do servidor foi deduzido da XP exata (pct None = nada mudou)."""
        if pct is None:
            return False
        text = (_("XP: evento do servidor de +%d%% detectado e marcado") % pct) if pct else _(
            "XP: sem evento do servidor agora (desmarcado pela XP exata)")
        self.alert = (text, "info", time.time())
        if self.analysis is not None:
            self.analysis.xp_loaded = False       # a lista de bônus da análise relê o que mudou
        return True

    def check_alerts(self, f, now):
        """Mostra no rodapé o aviso mais novo (buff que acabou, morte) por alguns segundos."""
        c = f.combat
        floor = max(f.alert_floor, self.alert_seen)
        for seq, _t, kind, text in c.alerts:
            if seq <= floor:
                continue
            self.alert_seen = seq
            if kind == "death" and self.cfg["death_card"]:
                self.show_death_card(c, seq, now)
            if kind == "boss" and self.cfg.get("alert_boss", True):
                self.show_boss_card(c, seq, now)
            if kind == "bossdead" and self.cfg.get("fight_summary", True):
                self.summary_due = (c, seq)
            if ((kind == "buff" and self.cfg["alert_buffs"]) or (kind == "death" and self.cfg["alert_death"])
                    or (kind == "fusion" and self.cfg["alert_fusion"])
                    or (kind == "boss" and self.cfg.get("alert_boss", True))
                    or (kind == "miracle" and self.cfg["alert_miracle"])):
                self.alert = (text, kind, now)
                self.dirty = True
                if kind == "miracle":
                    self.miracle_at = now
                    if self.cfg["miracle_sound"]:
                        play_chime(self.cfg["miracle_volume"])
                elif kind == "fusion" and self.cfg["fusion_sound"]:
                    play_beep(self.cfg["fusion_volume"])
        if self.alert and now - self.alert[2] > (MIRACLE_FLASH_S if self.alert[1] == "miracle" else ALERT_S):
            self.alert = None
            self.dirty = True
        if self.death_card and now - self.death_card[1] > DEATH_CARD_S:
            self.death_card = None
            self.dirty = True
        if self.boss_card and now - self.boss_card[1] > BOSS_CARD_S:
            self.boss_card = None
            self.dirty = True
        if self.summary_card and now - self.summary_card[1] > SUMMARY_CARD_S:
            self.summary_card = None
            self.dirty = True
        self.check_summary(c, now)

    def check_trackers(self, c, now):
        """Efeitos acompanhados (gerenciador de cartões): o que está ativo agora vira contador no pé das linhas.
        Só durante a gravação: num replay antigo o que ficou ligado no fim não está mais acontecendo."""
        try:
            trackers = cards.tracked(self.cfg)
            if not trackers or c.finished:
                if self.tracker_rows or self.pinned_fx or self.fx_cards:
                    self.tracker_rows, self.pinned_fx, self.fx_cards = [], {}, []
                    self.dirty = True
                self.watch.reset()
                self.fx_left = {}
                return
            if c is not self.watch_for:
                self.watch.reset()
                self.fx_left = {}
                self.watch_for = c
            rows, ended = self.watch.update(cards.live(c, trackers), now, self.cfg.get("tracker_flash", True))
            # o som de cada efeito: ao começar, ao acabar ou alguns segundos antes (um por vez, sem embolar)
            tones = cards.sounds(self.cfg, trackers, self.watch, ended, self.fx_left)
            if tones and now - self.fx_sound_at >= cards.SOUND_GAP_S:
                self.fx_sound_at = now
                if tones[0] is None:
                    play_beep(self.cfg.get("tracker_volume", 40))
                else:
                    play_sound(tones[0], self.cfg.get("tracker_volume", 40))
            if rows or self.tracker_rows or self.pinned_fx or self.fx_cards:
                self.dirty = True                 # o contador anda a cada leitura
            # cada efeito aparece como a pessoa escolheu: fixado na faixa fixa (à vista mesmo com um cartão),
            # cartão enquanto durar, ou contador no pé das linhas
            fixed = {p[3:] for p in (self.cfg.get("pins") or []) if p.startswith("fx:")}
            show = {"%s:%d" % (t["kind"], t["id"]): t["show"] for t in trackers}
            self.fx_closed &= {r["key"] for r in rows}        # acabou: na próxima vez o cartão volta
            self.pinned_fx = {r["key"]: r for r in rows if r["key"] in fixed}
            rest = [r for r in rows if r["key"] not in fixed]
            self.fx_cards = [r for r in rest if show.get(r["key"]) == "card"]
            self.tracker_rows = [r for r in rest if show.get(r["key"]) != "card" or r["key"] in self.fx_closed]
            mob = next((r["mob"] for r in self.fx_cards if r.get("mob")), None)
            if mob:                               # o desenho do monstro do cartão carrega em outra thread
                sprites.MONSTERS.start(clientdata.NAMES.grf)
                sprites.MONSTERS.image(("mob", mob))
        except Exception:  # noqa: BLE001 - os contadores são um extra
            self.log_error(*sys.exc_info())

    def tracker_count(self):
        """Quantos contadores cabem: até o escolhido, deixando pelo menos duas linhas da lista à vista."""
        limit = min(int(self.cfg.get("tracker_rows") or cards.DEFAULT_ROWS), max(1, self.cfg["rows"] - 2))
        return min(len(self.tracker_rows), limit)

    def draw_trackers(self):
        """Contadores dos efeitos acompanhados, no pé das linhas: o nome, em quem está e o tempo que falta, com a
        barra esvaziando. Sem duração conhecida mostra há quanto tempo está ativo. Quando acaba, pisca "acabou"."""
        n = self.tracker_n = self.tracker_count()
        if not n:
            return
        c, s, W, t = self.canvas, self.s, self.W, self.t
        rows = self.tracker_rows[:n]
        bottom = (self.rows_y0() + self.cfg["rows"] * ROW_H - 2) * s
        top = bottom - n * ROW_H * s
        x0, x1 = 8 * s, W - 8 * s
        c.create_rectangle(0, top - 3 * s, W, bottom + 1 * s, fill=t["bg"], outline="")
        c.create_line(x0, top - 2 * s, x1, top - 2 * s, fill=mix(t["bg"], t["muted"], 0.35))
        for i, r in enumerate(rows):
            y0 = top + i * ROW_H * s
            y1 = y0 + (ROW_H - 3) * s
            ended = r.get("ended") is not None
            left = r.get("left")
            if ended:
                col = "#ef4444"
            elif left is not None and left < 3000:
                col = "#f59e0b"
            else:
                col = t["accent"] if r["where"] == "target" else "#22c55e"
            frac = 1.0
            if ended:
                frac = 1.0 if self.phase < 4 else 0.0          # pisca
            elif left is not None and r.get("total"):
                frac = max(0.0, min(1.0, left / float(r["total"])))
            c.create_polygon(round_rect_pts(x0, y0, x1, y1, 4 * s), smooth=True, fill=mix(t["bg"], col, 0.13),
                             outline="")
            if frac > 0.01:
                c.create_polygon(round_rect_pts(x0, y0, x0 + max(8 * s, (x1 - x0) * frac), y1, 4 * s), smooth=True,
                                 fill=mix(t["bg"], col, 0.36), outline="")
            cy = (y0 + y1) / 2
            tid = c.create_text(x1 - 7 * s, cy, anchor="e", text=cards.time_text(r), font=self.fonts["num"],
                                fill=self.readable(col) if (ended or (left is not None and left < 3000)) else t["fg"])
            label = cards.short_name(r["name"]) + ((" · " + r["target"]) if r.get("target") else "")
            nid = c.create_text(x0 + 7 * s, cy, anchor="w", text=label, font=self.fonts["text"], fill=t["fg"])
            self.clip_text(nid, label, c.bbox(tid)[0] - 6 * s)
            self.hits.append((("tracker", r["key"]), (x0, y0, x1, y1)))

    def fx_card_rows(self):
        """Os efeitos ativos escolhidos para aparecer como cartão, menos os que a pessoa fechou até acabarem."""
        return [r for r in self.fx_cards if r["key"] not in self.fx_closed]

    def draw_fx_card(self):
        """Cartão dos efeitos acompanhados (de quem escolheu vê-los como cartão): no modelo dos outros cartões, fica
        enquanto o efeito durar, com o tempo que falta no lugar da contagem. O que acaba antes vai no título; os
        outros efeitos ativos (inclusive os contadores, que o cartão cobre) vêm nas linhas. Quando acaba, o cartão
        fica vermelho por uns segundos."""
        rows = self.fx_now
        if not rows:
            return
        first = rows[0]
        ended = first.get("ended") is not None
        left = first.get("left")
        name = cards.short_name(first["name"])
        if ended:
            sev, title = "grave", _("%s acabou") % name
        else:
            sev = "atencao" if left is not None and left < 3000 else ("info" if first["where"] == "target" else "bom")
            title = name
        lines = []
        if first.get("target"):
            lines.append(((_("em %s") if first["where"] == "target" else _("de %s")) % first["target"], CARD_DIM))
        if not ended:
            lines.append(((_("faltam %s") % cards.time_text(first)) if left is not None else cards.time_text(first),
                          CARD_WHITE))
        for r in rows[1:] + self.tracker_rows:
            gone = r.get("ended") is not None
            soon = r.get("left") is not None and r["left"] < 3000
            lines.append(("%s · %s" % (cards.short_name(r["name"]), cards.time_text(r)),
                          "#f87171" if gone else ("#fbbf24" if soon else CARD_WHITE)))
        frac = 1.0
        if ended:
            frac = 1.0 if self.phase < 4 else 0.0              # pisca
        elif left is not None and first.get("total"):
            frac = max(0.0, min(1.0, left / float(first["total"])))
        self.draw_card("fxcard", 0, 1, sev, title, lines, ("mob", first["mob"]) if first.get("mob") else None,
                       timer=cards.time_text(first), frac=frac)

    def close_fx_card(self):
        """Clique no cartão dos efeitos: fecha até eles acabarem (enquanto isso aparecem como contadores)."""
        self.fx_closed |= {r["key"] for r in self.fx_now}
        self.dirty = True

    def fx_show(self, kind, ident):
        """Como um efeito acompanhado aparece agora: "pin", "card" ou "counter"."""
        if self.fx_pin_key(kind, ident) in (self.cfg.get("pins") or []):
            return "pin"
        e = cards.entry(kind, ident)
        ids = set(e["ids"]) if e else {ident}
        return next((t["show"] for t in cards.tracked(self.cfg) if t["kind"] == kind and t["id"] in ids), "counter")

    def set_fx_show(self, kind, ident, mode):
        """Escolhe como um efeito acompanhado aparece: "counter" (contador no pé das linhas), "pin" (fixado na
        faixa fixa) ou "card" (cartão enquanto durar). Um efeito que ainda não era acompanhado entra na lista."""
        key = self.fx_pin_key(kind, ident)
        pinned = key in (self.cfg.get("pins") or [])
        if not cards.is_tracked(self.cfg, kind, ident):
            cards.track(self.cfg, kind, ident, on=True)
        if mode == "pin":
            if not pinned:
                self.toggle_pin_stat(key)
        else:
            if pinned:
                self.toggle_pin_stat(key)
            cards.track(self.cfg, kind, ident, on=True, show=mode)
            self.fx_closed.discard(key[3:])
        self.save()
        self.dirty = True
        if self.analysis is not None:
            self.analysis.refresh(force=True)

    def tracker_menu(self, key):
        m = self.new_menu()
        kind, _sep, ident = key.partition(":")
        seen = self.tracker_rows + self.fx_cards + list(self.pinned_fx.values())
        row = next((r for r in seen if r["key"] == key), None)
        if row is not None:
            sm = self.new_menu(m)
            var = self.keep(tk.StringVar(self.root, self.fx_show(kind, int(ident))))
            for mode, label in (("counter", _("Contador no pé das linhas")),
                                ("pin", _("Fixado na faixa fixa (à vista com um cartão aberto)")),
                                ("card", _("Cartão enquanto durar"))):
                sm.add_radiobutton(label=label, variable=var, value=mode,
                                   command=lambda mode=mode: self.set_fx_show(kind, int(ident), mode))
            m.add_cascade(label=_("Mostrar %s como") % cards.short_name(row["name"]), menu=sm)
            t = self.fx_tracker(kind, int(ident))
            if t is not None:
                m.add_cascade(label=_("Som: %s") % cards.sound_text(self.cfg, t), menu=self.fx_sound_menu(m, t))
                m.add_cascade(label=_("Temporizador: %s") % cards.timer_text(t), menu=self.fx_timer_menu(m, t))
            m.add_command(label=_("Parar de acompanhar %s") % row["name"],
                          command=lambda: self.untrack(kind, int(ident)))
        m.add_command(label=_("Cartões e efeitos acompanhados…"), command=lambda: self.open_analysis("cartoes"))
        return m

    def fx_tracker(self, kind, ident):
        """A entrada da lista dos acompanhados de um efeito (com o som e o temporizador), ou None."""
        e = cards.entry(kind, ident)
        ids = set(e["ids"]) if e else {ident}
        return next((t for t in cards.tracked(self.cfg) if t["kind"] == kind and t["id"] in ids), None)

    def set_fx_option(self, kind, ident, play=False, **opts):
        """Troca o som ou o temporizador de um efeito acompanhado (opts: sound, before, tone, secs)."""
        if cards.track(self.cfg, kind, ident, on=True, **opts):
            self.save()
        self.dirty = True
        if play:
            t = self.fx_tracker(kind, ident)
            if t is not None:
                play_sound(cards.voice(t), self.cfg.get("tracker_volume", 40))
        if self.analysis is not None:
            self.analysis.refresh(force=True)

    def fx_sound_menu(self, parent, t):
        """Submenu do som de um efeito: quando toca, quantos segundos antes e o tom."""
        kind, ident = t["kind"], t["id"]
        sm = self.new_menu(parent)
        var = self.keep(tk.StringVar(self.root, t["sound"] or ""))
        sm.add_radiobutton(label=_("Padrão da aba Cartões (%s)") % (
            _("ao acabar") if self.cfg.get("tracker_sound") else _("sem som")), variable=var, value="",
            command=lambda: self.set_fx_option(kind, ident, sound=None))
        for mode in cards.SOUNDS:
            label = (_("%d s antes de acabar") % t["before"]) if mode == "before" else _(cards.SOUND_TEXT[mode])
            sm.add_radiobutton(label=label, variable=var, value=mode,
                               command=lambda mode=mode: self.set_fx_option(kind, ident, sound=mode,
                                                                            play=mode != "off"))
        sm.add_separator()
        bm = self.new_menu(sm)
        bvar = self.keep(tk.IntVar(self.root, t["before"]))
        for s in sorted(set(cards.BEFORE_CHOICES) | {t["before"]}):
            bm.add_radiobutton(label="%d s" % s, variable=bvar, value=s,
                               command=lambda s=s: self.set_fx_option(kind, ident, sound="before", before=s))
        bm.add_command(label=_("Outro…"), command=lambda: self.ask_fx_before(kind, ident))
        sm.add_cascade(label=_("Quantos segundos antes"), menu=bm)
        km = self.new_menu(sm)
        kvar = self.keep(tk.StringVar(self.root, t["snd"]))
        self.add_sound_choices(km, kvar, lambda key: self.set_fx_option(kind, ident, snd=key, play=True))
        sm.add_cascade(label=_("Qual som: %s") % sound_name(t["snd"]), menu=km)
        tm = self.new_menu(sm)
        tvar = self.keep(tk.StringVar(self.root, t["tone"]))
        for tone, hz in itemping.TONES:
            tm.add_radiobutton(label="%s (%d Hz)" % (_(TONE_NAMES[tone]), hz), variable=tvar, value=tone,
                               command=lambda tone=tone: self.set_fx_option(kind, ident, tone=tone, play=True))
        sm.add_cascade(label=_("Tom"), menu=tm)
        return sm

    def fx_timer_menu(self, parent, t):
        """Submenu do temporizador de um efeito: a duração do jogo ou uma escolhida."""
        kind, ident = t["kind"], t["id"]
        tm = self.new_menu(parent)
        var = self.keep(tk.IntVar(self.root, t["secs"]))
        tm.add_radiobutton(label=_("A duração que o jogo manda"), variable=var, value=0,
                           command=lambda: self.set_fx_option(kind, ident, secs=0))
        choices = sorted(set(cards.TIMER_CHOICES) | ({t["secs"]} if t["secs"] else set()))
        for s in choices:
            tm.add_radiobutton(label=cards.timer_text(dict(secs=s)), variable=var, value=s,
                               command=lambda s=s: self.set_fx_option(kind, ident, secs=s))
        tm.add_command(label=_("Outro…"), command=lambda: self.ask_fx_timer(kind, ident))
        return tm

    def ask_fx_before(self, kind, ident):
        """"Quantos segundos antes" com um número digitado (de 1 s a 10 min)."""
        from tkinter import simpledialog
        t = self.fx_tracker(kind, ident)
        secs = simpledialog.askinteger(_("Segundos antes"), _("Quantos segundos antes de %s acabar o som toca?")
                                       % cards.short_name(cards.name_of(t)) if t else "",
                                       parent=self.root, minvalue=1, maxvalue=cards.MAX_BEFORE_S,
                                       initialvalue=(t or {}).get("before") or cards.DEFAULT_BEFORE)
        if secs:
            self.set_fx_option(kind, ident, sound="before", before=secs)

    def add_sound_choices(self, menu, var, command):
        """Os sons do programa e os da pasta da pessoa num menu de escolha (radiobuttons em `var`), e no fim o item
        para escolher a pasta."""
        for key in sounds.KEYS:
            menu.add_radiobutton(label=_(sounds.NAMES[key]), variable=var, value=key,
                                 command=lambda key=key: command(key))
        mine = sounds.custom_sounds(self.cfg.get("sound_folder"))
        if mine:
            menu.add_separator()
            for key, name in mine:
                menu.add_radiobutton(label=name, variable=var, value=key, command=lambda key=key: command(key))
        menu.add_separator()
        menu.add_command(label=_("Pasta com os seus sons…"), command=self.pick_sound_folder)

    def pick_sound_folder(self):
        """Escolhe a pasta dos sons da pessoa (.wav e .mp3, até 10 MB cada; toca no máximo 10 s)."""
        from tkinter import filedialog
        path = filedialog.askdirectory(parent=self.root, title=_("Pasta com os seus sons (.wav ou .mp3)"),
                                       initialdir=self.cfg.get("sound_folder") or None, mustexist=True)
        if not path:
            return
        self.cfg["sound_folder"] = os.path.normpath(path)
        set_sound_folder(self.cfg["sound_folder"])
        self.save()
        n = len(sounds.custom_sounds(self.cfg["sound_folder"]))
        self.alert = ((_("Pasta de sons: %d som(ns) .wav ou .mp3") % n) if n else
                      _("Pasta de sons: nenhum .wav ou .mp3 de até 10 MB nela"), "info", time.time())
        self.dirty = True
        if self.analysis is not None:
            self.analysis.refresh(force=True)

    @staticmethod
    def sound_name(key):
        return sound_name(key)

    def ping_sound_of(self, item):
        """O som escolhido para um item marcado, ou None (o som padrão do aviso de item)."""
        snd = (self.cfg.get("ping_snd") or {}).get(str(item))
        return snd if sounds.valid(snd) else None

    def set_ping_sound(self, item, snd):
        """Aviso de um item pelo botão direito: snd None = não avisar; "" = avisar com o som padrão do aviso de item;
        senão avisar com esse som (toca uma vez para ouvir)."""
        items = self.ping_list()
        old = self.cfg.get("ping_snd")
        chosen = self.cfg["ping_snd"] = dict(old) if isinstance(old, dict) else {}     # cópia: nunca o do padrão
        vol, tone = self.cfg.get("ping_volume", 40), self.cfg.get("ping_tone") or itemping.DEFAULT_TONE
        if snd is None:
            if item in items:
                items.remove(item)
            chosen.pop(str(item), None)
            if self.ping_card and self.ping_card[0]["item"] == item:
                self.ping_card = None
        else:
            if item not in items:
                items.append(item)
            if snd:
                chosen[str(item)] = snd
                play_sound((snd, tone), vol)
            else:
                chosen.pop(str(item), None)
                play_ping(vol, tone)
        self.save()
        self.drops_changed()

    def ping_sound_menu(self, parent, item):
        """Submenu do botão direito num item: não avisar, o som padrão do aviso ou qualquer outro som."""
        m = self.new_menu(parent)
        on = item in self.ping_items()
        cur = self.ping_sound_of(item)
        var = self.keep(tk.StringVar(self.root, (cur or "") if on else "-"))
        m.add_radiobutton(label=_("Não avisar"), variable=var, value="-", command=lambda: self.set_ping_sound(item, None))
        m.add_radiobutton(label=_("Avisar com o som padrão do aviso de item"), variable=var, value="",
                          command=lambda: self.set_ping_sound(item, ""))
        m.add_separator()
        self.add_sound_choices(m, var, lambda key: self.set_ping_sound(item, key))
        return m

    def ask_fx_timer(self, kind, ident):
        from tkinter import simpledialog
        t = self.fx_tracker(kind, ident)
        secs = simpledialog.askinteger(_("Temporizador"), _("Quantos segundos o contador de %s conta?")
                                       % cards.short_name(cards.name_of(t)) if t else "",
                                       parent=self.root, minvalue=1, maxvalue=cards.MAX_TIMER_S,
                                       initialvalue=(t or {}).get("secs") or 20)
        if secs:
            self.set_fx_option(kind, ident, secs=secs)

    def fx_pin_key(self, kind, ident):
        e = cards.entry(kind, ident)
        return "fx:%s:%d" % (kind, e["id"] if e else ident)

    def toggle_pin_fx(self, kind, ident):
        """Fixa (ou desafixa) um efeito acompanhado na faixa fixa: ele sai dos contadores do pé e fica na faixa,
        à vista mesmo com um cartão aberto. Fixar também põe o efeito na lista dos acompanhados."""
        key = self.fx_pin_key(kind, ident)
        if key not in (self.cfg.get("pins") or []) and not cards.is_tracked(self.cfg, kind, ident):
            cards.track(self.cfg, kind, ident, on=True)
        self.toggle_pin_stat(key)
        self.dirty = True
        if self.analysis is not None:
            self.analysis.refresh(force=True)

    def untrack(self, kind, ident):
        changed = cards.track(self.cfg, kind, ident, on=False)
        key = self.fx_pin_key(kind, ident)
        if key in (self.cfg.get("pins") or []):          # deixou de acompanhar: sai da faixa fixa também
            self.cfg["pins"] = [p for p in self.cfg["pins"] if p != key]
            self.resize_window()
            changed = True
        if changed:
            self.save()
        self.dirty = True
        if self.analysis is not None:
            self.analysis.refresh(force=True)

    def ping_char(self):
        """O personagem da lista de itens marcados: o do replay aberto, senão o último visto (None = nenhum ainda)."""
        cb = self.combat()
        name = cb.session.player if cb is not None else None
        if name and self.cfg.get("ping_last_char") != name:
            self.cfg["ping_last_char"] = name
        return name or self.cfg.get("ping_last_char")

    def ping_list(self):
        """A lista de itens marcados que vale agora: a de todos os personagens, a deste personagem ou a desta
        sessão do programa (ping_keep). É a própria lista guardada: mexer nela e salvar basta."""
        mode = self.cfg.get("ping_keep") or "all"
        if mode == "session":
            if self.ping_session is None:
                self.ping_session = []
            return self.ping_session
        who = self.ping_char() if mode == "char" else None
        if who:
            chars = self.cfg.setdefault("ping_chars", {})
            if not isinstance(chars.get(who), list):      # a primeira vez do personagem começa com a lista geral
                chars[who] = [i for i in (self.cfg.get("ping_items") or []) if isinstance(i, int)]
            return chars[who]
        if not isinstance(self.cfg.get("ping_items"), list):
            self.cfg["ping_items"] = []
        return self.cfg["ping_items"]

    def set_ping_keep(self, mode):
        """Troca para quem valem os itens marcados. A lista nova começa com o que valia até aqui."""
        if mode not in ("all", "char", "session") or mode == (self.cfg.get("ping_keep") or "all"):
            return
        cur = [i for i in self.ping_list() if isinstance(i, int)]
        self.cfg["ping_keep"] = mode
        if mode == "session":
            self.ping_session = list(cur)
        else:
            self.ping_list()
        self.save()
        self.drops_changed()

    def ping_items(self):
        """Os itens marcados para aviso."""
        out = set()
        for i in self.ping_list():
            try:
                out.add(int(i))
            except (TypeError, ValueError):
                pass
        return out

    def toggle_ping(self, item):
        """Marca ou desmarca o aviso de um item (botão direito no item, no widget ou na aba Drops da análise)."""
        items = self.ping_list()
        if item in items:
            items.remove(item)
            if self.ping_card and self.ping_card[0]["item"] == item:
                self.ping_card = None
        else:
            items.append(item)
        self.save()
        self.drops_changed()

    def check_pings(self, c, now):
        """Aviso de item: quando um item marcado cai, toca o som e mostra o cartão com o lugar. Se ele sair da
        vista sem ser pego (telou sem querer, foi puxado), o cartão volta até o item sumir do chão."""
        try:
            events = self.pings.poll(c, self.ping_items(), self.watcher.recording(now))
        except Exception:  # noqa: BLE001 - o aviso é um extra
            self.log_error(*sys.exc_info())
            events = []
        for kind, info in events:
            if kind in ("drop", "mvp", "left"):
                self.show_ping(kind, info, c, now)
            elif self.ping_card and self.ping_card[0].get("ref") is info:
                self.ping_card = None             # pego (por você ou por outro) ou o tempo no chão acabou
                self.dirty = True
        if self.ping_card and now - self.ping_card[1] > self.ping_card[0]["secs"]:
            self.ping_card = None
            self.dirty = True

    def show_ping(self, kind, info, c, now):
        item = info["item"]
        name = meter.item_name(item)
        secs = PING_CARD_S
        if kind == "left":                        # fica até o item sumir do chão
            secs = max(6.0, min(60.0, (itemping.ITEM_LIFE_MS - (c.now - info["t"])) / 1000.0))
        art = xp.GEAR.art.get(item)
        spec = ("item", item, art) if art else None
        try:
            if spec:
                sprites.MONSTERS.start(clientdata.NAMES.grf)
                sprites.MONSTERS.image(spec)
        except Exception:  # noqa: BLE001 - sem o desenho o cartão aparece do mesmo jeito
            spec = None
        if cards.enabled(self.cfg, "ping"):       # o cartão dá para desligar no gerenciador (o som é à parte)
            self.ping_card = (dict(kind=kind, ref=info, item=item, name=name, count=info.get("count") or 1,
                                   map=info.get("map"), x=info.get("x"), y=info.get("y"), mob=info.get("mob"),
                                   secs=secs, sprite=spec), now)
        text = {"drop": _("Caiu: %s"), "mvp": _("Prêmio de MVP: %s"), "left": _("Ficou para trás: %s")}[kind] % name
        self.alert = (text, "info", now)
        if self.cfg.get("ping_sound", True) and now - self.ping_played >= PING_SOUND_GAP_S:
            self.ping_played = now
            snd = self.ping_sound_of(item)            # o som escolhido para o item (botão direito nele) ou o padrão
            if snd:
                play_sound((snd, self.cfg.get("ping_tone") or itemping.DEFAULT_TONE), self.cfg.get("ping_volume", 40))
            else:
                play_ping(self.cfg.get("ping_volume", 40), self.cfg.get("ping_tone"))
        self.dirty = True

    def copy_ping(self):
        """Clique no cartão do item: copia o /navi do lugar onde ele caiu (para colar no jogo)."""
        d = self.ping_card[0] if self.ping_card else None
        cmd = itemping.navi(d)
        if not cmd:
            self.ping_card = None
            self.dirty = True
            return
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(cmd)
        except tk.TclError:
            return
        self.alert = (_("Copiado: %s") % cmd, "info", time.time())
        self.dirty = True

    def ping_menu(self):
        m = self.new_menu()
        d = self.ping_card[0] if self.ping_card else None
        if d and itemping.navi(d):
            m.add_command(label=_("Copiar o /navi do item"), command=self.copy_ping)
        m.add_command(label=_("Fechar este aviso"), command=lambda: (setattr(self, "ping_card", None),
                                                                     setattr(self, "dirty", True)))
        if d:
            m.add_command(label=_("Parar de avisar deste item"), command=lambda: self.toggle_ping(d["item"]))
        return m

    def draw_ping_card(self):
        """Cartão do item marcado que caiu: o lugar (mapa e coordenadas) e, com um clique, o /navi copiado para
        colar no jogo. Em amarelo quando o item ficou para trás, até ele sumir do chão."""
        if not self.ping_card:
            return
        d, shown = self.ping_card
        where = "%s · %d/%d" % (d["map"], d["x"], d["y"]) if d.get("x") is not None and d.get("map") else None
        name = d["name"] + (" ×%d" % d["count"] if d["count"] > 1 else "")
        lines = []
        if d["kind"] == "mvp":
            sev, title = "bom", _("Prêmio de MVP: %s") % name
            lines.append((_("Foi direto para a sua bolsa"), CARD_DIM))
        else:
            sev, title = ("atencao", _("Ficou para trás: %s") % name) if d["kind"] == "left" else (
                "bom", _("Caiu: %s") % name)
            if where:
                lines.append((where, CARD_WHITE))
                lines.append((_("Clique: copia o /navi para colar no jogo"), "#38bdf8"))
            if d["kind"] == "left":
                lines.append((_("Some do chão quando o tempo acabar"), CARD_DIM))
            elif d.get("mob"):
                lines.append((_("de %s") % d["mob"], CARD_DIM))
        self.draw_card("ping", shown, d["secs"], sev, title, lines, d.get("sprite"))

    def check_summary(self, c, now):
        """O chefe morreu: depois dos últimos pacotes (ou de ver que não vem outra fase), mostra o resumo da luta."""
        due = self.summary_due
        if due is None:
            return
        if due[0] is not c or due[1] not in c.fight_ends:
            self.summary_due = None
            return
        key, t = c.fight_ends[due[1]]
        e = c.entities.get(key)
        phased = e is not None and e.job in meter.PHASED_BOSSES and c.phases.get(key, 1) < 3
        if c.now < t + (SUMMARY_PHASE_MS if phased else SUMMARY_WAIT_MS) and not c.finished:
            return
        self.summary_due = None
        if any(h.out and h.dst == key and h.t > t + 1000 for h in c.hits[-300:]):
            return                                # veio outra fase: a luta continua
        self.show_summary(c, key, now)

    def show_summary(self, c, key, now):
        """Monta o cartão do fim da luta: tempo, a sua parte do dano e as principais conclusões do Dedo Duro."""
        try:
            import dedoduro
            r = dedoduro.analyze(c, key)
            if not r:
                return
            rows = sorted(r["party"] + r["others"], key=lambda p: -p["dmg"])
            mine = next((i for i, p in enumerate(rows) if p.get("me")), None)
            bad = [a for a in r["alerts"] if a["sev"] >= 1]
            e = c.entities.get(key)
            form = c.sprite_log[key][-1][1] if c.sprite_log.get(key) else (e.job if e is not None else 0)
            spec = ("mob", form) if form else None
            sprites.MONSTERS.start(clientdata.NAMES.grf)
            sprites.MONSTERS.image(spec)
            self.summary_card = (dict(
                key=key, sprite=spec, name=c.name_of(key), killed=r["killed"], ms=r["end"] - r["start"],
                share=rows[mine]["share"] if mine is not None else None,
                rank=mine + 1 if mine is not None else None, players=len(rows),
                alerts=[(a["sev"], a["what"], a["who"]) for a in bad[:3]],
                grave=sum(1 for a in bad if a["sev"] == 2), warn=sum(1 for a in bad if a["sev"] == 1)), now)
        except Exception:  # noqa: BLE001 - o resumo é um extra
            self.log_error(*sys.exc_info())
        self.dirty = True

    def check_session(self, f, now):
        """Resumo da sessão: a gravação que estava sendo escrita parou. Na hora quando o jogo solta o arquivo ou é
        fechado (session_ended); quando começa outra gravação, o step mostra na hora. O jogo segura o arquivo enquanto
        grava e solta quando a gravação para (visto ao vivo em 2026-11-19): com o jogo segurando, o arquivo parado
        (personagem parado, jogo travado) não é fim. Só quando não dá para saber quem está com o arquivo vale a espera
        de SESSION_END_S parado. Se a gravação voltar a crescer, o resumo sai (não tinha acabado); ele também sai
        quando a luta recomeça numa gravação nova ou depois de SESSION_CARD_S."""
        c, w = f.combat, self.watcher
        if w.pinned:
            return
        quiet = now - w.last_change
        card = self.session_card
        if card and card[0]["c"] is c and w.last_change > card[0].get("made", card[1]):
            self.session_card = None              # voltou a crescer depois do resumo: não tinha acabado
            self.dirty = True
        done = self.live_done
        if done and done[0] is c and w.last_change <= done[1]:
            pass                                  # já acabou e não cresceu desde então
        elif quiet <= session.SESSION_END_S:
            if self.live_combat is not c:
                self.live_combat, self.hold_seen, self.hold_now = c, 0, None
                if clientdata.NAMES.grf:            # os desenhos do resumo (os Porings e o cavaleiro da "Máquina
                    sprites.MONSTERS.start(clientdata.NAMES.grf)      # de abates")
                    sprites.LOADER.start(clientdata.NAMES.grf)
            if self.session_ended(f, now, quiet):
                self.end_live(c, now)
        elif self.live_combat is c:
            if self.hold_seen >= HOLD_SEEN_MIN and self.hold_now:
                if self.session_ended(f, now, quiet):  # o jogo ainda grava (parado ou travado): acaba quando soltar
                    self.end_live(c, now)
            else:
                self.end_live(c, now)
        if self.session_card:
            d, shown = self.session_card
            new = False
            if d["c"] is not c:                   # outra gravação: o resumo sai quando você volta a lutar nela
                n0 = d["n0"] if d["cur"] is c else 0
                if len(c.hits) < n0:
                    n0 = d["n0"] = 0              # Zerar na gravação nova
                new = any(h.out and h.src == c.me for h in c.hits[n0:])
            if now - shown > SESSION_CARD_S or new:
                self.session_card = None
                self.dirty = True

    def end_live(self, c, now):
        self.live_combat = None
        self.live_done = (c, self.watcher.last_change)
        self.show_session(c, now)

    def session_ended(self, f, now, quiet):
        """A gravação acabou antes dos SESSION_END_S parada? Sim se o jogo foi fechado, ou se o jogo soltou o arquivo
        dela: o Windows diz quem está com o arquivo aberto (meter.file_holders, sem abrir o arquivo). Isso só vale
        depois de ver, nesta gravação, o jogo com o arquivo aberto mesmo com ele parado (então o jogo segura o arquivo
        enquanto grava, e soltar quer dizer parar); sem isso, fica a espera de SESSION_END_S."""
        if quiet < HOLD_QUIET_S or now - self.hold_check_at < self.hold_every:
            return False
        self.hold_check_at = now
        t0 = time.perf_counter()
        holders = meter.file_holders(f.path)
        took = time.perf_counter() - t0
        self.hold_every = HOLD_CHECK_S if took < 0.1 else 5.0     # num computador em que a pergunta é lenta, menos
        self.hold_now = None if holders is None else bool(holders)
        if holders is None:
            return False
        if holders:
            self.hold_seen += 1
            return False
        if self.hold_seen >= HOLD_SEEN_MIN:
            return True
        return not meter.game_running()          # ninguém com o arquivo e o jogo fechado: acabou

    def show_session(self, c, now):
        """Monta o resumo da gravação que acabou: o que a pessoa escolheu na aba Cartões e os destaques dela. Gravação
        de menos de 1 min (session.MIN_MS) só ganha o resumo se teve um acontecimento (session.SHORT_OK: um chefe, uma
        carta, uma subida de nível, um one shot; o Bafomé de 58 s do usuário não tinha resumo), e não mexe nos
        recordes."""
        if not cards.enabled(self.cfg, "session"):
            return
        short = c.now < session.MIN_MS
        records = None
        if not short:
            try:
                before = json.dumps(self.cfg.get("session_records"), sort_keys=True)
                records = session.update_records(c, self.cfg)
                if json.dumps(self.cfg.get("session_records"), sort_keys=True) != before:
                    self.save()
            except Exception:  # noqa: BLE001 - os recordes são um extra
                self.log_error(*sys.exc_info())
                records = None
        try:
            d = session.card(c, self.cfg, favs=self.cfg.get("drop_favs") or [], marked=self.ping_items(),
                             records=records)
        except Exception:  # noqa: BLE001 - o resumo é um extra
            self.log_error(*sys.exc_info())
            return
        if not (d["lines"] or d["hl"] or d["sub"]):
            return
        if short and not any(h["key"] in session.SHORT_OK for h in d["hl"]):
            return
        cur = self.combat()
        d.update(c=c, cur=cur, n0=len(cur.hits) if cur is not None else 0, made=now)
        if d["hl"] and d["hl"][0].get("fx") == "chase":
            d["chase"] = {}                       # os desenhos do jogo entram quando ficarem prontos (draw_chase)
            if clientdata.NAMES.grf:
                sprites.MONSTERS.start(clientdata.NAMES.grf)
                sprites.LOADER.start(clientdata.NAMES.grf)
        if not self.session_covered():
            self.prepare_session_fx(d)
        self.session_card = (d, time.time())      # depois de montar a cena: a animação começa do começo
        self.session_waiting = False
        self.last_session = d
        self.dirty = True
        self.start_session_anim()

    def reopen_session(self):
        """O menu do widget: mostra de novo o último resumo da sessão (com a animação)."""
        d = self.last_session
        if not d:
            return
        cur = self.combat()
        d.update(cur=cur, n0=len(cur.hits) if cur is not None else 0)
        self.session_card = (d, time.time())
        self.dirty = True
        self.start_session_anim()

    def session_covered(self):
        """Algum cartão que passa na frente do resumo da sessão está na tela (a morte, o item marcado, o aviso de chefe,
        o resumo da luta: a ordem do draw)?"""
        return bool(self.death_card or self.ping_card or self.boss_card or self.summary_card)

    def session_wait(self, now):
        """O resumo da sessão atrás de outro cartão fica parado: o relógio dele (a animação e os SESSION_CARD_S) só
        anda quando ele aparece, e aí a animação começa do zero. Antes, quem parava a gravação logo depois de matar o
        chefe via o resumo da sessão só depois dos 14 s do resumo da luta, já sem a animação (o Osíris do usuário)."""
        card = self.session_card
        if not card:
            self.session_waiting = False
            return
        if self.session_covered():
            self.session_card = (card[0], now)
            self.session_waiting = True
        elif self.session_waiting:
            self.session_waiting = False
            self.prepare_session_fx(card[0])
            self.session_card = (card[0], time.time())
            self.dirty = True
            self.start_session_anim()

    def prepare_session_fx(self, d):
        """Monta antes os desenhos da cena do destaque do resumo `d` (o lutador, o monstro e os números da luta; os
        bichinhos e o cavaleiro da "Máquina de abates"), que levam uns 0,5 s: montados no primeiro quadro, a animação
        começava sem o primeiro meio segundo. Só se a animação está ligada e os desenhos do jogo já estão prontos."""
        hl = (d.get("hl") or [None])[0]
        if not hl or hl.get("fx") not in SCENE_FX or not self.cfg.get("session_anim", True):
            return
        try:
            if hl["fx"] in FIGHT_ACTS:
                self.fight_assets(hl.get("fight") or {}, hl["fx"])
            elif hl["fx"] == "chase":
                frames = d.setdefault("chase", {})
                if "mobs" not in frames and sprites.MONSTERS.book is not None:
                    frames["mobs"] = self.chase_frames()
                if "rider" not in frames and sprites.LOADER.wardrobe is not None:
                    frames["rider"] = self.rider_frames()
            elif hl["fx"] in ("deck", "mvp_card"):
                self.card_scene(d.setdefault("chase", {}), hl["fx"], hl.get("deal") or {})
        except Exception:  # noqa: BLE001 - a cena é um extra: sem ela, os desenhos de reserva
            self.log_error(*sys.exc_info())

    def start_session_anim(self):
        """Quadros extras (a cada SESSION_FX_MS) enquanto a animação do destaque do resumo da sessão roda. Com outro
        cartão na frente ela não roda (session_wait começa quando o resumo aparece)."""
        if (self.session_anim is not None or not self.session_card or not self.cfg.get("session_anim", True)
                or self.session_covered()):
            return
        hls = self.session_card[0].get("hl") or []
        if not (hls and hls[0].get("fx")):
            return

        def frame():
            self.session_anim = None
            card = self.session_card
            if not card or time.time() - card[1] > SESSION_FX_S + 0.2 or self.session_covered():
                self.dirty = True                 # o quadro sem a animação vem no laço normal
                return
            try:
                self.draw()
            except Exception:  # noqa: BLE001 - a animação é um extra
                self.log_error(*sys.exc_info())
                return
            self.session_anim = self.root.after(SESSION_FX_MS, frame)
        self.session_anim = self.root.after(SESSION_FX_MS, frame)

    def open_session(self):
        """Clique no resumo da sessão: abre a análise no Resumo."""
        self.session_card = None
        self.dirty = True
        self.open_analysis()
        if self.analysis is not None:
            try:
                self.analysis.select_tab("resumo")
            except Exception:  # noqa: BLE001
                self.log_error(*sys.exc_info())

    def session_menu(self):
        m = self.new_menu()
        m.add_command(label=_("Abrir a análise"), command=self.open_session)
        m.add_command(label=_("Fechar este resumo"), command=lambda: (setattr(self, "session_card", None),
                                                                     setattr(self, "dirty", True)))
        m.add_command(label=_("Escolher o que o resumo mostra…"), command=self.open_session_options)
        m.add_command(label=_("Não mostrar mais o resumo da sessão"), command=lambda: self.toggle_cfg("session_card"))
        return m

    def open_session_options(self):
        """A aba Cartões da análise, na parte do resumo da sessão."""
        self.open_analysis()
        if self.analysis is not None:
            try:
                self.analysis.select_tab("cartoes")
                self.analysis.cards_tab.show_page("session")
            except Exception:  # noqa: BLE001
                self.log_error(*sys.exc_info())

    def session_fit(self, d=None):
        """Quantas linhas das informações cabem no cartão, depois do título e do que os destaques de `d` (o cartão)
        pedem: a mesma conta do draw_session_card."""
        return self.session_layout(d or {})[1]

    def session_layout(self, d, stage=0.0):
        """(partes que cabem, quantas linhas cabem). O título sempre; depois até 2 linhas das informações, o
        subtítulo, a frase e a barra do destaque principal e os selos dos outros, nessa ordem, enquanto couberem; o
        resto do espaço vai para as linhas. `stage`: a altura do palco aberto no pé do cartão (fica fora da conta)."""
        s = self.s
        room = ((self.rows_y0() + self.cfg["rows"] * ROW_H - 3) - (TABS_Y0 - 2)) * s - 18 * s - 22 * s - stage
        hls = d.get("hl") or []
        main = hls[0] if hls else None
        want = []
        if d.get("sub") or main:
            want.append(("sub", 13 * s))
        if main and main.get("sub"):
            want.append(("phrase", 14 * s))
        if main and main.get("bar") is not None:
            want.append(("bar", 14 * s))
        if len(hls) > 1:
            want.append(("chips", 21 * s))
        n = len(d.get("lines") or ()) if d else 99
        used = min(n, 2) * 14 * s
        parts = set()
        for name, h in want:
            if used + h <= room:
                parts.add(name)
                used += h
        free = room - (used - min(n, 2) * 14 * s)
        return parts, max(0, int(free // (14 * s)))

    def draw_session_card(self):
        """Resumo da sessão que acabou: o destaque principal no título, numa faixa da cor dele e com a animação dele no
        começo (confete, moedinhas, estrelas, brilho); embaixo, a duração e o mapa, a frase e a barra do destaque, os
        outros destaques em selos e uma linha por informação escolhida (o que não cabe vira "mais N")."""
        if not self.session_card:
            return
        d, shown = self.session_card
        k = time.time() - shown
        if not 0 <= k < SESSION_CARD_S:
            return
        c, s, W = self.canvas, self.s, self.W
        hls = d.get("hl") or []
        main = hls[0] if hls else None
        col = main["color"] if main else SEV_COLORS["info"]
        x0, x1 = 8 * s, W - 8 * s
        y0 = (TABS_Y0 - 2) * s
        y1 = (self.rows_y0() + self.cfg["rows"] * ROW_H - 3) * s
        pad = 9 * s
        cx = (x0 + x1) / 2
        glass = bool(main and main.get("glass"))
        c.create_polygon(round_rect_pts(x0, y0, x1, y1, 10 * s), smooth=True, fill=GLASS_BG if glass else CARD_BG,
                         outline=col, width=max(1, int(2 * s)))
        if glass:                                 # vidro: duas faixas de brilho na diagonal e diamantes parados
            for off, wd in ((0.18, 0.10), (0.34, 0.04)):
                xa = x0 + (x1 - x0) * off
                c.create_polygon(xa, y0 + 2 * s, xa + (x1 - x0) * wd, y0 + 2 * s,
                                 xa + (x1 - x0) * wd - (y1 - y0) * 0.6, y1 - 2 * s, xa - (y1 - y0) * 0.6, y1 - 2 * s,
                                 fill=mix(GLASS_BG, "#ffffff", 0.07), outline="")
            if k >= SESSION_FX_S or not self.cfg.get("session_anim", True):
                self.draw_diamonds(2.0, (x0, y0, x1, y1), 0.45, GLASS_BG)
        self.hits.append((("session", None), (x0, y0, x1, y1)))
        # o palco das cenas com personagens: aberto durante a animação, depois recolhe
        stage = 0.0
        if main and main.get("fx") in SCENE_FX and self.cfg.get("session_anim", True) and k < SESSION_FX_S + STAGE_FOLD_S:
            stage = STAGE_HS.get(main.get("fx"), STAGE_H) * s * (1.0 if k < SESSION_FX_S else
                                                                  max(0.0, 1.0 - (k - SESSION_FX_S) / STAGE_FOLD_S))
        if stage > 1:
            c.create_rectangle(x0 + 3 * s, y1 - stage, x1 - 3 * s, y1 - 5 * s, fill=mix(CARD_BG, col, 0.06), outline="")
            c.create_line(x0 + 10 * s, y1 - stage, x1 - 10 * s, y1 - stage, fill=mix(CARD_BG, col, 0.3))
        parts, fit = self.session_layout(d, stage)
        lines = list(d.get("lines") or [])
        if len(lines) > fit:
            lines = (lines[:fit - 1] + [(_("mais %d na análise (clique)") % (len(lines) - fit + 1), CARD_DIM)]
                     if fit >= 1 else [])
        heights = dict(sub=13 * s, phrase=14 * s, bar=14 * s, chips=21 * s)
        total = 22 * s + sum(h for p, h in heights.items() if p in parts) + 14 * s * len(lines)
        y = y0 + max(pad, ((y1 - stage - y0) - total) / 2)
        anim = bool(main and main.get("fx") and self.cfg.get("session_anim", True) and k < SESSION_FX_S)
        # a faixa do título na cor do destaque, com a metade de cima mais clara (brilho) e um fio embaixo
        bx0, bx1 = x0 + 4 * s, x1 - 4 * s
        c.create_polygon(round_rect_pts(bx0, y - 3 * s, bx1, y + 19 * s, 7 * s), smooth=True,
                         fill=mix(CARD_BG, col, 0.13), outline="")
        c.create_polygon(round_rect_pts(bx0 + 2 * s, y - 2 * s, bx1 - 2 * s, y + 7 * s, 5 * s), smooth=True,
                         fill=mix(CARD_BG, col, 0.21), outline="")
        c.create_line(bx0 + 10 * s, y + 19 * s, bx1 - 10 * s, y + 19 * s, fill=mix(CARD_BG, col, 0.5))
        if anim:
            self.draw_session_fx(main["fx"], k, (x0, y0, x1, y1), col, y + 8 * s, (bx0 + 13 * s, y + 8 * s),
                                 main.get("tag"), d.setdefault("chase", {}), GLASS_BG if glass else CARD_BG,
                                 main.get("fight"), main.get("deal"))
        cid = c.create_text(x1 - pad, y0 + pad + 4 * s, anchor="e", text="✕", font=self.fonts["small"],
                            fill=CARD_DIM)
        count_w = c.bbox(cid)[2] - c.bbox(cid)[0]
        xr = x1 - pad - (count_w + 6 * s if y < y0 + pad + 14 * s else 0)
        xl = x0 + pad
        if main and main.get("emblem"):           # o emblema: um círculo na cor do destaque com o símbolo dele
            ex, ey, er = bx0 + 13 * s, y + 8 * s, 9 * s
            if anim:                              # entra crescendo e dá um pulinho
                er *= min(1.0, 0.4 + k / 0.25) * (1.0 + 0.12 * math.sin(min(k, 1.2) * 10) * max(0.0, 1.2 - k))
            c.create_oval(ex - er, ey - er, ex + er, ey + er, fill=col, outline=mix(col, "#ffffff", 0.45),
                          width=max(1, int(s)))
            c.create_text(ex, ey, text=main["emblem"], fill=CARD_BG,
                          font=("Segoe UI Symbol", -max(6, int(er * 1.15)), "bold"))
            xl = ex + 9 * s + 6 * s
        title = main["title"].upper() if main else _("Resumo da sessão").upper()
        self.center_text(max(cx, (xl + xr) / 2) if main else cx, y + 8 * s, title, self.fonts["title"],
                         mix(col, "#ffffff", 0.15), xl, xr)
        y += 22 * s
        if "sub" in parts:
            sub = d.get("sub") or ""
            text = (_("Resumo da sessão") + (" · " + sub if sub else "")) if main else sub
            self.center_text(cx, y + 4 * s, text, self.fonts["small"], CARD_DIM, x0 + pad, x1 - pad)
            y += 13 * s
        if "phrase" in parts:
            self.center_text(cx, y + 5 * s, main["sub"], self.fonts["small"], mix(col, "#ffffff", 0.45), x0 + pad,
                             x1 - pad)
            y += 14 * s
        if "bar" in parts:
            self.draw_session_bar(main["bar"], cx, y + 6 * s, x0 + pad, x1 - pad, col, k if anim else None)
            y += 14 * s
        if "chips" in parts:
            self.draw_session_chips(hls[1:], y + 9 * s, x0 + pad, x1 - pad)
            y += 21 * s
        for text, fill in lines:
            self.center_text(cx, y + 5 * s, text, self.fonts["small"], fill or CARD_DIM, x0 + pad, x1 - pad)
            y += 14 * s
        if anim and main.get("fx") == "mvp_card" and k < MVP_LAND_S:   # a carta de MVP se revela por cima
            self.draw_mvp_reveal(k, (x0, y0, x1, y1), main.get("deal") or {}, d.setdefault("chase", {}), col)
        left = 1.0 - k / SESSION_CARD_S
        if left > 0.005:
            c.create_line(x0 + 10 * s, y1 - 3 * s, x0 + 10 * s + (x1 - x0 - 20 * s) * left, y1 - 3 * s, fill=col,
                          width=max(2, int(2 * s)))

    def draw_fist(self, x, y, k, fade, bg, t=0.0):
        """O punho de um monge socando para a direita, com a frente em (x, y); k = tamanho (s). O antebraço e a mão
        enfaixados (as faixas cruzando os nós dos dedos e o pulso, as duas pontas soltas balançando para trás com o
        tempo `t`), o rosário no pulso, o polegar dobrado por cima dos dedos, deitado no eixo do soco, e os dedos
        fechados na frente."""
        c = self.canvas
        skin, shade, line, cloth, cloth_sh, cloth_ln, bead = (mix(bg, col, fade) for col in FIST)
        w = max(1, int(k))

        def pts(points):
            return [v for px, py in points for v in (x + px * k, y + py * k)]
        for j, (lift, ln) in enumerate(((-3, 18), (3, 14))):   # as pontas soltas das faixas, balançando
            wave = [(-24 - d, lift + 3 * math.sin(t * 9 + d * 0.35 + j)) for d in range(0, ln + 1, 3)]
            c.create_line(*pts(wave), smooth=True, fill=cloth_ln, width=max(2, int(4.2 * k)), capstyle="round")
            c.create_line(*pts(wave), smooth=True, fill=cloth, width=max(1, int(2.6 * k)), capstyle="round")
        c.create_polygon(pts([(-36, -6), (-17, -8), (-17, 8), (-36, 6)]), fill=skin, outline=line, width=w)
        for xs in (-33, -27, -21):                  # as faixas em volta do antebraço, na diagonal
            c.create_polygon(pts([(xs, -7), (xs + 4, -7), (xs + 2, 7), (xs - 2, 7)]), fill=cloth, outline=cloth_ln,
                             width=w)
        for j in range(5):                          # o rosário no pulso
            by = -7.5 + j * 3.75
            c.create_oval(*pts([(-19.5, by - 1.8), (-15.5, by + 1.8)]), fill=bead, outline=line, width=w)
            c.create_oval(*pts([(-18.6, by - 1.1), (-17.4, by - 0.1)]), fill=mix(bg, "#fed7aa", fade), outline="")
        c.create_polygon(pts([(-16, -10), (-6, -12), (8, -11), (13, -8), (15, -2), (14, 6), (9, 10), (-4, 11),
                              (-14, 9), (-17, 3), (-17, -4)]), smooth=True, fill=skin, outline=line, width=w)
        c.create_polygon(pts([(-14, 4), (-4, 7), (9, 7), (12, 9), (-4, 11), (-14, 9)]), smooth=True, fill=shade,
                         outline="")
        c.create_polygon(pts([(-12, -11), (-6, -12), (-9, 10), (-15, 9)]), fill=cloth, outline=cloth_ln, width=w)
        c.create_polygon(pts([(1, -11.5), (9, -11), (11, -9), (11, 9), (3, 9.5), (2, -2)]), smooth=True, fill=cloth,
                         outline=cloth_ln, width=w)
        for fy in (-6, -1.5, 3):                    # os dedos fechados, um em cima do outro, na frente
            c.create_line(*pts([(11, fy), (14.5, fy + 0.6)]), fill=line, width=w)
        c.create_line(*pts([(4, -10), (7, 8)]), fill=cloth_sh, width=w)
        c.create_polygon(pts([(-10, -2), (-3, -4.5), (6, -4), (9, -1.5), (6, 1.5), (-3, 2), (-10, 1)]), smooth=True,
                         fill=skin, outline=line, width=w)   # o polegar dobrado, deitado no eixo do soco
        c.create_oval(*pts([(-6, -10), (2, -7.5)]), fill=mix(bg, "#fff7ed", 0.8 * fade), outline="")

    def draw_cracks(self, x, y, grow, box, fade, bg):
        """A tela rachando a partir de (x, y): rachaduras em zigue-zague para todo lado, dois anéis de trincas em
        volta e cacos perto do centro. grow: 0 a 1 (o tamanho delas). Sempre o mesmo desenho (semente fixa)."""
        c, s = self.canvas, self.s
        x0, y0, x1, y1 = box
        rnd = random.Random(23)
        light, shadow = mix(bg, "#f1f5f9", 0.85 * fade), mix(bg, "#000000", 0.6 * fade)
        width = max(1, int(1.4 * s))

        def inside(px, py):
            return x0 + 4 * s < px < x1 - 4 * s and y0 + 4 * s < py < y1 - 4 * s
        for i in range(9):
            ang = (i / 9.0) * 2 * math.pi + rnd.uniform(-0.25, 0.25)
            length = rnd.uniform(55, 120) * s * grow
            px, py, done = x, y, 0.0
            while done < length:
                seg = rnd.uniform(7, 14) * s
                ang += rnd.uniform(-0.45, 0.45)
                nx, ny = px + math.cos(ang) * seg, py + math.sin(ang) * seg * 0.75
                if not inside(nx, ny):
                    break
                c.create_line(px + s, py + s, nx + s, ny + s, fill=shadow, width=width)
                c.create_line(px, py, nx, ny, fill=light, width=width)
                if rnd.random() < 0.3:              # um galho saindo da rachadura
                    ba = ang + rnd.choice((-1, 1)) * rnd.uniform(0.6, 1.1)
                    bx, by = nx + math.cos(ba) * seg * 0.7, ny + math.sin(ba) * seg * 0.5
                    if inside(bx, by):
                        c.create_line(nx, ny, bx, by, fill=light, width=max(1, int(s)))
                px, py, done = nx, ny, done + seg
        for ring in (16, 32):                       # os anéis de trincas em volta do impacto
            r = ring * s * grow
            prev = None
            for j in range(13):
                a = j / 12.0 * 2 * math.pi
                rr = r * rnd.uniform(0.8, 1.2)
                p = (x + math.cos(a) * rr, y + math.sin(a) * rr * 0.7)
                if prev is not None and inside(*p) and inside(*prev) and rnd.random() < 0.75:
                    c.create_line(prev[0], prev[1], p[0], p[1], fill=light, width=max(1, int(s)))
                prev = p
        for _j in range(6):                         # cacos perto do centro
            a, r = rnd.uniform(0, 2 * math.pi), rnd.uniform(4, 14) * s * grow
            cx_, cy_ = x + math.cos(a) * r, y + math.sin(a) * r * 0.7
            sz = rnd.uniform(2, 4) * s
            c.create_polygon(cx_, cy_ - sz, cx_ + sz, cy_ + sz * 0.6, cx_ - sz * 0.8, cy_ + sz * 0.4,
                             fill=mix(bg, "#cbd5e1", 0.5 * fade), outline=light)

    def draw_burst(self, x, y, r, spikes, fill, edge):
        """Uma estrela de impacto (as pontas alternam o raio todo e 45% dele)."""
        pts = []
        for i in range(spikes * 2):
            a = math.pi * i / spikes
            rr = r if i % 2 == 0 else r * 0.45
            pts += [x + math.cos(a) * rr, y + math.sin(a) * rr * 0.8]
        self.canvas.create_polygon(pts, fill=fill, outline=edge, width=max(1, int(self.s)))

    def draw_diamonds(self, k, box, fade, bg):
        """Diamantes no cartão do "Intocável": a coroa clara, o pavilhão azulado, o brilho piscando."""
        c, s = self.canvas, self.s
        x0, y0, x1, y1 = box
        rnd = random.Random(11)
        for i in range(9):
            x, y = rnd.uniform(x0 + 16 * s, x1 - 16 * s), rnd.uniform(y0 + 12 * s, y1 - 12 * s)
            w = rnd.uniform(4.0, 7.5) * s
            y += math.sin(k * 2.0 + i) * 2 * s
            tw = 0.55 + 0.45 * math.sin(k * 3.1 + i * 1.7)
            a = fade * (0.35 + 0.65 * tw)
            c.create_polygon(x - w, y - 0.25 * w, x - 0.55 * w, y - 0.8 * w, x + 0.55 * w, y - 0.8 * w, x + w,
                             y - 0.25 * w, fill=mix(bg, "#e0f2fe", a), outline=mix(bg, "#7dd3fc", a))
            c.create_polygon(x - w, y - 0.25 * w, x + w, y - 0.25 * w, x, y + 1.1 * w,
                             fill=mix(bg, "#38bdf8", a), outline=mix(bg, "#7dd3fc", a))
            c.create_line(x - 0.3 * w, y - 0.25 * w, x, y + 1.1 * w, fill=mix(bg, "#bae6fd", a))
            if tw > 0.9:
                c.create_text(x + 0.7 * w, y - 0.9 * w, text="✦", fill=mix(bg, "#ffffff", fade),
                              font=("Segoe UI Symbol", -int(7 * s)))

    def card_photo(self, card, w, h):
        """A ilustração da carta `card` (a carta inteira, como o jogo mostra) reduzida para w x h, como imagem do Tk;
        guardada por zoom. None sem o jogo ou sem a ilustração (a cena desenha uma carta no lugar)."""
        cache = getattr(self, "_card_photos", None)
        if cache is None or cache[0] != round(self.s, 3):
            cache = self._card_photos = (round(self.s, 3), {})
        key = (card, w, h)
        if key in cache[1]:
            return cache[1][key]
        book = sprites.MONSTERS.book
        art = book.card_art(card) if book is not None and card else None
        if not art:
            return None                         # sem guardar: o jogo pode terminar de carregar depois
        aw, ah, px = art
        w, h = max(1, int(w)), max(1, int(h))
        photo = tk.PhotoImage(master=self.root, data=sprites.png_b64(w, h, sprites.resize(aw, ah, px, w, h)),
                              format="png")
        cache[1][key] = photo
        return photo

    def mob_acts(self, mob, acts, box_w, box_h, direction):
        """{ação: (quadros do Tk, ms por quadro)} de um monstro do jogo numa caixa de box_w x box_h (zoom 1); {} sem
        o desenho."""
        book = sprites.MONSTERS.book
        if book is None or not mob or not book.has(mob):
            return {}
        import ui_parts
        part = book.part(mob)
        out = {}
        for act in acts:
            try:
                made = ui_parts.mob_frames(self.root, part, act, direction, int(box_w * self.s), int(box_h * self.s),
                                           {}) if part is not None else None
            except Exception:  # noqa: BLE001 - sem o desenho: a cena segue sem ele
                made = None
            if made and made[0]:
                out[act] = made
        return out

    def card_scene(self, frames, kind, deal):
        """Monta os desenhos das cenas de carta em `frames` (o d["chase"] do resumo). "deck": "faces" (as cartas do
        leque) e "joker" (o Coringa atirando, virado para o leque). "mvp_card": "big" ({fração da largura: a carta
        girando}), "mid" e "small" (descendo e no palco) e "mob" (o MVP que deixou a carta, de frente, caindo). Só o
        que falta; sem o jogo não monta nada (a cena usa as cartas desenhadas)."""
        if sprites.MONSTERS.book is None:
            return
        s = self.s
        cards = list(deal.get("cards") or [])
        if kind == "deck":
            if "faces" not in frames:
                frames["faces"] = [self.card_photo(cid, DECK_CARD[0] * s, DECK_CARD[1] * s) for cid in cards[:DECK_SHOW]]
            if "joker" not in frames:
                frames["joker"] = self.mob_acts(JOKER_MOB, (sprites.MOB_ATTACK,), 54, 54, 7)
            return
        card = cards[0] if cards else None
        if "big" not in frames and card:
            bw, bh = MVP_BIG[0] * s, MVP_BIG[1] * s
            frames["big"] = {f: self.card_photo(card, bw * f, bh) for f in MVP_FLIPS}
            frames["mid"] = self.card_photo(card, (MVP_BIG[0] + MVP_SMALL[0]) / 2.0 * s,
                                            (MVP_BIG[1] + MVP_SMALL[1]) / 2.0 * s)
            frames["small"] = self.card_photo(card, MVP_SMALL[0] * s, MVP_SMALL[1] * s)
        if "mob" not in frames:
            # só a ação de morrer: o primeiro quadro é ele de pé (com a parada, as duas ações sairiam em escalas
            # diferentes e o monstro "pularia" de tamanho)
            frames["mob"] = self.mob_acts(deal.get("mob"), (sprites.MOB_DIE,), 58, 58, 0)

    def chase_frames(self):
        """{monstro: ([quadros andando para a direita], ms por quadro)} dos bichinhos da "Máquina de abates", do
        data.grf do jogo, guardados por zoom; {} sem o jogo (ou enquanto o bestiário carrega)."""
        cache = getattr(self, "_chase", None)
        key = round(self.s, 3)
        if cache is not None and cache[0] == key:
            return cache[1]
        book = sprites.MONSTERS.book
        if book is None:
            return {}
        import ui_parts
        out = {}
        for mob in CHASE_MOBS:
            try:
                part = book.part(mob) if book.has(mob) else None
                made = ui_parts.mob_frames(self.root, part, sprites.MOB_WALK, 6, int(34 * self.s), int(30 * self.s),
                                           {}) if part is not None else None
            except Exception:  # noqa: BLE001 - sem o desenho: o bichinho desenhado entra no lugar
                made = None
            if made and made[0]:
                out[mob] = made
        self._chase = (key, out)
        return out

    def rider_frames(self):
        """O Cavaleiro no Peco Peco andando para a direita com a lança na mão, das peças do jogo (o guarda-roupa da
        aba Visuais): o corpo e a cabeça andando (as pernas do Peco correndo) e a lança da pose em guarda (andando o
        jogo não desenha a arma), presa pela âncora da cabeça de cada passo para subir e descer junto. Reduzido para o
        cartão: ([(foto, x da origem, y da origem)], ms por quadro), guardado por zoom; None sem o guarda-roupa."""
        cache = getattr(self, "_rider", None)
        key = round(self.s, 3)
        if cache is not None and cache[0] == key:
            return cache[1]
        w = sprites.LOADER.wardrobe
        if w is None:
            return None
        got = None
        try:
            order, body, _missing = w.parts(CHASE_RIDER, 6)
            weapon = next((p for p in order if p.name == "weapon"), None)
            rest = [p for p in order if p is not weapon]
            walk = body.act.frames(sprites.WALK * 8 + 6)
            ready = body.act.frames(LANCE_POSE * 8 + 6)
            lance = sprites.compose([weapon], body, LANCE_POSE, 6, 0) if weapon is not None and ready else None
            first = sprites.compose(rest, body, sprites.WALK, 6, 0) if walk else None
            if first is not None:
                f = 42 * self.s / float(first[1])
                frames = []
                for i in range(len(walk)):
                    img = first if i == 0 else sprites.compose(rest, body, sprites.WALK, 6, i)
                    if img is None:
                        continue
                    if lance is not None and walk[i][1] and ready[0][1]:
                        aw, ar = walk[i][1][0], ready[0][1][0]
                        img = merge_rgba(img, lance, aw[0] - ar[0], aw[1] - ar[1])
                    wd, ht, px, ox, oy = img
                    tw, th = max(1, int(round(wd * f))), max(1, int(round(ht * f)))
                    photo = tk.PhotoImage(master=self.root, data=sprites.png_b64(tw, th, sprites.resize(wd, ht, px, tw,
                                                                                                    th)), format="png")
                    frames.append((photo, ox * f, oy * f))
                delay = body.act.delays[sprites.WALK * 8 + 6] if len(body.act.delays) > sprites.WALK * 8 + 6 else 100
                got = (frames, delay or 100.0) if frames else None
        except Exception:  # noqa: BLE001 - sem o desenho: o aventureiro desenhado entra no lugar
            got = None
        self._rider = (key, got)
        return got

    def fight_assets(self, fight, kind):
        """Os desenhos da cena de luta de um cartão de dano, do jogo: o lutador (o visual de quem grava, se for de uma
        classe de punho, ou o Mestre) nas ações da cena, virado para a direita; o monstro (o da sessão, ou um Poring)
        parado, apanhando e caindo, virado para o lutador; e os números de dano. Guardados por (visual, monstro, cena,
        zoom); None sem o guarda-roupa do jogo."""
        look = fight.get("look") or FIGHTER
        mob = fight.get("mob")
        key = (repr(sorted(look.items())), mob, kind, round(self.s, 3))
        cache = getattr(self, "_fight", None)
        if cache is not None and cache[0] == key:
            return cache[1]
        w, book = sprites.LOADER.wardrobe, sprites.MONSTERS.book
        if w is None:
            return None
        out = dict(acts={}, mob={}, digits=None, photos={}, star=look.get("job") in STAR_JOBS)
        try:
            look, body_h = self.scene_look(w, look)
            ref = w.render(look, sprites.IDLE, 6, 0)
            f = 42 * self.s / float(body_h or ref[1]) if ref else None
            for act in FIGHT_ACTS[kind]:
                r0 = w.render(look, act, 6, 0) if f else None
                if r0 is None:
                    continue
                frames = []
                for i in range(r0[6]):
                    r = r0 if i == 0 else w.render(look, act, 6, i)
                    if r is None:
                        continue
                    wd, ht, px, ox, oy = r[:5]
                    tw, th = max(1, int(round(wd * f))), max(1, int(round(ht * f)))
                    photo = tk.PhotoImage(master=self.root, data=sprites.png_b64(tw, th, sprites.resize(wd, ht, px, tw,
                                                                                                    th)), format="png")
                    frames.append((photo, ox * f, oy * f))
                if frames:
                    out["acts"][act] = (frames, r0[5] or 100.0)
        except Exception:  # noqa: BLE001 - sem o lutador: os socos desenhados entram no lugar
            out["acts"] = {}
        if not out["acts"]:
            self._fight = (key, None)
            return None
        if book is not None:
            import ui_parts
            target = mob if mob and book.has(mob) else (FIGHT_DUMMY if book.has(FIGHT_DUMMY) else None)
            part = book.part(target) if target else None
            for action in (sprites.MOB_IDLE, sprites.MOB_HURT, sprites.MOB_DIE):
                try:
                    made = ui_parts.mob_frames(self.root, part, action, 2, int(42 * self.s), int(40 * self.s), {}) \
                        if part is not None else None
                except Exception:  # noqa: BLE001 - sem o desenho do monstro: o Poring desenhado
                    made = None
                if made and made[0]:
                    out["mob"][action] = made
            try:
                out["digits"] = book.digits()
            except Exception:  # noqa: BLE001 - sem os números do jogo: os escritos
                out["digits"] = None
        self._fight = (key, out)
        return out

    @staticmethod
    def scene_look(w, look):
        """O visual para a cena: sem as peças muito maiores que o corpo (o chapéu-aura de dragão, as capas gigantes),
        que no palco pequeno engoliriam o personagem; e a altura do corpo com a cabeça, que dá a escala.
        (visual, altura) — altura None se não der para medir."""
        order, body, _missing = w.parts(look, 6)
        if body is None:
            return look, None
        b = sprites.compose([body], body, sprites.IDLE, 6, 0)
        if b is None:
            return look, None
        out = dict(look)
        for p in order:
            if p is not body and p.name in ("top", "mid", "low", "robe"):
                r = sprites.compose([p], body, sprites.IDLE, 6, 0)
                if r and (r[1] > BIG_PART[0] * b[1] or r[0] > BIG_PART[1] * b[0]):
                    out[p.name] = 0
        head = next((p for p in order if p.name == "cabeça"), None)
        bh = sprites.compose([body, head] if head else [body], body, sprites.IDLE, 6, 0)
        return out, (bh[1] if bh else b[1])

    def digit_photos(self, assets, tint, zoom):
        """Os dígitos 0 a 9 do jogo como imagens do Tk, na cor (`tint`, ou brancos) e no zoom pedidos, todos da mesma
        altura (no arquivo o 0, o 1 e o 2 vêm um pouco menores)."""
        key = (tint, zoom)
        got = assets["photos"].get(key)
        if got is None:
            height = max(h for _w, h, _px in assets["digits"])
            got = []
            for w, h, px in assets["digits"]:
                if h != height:
                    nw = max(1, int(round(w * height / float(h))))
                    px, w, h = sprites.resize(w, h, px, nw, height), nw, height
                if tint:
                    px = [(r * tint[0] // 255, g * tint[1] // 255, b * tint[2] // 255, a) for r, g, b, a in px]
                photo = tk.PhotoImage(master=self.root, data=sprites.png_b64(w, h, px), format="png")
                got.append(photo.zoom(zoom) if zoom > 1 else photo)
            assets["photos"][key] = got
        return got

    def draw_number(self, x, y, value, assets, tint=None, zoom=1):
        """Um número de dano centrado em x, com a base em y: os dígitos do jogo (sprite 숫자) encostados como no jogo;
        sem eles, escrito em branco com contorno."""
        text = "%d" % int(value)
        c = self.canvas
        if assets.get("digits"):
            photos = self.digit_photos(assets, tint, zoom)
            widths = [photos[int(ch)].width() for ch in text]
            xx = x - (sum(widths) - (len(text) - 1) * zoom) / 2.0
            for ch, wd in zip(text, widths):
                c.create_image(xx, y, anchor="sw", image=photos[int(ch)])
                xx += wd - zoom
            return
        font = ("Arial Black", -int(11 * self.s * zoom))
        fill = "#%02x%02x%02x" % tint if tint else "#ffffff"
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            c.create_text(x + dx * self.s, y + dy * self.s, text=text, anchor="s", font=font, fill="#000000")
        c.create_text(x, y, text=text, anchor="s", font=font, fill=fill)

    def draw_fight(self, kind, k, box, fade, fight, bg, col):
        """A cena de luta no pé do cartão. "combo" (Maior DPS): o lutador emenda os ataques e o monstro apanha sem
        parar, com um monte de números (de vez em quando um crítico amarelo). "heavy" (Maior golpe): carrega com uma
        aura dourada e dá um golpe só, com o número grande, um clarão e o monstro cambaleando. "asura" (one shot):
        carrega com as esferas espirituais girando, avança, acerta com o número enorme, o monstro cai e a tela racha.
        False se os desenhos do jogo não estiverem prontos (quem chamou desenha os socos de antes)."""
        assets = self.fight_assets(fight, kind)
        if assets is None:
            return False
        c, s = self.canvas, self.s
        x0, y0, x1, y1 = box
        base = y1 - 8 * s
        tx = x0 + (x1 - x0) * 0.70
        ax = tx - 50 * s
        acts, mobs = assets["acts"], assets["mob"]
        hit = float(fight.get("hit") or 0) or 99999
        avg = float(fight.get("avg") or 0) or hit * 0.3
        rnd = random.Random(31)

        def frame_of(act, t, ms=None, loop=True):
            frames, delay = acts[act]
            i = int(t * 1000.0 / (ms or delay))
            return frames[i % len(frames) if loop else min(i, len(frames) - 1)]

        def mob_photo(action, t, loop=True):
            photos, delay = mobs[action]
            i = int(t * 1000.0 / max(40.0, delay))
            return photos[i % len(photos) if loop else min(i, len(photos) - 1)]

        def put(photo_ox_oy, x, y):
            photo, ox, oy = photo_ox_oy
            c.create_image(x - ox, y - oy, anchor="nw", image=photo)

        mob_h = 34 * s
        numbers = []                                # (quando, valor, cor, zoom, deslocamento)
        mob_state, mob_t, shake, knock = sprites.MOB_IDLE, k, 0.0, 0.0
        impact_x, impact_y = tx - 12 * s, base - 20 * s
        if kind == "boss_down":                     # combo no chefe; no golpe final ele cai
            final = BOSS_FALL_S
            if k < final - 0.3:
                seq = [a for a in (ATK2, ATK3) if a in acts] or list(acts)
                lengths = [len(acts[a][0]) * 0.08 for a in seq]
                t = (k % sum(lengths)) if k > 0 else 0.0
                for a, ln in zip(seq, lengths):
                    if t < ln or a == seq[-1]:
                        put(frame_of(a, t, 80.0), ax, base)
                        break
                    t -= ln
            elif ATK1 in acts:
                put(frame_of(ATK1, k - (final - 0.3), loop=False), ax, base)
            for i in range(9):                      # golpes até o final
                ti = 0.4 + 0.33 * i
                if ti > k or ti > final - 0.35:
                    break
                numbers.append((ti, avg * rnd.uniform(0.75, 1.25), None, 1, ((i % 3) - 1) * 12 * s))
                if k - ti < 0.16:
                    mob_state, mob_t = sprites.MOB_HURT, k - ti
                    self.draw_burst(impact_x, impact_y, 6 * s, 8, mix(bg, "#ffffff", fade), mix(bg, "#f97316", fade))
            if k >= final:
                t = k - final
                mob_state, mob_t = sprites.MOB_DIE, t
                shake = math.sin(t * 70) * 3 * s * max(0.0, 1 - t / 0.4)
                numbers.append((final, hit or avg * 3, CRIT_TINT, 2, 0.0))
                if t < 0.5:
                    u = t / 0.5
                    self.draw_burst(impact_x, impact_y, (12 + 16 * u) * s, 12, mix(bg, "#fde047", fade * (1 - u)),
                                    mix(bg, "#f97316", fade * (1 - u)))
        elif kind == "combo":
            seq = [a for a in (ATK2, ATK3) if a in acts] or list(acts)
            ms = 70.0
            lengths = [len(acts[a][0]) * ms / 1000.0 for a in seq]
            cycle = sum(lengths)
            t = (k - 0.15) % cycle if k > 0.15 else 0.0
            for a, ln in zip(seq, lengths):
                if t < ln or a == seq[-1]:
                    put(frame_of(a, t, ms), ax, base)
                    break
                t -= ln
            for i in range(18):                     # um golpe a cada 0,3 s; os números saem em três colunas
                ti = 0.35 + 0.3 * i
                if ti > k or ti > SESSION_FX_S - 0.8:
                    break
                crit = i % 4 == 3
                value = avg * rnd.uniform(0.75, 1.25) * (1.4 if crit else 1.0)
                numbers.append((ti, value, CRIT_TINT if crit else None, 1, ((i % 3) - 1) * 12 * s + rnd.uniform(-2, 2) * s))
                if k - ti < 0.16:
                    mob_state, mob_t = sprites.MOB_HURT, k - ti
                    self.draw_burst(impact_x, impact_y + rnd.uniform(-6, 6) * s, (6 if not crit else 9) * s, 8,
                                    mix(bg, "#fde047" if crit else "#ffffff", fade), mix(bg, "#f97316", fade))
        else:
            charge = 1.2 if kind == "heavy" else 1.1
            strike = charge + (0.0 if kind == "heavy" else 0.18)
            impact = charge + 0.3 if kind == "heavy" else strike
            if k < charge:                          # carregando: a aura dourada (e as esferas no Asura)
                g = min(1.0, k / charge)
                cx_, cy_ = ax, base - 22 * s
                for j in range(3):
                    r = (14 + 6 * j + 2 * math.sin(k * 16 + j)) * s * (0.7 + 0.5 * g)
                    c.create_oval(cx_ - r, cy_ - r * 1.25, cx_ + r, cy_ + r * 1.25,
                                  outline=mix(bg, ("#fde68a", "#fbbf24", "#f59e0b")[j], fade * g * (0.85 - 0.2 * j)),
                                  width=max(1, int(2 * s)))
                if kind == "asura":                 # as esferas espirituais (ou estrelinhas, na linha estelar)
                    for j in range(5):
                        a = k * 5 + j * 2 * math.pi / 5
                        ox_, oy_ = cx_ + math.cos(a) * 20 * s, cy_ + math.sin(a) * 9 * s - 6 * s
                        if assets.get("star"):
                            c.create_text(ox_, oy_, text="★", font=("Segoe UI Symbol", -int(9 * s)),
                                          fill=mix(bg, ("#fde047", "#c084fc")[j % 2], fade))
                        else:
                            c.create_oval(ox_ - 3 * s, oy_ - 3 * s, ox_ + 3 * s, oy_ + 3 * s,
                                          fill=mix(bg, "#fde047", fade), outline=mix(bg, "#f59e0b", fade))
                if CAST in acts:
                    put(frame_of(CAST, k), ax, base)
                elif ATK1 in acts:
                    put(frame_of(ATK1, 0.0), ax, base)
            elif kind == "asura" and k < strike:    # o avanço
                u = (k - charge) / (strike - charge)
                x = ax + (tx - 24 * s - ax) * u
                for j in (-14, -8, -2):
                    c.create_line(x - 46 * s, base + j * s - 10 * s, x - 14 * s, base + j * s - 10 * s,
                                  fill=mix(bg, "#fde68a", 0.7 * fade), width=max(1, int(1.5 * s)))
                if ATK1 in acts:
                    put(frame_of(ATK1, 0.3, loop=False), x, base)
            else:                                   # o golpe e depois
                x = tx - 24 * s if kind == "asura" else ax
                if ATK1 in acts:
                    put(frame_of(ATK1, k - strike, loop=False), x, base)
            if k >= impact:
                t = k - impact
                shake = math.sin(t * 70) * 3 * s * max(0.0, 1 - t / 0.4)
                if kind == "heavy":
                    knock = 7 * s * math.exp(-t * 4) * min(1.0, t / 0.08)
                    if t < 0.45:
                        mob_state, mob_t = sprites.MOB_HURT, t
                    numbers.append((impact, hit, CRIT_TINT, 2, 0.0))
                    if t < 0.5:
                        u = t / 0.5
                        self.draw_burst(impact_x, impact_y, (12 + 18 * u) * s, 12, mix(bg, "#fde047", fade * (1 - u)),
                                        mix(bg, "#f97316", fade * (1 - u)))
                else:
                    mob_state, mob_t = sprites.MOB_DIE, t
                    numbers.append((impact, hit, SHOT_TINT, 2, 0.0))
                    if t < 0.35:
                        c.create_polygon(round_rect_pts(x0 + 3 * s, y0 + 3 * s, x1 - 3 * s, y1 - 3 * s, 8 * s),
                                         smooth=True, fill=mix(bg, "#fff7ed", 0.6 * (1.0 - t / 0.35)), outline="")
                    if t < 1.4:
                        u = t / 1.4
                        self.draw_burst(impact_x, impact_y, (30 - 12 * u) * s, 14, mix(bg, "#fde047", fade * (1 - u)),
                                        mix(bg, "#f97316", fade * (1 - u)))
                for j in range(3):                  # ondas de choque
                    u = t - j * 0.12
                    if 0 <= u < 0.8:
                        r = (12 + (110 if kind == "asura" else 70) * u) * s
                        c.create_oval(impact_x - r, impact_y - r * 0.6, impact_x + r, impact_y + r * 0.6,
                                      outline=mix(bg, col, fade * (1.0 - u / 0.8)), width=max(1, int(3 * s * (1 - u))))
                if kind == "asura" and t > 0.45:
                    self.draw_cracks(impact_x, impact_y, min(1.0, (t - 0.45) / 0.25), box, fade, bg)
        # o monstro (virado para o lutador): parado, apanhando ou caindo
        got = mobs.get(mob_state) or mobs.get(sprites.MOB_IDLE)
        if got:
            photo = mob_photo(mob_state if mob_state in mobs else sprites.MOB_IDLE,
                              mob_t, loop=mob_state == sprites.MOB_IDLE)
            c.create_image(tx + knock + shake, base, anchor="s", image=photo)
            mob_h = photo.height()
        elif mob_state != sprites.MOB_DIE or mob_t < 0.3:
            self.draw_poring(tx + knock + shake, base, CHASE_COLORS[FIGHT_DUMMY], 0.0, fade, bg)
        for ti, value, tint, zoom, dx in numbers:   # os números sobem acima do monstro e somem
            u = (k - ti) / (1.6 if zoom > 1 else 0.7)
            if 0 <= u < 1:
                self.draw_number(tx + dx, base - mob_h - 2 * s - (14 if zoom == 1 else 20) * s * u, value, assets, tint,
                                 zoom)
        return True

    def draw_chase(self, k, box, fade, frames, bg):
        """Os bichinhos atravessam o pé do cartão pulando, fugindo do Cavaleiro no Peco Peco com a lança (os desenhos
        do jogo, que entram assim que ficam prontos; sem o jogo, desenhados aqui)."""
        c, s = self.canvas, self.s
        x0, y0, x1, y1 = box
        if "mobs" not in frames and sprites.MONSTERS.book is not None:
            frames["mobs"] = self.chase_frames()
        if "rider" not in frames and sprites.LOADER.wardrobe is not None:
            frames["rider"] = self.rider_frames()
        mobs = frames.get("mobs") or {}
        base = y1 - 9 * s
        lead = x0 - 40 * s + ((x1 - x0) + 230 * s) * min(1.0, k / 5.4)
        for i, mob in enumerate(CHASE_MOBS):
            x = lead - (i * 27 + (i % 2) * 6) * s
            hop = abs(math.sin(k * 7.5 + i * 1.3))
            y = base - hop * 7 * s
            if not x0 + 12 * s < x < x1 - 12 * s:
                continue
            got = mobs.get(mob)
            if got:
                photos, delay = got
                c.create_image(x, y, anchor="s", image=photos[int(k * 1000 / max(40.0, delay)) % len(photos)])
            else:
                self.draw_poring(x, y, CHASE_COLORS[mob], hop, fade, bg)
            if (k * 2 + i) % 1.0 < 0.5:             # gotinhas de suor voando para trás
                u = (k * 2 + i) % 1.0 / 0.5
                c.create_oval(x - 10 * s - 8 * s * u, y - 22 * s - 6 * s * u, x - 7 * s - 8 * s * u,
                              y - 18 * s - 6 * s * u, fill=mix(bg, "#bae6fd", fade * (1 - u)), outline="")
        hx = lead - (len(CHASE_MOBS) * 27 + 46) * s
        rider = frames.get("rider")
        if rider:
            photos, delay = rider
            photo, ox, oy = photos[int(k * 1000 / max(40.0, delay)) % len(photos)]
            if x0 + 4 * s < hx - ox and hx - ox + photo.width() < x1 - 4 * s:
                c.create_image(hx - ox, base + 2 * s - oy, anchor="nw", image=photo)
        elif x0 + 14 * s < hx < x1 - 14 * s:
            self.draw_hero(hx, base, k, fade, bg)

    def draw_card_back(self, cx, cy, w, h, f, bg, fade=1.0):
        """O verso de uma carta do baralho com o meio em (cx, cy): vinho com filete e losango dourados; a largura vezes
        |f| (a carta virando no ar: 0 = de lado)."""
        c, s = self.canvas, self.s
        hw = max(0.6 * s, w * abs(f) / 2.0)
        wine, gold, shade = (mix(bg, col, fade) for col in CARD_BACK)
        c.create_rectangle(cx - hw + s, cy - h / 2 + s, cx + hw + s, cy + h / 2 + s, fill=shade, outline="")
        c.create_rectangle(cx - hw, cy - h / 2, cx + hw, cy + h / 2, fill=wine, outline=gold, width=max(1, int(s)))
        if hw > 5 * s:                              # o filete de dentro e o losango (somem com a carta de lado)
            c.create_rectangle(cx - hw + 2.5 * s, cy - h / 2 + 2.5 * s, cx + hw - 2.5 * s, cy + h / 2 - 2.5 * s,
                               outline=mix(bg, CARD_BACK[1], 0.5 * fade))
            m = min(hw * 0.5, w * 0.24)
            c.create_polygon(cx, cy - h * 0.2, cx + m, cy, cx, cy + h * 0.2, cx - m, cy, fill=gold, outline="")

    def draw_card_face(self, cx, cy, w, h, photo, bg, gold=False, fade=1.0):
        """A frente de uma carta: a ilustração do jogo; sem ela, uma carta desenhada (moldura prateada ou dourada)."""
        if photo is not None:
            self.canvas.create_image(cx, cy, image=photo)
            return
        c, s = self.canvas, self.s
        frame = mix(bg, "#fbbf24" if gold else "#d1d5db", fade)
        c.create_rectangle(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2, fill=mix(bg, "#fef3c7", fade), outline=frame,
                           width=max(1, int(2 * s)))
        c.create_rectangle(cx - w / 2 + 3 * s, cy - h / 2 + 6 * s, cx + w / 2 - 3 * s, cy + h / 2 - 4 * s,
                           fill=mix(bg, "#a7f3d0" if not gold else "#fde68a", fade), outline="")
        c.create_oval(cx - w * 0.22, cy - h * 0.12, cx + w * 0.22, cy + h * 0.2, fill=mix(bg, "#f472b6", fade),
                      outline="")

    def draw_shine(self, left, top, right, bottom, x, slant, color, width):
        """Um risco de luz na diagonal passando por cima de uma carta, cortado nas bordas dela: de (x, top) a
        (x - slant, bottom)."""
        if x - slant > right or x < left:
            return
        a = (x, top) if x <= right else (right, top + (x - right) / slant * (bottom - top))
        b = (x - slant, bottom) if x - slant >= left else (left, top + (x - left) / slant * (bottom - top))
        if a[1] < b[1]:
            self.canvas.create_line(a[0], a[1], b[0], b[1], fill=color, width=max(1, int(width)))

    def draw_deck(self, k, box, fade, deal, frames, bg, col):
        """"Mão de cartas": o Coringa (do jogo) embaralha (as metades se separam e as cartas caem intercaladas no
        meio), depois atira as cartas da sessão uma a uma; cada uma vira no ar e pousa num leque mostrando a ilustração
        dela. No fim, um brilho passa pelo leque e o total aparece em cima do baralho."""
        c, s = self.canvas, self.s
        x0, y0, x1, y1 = box
        if "faces" not in frames or "joker" not in frames:
            self.card_scene(frames, "deck", deal)          # o jogo terminou de carregar depois do resumo
        cards = list(deal.get("cards") or [])
        faces = frames.get("faces") or []
        n = max(1, min(len(cards), DECK_SHOW))
        total = deal.get("n") or len(cards)
        cw, ch = DECK_CARD[0] * s, DECK_CARD[1] * s
        base = y1 - 7 * s                                   # o chão do palco
        cy = base - ch / 2 - 2 * s
        # o Coringa à esquerda: atira enquanto embaralha e distribui
        jx = x0 + 33 * s
        joker = (frames.get("joker") or {}).get(sprites.MOB_ATTACK)
        if joker:
            photos, delay = joker
            busy = DECK_SHUFFLE[0] <= k < DECK_DEAL[1]
            i = int((k - DECK_SHUFFLE[0]) * 1000 / delay) % len(photos) if busy else 0
            c.create_image(jx, base + 2 * s, anchor="s", image=photos[i])
        # o baralho, à direita do Coringa
        dx, dy = x0 + 74 * s, cy + 3 * s
        bw, bh = 20 * s, 27 * s
        fly = 0.42
        step = (DECK_DEAL[1] - DECK_DEAL[0] - fly) / max(1, n - 1)
        launched = sum(1 for i in range(n) if k >= DECK_DEAL[0] + i * step)
        grow = min(1.0, k / DECK_SHUFFLE[0]) if k < DECK_SHUFFLE[0] else 1.0
        if DECK_SHUFFLE[0] <= k < DECK_SHUFFLE[1]:          # embaralhando: duas vezes
            p = (k - DECK_SHUFFLE[0]) / (DECK_SHUFFLE[1] - DECK_SHUFFLE[0]) * 2.0
            cyc = p % 1.0
            split = math.sin(min(1.0, cyc / 0.22) * math.pi / 2) if cyc < 0.82 else max(0.0, 1 - (cyc - 0.82) / 0.18)
            off = 12 * s * split
            for j in range(3):                              # as duas metades, um pouco erguidas
                self.draw_card_back(dx - off - j * 0.6 * s, dy - 3 * s * split - j * s, bw, bh, 1.0, bg, fade)
                self.draw_card_back(dx + off + j * 0.6 * s, dy - 3 * s * split - j * s, bw, bh, 1.0, bg, fade)
            if 0.22 <= cyc < 0.82:                          # as cartas caindo intercaladas no meio
                q = (cyc - 0.22) / 0.6
                for j in range(10):
                    u = (q - j * 0.085) / 0.16
                    if 0 <= u <= 1:
                        side = -1 if j % 2 == 0 else 1
                        x = dx + side * off * (1 - u)
                        y = dy - 3 * s * split - math.sin(u * math.pi) * 9 * s + 3 * s * u
                        self.draw_card_back(x, y, bw, bh, 0.95, bg, fade)
        else:                                               # o monte, mais baixo a cada carta atirada
            for j in range(max(2, 5 - launched)):
                self.draw_card_back(dx + j * 0.5 * s, dy - j * 1.2 * s, bw * grow, bh * grow, 1.0, bg, fade)
        # o leque: centrado na área à direita do baralho, com as do meio um pouco mais altas
        fx0, fx1 = x0 + 108 * s, x1 - 20 * s
        gap = min(cw + 5 * s, (fx1 - fx0) / max(1, n - 1)) if n > 1 else 0
        start = (fx0 + fx1) / 2 - gap * (n - 1) / 2
        landed_all = DECK_DEAL[0] + (n - 1) * step + fly
        for i in range(n):
            sx = start + gap * i
            sy = cy - 4 * s * math.sin(math.pi * i / max(1, n - 1)) if n > 1 else cy
            tl = DECK_DEAL[0] + i * step
            if k < tl:
                continue
            u = (k - tl) / fly
            if u < 1:                                       # no ar: vira uma volta e meia
                x = dx + (sx - dx) * u
                y = dy + (sy - dy) * u - math.sin(u * math.pi) * 24 * s
                self.draw_card_back(x, y, cw * (0.75 + 0.25 * u), ch * (0.75 + 0.25 * u), math.cos(u * math.pi * 3),
                                    bg, fade)
                continue
            self.draw_card_face(sx, sy, cw, ch, faces[i] if i < len(faces) else None, bg, fade=fade)
            land = k - tl - fly
            if land < 0.3:                                  # pousou: um brilho em volta
                g = land / 0.3 * 7 * s
                c.create_rectangle(sx - cw / 2 - g, sy - ch / 2 - g, sx + cw / 2 + g, sy + ch / 2 + g,
                                   outline=mix(bg, "#ffffff", (1 - land / 0.3) * fade), width=max(1, int(1.5 * s)))
            if i == n - 1 and total > n:                    # as que não couberam
                tx, ty = sx + cw / 2 - 1 * s, sy + ch / 2 - 1 * s
                c.create_polygon(round_rect_pts(tx - 15 * s, ty - 10 * s, tx + 3 * s, ty + 2 * s, 4 * s), smooth=True,
                                 fill=mix(bg, col, fade), outline="")
                c.create_text(tx - 6 * s, ty - 4 * s, text="+%d" % (total - n), fill=mix(bg, CARD_BG, fade),
                              font=(self.fonts["small"].actual("family"), -int(9 * s), "bold"))
        if k > landed_all:                                  # tudo distribuído: o brilho passa e o total aparece
            t = k - landed_all
            if t < 0.9:
                lx = start - cw + (gap * (n - 1) + 2 * cw) * (t / 0.9)
                for i in range(n):
                    sx = start + gap * i
                    sy = cy - 4 * s * math.sin(math.pi * i / max(1, n - 1)) if n > 1 else cy
                    self.draw_shine(sx - cw / 2, sy - ch / 2, sx + cw / 2, sy + ch / 2, lx, 10 * s,
                                    mix(bg, "#ffffff", 0.85 * fade), 2.5 * s)
            pop = min(1.0, t / 0.2) * (1 + 0.25 * math.sin(min(t, 0.6) * 15) * max(0.0, 0.6 - t))
            if pop > 0.05:
                c.create_text(dx, dy - bh / 2 - 9 * s, text="×%d" % total, fill=mix(bg, col, fade),
                              font=(self.fonts["small"].actual("family"), -max(6, int(13 * s * pop)), "bold"))
            twinkle = random.Random(int(k * 8))
            for _i in range(6):                             # estrelinhas em cima do leque
                tx = twinkle.uniform(start - cw / 2, start + gap * (n - 1) + cw / 2)
                ty = twinkle.uniform(cy - ch / 2 - 12 * s, cy - ch / 2 - 2 * s)
                c.create_text(tx, ty, text="✦", fill=mix(bg, twinkle.choice((col, "#ffffff", "#fde68a")),
                                                          fade * twinkle.uniform(0.4, 1.0)),
                              font=("Segoe UI Symbol", -int(twinkle.uniform(6, 10) * s)))

    def mvp_spots(self, box):
        """Onde fica a carta de MVP: (centro na revelação, centro no palco, chão do MVP)."""
        s = self.s
        x0, y0, x1, y1 = box
        cx = (x0 + x1) / 2
        stage = STAGE_HS["mvp_card"] * s
        return (cx, y0 + (y1 - y0) * 0.4), (cx, y1 - stage / 2 - 2 * s), y1 - 10 * s

    def mvp_face(self, frames, f, w, h, cx, cy, bg, fade=1.0):
        """A carta de MVP de frente com a largura vezes f (a montada mais perto); a desenhada, sem o jogo."""
        big = frames.get("big") or {}
        pick = min(MVP_FLIPS, key=lambda v: abs(v - f))
        photo = big.get(pick)
        if photo is not None:
            self.canvas.create_image(cx, cy, image=photo)
        else:
            self.draw_card_face(cx, cy, w * max(0.1, f), h, None, bg, gold=True, fade=fade)

    def draw_rays(self, cx, cy, r, k, n, bg, alpha, spin=0.6):
        """Raios dourados girando atrás de algo em (cx, cy)."""
        c = self.canvas
        for rr, ww, aa in ((r, 0.42, 0.5), (r * 0.6, 0.26, 1.0)):     # o raio longo e fraco, e o curto e forte
            for j in range(n):
                a = k * spin + j * 2 * math.pi / n
                w = math.pi / n * ww
                c.create_polygon(cx, cy, cx + math.cos(a - w) * rr, cy + math.sin(a - w) * rr, cx + math.cos(a + w) * rr,
                                 cy + math.sin(a + w) * rr, fill=mix(bg, MVP_GOLD[0], alpha * aa * (1.0 if j % 2 else 0.6)),
                                 outline="")

    def draw_mvp_reveal(self, k, box, deal, frames, col):
        """"Carta de MVP", por cima do texto: o cartão escurece, um facho dourado desce e o MVP que deixou a carta (do
        jogo, de frente) cai nele, soltando faíscas; a carta sobe girando, se revela com um clarão e raios, com o nome
        embaixo; depois desce para o palco enquanto o escuro escorre e o texto aparece."""
        c, s = self.canvas, self.s
        x0, y0, x1, y1 = box
        if "big" not in frames or "mob" not in frames:
            self.card_scene(frames, "mvp_card", deal)
        (cx, ry), (sx, sy), floor = self.mvp_spots(box)
        dark = "#07080c"
        bw, bh = MVP_BIG[0] * s, MVP_BIG[1] * s
        land = min(1.0, max(0.0, (k - MVP_REVEAL_S) / (MVP_LAND_S - MVP_REVEAL_S)))
        ease = land * land * (3 - 2 * land)
        top = y0 + 2 * s + (y1 - y0) * ease                # o escuro escorre para baixo na descida
        if top < y1 - 4 * s:
            c.create_polygon(round_rect_pts(x0 + 2 * s, top, x1 - 2 * s, y1 - 2 * s, 8 * s), smooth=True, fill=dark,
                             outline="")
            beam = min(1.0, max(0.0, (k - 0.1) / 0.5)) * (1 - ease)
            if beam > 0:                                    # o facho: camadas do largo e fraco ao fino e forte
                bot = top + (floor - top) * min(1.0, max(0.0, (k - 0.1) / 0.5))
                pulse = 1 + 0.08 * math.sin(k * 7)
                for wd, a in ((30, 0.10), (19, 0.18), (10, 0.32), (4, 0.62)):
                    wt, wb = wd * 0.45 * s * pulse, wd * s * pulse
                    c.create_polygon(cx - wt, top, cx + wt, top, cx + wb, bot, cx - wb, bot,
                                     fill=mix(dark, MVP_GOLD[0], a * beam), outline="")
            mob = (frames.get("mob") or {}).get(sprites.MOB_DIE)
            if mob and 0.2 <= k < 1.75 and top < floor - 20 * s:   # o MVP de pé na luz, depois caindo
                photos, delay = mob
                i = 0 if k < 0.8 else min(len(photos) - 1, int((k - 0.8) * 1000 / delay))
                c.create_image(cx, floor, anchor="s", image=photos[i])
            sparks = random.Random(11)
            for j in range(34):                             # faíscas douradas subindo de onde ele caiu
                t = k - 0.8 - sparks.uniform(0.0, 1.4)
                life = sparks.uniform(0.7, 1.3)
                if 0 <= t < life:
                    x = cx + sparks.uniform(-26, 26) * s + math.sin(t * 5 + j) * 3 * s
                    y = floor - 8 * s - sparks.uniform(40, 90) * s * t
                    if y > top + 3 * s:
                        r = sparks.uniform(0.8, 1.8) * s
                        c.create_oval(x - r, y - r, x + r, y + r, fill=mix(dark, sparks.choice(MVP_GOLD),
                                                                            (1 - t / life) * (1 - ease)), outline="")
        if k < MVP_SPIN[0]:
            return
        if k < MVP_SPIN[1]:                                 # sobe girando: duas voltas, cada vez mais devagar
            u = (k - MVP_SPIN[0]) / (MVP_SPIN[1] - MVP_SPIN[0])
            spin = 4 * math.pi * (1 - (1 - u) ** 3)
            rise = 1 - (1 - min(1.0, u / 0.7)) ** 2
            px, py = cx, (floor - 30 * s) + (ry - (floor - 30 * s)) * rise
            f = math.cos(spin)
            if u < 0.5:                                     # pequena e rápida: só o verso aparece
                sc = 0.45 + 0.55 * u / 0.5
                self.draw_card_back(px, py, bw * sc, bh * sc, f, dark)
            elif f >= 0:
                self.mvp_face(frames, f, bw, bh, px, py, dark)
            else:
                self.draw_card_back(px, py, bw, bh, f, dark)
            return
        t = k - MVP_SPIN[1]
        if k < MVP_REVEAL_S:                                # revelada: raios atrás, clarão, brilhos e o nome
            self.draw_rays(cx, ry, 78 * s, k, 16, dark, 0.34)
            if t < 0.5:                                     # o clarão: um halo claro atrás da carta e riscos de luz
                g = t / 0.5
                e = (5 + 16 * g) * s
                c.create_polygon(round_rect_pts(cx - bw / 2 - e, ry - bh / 2 - e, cx + bw / 2 + e, ry + bh / 2 + e,
                                                10 * s), smooth=True, fill=mix(dark, "#fff3c4", 0.9 * (1 - g)),
                                 outline="")
                for j in range(8):
                    a = j * math.pi / 4 + math.pi / 8
                    r0, r1 = bh * 0.5, bh * (0.62 + 0.55 * g)
                    c.create_line(cx + math.cos(a) * r0, ry + math.sin(a) * r0, cx + math.cos(a) * r1,
                                  ry + math.sin(a) * r1, fill=mix(dark, "#ffffff", 1 - g), width=max(1, int(2 * s)))
            self.mvp_face(frames, 1.0, bw, bh, cx, ry, dark)
            twinkle = random.Random(int(k * 9))
            for _i in range(10):
                a, r = twinkle.uniform(0, 2 * math.pi), twinkle.uniform(0.62, 0.95) * bh
                c.create_text(cx + math.cos(a) * r * 0.9, ry + math.sin(a) * r * 0.62, text="✦",
                              fill=mix(dark, twinkle.choice(MVP_GOLD), twinkle.uniform(0.5, 1.0)),
                              font=("Segoe UI Symbol", -int(twinkle.uniform(7, 12) * s)))
            name = deal.get("name")
            if name and t > 0.05:
                font = (self.fonts["small"].actual("family"), -int(11 * s), "bold")
                a = min(1.0, (t - 0.05) / 0.15)
                c.create_text(cx + s, ry + bh / 2 + 11 * s, text=name, fill=mix(dark, "#000000", a), font=font)
                c.create_text(cx, ry + bh / 2 + 10 * s, text=name, fill=mix(dark, MVP_GOLD[1], a), font=font)
            return
        # descendo para o palco, encolhendo (as três montadas: grande, meio, pequena)
        px, py = cx + (sx - cx) * ease, ry + (sy - ry) * ease
        if ease < 0.35:
            self.mvp_face(frames, 1.0, bw, bh, px, py, dark)
        else:
            photo = frames.get("mid") if ease < 0.7 else frames.get("small")
            size = (MVP_BIG[0] + MVP_SMALL[0]) / 2.0 if ease < 0.7 else MVP_SMALL[0]
            hsize = (MVP_BIG[1] + MVP_SMALL[1]) / 2.0 if ease < 0.7 else MVP_SMALL[1]
            self.draw_card_face(px, py, size * s, hsize * s, photo, CARD_BG, gold=True)

    def draw_mvp_stage(self, k, box, fade, deal, frames, bg):
        """"Carta de MVP", no palco: a carta pousada com os raios dourados girando atrás, um brilho holográfico
        passando por ela de tempos em tempos, estrelinhas em volta e fogos dos dois lados."""
        c, s = self.canvas, self.s
        x0, y0, x1, y1 = box
        if "small" not in frames:
            self.card_scene(frames, "mvp_card", deal)
        _r, (sx, sy), _f = self.mvp_spots(box)
        w, h = MVP_SMALL[0] * s, MVP_SMALL[1] * s
        t = k - MVP_LAND_S
        self.draw_rays(sx, sy, 40 * s, k, 10, bg, 0.30 * fade, 0.8)
        self.draw_card_face(sx, sy, w, h, frames.get("small"), bg, gold=True, fade=fade)
        p = (t % 1.3) / 0.55                                # o brilho holográfico: um risco claro e um colorido
        if p < 1:
            lx = sx - w / 2 - 6 * s + (w + 22 * s) * p
            self.draw_shine(sx - w / 2, sy - h / 2, sx + w / 2, sy + h / 2, lx, 12 * s, mix(bg, "#ffffff", 0.9 * fade),
                            2.5 * s)
            self.draw_shine(sx - w / 2, sy - h / 2, sx + w / 2, sy + h / 2, lx - 5 * s, 12 * s,
                            mix(bg, "#a5f3fc", 0.6 * fade), 1.5 * s)
        twinkle = random.Random(int(k * 8))
        for _i in range(8):
            a, r = twinkle.uniform(0, 2 * math.pi), twinkle.uniform(0.75, 1.15)
            c.create_text(sx + math.cos(a) * w * r, sy + math.sin(a) * h * 0.55 * r, text="✦",
                          fill=mix(bg, twinkle.choice(MVP_GOLD), fade * twinkle.uniform(0.4, 1.0)),
                          font=("Segoe UI Symbol", -int(twinkle.uniform(6, 10) * s)))
        stage_top = y1 - STAGE_HS["mvp_card"] * s
        for tb, fx, fy in ((0.25, x0 + 52 * s, stage_top + 16 * s), (0.95, x1 - 52 * s, stage_top + 12 * s),
                           (1.65, x0 + 88 * s, stage_top + 10 * s), (2.1, x1 - 86 * s, stage_top + 18 * s)):
            u = t - tb                                      # fogos: uma explosão de faíscas que cai
            if not 0 <= u < 0.9:
                continue
            spark = random.Random(int(tb * 100))
            for j in range(18):
                a = j * 2 * math.pi / 18 + spark.uniform(-0.1, 0.1)
                r = 24 * s * (1 - (1 - min(1.0, u / 0.6)) ** 2) * spark.uniform(0.75, 1.1)
                x = fx + math.cos(a) * r
                y = fy + math.sin(a) * r + 14 * s * u * u
                if x0 + 4 * s < x < x1 - 4 * s and stage_top < y < y1 - 4 * s:
                    tail = 3 * s * (1 - u)
                    c.create_line(x - math.cos(a) * tail, y - math.sin(a) * tail, x, y,
                                  fill=mix(bg, spark.choice(MVP_GOLD + ("#fb923c",)), fade * (1 - u / 0.9)),
                                  width=max(1, int(1.6 * s)))

    def draw_poring(self, x, y, color, hop, fade, bg):
        """Um bichinho de geleia (o Poring e a família dele) de pé em (x, y): a gota, o brilho, olhos e a boquinha
        aberta de susto. hop: 0 no chão (achatado) a 1 no alto."""
        c, s = self.canvas, self.s
        sq = 1.0 - hop
        w, h = 10 * s * (1 + 0.15 * sq), 9 * s * (1 - 0.15 * sq)
        edge = "#" + "".join("%02x" % int(int(color[i:i + 2], 16) * 0.65) for i in (1, 3, 5))
        c.create_polygon(x, y - 2.3 * h, x + 0.55 * w, y - 1.75 * h, x + w, y - 0.9 * h, x + 0.85 * w, y,
                         x - 0.85 * w, y, x - w, y - 0.9 * h, x - 0.55 * w, y - 1.75 * h, smooth=True,
                         fill=mix(bg, color, fade), outline=mix(bg, edge, fade), width=max(1, int(s)))
        c.create_oval(x - 0.62 * w, y - 1.65 * h, x - 0.2 * w, y - 1.25 * h, fill=mix(bg, "#ffffff", 0.85 * fade),
                      outline="")
        eye = mix(bg, "#1f2937", fade)
        for ex in (x + 0.12 * w, x + 0.55 * w):
            c.create_oval(ex - 1.3 * s, y - 1.25 * h, ex + 0.5 * s, y - 0.8 * h, fill=eye, outline="")
        c.create_oval(x + 0.28 * w, y - 0.62 * h, x + 0.5 * w, y - 0.35 * h, fill=mix(bg, "#7f1d1d", fade), outline="")

    def draw_hero(self, x, y, k, fade, bg):
        """Um aventureiro correndo para a direita com a espada no alto (o "jogador" da Máquina de abates)."""
        c, s = self.canvas, self.s
        skin, hair = mix(bg, "#fcd9b6", fade), mix(bg, "#8b5a2b", fade)
        tunic, dark, steel = mix(bg, "#3b82f6", fade), mix(bg, "#1e3a8a", fade), mix(bg, "#e5e7eb", fade)
        run = math.sin(k * 15)
        bob = abs(run) * 1.5 * s
        y -= bob
        for side in (1, -1):                        # pernas
            a = 0.7 * run * side
            c.create_line(x, y - 9 * s, x + math.sin(a) * 9 * s, y - (1 - math.cos(a)) * 3 * s + bob, fill=dark,
                          width=max(2, int(2.6 * s)), capstyle="round")
        c.create_polygon(round_rect_pts(x - 5 * s, y - 21 * s, x + 5 * s, y - 8 * s, 3 * s), smooth=True,
                         fill=tunic, outline=dark)
        c.create_line(x - 2 * s, y - 17 * s, x - 7 * s - run * 3 * s, y - 11 * s, fill=skin,
                      width=max(2, int(2.2 * s)), capstyle="round")
        sw = -1.1 + 0.55 * math.sin(k * 9)         # a espada balançando no alto
        hx, hy = x + 3 * s, y - 18 * s
        hand = (hx + math.cos(sw) * 7 * s, hy + math.sin(sw) * 7 * s)
        c.create_line(hx, hy, hand[0], hand[1], fill=skin, width=max(2, int(2.2 * s)), capstyle="round")
        tip = (hand[0] + math.cos(sw - 0.5) * 16 * s, hand[1] + math.sin(sw - 0.5) * 16 * s)
        c.create_line(hand[0], hand[1], tip[0], tip[1], fill=steel, width=max(2, int(2.4 * s)))
        gx, gy = math.cos(sw - 0.5 + math.pi / 2) * 3 * s, math.sin(sw - 0.5 + math.pi / 2) * 3 * s
        c.create_line(hand[0] - gx, hand[1] - gy, hand[0] + gx, hand[1] + gy, fill=mix(bg, "#fbbf24", fade),
                      width=max(2, int(2 * s)))
        c.create_oval(x - 5.5 * s, y - 32 * s, x + 5.5 * s, y - 21 * s, fill=skin, outline=dark)
        c.create_arc(x - 6 * s, y - 33 * s, x + 6 * s, y - 22 * s, start=15, extent=190, style="chord", fill=hair,
                     outline="")
        c.create_oval(x + 1.8 * s, y - 27.5 * s, x + 3.3 * s, y - 25.5 * s, fill=dark, outline="")

    def draw_session_bar(self, pct, cx, cy, xl, xr, col, k):
        """A barra do nível do "Quase lá", com o % ao lado; `k` (o tempo da animação): um brilho corre por ela."""
        c, s = self.canvas, self.s
        label = dec("%.1f%%" % pct)
        lw = self.fonts["small"].measure(label) + 6 * s
        bw = max(40 * s, min(220 * s, (xr - xl) - lw))
        bx0 = cx - (bw + lw) / 2
        bx1 = bx0 + bw
        c.create_polygon(round_rect_pts(bx0, cy - 4 * s, bx1, cy + 4 * s, 4 * s), smooth=True,
                         fill=mix(CARD_BG, col, 0.18), outline="")
        fw = bw * max(0.0, min(100.0, pct)) / 100.0
        if fw > 8 * s:
            c.create_polygon(round_rect_pts(bx0, cy - 4 * s, bx0 + fw, cy + 4 * s, 4 * s), smooth=True, fill=col,
                             outline="")
            if k is not None:                       # o brilho corre da esquerda para a direita
                sx = bx0 + ((k * 0.8) % 1.0) * fw
                c.create_rectangle(sx, cy - 3 * s, min(sx + 12 * s, bx0 + fw - 2 * s), cy + 3 * s,
                                   fill=mix(col, "#ffffff", 0.55), outline="")
        c.create_text(bx1 + 6 * s, cy, anchor="w", text=label, font=self.fonts["small"], fill=col)

    def draw_session_chips(self, hls, cy, xl, xr):
        """Os selos dos destaques que não viraram título, centralizados; os que não cabem ficam de fora."""
        c, s = self.canvas, self.s
        font = self.fonts["small"]
        gap = 5 * s
        shown, total = [], 0.0
        for h in hls:
            w = font.measure(h["chip"]) + 14 * s
            if total + w + (gap if shown else 0) > xr - xl:
                break
            total += w + (gap if shown else 0)
            shown.append((h, w))
        x = (xl + xr) / 2 - total / 2
        for h, w in shown:
            c.create_polygon(round_rect_pts(x, cy - 8 * s, x + w, cy + 8 * s, 8 * s), smooth=True,
                             fill=mix(CARD_BG, h["color"], 0.2), outline=mix(CARD_BG, h["color"], 0.75))
            c.create_text(x + w / 2, cy, text=h["chip"], font=font, fill=mix("#ffffff", h["color"], 0.35))
            x += w + gap

    def draw_session_fx(self, kind, k, box, col, title_y, origin, tag=None, chase=None, bg=CARD_BG, fight=None,
                        deal=None):
        """A animação do destaque principal nos primeiros SESSION_FX_S do resumo (atrás do texto): confete (do alto e
        dos cantos), moedinhas que se empilham (ganhou muito) ou que caem do emblema (gastou muito), estrelas piscando
        (Milagre), brilhos em volta do título, ondas saindo do emblema, chuva ou a moldura pulsando. As peças saem
        sempre da mesma semente: de um quadro para o outro só o tempo muda."""
        c, s = self.canvas, self.s
        x0, y0, x1, y1 = box
        fade = 1.0 if k < SESSION_FX_S - 1.5 else max(0.0, (SESSION_FX_S - k) / 1.5)
        rnd = random.Random(7)
        if kind in ("lucky", "flash"):              # ondas que saem do emblema (o brilho de uma carta, um golpe)
            ex, ey = origin
            for j in range(3):
                t = k - j * 0.3
                if 0 <= t < 1.2:
                    rx = 12 * s + (x1 - ex - 16 * s) * t / 1.2
                    ry = min(ey - y0 - 4 * s, y1 - ey - 4 * s) * min(1.0, 0.25 + t)
                    a = (1.0 - t / 1.2) * fade
                    c.create_arc(ex - rx, ey - ry, ex + rx, ey + ry, start=-75, extent=150, style="arc",
                                 outline=mix(CARD_BG, col, a), width=max(1, int(2 * s)))
            if kind == "lucky":
                kind = "sparkle"
            else:
                return
        if kind == "confetti":                      # metade cai do alto, metade sai dos dois cantos de baixo
            for i in range(48):
                color = rnd.choice(CONFETTI)
                w, h = rnd.uniform(2.0, 3.5) * s, rnd.uniform(4.5, 7.5) * s
                spin, sway = rnd.uniform(3, 8), rnd.uniform(2.0, 4.0)
                if i % 2:
                    left = i % 4 == 1
                    delay = rnd.uniform(0.0, 0.5)
                    vx = rnd.uniform(50, 150) * s * (1 if left else -1)
                    vy = -rnd.uniform(110, 190) * s
                    t = k - delay
                    if t < 0:
                        continue
                    x = (x0 + 10 * s if left else x1 - 10 * s) + vx * t
                    y = y1 - 8 * s + vy * t + 0.5 * 170 * s * t * t
                else:
                    delay, vx = rnd.uniform(0.3, 2.0), rnd.uniform(-18, 18) * s
                    vy, xs = rnd.uniform(30, 70) * s, rnd.uniform(x0 + 8 * s, x1 - 8 * s)
                    t = k - delay
                    if t < 0:
                        continue
                    x = xs + vx * t + math.sin(t * sway + i) * 6 * s
                    y = y0 + 4 * s + vy * t + 26 * s * t * t
                if not (y0 + 3 * s < y < y1 - 5 * s and x0 + 3 * s < x < x1 - 3 * s):
                    continue
                a = t * spin + i
                ca, sa = math.cos(a), math.sin(a)
                pts = []
                for px, py in ((-w, -h), (w, -h), (w, h), (-w, h)):
                    pts += [x + px * ca - py * sa, y + px * sa + py * ca]
                c.create_polygon(pts, fill=mix(CARD_BG, color, fade), outline="")
        elif kind == "rain":                        # a sessão difícil: chuvinha caindo de lado
            for i in range(64):
                xs, delay = rnd.uniform(x0, x1 + 40 * s), rnd.uniform(0.0, 1.2)
                speed = rnd.uniform(150, 220) * s
                t = (k - delay) % 1.3 if k >= delay else -1
                if t < 0:
                    continue
                y = y0 + 6 * s + speed * t
                x = xs - 0.35 * speed * t
                if y > y1 - 8 * s or x < x0 + 6 * s or x > x1 - 4 * s:
                    continue
                c.create_line(x, y, x - 4 * s, y + 11 * s, fill=mix(CARD_BG, "#93c5fd", 0.8 * fade),
                              width=max(1, int(1.4 * s)))
        elif kind == "coins_stack":                 # ganhou: moedinhas caem e se empilham em montinhos no pé do cartão
            floor, th, g = y1 - 10 * s, 3.0 * s, 520 * s
            rx, ry = 7.5 * s, 2.6 * s
            piles = 6
            xs = [x0 + 20 * s + (x1 - x0 - 40 * s) * (j + 0.5) / piles for j in range(piles)]
            height = [0] * piles
            coins = []
            for i in range(34):                     # a ordem de chegada: cada moeda pousa em cima da anterior
                j = rnd.randrange(piles)
                coins.append((0.15 + i * 0.085 + rnd.uniform(0.0, 0.06), j, height[j], rnd.uniform(5, 9)))
                height[j] += 1
            for delay, j, level, spin in coins:
                t = k - delay
                if t < 0:
                    continue
                x, top = xs[j], floor - level * th
                fall = math.sqrt(2 * max(1.0, top - (y0 + 6 * s)) / g)
                if t < fall:                        # caindo e girando
                    y, r = y0 + 6 * s + 0.5 * g * t * t, 5.5 * s
                    w = max(1.0 * s, r * abs(math.cos(t * spin)))
                    c.create_oval(x - w, y - r, x + w, y + r, fill=mix(CARD_BG, "#fbbf24", fade),
                                  outline=mix(CARD_BG, "#b45309", fade), width=max(1, int(s)))
                    continue
                # na pilha: a borda (mais escura) e a face de cima
                c.create_oval(x - rx, top - ry + 1.6 * s, x + rx, top + ry + 1.6 * s,
                              fill=mix(CARD_BG, "#b45309", fade), outline="")
                c.create_oval(x - rx, top - ry, x + rx, top + ry, fill=mix(CARD_BG, "#fbbf24", fade),
                              outline=mix(CARD_BG, "#d97706", fade), width=max(1, int(s)))
                if t - fall < 0.25:                 # brilho de quando pousa
                    c.create_line(x - rx * 0.5, top - ry * 0.2, x + rx * 0.2, top - ry * 0.2,
                                  fill=mix(CARD_BG, "#fff7d6", fade), width=max(1, int(s)))
        elif kind == "coins_down":                  # gastou: saem do emblema e caem pelo pé do cartão
            ex, ey = origin
            for i in range(22):
                delay = rnd.uniform(0.0, 2.4)
                spin, r = rnd.uniform(6, 11), rnd.uniform(4.5, 6.5) * s
                vx, vy = rnd.uniform(10, 170) * s, -rnd.uniform(40, 110) * s
                t = k - delay
                if t < 0:
                    continue
                x = ex + vx * t
                y = ey + vy * t + 0.5 * 320 * s * t * t
                if y > y1 - 4 * s or not x0 + 4 * s < x < x1 - 4 * s:
                    continue
                a = fade * min(1.0, max(0.0, (y1 - 4 * s - y) / (18 * s)))
                turn = abs(math.cos(t * spin + i))
                rx = max(1.0 * s, r * turn)
                c.create_oval(x - rx, y - r, x + rx, y + r, fill=mix(CARD_BG, "#fbbf24", a),
                              outline=mix(CARD_BG, "#b45309", a), width=max(1, int(s)))
                if turn > 0.45:
                    c.create_line(x - rx * 0.35, y - r * 0.5, x - rx * 0.35, y + r * 0.25,
                                  fill=mix(CARD_BG, "#fef3c7", a), width=max(1, int(s)))
        elif kind == "jabs":                        # golpes e dano: a luva sai da esquerda, bate e volta, várias vezes
            rows = (y1 - 34 * s, y1 - 20 * s)    # no palco, no pé do cartão
            reach = x1 - x0 - 118 * s
            for i in range(5):
                t = k - (0.3 + i * 0.6)
                if not 0 <= t < 0.6:
                    continue
                e = (t / 0.16) ** 0.7 if t < 0.16 else (1.0 if t < 0.26 else max(0.0, 1.0 - (t - 0.26) / 0.34))
                gy = rows[i % 2]
                gx = x0 + 38 * s + reach * e
                if t < 0.17:                        # riscos de velocidade atrás da luva
                    for j in (-6, 0, 6):
                        c.create_line(gx - 44 * s, gy + j * s, gx - 30 * s, gy + j * s,
                                      fill=mix(bg, "#ffffff", 0.45 * fade), width=max(1, int(s)))
                if 0.14 < t < 0.36:                 # o impacto na frente da luva
                    u = (t - 0.14) / 0.22
                    self.draw_burst(gx + 15 * s, gy, (9 + 9 * u) * s, 10, mix(bg, "#fde047", fade * (1 - u)),
                                    mix(bg, "#f97316", fade * (1 - u)))
                self.draw_fist(gx, gy, 1.0 * s, fade, bg, k)
        elif kind == "one_punch":                   # one shot: o punho toma impulso, atravessa o cartão e explode
            gy = y1 - 26 * s                        # no palco, no pé do cartão
            hit_x = x1 - 46 * s
            if k < 0.9:                             # o impulso: recua, cresce, treme e junta a aura dourada
                g = min(1.0, k / 0.9)
                gx = x0 + 58 * s - 8 * s * g + math.sin(k * 70) * 1.6 * s * g     # o punho não passa da borda
                for j in range(3):
                    r = (16 + 7 * j + 3 * math.sin(k * 18 + j)) * s * (0.6 + 0.6 * g)
                    c.create_oval(gx - 8 * s - r * 1.3, gy - r, gx - 8 * s + r * 1.3, gy + r,
                                  outline=mix(bg, ("#fde68a", "#fbbf24", "#f59e0b")[j], fade * g * (0.9 - 0.25 * j)),
                                  width=max(1, int(2 * s)))
                for j in range(8):                  # faíscas subindo
                    u = (k * 1.6 + j / 8.0) % 1.0
                    c.create_text(gx - 30 * s + j * 6 * s, gy + 12 * s - u * 30 * s, text="✦",
                                  font=("Segoe UI Symbol", -int(6 * s)), fill=mix(bg, "#fde68a", fade * g * (1 - u)))
                self.draw_fist(gx, gy, (0.9 + 0.6 * g) * s, fade, bg, k)
            elif k < 1.05:                          # o soco
                u = (k - 0.9) / 0.15
                gx = x0 + 50 * s + (hit_x - 18 * s - x0 - 50 * s) * u
                for j in (-12, -5, 2, 9):
                    c.create_line(x0 + 10 * s, gy + j * s, gx - 30 * s, gy + j * s,
                                  fill=mix(bg, "#ffffff", 0.5 * fade), width=max(1, int(1.5 * s)))
                self.draw_fist(gx, gy, 1.5 * s, fade, bg, k)
            else:                                   # o impacto: clarão, onda de choque, estrelas e a luva vibrando
                t = k - 1.05
                if t < 0.35:
                    c.create_polygon(round_rect_pts(x0 + 3 * s, y0 + 3 * s, x1 - 3 * s, y1 - 3 * s, 8 * s), smooth=True,
                                     fill=mix(bg, "#fff7ed", 0.6 * (1.0 - t / 0.35)), outline="")
                for j in range(3):
                    u = t - j * 0.12
                    if 0 <= u < 0.9:
                        r = (14 + 120 * u) * s
                        c.create_oval(hit_x - r, gy - r * 0.6, hit_x + r, gy + r * 0.6,
                                      outline=mix(bg, col, fade * (1.0 - u / 0.9)), width=max(1, int(3 * s * (1 - u))))
                if t < 1.6:
                    u = t / 1.6
                    self.draw_burst(hit_x + 6 * s, gy, (34 - 16 * u) * s, 14, mix(bg, "#fde047", fade * (1 - u)),
                                    mix(bg, "#f97316", fade * (1 - u)))
                for j in range(14):                 # estilhaços
                    ang = rnd.uniform(-math.pi, math.pi)
                    sp = rnd.uniform(60, 150) * s
                    if t < 1.2:
                        px = hit_x + math.cos(ang) * sp * t
                        py = gy + math.sin(ang) * sp * t * 0.6 + 60 * s * t * t
                        if x0 + 4 * s < px < x1 - 4 * s and y0 + 4 * s < py < y1 - 4 * s:
                            c.create_text(px, py, text="✦", font=("Segoe UI Symbol", -int(8 * s)),
                                          fill=mix(bg, rnd.choice(("#fde047", "#fb923c", "#ffffff")),
                                                   fade * (1 - t / 1.2)))
                if t > 0.45:                        # depois da onda de choque, a tela racha a partir do impacto
                    self.draw_cracks(hit_x, gy, min(1.0, (t - 0.45) / 0.25), box, fade, bg)
                wob = math.exp(-t * 5) * math.sin(t * 40) * 6 * s
                self.draw_fist(hit_x - 26 * s + wob, gy, 1.5 * s, fade, bg, k)
        elif kind in ("combo", "heavy", "asura", "boss_down"):  # a cena de luta com os desenhos do jogo
            if not self.draw_fight(kind, k, box, fade, fight or {}, bg, col):
                self.draw_session_fx({"asura": "one_punch", "boss_down": "confetti"}.get(kind, "jabs"), k, box, col,
                                     title_y, origin, tag, chase, bg)
            elif kind == "boss_down" and k > BOSS_FALL_S:       # o chefe caiu: confete
                self.draw_session_fx("confetti", k - BOSS_FALL_S, box, col, title_y, origin, tag, chase, bg)
        elif kind == "deck":                        # o Coringa embaralha e distribui as cartas da sessão
            self.draw_deck(k, box, fade, deal or {}, chase if chase is not None else {}, bg, col)
        elif kind == "mvp_card":                    # a carta de MVP no palco (a revelação vem por cima do texto)
            if k >= MVP_LAND_S:
                self.draw_mvp_stage(k, box, fade, deal or {}, chase if chase is not None else {}, bg)
        elif kind == "chase":                       # Porings, Drops, Poporings e Marins fugindo de um cavaleiro
            self.draw_chase(k, box, fade, chase if chase is not None else {}, bg)
        elif kind == "diamonds":                    # o "Intocável": diamantes brilhando no vidro
            self.draw_diamonds(k, box, fade, bg)
        elif kind == "stars":
            twinkle = random.Random(int(k * 10))
            for _i in range(24):
                x, y = twinkle.uniform(x0 + 10 * s, x1 - 10 * s), twinkle.uniform(y0 + 8 * s, y1 - 8 * s)
                size = twinkle.uniform(7, 14) * s
                color = mix(CARD_BG, twinkle.choice(MIRACLE_COLORS), fade * twinkle.uniform(0.35, 0.9))
                c.create_text(x, y, text=twinkle.choice("★✦✧⋆"), fill=color, font=("Segoe UI Symbol", -int(size)))
        elif kind == "sparkle":
            cx = (x0 + x1) / 2
            for i in range(14):
                ang, rx = rnd.uniform(0, 2 * math.pi), rnd.uniform(0.18, 0.48) * (x1 - x0)
                ry, speed = rnd.uniform(6, 24) * s, rnd.uniform(3.0, 6.0)
                pulse = 0.5 + 0.5 * math.sin(k * speed + i)
                x, y = cx + math.cos(ang) * rx, title_y + math.sin(ang) * ry
                c.create_text(x, y, text="✦", fill=mix(CARD_BG, col, fade * (0.25 + 0.75 * pulse)),
                              font=("Segoe UI Symbol", -int((6 + 8 * pulse) * s)))
        elif kind == "glow":
            pulse = 0.5 + 0.5 * math.sin(k * 4.0)
            c.create_polygon(round_rect_pts(x0 + 3 * s, y0 + 3 * s, x1 - 3 * s, y1 - 3 * s, 8 * s), smooth=True,
                             fill="", outline=mix(CARD_BG, col, fade * (0.25 + 0.5 * pulse)),
                             width=max(1, int((1 + 2 * pulse) * s)))
        if tag and kind in ("coins_stack", "coins_down") and k < 3.0:
            # o número flutua ao lado do emblema: subindo (ganhou) ou descendo (gastou)
            ex, ey = origin
            u = min(1.0, k / 3.0)
            up = kind == "coins_stack"
            ty = ey - 4 * s - 14 * s * u if up else ey + 6 * s + 14 * s * u
            c.create_text(ex + 14 * s, ty, anchor="w", text=tag, font=self.fonts["small"],
                          fill=mix(CARD_BG, "#fde68a" if up else "#fca5a5", fade * (1.0 - 0.7 * u)))

    def open_summary(self):
        """Clique no resumo: abre a análise no Dedo Duro, na luta do cartão."""
        card, self.summary_card = self.summary_card, None
        self.dirty = True
        self.open_analysis()
        if self.analysis is not None and card:
            try:
                self.analysis.dd_key = card[0]["key"]
                self.analysis.select_tab("dedo")
                self.analysis.refresh(force=True)
            except Exception:  # noqa: BLE001
                self.log_error(*sys.exc_info())

    def summary_menu(self):
        m = self.new_menu()
        m.add_command(label=_("Abrir o Dedo Duro desta luta…"), command=self.open_summary)
        m.add_command(label=_("Fechar este resumo"), command=lambda: (setattr(self, "summary_card", None),
                                                                     setattr(self, "dirty", True)))
        m.add_command(label=_("Não mostrar mais o resumo da luta"), command=lambda: self.toggle_cfg("fight_summary"))
        return m

    def draw_summary_card(self):
        """Cartão do fim da luta: verde quando o chefe morreu (azul se não), a sua parte do dano e até 3 conclusões
        do Dedo Duro, cada uma com a bolinha da gravidade dela."""
        if not self.summary_card:
            return
        d, shown = self.summary_card
        title = (_("%s: derrotado em %s") % (d["name"], dur(d["ms"]))) if d["killed"] else _("%s: não morreu") % d["name"]
        lines = []
        if d["share"] is not None:
            lines.append((_("Você: %s do dano · %dº de %d") % (dec("%.1f%%" % (100 * d["share"])), d["rank"],
                                                               d["players"]), CARD_WHITE))
        for sev, what, who in d["alerts"]:
            lines.append(("%s %s · %s" % ("●" if sev == 2 else "◐", what, who), "#fca5a5" if sev == 2 else "#fcd34d"))
        more = d["grave"] + d["warn"] - len(d["alerts"])
        if not d["alerts"]:
            lines.append((_("Nada grave nem de atenção no Dedo Duro"), "#4ade80"))
        elif more > 0:
            lines.append((_("mais %d no Dedo Duro (clique para abrir)") % more, CARD_DIM))
        self.draw_card("summary", shown, SUMMARY_CARD_S, "bom" if d["killed"] else "info", title, lines, d.get("sprite"))

    def show_boss_card(self, c, seq, now):
        """Cartão do chefe que mudou; o que chega do mesmo chefe logo depois entra no mesmo cartão."""
        info = getattr(c, "boss_alerts", {}).get(seq)
        if info is None or not cards.enabled(self.cfg, cards.boss_card_key(info)):
            return
        try:
            info = dict(info)
            cur = self.boss_card[0] if self.boss_card else None
            if (cur and cur["aid"] == info["aid"] and 0 <= info["t"] - cur["t"] <= BOSS_MERGE_MS
                    and not info.get("mech") and not cur.get("mech")):
                info = dict(cur, **{k: v for k, v in info.items() if v is not None})
            if info.get("mech"):                  # mecânica: o HP de quem grava dá o tamanho do golpe que mata
                log = c.hp_log.get(c.me) or ()
                info["hp"] = next((hp for _t, hp, _m in reversed(log) if hp), None)
            e = c.entities.get(info["aid"])
            form = info.get("form") or (c.sprite_log[info["aid"]][-1][1] if c.sprite_log.get(info["aid"])
                                        else (e.job if e is not None else 0))
            info["name"] = c.name_of(info["aid"])
            info["job"] = e.job if e is not None else None
            info["sprite"] = ("mob", form) if form else None
            info["mine"] = analysis.my_attack_element(c, info["t"])
            if not info.get("element") and form:          # forma nova: a propriedade dela, se conhecida
                import dedoduro
                known = dedoduro.BOSS_ELEMENTS.get(form) or (
                    (dedoduro.MOB_DB.get(str(form)) or {}).get("e"), (dedoduro.MOB_DB.get(str(form)) or {}).get("l"))
                if known and known[0]:
                    info["form_element"] = known
            sprites.MONSTERS.start(clientdata.NAMES.grf)
            sprites.MONSTERS.image(info["sprite"])
            self.boss_card = (info, now)
        except Exception:  # noqa: BLE001 - o aviso no rodapé continua
            self.log_error(*sys.exc_info())
        self.dirty = True

    def show_death_card(self, c, seq, now):
        """Monta o resumo da morte (fontes de dano nos 5 s antes) para mostrar por cima das linhas."""
        info = getattr(c, "death_alerts", {}).get(seq)
        if info is None:
            return
        try:
            d = analysis.death_card(c, *info)
            # o desenho do topo, lido do data.grf do jogo: a armadilha, o próprio personagem caído (União, vida
            # que caiu sem golpe) ou o monstro do golpe final
            if d["trap"]:
                d["sprite"] = ("trap",)
            elif d["fusion"] or d["no_hit"]:
                d["sprite"] = ("char", tuple(sorted(c.session.look.items())), tuple(sorted(c.worn_at(info[1]).items())))
            elif d.get("sprite_mob"):
                d["sprite"] = ("mob", d["sprite_mob"])
            grf = clientdata.NAMES.grf
            sprites.MONSTERS.start(grf)
            if d.get("sprite") and d["sprite"][0] == "char":
                sprites.LOADER.start(grf)
            sprites.MONSTERS.image(d.get("sprite"))
            self.death_card = (d, now)
        except Exception:  # noqa: BLE001 - o resumo é um extra; o aviso no rodapé continua
            self.log_error(*sys.exc_info())
        self.dirty = True

    def combat(self):
        f = self.watcher.file
        return f.combat if f is not None and f.ready else None

    def tests_waiting(self):
        """Há luta contra o boneco esperando para ser salva sozinha? (a que está em andamento na gravação aberta, ou
        a de uma gravação que o widget deixou de seguir)"""
        if not self.cfg["auto_tests"]:
            return False
        files = [self.watcher.file] + [item[0] for item in self.tests_left.items]
        return any(testes.waiting(self.tests, rf, self.tests_seen) is not None for rf in files)

    def save_waiting_tests(self):
        """Ao fechar: a luta contra o boneco que ainda esperava para ser salva sozinha não se perde mais (desde que a
        gravação já tenha parado)."""
        if not self.cfg["auto_tests"]:
            return
        try:
            self.tests_left.add(self.watcher.file, self.watcher.last_change)
            self.tests_left.step(self.tests, self.tests_seen, time.time(), closing=True)
        except Exception:  # noqa: BLE001
            self.log_error(*sys.exc_info())

    def check_recording(self, now):
        """Lembrete de gravação desligada: o jogo está aberto e nenhum replay está sendo escrito há algum tempo."""
        if not self.cfg.get("alert_rec", True):
            self.rec_seen_at = now
            return
        if now - self.game_check_at >= GAME_CHECK_S:
            self.game_check_at = now
            self.game_on = meter.game_running()
        w = self.watcher
        writing = w.file is not None and not w.pinned and now - w.last_change <= w.ACTIVE_S
        if not self.game_on or writing or w.pinned:
            self.rec_seen_at = now
            self.rec_warned = False
        elif self.rec_off(now) and not self.rec_warned:
            self.rec_warned = True                # uma vez por episódio: o rodapé segue avisando
            self.dirty = True
            if self.cfg.get("rec_sound"):
                play_beep(self.cfg["fusion_volume"])

    def rec_off(self, now):
        return bool(self.cfg.get("alert_rec", True)) and self.game_on and now - self.rec_seen_at > REC_OFF_S

    def status(self):
        """(texto, cor_da_bolinha) do rodapé."""
        t = self.t
        now = time.time()
        w = self.watcher
        if not w.folders:
            return _("Pasta Replay não encontrada"), t["live"], False
        f = w.file
        if self.rec_off(now):
            return _("Gravação desligada: ligue o replay no jogo"), t["live"], True
        if f is None:
            return _("Aguardando gravação de replay…"), t["muted"], False
        if not f.ready:
            if w.pinned:
                return _("Abrindo %s…") % os.path.basename(f.path), t["muted"], False
            # o jogo só preenche a tabela do cabeçalho uns 10 s depois de começar a gravar;
            # nada se perde, a leitura começa do início quando ela aparece
            return _("Gravação começou · aguardando o jogo (~10 s)"), t["live"], True
        if w.pinned:
            return os.path.basename(f.path), t["muted"], False
        if w.recording(now):
            return _("Gravando · %s") % os.path.basename(f.path), t["live"], True
        return _("Gravação encerrada · %s") % os.path.basename(f.path), t["muted"], False

    # ------------------------------------------------------------ desenho

    def draw(self):
        self.dirty = False
        self.last_draw = time.time()
        c = self.canvas
        c.delete("all")
        t = self.t = self.theme()
        s = self.s
        self.W, self.H = W, H = self.size_px()
        self.hits = []
        # o cartão dos efeitos acompanhados só aparece quando nenhum outro cartão está na frente
        self.fx_now = [] if (self.death_card or self.ping_card or self.boss_card or self.summary_card
                             or self.session_card) else self.fx_card_rows()
        self.root.configure(bg=t["bg"])
        c.configure(bg=t["bg"])

        cb = self.combat()
        session = self.cfg["session"]
        enc = None
        if cb is not None and not session:
            enc = cb.encounter(self.enc_back)
            if enc is None and self.enc_back:
                self.enc_back = 0
                enc = cb.encounter(0)
        snap = cb.snapshot(enc, session=session) if cb is not None else None

        # barra de cima: nome do personagem e botões
        x = W - 16 * s
        for key, glyph, color in (("close", self.icon("close"), t["muted"]),
                                  ("min", self.icon("min"), t["muted"]),
                                  ("more", self.icon("more"), t["muted"]),
                                  ("chart", self.icon("chart"), t["muted"]),
                                  ("shot", self.icon("shot"), t["muted"]),
                                  ("pin", self.icon("pin_on" if self.cfg["pinned"] else "pin_off"),
                                   t["accent"] if self.cfg["pinned"] else t["muted"])):
            self.icon_button(key, x, TOP_Y * s, glyph, color)
            x -= 23 * s
        title_right = x + 8 * s
        if cb is not None:
            sess = cb.session
            name = (cb.name_of(cb.me) if meter.HIDE_NAMES else sess.player) or _("Personagem")
            job = meter.job_name(sess.job)
        else:
            name, job = _("Medidor de DPS"), "Ragnarok"
        tx = 12 * s
        tid = c.create_text(tx, TOP_Y * s, anchor="w", text=name, font=self.fonts["title"], fill=t["fg"])
        x1 = c.bbox(tid)[2]
        if job and x1 + 30 * s < title_right:
            jid = c.create_text(x1 + 5 * s, TOP_Y * s + 1 * s, anchor="w", text="· " + job,
                                font=self.fonts["small"], fill=t["muted"])
            if c.bbox(jid)[2] > title_right:
                c.delete(jid)

        # número grande; as linhas da direita têm prioridade, o número encolhe se precisar
        rx = W - 12 * s
        active = self.cfg["rate"] == "active"
        lines = []
        if snap:
            if snap["live"]:
                lines.append((_("agora %s/s") % num(snap["dps_now"]), t["accent"]))
            lines.append((_("total %s") % num(snap["my_total"]), t["fg"]))
            if active:
                lines.append((_("batendo %s") % dur(snap["my_active_ms"]), t["muted"]))
            else:
                label = _("em combate") if session else (_("ao vivo") if snap["live"] else _("duração"))
                lines.append((_("%s %s") % (label, dur(snap["duration_ms"])), t["muted"]))
        lines_w = max([self.fonts["small"].measure(txt) for txt, _c in lines] + [0])
        side = self.side_pins(cb)                 # com um cartão aberto, o que está fixado vem para cá
        if side:
            lines, lines_w = [], self.side_pins_width(side)
        big_text = num(snap["my_adps"] if active else snap["my_dps"]) if snap else "—"
        room = rx - lines_w - 10 * s - 12 * s
        unit_w = self.fonts["unit"].measure("DPS") + 4 * s
        big_font, show_unit = self.fonts["big"], True
        for font, unit in ((self.fonts["big"], True), (self.fonts["big_s"], True), (self.fonts["big_s"], False)):
            big_font, show_unit = font, unit
            if font.measure(big_text) + (unit_w if unit else 0) <= room:
                break
        bid = c.create_text(12 * s, BIG_Y * s, anchor="w", text=big_text, font=big_font, fill=t["fg"])
        if show_unit:
            c.create_text(c.bbox(bid)[2] + 4 * s, BIG_Y * s + 7 * s, anchor="w", text="DPS",
                          font=self.fonts["unit"], fill=t["muted"])
        y0 = BIG_Y * s - (len(lines) - 1) * 7 * s
        for i, (txt, col) in enumerate(lines):
            c.create_text(rx, y0 + i * 14 * s, anchor="e", text=txt, font=self.fonts["small"], fill=col)
        if side:
            self.draw_side_pins(side, rx)

        # abas
        x = 10 * s
        for key, label in TABS:
            x = self.chip(("tab", key), x, label, self.cfg["tab"] == key) + 4 * s
        mode = self.view_label(cb) + " ▾"
        mw = self.fonts["tab"].measure(mode) + 16 * s
        self.chip(("btn", "view"), max(x + 4 * s, W - 10 * s - mw), mode, False, outline=True)

        # faixa das informações fixadas (sempre visível, em qualquer aba; com um cartão aberto ela fica acima dele)
        card_up = (self.death_card or self.ping_card or self.boss_card or self.summary_card or self.session_card
                   or self.fx_now)
        if not card_up:
            self.draw_pins(cb)

        # linhas (o resumo da morte fica por cima delas por alguns segundos)
        self.draw_rows(snap)
        self.tracker_n = 0
        if not card_up:
            self.draw_trackers()              # um cartão ocupa a área inteira: os contadores voltam quando ele sai
        if not self.death_card:
            if self.ping_card:                    # o item marcado que caiu passa na frente dos outros avisos
                self.draw_ping_card()
            else:
                self.draw_boss_card()
                if not self.boss_card:
                    self.draw_summary_card()
                if not self.boss_card and not self.summary_card:
                    self.draw_session_card()
        self.draw_fx_card()
        self.draw_death()
        if self.death_card and self.cfg.get("pins"):
            self.draw_pins(cb, top=TOP_Y + 14)    # o resumo da morte cobre o DPS: a faixa fica logo acima dele

        # rodapé
        fy = H - FOOT_H * s / 2 - 2 * s
        text, dot, live = self.status()
        bx = W - 10 * s
        bx = self.text_button("reset", bx, fy, self.icon("reset"), _("Zerar"))
        if not session and cb is not None:
            encs = len(cb.history) + (1 if cb.current else 0)
            if encs > 1:
                bx = self.icon_button("next", bx - 12 * s, fy, self.icon("next"),
                                      t["fg"] if self.enc_back > 0 else mix(t["bg"], t["muted"], 0.4)) - 12 * s
                bx = self.icon_button("prev", bx - 2 * s, fy, self.icon("prev"),
                                      t["fg"] if self.enc_back < encs - 1 else mix(t["bg"], t["muted"], 0.4)) - 12 * s
                text = _("Luta %d/%d · %s") % (encs - self.enc_back, encs, (snap or {}).get("target") or text)
            elif snap and snap["target"]:
                text = "%s · %s" % (snap["target"], text)
        elif snap and snap["target"]:
            text = "%s · %s" % (snap["target"], text)
        # /where: mapa e coordenadas de quem grava; o clique copia o /navi
        where = cb.where() if cb is not None else None
        if where and where[1] is not None:
            label = "%s %d/%d" % (where[0], where[1], where[2])
            if self.fonts["small"].measure(label) > (bx - 20 * s) * 0.55:
                label = "%d/%d" % (where[1], where[2])
            bx = self.text_button("where", bx - 6 * s, fy, self.icon("where"), label)
        r = 3.2 * s
        pulse = live and self.phase < 4
        color = t["muted"]
        hint = HINTS.get(self.hover[1] if self.hover and self.hover[0] in ("btn", "tab") else
                         (self.hover[0] if self.hover else None))
        if self.hover and self.hover[0] == "fav":
            hint = _("Clique: favorito · botão direito: fixar ou ocultar")
        if hint and not self.alert:
            text, color = hint, t["fg"]
        elif not self.alert and cb is not None and cb.miracle_left() is not None:
            left = cb.miracle_left()
            doubt = cb.miracle_uncertain() is not None        # depois de morrer ou trocar de mapa
            text = (_("★ Milagre? · %d min (a confirmar)") if doubt else _("★ Milagre · %d min")) % max(
                1, round(left / 60000.0))
            color = self.readable("#fbbf24")
            live = True
        elif not self.alert and snap is not None and cb is not None and cb.off_notice() == "now":
            # a luta contada acabou e quem grava segue batendo em monstros comuns: os números à vista são os dela
            text, color = _("Monstros comuns: dano não contado (Opções ⋯)"), self.readable("#f59e0b")
        if self.alert:
            # aviso (buff que acabou, morte) no lugar do status, piscando
            text, kind = self.alert[0], self.alert[1]
            dot = t["live"] if kind in ("death", "fusion") else (
                t["accent"] if kind in ("info", "miracle") else "#f59e0b")
            color = dot
            live = True
            c.create_polygon(round_rect_pts(6 * s, fy - 10 * s, bx - 4 * s, fy + 10 * s, 6 * s), smooth=True,
                             fill=mix(t["bg"], dot, 0.16 if self.phase < 4 else 0.08), outline="")
        c.create_oval(12 * s - r, fy - r, 12 * s + r, fy + r, outline="",
                      fill=dot if not live or pulse else mix(dot, t["bg"], 0.55))
        sid = c.create_text(20 * s, fy, anchor="w", text=text, font=self.fonts["small"], fill=color)
        self.clip_text(sid, text, bx - 6 * s)

        # alça de redimensionar
        self.hits.append((("grip", None), (W - 11 * s, H - 11 * s, W, H)))
        for dx, dy in ((0, 0), (4, 0), (0, 4)):
            gx, gy, rr = W - (4 + dx) * s, H - (4 + dy) * s, max(0.8, 1.0 * s)
            c.create_oval(gx - rr, gy - rr, gx + rr, gy + rr, fill=mix(t["bg"], t["muted"], 0.6), outline="")
        self.paint_hover()
        self.draw_miracle()

    def draw_miracle(self):
        """Faixa dourada com estrelas quando o Milagre ativa (alguns segundos)."""
        k = time.time() - self.miracle_at
        if not 0 <= k < MIRACLE_BANNER_S:
            return
        c, t, s, W, H = self.canvas, self.t, self.s, self.W, self.H
        grow = min(1.0, k / 0.35)                              # abre rápido
        fade = 1.0 if k < MIRACLE_BANNER_S - 1.2 else max(0.0, (MIRACLE_BANNER_S - k) / 1.2)
        cy = H * 0.42
        hh = 34 * s * grow
        gold = MIRACLE_COLORS[int(k * 8) % 3]
        fill = mix(t["bg"], "#4c1d95", 0.85 * fade)
        c.create_polygon(round_rect_pts(8 * s, cy - hh, W - 8 * s, cy + hh, 10 * s), smooth=True, fill=fill,
                         outline=mix(t["bg"], gold, fade), width=max(2, int(2 * s)))
        if grow < 1:
            return
        rnd = random.Random(int(k * 12))                       # estrelas que piscam
        for _i in range(28):
            x, y = rnd.uniform(14 * s, W - 14 * s), rnd.uniform(cy - hh + 4 * s, cy + hh - 4 * s)
            size = rnd.uniform(7, 15) * s
            col = mix(t["bg"], rnd.choice(MIRACLE_COLORS), fade * rnd.uniform(0.45, 1.0))
            c.create_text(x, y, text=rnd.choice("★✦✧⋆"), fill=col, font=("Segoe UI Symbol", -int(size)))
        c.create_text(W / 2, cy - 8 * s, text=_("★ MILAGRE ★"), fill=mix(t["bg"], "#fde68a", fade),
                      font=self.fonts["big_s"])
        c.create_text(W / 2, cy + 18 * s, text=_("todos os monstros são alvos estelares por 1 hora"),
                      fill=mix(t["bg"], "#f5f3ff", fade), font=self.fonts["small"])

    # ------------------------------------------------------------ resumo da morte

    def death_texts(self, d):
        """(causa, overkill, resumo) do resumo da morte, já no idioma da pessoa."""
        kill = next((g for g in d["sources"] if g["killing"]), None)
        if d["trap"]:
            cause = _("Armadilha do mapa") + (_(" (~%d%% do HP máx.)") % round(d["trap_pct"] * 100)
                                              if d["trap_pct"] else "")
        elif d["fusion"]:
            cause = _("União Solar: atacou com %s de HP") % (
                "%d%%" % round(d["hp_pct"] * 100) if d["hp_pct"] is not None else _("pouco"))
        elif d["special"] == "offscreen":
            cause = _("Provável golpe de %s fora da tela · sobrecarga há %d s") % (
                d["killer"], round(d["overload_ms"] / 1000.0))
        elif kill is not None and not d["unclear"]:
            cause = _("Golpe final: %s") % self.source_label(dict(kill, count=1))
            el = analysis.element_name(kill["element"])
            if el:
                cause += " · " + el
        elif d["no_hit"]:
            cause = _("Sem golpe visível: a vida caiu sem um ataque no replay")
        elif kill is not None:
            # o golpe visível sozinho não bastava (ex.: reflexo da Dor Máxima): fica com quem bateu por último
            cause = _("Último golpe visível: %s") % self.source_label(dict(kill, count=1))
        elif d["unclear"]:
            cause = _("Causa incerta: o último golpe visível não bastava")
        else:
            cause = ""
        over = (_("overkill %s") % num(d["overkill"])) if d["overkill"] and not d["fusion"] else ""
        secs = d["window"] / 1000.0          # 5 s, ou menos se a vida voltou a 95% no meio do caminho
        span = ("%d s" % round(secs)) if secs >= 4.95 else dec("%.1f s" % secs)
        summary = (_("%s em %d golpe nos últimos %s") if d["hits"] == 1 else _("%s em %d golpes nos últimos %s")) % (
            num(d["total"]), d["hits"], span)
        if d["max_hp"]:
            summary += " · " + _("HP máx. %s") % num(d["max_hp"])
        return cause, over, summary

    def source_label(self, g):
        """'Monstro ×N · skill' (armadilha e HP sem golpe só com o nome)."""
        who = g["source"] + (" ×%d" % g["count"] if g["count"] > 1 else "")
        return "%s · %s" % (who, g["skill"]) if g["element"] is not None or g["count"] else who

    def shown_sources(self, d, n):
        """As n maiores fontes, sempre com a do golpe final (no lugar da última, se ela não couber)."""
        out = d["sources"][:max(0, n)]
        kill = next((g for g in d["sources"] if g["killing"]), None)
        if out and kill is not None and kill not in out:
            out[-1] = kill
        return out

    def draw_death(self):
        """Resumo da morte (10 s, clique fecha): o widget escurece com uma moldura vermelha e um cartão no meio
        mostra o monstro que deu o golpe final, a causa e quem mais bateu nos 5 s antes, com a propriedade do ataque."""
        if not self.death_card:
            return
        d, shown = self.death_card
        k = time.time() - shown
        if not 0 <= k < DEATH_CARD_S:
            return
        c, s, W, H = self.canvas, self.s, self.W, self.H
        left = 1.0 - k / DEATH_CARD_S
        x0, x1 = 8 * s, W - 8 * s
        y0, y1 = (TOP_Y + 14 + self.pin_shift()) * s, H - (FOOT_H + 2) * s
        pad = 10 * s
        white, dim = "#ffffff", "#d79a9a"
        fw = max(2, int(3 * s))                # moldura vermelha em volta do widget
        c.create_rectangle(fw / 2, fw / 2, W - fw / 2, H - fw / 2, outline=DEATH_RED, width=fw)
        c.create_polygon(round_rect_pts(x0, y0, x1, y1, 10 * s), smooth=True, fill=DEATH_CARD_BG,
                         outline=DEATH_RED, width=max(1, int(1.5 * s)))
        self.hits.append((("death", None), (x0, y0, x1, y1)))
        cause, over, summary = self.death_texts(d)

        refl = d.get("reflected")             # Dor Máxima: o golpe que foi refletido ganha uma linha

        def text_h(n):                     # título + causa (+ reflexo) + fontes + resumo
            return (26 + 16 + (14 if refl else 0) + 17 * n + 16 + 8) * s
        # o sprite do monstro fica com o espaço que sobra; sem monstro (União, sem golpe visível...), uma caveira
        spec = d.get("sprite")
        want = sprites.MONSTERS.expected(spec)
        n = min(4, len(d["sources"]))
        # uma 4ª fonte só entra se o sprite continuar grande; senão, menos fontes antes de encolher o sprite
        while n > 1 and (y1 - y0) - pad - text_h(n) < (80 if n > 3 else 44) * s:
            n -= 1
        sprite_h = min((80 if want else 56) * s, (y1 - y0) - pad - text_h(n))
        if sprite_h < 30 * s:
            sprite_h = 0
        y = y0 + pad
        cid = c.create_text(x1 - pad, y + 5 * s, anchor="e", text="%d s  ✕" % max(1, round(left * DEATH_CARD_S)),
                            font=self.fonts["small"], fill=dim)
        if sprite_h:
            cx, foot = (x0 + x1) / 2, y + sprite_h
            c.create_oval(cx - 34 * s, foot - 5 * s, cx + 34 * s, foot + 3 * s, fill="#3a0f0f", outline="")
            room_w = (x1 - x0) - 2 * pad - 2 * (c.bbox(cid)[2] - c.bbox(cid)[0])
            if want:
                photo = self.sprite_photo(spec, int(sprite_h), int(room_w))
                if photo is not None:
                    c.create_image(cx, foot, anchor="s", image=photo)
            else:
                r = sprite_h * 0.40
                self.draw_skull(cx, foot - r * 1.15, r)
            y = foot + 4 * s
        nth = d.get("nth", 1)
        title = DEATH_TITLES[min(nth, len(DEATH_TITLES)) - 1]
        if "%d" in title:
            title = title % nth
        self.draw_death_title((x0 + x1) / 2, y + 13 * s, x0 + pad, x1 - pad, icon=want or not sprite_h, title=title)
        if nth > 1:                            # contador no canto: caveira ×N
            self.draw_skull(x0 + pad + 5 * s, y0 + pad + 5 * s, 5 * s)
            c.create_text(x0 + pad + 13 * s, y0 + pad + 5 * s, anchor="w", text="×%d" % nth,
                          font=self.fonts["small"], fill="#fca5a5")
        y += 26 * s
        line = cause + ("  ·  " + over if over else "")
        lid = c.create_text((x0 + x1) / 2, y + 7 * s, text=line, font=self.fonts["small"], fill=white)
        if c.bbox(lid)[2] - c.bbox(lid)[0] > x1 - x0 - 2 * pad:
            c.itemconfigure(lid, anchor="w")
            c.coords(lid, x0 + pad, y + 7 * s)
            self.clip_text(lid, line, x1 - pad)
        y += 16 * s
        if refl:
            rtext = _("↩ refletiu %s · %s · %s") % (refl["skill"], _("você") if refl["mine"] else refl["who"],
                                                     num(refl["dmg"]))
            rid = c.create_text((x0 + x1) / 2, y + 5 * s, text=rtext, font=self.fonts["small"], fill="#fca5a5")
            if c.bbox(rid)[2] - c.bbox(rid)[0] > x1 - x0 - 2 * pad:
                c.itemconfigure(rid, anchor="w")
                c.coords(rid, x0 + pad, y + 5 * s)
                self.clip_text(rid, rtext, x1 - pad)
            y += 14 * s
        top = d["sources"][0]["dmg"] if d["sources"] else 1
        row_h = 17 * s
        heat = ("#dc2626", "#ea580c", "#d97706", "#a16207")     # do vermelho ao âmbar, pela posição
        for i, g in enumerate(self.shown_sources(d, n)):
            ry0, ry1 = y + 1 * s, y + row_h - 2 * s
            col = ELEMENT_COLORS.get(g["element"] or "", "#9ca3af")
            frac = g["dmg"] / float(top or 1)
            bx0, bx1 = x0 + pad - 3 * s, x1 - pad + 3 * s
            bw = (bx1 - bx0) * frac
            # barra: a maior fonte em vermelho, as seguintes em laranja e âmbar
            c.create_polygon(round_rect_pts(bx0, ry0, bx1, ry1, 4 * s), smooth=True, fill="#2a0b0b", outline="")
            if bw > 2 * s:
                c.create_polygon(round_rect_pts(bx0, ry0, bx0 + bw, ry1, 4 * s), smooth=True,
                                 fill=mix(DEATH_CARD_BG, heat[min(i, len(heat) - 1)], 0.55), outline="")
            cy = (ry0 + ry1) / 2
            r = 3.2 * s
            c.create_oval(x0 + pad + 2 * s - r, cy - r, x0 + pad + 2 * s + r, cy + r, fill=col, outline="")
            rid = c.create_text(x1 - pad, cy, anchor="e", text="%d%%" % round(g["share"] * 100),
                                font=self.fonts["small"], fill=dim)
            vid = c.create_text(c.bbox(rid)[0] - 6 * s, cy, anchor="e", text=num(g["dmg"]), font=self.fonts["small"],
                                fill=white)
            el = analysis.element_name(g["element"])
            label = ("✝ " if g["killing"] else "") + self.source_label(g) + ("  (%s)" % el if el else "")
            lid = c.create_text(x0 + pad + 9 * s, cy, anchor="w", text=label, font=self.fonts["small"], fill=white)
            self.clip_text(lid, label, c.bbox(vid)[0] - 6 * s)
            y += row_h
        sid = c.create_text((x0 + x1) / 2, y1 - 13 * s, text=summary, font=self.fonts["small"], fill=dim)
        if c.bbox(sid)[2] - c.bbox(sid)[0] > x1 - x0 - 2 * pad:
            c.itemconfigure(sid, anchor="w")
            c.coords(sid, x0 + pad, y1 - 13 * s)
            self.clip_text(sid, summary, x1 - pad)
        # contagem regressiva: linha que encolhe na borda de baixo
        c.create_line(x0 + 10 * s, y1 - 3 * s, x0 + 10 * s + (x1 - x0 - 20 * s) * left, y1 - 3 * s,
                      fill=DEATH_RED, width=max(2, int(2 * s)))

    def draw_death_title(self, cx, cy, xl, xr, icon=True, title=None):
        """O título ('V O C Ê  M O R R E U') com as letras espaçadas entre duas linhas finas, e a caveira à
        esquerda; um título comprido demais para espaçar sai com as letras juntas."""
        c, s = self.canvas, self.s
        title = title or _("VOCÊ MORREU")
        f = self.fonts["spaced"]
        room = xr - xl - (26 * s if icon else 0) - 2 * 18 * s
        spaced = " ".join(title).replace("   ", "  ")
        if f.measure(spaced) > room:
            spaced = title
        tw = f.measure(spaced)
        c.create_text(cx, cy, text=spaced, font=f, fill="#fca5a5")
        gap = 10 * s
        line = mix(DEATH_CARD_BG, DEATH_RED, 0.8)
        c.create_line(xl + (26 * s if icon else 0), cy, cx - tw / 2 - gap, cy, fill=line, width=1)
        c.create_line(cx + tw / 2 + gap, cy, xr, cy, fill=line, width=1)
        if icon:                               # sem a caveira grande no topo, uma pequena ao lado do título
            self.draw_skull(xl + 10 * s, cy, 9 * s)

    def draw_skull(self, cx, cy, r):
        """Caveira desenhada (crânio, olhos, nariz e dentes), branca com contorno vermelho."""
        c, s = self.canvas, self.s
        bone, line, hole = "#f5f5f4", "#b91c1c", DEATH_CARD_BG
        c.create_oval(cx - r, cy - r * 1.05, cx + r, cy + r * 0.7, fill=bone, outline=line, width=max(1, int(s)))
        c.create_polygon(round_rect_pts(cx - r * 0.55, cy + r * 0.25, cx + r * 0.55, cy + r * 1.05, r * 0.25),
                         smooth=True, fill=bone, outline=line, width=max(1, int(s)))
        for side in (-1, 1):
            ex = cx + side * r * 0.42
            c.create_oval(ex - r * 0.27, cy - r * 0.2, ex + r * 0.27, cy + r * 0.3, fill=hole, outline="")
        c.create_polygon(cx, cy + r * 0.32, cx - r * 0.13, cy + r * 0.55, cx + r * 0.13, cy + r * 0.55, fill=hole)
        for tx in (-0.2, 0.0, 0.2):
            c.create_line(cx + tx * r, cy + r * 0.72, cx + tx * r, cy + r * 1.0, fill=hole, width=1)

    def sprite_photo(self, spec, max_h, max_w):
        """O desenho do resumo (monstro, armadilha ou personagem caído, do data.grf do jogo) do tamanho pedido;
        None enquanto carrega ou se não houver."""
        img = sprites.MONSTERS.image(spec)
        if img is None or max_h < 8 or max_w < 8:
            return None
        w, h, px = img
        f = min(max_h / float(h), max_w / float(w), 2.0)
        tw, th = max(1, int(round(w * f))), max(1, int(round(h * f)))
        key = (repr(spec), tw, th)
        if key in self.sprite_photos:
            return self.sprite_photos[key]
        if len(self.sprite_photos) > 40:
            self.sprite_photos = {}
        try:
            px2 = px if (tw, th) == (w, h) else sprites.resize(w, h, px, tw, th)
            photo = tk.PhotoImage(master=self.root, data=sprites.png_b64(tw, th, px2), format="png")
        except (tk.TclError, ValueError, IndexError, ZeroDivisionError):
            photo = None                       # desenho estranho: o cartão aparece sem o sprite
        self.sprite_photos[key] = photo
        return photo

    def clip_text(self, item, text, max_x):
        c = self.canvas
        if c.bbox(item)[2] <= max_x:
            return
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo + hi + 1) // 2
            c.itemconfigure(item, text=text[:mid] + "…")
            if c.bbox(item)[2] <= max_x:
                lo = mid
            else:
                hi = mid - 1
        c.itemconfigure(item, text=(text[:lo] + "…") if lo < len(text) else text)

    def draw_rows(self, snap):
        c, s, t = self.canvas, self.s, self.t
        W = self.W
        n = self.cfg["rows"]
        tab = self.cfg["tab"]
        y = self.rows_y0() * s
        msg = None
        rows = []
        # Drops e XP não dependem do dano contado: com "Contar dano em: só MVPs e bonecos" num mapa de monstros
        # comuns não há encontro nenhum, e os itens e a XP continuam valendo
        if snap is None and not (tab in ("drops", "xp") and self.combat() is not None):
            f = self.watcher.file
            if f is not None and f.ready and f.combat.off_notice():
                # batendo em monstros comuns com "Contar dano em: só MVPs e bonecos": diz por que não há números
                msg = (_("Dano em monstros comuns não é contado."), _("Para contar: Opções ⋯ › Contar dano em"))
            elif f is not None and f.ready and f.combat.was_reset:
                msg = (_("Zerado."), _("O próximo dano começa um encontro novo."))
            elif f is not None and f.ready:
                msg = (_("Nenhum dano ainda."), _("Ataque algo enquanto grava o replay."))
            elif not self.watcher.folders:
                # sem pasta Replay: um clique no meio abre a escolha da pasta do jogo
                msg = (_("Não achei a pasta Replay do jogo."), _("Clique aqui e escolha a pasta do Ragnarok."))
            else:
                folders = self.watcher.folders
                where = short_path(folders[0]) if len(folders) == 1 else _("%d pastas Replay") % len(folders)
                msg = (_("No jogo, comece a gravar um replay."), _("Olhando em %s") % where)
        elif tab == "group":
            players = snap["players"]
            shown = players[:n]
            me = next((p for p in players if p["me"]), None)
            if me is not None and me not in shown and n > 1:
                shown = shown[:n - 1] + [me]
            top = players[0]["total"] if players else 1
            for p in shown:
                rank = players.index(p) + 1
                pct = "%.0f%%" % (p["share"] * 100)
                rate = p["adps"] if self.cfg["rate"] == "active" else p["dps"]
                if self.cfg["show_pct"]:
                    right = pct
                elif self.base_w() >= 340:
                    right = "%s/s · %s" % (num(rate), pct)
                else:
                    right = "%s/s" % num(rate)
                rows.append(dict(label="%d. %s" % (rank, p["name"]), value=num(p["total"]), right=right,
                                 frac=p["total"] / (top or 1), me=p["me"]))
            if not players:
                msg = (_("Nenhum dano neste encontro."), "")
        elif tab == "skills":
            sk = snap["skills"]
            top = sk[0]["total"] if sk else 1
            for k in sk[:n]:
                rows.append(dict(label=k["name"], value=num(k["total"]),
                                 right=(_("%.0f%% · %d acertos") if self.base_w() >= 340 else "%.0f%% · %d×")
                                 % (k["share"] * 100, k["hits"]),
                                 frac=k["total"] / (top or 1), me=True))
            if not sk:
                msg = (_("Você não causou dano aqui."), "")
        elif tab == "drops":
            cb = self.combat()
            items, favs = self.drop_items(cb)
            top = max([r["mine"] + r["mvp"] for r in items] + [1])
            first = max(0, min(self.drop_scroll, len(items) - n))
            self.drop_scroll, self.drop_view = first, (first, n, len(items))
            pings = self.ping_items()
            for r in items[first:first + n]:
                rows.append(dict(label=r["name"] + (" ♪" if r["item"] in pings else ""),
                                 value="×%d" % (r["mine"] + r["mvp"]),
                                 right=_("prêmio de MVP") if r["mvp"] else "", frac=(r["mine"] + r["mvp"]) / float(top),
                                 me=True, item=r["item"], fav=r["item"] in favs, pin="item:%d" % r["item"],
                                 color=self.item_color(r["item"])))
            if not items:
                hidden = self.hidden_items()
                msg = (_("Você não pegou nenhum item aqui."),
                       _("%d itens ocultos: botão direito › Itens ocultos") % len(hidden) if hidden else
                       _("O que caiu no chão e o que outros pegaram fica na análise (aba Drops)."))
        elif tab == "xp":
            rows = self.xp_rows(self.combat())[:n]
        else:
            tg = snap["targets"]
            top = tg[0]["total"] if tg else 1
            total = snap["my_total"] or 1
            for g in tg[:n]:
                rows.append(dict(label=g["name"], value=num(g["total"]),
                                 right="%.0f%%" % (g["total"] * 100.0 / total),
                                 frac=g["total"] / (top or 1), me=True))
            if not tg:
                msg = (_("Você não causou dano aqui."), "")
        if msg:
            cy = y + n * ROW_H * s / 2
            c.create_text(W / 2, cy - 8 * s, text=msg[0], font=self.fonts["text"], fill=t["fg"])
            if msg[1]:
                c.create_text(W / 2, cy + 9 * s, text=msg[1], font=self.fonts["small"], fill=t["muted"])
            return
        x0, x1 = 10 * s, W - 10 * s
        # coluna da direita do tamanho do maior texto, para nada se sobrepor em nenhum tamanho
        right_w = max([self.fonts["small"].measure(r["right"]) for r in rows] + [40 * s]) + 6 * s
        value_x = x1 - right_w - 6 * s
        for r in rows:
            y1 = y + (ROW_H - 3) * s
            c.create_polygon(round_rect_pts(x0, y, x1, y1, 4 * s), smooth=True, fill=t["track"], outline="")
            bw = max(0.0, min(1.0, r["frac"])) * (x1 - x0)
            if bw >= 2 * s:
                c.create_polygon(round_rect_pts(x0, y, x0 + bw, y1, 4 * s), smooth=True,
                                 fill=t["bar_me"] if r["me"] and tab == "group" else t["bar"], outline="")
            cy = (y + y1) / 2
            fg = on_color(t["bar"]) if luminance(t["bg"]) < 0.5 else t["fg"]
            c.create_text(x1 - 6 * s, cy, anchor="e", text=r["right"], font=self.fonts["small"],
                          fill=mix(fg, t["muted"], 0.35))
            vid = c.create_text(value_x, cy, anchor="e", text=r["value"], font=self.fonts["num"], fill=fg)
            lx = x0 + 7 * s
            if "item" in r:                    # estrela de favorito (clique marca/desmarca)
                star = c.create_text(lx, cy, anchor="w", text="★" if r["fav"] else "☆", font=self.fonts["text"],
                                     fill="#fbbf24" if r["fav"] else mix(fg, t["muted"], 0.4))
                bx = c.bbox(star)
                # área de clique generosa: do começo da linha até depois da estrela, na altura toda da linha
                self.hits.append((("fav", r["item"]), (x0, y, bx[2] + 6 * s, y1)))
                lx = bx[2] + 5 * s
            lid = c.create_text(lx, cy, anchor="w", text=r["label"], font=self.fonts["text"],
                                fill=self.readable(r.get("color")) or fg)
            self.clip_text(lid, r["label"], c.bbox(vid)[0] - 8 * s)
            if r.get("pin"):                   # botão direito na linha: fixar, ocultar...
                self.hits.insert(0, (("row", r["pin"]), (x0, y, x1, y1)))
            y += ROW_H * s
        first, shown, total = self.drop_view if tab == "drops" else (0, 0, 0)
        if total > shown > 0:                  # barrinha de rolagem: tem mais itens (roda do mouse)
            top_y, h = self.rows_y0() * s, shown * ROW_H * s - 3 * s
            c.create_line(W - 4 * s, top_y, W - 4 * s, top_y + h, fill=t["track"], width=max(2, int(2 * s)))
            a = top_y + h * first / total
            c.create_line(W - 4 * s, a, W - 4 * s, a + max(8 * s, h * shown / total), fill=t["muted"],
                          width=max(2, int(2 * s)))

    # ------------------------------------------------------------ drops, XP e faixa fixa

    def view_rng(self, cb, pad=False):
        """Recorte da visão escolhida: None = tudo; senão a luta (pad: com a folga dos drops que caem depois)."""
        if cb is None or self.cfg["session"]:
            return None
        enc = cb.encounter(self.enc_back)
        if enc is None:
            return None
        return (enc.start - 2000, enc.last + 30000) if pad else (enc.start, enc.last)

    def drop_items(self, cb):
        """Itens que quem grava pegou na visão atual, sem os ocultos, com os favoritos no topo."""
        marked = self.cfg.get("drop_favs") or []
        hidden = self.hidden_items()
        items = [r for r in cb.drop_summary(self.view_rng(cb, pad=True))
                 if (r["mine"] or r["mvp"]) and r["item"] not in hidden]
        items = itemkind.favorites_first(items, marked, lambda r: (-(r["mine"] + r["mvp"]), r["name"]))
        return items, set(marked)

    def item_color(self, item):
        itemkind.start()
        return itemkind.color_of(item, self.cfg, meter.ITEMS.get(str(item), {}).get("name"))

    def readable(self, color):
        """A cor escolhida, escurecida no tema claro para dar para ler."""
        if not color:
            return None
        return mix(color, "#000000", 0.45) if luminance(self.t["bg"]) > 0.5 else color

    def xp_rows(self, cb):
        """Linhas da aba XP (cada uma com a chave para fixar na faixa). O widget se redesenha a cada leitura do
        replay, mas a XP só muda a cada abate: a conta é refeita no máximo 1 vez por segundo (ou quando a visão ou
        os bônus marcados mudam). Refazê-la a cada desenho era o que prendia o widget nas sessões longas."""
        if cb is None:
            return []
        cfg = self.cfg
        key = (id(cb), cfg["session"], self.enc_back, cfg.get("xp_mode"), cfg.get("xp_fixed"),
               repr(cfg.get("xp_bonuses")), repr(cfg.get("xp_event_off")), len(cb.level_ups), len(cb.quests_done),
               len(cb.quests_added), cb.finished, xp.GEAR.table is None, i18n.LANG)
        now = time.monotonic()
        hit = self._xp_rows
        if hit and hit[0] == key and now < hit[1]:
            return hit[2]
        rows = self.xp_rows_now(cb)
        cost = time.monotonic() - now
        self._xp_rows = (key, now + cost + max(XP_ROWS_S, XP_ROWS_COST * cost), rows)
        return rows

    def xp_rows_now(self, cb):
        rng = self.view_rng(cb)
        est = xp.estimate(cb, self.cfg, rng)
        kind, _info = est["source"]
        how = {"medido": _("×%s medido"), "fixo": _("×%s fixo"), "auto": _("×%s aproximado")}.get(
            kind, _("×%s pela lista")) % dec("%.2f" % est["factor"])
        rows = []
        if xp.calibration_hint(cb, self.cfg):
            # mapa sem medida: duas gravações seguidas dão a XP exata (a linha só aparece na aba XP; não é fixável)
            # texto curto e sem coluna da direita: um texto largo ali empurra as colunas de todas as linhas
            rows.append(dict(label=_("Calibrar: grave de novo"), value="⟳", right="", frac=0.0, me=False,
                             color="#f59e0b"))
        # porcentagem do nível primeiro, número absoluto depois (quando o jogo mandou quanto falta para o nível)
        pct = est["pct"] is not None
        rows.append(dict(label=_("XP estimada") if rng is None else _("XP nesta luta"),
                         value=dec("%.2f%%" % est["pct"]) if pct else num(est["xp"]),
                         right=("%s · %s" % (num(est["xp"]), how)) if pct else how, frac=1.0, me=True, pin="xp_total"))
        if est["per_min"] is not None:
            rows.append(dict(label=_("XP por minuto"),
                             value=dec("%.3f%%" % est["per_min_pct"]) if pct else num(est["per_min"]),
                             right=(_("%s/min") % num(est["per_min"])) if pct else "", frac=1.0, me=True, pin="xp_min"))
            rows.append(dict(label=_("XP por hora"),
                             value=dec("%.2f%%" % est["per_hour_pct"]) if pct else num(est["per_hour"]),
                             right=(_("%s/h") % num(est["per_hour"])) if pct else "", frac=1.0, me=True, pin="xp_hour"))
        # a gravação que continua a anterior (reiniciou para calibrar) já tem o ritmo dela: a previsão aparece logo
        if est["per_min"] is not None or xp.carry(cb) is not None:
            eta, left = xp.time_to_level(cb, self.cfg)      # pelo ritmo dos últimos minutos de farm
            missing = xp.quests_uncounted(cb, self.cfg)     # missões entregues cuja XP não entra na conta
            if eta is not None:
                right = (_("faltam %s") % num(left)) if left else ""
                if missing and eta:
                    right = _("pode ser menos: missões fora da conta")
                dn = xp.death_note(cb, self.cfg)            # morte sem seguro: a previsão já desconta os 5%
                if dn:
                    right = (right + " · " if right else "") + xp.death_text(*dn)
                # estimativa passou do nível sem a subida chegar: quem grava ainda não subiu (o jogo manda a subida na
                # hora), então "a qualquer momento", nunca "já subiu"
                rows.append(dict(label=_("Até o próximo nível"),
                                 value=xp.span_text(eta) if eta else _("a qualquer momento"),
                                 right=right, frac=1.0, me=True, pin="xp_eta"))
            elif xp.no_known_xp(cb):
                rows.append(dict(label=_("Até o próximo nível"), value="—",
                                 right=_("nenhum abate com XP conhecida"), frac=1.0, me=True, pin="xp_eta"))
            elif xp.warming_up(cb, self.cfg):
                rows.append(dict(label=_("Até o próximo nível"), value=_("calculando…"),
                                 right=_("10 min de farm ou 1%"), frac=1.0, me=True, pin="xp_eta"))
        per = (_("%s/min") % dec("%.1f" % est["kills_per_min"])) if est["kills_per_min"] is not None else ""
        if est["unknown"]:
            per = (per + " · " if per else "") + _("%d sem XP") % est["unknown"]
        rows.append(dict(label=_("Abates"), value="%d" % est["kills"], right=per, frac=0.0, me=False, pin="kills"))
        # missões: o que já foi entregue no recorte e o progresso das caças em andamento (dá para fixar na faixa)
        if est["quests"] and not est["quest_xp"]:
            # o jogo não grava quanto a missão rende: por enquanto só avisa que essa XP ficou de fora
            rows.append(dict(label=_("Missões entregues"), value="%d" % len(est["quests"]),
                             right=_("XP fora da conta: estimativa abaixo do real"), frac=0.0, me=False))
        elif est["quests"]:
            nxt_exp = cb.session.next_exp
            known = est["quest_xp"]
            right = _("%d entregue(s)") % len(est["quests"])
            if est["quests_unknown"]:
                right += " · " + _("%d sem XP conhecida") % est["quests_unknown"]
            rows.append(dict(label=_("XP de missões"),
                             value=dec("%.2f%%" % (100.0 * known / nxt_exp)) if nxt_exp else num(known),
                             right=right, frac=1.0, me=True))
        for h in xp.hunts(cb)[:3]:
            rows.append(dict(label=quests.title(h["quest"]), value=" · ".join("%d/%d" % p for p in h["parts"]),
                             right=dec("%.0f%%" % (100.0 * h["count"] / h["goal"])) if h["goal"] else "",
                             frac=min(1.0, h["count"] / float(h["goal"])) if h["goal"] else 0.0, me=False,
                             pin="quest:%d" % h["quest"]))
        pr = xp.progress(cb, self.cfg)
        prog = meter.level_progress(cb.session)
        if pr is not None and pr["pct"] is not None:   # onde está agora: o último ponto exato + a XP estimada
            # sem a subida de nível, quem grava ainda está no nível: nunca 100%
            rows.append(dict(label=_("Nível %d") % pr["level"], value=dec("%.1f%%" % min(99.9, pr["pct"])),
                             right=_("agora (sem as missões)") if xp.quests_uncounted(cb, self.cfg)
                             else _("agora (estimado)"), frac=min(1.0, pr["pct"] / 100.0), me=False, pin="level"))
        elif pr is not None and not pr["need"] and pr["level"] != cb.session.base_level:
            # subiu até o nível máximo da classe: não há XP para o próximo (antes mostrava o nível do começo)
            rows.append(dict(label=_("Nível %d") % pr["level"], value=_("máximo"), right="", frac=1.0, me=False,
                             pin="level"))
        elif prog is not None:
            rows.append(dict(label=_("Nível %d") % cb.session.base_level, value=dec("%.1f%%" % (100 * prog)),
                             right=_("no início da gravação"), frac=prog, me=False, pin="level"))
        nxt = meter.xp_after_soon(getattr(cb, "path", None), cb.session)
        if nxt and nxt["gain"] is not None:
            rows.append(dict(label=_("XP real até a próxima gravação"), value="+" + num(nxt["gain"]), right="",
                             frac=1.0, me=False))
        return rows

    def pin_texts(self, cb):
        """[(chave, rótulo, valor, detalhe, cor)] das informações fixadas, na ordem em que foram fixadas."""
        pins = self.cfg.get("pins") or []
        stats = {}
        if any(not p.startswith(("item:", "fx:")) for p in pins):
            stats = {r["pin"]: r for r in self.xp_rows(cb) if r.get("pin")}
        items = None
        out = []
        for key in pins:
            if key.startswith("item:"):
                item = int(key[5:])
                if items is None:
                    items = {r["item"]: r for r in cb.drop_summary(self.view_rng(cb, pad=True))} if cb else {}
                r = items.get(item)
                out.append((key, meter.item_name(item), "×%d" % ((r["mine"] + r["mvp"]) if r else 0), "",
                            self.item_color(item)))
            elif key.startswith("fx:"):          # efeito acompanhado fixado: o contador dele (— = não está ativo)
                kind, _sep, ident = key[3:].partition(":")
                try:
                    name = cards.short_name(cards.name_of(dict(kind=kind, id=int(ident))))
                except ValueError:
                    continue
                r = self.pinned_fx.get(key[3:])
                if r is None:
                    out.append((key, name, "—", "", None))
                else:
                    left = r.get("left")
                    col = "#ef4444" if r.get("ended") is not None else (
                        "#f59e0b" if left is not None and left < 3000 else "#22c55e")
                    out.append((key, name, cards.time_text(r), "", col))
            elif key.startswith("quest:"):       # caça de missão: some da aba quando é entregue, a faixa avisa
                r = stats.get(key)
                out.append((key, quests.title(int(key[6:])), r["value"] if r else _("entregue ou sem progresso"),
                            r["right"] if r else "", None))
            else:
                r = stats.get(key)
                out.append((key, PIN_LABELS.get(key, key), r["value"] if r else "—", r["right"] if r else "", None))
        return out

    def pin_shift(self):
        """Quanto o resumo da morte desce para a faixa fixa ficar à vista acima dele (com algo fixado o widget é
        essa altura mais alto, então o resumo continua do tamanho de sempre)."""
        return PIN_H if self.cfg.get("pins") else 0

    def side_pins(self, cb):
        """Com um cartão aberto (menos o da morte), o que está fixado vai para a direita do DPS, no lugar de
        "agora / total / em combate": o cartão cobre a faixa fixa e fica com a área inteira.
        [(chave, rótulo, valor, cor)], ou [] quando não é o caso."""
        if self.death_card or not self.cfg.get("pins") or not (
                self.ping_card or self.boss_card or self.summary_card or self.session_card or self.fx_now):
            return []
        return [(key, label, value, color) for key, label, value, _right, color in self.pin_texts(cb)]

    def side_pins_width(self, parts):
        """Largura que os fixados pedem à direita do DPS (no máximo metade do widget: o nome é cortado)."""
        f, v = self.fonts["small"], self.fonts["text"]
        widest = max([f.measure(label) + 9 * self.s + v.measure(value) for _k, label, value, _c in parts] + [0])
        return min(self.W * 0.52, widest)

    def draw_side_pins(self, parts, rx):
        """Os fixados à direita do DPS, um por linha: o valor encostado à direita e o nome antes dele."""
        c, s, t = self.canvas, self.s, self.t
        room = self.side_pins_width(parts)
        y0 = BIG_Y * s - (len(parts) - 1) * 8 * s
        for i, (key, label, value, color) in enumerate(parts):
            cy = y0 + i * 16 * s
            vid = c.create_text(rx, cy, anchor="e", text=value, font=self.fonts["text"], fill=t["fg"])
            vx = c.bbox(vid)[0]
            name, f = label, self.fonts["small"]
            while len(name) > 1 and f.measure(name) > room - (rx - vx) - 5 * s:
                name = name[:-2].rstrip() + "…"
            lid = c.create_text(vx - 5 * s, cy, anchor="e", text=name, font=f, fill=self.readable(color) or t["muted"])
            self.hits.append((("pinbar", key), (c.bbox(lid)[0] - 3 * s, cy - 8 * s, rx + 3 * s, cy + 8 * s)))

    def draw_pins(self, cb, top=None):
        """Faixa abaixo das abas com até 2 informações fixadas (botão direito numa linha › Fixar no widget).
        `top`: com um cartão aberto, onde a faixa fica (logo acima dele)."""
        if not self.cfg.get("pins"):
            return
        c, s, t, W = self.canvas, self.s, self.t, self.W
        if top is None:
            top = ROWS_Y0
        else:                                 # acima de um cartão: limpa o que havia ali (abas ou o número grande)
            c.create_rectangle(4 * s, (top - 2) * s, W - 4 * s, (top + PIN_H) * s, fill=t["bg"], outline="")
        y0, y1 = top * s, (top + PIN_H - 4) * s
        x0, x1 = 10 * s, W - 10 * s
        c.create_polygon(round_rect_pts(x0, y0, x1, y1, 5 * s), smooth=True, fill=mix(t["bg"], t["accent"], 0.16),
                         outline="")
        cy = (y0 + y1) / 2
        icon = c.create_text(x0 + 7 * s, cy, anchor="w", text=self.icon("pin_on"), font=self.fonts["icon"],
                             fill=t["accent"])
        x = c.bbox(icon)[2] + 6 * s
        parts = self.pin_texts(cb)
        part = (x1 - 6 * s - x) / max(1, len(parts))
        for i, (key, label, value, right, color) in enumerate(parts):
            px0 = x + i * part
            px1 = px0 + part - 10 * s
            if i:
                c.create_line(px0 - 6 * s, y0 + 4 * s, px0 - 6 * s, y1 - 4 * s, fill=mix(t["bg"], t["muted"], 0.5))
            lid = c.create_text(px0, cy, anchor="w", text=label, font=self.fonts["small"],
                                fill=self.readable(color) or t["muted"])
            self.clip_text(lid, label, px1 - 30 * s)
            text = value + (" · " + right if right else "")
            vid = c.create_text(c.bbox(lid)[2] + 5 * s, cy, anchor="w", text=text, font=self.fonts["text"],
                                fill=t["fg"])
            if c.bbox(vid)[2] > px1 and right:      # sem espaço: fica só o valor
                c.itemconfigure(vid, text=value)
            self.clip_text(vid, c.itemcget(vid, "text"), px1)
            self.hits.append((("pinbar", key), (px0 - 4 * s, y0, px1 + 4 * s, y1)))

    def toggle_pin_stat(self, key):
        pins = list(self.cfg.get("pins") or [])
        if key in pins:
            pins.remove(key)
        else:
            pins = (pins + [key])[-MAX_PINS:]          # com 2 fixadas, a mais antiga sai
        self.cfg["pins"] = pins
        self.save()
        self.resize_window()

    def clear_pins(self):
        self.cfg["pins"] = []
        self.save()
        self.resize_window()

    def toggle_fav(self, item):
        favs = list(self.cfg.get("drop_favs") or [])
        if item in favs:
            favs.remove(item)
        else:
            favs.append(item)
        self.cfg["drop_favs"] = favs
        self.save()
        self.drops_changed()

    def hidden_items(self):
        """Itens ocultos: os de sempre (config) e os de agora (até fechar o programa)."""
        return set(self.cfg.get("drop_hidden") or []) | self.session_hidden

    def hide_item(self, item, always):
        if always:
            hidden = list(self.cfg.get("drop_hidden") or [])
            if item not in hidden:
                hidden.append(item)
            self.cfg["drop_hidden"] = hidden
            self.save()
        else:
            self.session_hidden.add(item)
        self.drops_changed()

    def unhide_item(self, item):
        self.session_hidden.discard(item)
        hidden = [i for i in (self.cfg.get("drop_hidden") or []) if i != item]
        if hidden != (self.cfg.get("drop_hidden") or []):
            self.cfg["drop_hidden"] = hidden
            self.save()
        self.drops_changed()

    def unhide_all(self):
        self.session_hidden.clear()
        self.cfg["drop_hidden"] = []
        self.save()
        self.drops_changed()

    def drops_changed(self):
        """Favorito, oculto ou cor mudou: redesenha o widget e a análise."""
        self.dirty = True
        if self.analysis is not None:
            self.analysis.refresh(force=True)

    def hidden_menu(self, parent):
        """Submenu com cada item oculto (clique mostra de novo) e "Mostrar todos"; None se não há."""
        always = list(self.cfg.get("drop_hidden") or [])
        items = always + sorted(i for i in self.session_hidden if i not in always)
        if not items:
            return None
        hm = self.new_menu(parent)
        for item in items:
            when = _("sempre") if item in always else _("até fechar o programa")
            hm.add_command(label=_("Mostrar de novo: %s (%s)") % (meter.item_name(item), when),
                           command=lambda i=item: self.unhide_item(i))
        hm.add_separator()
        hm.add_command(label=_("Mostrar todos os itens ocultos"), command=self.unhide_all)
        return hm

    def pins_menu(self, parent):
        """Submenu "Faixa fixa": as informações que dá para fixar e as fixadas agora."""
        pm = self.new_menu(parent)
        pins = self.cfg.get("pins") or []
        for key, label in PIN_STATS:
            var = self.keep(tk.BooleanVar(self.root, key in pins))
            pm.add_checkbutton(label=label, variable=var, command=lambda k=key: self.toggle_pin_stat(k))
        for key in pins:
            if key.startswith("item:"):
                var = self.keep(tk.BooleanVar(self.root, True))
                pm.add_checkbutton(label=_("Drop: %s") % meter.item_name(int(key[5:])), variable=var,
                                   command=lambda k=key: self.toggle_pin_stat(k))
            elif key.startswith("quest:"):
                var = self.keep(tk.BooleanVar(self.root, True))
                pm.add_checkbutton(label=_("Missão: %s") % quests.title(int(key[6:])), variable=var,
                                   command=lambda k=key: self.toggle_pin_stat(k))
            elif key.startswith("fx:"):
                kind, _sep, ident = key[3:].partition(":")
                var = self.keep(tk.BooleanVar(self.root, True))
                pm.add_checkbutton(label=_("Efeito: %s") % cards.name_of(dict(kind=kind, id=int(ident))), variable=var,
                                   command=lambda k=key: self.toggle_pin_stat(k))
        pm.add_separator()
        pm.add_command(label=_("Até %d. Também dá para fixar com o botão direito numa linha das abas XP e Drops.")
                       % MAX_PINS, state="disabled")
        if pins:
            pm.add_command(label=_("Desafixar tudo"), command=self.clear_pins)
        return pm

    def sound_menu(self, parent):
        """Sons do Milagre e da União (liga/desliga e volume, com teste)."""
        sm = self.new_menu(parent)
        for key, vol_key, label, vol_label, play in (
                ("miracle_sound", "miracle_volume", _("Tocar um som no Milagre"), _("Volume do Milagre"), play_chime),
                ("fusion_sound", "fusion_volume", _("Tocar um som com HP baixo na União"), _("Volume da União"),
                 play_beep)):
            var = self.keep(tk.BooleanVar(self.root, self.cfg[key]))
            sm.add_checkbutton(label=label, variable=var, command=lambda k=key: self.toggle_cfg(k))
            vm = self.new_menu(sm)
            vvar = self.keep(tk.IntVar(self.root, self.cfg[vol_key]))
            for v in CHIME_VOLUMES:
                vm.add_radiobutton(label="%d%%" % v, variable=vvar, value=v,
                                   command=lambda v=v, k=vol_key, p=play: self.set_volume(k, v, p))
            vm.add_separator()
            vm.add_command(label=_("Tocar o som agora"), command=lambda k=vol_key, p=play: p(self.cfg[k]))
            sm.add_cascade(label=vol_label, menu=vm)
            sm.add_separator()
        var = self.keep(tk.BooleanVar(self.root, self.cfg["rec_sound"]))
        sm.add_checkbutton(label=_("Tocar um som quando a gravação estiver desligada"), variable=var,
                           command=lambda: self.toggle_cfg("rec_sound"))
        sm.add_separator()
        # aviso de item: som quando cai um item marcado (botão direito num item › Avisar quando cair)
        play = lambda v: play_ping(v, self.cfg.get("ping_tone"))            # noqa: E731
        var = self.keep(tk.BooleanVar(self.root, self.cfg["ping_sound"]))
        sm.add_checkbutton(label=_("Tocar um som quando cair um item marcado"), variable=var,
                           command=lambda: self.toggle_cfg("ping_sound"))
        vm = self.new_menu(sm)
        vvar = self.keep(tk.IntVar(self.root, self.cfg["ping_volume"]))
        for v in itemping.VOLUMES:
            vm.add_radiobutton(label="%d%%" % v, variable=vvar, value=v,
                               command=lambda v=v: self.set_volume("ping_volume", v, play))
        vm.add_separator()
        vm.add_command(label=_("Tocar o som agora"), command=lambda: play(self.cfg["ping_volume"]))
        sm.add_cascade(label=_("Volume do aviso de item"), menu=vm)
        tm = self.new_menu(sm)
        tvar = self.keep(tk.StringVar(self.root, self.cfg.get("ping_tone") or itemping.DEFAULT_TONE))
        for tone, hz in itemping.TONES:
            tm.add_radiobutton(label="%s (%d Hz)" % (_(TONE_NAMES[tone]), hz), variable=tvar, value=tone,
                               command=lambda tone=tone: self.set_ping_tone(tone))
        sm.add_cascade(label=_("Tom do aviso de item"), menu=tm)
        sm.add_separator()
        folder = self.cfg.get("sound_folder")
        sm.add_command(label=(_("Pasta com os seus sons: %s (%d)…") % (os.path.basename(folder) or folder,
                                                                       len(sounds.custom_sounds(folder))))
                       if folder else _("Pasta com os seus sons…"), command=self.pick_sound_folder)
        sm.add_separator()
        sm.add_command(label=_("Os sons só tocam com o aviso do Milagre ou da União ligado."), state="disabled")
        return sm

    def set_ping_tone(self, tone):
        """Troca o tom do aviso de item e toca para a pessoa ouvir."""
        self.cfg["ping_tone"] = tone
        self.save()
        play_ping(self.cfg.get("ping_volume", 40), tone)

    def row_menu(self, target):
        """Botão direito numa linha das abas XP e Drops (ou na faixa fixa)."""
        m = self.new_menu()
        kind, key = target
        pins = self.cfg.get("pins") or []
        if kind == "pinbar":
            m.add_command(label=_("Desafixar"), command=lambda: self.toggle_pin_stat(key))
            if len(pins) > 1:
                m.add_command(label=_("Desafixar tudo"), command=self.clear_pins)
        else:
            pin = key if kind == "row" else "item:%d" % key
            m.add_command(label=_("Desafixar do widget") if pin in pins else _("Fixar no widget"),
                          command=lambda: self.toggle_pin_stat(pin))
            if pin.startswith("item:"):
                item = int(pin[5:])
                fav = item in (self.cfg.get("drop_favs") or [])
                m.add_command(label=_("Tirar dos favoritos") if fav else _("Favoritar (fica no topo)"),
                              command=lambda: self.toggle_fav(item))
                # o aviso com o som escolhido ali mesmo: não avisar, o som padrão do aviso ou qualquer outro som
                on = item in self.ping_items()
                snd = self.ping_sound_of(item)
                m.add_cascade(label=(_("Aviso quando cair: %s") % (sound_name(snd) if snd else _("som padrão"))) if on
                              else _("Avisar quando cair (som e lugar)"), menu=self.ping_sound_menu(m, item))
                m.add_separator()
                m.add_command(label=_("Ocultar até fechar o programa"), command=lambda: self.hide_item(item, False))
                m.add_command(label=_("Ocultar sempre"), command=lambda: self.hide_item(item, True))
        hm = self.hidden_menu(m)
        if hm is not None:
            m.add_cascade(label=_("Itens ocultos"), menu=hm)
        m.add_separator()
        m.add_cascade(label=_("Todas as opções"), menu=self.main_menu(m))
        return m

    def chip(self, target, x, label, active, outline=False):
        c, s, t = self.canvas, self.s, self.t
        w = self.fonts["tab"].measure(label) + 16 * s
        box = (x, TABS_Y0 * s, x + w, TABS_Y1 * s)
        hov = self.hover == target
        if active:
            fill, fg = t["accent"], on_color(t["accent"])
        else:
            fill = shade(t["btn"], 0.10) if hov else (t["bg"] if outline else t["btn"])
            fg = t["fg"] if hov or outline else t["muted"]
        c.create_polygon(round_rect_pts(*box, 9 * s), smooth=True, fill=fill,
                         outline=t["btn"] if outline else "", width=max(1, s))
        c.create_text((box[0] + box[2]) / 2, (box[1] + box[3]) / 2, text=label, font=self.fonts["tab"], fill=fg)
        self.hits.append((target, box))
        return box[2]

    def icon_button(self, key, cx, cy, glyph, color):
        c, s = self.canvas, self.s
        half = 10 * s
        box = (cx - half, cy - half, cx + half, cy + half)
        tag = "hover_" + key
        c.create_polygon(round_rect_pts(*box, 5 * s), smooth=True, fill="", outline="", tags=(tag, tag + "_bg"))
        c.create_text(cx, cy, text=glyph, font=self.fonts["icon"], fill=color, tags=(tag, tag + "_fg"))
        self.hits.append((("btn", key), box))
        return box[0]

    def text_button(self, key, right, cy, glyph, label):
        c, s, t = self.canvas, self.s, self.t
        wi = self.fonts["icon"].measure(glyph)
        wl = self.fonts["small"].measure(label)
        w = wi + wl + 5 * s + 16 * s
        box = (right - w, cy - 10 * s, right, cy + 10 * s)
        tag = "hover_" + key
        c.create_polygon(round_rect_pts(*box, 6 * s), smooth=True, fill=t["btn"], outline="",
                         tags=(tag, tag + "_bg"))
        c.create_text(box[0] + 8 * s, cy, anchor="w", text=glyph, font=self.fonts["icon"], fill=t["fg"])
        c.create_text(box[0] + 8 * s + wi + 5 * s, cy, anchor="w", text=label, font=self.fonts["small"], fill=t["fg"])
        self.hits.append((("btn", key), box))
        return box[0]

    def paint_hover(self):
        tgt = self.hover
        c = self.canvas
        if tgt and tgt[0] == "btn":
            key = tgt[1]
            if key == "close":
                c.itemconfigure("hover_close_bg", fill="#e81123")
                c.itemconfigure("hover_close_fg", fill="#ffffff")
            elif c.find_withtag("hover_%s_bg" % key):
                base = self.t["btn"] if key == "reset" else self.t["bg"]
                c.itemconfigure("hover_%s_bg" % key, fill=shade(base, 0.12))
        cursor = ""
        if tgt:
            cursor = {"btn": "hand2", "tab": "hand2", "fav": "hand2", "ping": "hand2",
                      "grip": "size_nw_se"}.get(tgt[0], "")
        c.configure(cursor=cursor)

    # ------------------------------------------------------------ ações

    def reload(self):
        """Lê o arquivo atual de novo do início (ex.: mudou o intervalo de encontro)."""
        f = self.watcher.file
        self.watcher.gap_ms = self.gap_ms()
        if f is not None:
            pinned = self.watcher.pinned
            nf = meter.ReplayFile(f.path, self.gap_ms(), self.cfg["targets"])
            nf.poll(max_bytes=64 << 20)
            self.watcher.file = nf
            self.watcher.pinned = pinned
        self.dirty = True

    def reset(self):
        cb = self.combat()
        if cb is not None:
            xp.keep_level(cb, self.cfg)          # a posição no nível não volta para trás com os abates apagados
            cb.reset()
        self.enc_back = 0
        self.dirty = True

    def toggle_session(self):
        self.set_view(not self.cfg["session"])

    def set_view(self, session, back=0):
        """Tudo (desde o início ou desde Zerar) ou uma luta (0 = a atual, 1 = a anterior...)."""
        self.cfg["session"] = session
        self.enc_back = back
        self.save()
        self.dirty = True

    def set_targets(self, mode):
        self.cfg["targets"] = mode
        self.watcher.targets = mode
        self.save()
        self.enc_back = 0
        self.reload()

    def set_tab(self, key):
        self.cfg["tab"] = key
        self.save()
        self.dirty = True

    def view_label(self, cb):
        if self.cfg["session"]:
            return _("Tudo")
        if not self.enc_back:
            return _("Luta atual")
        encs = len(cb.encounters()) if cb else 0
        return _("Luta %d de %d") % (encs - self.enc_back, encs)

    def view_menu(self, parent=None):
        m = self.new_menu(parent)
        cb = self.combat()
        var = self.keep(tk.StringVar(self.root, "all" if self.cfg["session"] else "enc%d" % self.enc_back))
        m.add_radiobutton(label=_("Tudo (desde o início ou desde Zerar)"), variable=var, value="all",
                          command=lambda: self.set_view(True))
        m.add_radiobutton(label=_("Luta atual (a mais recente)"), variable=var, value="enc0",
                          command=lambda: self.set_view(False, 0))
        encs = cb.encounters() if cb else []
        if len(encs) > 1:
            m.add_separator()
            m.add_command(label=_("Lutas anteriores:"), state="disabled")
            for back in range(1, min(len(encs), 15)):
                enc = encs[-1 - back]
                tgt = max(enc.by_target.items(), key=lambda kv: kv[1])[0] if enc.by_target else None
                mine = enc.by_source.get(cb.me)
                label = _("Luta %d · %s · %s") % (len(encs) - back, cb.target_name(tgt) if tgt is not None else "?",
                                               dur(enc.duration_ms()))
                if mine:
                    label += " · %s/s" % num(mine.total * 1000.0 / enc.duration_ms())
                m.add_radiobutton(label="    " + label, variable=var, value="enc%d" % back,
                                  command=lambda b=back: self.set_view(False, b))
        m.add_separator()
        m.add_cascade(label=_("Uma luta termina após"), menu=self.gap_menu(m))
        m.add_cascade(label=_("Contar dano em"), menu=self.targets_menu(m))
        return m

    def gap_menu(self, parent):
        gap = self.new_menu(parent)
        gap_var = self.keep(tk.IntVar(self.root, self.cfg["gap_s"]))
        for value, label in GAP_CHOICES:
            gap.add_radiobutton(label=label, variable=gap_var, value=value, command=lambda v=value: self.set_gap(v))
        gap.add_separator()
        gap.add_command(label=_("As fases de um MVP contam como uma luta só"), state="disabled")
        return gap

    def targets_menu(self, parent):
        tm = self.new_menu(parent)
        var = self.keep(tk.StringVar(self.root, self.cfg["targets"]))
        for value, label in TARGET_CHOICES:
            tm.add_radiobutton(label=label, variable=var, value=value, command=lambda v=value: self.set_targets(v))
        tm.add_separator()
        tm.add_command(label=_("Invocações de jogadores (ex.: Esfera Marinha) nunca contam"), state="disabled")
        return tm

    def browse(self, step):
        cb = self.combat()
        if cb is None or self.cfg["session"]:
            return
        encs = len(cb.history) + (1 if cb.current else 0)
        self.enc_back = max(0, min(encs - 1, self.enc_back + step))
        self.dirty = True

    def toggle_pin(self):
        self.cfg["pinned"] = not self.cfg["pinned"]
        self.root.attributes("-topmost", self.cfg["pinned"])
        self.save()
        self.dirty = True

    def set_theme(self, name):
        self.cfg["theme"] = name
        self.save()
        self.apply_border()
        self.dirty = True

    def set_scale(self, scale, save=True):
        scale = max(MIN_SCALE, min(MAX_SCALE, scale))
        if abs(scale - self.cfg["scale"]) < 0.005:
            return
        self.cfg["scale"] = scale
        self.resize_window()
        if save:
            self.save()

    def resize_window(self):
        self.size_fonts()
        w, h = self.size_px()
        self.root.geometry("%dx%d" % (w, h))
        self.draw()

    def set_alpha(self, alpha):
        self.cfg["alpha"] = alpha
        self.root.attributes("-alpha", alpha)
        self.save()

    def set_rows(self, n):
        self.cfg["rows"] = n
        self.save()
        self.resize_window()

    def set_width(self, w):
        self.cfg["width"] = w
        self.save()
        self.resize_window()

    def set_gap(self, secs):
        self.cfg["gap_s"] = secs
        self.save()
        self.enc_back = 0
        self.reload()

    def rate_menu(self, parent):
        rm = self.new_menu(parent)
        var = self.keep(tk.StringVar(self.root, self.cfg["rate"]))
        for value, label in (("combat", _("Em combate (dano ÷ tempo da luta)")),
                             ("active", _("Ativo (dano ÷ tempo em que cada um estava batendo)"))):
            rm.add_radiobutton(label=label, variable=var, value=value, command=lambda v=value: self.set_rate(v))
        rm.add_separator()
        rm.add_command(label=_("Ativo: pausas de mais de 5 s sem bater não contam (morto, esperando, correndo)"),
                       state="disabled")
        return rm

    def set_volume(self, key, value, play):
        self.cfg[key] = value
        self.save()
        play(value)

    def set_rate(self, value):
        self.cfg["rate"] = value
        self.save()
        self.dirty = True

    def toggle_pct(self):
        self.cfg["show_pct"] = not self.cfg["show_pct"]
        self.save()
        self.dirty = True

    def close_death_card(self):
        self.death_card = None
        self.dirty = True

    def boss_menu(self):
        m = self.new_menu()
        m.add_command(label=_("Fechar este aviso"), command=lambda: (setattr(self, "boss_card", None),
                                                                     setattr(self, "dirty", True)))
        m.add_command(label=_("Não mostrar mais o aviso do chefe"), command=lambda: self.toggle_cfg("alert_boss"))
        return m

    def draw_card(self, hit, shown, secs, sev, title, lines, spec=None, timer=None, frac=None):
        """Cartão no padrão único: moldura e título na cor da gravidade, desenho do chefe no alto, linhas centradas e
        a contagem regressiva embaixo. Ocupa sempre a mesma área (das abas até o fim das linhas), então todos têm o
        mesmo tamanho; num widget com poucas linhas o desenho encolhe ou some, e sobram as linhas que couberem.
        `timer` e `frac`: para o cartão de um efeito acompanhado, o tempo que falta do efeito (texto e barra) no
        lugar da contagem do próprio cartão."""
        k = time.time() - shown
        if timer is None and not 0 <= k < secs:
            return
        c, s, W = self.canvas, self.s, self.W
        col = SEV_COLORS[sev]
        x0, x1 = 8 * s, W - 8 * s
        y0 = (TABS_Y0 - 2) * s
        y1 = (self.rows_y0() + self.cfg["rows"] * ROW_H - 3) * s
        pad = 9 * s
        c.create_polygon(round_rect_pts(x0, y0, x1, y1, 10 * s), smooth=True, fill=CARD_BG, outline=col,
                         width=max(1, int(2 * s)))
        self.hits.append(((hit, None), (x0, y0, x1, y1)))
        cx = (x0 + x1) / 2
        cid = c.create_text(x1 - pad, y0 + pad + 4 * s, anchor="e",
                            text=(timer + "  ✕") if timer is not None else "%d s  ✕" % max(1, round(secs - k)),
                            font=self.fonts["small"], fill=CARD_DIM)
        count_w = c.bbox(cid)[2] - c.bbox(cid)[0]
        room = (y1 - y0) - 2 * pad

        def text_h(n):                         # título + n linhas
            return (22 + 14 * n) * s
        n = len(lines)
        while n > 1 and room < text_h(n):
            n -= 1
        sprite_h = 0
        if spec and sprites.MONSTERS.expected(spec):
            sprite_h = min(56 * s, room - text_h(n))
            if sprite_h < 26 * s:
                sprite_h = 0
        if sprite_h:
            foot = y0 + pad + sprite_h
            c.create_oval(cx - 30 * s, foot - 4 * s, cx + 30 * s, foot + 3 * s, fill="#23262f", outline="")
            photo = self.sprite_photo(spec, int(sprite_h), int((x1 - x0) - 2 * pad - 2 * count_w))
            if photo is not None:
                c.create_image(cx, foot, anchor="s", image=photo)
            y = foot + 6 * s
            xr = x1 - pad
        else:                                  # sem desenho: o texto fica no meio da altura
            y = y0 + max(pad, ((y1 - y0) - text_h(n)) / 2)
            xr = x1 - pad - (count_w + 6 * s if y < y0 + pad + 14 * s else 0)
        self.center_text(cx, y + 8 * s, title.upper(), self.fonts["title"], col, x0 + pad, xr)
        y += 22 * s
        for text, fill in lines[:n]:
            self.center_text(cx, y + 5 * s, text, self.fonts["small"], fill or CARD_DIM, x0 + pad, x1 - pad)
            y += 14 * s
        left = frac if frac is not None else 1.0 - k / secs
        if left > 0.005:
            c.create_line(x0 + 10 * s, y1 - 3 * s, x0 + 10 * s + (x1 - x0 - 20 * s) * left, y1 - 3 * s, fill=col,
                          width=max(2, int(2 * s)))

    def center_text(self, cx, cy, text, font, fill, xl, xr):
        """Texto centrado em cx; se não couber entre xl e xr, encosta na esquerda e corta com reticências."""
        c = self.canvas
        tid = c.create_text(cx, cy, text=text, font=font, fill=fill)
        b = c.bbox(tid)
        if b[2] - b[0] > xr - xl or b[2] > xr:
            c.itemconfigure(tid, anchor="w")
            c.coords(tid, xl, cy)
            self.clip_text(tid, text, xr)
        return tid

    def draw_boss_card(self):
        """Cartão de 5 s do chefe: o que mudou (propriedade, imunidade, tamanho) com o que bater e o que evitar, ou a
        mecânica que começou (Dor Máxima, Aliviar muito alto, defesa do Aquila)."""
        if not self.boss_card:
            return
        d, shown = self.boss_card
        dim = CARD_DIM
        el = d.get("immune") or d.get("element") or (d.get("form_element") or (None, 1))[0]
        level = 1 if d.get("element") or d.get("immune") else (d.get("form_element") or (None, 1))[1] or 1
        mine = d.get("mine")
        mech = MECH_CARDS.get(d.get("mech"))
        lines = []
        if mech:
            sev = mech[1]
            title = "%s: %s" % (d["name"], _(mech[0]))
            lines = [(_(text), fill) for text, fill in mech[2]]
            if d["mech"] == "maxpain_on" and d.get("hp"):
                # o reflexo é ~11% do golpe: acima de HP ÷ 0,11 o próprio golpe mata quem bateu
                lines.append((_("Golpe acima de %s te mata agora") % num(d["hp"] / analysis.MAXPAIN_RATIO[2]),
                              "#fbbf24"))
            elif d["mech"] == "defense" and d.get("job") in meter.DEF_BREAK_BOSSES:
                lines.append((_("Falta éter verde para a defesa cair"), "#4ade80"))
            elif d["mech"] == "relief":
                lines.append(((_("%d almas ativas ou mais") if d.get("more") else _("%d almas ativas"))
                              % d.get("souls", 0), "#fbbf24"))
                lines.append((_("O chefe está levando %d%% a menos de dano") % d.get("pct", 0), dim))
            el = None
        elif d.get("immune"):
            sev = "grave" if mine == d["immune"] else "atencao"      # grave quando é a propriedade do seu ataque
            title = _("%s: imune a %s") % (d["name"], analysis.element_name(d["immune"]))
        elif d.get("element"):
            sev = "atencao"
            title = _("%s virou %s") % (d["name"], analysis.element_name(d["element"]))
        else:
            sev = "atencao"
            title = (_("%s ficou pequeno") if d.get("size") == "S" else _("%s ficou grande") if d.get("size") == "L"
                     else _("%s ficou médio")) % d["name"]
        if d.get("size") and d.get("prev_size"):
            lines.append((_("Tamanho: %s (era %s)") % (_(SIZE_NAMES.get(d["size"], "?")),
                                                       _(SIZE_NAMES.get(d["prev_size"], "?"))), dim))
        if d.get("immune"):
            lines.append((_("Golpes de %s não tiram dano") % analysis.element_name(d["immune"]), "#f87171"))
        elif el:
            if not d.get("element"):
                lines.append((_("Propriedade: %s %d") % (analysis.element_name(el), level), dim))
            best, avoid = analysis.element_advice(el, level)
            if best:
                lines.append((_("Bata com: %s") % " · ".join("%s %d%%" % (analysis.element_name(a), p)
                                                             for a, p in best), "#4ade80"))
            if avoid:
                lines.append((_("Evite: %s") % " · ".join("%s %d%%" % (analysis.element_name(a), p)
                                                         for a, p in avoid), "#f87171"))
        if mine and (el or d.get("immune")):
            if d.get("immune"):
                pct = 0 if mine == d["immune"] else 100
            else:
                import dedoduro
                pct = ((dedoduro.RATHENA.get("attr") or {}).get(str(level)) or {}).get(mine, {}).get(el)
            if pct is not None:
                lines.append((_("Seu ataque: %s → %d%%") % (analysis.element_name(mine), pct),
                              "#f87171" if pct < 100 else ("#4ade80" if pct > 100 else dim)))
        self.draw_card("bosscard", shown, BOSS_CARD_S, sev, title, lines, d.get("sprite"))

    def death_menu(self):
        """Botão direito no resumo da morte: fechar ou desligar de vez (volta pelo menu de opções)."""
        m = self.new_menu()
        m.add_command(label=_("Fechar este resumo"), command=self.close_death_card)
        m.add_command(label=_("Não mostrar mais o resumo da morte"), command=lambda: self.toggle_cfg("death_card"))
        m.add_command(label=_("Ver todas as mortes na análise…"), command=self.open_deaths)
        return m

    def open_deaths(self):
        self.close_death_card()
        self.open_analysis()
        if self.analysis is not None:
            try:
                self.analysis.select_tab("mortes")
            except Exception:  # noqa: BLE001
                self.log_error(*sys.exc_info())

    def toggle_cfg(self, key):
        self.cfg[key] = not self.cfg[key]
        if key == "death_card" and not self.cfg[key]:
            self.death_card = None
        if key.startswith("alert_") and not self.cfg[key]:
            self.alert = None
        self.save()
        self.dirty = True

    def open_file(self):
        start = self.watcher.folder or os.path.expanduser("~")
        path = filedialog.askopenfilename(parent=self.root, title=_("Abrir replay"), initialdir=start,
                                          filetypes=[(_("Replay do Ragnarok"), "*.rrf"), (_("Todos"), "*.*")])
        if path:
            self.watcher.gap_ms = self.gap_ms()
            self.watcher.open(path)
            self.enc_back = 0
            self.dirty = True

    def follow(self):
        self.watcher.follow()
        self.enc_back = 0
        self.dirty = True

    def pick_folder(self):
        path = filedialog.askdirectory(parent=self.root,
                                       title=_("Escolha a pasta do Ragnarok (ou a pasta Replay dentro dela)"),
                                       initialdir=self.watcher.folder or "C:\\")
        if path:
            self.cfg["folder"] = meter.replay_dir_for(path)       # aceita a pasta do jogo ou a Replay
            self.save()
            self.watcher.set_folder(self.cfg["folder"])
            self.dirty = True

    def minimize(self):
        if IS_WIN and self.hwnd:
            user32.ShowWindow(self.hwnd, 6)           # SW_MINIMIZE
        else:
            self.root.iconify()

    def open_analysis(self, tab=None):
        """Abre a análise (ou traz para a frente); `tab`: já na aba pedida."""
        if self.analysis is not None:
            self.analysis.bring_to_front()
        else:
            self.analysis = AnalysisWindow(self)
        if tab:
            self.analysis.select_tab(tab)
            self.analysis.refresh(force=True)

    def open_pings(self):
        """A janela Avisos de item, mesmo sem replay aberto."""
        self.open_analysis()
        self.analysis.open_pings()

    def set_lang(self, code):
        """Troca o idioma: grava e reabre o medidor (os textos são montados ao abrir)."""
        if code == i18n.LANG:
            return
        self.cfg["lang"] = code
        self.save()
        args = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, os.path.abspath(__file__)]
        f = self.watcher.file
        if self.watcher.pinned and f is not None:
            args.append(f.path)
        try:
            subprocess.Popen(args, close_fds=True)
        except OSError:
            return
        self.quit()

    def about(self):
        messagebox.showinfo(_("Sobre"), "Replay Master %s\n\n%s\n\n%s" % (
            VERSION, _("Medidor de DPS para Ragnarok Online (ROLatam) · versão %s") % VERSION,
            _("Só lê o arquivo de replay que o jogo grava. Não lê a memória do jogo, não mexe na rede e não "
              "manda nada para a internet.")), parent=self.root)

    def quit(self):
        self.save_waiting_tests()
        if self.analysis is not None:
            self.analysis.close()
        self.save_position()
        self.root.destroy()

    def activate(self, target):
        kind, key = target
        if kind == "tab":
            self.set_tab(key)
            return
        if kind == "fav":                      # estrela na aba Drops: favorito fica sempre no topo
            self.toggle_fav(key)
            return
        actions = {
            "pin": self.toggle_pin, "min": self.minimize, "close": self.quit,
            "more": lambda: self.popup_at(target, self.main_menu),
            "view": lambda: self.popup_at(target, self.view_menu), "reset": self.reset, "chart": self.open_analysis,
            "prev": lambda: self.browse(1), "next": lambda: self.browse(-1), "where": self.copy_where,
            "shot": self.copy_image,
        }
        actions[key]()

    def copy_image(self):
        """Copia o widget como imagem (para colar no Discord). Com "sem nomes", cada jogador aparece como a classe."""
        import clipimg
        cb = self.combat()
        hide = bool(self.cfg.get("copy_hide_names")) and cb is not None
        ok = False
        try:
            if hide:
                meter.HIDE_NAMES = True
                cb.version += 1
            self.hover = None                     # sem o realce do botão que acabou de ser clicado
            self.draw()
            self.root.update_idletasks()
            ok = clipimg.copy_window(self.hwnd)
        except Exception:  # noqa: BLE001
            self.log_error(*sys.exc_info())
        finally:
            if hide:
                meter.HIDE_NAMES = False
                cb.version += 1
        self.alert = (_("Imagem copiada: cole com Ctrl+V") if ok else _("Não deu para copiar a imagem"), "info",
                      time.time())
        self.dirty = True

    def copy_where(self):
        """Copia o /navi de onde quem grava está (no formato do jogo: /navi mapa x/y)."""
        cb = self.combat()
        w = cb.where() if cb is not None else None
        if not w or w[1] is None:
            return
        cmd = "/navi %s %d/%d" % (w[0], w[1], w[2])
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(cmd)
        except tk.TclError:
            return
        self.alert = (_("Copiado: %s") % cmd, "info", time.time())
        self.dirty = True

    # ------------------------------------------------------------ menus

    def new_menu(self, parent=None):
        return tk.Menu(parent or self.root, tearoff=0)

    def keep(self, obj):
        self.menu_refs.append(obj)
        return obj

    def swatch(self, theme):
        h = max(12, int(round(14 * self.dpi)))
        img = self.keep(tk.PhotoImage(master=self.root, width=h * 2, height=h))
        img.put(theme["bg"], to=(0, 0, h * 2, h))
        b = max(2, h // 5)
        img.put(theme["accent"], to=(b, b, h, h - b))
        img.put(theme["live"], to=(h + 1, b, h * 2 - b, h - b))
        return img

    def main_menu(self, parent=None):
        m = self.new_menu(parent)
        cfg = self.cfg
        pinned = self.keep(tk.BooleanVar(self.root, cfg["pinned"]))
        m.add_checkbutton(label=_("Fixar sempre no topo"), variable=pinned, command=self.toggle_pin)
        m.add_cascade(label=_("Mostrar"), menu=self.view_menu(m))
        m.add_cascade(label=_("Contar dano em"), menu=self.targets_menu(m))
        pct = self.keep(tk.BooleanVar(self.root, cfg["show_pct"]))
        m.add_checkbutton(label=_("Grupo: mostrar % em vez de DPS"), variable=pct, command=self.toggle_pct)
        m.add_cascade(label=_("DPS"), menu=self.rate_menu(m))
        m.add_command(label=_("Zerar"), command=self.reset)
        m.add_separator()
        m.add_command(label=_("Análise completa…"), command=self.open_analysis)
        if self.last_session:
            m.add_command(label=_("Resumo da última sessão"), command=self.reopen_session)
        m.add_command(label=_("Cartões e efeitos acompanhados…"), command=lambda: self.open_analysis("cartoes"))
        m.add_command(label=_("Avisos de item…"), command=self.open_pings)
        m.add_command(label=_("Relatório de aprendizado…"), command=self.open_report)
        m.add_command(label=_("Copiar a imagem do widget"), command=self.copy_image)
        hide = self.keep(tk.BooleanVar(self.root, cfg["copy_hide_names"]))
        m.add_checkbutton(label=_("Copiar imagem sem os nomes dos jogadores"), variable=hide,
                          command=lambda: self.toggle_cfg("copy_hide_names"))
        for key, label in (("alert_buffs", _("Avisar quando um buff acabar na luta")),
                           ("alert_death", _("Avisar quando eu morrer (com overkill)")),
                           ("death_card", _("Mostrar o que me matou por 10 s (resumo da morte)")),
                           ("alert_boss", _("Avisos do chefe: propriedade, tamanho e mecânicas (5 s)")),
                           ("fight_summary", _("Resumo no fim da luta contra chefe (Dedo Duro)")),
                           ("alert_rec", _("Lembrar quando o jogo está aberto sem gravar")),
                           ("alert_fusion", _("Avisar HP baixo com a União Solar (Mestre Taekwon)")),
                           ("alert_miracle", _("Festejar o Milagre Solar, Lunar e Estelar (Mestre Taekwon)")),
                           ("auto_tests", _("Salvar testes no boneco sozinho"))):
            var = self.keep(tk.BooleanVar(self.root, cfg[key]))
            m.add_checkbutton(label=label, variable=var, command=lambda k=key: self.toggle_cfg(k))
        m.add_cascade(label=_("Sons"), menu=self.sound_menu(m))
        m.add_cascade(label=_("Faixa fixa"), menu=self.pins_menu(m))
        hm = self.hidden_menu(m)
        if hm is not None:
            m.add_cascade(label=_("Drops ocultos"), menu=hm)

        m.add_command(label=_("Abrir replay salvo…"), command=self.open_file)
        if self.watcher.pinned:
            m.add_command(label=_("Voltar a seguir a gravação"), command=self.follow)
        m.add_command(label=_("Pasta dos replays…"), command=self.pick_folder)
        for folder in self.watcher.folders[:5] or [_("(não encontrada)")]:
            m.add_command(label="  " + folder, state="disabled")
        m.add_separator()

        color = self.new_menu(m)
        var = self.keep(tk.StringVar(self.root, cfg["theme"]))
        for name, theme in THEMES.items():
            color.add_radiobutton(label="  " + _(name), image=self.swatch(theme), compound="left",
                                  variable=var, value=name, command=lambda n=name: self.set_theme(n))
        m.add_cascade(label=_("Cor"), menu=color)
        size = self.new_menu(m)
        scale_var = self.keep(tk.DoubleVar(self.root, cfg["scale"]))
        for value, label in SIZES:
            size.add_radiobutton(label="%s (%d%%)" % (label, value * 100), variable=scale_var, value=value,
                                 command=lambda v=value: self.set_scale(v))
        size.add_separator()
        width_var = self.keep(tk.IntVar(self.root, self.base_w()))
        for value, label in WIDTHS:
            size.add_radiobutton(label=_("Largura: %s") % label, variable=width_var, value=value,
                                 command=lambda v=value: self.set_width(v))
        size.add_separator()
        size.add_command(label=_("Arraste o canto: largura e linhas"), state="disabled")
        size.add_command(label=_("Ctrl + roda (ou Shift + arrastar): zoom"), state="disabled")
        m.add_cascade(label=_("Tamanho"), menu=size)
        rows = self.new_menu(m)
        rows_var = self.keep(tk.IntVar(self.root, cfg["rows"]))
        for value in sorted(set(ROW_CHOICES + [cfg["rows"]])):
            rows.add_radiobutton(label=_("%d linhas") % value, variable=rows_var, value=value,
                                 command=lambda v=value: self.set_rows(v))
        m.add_cascade(label=_("Linhas"), menu=rows)
        alpha = self.new_menu(m)
        alpha_var = self.keep(tk.DoubleVar(self.root, cfg["alpha"]))
        for value in ALPHAS:
            alpha.add_radiobutton(label="%d%%" % round(value * 100), variable=alpha_var, value=value,
                                  command=lambda v=value: self.set_alpha(v))
        m.add_cascade(label=_("Opacidade"), menu=alpha)
        lang = self.new_menu(m)
        lang_var = self.keep(tk.StringVar(self.root, i18n.LANG))
        for code, label in i18n.LANGS:
            lang.add_radiobutton(label=label, variable=lang_var, value=code, command=lambda c=code: self.set_lang(c))
        m.add_cascade(label="%s / Language" % _("Idioma") if i18n.LANG != "en" else "Language", menu=lang)
        m.add_command(label=_("Sobre"), command=self.about)
        m.add_separator()
        m.add_command(label=_("Minimizar"), command=self.minimize)
        m.add_command(label=_("Fechar"), command=self.quit)
        return m

    def popup(self, factory, x, y):
        if self.menu is not None:
            self.menu.destroy()
        self.menu_refs = []
        self.menu = factory()
        prev = None
        if IS_WIN and self.hwnd:
            # o menu precisa da janela ativa para fechar direito; depois o foco volta para o jogo
            prev = user32.GetForegroundWindow()
            user32.SetForegroundWindow(self.hwnd)
        try:
            self.menu.tk_popup(int(x), int(y))
        finally:
            self.menu.grab_release()
        if prev and prev != self.hwnd:
            self.root.after(250, lambda: self.give_back_focus(prev))

    def give_back_focus(self, prev):
        # só devolve se nada novo abriu (diálogo de arquivo, janela de análise...)
        if IS_WIN and user32.GetForegroundWindow() == self.hwnd:
            user32.SetForegroundWindow(prev)

    def popup_at(self, target, factory):
        box = next((b for tg, b in self.hits if tg == target), None)
        x0, y1 = (box[0], box[3]) if box else (0, 0)
        self.popup(factory, self.root.winfo_rootx() + x0, self.root.winfo_rooty() + y1 + 2)

    # ------------------------------------------------------------ eventos

    def target_at(self, x, y):
        for target, (x0, y0, x1, y1) in reversed(self.hits):
            if x0 <= x <= x1 and y0 <= y <= y1:
                return target
        return None

    def set_hover(self, target):
        if target != self.hover:
            self.hover = target
            self.draw()

    def on_motion(self, e):
        if not (self.drag or self.resize):
            self.set_hover(self.target_at(e.x, e.y))

    def on_press(self, e):
        self.pressed = self.drag = self.resize = None
        tgt = self.press_target = self.target_at(e.x, e.y)
        if tgt and tgt[0] in ("btn", "tab", "fav"):
            self.pressed = tgt
        elif tgt and tgt[0] == "grip":
            # arrastar o canto muda largura e número de linhas; com Shift, o zoom
            self.resize = (e.x_root, e.y_root, self.W, self.H, self.cfg["scale"], bool(e.state & 0x1))
        else:
            self.drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())
            self.press_xy = (e.x_root, e.y_root)

    def on_drag(self, e):
        if self.drag:
            dx, dy = self.drag
            self.root.geometry("+%d+%d" % (e.x_root - dx, e.y_root - dy))
        elif self.resize:
            x0, y0, w0, h0, sc0, zoom = self.resize
            if zoom:
                ratio = max((w0 + e.x_root - x0) / w0, (h0 + e.y_root - y0) / h0)
                self.set_scale(sc0 * ratio, save=False)
                return
            s = self.s
            width = int(round((w0 + e.x_root - x0) / s))
            rows = int(round(((h0 + e.y_root - y0) / s - self.rows_y0() - 6 - FOOT_H) / ROW_H))
            width = max(MIN_W, min(MAX_W, width))
            rows = max(MIN_ROWS, min(MAX_ROWS, rows))
            if width != self.base_w() or rows != self.cfg["rows"]:
                self.cfg["width"], self.cfg["rows"] = width, rows
                self.resize_window()

    def on_release(self, e):
        if self.pressed:
            tgt, self.pressed = self.pressed, None
            if self.target_at(e.x, e.y) == tgt:
                self.activate(tgt)
        elif self.drag:
            self.drag = None
            moved = self.press_xy and abs(e.x_root - self.press_xy[0]) + abs(e.y_root - self.press_xy[1]) > 4
            if not moved and self.press_target and self.press_target[0] == "death":
                self.close_death_card()
            elif not moved and self.press_target and self.press_target[0] == "bosscard":
                self.boss_card = None
                self.dirty = True
            elif not moved and self.press_target and self.press_target[0] == "summary":
                self.open_summary()
            elif not moved and self.press_target and self.press_target[0] == "session":
                self.open_session()
            elif not moved and self.press_target and self.press_target[0] == "fxcard":
                self.close_fx_card()
            elif not moved and self.press_target and self.press_target[0] == "ping":
                self.copy_ping()
            elif not moved and not self.watcher.folders:
                self.pick_folder()
            else:
                self.save_position()
        elif self.resize:
            self.resize = None
            self.save()

    def on_right_click(self, e):
        tgt = self.target_at(e.x, e.y)
        if tgt and tgt[0] in ("row", "fav", "pinbar"):
            self.popup(lambda: self.row_menu(tgt), e.x_root, e.y_root)
        elif tgt and tgt[0] == "death":
            self.popup(self.death_menu, e.x_root, e.y_root)
        elif tgt and tgt[0] == "bosscard":
            self.popup(self.boss_menu, e.x_root, e.y_root)
        elif tgt and tgt[0] == "summary":
            self.popup(self.summary_menu, e.x_root, e.y_root)
        elif tgt and tgt[0] == "session":
            self.popup(self.session_menu, e.x_root, e.y_root)
        elif tgt and tgt[0] == "ping":
            self.popup(self.ping_menu, e.x_root, e.y_root)
        elif tgt and tgt[0] == "tracker":
            self.popup(lambda: self.tracker_menu(tgt[1]), e.x_root, e.y_root)
        elif tgt and tgt[0] == "fxcard" and self.fx_now:
            self.popup(lambda: self.tracker_menu(self.fx_now[0]["key"]), e.x_root, e.y_root)
        else:
            self.popup(self.main_menu, e.x_root, e.y_root)

    def on_wheel(self, e):
        if e.state & 0x4:                                   # Ctrl
            self.set_scale(self.cfg["scale"] * (1.08 if e.delta > 0 else 1 / 1.08))
        elif self.cfg["tab"] == "drops":                    # rola a lista de itens (3 por "clique" da roda)
            first, shown, total = self.drop_view
            step = DROP_SCROLL_ROWS * max(1, abs(e.delta) // 120)
            new = max(0, min(total - shown, first + (-step if e.delta > 0 else step)))
            if new != first:
                self.drop_scroll = new
                self.dirty = True


def selftest(app, report):
    """Autoteste do pacote (`ReplayMaster.exe replay.rrf --autoteste saida.txt`): espera o replay ser lido, abre a
    análise, passa por todas as abas, monta o desenho de um monstro do replay e grava em `report` o que deu
    certo. É para quem monta o pacote conferir o .exe por dentro; o programa fecha sozinho no fim."""
    lines = ["Replay Master %s" % VERSION]
    t0 = time.time()

    def finish():
        try:
            with open(report, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except OSError:
            pass
        app.root.destroy()

    def sprite(tries=0):
        try:
            import gdip
            import ui_parts
            book = sprites.MONSTERS.book
            if book is None and tries < 60 and sprites.MONSTERS.error is None and clientdata.NAMES.grf:
                ui_parts.start_loaders()
                app.root.after(250, lambda: sprite(tries + 1))
                return
            c = app.combat()
            mobs = sorted({e.job for e in c.entities.values() if e.kind == "mob"}) if c is not None else []
            mob = next((m for m in mobs if book is not None and book.has(m)), None)
            if mob is None:
                lines.append("desenho: sem jogo instalado ou sem monstro com sprite neste replay")
            else:
                made = ui_parts.mob_frames(app.root, book.part(mob), sprites.MOB_IDLE, 0, 164, 134, {})
                lines.append("desenho do monstro %d: %d quadros de %dx%d, GDI+ %s" % (
                    mob, len(made[0]), made[0][0].width(), made[0][0].height(), "ok" if gdip.ready() else "indisponível"))
        except Exception:  # noqa: BLE001
            lines.append("ERRO no desenho\n" + traceback.format_exc())
        lines.append("fim em %.1f s" % (time.time() - t0))
        finish()

    def tabs():
        try:
            import analysis_ui
            f = app.watcher.file
            if (f is None or not f.ready or f.pos < f.size) and time.time() - t0 < 60:
                app.root.after(200, tabs)
                return
            c = app.combat()
            lines.append("replay: %s" % ("%d golpes" % len(c.hits) if c is not None else "NÃO LIDO"))
            app.open_analysis()
            for tab in analysis_ui.TABS:
                t1 = time.time()
                app.analysis.select_tab(tab)
                app.analysis.refresh(force=True)
                app.analysis.top.update()
                lines.append("aba %s: ok (%.2f s)" % (tab, time.time() - t1))
        except Exception:  # noqa: BLE001
            lines.append("ERRO nas abas\n" + traceback.format_exc())
            finish()
            return
        app.root.after(300, sprite)
    app.root.after(800, tabs)


def main():
    if learnfolder.ARG in sys.argv:              # o processo que lê as gravações da pasta: sem janela, e acaba sozinho
        learnfolder.child(sys.argv)
        return
    if IS_WIN:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (OSError, AttributeError):
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except (OSError, AttributeError):
                pass
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RODpsMeter.ReplayMaster")
        except (OSError, AttributeError):
            pass
    sys.setswitchinterval(SWITCH_S)
    root = tk.Tk()
    args = sys.argv[1:]
    report = None
    if "--autoteste" in args:                    # confere o pacote por dentro e fecha (veja selftest)
        i = args.index("--autoteste")
        report = args[i + 1] if i + 1 < len(args) else None
        del args[i:i + 2]
    path = args[0] if args and os.path.isfile(args[0]) else None
    app = DpsApp(root, path)
    app.watch_stalls()
    if report:
        selftest(app, report)
    root.mainloop()


if __name__ == "__main__":
    main()
