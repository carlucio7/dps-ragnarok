# -*- coding: utf-8 -*-
"""As cenas dos cartões de classe do resumo da sessão (roles.py): Redentor, Chuva de Lex, Podem ir, Sem mim era Wipe,
Oi tchau, Quero um aumento, Bem servido e Tá fácil pra ninguém, cada uma num palco no pé do cartão, com os desenhos
do jogo (data.grf): quem grava (o personagem dele, de qualquer classe), as classes do grupo, o chefe ou os monstros
da gravação, os ícones dos buffs e dos itens, os emotes e alguns efeitos de skill (.str) desenhados em escala pelo
GDI+.

É uma mistura (mixin) do widget: usa o canvas, o zoom (self.s) e os desenhos dele (draw_number, draw_burst,
scene_look, fx_bgra, bgra_photo). Tudo o que a cena usa é montado uma vez (class_assets, na hora em que o resumo
aparece) e guardado; cada quadro só põe as imagens prontas no canvas. Sem os desenhos do jogo, a cena não desenha
(draw_class_fx devolve False) e quem chamou usa o brilho de sempre.

Das versões que o usuário testou na 1.14.0-teste2 (2026-11-22) ficaram a B do Redentor, da Chuva de Lex (agora com a
cruz da Lex caindo na cabeça do chefe, como no jogo) e do Podem ir, e a A do Sem mim era Wipe e do Oi, tchau.
"""

import base64
import math
import random
import struct
import sys
import threading
import tkinter as tk

import gdip
import lub
import sprites
import streffect
from ui_parts import mix

CLASS_FX = ("bulwark", "lex_double", "buff_wings", "credit_boss", "aoe_blast", "revive", "served_ks", "served_mvp",
            "no_elixir")
# altura do palco de cada cena (zoom 1): os personagens têm 38 de altura e os ícones e números vão por cima
STAGE_HS = {"bulwark": 62, "lex_double": 62, "buff_wings": 66, "credit_boss": 62, "aoe_blast": 60, "revive": 62,
            "served_ks": 62, "served_mvp": 64, "no_elixir": 62}
# o cartão de cada cena (para o personagem de exemplo, sem o visual de quem grava)
KIND_KEY = {"bulwark": "redeemer", "lex_double": "lex", "buff_wings": "buffed", "credit_boss": "credit",
            "aoe_blast": "aoe", "revive": "revive", "served_ks": "served", "served_mvp": "served",
            "no_elixir": "no_elixir"}
HERO_H = 38                   # altura do corpo com a cabeça (zoom 1)
ALLY_H = 34
MOB_BOX = (46, 44)            # o chefe cabe nesta caixa
CROWD_BOX = (22, 20)          # os monstros do "Oi, tchau"
EMOTE_BOX = 22                # os emotes do jogo
SCENE_KEEP = 6                # cenas montadas guardadas (a prévia da aba Cartões passa de uma para a outra)
RIGHT, LEFT, FRONT = 6, 2, 0  # direções do .act (6 = olhando para a direita)
EFF = "data\\texture\\effect\\"
ICON_LUA = "data\\luafiles514\\lua files\\stateicon\\"
# os ícones das skills antigas não estão na tabela de ícones do jogo (o cliente sabe de cor): o arquivo de cada um
OLD_ICONS = {9: "안젤루스.tga", 10: "블레싱.tga", 12: "민첩성증가.tga", 15: "임포시티오마누스.tga",
             16: "수프라기움.tga", 19: "기리에엘레이손.tga", 20: "마니피캇.tga", 21: "글로리아.tga",
             22: "렉스에테르나.tga", 336: "레노바티오.tga", 340: "EXPIATIO.TGA", 473: "ICON05.tga"}
DEVOTION_ICON = "헌신.tga"     # o ícone da Redenção
# skill de buff -> o status (o ícone) que ela põe
SKILL_STATUS = {5282: 1228, 5281: 1227, 5275: 1200, 5272: 1199, 5271: 1198, 5278: 1201, 5269: 1197, 2041: 10,
                2042: 12, 34: 10, 29: 12, 66: 15, 67: 16, 2045: 19, 74: 20, 75: 21, 2050: 336, 361: 1121,
                2047: 331, 2048: 332, 2053: 340, 33: 9, 78: 22}
# efeitos de skill do jogo usados nas cenas; "lex": a cruz vermelha da Lex Aeterna (o efeito clássico, cross1.bmp)
STR = {"guardian": "imperial_guard\\ig_guardian_shield\\new_guardianshield\\guardianshield\\guardianshield.str",
       "competentia": "competentia\\competentia\\competentia.str",
       "benedictum": "benedictum\\benedictum\\benedictum.str",
       "allbloom": "allbloom\\allbloom\\allbloom.str",
       "comet": "new_comet\\new_comet_sub_explosion\\new_comet_sub_explosion.str",
       "quake": "new_rush_quake\\new_rush_quake_bottom\\new_rush_quake.str",
       "lex": "red_cross.str"}
STR_SCALE = 0.42              # os efeitos no tamanho dos personagens do palco (zoom 1)
LEX_SCALE = 0.36              # a cruz da Lex: pequena, na cabeça do chefe
# quanto o efeito pode descer abaixo de onde ele é posto (zoom 1): o pé do cartão; a explosão do Cometa passava do
# cartão e cobria o rodapé do widget
STR_BELOW = {"competentia": 23, "comet": 11}
STR_FRAMES = 16               # quadros guardados de cada efeito
STR_KEEP = 4                  # efeitos (quadros crus) guardados ao mesmo tempo
# os emotes do jogo (emotion.spr, a ação de cada um): /omg, o joinha com piscadinha, o /swt (gota de suor) e o "!!"
EMOTE_OMG, EMOTE_WINK, EMOTE_SWEAT, EMOTE_HUK = 75, 21, 5, 23
# um personagem de cada classe para quando não há o visual (a prévia e os aliados): classe, sexo, cabelo, cor do
# cabelo, arma (o tipo) e escudo
LOOKS = {
    4252: dict(sex=1, hair=5, hair_color=1, weapon=3), 4253: dict(sex=1, hair=3, hair_color=0, weapon=6),
    4254: dict(sex=1, hair=9, hair_color=1, weapon=16), 4255: dict(sex=0, hair=11, hair_color=6, weapon=23),
    4256: dict(sex=0, hair=17, hair_color=2, weapon=15), 4257: dict(sex=1, hair=12, hair_color=4, weapon=11),
    4258: dict(sex=1, hair=2, hair_color=3, weapon=4, shield=3), 4259: dict(sex=0, hair=8, hair_color=7, weapon=8),
    4260: dict(sex=0, hair=13, hair_color=0, weapon=1), 4261: dict(sex=0, hair=5, hair_color=4, weapon=10),
    4262: dict(sex=1, hair=8, hair_color=0, weapon=12), 4263: dict(sex=1, hair=10, hair_color=2, weapon=13),
    4264: dict(sex=0, hair=16, hair_color=5, weapon=14), 4302: dict(sex=1, hair=6, hair_color=0, weapon=0),
    4303: dict(sex=0, hair=14, hair_color=3, weapon=10), 4304: dict(sex=1, hair=4, hair_color=1, weapon=1),
    4305: dict(sex=0, hair=9, hair_color=6, weapon=1), 4306: dict(sex=1, hair=7, hair_color=2, weapon=17),
    4307: dict(sex=1, hair=3, hair_color=5, weapon=2), 4308: dict(sex=0, hair=2, hair_color=1, weapon=10),
    4066: dict(sex=1, hair=2, hair_color=3, weapon=4, shield=3), 4073: dict(sex=1, hair=2, hair_color=3, weapon=4,
                                                                            shield=3),   # o Guardião Real (e o trans)
}
DEFAULT_ALLIES = (4302, 4255, 4254, 4262)
DEFAULT_OTHERS = (4252, 4260, 4253)   # os outros jogadores do "Bem servido" sem saber quem eram
INSIGNIA = {-2465: "#38bdf8", -2466: "#86efac", -2467: "#d6a38f", -2468: "#f97316", -285: "#f97316",
            -286: "#38bdf8", -287: "#86efac"}
RED_TINT, GOLD_TINT, TEAL_TINT = (255, 110, 80), (255, 214, 90), (94, 234, 212)
HEAL_TINT = (110, 240, 130)   # a cura do elixir: os números verdes do jogo


def round_pts(x1, y1, x2, y2, r):
    """Os pontos de um retângulo arredondado (para create_polygon com smooth=True)."""
    r = max(0.0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return [x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y1 + r,
            x2, y2 - r, x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2,
            x1, y2, x1, y2 - r, x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1]


def look_for(job, n=0):
    """Um visual da classe `job` (LOOKS; outras classes: um cabelo e uma cor que variam com `n`)."""
    base = LOOKS.get(job)
    if base is None:
        base = dict(sex=(job + n) % 2, hair=2 + (job + n) % 9, hair_color=(job + 3 * n) % 8, weapon=0)
    return dict(base, job=job)


def weapon_attack(w, look, direction=RIGHT):
    """A ação de ataque com a arma deste visual, achada nos desenhos da própria arma: nas sprites do jogo as ações 5 e
    10 são o soco e o chute sem arma, e o golpe com a arma é a 11 (espada, lança, arco, katar, machado, maça) ou a 10
    (adaga, instrumento, arma de fogo); vale a ação em que a arma aparece em mais quadros. None sem arma (o Mado
    Gear, o livro do Mestre Celestial)."""
    try:
        order, _body, _missing = w.parts(look, direction)
    except Exception:  # noqa: BLE001 - visual estranho: sem arma
        return None
    part = next((p for p in order if p.name == "weapon"), None)
    if part is None:
        return None
    best, score = None, 0
    for act in (sprites.ATTACK3, sprites.ATTACK2, sprites.ATTACK):
        frames = part.act.frames(act * 8 + direction)
        n = sum(1 for layers, _anchors in frames if any(ly.index >= 0 for ly in layers))
        if n > score:
            best, score = act, n
    return best


def attack_act(w, look, direction=RIGHT):
    """A ação de ataque da classe na cena (o usuário, 2026-11-22: socos e chutes só para Monges e Taekwons): as de
    magia e suporte conjuram, as de punho socam e as outras golpeiam com a arma (weapon_attack; sem arma, o soco)."""
    import session
    style = session.fight_style(look.get("job") or 0)
    if style == "magic":
        return sprites.CAST
    if style == "fist":
        return sprites.ATTACK
    return weapon_attack(w, look, direction) or sprites.ATTACK


class EffectKit:
    """Os efeitos de skill (.str) e os ícones de buff do data.grf, para as cenas de classe: o índice da pasta de
    efeitos abre numa thread (~0,1 s), e cada efeito ou ícone é lido e guardado no primeiro pedido."""

    def __init__(self):
        self.path = None
        self.grf = None
        self.names = {}               # id do status -> arquivo do ícone (tabela do jogo)
        self._thread = None
        self._icons = {}
        self._str = {}
        self._pending = set()         # efeitos sendo desenhados numa thread (prefetch)
        self._lock = threading.Lock()
        self.error = None

    def start(self, grf_path):
        if not grf_path or (self.path == grf_path and (self.grf or self._thread)):
            return
        self.path, self.grf = grf_path, None

        def run():
            try:
                g = sprites.Grf(grf_path, prefixes=(EFF, ICON_LUA))
                self.names = self._icon_table(g)
                self.grf = g
            except Exception as e:  # noqa: BLE001 - sem os efeitos: as cenas desenham os seus
                self.error = str(e) or e.__class__.__name__
            finally:
                self._thread = None
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    @staticmethod
    def _icon_table(g):
        try:
            ids = lub.run(g.read(ICON_LUA + "efstids.lub") or b"", "cp949").get("EFST_IDs") or {}
            img = lub.run(g.read(ICON_LUA + "stateiconimginfo.lub") or b"", "cp949").get("StateIconImgList") or {}
        except (ValueError, struct.error, IndexError, KeyError):
            return {}
        by_name = {}
        for tab in img.values():
            if isinstance(tab, dict):
                for k, v in tab.items():
                    by_name[k[1] if isinstance(k, tuple) else k] = v
        return {v: by_name[k] for k, v in ids.items() if k in by_name and isinstance(v, int)}

    def wait(self, timeout=2.0):
        t = self._thread
        if t is not None:
            t.join(timeout)
        return self.grf is not None

    def _texture(self, path):
        data = self.grf.read(path) if self.grf is not None else None
        if not data:
            return None
        try:
            return (streffect.tga_bgra if path.lower().endswith(".tga") else streffect.bmp_bgra)(data)
        except (ValueError, struct.error, IndexError):
            return None

    def icon(self, efst):
        """O ícone do status `efst` (ou o da Redenção, com "devotion"): (w, h, BGRA) ou None."""
        if efst not in self._icons:
            name = DEVOTION_ICON if efst == "devotion" else (OLD_ICONS.get(efst) or self.names.get(efst))
            self._icons[efst] = self._texture(EFF + name) if name else None
        return self._icons[efst]

    def str_frames(self, name, scale, count=STR_FRAMES):
        """Os quadros de um efeito de skill (STR) em escala: (duração em s, [(w, h, RGBA, x, y)]), com (x, y) = o canto
        em relação à origem do efeito (os pés de quem está nele). None sem o efeito."""
        key = (name, round(scale, 3), count)
        with self._lock:
            if key in self._str:
                return self._str[key]
        got = self._render(name, scale, count)
        with self._lock:
            self._keep(key, got)
        return got

    def _render(self, name, scale, count):
        try:
            return self._build(STR[name], scale, count) if gdip.ready() else None
        except (ValueError, struct.error, IndexError, KeyError, ZeroDivisionError):
            return None

    def _keep(self, key, got):
        while len(self._str) >= STR_KEEP:              # os quadros crus ocupam ~1–2 MB por efeito
            self._str.pop(next(iter(self._str)))
        self._str[key] = got

    def ready_frames(self, name, scale, count=STR_FRAMES):
        """(já desenhado?, quadros ou None) de um efeito, sem esperar."""
        key = (name, round(scale, 3), count)
        with self._lock:
            return key in self._str, self._str.get(key)

    def prefetch(self, name, scale, count=STR_FRAMES):
        """Desenha os quadros de um efeito numa thread (o gdip tem a trava para isso): desenhar o Escudo do Guardião ou
        as asas da Competentia leva de 0,3 a 0,5 s, e a janela ficava parada esse tempo quando o resumo aparecia.
        ready_frames diz quando ficou pronto."""
        key = (name, round(scale, 3), count)
        with self._lock:
            if key in self._str or key in self._pending:
                return
            self._pending.add(key)

        def run():
            got = self._render(name, scale, count)
            with self._lock:
                self._keep(key, got)
                self._pending.discard(key)
        threading.Thread(target=run, daemon=True).start()

    def _build(self, path, scale, count):
        data = self.grf.read(EFF + path) if self.grf is not None else None
        if not data:
            return None
        s = streffect.parse(data)
        folder = (EFF + path).rsplit("\\", 1)[0] + "\\" if "\\" in path else EFF
        n = max(1, s["frames"])
        tex = {}
        out = []
        sq = streffect.SQUASH
        for i in range(count):
            f = int(i * n / count)
            ops, imgs = [], []
            for li, layer in enumerate(s["layers"]):
                st = streffect.state(layer, f)
                if st is None or st["tex"] is None or st["color"][3] <= 0.5:
                    continue
                additive = st["dst"] != streffect.NORMAL_DST
                tk_ = (li, st["tex"], additive)
                if tk_ not in tex:
                    t = self._texture(folder + layer["tex"][st["tex"]])
                    tex[tk_] = (t[0], t[1], streffect.glow(t[2]) if additive else t[2]) if t else None
                if tex[tk_] is None:
                    continue
                tw, th, bgra = tex[tk_]
                color = tuple(max(0, min(255, int(v))) for v in st["color"][:3]) + (
                    max(0, min(255, int(st["color"][3]))),)
                xs, ys = st["xy"][:4], st["xy"][4:]
                m11, m12 = (xs[1] - xs[0]) / tw, (ys[1] - ys[0]) / tw
                m21, m22 = (xs[3] - xs[0]) / th, (ys[3] - ys[0]) / th
                if abs(m11 * m22 - m12 * m21) < 1e-7 or any(v != v for v in (m11, m12, m21, m22)):
                    continue
                im = gdip.Image(tw, th, streffect.tint(bgra, color))
                imgs.append(im)
                cx, cy = (xs[1] + xs[3]) / 2.0, (ys[1] + ys[3]) / 2.0
                ang = -math.radians(st["angle"] * 360.0 / 1024.0)
                ca, sa = math.cos(ang), math.sin(ang)
                ox, oy = st["pos"][0] - streffect.ORIGIN[0], sq * (st["pos"][1] - streffect.ORIGIN[1])
                ops.append((im, scale * (m11 * ca - m12 * sa), scale * sq * (m11 * sa + m12 * ca),
                            scale * (m21 * ca - m22 * sa), scale * sq * (m21 * sa + m22 * ca),
                            scale * (cx * ca - cy * sa + ox), scale * (sq * (cx * sa + cy * ca) + oy), True))
            try:
                box = None
                for im, a11, a12, a21, a22, tx, ty, _sm in ops:
                    hw, hh = im.w / 2.0, im.h / 2.0
                    for u in (-hw, hw):
                        for v in (-hh, hh):
                            px, py = u * a11 + v * a21 + tx, u * a12 + v * a22 + ty
                            box = (px, py, px, py) if box is None else (min(box[0], px), min(box[1], py),
                                                                        max(box[2], px), max(box[3], py))
                if box is None:
                    out.append(None)
                    continue
                bx0, by0 = int(math.floor(box[0])) - 1, int(math.floor(box[1])) - 1
                w, h = int(math.ceil(box[2])) + 1 - bx0, int(math.ceil(box[3])) + 1 - by0
                if w <= 0 or h <= 0 or w * h > 360000:
                    out.append(None)
                    continue
                raw = gdip.render(w, h, [(im, a11, a12, a21, a22, tx - bx0, ty - by0, sm)
                                         for im, a11, a12, a21, a22, tx, ty, sm in ops])
                out.append((w, h, gdip.swap_rb(raw), bx0, by0) if raw else None)
            finally:
                for im in imgs:
                    im.close()
        return n / float(s["fps"] or 60), out


KIT = EffectKit()


class ClassScenes:
    """As cenas dos cartões de classe (mistura do widget)."""

    # ------------------------------------------------------------------ montagem

    def class_assets(self, scene, kind):
        """Os desenhos de uma cena de classe, montados uma vez e guardados (as SCENE_KEEP últimas): dict(hero,
        allies, mob, crowd, icons, fx, digits, angel, emotes, item). None sem o guarda-roupa do jogo (a cena não
        desenha)."""
        w = sprites.LOADER.wardrobe
        if w is None:
            return None
        zoom = round(self.s, 3)
        look = self.cs_hero_look(scene, kind)
        allies = self.cs_ally_jobs(scene, kind)
        key = (kind, repr(sorted(look.items())), tuple(allies), scene.get("mob"), scene.get("effect"),
               tuple(scene.get("skills") or scene.get("buffs") or ()), scene.get("item"), zoom)
        cache = getattr(self, "_class_scenes", None)
        if cache is None:
            cache = self._class_scenes = {}
        if key in cache:
            got = cache.pop(key)
            cache[key] = got
            return got
        try:
            out = self.cs_build(w, scene, kind, look, allies)
        except Exception:  # noqa: BLE001 - a cena é um extra: sem ela, o brilho de sempre
            self.log_error(*sys.exc_info())
            out = None
        cache[key] = out
        while len(cache) > SCENE_KEEP:
            cache.pop(next(iter(cache)))
        return out

    @staticmethod
    def cs_hero_look(scene, kind):
        look = scene.get("look")
        if look:
            return dict(look)
        import session
        return look_for(scene.get("job") or session.ROLE_JOBS[KIND_KEY[kind]][0])

    @staticmethod
    def cs_ally_jobs(scene, kind):
        """As classes dos outros personagens da cena: os aliados do grupo; no "Bem servido", os outros jogadores (quem
        levou o KS, quem bateu no MVP antes)."""
        n = {"bulwark": 3, "lex_double": 2, "buff_wings": 4, "credit_boss": 2, "revive": 3, "served_ks": 1,
             "served_mvp": 2}.get(kind, 0)
        if kind in ("served_ks", "served_mvp"):
            jobs, fill = [j for j in (scene.get("others") or []) if j], DEFAULT_OTHERS
        else:
            jobs, fill = [j for j in (scene.get("allies") or []) if j], DEFAULT_ALLIES
        out = []
        for j in (jobs or list(fill)) + list(fill):
            if len(out) >= n:
                break
            if j not in out:
                out.append(j)
        return out[:n]

    def cs_build(self, w, scene, kind, look, allies):
        s = self.s
        out = dict(hero={}, allies=[], mob={}, crowd={}, icons={}, fx={}, digits=None, angel=None, emotes={},
                   item=None)
        hero_dir = {"buff_wings": FRONT, "served_ks": LEFT}.get(kind, RIGHT)
        # "hit": o ataque da classe (attack_act): a arma das classes físicas, o soco das de punho, a magia das outras
        hit = ("hit", attack_act(w, look, hero_dir))
        hero_acts = {"bulwark": (sprites.READY, sprites.HURT), "lex_double": (sprites.CAST,),
                     "buff_wings": (sprites.CAST,), "credit_boss": (sprites.CAST,),
                     "aoe_blast": (sprites.CAST, hit), "revive": (sprites.CAST,),
                     "served_ks": (hit,), "served_mvp": (sprites.WALK, hit),
                     "no_elixir": (hit, sprites.HURT, sprites.SIT)}[kind]
        out["hero"] = self.cs_actor(w, look, (sprites.IDLE,) + hero_acts, hero_dir, HERO_H * s)
        if not out["hero"]:
            return None
        for i, job in enumerate(allies):
            ally = look_for(job, i)
            if kind == "buff_wings":
                d, acts = (RIGHT if i < len(allies) / 2.0 else LEFT), (sprites.IDLE,)
            elif kind in ("lex_double", "credit_boss", "served_ks", "served_mvp"):
                d, acts = RIGHT, (sprites.IDLE, ("hit", attack_act(w, ally)))
            elif kind == "revive":
                d, acts = FRONT, (sprites.IDLE, sprites.DEAD, sprites.SIT)
            else:
                d, acts = RIGHT, (sprites.IDLE, sprites.HURT)
            got = self.cs_actor(w, ally, acts, d, ALLY_H * s)
            if got:
                out["allies"].append(got)
        book = sprites.MONSTERS.book
        if book is not None:
            import ui_parts
            mob = scene.get("mob")
            if kind == "aoe_blast":
                target = mob if mob and book.has(mob) else (1002 if book.has(1002) else None)
                part = book.part(target) if target else None
                for action in (sprites.MOB_IDLE, sprites.MOB_DIE):
                    made = ui_parts.mob_frames(self.root, part, action, LEFT, int(CROWD_BOX[0] * s),
                                               int(CROWD_BOX[1] * s), {}) if part is not None else None
                    if made and made[0]:
                        out["crowd"][action] = made
            elif not (kind == "buff_wings" and scene.get("rounds")):
                fallback = 1002 if kind == "served_ks" else 1039
                target = mob if mob and book.has(mob) else (fallback if book.has(fallback) else None)
                part = book.part(target) if target else None
                actions = (sprites.MOB_IDLE, sprites.MOB_ATTACK, sprites.MOB_HURT)
                if kind in ("served_ks", "served_mvp"):
                    actions += (sprites.MOB_DIE,)
                elif kind == "no_elixir":           # só bate (o Betelgeuse levava 0,4 s para montar as três)
                    actions = (sprites.MOB_IDLE, sprites.MOB_ATTACK)
                box = (MOB_BOX[0] * 0.8, MOB_BOX[1] * 0.8) if kind == "served_ks" else MOB_BOX
                for action in actions:
                    made = ui_parts.mob_frames(self.root, part, action, LEFT, int(box[0] * s), int(box[1] * s),
                                               {}) if part is not None else None
                    if made and made[0]:
                        out["mob"][action] = made
            try:
                out["digits"] = book.digits()
            except Exception:  # noqa: BLE001 - sem os números do jogo: os escritos
                out["digits"] = None
            if kind == "revive":
                ang = book.effect_tex("angel")
                if ang:
                    img = (ang[0], ang[1], streffect.glow(ang[2]))
                    out["angel"] = self.bgra_photo(*self.fx_bgra(img, 26 * s * ang[0] / float(ang[1]), 26 * s, 0.9))
            if kind in ("served_ks", "served_mvp", "no_elixir"):
                out["emotes"] = self.cs_emotes(book, (EMOTE_OMG, EMOTE_WINK, EMOTE_HUK) if kind != "no_elixir"
                                               else (EMOTE_SWEAT,))
            if kind == "no_elixir" and scene.get("item"):
                out["item"] = self.cs_item_icon(book, scene["item"], 15 * s)
        out["photos"] = {}
        # efeitos e ícones do jogo
        if KIT.wait(1.5):
            want = {"bulwark": ("guardian",), "buff_wings": ("competentia", "benedictum"),
                    "aoe_blast": ("comet",), "lex_double": ("lex",)}.get(kind, ())
            if kind == "credit_boss":
                eff = scene.get("effect")
                want = ("allbloom",) if eff in (1183, 1182, 1184) else ("comet",) if eff == 1142 else \
                    ("quake",) if eff == 1402 else ()
            out["fx_wait"] = {}
            for name in want:
                scale = (LEX_SCALE if name == "lex" else STR_SCALE) * s * {
                    "comet": 1.3 if kind == "aoe_blast" else 1.0, "allbloom": 0.55}.get(name, 1.0)
                done, made = KIT.ready_frames(name, scale)
                if done:
                    if made:
                        out["fx"][name] = self.cs_fx_photos(made, kind, name)
                else:                       # desenhado numa thread: a cena começa sem ele e o pega quando ficar pronto
                    KIT.prefetch(name, scale)
                    out["fx_wait"][name] = (scale, kind)
            ids = []
            if kind == "buff_wings":
                # os buffs que ele mais usou (a Lex é no chefe: fica de fora)
                ids = [SKILL_STATUS[k] for k in (scene.get("skills") or []) if SKILL_STATUS.get(k, 22) != 22]
                ids += [e for e in (scene.get("buffs") or []) if e not in ids]
            elif kind == "lex_double":
                ids = [22]
            elif kind == "bulwark":
                ids = ["devotion"]
            elif kind == "credit_boss" and scene.get("effect") is not None:
                ids = [scene["effect"]] if scene["effect"] > 0 else []
            seen = []
            for e in ids:
                if e in seen:
                    continue
                img = KIT.icon(e)
                if img:
                    seen.append(e)
                    out["icons"][e] = self.bgra_photo(*self.fx_bgra(img, 12 * s, 12 * s))
                if len(seen) >= 6:
                    break
            out["icon_order"] = seen
        return out

    def cs_emotes(self, book, ids):
        """{emote: ([fotos], ms por quadro)} dos emotes do jogo (emotion.spr: uma ação por emote)."""
        import ui_parts
        try:
            spr = book.grf.read(sprites.EFFECT_SPR + "emotion.spr")
            act = book.grf.read(sprites.EFFECT_SPR + "emotion.act")
            part = sprites.Part("emotion", sprites.Sprite(spr), sprites.Act(act)) if spr and act else None
        except Exception:  # noqa: BLE001 - sem os emotes: a cena segue sem eles
            part = None
        out = {}
        if part is None:
            return out
        box = int(EMOTE_BOX * self.s)
        for i in ids:
            made = ui_parts.mob_frames(self.root, part, i // 8, i % 8, box, box, {})
            if made and made[0]:
                out[i] = made
        return out

    def cs_item_icon(self, book, item, size):
        """O ícone (24 × 24 no jogo) do item no tamanho `size`, ou None sem a lista de itens ou o desenho."""
        try:
            import xp
            art = xp.GEAR.art.get(item)
        except (ImportError, AttributeError):
            art = None
        img = book.icon(art) if art else None
        if not img:
            return None
        w, h, px = img
        return self.cs_photo(w, h, px, size / float(max(w, h)))

    def cs_fx_photos(self, made, kind, name):
        """(duração, [(foto, x, y)]) de um efeito já desenhado, cortado no palco da cena."""
        s = self.s
        secs, frames = made
        photos = []
        lo, hi = -(STAGE_HS.get(kind, 60) + 24) * s, STR_BELOW.get(name, 7 if name != "lex" else 40) * s
        for fr in frames:
            fr = self.cs_crop(fr, lo, hi)
            if fr is None:
                photos.append(None)
                continue
            fw, fh, rgba, fx0, fy0 = fr
            photos.append((tk.PhotoImage(master=self.root, data=base64.b64encode(
                sprites.png_rgba(fw, fh, rgba)).decode("ascii"), format="png"), fx0, fy0))
        return secs, photos

    def cs_fx_get(self, a, name):
        """Os quadros de um efeito da cena; o que estava sendo desenhado numa thread entra assim que fica pronto."""
        got = a["fx"].get(name)
        if got is None and name in a.get("fx_wait", {}):
            scale, kind = a["fx_wait"][name]
            done, made = KIT.ready_frames(name, scale)
            if done:
                a["fx_wait"].pop(name, None)
                if made:
                    got = a["fx"][name] = self.cs_fx_photos(made, kind, name)
        return got

    @staticmethod
    def cs_crop(fr, lo, hi):
        """O quadro de efeito (w, h, RGBA, x, y) só com as linhas entre `lo` e `hi` (em relação à origem), ou None."""
        if fr is None:
            return None
        w, h, rgba, x0, y0 = fr
        r0, r1 = max(0, int(math.ceil(lo - y0))), min(h, int(math.floor(hi - y0)))
        if r1 <= r0:
            return None
        if r0 == 0 and r1 == h:
            return fr
        return w, r1 - r0, rgba[r0 * w * 4:r1 * w * 4], x0, y0 + r0

    def cs_actor(self, w, look, acts, direction, height):
        """{ação: ([(foto, ox, oy)], ms por quadro)} de um personagem, com `height` de altura (corpo e cabeça). Uma ação
        dada como (apelido, ação) fica guardada no apelido (o "hit": o ataque da classe)."""
        look2, body_h = self.scene_look(w, look)
        ref = w.render(look2, sprites.IDLE, direction, 0)
        if ref is None:
            return {}
        f = height / float(body_h or ref[1])
        out = {}
        for spec in acts:
            name, act = spec if isinstance(spec, tuple) else (spec, spec)
            r0 = w.render(look2, act, direction, 0)
            if r0 is None:
                continue
            count = r0[6]
            idx = range(count) if act != sprites.DEAD else [count - 1]
            frames = []
            for i in idx:
                r = r0 if i == 0 else w.render(look2, act, direction, i)
                if r is None:
                    continue
                wd, ht, px, ox, oy = r[:5]
                frames.append((self.cs_photo(wd, ht, px, f), ox * f, oy * f))
            if frames:
                out[name] = (frames, r0[5] or 100.0)
        return out

    def cs_photo(self, w, h, px, f):
        tw, th = max(1, int(round(w * f))), max(1, int(round(h * f)))
        raw = gdip.resize(w, h, b"".join(bytes(p) for p in px), tw, th) if gdip.ready() else None
        if raw is not None:
            data = base64.b64encode(sprites.png_rgba(tw, th, raw)).decode("ascii")
        else:
            data = sprites.png_b64(tw, th, sprites.resize(w, h, px, tw, th))
        return tk.PhotoImage(master=self.root, data=data, format="png")

    # ------------------------------------------------------------------ peças de desenho

    def cs_put(self, fr, x, y):
        if fr is not None:
            photo, ox, oy = fr
            self.canvas.create_image(x - ox, y - oy, anchor="nw", image=photo)

    @staticmethod
    def cs_frame(actor, act, t, ms=None, loop=True):
        got = actor.get(act) or actor.get(sprites.IDLE)
        if not got:
            return None
        frames, delay = got
        i = int(max(0.0, t) * 1000.0 / (ms or delay))
        return frames[i % len(frames) if loop else min(i, len(frames) - 1)]

    @staticmethod
    def cs_mob(mob, action, t, loop=True):
        got = mob.get(action) or mob.get(sprites.MOB_IDLE)
        if not got:
            return None
        photos, delay = got
        i = int(max(0.0, t) * 1000.0 / max(40.0, delay))
        return photos[i % len(photos) if loop else min(i, len(photos) - 1)]

    def cs_emote(self, a, emote, x, y, t):
        """Um emote do jogo em cima de (x, y), no instante `t` dele (s); nada antes de começar ou depois de acabar."""
        got = a.get("emotes", {}).get(emote)
        if not got or t < 0:
            return
        photos, delay = got
        i = int(t * 1000.0 / max(40.0, delay))
        if i < len(photos):
            self.canvas.create_image(x, y, anchor="s", image=photos[i])

    def cs_label(self, x, y, text, color, bg, size=9, anchor="center", bold=True):
        """Texto pequeno com contorno escuro (legível em cima dos desenhos)."""
        c, s = self.canvas, self.s
        font = ("Segoe UI", -max(7, int(size * s)), "bold" if bold else "normal")
        dark = mix(bg, "#000000", 0.7)
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            c.create_text(x + dx * max(1, s * 0.8), y + dy * max(1, s * 0.8), text=text, font=font, fill=dark,
                          anchor=anchor)
        return c.create_text(x, y, text=text, font=font, fill=color, anchor=anchor)

    def cs_pill(self, x1, y, text, color, bg, fade, side="right"):
        """O placar da cena: uma etiqueta arredondada encostada à direita em x1 (side="left": começando em x1;
        "center": centrada em x1)."""
        c, s = self.canvas, self.s
        font = ("Segoe UI", -max(8, int(10.5 * s)), "bold")
        tid = c.create_text(0, 0, text=text, font=font)
        b = c.bbox(tid)
        c.delete(tid)
        w = (b[2] - b[0]) + 12 * s
        h = 15 * s
        x1 = x1 + w if side == "left" else (x1 + w / 2 if side == "center" else x1)
        c.create_polygon(round_pts(x1 - w, y - h / 2, x1, y + h / 2, 7 * s), smooth=True,
                         fill=mix(bg, color, 0.22 * fade), outline=mix(bg, color, 0.85 * fade), width=max(1, int(s)))
        c.create_text(x1 - w / 2, y, text=text, font=font, fill=mix(bg, "#ffffff", fade))

    def cs_number(self, x, y, value, a, tint=None, zoom=1):
        """Um número de dano centrado em x (os dígitos do jogo); devolve a largura dele."""
        assets = dict(digits=a.get("digits"), photos=a["photos"])
        self.draw_number(x, y, value, assets, tint, zoom)
        text = "%d" % int(value)
        if assets.get("digits"):
            photos = self.digit_photos(assets, tint, zoom)
            return sum(photos[int(ch)].width() for ch in text) - (len(text) - 1) * zoom
        return len(text) * 7 * self.s * zoom

    def cs_fx(self, a, name, x, y, t, loop=False):
        """Um efeito de skill do jogo com a origem em (x, y), no instante `t` dele (s). False se acabou ou não há."""
        got = self.cs_fx_get(a, name) if t >= 0 else None
        if not got or t < 0:
            return False
        secs, frames = got
        u = t / secs
        if u >= 1 and not loop:
            return False
        fr = frames[int((u % 1.0) * len(frames)) % len(frames)]
        if fr is not None:
            photo, fx0, fy0 = fr
            self.canvas.create_image(x + fx0, y + fy0, anchor="nw", image=photo)
        return True

    def cs_fx_frame(self, a, name, i, x, y):
        """O quadro `i` (dos STR_FRAMES guardados) de um efeito do jogo com a origem em (x, y). False sem ele."""
        got = self.cs_fx_get(a, name)
        if not got:
            return False
        frames = got[1]
        fr = frames[max(0, min(len(frames) - 1, i))]
        if fr is None:
            return False
        photo, fx0, fy0 = fr
        self.canvas.create_image(x + fx0, y + fy0, anchor="nw", image=photo)
        return True

    def cs_icon(self, a, e, x, y, bg, fade=1.0, r=None):
        """O ícone do status `e` centrado em (x, y); sem ele, um círculo com uma cruz."""
        photo = a["icons"].get(e)
        if photo is not None:
            self.canvas.create_image(x, y, image=photo)
            return
        s = self.s
        r = r or 6 * s
        self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=mix(bg, "#fde68a", 0.85 * fade),
                                outline=mix(bg, "#b45309", fade))
        self.canvas.create_text(x, y, text="✚", fill=mix(bg, "#7c2d12", fade),
                                font=("Segoe UI Symbol", -max(6, int(r * 1.2))))

    def cs_seal(self, x, y, r, u, bg, fade, color="#f0abfc"):
        """O selo da Lex Aeterna (sem o efeito do jogo): dois anéis e a cruz, crescendo e sumindo com `u` (0 a 1)."""
        c, s = self.canvas, self.s
        a = fade * max(0.0, 1.0 - u)
        if a <= 0.05:
            return
        rr = r * (0.6 + 0.6 * u)
        c.create_oval(x - rr, y - rr * 0.8, x + rr, y + rr * 0.8, outline=mix(bg, color, a), width=max(1, int(2 * s)))
        c.create_oval(x - rr * 0.62, y - rr * 0.5, x + rr * 0.62, y + rr * 0.5, outline=mix(bg, "#fde68a", a),
                      width=max(1, int(s)))
        c.create_text(x, y, text="✠", fill=mix(bg, "#fff1f2", a), font=("Segoe UI Symbol", -max(7, int(rr * 0.9))))

    def cs_sparkles(self, x, y, k, n, rx, ry, bg, fade, color, seed=3):
        rnd = random.Random(seed)
        for i in range(n):
            ang = rnd.uniform(0, 2 * math.pi)
            tw = 0.5 + 0.5 * math.sin(k * rnd.uniform(5, 8) + i * 1.7)
            if tw < 0.3:
                continue
            px, py = x + math.cos(ang) * rx * rnd.uniform(0.4, 1.0), y + math.sin(ang) * ry * rnd.uniform(0.4, 1.0)
            self.canvas.create_text(px, py, text="✦", fill=mix(bg, color, tw * fade),
                                    font=("Segoe UI Symbol", -max(5, int((5 + 4 * tw) * self.s))))

    def cs_hp_bar(self, x, y, frac, bg, fade, w=30):
        """A barrinha de vida em cima de um personagem ou monstro (centrada em x, o topo em y)."""
        c, s = self.canvas, self.s
        frac = max(0.0, min(1.0, frac))
        hw, h = w * s / 2.0, 3.2 * s
        c.create_rectangle(x - hw - s, y - s, x + hw + s, y + h + s, fill=mix(bg, "#0b0f17", fade), outline="")
        tone = "#22c55e" if frac > 0.5 else ("#eab308" if frac > 0.25 else "#ef4444")
        if frac > 0:
            c.create_rectangle(x - hw, y, x - hw + 2 * hw * frac, y + h, fill=mix(bg, tone, fade), outline="")

    # ------------------------------------------------------------------ as cenas

    def draw_class_fx(self, kind, k, box, fade, scene, bg, col):
        """A cena de classe `kind` no instante k. False se os desenhos do jogo não estiverem prontos."""
        a = self.class_assets(scene or {}, kind)
        if a is None:
            return False
        getattr(self, "cs_" + kind)(k, box, fade, scene or {}, a, bg, col)
        return True

    def cs_hits(self, start, every, count, total, seed=11):
        """Os golpes de uma cena: [(quando, valor)], com os valores somando `total` (variando em volta da média)."""
        rnd = random.Random(seed)
        raw = [rnd.uniform(0.6, 1.4) for _ in range(count)]
        f = (total or 0) / float(sum(raw)) if total else 0
        return [(start + every * i, v * f) for i, v in enumerate(raw)]

    def cs_num(self, v):
        from fmt import num
        return num(v)

    @staticmethod
    def cs_dec(v):
        from fmt import dec
        return dec("%.1f" % v)

    @staticmethod
    def cs_t(text):
        from i18n import _
        return _(text)

    def cs_bulwark(self, k, box, fade, sc, a, bg, col):
        """Redentor: quem grava na frente do grupo levanta o Escudo do Guardião; o chefe atira, os ataques batem no
        escudo e o número sai em cima dele."""
        c, s = self.canvas, self.s
        x0, y0, x1, y1 = box
        W, base = x1 - x0, y1 - 9 * s
        ax = [x0 + W * f for f in (0.09, 0.21, 0.33)][:len(a["allies"])]
        hx = x0 + W * 0.52
        mx = x0 + W * 0.88
        wall = hx + 15 * s
        hits = self.cs_hits(1.0, 0.4, 9, sc.get("total"), seed=17)
        fly = 0.26
        for x, ally in zip(ax, a["allies"]):
            self.cs_put(self.cs_frame(ally, sprites.IDLE, k), x, base)
        # o escudo: cresce no começo e fica tremendo de leve a cada impacto
        grow = min(1.0, max(0.0, (k - 0.35) / 0.5))
        if grow > 0:
            shake = sum(math.exp(-(k - t - fly) * 9) for t, _v in hits if k >= t + fly) * 1.5 * s
            for j, (wd, tone, al) in enumerate(((3.2, "#b45309", 0.6), (1.6, "#fde68a", 0.95))):
                r = 26 * s * grow
                c.create_arc(wall - r * 0.55 + shake, base - 20 * s - r, wall + r * 0.55 + shake, base - 20 * s + r,
                             start=-75, extent=150, style="arc", outline=mix(bg, tone, al * fade),
                             width=max(1, int(wd * s)))
        self.cs_fx(a, "guardian", hx, base, k - 0.2)
        took = any(0 <= k - t - fly < 0.14 for t, _v in hits)
        self.cs_put(self.cs_frame(a["hero"], sprites.HURT if took else sprites.READY, k), hx, base)
        atk = next((k - t for t, _v in hits if 0 <= k - t + 0.22 < 0.4), None)
        photo = self.cs_mob(a["mob"], sprites.MOB_ATTACK if atk is not None else sprites.MOB_IDLE,
                            (atk + 0.22) if atk is not None else k, loop=atk is None)
        if photo is not None:
            c.create_image(mx, base, anchor="s", image=photo)
        absorbed = 0.0
        for j, (t, v) in enumerate(hits):
            dt = k - t
            if dt < 0:
                continue
            gy = base - (14 + (j % 3) * 7) * s
            if dt < fly:                                    # o ataque voando até o escudo
                u = dt / fly
                px = mx - 14 * s + (wall + 2 * s - (mx - 14 * s)) * u
                for tr in range(3):
                    q = px + tr * 6 * s
                    r = (3.4 - tr) * s
                    c.create_oval(q - r, gy - r, q + r, gy + r, fill=mix(bg, ("#fb7185", "#f97316", "#fde047")[tr],
                                                                         fade * (1 - tr * 0.25)), outline="")
                continue
            absorbed += v
            dd_ = dt - fly
            if dd_ < 0.25:                                  # bate no escudo e espalha faíscas
                self.draw_burst(wall + 2 * s, gy, (5 + 8 * dd_ / 0.25) * s, 10, mix(bg, "#fffbeb", fade * (1 - dd_)),
                                mix(bg, "#f59e0b", fade * (1 - dd_)))
            if dd_ < 0.8:
                self.cs_number(hx - 4 * s + ((j % 3) - 1) * 9 * s, base - HERO_H * s - 3 * s - 14 * s * dd_ / 0.8, v,
                               a, RED_TINT)
        if absorbed:
            self.cs_pill(x1 - 8 * s, y1 - STAGE_HS["bulwark"] * s + 10 * s,
                         "⛨ " + self.cs_num(absorbed if k < hits[-1][0] + fly + 0.05 else (sc.get("total") or 0)),
                         col, bg, fade)

    def cs_lex_cross(self, a, x, head, dt, bg, fade):
        """A cruz da Lex Aeterna caindo na cabeça do chefe (o efeito do jogo): cai em LEX_FALL s até `head`, bate com o
        pulso do efeito e some. `dt`: o tempo desde que ela bateu (negativo enquanto cai)."""
        s = self.s
        fall, stay = 0.22, 0.42
        if dt < -fall or dt > stay:
            return
        if self.cs_fx_get(a, "lex"):
            if dt < 0:                                      # caindo, acelerando
                u = (dt + fall) / fall
                self.cs_fx_frame(a, "lex", 0, x, head - 30 * s * (1 - u * u))
            else:                                           # o pulso do jogo (quadros 4 a 15) e some
                self.cs_fx_frame(a, "lex", 4 + int(dt / stay * 11.99), x, head)
            return
        if dt >= 0:                                         # sem o efeito: o selo desenhado
            self.cs_seal(x, head, 10 * s, dt / stay, bg, fade)

    def cs_lex_double(self, k, box, fade, sc, a, bg, col):
        """Chuva de Lex: o grupo bate no chefe; a cada Lex a cruz cai na cabeça dele e o golpe seguinte sai em dobro (o
        número cresce e ganha um ×2), e o placar soma o que as Lex renderam."""
        c, s = self.canvas, self.s
        x0, y0, x1, y1 = box
        W, base = x1 - x0, y1 - 9 * s
        hx = x0 + W * 0.09
        ax = [x0 + W * f for f in (0.27, 0.41)][:len(a["allies"])]
        mx = x0 + W * 0.8
        self.cs_put(self.cs_frame(a["hero"], sprites.CAST, k, ms=70), hx, base)
        for i, (x, ally) in enumerate(zip(ax, a["allies"])):
            self.cs_put(self.cs_frame(ally, "hit", k + i * 0.13, ms=75), x, base)
        rounds = [0.6 + 0.56 * i for i in range(8)]
        hurt = next((k - t - 0.2 for t in rounds if 0 <= k - t - 0.2 < 0.15), None)
        photo = self.cs_mob(a["mob"], sprites.MOB_HURT if hurt is not None else sprites.MOB_IDLE,
                            hurt if hurt is not None else k, loop=hurt is None)
        mob_h = photo.height() if photo is not None else 30 * s
        if photo is not None:
            c.create_image(mx, base, anchor="s", image=photo)
        cy = base - mob_h * 0.55
        head = max(y1 - STAGE_HS["lex_double"] * s + 14 * s, base - mob_h - 8 * s)   # o meio da cruz, na cabeça
        credit = float(sc.get("credit") or 0)
        per = credit / len(rounds) if credit else 0
        rnd = random.Random(5)
        gained = 0.0
        for i, t in enumerate(rounds):
            dt = k - t
            self.cs_lex_cross(a, mx, head, dt, bg, fade)
            if dt < 0:
                continue
            hit = dt - 0.2
            if hit < 0:
                continue
            base_v = (per or 800000.0) * rnd.uniform(0.7, 1.3)
            gained += base_v if credit else 0
            if hit < 0.9:
                u = hit / 0.9
                y = cy - 20 * s - 14 * s * u
                xx = mx + ((i % 3) - 1) * 10 * s
                if hit < 0.18:                              # primeiro o golpe comum...
                    self.cs_number(xx, y, base_v, a)
                else:                                       # ...que dobra, amarelo
                    self.cs_number(xx, y, base_v * 2, a, GOLD_TINT, 1)
                if 0.12 < hit < 0.6:                        # o ×2 pula da cruz
                    q = (hit - 0.12) / 0.48
                    self.cs_label(mx - 18 * s, cy - 4 * s - 8 * s * q, "×2", mix(bg, "#fde047", fade * (1 - q * 0.6)),
                                  bg, 11)
        if credit and k > 0.7:
            last = rounds[-1] + 0.25
            self.cs_pill(x0 + 8 * s, y1 - STAGE_HS["lex_double"] * s + 10 * s,
                         "✠ +" + self.cs_num(gained if k < last else credit), col, bg, fade, side="left")

    def cs_buff_wings(self, k, box, fade, sc, a, bg, col):
        """Podem ir: quem grava no meio, com as asas da Competentia do jogo; um raio de luz vai para cada aliado, que
        ganha o brilho do Benedictum; no fim, o placar: a parte da luta coberta, ou as rodadas de buff da caçada."""
        c, s = self.canvas, self.s
        x0, y0, x1, y1 = box
        W, base = x1 - x0, y1 - 9 * s
        hx = x0 + W * 0.5
        n = len(a["allies"])
        spots = (0.13, 0.29, 0.71, 0.87) if n >= 4 else (0.2, 0.8, 0.35)[:n]
        ax = [x0 + W * f for f in spots[:n]]
        if not self.cs_fx(a, "competentia", hx, base - 16 * s, k - 0.15, loop=k < 4.5):
            self.cs_sparkles(hx, base - 22 * s, k, 10, 26 * s, 18 * s, bg, fade, "#fde68a")
        self.cs_put(self.cs_frame(a["hero"], sprites.CAST if k < 3.6 else sprites.IDLE, k, ms=90), hx, base)
        order = sorted(range(n), key=lambda i: abs(ax[i] - hx))
        for rank, i in enumerate(order):
            x = ax[i]
            self.cs_put(self.cs_frame(a["allies"][i], sprites.IDLE, k + i * 0.2), x, base)
            t = k - 1.3 - 0.42 * rank
            if 0 <= t < 0.45:                               # o raio
                u = min(1.0, t / 0.2)
                sx, sy = hx, base - 30 * s
                ex, ey = sx + (x - sx) * u, sy + (base - 20 * s - sy) * u
                c.create_line(sx, sy, ex, ey, fill=mix(bg, "#fde68a", fade * (1 - t / 0.45)), width=max(2, int(3 * s)))
                c.create_line(sx, sy, ex, ey, fill=mix(bg, "#ffffff", fade * (1 - t / 0.45)), width=max(1, int(s)))
            if t >= 0.15:
                if not self.cs_fx(a, "benedictum", x, base, (t - 0.15) * 1.3):
                    if t < 1.2:
                        self.cs_sparkles(x, base - 18 * s, k, 6, 10 * s, 14 * s, bg, fade, "#fde68a", seed=i)
            if t > 0.4:
                icons = a.get("icon_order") or []
                e = icons[i % len(icons)] if icons else None
                self.cs_icon(a, e, x, base - ALLY_H * s - 8 * s, bg, fade, r=5 * s)
        if k > 3.4:
            u = min(1.0, (k - 3.4) / 0.8)
            if sc.get("rounds"):                            # na caçada: as rodadas de buff
                text = "✚ %d×" % max(1, round(sc["rounds"] * u))
            else:
                text = "✚ %d%%" % round(100 * (sc.get("cover") or 0) * u)
            self.cs_pill((x0 + x1) / 2, y1 - STAGE_HS["buff_wings"] * s + 9 * s, text, col, bg, fade, side="center")

    def cs_credit_boss(self, k, box, fade, sc, a, bg, col):
        """Sem mim era Wipe: o efeito de quem grava no chefe (as flores do Pólen, a explosão do Cometa, o tremor do
        Avanço Sísmico, a Garra, o selo da Lex, a Insígnia) e, em cada golpe do grupo, o dano a mais em destaque ao
        lado; o placar soma o que os efeitos renderam."""
        c, s = self.canvas, self.s
        x0, y0, x1, y1 = box
        W, base = x1 - x0, y1 - 9 * s
        hx = x0 + W * 0.08
        ax = [x0 + W * f for f in (0.26, 0.4)][:len(a["allies"])]
        mx = x0 + W * 0.79
        eff = sc.get("effect")
        self.cs_put(self.cs_frame(a["hero"], sprites.CAST if k < 1.2 else sprites.IDLE, k, ms=90), hx, base)
        # o efeito embaixo do chefe (antes dele)
        if eff in INSIGNIA and k > 0.4:
            u = min(1.0, (k - 0.4) / 0.4)
            tone = INSIGNIA[eff]
            for j, al in enumerate((0.9, 0.5)):
                rx, ry = (26 - 6 * j) * s * u, (7 - 2 * j) * s * u
                c.create_oval(mx - rx, base - ry, mx + rx, base + ry, outline=mix(bg, tone, al * fade),
                              width=max(1, int(2 * s)))
        if eff in (1183, 1182, 1184) and k > 0.4:
            self.cs_fx(a, "allbloom", mx, base, k - 0.4, loop=True)
        if eff == 1402:
            self.cs_fx(a, "quake", mx, base, (k - 0.4) % 1.2 if k > 0.4 else -1)
        for i, (x, ally) in enumerate(zip(ax, a["allies"])):
            self.cs_put(self.cs_frame(ally, "hit", k + i * 0.17, ms=80), x, base)
        rounds = [0.9 + 0.45 * i for i in range(9)]
        hurt = next((k - t for t in rounds if 0 <= k - t < 0.15), None)
        photo = self.cs_mob(a["mob"], sprites.MOB_HURT if hurt is not None else sprites.MOB_IDLE,
                            hurt if hurt is not None else k, loop=hurt is None)
        mob_h = photo.height() if photo is not None else 30 * s
        if photo is not None:
            c.create_image(mx, base, anchor="s", image=photo)
        cy = base - mob_h * 0.55
        if eff == 1142:
            self.cs_fx(a, "comet", mx, base - 6 * s, (k - 0.5) % 1.4 if k > 0.5 else -1)
        if eff == 730 and k > 0.5:                         # a Garra Sombria: três riscos roxos
            for j in range(3):
                u = ((k - 0.5) * 1.4 - j * 0.12) % 1.6
                if u < 0.35:
                    q = u / 0.35
                    sx = mx - 10 * s + j * 7 * s
                    c.create_line(sx, cy - 12 * s, sx + 8 * s * q, cy - 12 * s + 24 * s * q,
                                  fill=mix(bg, "#a855f7", fade), width=max(2, int(2.6 * s)), capstyle="round")
        if eff == 22:
            for t in rounds:
                if 0 <= k - t + 0.2 < 0.4:
                    self.cs_seal(mx, cy, 10 * s, (k - t + 0.2) / 0.4, bg, fade)
        if eff not in (1183, 1182, 1184, 1142, 1402, 730, 22) and eff not in INSIGNIA and k > 0.4:
            self.cs_icon(a, eff, mx + 16 * s, base - mob_h - 2 * s, bg, fade)   # efeito sem desenho: o ícone dele
        share = max(0.05, min(0.9, sc.get("share") or 0.3))
        via = float(sc.get("via") or 0)
        rnd = random.Random(9)
        gained = 0.0
        for i, t in enumerate(rounds):
            dt = k - t
            if dt < 0:
                continue
            whole = (via / len(rounds) / share if via else 900000.0) * rnd.uniform(0.75, 1.25)
            extra = whole * share
            gained += via / len(rounds) if via else 0
            if dt < 0.9:
                u = dt / 0.9
                y = cy - 18 * s - 14 * s * u
                xx = mx - 14 * s + ((i % 3) - 1) * 6 * s
                wd = self.cs_number(xx, y, whole - extra, a)
                if dt > 0.12:
                    self.cs_label(xx + wd / 2 + 3 * s, y - 6 * s, "+" + self.cs_num(extra), mix(bg, "#5eead4", fade),
                                  bg, 9, anchor="w")
        if via and k > 1.0:
            self.cs_pill(x0 + 8 * s, y1 - STAGE_HS["credit_boss"] * s + 10 * s,
                         "⇈ +" + self.cs_num(gained if k < rounds[-1] + 0.1 else via), col, bg, fade, side="left")

    def cs_crowd_spots(self, box, n):
        """Os lugares da multidão do "Oi, tchau" (até 14 monstros em duas fileiras): [(x, pés, fileira)]."""
        s = self.s
        x0, y0, x1, y1 = box
        W, base = x1 - x0, y1 - 9 * s
        show = min(n, 14)
        back = show // 2
        out = []
        for i in range(back):
            out.append((x0 + W * (0.36 + 0.58 * (i + 0.5) / max(1, back)), base - 9 * s, 0))
        front = show - back
        for i in range(front):
            out.append((x0 + W * (0.32 + 0.62 * (i + 0.5) / max(1, front)), base, 1))
        return out

    def cs_aoe_blast(self, k, box, fade, sc, a, bg, col):
        """Oi, tchau: quem grava conjura, um círculo mágico cresce embaixo da multidão e uma explosão (a do Cometa do
        jogo) derruba todos de uma vez; o contador salta com o número de abates."""
        c, s = self.canvas, self.s
        x0, y0, x1, y1 = box
        W, base = x1 - x0, y1 - 9 * s
        hx = x0 + W * 0.1
        n = sc.get("n") or 20
        spots = self.cs_crowd_spots(box, n)
        hit = 1.35
        self.cs_put(self.cs_frame(a["hero"], sprites.CAST if k < hit else "hit",
                                  k if k < hit else k - hit, ms=80, loop=k < hit), hx, base)
        cx = x0 + W * 0.64
        if 0.3 < k < hit + 0.3:                             # o círculo mágico
            u = min(1.0, (k - 0.3) / (hit - 0.3))
            for j in range(2):
                rx, ry = (W * 0.34 - j * 8 * s) * u, (8 - j * 2) * s * u
                c.create_oval(cx - rx, base - 4 * s - ry, cx + rx, base - 4 * s + ry,
                              outline=mix(bg, ("#f97316", "#fde68a")[j], fade * (0.9 - 0.3 * j)),
                              width=max(1, int(1.6 * s)))
        rnd = random.Random(4)
        for x, feet, row in spots:                         # fileira de trás primeiro
            d = rnd.uniform(0.0, 0.18)
            if k < hit + d:
                photo = self.cs_mob(a["crowd"], sprites.MOB_IDLE, k + x * 0.01)
            else:
                photo = self.cs_mob(a["crowd"], sprites.MOB_DIE, k - hit - d, loop=False)
                if k - hit - d > 0.55:
                    photo = None
            if photo is not None:
                c.create_image(x, feet, anchor="s", image=photo)
        if k >= hit:
            t = k - hit
            if not self.cs_fx(a, "comet", cx, base - 4 * s, t * 1.1):
                if t < 0.8:
                    self.draw_burst(cx, base - 16 * s, (14 + 30 * t) * s, 14, mix(bg, "#fde047", fade * (1 - t / 0.8)),
                                    mix(bg, "#f97316", fade * (1 - t / 0.8)))
            for j in range(3):
                u = t - j * 0.12
                if 0 <= u < 0.8:
                    r = (14 + 120 * u) * s
                    c.create_oval(cx - r, base - 8 * s - r * 0.3, cx + r, base - 8 * s + r * 0.3,
                                  outline=mix(bg, col, fade * (1 - u / 0.8)), width=max(1, int(2.5 * s * (1 - u))))
            if t > 0.25:                                    # o contador
                u = min(1.0, (t - 0.25) / 0.3)
                size = 15 + 8 * math.exp(-(t - 0.25) * 6)
                self.cs_label(cx, y1 - STAGE_HS["aoe_blast"] * s + 14 * s, "%d" % round(n * u),
                              mix(bg, "#fff7ed", fade), bg, size)
                self.cs_label(cx + 3 * s + size * s * 0.35 * len("%d" % n), y1 - STAGE_HS["aoe_blast"] * s + 16 * s,
                              self.cs_t("abates"), mix(bg, "#fdba74", fade), bg, 8, anchor="w", bold=False)

    def cs_revive(self, k, box, fade, sc, a, bg, col):
        """Quero um aumento: os aliados caídos; quem grava conjura e, um a um, cada um ganha um facho de luz com o anjo
        do jogo e se levanta; o placar conta os que voltaram."""
        c, s = self.canvas, self.s
        x0, y0, x1, y1 = box
        W, base = x1 - x0, y1 - 9 * s
        hx = x0 + W * 0.13
        ax = [x0 + W * f for f in (0.42, 0.6, 0.78)][:len(a["allies"])]
        self.cs_put(self.cs_frame(a["hero"], sprites.CAST if k < 4.2 else sprites.IDLE, k, ms=90), hx, base)
        back = 0
        for i, (x, ally) in enumerate(zip(ax, a["allies"])):
            t = k - 0.9 - 1.0 * i
            if 0 <= t < 1.2:                                # o facho de luz
                al = min(1.0, t / 0.2) * max(0.0, 1.0 - max(0.0, t - 0.7) / 0.5)
                for j, (wd, tone) in enumerate(((14, "#fef9c3"), (8, "#fde68a"), (3, "#ffffff"))):
                    c.create_rectangle(x - wd * s / 2, y1 - STAGE_HS["revive"] * s + 3 * s, x + wd * s / 2, base,
                                       fill=mix(bg, tone, al * fade * (0.25 + 0.25 * j)), outline="")
                if a.get("angel") is not None and t < 1.0:
                    c.create_image(x, base - 30 * s - 10 * s * t, image=a["angel"])
            if t < 0.45:
                fr = self.cs_frame(ally, sprites.DEAD, 0, loop=False)
            elif t < 0.75:
                fr = self.cs_frame(ally, sprites.SIT, 0, loop=False)
            else:
                fr = self.cs_frame(ally, sprites.IDLE, k)
                back += 1
                if t < 1.6:
                    self.cs_sparkles(x, base - 18 * s, k, 6, 11 * s, 15 * s, bg, fade, "#fde68a", seed=i + 5)
            self.cs_put(fr, x, base)
        if back:
            n = sc.get("n") or back
            shown = n if back >= len(ax) else max(1, int(round(n * back / float(len(ax) or 1))))
            self.cs_pill(x1 - 8 * s, y1 - STAGE_HS["revive"] * s + 10 * s, "☥ %d" % shown, col, bg, fade)

    def cs_served_ks(self, k, box, fade, sc, a, bg, col):
        """Bem servido (KS): outro jogador bate no monstro, a vida dele cai quase toda; quem grava dá um golpe só, o
        monstro cai, sai o "KS!", o outro faz o /omg do jogo e quem grava o joinha com piscadinha; o placar conta os
        KS da gravação."""
        c, s = self.canvas, self.s
        x0, y0, x1, y1 = box
        W, base = x1 - x0, y1 - 9 * s
        vx, mx, hx = x0 + W * 0.2, x0 + W * 0.56, x0 + W * 0.84
        steal = 2.6                                         # o golpe de quem grava
        hits = [0.35 + 0.36 * i for i in range(6)]          # os golpes do outro
        rnd = random.Random(21)
        # o outro jogador: bate até o roubo, depois fica parado
        victim = a["allies"][0] if a["allies"] else None
        if victim:
            self.cs_put(self.cs_frame(victim, "hit" if k < hits[-1] + 0.3 else sprites.IDLE, k, ms=75), vx, base)
        # o monstro: apanha, e cai no golpe de quem grava
        dead = k >= steal
        hurt = next((k - t for t in hits if 0 <= k - t < 0.15), None)
        if dead:
            photo = self.cs_mob(a["mob"], sprites.MOB_DIE, k - steal, loop=False)
            if k - steal > 1.1:
                photo = None
        else:
            photo = self.cs_mob(a["mob"], sprites.MOB_HURT if hurt is not None else sprites.MOB_IDLE,
                                hurt if hurt is not None else k, loop=hurt is None)
        mob_h = photo.height() if photo is not None else 26 * s
        if photo is not None:
            c.create_image(mx, base, anchor="s", image=photo)
        top = max(y1 - STAGE_HS["served_ks"] * s + 14 * s, base - mob_h - 7 * s)
        if not dead:                                        # a vida do monstro caindo a cada golpe do outro
            taken = sum(1 for t in hits if k >= t)
            self.cs_hp_bar(mx, top, 1.0 - 0.15 * taken, bg, fade, 26)
        for i, t in enumerate(hits):                        # os números do outro
            dt = k - t
            if 0 <= dt < 0.7:
                self.cs_number(mx + ((i % 3) - 1) * 9 * s, top - 2 * s - 12 * s * dt / 0.7,
                               rnd.uniform(9e5, 1.4e6), a)
        # quem grava: parado olhando, ataca uma vez e comemora
        if steal - 0.25 <= k < steal + 0.5:
            self.cs_put(self.cs_frame(a["hero"], "hit", k - steal + 0.25, ms=70, loop=False), hx, base)
        else:
            self.cs_put(self.cs_frame(a["hero"], sprites.IDLE, k), hx, base)
        if k >= steal:
            t = k - steal
            if t < 0.3:
                self.draw_burst(mx + 6 * s, base - mob_h * 0.5, (6 + 12 * t / 0.3) * s, 10,
                                mix(bg, "#fffbeb", fade), mix(bg, "#f472b6", fade))
            if t < 1.3:
                self.cs_number(mx + 4 * s, top - 4 * s - 16 * s * min(1.0, t / 1.0), 2.2e6, a, GOLD_TINT, 1)
            if 0.15 < t < 1.3:                              # o "KS!" (até o placar entrar no lugar dele)
                u = min(1.0, (t - 0.15) / 0.2)
                size = 11 + 6 * math.exp(-(t - 0.15) * 7)
                self.cs_label(mx, base - 30 * s - 6 * s * u, "KS!", mix(bg, "#f9a8d4", fade), bg, size)
            # os emotes: o /omg do outro, o joinha de quem grava
            self.cs_emote(a, EMOTE_OMG, vx, base - ALLY_H * s - 1 * s, t - 0.25)
            self.cs_emote(a, EMOTE_WINK, hx, base - HERO_H * s - 1 * s, t - 0.7)
            n = sc.get("n") or 1
            u = min(1.0, max(0.0, (t - 1.3) / 0.8))
            if t > 1.3:                                     # o placar no meio, depois que o número sumiu
                self.cs_pill(mx, y1 - STAGE_HS["served_ks"] * s + 10 * s, "♨ %d KS" % max(1, round(n * u)), col, bg,
                             fade, side="center")

    def cs_served_mvp(self, k, box, fade, sc, a, bg, col):
        """Bem servido (MVP): os outros batem no MVP e a vida dele cai; quem grava chega andando, emenda os golpes, o
        MVP cai e o "MVP!" dourado sobe em cima dele; os outros fazem o /omg."""
        c, s = self.canvas, self.s
        x0, y0, x1, y1 = box
        W, base = x1 - x0, y1 - 9 * s
        mx = x0 + W * 0.8
        ox = [x0 + W * f for f in (0.42, 0.57)][:len(a["allies"])]
        arrive, start, final = 1.1, 2.0, 3.5               # chega andando, começa a bater, o golpe final
        before = max(0.2, min(0.85, sc.get("before") or 0.45))
        rnd = random.Random(33)
        for i, (x, other) in enumerate(zip(ox, a["allies"])):
            self.cs_put(self.cs_frame(other, "hit" if k < final else sprites.IDLE, k + i * 0.17, ms=80), x, base)
        # quem grava: entra andando pela esquerda, para e bate
        hx_end = x0 + W * 0.24
        if k < arrive:
            hx = x0 - 20 * s
        elif k < start:
            u = (k - arrive) / (start - arrive)
            hx = x0 - 20 * s + (hx_end - x0 + 20 * s) * u
        else:
            hx = hx_end
        if arrive <= k < start:
            self.cs_put(self.cs_frame(a["hero"], sprites.WALK, k), hx, base)
        elif start <= k < final + 0.3:
            self.cs_put(self.cs_frame(a["hero"], "hit", k - start, ms=70), hx, base)
        elif k >= final + 0.3:
            self.cs_put(self.cs_frame(a["hero"], sprites.IDLE, k), hx, base)
        # o MVP: apanha e cai no golpe final
        dead = k >= final
        theirs = [0.3 + 0.3 * i for i in range(12)]
        mine = [start + 0.22 * i for i in range(7)]
        hurt = next((k - t for t in theirs + mine if 0 <= k - t < 0.12), None)
        if dead:
            photo = self.cs_mob(a["mob"], sprites.MOB_DIE, k - final, loop=False)
        else:
            photo = self.cs_mob(a["mob"], sprites.MOB_HURT if hurt is not None else sprites.MOB_IDLE,
                                hurt if hurt is not None else k, loop=hurt is None)
        mob_h = photo.height() if photo is not None else 30 * s
        if photo is not None:
            c.create_image(mx, base, anchor="s", image=photo)
        top = max(y1 - STAGE_HS["served_mvp"] * s + 14 * s, base - mob_h - 7 * s)
        if not dead:                                        # a vida: os outros tiram `before` até ele chegar
            if k < start:
                frac = 1.0 - before * min(1.0, k / start)
            else:
                frac = (1.0 - before) * max(0.0, 1.0 - (k - start) / (final - start))
            self.cs_hp_bar(mx, top, frac, bg, fade, 30)
        for i, t in enumerate(theirs):                      # os números dos outros (brancos, à esquerda)...
            dt = k - t
            if 0 <= dt < 0.6 and t < start:             # (depois que ele chega, só os dele: não embolam)
                self.cs_number(mx - 16 * s + ((i % 2) * 2 - 1) * 5 * s, top - 2 * s - 10 * s * dt / 0.6,
                               rnd.uniform(6e5, 9e5), a)
        for i, t in enumerate(mine):                        # ...e os dele (dourados, à direita)
            dt = k - t
            if 0 <= dt < 0.6:
                self.cs_number(mx + 4 * s + ((i % 3) - 1) * 14 * s, top - 2 * s - (i % 2) * 6 * s - 10 * s * dt / 0.6,
                               rnd.uniform(1.8e6, 2.6e6), a, GOLD_TINT, 1)
        if k >= final:
            t = k - final
            if t < 0.4:
                self.draw_burst(mx, base - mob_h * 0.5, (8 + 16 * t / 0.4) * s, 12, mix(bg, "#fef3c7", fade),
                                mix(bg, "#fbbf24", fade))
            if t > 0.3:                                     # o "MVP!" dourado em cima de quem grava
                u = min(1.0, (t - 0.3) / 0.25)
                size = 13 + 7 * math.exp(-(t - 0.3) * 6)
                yy = base - HERO_H * s - 10 * s - 4 * s * u
                self.cs_label(hx, yy, "MVP!", mix(bg, "#fde047", fade), bg, size)
                self.cs_sparkles(hx, yy, k, 8, 22 * s, 9 * s, bg, fade, "#fde68a", seed=8)
            for x in ox:
                self.cs_emote(a, EMOTE_OMG, x, base - ALLY_H * s - 1 * s, t - 0.35)
            self.cs_emote(a, EMOTE_WINK, hx + 14 * s, base - HERO_H * s - 1 * s, t - 1.1)

    def cs_no_elixir(self, k, box, fade, sc, a, bg, col):
        """Tá fácil pra ninguém: o chefe bate em quem grava, que bebe o elixir a cada golpe (o ícone do item do jogo e
        a cura verde) enquanto o estoque cai até zerar; aí o ícone fica riscado, vem o /swt do jogo, o golpe seguinte
        entra e ele termina de joelhos."""
        c, s = self.canvas, self.s
        x0, y0, x1, y1 = box
        W, base = x1 - x0, y1 - 9 * s
        hx, mx = x0 + W * 0.34, x0 + W * 0.74
        hits = [0.5, 1.25, 2.0, 2.75, 3.5, 4.2]            # os golpes do chefe
        drinks = [0.8, 1.55, 2.3]                           # os goles: 3 → 2 → 1 → 0
        empty = drinks[-1]
        took = next((k - t for t in hits if 0 <= k - t < 0.25), None)
        # a vida de quem grava: cai em cada golpe, sobe em cada gole; sem elixir, só cai
        hp = 0.9
        for t in sorted(hits + drinks):
            if k < t:
                break
            hp = hp - 0.3 if t in hits else min(1.0, hp + 0.28)
        hp = max(0.06, hp)
        kneel = k >= hits[-1] + 0.25
        if kneel:
            fr = self.cs_frame(a["hero"], sprites.SIT, 0, loop=False)
        elif took is not None and took < 0.18:
            fr = self.cs_frame(a["hero"], sprites.HURT, took, loop=False)
        else:
            fr = self.cs_frame(a["hero"], "hit", k, ms=85)
        self.cs_put(fr, hx, base)
        self.cs_hp_bar(hx, base - HERO_H * s - 6 * s, hp, bg, fade, 26)
        atk = next((k - t for t in hits if 0 <= k - t + 0.22 < 0.4), None)
        photo = self.cs_mob(a["mob"], sprites.MOB_ATTACK if atk is not None else sprites.MOB_IDLE,
                            (atk + 0.22) if atk is not None else k, loop=atk is None)
        if photo is not None:
            c.create_image(mx, base, anchor="s", image=photo)
        rnd = random.Random(12)
        for t in hits:                                      # o dano em quem grava (vermelho)
            dt = k - t
            if 0 <= dt < 0.7:
                self.cs_number(hx + 10 * s, base - HERO_H * s - 10 * s - 12 * s * dt / 0.7, rnd.uniform(5e4, 9e4), a,
                               RED_TINT)
        for t in drinks:                                    # cada gole: o ícone sobe e a cura verde
            dt = k - t
            if 0 <= dt < 0.6:
                yy = base - HERO_H * s * 0.55 - 10 * s * dt / 0.6
                if a.get("item") is not None:
                    c.create_image(hx - 12 * s, yy, image=a["item"])
                else:
                    self.cs_bottle(hx - 12 * s, yy, bg, fade)
                self.cs_number(hx - 4 * s, base - HERO_H * s - 12 * s - 10 * s * dt / 0.6, 2750, a, HEAL_TINT)
        # o estoque: o ícone e ×N; zerado, vermelho e riscado
        left = 3 - sum(1 for t in drinks if k >= t)
        px, py = x0 + 10 * s, y1 - STAGE_HS["no_elixir"] * s + 10 * s
        if a.get("item") is not None:
            c.create_image(px + 7 * s, py, image=a["item"])
        else:
            self.cs_bottle(px + 7 * s, py, bg, fade)
        if left == 0:
            u = min(1.0, (k - empty) / 0.15)
            c.create_line(px, py + 7 * s, px + 14 * s * u, py - 7 * s * u + 7 * s * (1 - u),
                          fill=mix(bg, "#ef4444", fade), width=max(2, int(2.4 * s)))
            pulse = 1.0 + 0.25 * math.exp(-(k - empty) * 5) * abs(math.sin((k - empty) * 18))
            self.cs_label(px + 18 * s, py, "×0", mix(bg, "#f87171", fade), bg, 11 * pulse, anchor="w")
        else:
            self.cs_label(px + 18 * s, py, "×%d" % left, mix(bg, "#e5e7eb", fade), bg, 11, anchor="w")
        self.cs_emote(a, EMOTE_SWEAT, hx - 24 * s, base - HERO_H * s + 8 * s, k - empty - 0.15)   # ao lado da cabeça

    def cs_bottle(self, x, y, bg, fade):
        """Um frasco desenhado (sem o ícone do item)."""
        c, s = self.canvas, self.s
        c.create_rectangle(x - 2 * s, y - 7 * s, x + 2 * s, y - 4 * s, fill=mix(bg, "#d6d3d1", fade), outline="")
        c.create_oval(x - 5 * s, y - 5 * s, x + 5 * s, y + 6 * s, fill=mix(bg, "#facc15", fade),
                      outline=mix(bg, "#a16207", fade))
