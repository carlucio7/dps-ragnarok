# -*- coding: utf-8 -*-
"""Os números de quem grava além do dano: atributos (ASPD, ATQ, precisão...), conjuração, recarga, pós-conjuração,
itens usados e skills que não saíram.

O que o replay traz (medido em gravações do ROLatam):
  * atributos: a sessão guarda os do começo da gravação e o jogo manda cada um quando muda (0x00b0, 0x00bd e
    0x0141). Só de quem grava.
  * conjuração: o tempo de cada conjuração já com todas as reduções (0x07fb), de todo mundo à vista. O replay não
    separa a parte fixa da variável: só o total que valeu naquele uso.
  * recarga: a de cada skill de quem grava, quando ela começa (0x043d).
  * pós-conjuração: o ícone dela em quem grava traz a duração de base e a que valeu depois das reduções.
  * itens usados: de todo mundo à vista (0x01c8).
  * skill que não saiu: o jogo responde a cada tentativa com a causa (0x0110); causa 4 = ainda em recarga.
"""

import collections

import meter
import rrf
from i18n import _

# atributos mostrados, na ordem: (chave, nome, melhor quando "high" / "low" / None)
SHOWN = [("aspd", "ASPD", "high"), ("atk", "ATQ", "high"), ("matk", "ATQM", "high"), ("patk", "P.ATQ", "high"),
         ("smatk", "S.ATQM", "high"), ("hit", "Precisão", "high"), ("crit", "Crítico", "high"),
         ("crate", "C.Rate", "high"), ("flee", "Esquiva", "high"), ("def", "DEF", "high"), ("mdef", "DEFM", "high"),
         ("res", "RES", "high"), ("mres", "RESM", "high"), ("hplus", "H.Plus", "high"),
         ("maxhp", "HP máx.", "high"), ("maxsp", "SP máx.", "high")]
BASE = [("str", "FOR"), ("agi", "AGI"), ("vit", "VIT"), ("int", "INT"), ("dex", "DES"), ("luk", "SOR"),
        ("pow", "POW"), ("sta", "STA"), ("wis", "WIS"), ("spl", "SPL"), ("con", "CON"), ("crt", "CRT")]
# atributos que a janela do jogo mostra somando duas partes (a que vem dos atributos + a do equipamento)
PAIRS = {"atk": "atk2", "matk": "matk2", "def": "def2", "mdef": "mdef2", "flee": "flee2"}


def aspd_shown(amotion):
    """O jogo manda o intervalo entre ataques; a janela de atributos mostra (2000 - intervalo) / 10."""
    return (2000.0 - amotion) / 10.0


def span(c, rng):
    return (0, c.now) if rng is None else (max(0, rng[0]), min(c.now, rng[1]))


def values(c, rng=None):
    """{atributo: (média no trecho, menor, maior)} de quem grava. A ASPD já vem como o jogo mostra; ATQ, ATQM,
    DEF, DEFM e esquiva vêm com as duas partes somadas. Só entra o que o replay disse."""
    t0, t1 = span(c, rng)
    if t1 <= t0:
        t1 = t0 + 1
    out = {}
    for key, _name, _better in SHOWN:
        got = c.stat_span(key, t0, t1)
        if got is None:
            continue
        avg, lo, hi = got
        other = c.stat_span(PAIRS[key], t0, t1) if key in PAIRS else None
        if other is not None:
            avg, lo, hi = avg + other[0], lo + other[1], hi + other[2]
        if key == "aspd":
            avg, lo, hi = aspd_shown(avg), aspd_shown(hi), aspd_shown(lo)
        out[key] = (avg, lo, hi)
    for key, _name in BASE:
        v = c.stat_at(key, t0)
        if v is None:
            continue
        plus = c.stat_at(key, t1, c.stat_bonus.get(key))
        out[key] = (v + (plus or 0), v, plus)          # (total, base, bônus ou None)
    return out


def casts(c, rng=None, aid=None):
    """Conjuração e recarga por skill de um jogador (quem grava, se aid for None):
    [dict(skill, name, n, cast (média ms), cast_min, cast_max, cooldown (ms) ou None, stopped)]."""
    aid = c.me if aid is None else aid
    t0, t1 = span(c, rng)
    acc = collections.OrderedDict()
    for t, src, _raw, _dst, skill, ms in c.casts:
        if src == aid and t0 <= t <= t1:
            a = acc.setdefault(skill, [0, 0, None, 0])
            a[0] += 1
            a[1] += ms
            a[2] = ms if a[2] is None else min(a[2], ms)
            a[3] = max(a[3], ms)
    cds = collections.defaultdict(collections.Counter)
    if aid == c.me:
        for t, skill, ms in c.cooldowns:
            if t0 <= t <= t1:
                cds[skill][ms] += 1
    rows = []
    for skill in list(acc) + [s for s in cds if s not in acc]:
        a = acc.get(skill) or [0, 0, None, 0]
        cd = cds[skill].most_common(1)[0][0] if cds.get(skill) else None
        rows.append(dict(skill=skill, name=meter.skill_name(skill, meter.pretty_aegis(c.skill_aegis.get(skill))),
                         n=a[0] or sum(cds[skill].values()), cast=(a[1] / a[0]) if a[0] else None,
                         cast_min=a[2], cast_max=a[3] if a[0] else None, cooldown=cd))
    rows.sort(key=lambda r: -r["n"])
    return rows


def post_delay(c, rng=None):
    """A pós-conjuração de quem grava no trecho: dict(base, real, cut (redução, 0-1), n) ou None."""
    t0, t1 = span(c, rng)
    seen = collections.Counter((base, real) for t, base, real in c.post_delays if t0 <= t <= t1 and base)
    if not seen:
        return None
    (base, real), _n = seen.most_common(1)[0]
    return dict(base=base, real=real, cut=max(0.0, 1.0 - real / float(base)), n=sum(seen.values()))


def items_used(c, rng=None, aid=None):
    """Itens que o jogador usou no trecho: [dict(item, name, n)], do mais usado para o menos."""
    aid = c.me if aid is None else aid
    t0, t1 = span(c, rng)
    seen = collections.Counter(item for t, who, item in c.item_uses if who == aid and t0 <= t <= t1)
    return [dict(item=i, name=meter.item_name(i), n=n) for i, n in seen.most_common()]


def blocked(c, rng=None):
    """Quantas vezes quem grava tentou usar uma skill que ainda estava em recarga ou pós-conjuração."""
    t0, t1 = span(c, rng)
    return sum(1 for t, _skill, cause in c.skill_fails if cause == rrf.FAIL_DELAY and t0 <= t <= t1)


def stopped(c, rng=None, aid=None):
    """Conjurações do jogador interrompidas no trecho."""
    aid = c.me if aid is None else aid
    t0, t1 = span(c, rng)
    return sum(1 for t, who in c.cast_stops if who == aid and t0 <= t <= t1)


def stat_text(key, v):
    """O valor de um atributo como a janela do jogo mostra."""
    if v is None:
        return "—"
    if key == "aspd":
        from fmt import dec
        return dec("%.1f" % v)
    return "%d" % round(v)


def name_of(key):
    return _(dict((k, n) for k, n, _b in SHOWN).get(key) or dict(BASE).get(key) or key)
