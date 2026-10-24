"""Agregacao de dano (encontros, ranking, skills) e leitura ao vivo da pasta Replay."""

import collections
import json
import os
import re
import struct
import sys

import clientdata
import i18n
import rrf
from i18n import _
from fmt import num as _num

RES_DIR = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))

SUMMON_KINDS = {"homun", "merc", "elem", "abr", "bionic", "mob", "unknown", "pet"}
# MVPs que lutam em fases, cada fase com um AID novo e o mesmo id de monstro.
# Lista fechada (como no ragreplaystats): ajudantes com flag de chefe que nascem
# um apos o outro (Alma Morta, Espinho...) nao podem virar uma luta so.
PHASED_BOSSES = {20994}       # Betelgeuse: 3 fases, ~11 s entre elas
MAX_PHASE_GAP_MS = 60000
DUMMY_MIN, DUMMY_MAX = 21060, 21099   # bonecos de treino
MVP_HP = 1000000
# (traduzidos na hora do aviso: os nomes do jogo só carregam depois do import)
FUSION_WARNINGS = [(0.28, "HP %d%% com a União: abaixo de 20%% o próximo ataque mata"),
                   (0.22, "HP %d%% com a União: o próximo ataque pode matar!")]
FUSION_REARM = 0.32
DEDUP_MS = 200
FRIENDLY_KINDS = {"pc", "homun", "merc", "elem", "abr", "bionic", "pet"}
NOW_WINDOW_MS = 5000          # janela do "DPS agora"


def _load(name):
    try:
        with open(os.path.join(RES_DIR, "data", name), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


SKILLS = _load("skill.json")
JOBS = _load("job.json")
MONSTERS = _load("monster.json")
# Nomes em inglês e espanhol tirados do cliente da LATAM (tools/build_names.py), para quando o jogo
# não está instalado no PC. Com o jogo instalado, valem os da instalação (clientdata), mais novos.
BUNDLED_NAMES = _load("names.json").get(i18n.LANG, {}) if i18n.LANG != "pt" else {}
clientdata.NAMES.pt_monsters = {int(k): v["name"] for k, v in MONSTERS.items() if v.get("name")}


def game_name(kind, ident, pt=None):
    """Nome do jogo no idioma escolhido: o português da base do medidor, ou o do cliente (instalação
    do jogador, depois a cópia do pacote) em inglês e espanhol. Em português, o cliente só completa
    o que a base não tem (conteúdo novo)."""
    if i18n.LANG == "pt" and pt:
        return pt
    return clientdata.NAMES.game_name(kind, ident) or BUNDLED_NAMES.get(kind, {}).get(str(ident)) or pt


# Nomes do jogo citados nos textos da tela (em português no catálogo do i18n): em inglês e espanhol
# viram o nome que o jogador vê no jogo dele. (texto em português, tipo, id)
TERMS = [("União Solar, Lunar e Estelar", "skill", 444), ("União Solar", "skill", 444), ("União", "skill", 444),
         ("Mestre Taekwon", "job", 4047), ("Executor", "job", 4254), ("Engenheiro", "job", 4253),
         ("Magus", "job", 4255), ("Cardeal", "job", 4256), ("Asceta", "job", 4303),
         ("Garra Sombria", "skill", 5001), ("Dor Máxima", "skill", 716), ("Florescer", "skill", 5222),
         ("Pólen", "status", 1183), ("Clímax", "skill", 5232), ("Potencializar Veneno", "skill", 2021),
         ("Manejo Perfeito", "skill", 112), ("Grito de Guerra", "skill", 155), ("Bênção", "skill", 34),
         ("Aumentar Agilidade", "skill", 29), ("Impositio Manus", "skill", 66), ("Avanço Sísmico", "skill", 5296),
         ("Talismã dos Elementos", "skill", 5423), ("Talismã do Guerreiro", "skill", 5419),
         ("Talismã do Mago", "skill", 5420), ("Reencarnação das Almas", "skill", 5432),
         ("Competentia", "skill", 5278), ("Benedictum", "skill", 5282), ("Religio", "skill", 5281),
         ("Presens Acies", "skill", 5275), ("Argutus Telum", "skill", 5272), ("Argutus Vita", "skill", 5271),
         ("Lauda Agnus", "skill", 2047), ("Lauda Ramus", "skill", 2048), ("Encanto de Órion", "skill", 2451),
         ("Clementia", "skill", 2041), ("Canto Candidus", "skill", 2042), ("Esfera Marinha", "monster", 1142)]
_terms = [None, None]


def localize_terms(text):
    """Troca os nomes do jogo em português que aparecem num texto pelos do idioma escolhido."""
    if clientdata.NAMES.version != _terms[0]:
        pairs = {}
        for pt, kind, ident in TERMS:
            if pt == "Clímax" and i18n.LANG != "en":
                continue            # em espanhol "Clímax" também é o momento da luta
            name = game_name(kind, ident)
            if name and name != pt:
                pairs[pt] = name
        order = sorted(pairs, key=len, reverse=True)
        pattern = re.compile("|".join(r"(?<!\w)%s(?!\w)" % re.escape(p) for p in order)) if order else None
        _terms[:] = [clientdata.NAMES.version, (pattern, pairs)]
    pattern, pairs = _terms[1]
    return pattern.sub(lambda m: pairs[m.group(0)], text) if pattern else text


if i18n.LANG != "pt":
    i18n.TERM_HOOK = localize_terms


_pt_index = {}


def translate_pt(name):
    """Nome em português que o cliente não tem pelo id (ex.: "Dor Máxima (ataque)", skill de item,
    comida): procura o mesmo nome entre skills, monstros e itens, ou traduz base + complemento."""
    if not name or i18n.LANG == "pt":
        return None
    if not _pt_index:
        for kind, table in (("skill", SKILLS), ("monster", MONSTERS), ("item", ITEMS)):
            idx = _pt_index[kind] = collections.defaultdict(list)
            for k, v in table.items():
                if isinstance(v, dict) and v.get("name"):
                    idx[v["name"].strip().lower()].append(k)
    key = name.strip().lower()
    for kind in ("skill", "monster", "item"):
        for ident in _pt_index[kind].get(key, ()):
            loc = clientdata.NAMES.game_name(kind, ident) or BUNDLED_NAMES.get(kind, {}).get(str(ident))
            if loc:
                return loc
    m = re.match(r"^(.*\S) \((.+)\)$", name)
    if m:
        base = translate_pt(m.group(1)) or (_(m.group(1)) if _(m.group(1)) != m.group(1) else None)
        if base:
            return "%s (%s)" % (base, translate_pt(m.group(2)) or _(m.group(2)))
    t = _(name)                                        # rótulos do próprio medidor
    return t if t != name else None


def skill_name(sid, fallback=None):
    if sid == 0:
        return _("Ataque básico")
    e = SKILLS.get(str(sid))
    pt = e.get("name") if e else None
    name = game_name("skill", sid, pt)
    if name == pt and pt:
        name = translate_pt(pt) or _aegis_name(sid) or pt
    return name or fallback or "Skill %d" % sid


_aegis = {}


def _aegis_name(sid):
    """Em inglês, para skill que o cliente não nomeia (skills de monstro, invocações): a descrição do
    rAthena ("Guided Attack") ou o nome interno legível."""
    if i18n.LANG != "en":
        return None
    if not _aegis:
        _aegis.update({k: (v.get("d") if v.get("d") and not v["d"].isupper() else None) or pretty_aegis(v.get("n"))
                       for k, v in (_load("rathena.json").get("skills") or {}).items()})
    return _aegis.get(str(sid))


def monster_name(mob_id):
    m = MONSTERS.get(str(mob_id))
    return game_name("monster", mob_id, m.get("name") if m else None)


STATUSES = _load("status.json")
EFST = _load("efst.json")             # id -> nome interno e skills que aplicam (gerado do rAthena)
ITEMS = _load("item.json")
RANDOM_OPTIONS = _load("randomopt.json")


def _norm(text):
    import unicodedata
    text = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return "".join(ch for ch in text if ch.isalnum() or ch == " ").strip()


def _ids_by_name(names):
    by = collections.defaultdict(list)
    for k, v in STATUSES.items():
        by[_norm(v.get("name", ""))].append(int(k))
    return {i for n in names for i in by.get(_norm(n), [])}


# Buffs de grupo/suporte que contam para DPS (lista do simulador da LATAM Tools)
PARTY_BUFFS = _ids_by_name([
    "Aumentar Agilidade", "Bênção", "Impositio Manus", "Expiatio", "Competentia", "Religio", "Benedictum",
    "Reencarnação das Almas", "Talismã do Protetor", "Talismã do Guerreiro", "Talismã do Mágico",
    "Talismã dos Elementos", "Argutus Vita", "Argutus Telum", "Presens Acies", "Grito de Guerra", "Lauda Agnus",
    "Lauda Ramus", "Adrenalina Pura", "Força Violenta", "Manejo Perfeito", "Espírito da Fada",
    "Espírito das Sombras", "Espírito do Falcão", "Espírito do Golem", "Poder de Odin", "Chuva de Mariscos",
    "Serenata ao Luar", "Encanto de Órion", "Aegis Domini", "Poema de Bragi", "Ritmo Contagiante", "Enfeitiçar",
    "Marcha de Prontera", "Serenata de Jawaii", "Assovio", "Crepúsculo Sangrento", "Maçãs de Idun", "Sibilo",
    "Beijo da Sorte", "Dança Cigana", "Rufar dos Tambores", "Anel dos Nibelungos", "Ode a Siegfried",
    "Sinfonia dos Ventos", "Canção de Balder", "Balada Sinfônica", "Canção de Frigga", "Orvalho de Idun",
    "Dança com Lobos", "Murmúrio Perene", "Interlúdio", "Angelus", "Magnificat", "Kyrie Eleison", "Assumptio"])
# Debuffs que importam no monstro (mesma lista, mais os que aparecem nos replays)
MOB_DEBUFFS = _ids_by_name([
    "Garra Sombria", "Esporo Explosivo", "Rapsódia do Minerador", "Recital de Geffenia", "Assombração",
    "Oleum Sanctum", "Lex Aeterna", "Vício Mágico", "Estigma", "Estigma do Julgamento", "Quake", "Florescer",
    "Vazio das Sombras"])
# Os que o simulador chama por outro nome (ou que o cliente não nomeia), ligados pela skill que
# aplica o status (simulador -> skill -> status do rAthena -> id do ícone). O nome mostrado é o do
# simulador, com o nome do cliente entre parênteses quando é diferente.
SIM_BUFFS = {112: "Terreno Mágico", 113: "Amplificação Mística", 567: "Insígnia do Fogo", 568: "Insígnia da Água",
             569: "Insígnia do Vento", 570: "Insígnia da Terra", 1358: "Talismã do Mago"}
SIM_DEBUFFS = {1142: "Cometa", 395: "Ataque Surpresa", 330: "Oratio", 1318: "Infecção", 328: "Potencializar Veneno",
               1214: "Intoxicação", 1381: "Geladinho", 1183: "Pólen", 1182: "Empalamento", 1382: "Gravitação",
               1402: "Avanço Sísmico", 1403: "Avanço Sísmico", 1166: "Redução de dano do chefe"}
SIM_ONLY = {1214}                     # o cliente chama a Intoxicação de "Leitura Intensiva"
PARTY_BUFFS |= set(SIM_BUFFS)
MOB_DEBUFFS |= set(SIM_DEBUFFS) - {1166}
# Status de sistema que não são buff de verdade (tempo de pós-conjuração, recarga de item...)
SYSTEM_EFST = ("POSTDELAY", "REUSE_", "PLAYTIME", "HEAD_EQUIPMENT", "SPECIALZONE", "WEIGHTOVER", "_PLACE",
               "ACTIONDELAY", "ENSEMBLEFATIGUE")
CONSUMABLE_WORDS = ("pocao", "elixir", "comida", "bolinho", "pilula", "suco", "churrasco", "estimulante",
                    "abrasivo", "manual de mascar", "salada", "sopa", "torta", "bolo", "biscoito", "cha ",
                    "cerveja", "vinho", "drink", "pao", "racao", "doce")
SERVICE_WORDS = ("bonus de exp", "bonus de drop", "armazem", "premium", "vip")


def status_name(efst):
    """Nome do buff/debuff na tela (no idioma escolhido)."""
    if i18n.LANG != "pt":
        name = clientdata.NAMES.game_name("status", efst) or BUNDLED_NAMES.get("status", {}).get(str(efst))
        if name and name.isupper():
            # alguns ícones têm nome interno em maiúsculas ("DARK CROW"): o da skill é o que o jogador conhece
            skill = next((game_name("skill", sid) for sid in (EFST.get(str(efst)) or {}).get("s", [])
                          if game_name("skill", sid)), None)
            name = skill or name.title()
        if name and "%" not in name:
            return name
        pt = status_name_pt(efst)
        name = translate_pt(pt) or (translate_pt(re.sub(r" \(.*\)$", "", pt)) if "(" in pt else None)
        if name:
            return name
        for sid in (EFST.get(str(efst)) or {}).get("s", []):     # nome da skill que aplica o status
            name = game_name("skill", sid) or _aegis_name(sid)
            if name:
                return name
    return status_name_pt(efst)


def status_name_pt(efst):
    """Nome em português (com os nomes do simulador): é o que a lógica usa para classificar."""
    name = (STATUSES.get(str(efst)) or {}).get("name") or ""
    if not name or name == "?" or "%" in name:
        name = ""
    sim = SIM_BUFFS.get(efst) or SIM_DEBUFFS.get(efst)
    if sim:
        if not name or _norm(name) == _norm(sim) or efst in SIM_ONLY:
            return sim
        return "%s (%s)" % (sim, name)
    if name:
        return name
    info = EFST.get(str(efst)) or {}
    for sid in info.get("s", []):                    # nome da skill que aplica o status
        sk = SKILLS.get(str(sid))
        if sk and sk.get("name"):
            return sk["name"]
    if info.get("c"):
        return info["c"].replace("_", " ").title()
    return "Status %d" % efst


def status_kind(efst):
    const = (EFST.get(str(efst)) or {}).get("c", "")
    if any(p in const for p in SYSTEM_EFST):
        return "Sistema"
    if efst in PARTY_BUFFS:
        return "Grupo/suporte"
    n = _norm(status_name_pt(efst))
    if any(w in n for w in CONSUMABLE_WORDS):
        return "Consumível"
    if any(w in n for w in SERVICE_WORDS):
        return "Serviço"
    if n.startswith("status "):
        return "Outro"
    return "Classe/outros"


def status_alert(efst, total_ms):
    """Avisar quando este buff acabar no meio da luta?"""
    kind = status_kind(efst)
    return kind in ("Grupo/suporte", "Consumível") or (kind == "Classe/outros" and total_ms >= 60000)


# Slots de equipamento (máscara de posição do rAthena), na ordem de exibição
EQUIP_SLOTS = [(256, "Topo"), (512, "Meio"), (1, "Baixo"), (16, "Armadura"), (2, "Arma"), (32, "Escudo"),
               (4, "Capa"), (64, "Sapato"), (8, "Acessório esq."), (128, "Acessório dir."), (32768, "Munição"),
               (1024, "Visual topo"), (2048, "Visual meio"), (4096, "Visual baixo"), (8192, "Visual capa"),
               (65536, "Sombrio armadura"), (131072, "Sombrio arma"), (262144, "Sombrio escudo"),
               (524288, "Sombrio sapato"), (1048576, "Sombrio acess. dir."), (2097152, "Sombrio acess. esq.")]
GRADES = {1: "D", 2: "C", 3: "B", 4: "A"}


def item_name(item_id):
    e = ITEMS.get(str(item_id))
    return game_name("item", item_id, e.get("name") if e else None) or "Item %d" % item_id


def item_text(it):
    """"+12 Coroa de Belzebu [1] (Carta X) · grau A · ATQ +5%"""
    name = item_name(it.item_id)
    text = ("+%d " % it.refine if it.refine else "") + name
    cards = [item_name(c) for c in it.cards if c > 0 and str(c) in ITEMS]
    if cards:
        text += " (%s)" % ", ".join(cards)
    if it.grade in GRADES:
        text += _(" · grau %s") % GRADES[it.grade]
    opts = []
    for oid, val, _param in it.options:
        fmt_ = game_name("option", oid, RANDOM_OPTIONS.get(str(oid)))
        if fmt_:
            try:
                opts.append(fmt_ % val if "%d" in fmt_ else fmt_.replace("%%", "%"))
            except (TypeError, ValueError):
                opts.append(fmt_.replace("%%", "%"))
    if opts:
        text += " · " + ", ".join(opts)
    return text


def job_name(jid):
    return game_name("job", jid, JOBS.get(str(jid))) or ""


class Stat:
    __slots__ = ("total", "hits", "max_hit", "crits", "first", "last")

    def __init__(self):
        self.total = self.hits = self.max_hit = self.crits = 0
        self.first = self.last = None

    def add(self, dmg, t, crit=False):
        self.total += dmg
        self.hits += 1
        if dmg > self.max_hit:
            self.max_hit = dmg
        if crit:
            self.crits += 1
        if self.first is None:
            self.first = t
        self.last = t


class Hit:
    """Um evento de dano guardado para a analise."""
    __slots__ = ("t", "src", "raw", "dst", "dst_raw", "skill", "dmg", "hits", "crit", "miss", "out")

    def __init__(self, x, src, dst, dst_raw, out):
        self.t = x.time
        self.src = src            # aliado: dono (invocacao/unidade resolvida); monstro: 1a fase
        self.raw = x.src          # quem bateu de fato
        self.dst = dst            # monstro: 1a fase; aliado: dono
        self.dst_raw = dst_raw
        self.skill = x.skill
        self.dmg = x.damage
        self.hits = x.hits
        self.crit = x.crit
        self.miss = x.miss
        self.out = out            # True = aliado batendo; False = monstro batendo


class Encounter:
    def __init__(self, t):
        self.start = t
        self.last = t
        self.paused = 0                                    # trocas de fase (fora do tempo de DPS)
        self.pauses = []                                   # (de, até) de cada troca de fase
        self.by_source = collections.defaultdict(Stat)     # dono (AID) -> Stat
        self.by_skill = collections.defaultdict(Stat)      # (fonte, skill) do jogador -> Stat
        self.by_target = collections.defaultdict(int)      # alvo -> dano (todos os jogadores)
        self.my_targets = collections.defaultdict(int)     # alvo -> dano (so o jogador)

    def duration_ms(self, now=None):
        end = self.last if now is None else max(self.last, now)
        return max(1000, end - self.start - self.paused)


class Combat:
    """Recebe os pacotes do replay e mantem o encontro atual + historico."""

    def __init__(self, session, gap_ms=10000, targets="all"):
        self.session = session
        self.targets = targets        # "all" = todos os monstros; "mvp" = só MVPs e bonecos de treino
        self.trap_log = []            # (t, aid) de cada armadilha do mapa que atingiu um aliado
        self.effect_log = collections.defaultdict(list)   # aid aliado -> [(t, id do efeito)]
        self.party = set()            # membros do grupo (quem recebe 0x080e) — você entra à parte
        self.res_log = []             # (t, aid) de cada ressurreição
        self.status_val = {}          # (aid, efst, início) -> val1 (nível/força do efeito)
        self.status_first = {}        # (aid, efst) -> (t, ligou) do primeiro aviso visto na gravação
        self.status_total = {}        # efst -> maior duração (ms) que o servidor mandou
        self.me = session.aid
        self.gap_ms = gap_ms
        self.entities = {}
        self.owner = {}               # unidade/invocacao -> dono
        self.skill_aegis = {}         # nomes da lista de skills do proprio jogador
        self.current = None
        self.history = []             # encontros encerrados (mais recente no fim)
        self.total = None             # tudo desde o inicio (ou desde o ultimo "zerar")
        self.closed_ms = 0            # tempo em combate dos encontros ja encerrados
        self.recent = collections.deque()   # (t, dano) do jogador, para o "DPS agora"
        self.now = 0
        self.map = session.map
        self.finished = False         # a gravacao parou (nada mais esta "ao vivo")
        self.dead = set()             # AIDs que morreram (ZC_NOTIFY_VANISH tipo 1)
        self.alias = {}               # fase seguinte de um MVP -> AID da primeira fase
        self.chains = {}              # id do monstro -> [AID da 1a fase, AID da fase atual, ultimo evento]
        self.phases = collections.Counter()   # AID da 1a fase -> numero de fases
        self.phase_starts = collections.defaultdict(list)   # AID da 1a fase -> inicio de cada fase seguinte
        self.phase_hit = {}           # AID da 1a fase -> AID (fase) do ultimo golpe aliado
        # registro completo, para a janela de analise
        self.hits = []                # Hit: aliados -> inimigos e inimigos -> aliados
        self.uses = []                # (t, fonte, fonte_original, alvo, skill) de skills sem dano
        self.casts = []               # (t, fonte, fonte_original, alvo, skill, ms de conjuracao)
        self.deaths = {}              # AID -> quando morreu (a ultima vez)
        self.death_log = []           # (t, AID) de todas as mortes
        self.version = 0             # muda a cada evento novo (para a interface saber se redesenha)
        self._last_seen = {}
        self.status_on = {}           # (aid, efst) -> [início, duração total, restante] dos ativos
        self.status_log = []          # (aid, efst, início, fim) dos que já acabaram
        self.hp_log = collections.defaultdict(list)   # aid -> [(t, hp, hp máx.)]
        self.alerts = collections.deque(maxlen=50)    # (nº, t, tipo, texto) para o widget mostrar
        self.alert_seq = 0
        self._alerted = {}
        self.bag = {}                 # slot da bolsa -> Item
        self.worn = {}                # bit do slot -> Item
        self.equip_log = [(0, {})]    # (t, {bit: Item}) a cada troca
        self.options = collections.defaultdict(list)   # aid -> [(t, opções)] (União = OPTION_FLYING)
        self.max_hp_seen = {}
        self._fusion_armed = [True, True]
        if session.option:
            self.options[self.me].append((0, session.option))

    # --- nomes ---------------------------------------------------------

    def add_entity(self, e):
        old = self.entities.get(e.aid)
        if old and not e.name and old.name:
            e.name = old.name
        self.entities[e.aid] = e

    def owner_of(self, aid):
        o = self.owner.get(aid)
        if o is not None:
            return o
        # invocacoes trazem o AID do dono no campo GID do spawn; o dono pode
        # aparecer depois da invocacao, entao isso e conferido na hora do dano
        e = self.entities.get(aid)
        if e is not None and e.kind in SUMMON_KINDS and e.gid and e.gid != aid:
            g = self.entities.get(e.gid)
            if e.gid == self.me or (g is not None and g.kind == "pc"):
                self.owner[aid] = e.gid
                return e.gid
        return None

    def resolve(self, aid):
        for _ in range(4):
            o = self.owner_of(aid)
            if o is None or o == aid:
                break
            aid = o
        return aid

    def name_of(self, aid):
        if aid == self.me:
            return self.session.player or _("Você")
        e = self.entities.get(aid)
        if e:
            name = clientdata.NAMES.resolve(e.name) if e.name else None
            if name:
                return name
            if e.kind == "mob":
                return monster_name(e.job) or _("Monstro %d") % e.job   # nem o jogo nem a base conhecem
        return "#%d" % aid

    def is_mvp(self, aid):
        """MVP (marca 2 no spawn), boneco de treino, ou chefe em fases/HP de MVP na tabela."""
        aid = self.alias.get(aid, aid)
        e = self.entities.get(aid)
        if e is None:
            return False
        if e.boss == 2 or e.job in PHASED_BOSSES or DUMMY_MIN <= e.job <= DUMMY_MAX:
            return True
        m = MONSTERS.get(str(e.job))
        return e.boss != 1 and bool(m) and (m.get("hp") or 0) >= MVP_HP   # visível desde o início (sem marca)

    def counts_target(self, aid):
        return self.targets != "mvp" or self.is_mvp(aid)

    def target_name(self, aid):
        n = self.phases.get(aid, 0)
        return self.name_of(aid) + (_(" ★ (%d fases)") % n if n > 1 else "")

    def is_friendly(self, aid):
        # invocações de jogadores (ex.: Esfera Marinha) são aliadas, mesmo sendo "monstros"
        if aid == self.me or aid in self.owner or self.owner_of(aid) is not None:
            return True
        e = self.entities.get(aid)
        return e is not None and e.kind in FRIENDLY_KINDS

    # --- pacotes -------------------------------------------------------

    def feed(self, records, last_time=None):
        for t, pid, d in records:
            self.handle(t, pid, d)
        if last_time is not None and last_time > self.now:
            self.now = last_time

    def handle(self, t, pid, d):
        if t > self.now:
            self.now = t
        if pid in rrf.DAMAGE_PACKETS:
            x = rrf.parse_damage(t, pid, d)
            if x is not None:
                self.on_damage(x)
        elif pid in rrf.SPAWN_PACKETS:
            e = rrf.parse_spawn(pid, d)
            if e is not None:
                self.add_entity(e)
                if e.kind == "pc":
                    self.set_option(e.aid, t, e.option)
        elif pid == rrf.P_EFFECT:
            r = rrf.parse_effect(d)
            if r is not None and self.is_friendly(r[0]):
                log = self.effect_log[r[0]]
                log.append((t, r[1]))
                if len(log) > 3000:
                    del log[:1000]
                if r[1] in rrf.MAP_DAMAGE_EFFECTS:
                    self.trap_log.append((t, r[0]))
                    self.version += 1
        elif pid == rrf.P_OPTION:
            r = rrf.parse_option(d)
            if r is not None:
                self.set_option(r[0], t, r[1])
        elif pid == rrf.P_GROUND_UNIT:
            r = rrf.parse_ground_unit(d)
            if r and r[0] != r[1]:
                self.owner[r[0]] = r[1]
        elif pid == rrf.P_MAPMOVE:
            self.map = rrf.decode_name(d[2:18])
        elif pid == rrf.P_VANISH:
            if len(d) >= 7:
                aid = struct.unpack_from("<I", d, 2)[0]
                e = self.entities.get(aid)
                if d[6] == 1 or (e is not None and e.kind == "mob"):
                    self.end_statuses(aid, t)          # monstro morto/sumido perde os debuffs
                if d[6] == 1:
                    self.dead.add(aid)
                    self.deaths[aid] = t
                    self.death_log.append((t, aid))
                    self.version += 1
                    if aid == self.me:
                        self.on_my_death(t)
        elif pid in rrf.STATUS_PACKETS:
            r = rrf.parse_status(pid, d)
            if r is not None:
                self.on_status(t, *r)
        elif pid == rrf.P_PARAM:
            r = rrf.parse_param(d)
            if r is not None and r[0] in (rrf.SP_HP, rrf.SP_MAXHP):
                self.on_hp(t, self.me, r[1] if r[0] == rrf.SP_HP else None, r[1] if r[0] == rrf.SP_MAXHP else None)
        elif pid == rrf.P_PARTY_HP:
            r = rrf.parse_party_hp(d)
            if r is not None:
                self.party.add(r[0])
                self.on_hp(t, r[0], r[1], r[2])
        elif pid == rrf.P_RESURRECT:
            aid = rrf.parse_resurrect(d)
            if aid is not None:
                self.res_log.append((t, aid))
                self.version += 1
        elif pid in (rrf.P_WEAR, rrf.P_TAKEOFF):
            r = rrf.parse_wear(pid, d)
            if r is not None and r[3]:
                self.on_wear(t, *r[:3])
        elif pid == rrf.P_ITEM_ADD:
            it = rrf.parse_item_add(d)
            if it is not None:
                self.bag[it.slot] = it
        elif pid in rrf.SKILL_USE_PACKETS:
            r = rrf.parse_skill_use(pid, d)
            if r is not None and self.fresh(("u",) + r, t):
                src = self.actor(r[0], t)
                self.uses.append((t, src, r[0], self.alias.get(r[1], r[1]), r[2]))
                self.version += 1
        elif pid in rrf.CAST_PACKETS:
            r = rrf.parse_cast(d)
            if r is not None and self.fresh(("c",) + r[:3], t):
                src = self.actor(r[0], t)
                self.casts.append((t, src, r[0], self.alias.get(r[1], r[1]), r[2], r[3]))
                self.version += 1
        elif pid == 0x010F:
            self.skill_aegis.update(skill_list_names(d))

    # --- buffs, HP, equipamento -----------------------------------------

    def start_statuses(self, items):
        """Buffs que já estavam no personagem no início da gravação."""
        for efst, total, left in items:
            self.on_status(0, self.me, efst, True, total, left)

    def on_status(self, t, aid, efst, on, total=0, left=0, val1=0):
        key = (aid, efst)
        first = key not in self.status_first
        if first:
            self.status_first[key] = (t, bool(on))
        cur = self.status_on.get(key)
        if on:
            if total and total > self.status_total.get(efst, 0):
                self.status_total[efst] = total
            if cur is None:
                self.status_on[key] = [t, total, left]
                self.status_val[(aid, efst, t)] = val1
            else:
                cur[1], cur[2] = total or cur[1], left or cur[2]     # renovou
                if val1:
                    self.status_val[(aid, efst, cur[0])] = val1
            return
        if cur is None:
            # acabou sem o início ter aparecido: o jogador já estava com ele quando a gravação começou
            # (só os seus buffs vêm prontos no início; os dos outros só aparecem quando acabam)
            e = self.entities.get(aid)
            if first and t > 0 and (aid == self.me or (e is not None and e.kind == "pc")):
                self.status_log.append((aid, efst, 0, t))
            return
        del self.status_on[key]
        self.status_log.append((aid, efst, cur[0], t))
        if aid == self.me and self.active() and status_alert(efst, cur[1]) and t - cur[0] >= 2000:
            # um buff importante acabou no meio da luta
            if t - self._alerted.get(efst, -10 ** 9) > 10000:
                self._alerted[efst] = t
                self.alert(t, "buff", _("%s acabou") % status_name(efst))

    def end_statuses(self, aid, t):
        for key in [k for k in self.status_on if k[0] == aid]:
            start = self.status_on.pop(key)[0]
            self.status_log.append((aid, key[1], start, max(start, t)))

    def in_party(self, aid):
        return aid == self.me or aid in self.party

    def statuses(self, aid=None):
        """Intervalos (aid, efst, início, fim); os ainda ativos terminam em `now`."""
        out = [s for s in self.status_log if aid is None or s[0] == aid]
        out += [(a, e, v[0], self.now) for (a, e), v in self.status_on.items() if aid is None or a == aid]
        return out

    def on_hp(self, t, aid, hp, max_hp):
        log = self.hp_log[aid]
        last = log[-1] if log else (0, None, None)
        log.append((t, hp if hp is not None else last[1], max_hp if max_hp is not None else last[2]))
        if len(log) > 4000:
            del log[:1000]
        self.max_hp_seen[aid] = max(self.max_hp_seen.get(aid, 0), hp or 0, max_hp or 0)
        if aid == self.me and hp is not None:
            self.check_fusion_hp(t, hp)

    # --- União Solar, Lunar e Estelar (Mestre Taekwon) ---------------------
    # Cada ataque físico contra monstro custa 2% do HP máximo, e atacar com 20% de HP
    # ou menos mata na hora. O servidor marca a União com a opção "voando".

    def set_option(self, aid, t, option):
        log = self.options[aid]
        if not log or log[-1][1] != option:
            log.append((t, option))

    def fused_at(self, aid, t):
        opt = 0
        for when, o in self.options.get(aid, ()):
            if when > t:
                break
            opt = o
        return bool(opt & rrf.OPTION_FLYING)

    def check_fusion_hp(self, t, hp):
        mx = self.max_hp_seen.get(self.me)
        if not mx or not self.fused_at(self.me, t):
            return
        pct = hp / mx
        if pct >= FUSION_REARM:
            self._fusion_armed = [True, True]
            return
        for level, (limit, text) in enumerate(FUSION_WARNINGS):
            if pct <= limit and self._fusion_armed[level]:
                self._fusion_armed[level] = False
                if level == 0:
                    self._fusion_armed[1] = pct > FUSION_WARNINGS[1][0]
                self.alert(t, "fusion", _(text) % round(pct * 100))
                break

    def on_my_death(self, t):
        import analysis   # evita import circular
        rec = analysis.death_recap(self, self.me, t)
        text = _("Você morreu")
        if rec["trap"]:
            text += _(": armadilha do mapa")
            if rec["trap_pct"]:
                text += _(" (~%d%% do HP máx.)") % round(rec["trap_pct"] * 100)
            if rec["overkill"]:
                text += _(" · overkill %s") % _num(rec["overkill"])
        elif rec["fusion"]:
            text += _(": União Solar (atacou com %s de HP)") % (
                "%d%%" % round(rec["hp_pct"] * 100) if rec["hp_pct"] is not None else _("pouco"))
        elif rec["killer"] and not rec["unclear"]:
            text += ": %s (%s)" % (rec["skill"], rec["killer"])
        if rec["overkill"] and not rec["fusion"] and not rec["trap"]:
            text += _(" · overkill %s") % _num(rec["overkill"])
        self.alert(t, "death", text)

    def alert(self, t, kind, text):
        self.alert_seq += 1
        self.alerts.append((self.alert_seq, t, kind, text))

    def set_items(self, bag, worn):
        self.bag = dict(bag)
        for it in worn:
            for bit, _label in EQUIP_SLOTS:
                if it.location & bit:
                    self.worn[bit] = it
        self.equip_log = [(0, dict(self.worn))]

    def on_wear(self, t, slot, location, equipped):
        if equipped:
            it = self.bag.get(slot)
            if it is None:
                return
            for bit, _label in EQUIP_SLOTS:
                if location & bit:
                    self.worn[bit] = it
        else:
            for bit, _label in EQUIP_SLOTS:
                if location & bit:
                    self.worn.pop(bit, None)
        self.equip_log.append((t, dict(self.worn)))

    def equipment_at(self, t):
        """Equipamento vestido no instante t: [(rótulo do slot, Item)]."""
        worn = {}
        for when, state in self.equip_log:
            if when > t:
                break
            worn = state
        return [(label, worn[bit]) for bit, label in EQUIP_SLOTS if bit in worn]

    def fresh(self, key, t):
        """O servidor costuma mandar o mesmo uso/conjuracao duas vezes seguidas;
        repeticoes em ate 200 ms (mesma fonte, alvo e skill) sao ignoradas."""
        prev = self._last_seen.get(key)
        if prev is not None and t - prev <= DEDUP_MS:
            return False
        self._last_seen[key] = t
        return True

    def actor(self, aid, t):
        """Quem responde por uma acao: o dono (invocacao/unidade) ou a 1a fase do MVP."""
        src = self.resolve(aid)
        if not self.is_friendly(src) and self.entities.get(aid) is not None:
            src = self.phase_root(aid, t)
        return src

    def phase_root(self, aid, t):
        """AID da primeira fase quando `aid` e uma fase seguinte de um MVP em fases."""
        root = self.alias.get(aid)
        if root is not None:
            self.chains[self.entities[aid].job][2] = t
            return root
        e = self.entities.get(aid)
        if e is None or e.kind != "mob" or e.job not in PHASED_BOSSES:
            return aid
        chain = self.chains.get(e.job)
        if chain is not None and chain[1] == aid:
            chain[2] = t
            return chain[0]
        if chain is not None and chain[1] not in self.dead and 0 <= t - chain[2] <= MAX_PHASE_GAP_MS:
            # fase nova: o chefe anterior sumiu sem morrer e outro igual apareceu logo depois
            self.alias[aid] = chain[0]
            self.phases[chain[0]] += 1
            self.phase_starts[chain[0]].append(t)
            self.end_statuses(chain[1], chain[2])  # a fase anterior sumiu sem aviso depois do último evento
            chain[1], chain[2] = aid, t
            return chain[0]
        self.chains[e.job] = [aid, aid, t]
        self.phases[aid] = 1
        return aid

    def on_damage(self, x):
        # golpes de dano 0 (ex.: chefe invencivel) contam como acerto, como no Ragna Recap
        src = self.resolve(x.src)
        if not self.is_friendly(src):
            if self.is_friendly(x.dst) and (src in self.alias or src in self.entities):
                # monstro batendo (ou uma unidade no chao dele): entra na analise e mantem a fase "viva"
                root = self.phase_root(src, x.time)
                self.hits.append(Hit(x, root, self.resolve(x.dst), x.dst, False))
                self.version += 1
            return
        if self.is_friendly(x.dst) or not self.counts_target(x.dst):
            return
        dst = self.phase_root(x.dst, x.time)
        self.hits.append(Hit(x, src, dst, x.dst, True))
        self.version += 1
        enc = self.current
        gap = x.time - enc.last if enc is not None else 0
        # troca de fase: o chefe some e volta com outro AID; ninguem consegue bater nesse
        # meio-tempo, entao ele fica fora do tempo em combate (qualquer que seja a pausa
        # configurada) e nao divide o encontro
        phase_change = False
        if dst in self.phases:
            prev = self.phase_hit.get(dst)
            phase_change = prev is not None and prev != x.dst
            self.phase_hit[dst] = x.dst
        if enc is not None and dst in enc.by_target and dst in self.phases and gap <= MAX_PHASE_GAP_MS \
                and (gap > self.gap_ms or phase_change):
            enc.paused += gap
            enc.pauses.append((enc.last, x.time))
            if self.total is not None:
                self.total.paused += gap
        elif enc is None or gap > self.gap_ms:
            if enc is not None:
                self.closed_ms += enc.duration_ms()
                self.history.append(enc)
                del self.history[:-20]
            enc = self.current = Encounter(x.time)
        if self.total is None:
            self.total = Encounter(x.time)
        label = "" if x.src == self.me else self.name_of(x.src)
        for e in (enc, self.total):
            e.last = max(e.last, x.time)
            e.by_source[src].add(x.damage, x.time, x.crit)
            e.by_target[dst] += x.damage
            if src == self.me:
                e.by_skill[(label, x.skill)].add(x.damage, x.time, x.crit)
                e.my_targets[dst] += x.damage
        if src == self.me:
            self.recent.append((x.time, x.damage))

    def reset(self):
        self.current = self.total = None
        self.history = []
        self.closed_ms = 0
        self.recent.clear()
        self.hits, self.uses, self.casts = [], [], []
        self.deaths = {}
        self.death_log = []
        self.was_reset = True
        self.version += 1

    def encounters(self):
        """Encontros do mais antigo ao mais novo."""
        return self.history + ([self.current] if self.current else [])

    def is_live(self, enc):
        return enc is self.current and self.active()

    was_reset = False

    # --- leitura para a interface ------------------------------------

    def active(self):
        return (not self.finished and self.current is not None
                and self.now - self.current.last <= self.gap_ms)

    def dps_now(self):
        lim = self.now - NOW_WINDOW_MS
        while self.recent and self.recent[0][0] < lim:
            self.recent.popleft()
        return sum(d for _, d in self.recent) * 1000.0 / NOW_WINDOW_MS

    def encounter(self, index=0):
        """0 = atual (ou o ultimo), 1 = anterior..."""
        encs = self.history + ([self.current] if self.current else [])
        if not encs or index >= len(encs):
            return None
        return encs[-1 - index]

    def snapshot(self, enc=None, session=False):
        """Numeros prontos para a tela. session=True soma todos os encontros e usa
        o tempo em combate (sem as pausas) como divisor do DPS."""
        if session:
            enc = self.total
        else:
            enc = enc or self.encounter()
        if enc is None:
            return None
        live = self.active() and (session or enc is self.current)
        if session:
            cur = self.current.duration_ms(self.now if self.active() else None) if self.current else 0
            dur = max(1000, self.closed_ms + cur)
        else:
            dur = enc.duration_ms(self.now if live else None)
        rows = sorted(enc.by_source.items(), key=lambda kv: -kv[1].total)
        group_total = sum(s.total for _, s in rows) or 1
        players = [dict(aid=a, name=self.name_of(a), me=a == self.me, total=s.total,
                        dps=s.total * 1000.0 / dur, share=s.total / group_total,
                        hits=s.hits, max_hit=s.max_hit) for a, s in rows]
        mine = enc.by_source.get(self.me)
        my_total = mine.total if mine else 0
        skills = sorted(enc.by_skill.items(), key=lambda kv: -kv[1].total)
        skill_rows = []
        for (label, sid), s in skills:
            name = skill_name(sid, pretty_aegis(self.skill_aegis.get(sid)))
            if label:
                name = "%s: %s" % (label, name)
            skill_rows.append(dict(name=name, total=s.total, hits=s.hits, max_hit=s.max_hit,
                                   share=s.total / (my_total or 1), dps=s.total * 1000.0 / dur))
        targets = sorted(enc.my_targets.items(), key=lambda kv: -kv[1])
        main_target = max(enc.by_target.items(), key=lambda kv: kv[1])[0] if enc.by_target else None
        return dict(
            live=live, duration_ms=dur, start=enc.start,
            my_total=my_total, my_dps=my_total * 1000.0 / dur,
            my_hits=mine.hits if mine else 0, my_max=mine.max_hit if mine else 0,
            my_crits=mine.crits if mine else 0,
            dps_now=self.dps_now() if live else 0.0,
            group_total=group_total if rows else 0,
            players=players, skills=skill_rows,
            targets=[dict(name=self.target_name(a), total=v) for a, v in targets],
            target=self.target_name(main_target) if main_target else "",
        )


def skill_list_names(d):
    out = {}
    try:
        end = min(struct.unpack_from("<H", d, 2)[0], len(d))
        for p in range(4, end - 36, 37):
            sid = struct.unpack_from("<H", d, p)[0]
            out[sid] = rrf.decode_name(d[p + 12:p + 36])
    except struct.error:
        pass
    return out


def pretty_aegis(name):
    if not name:
        return None
    parts = name.split("_", 1)
    return (parts[1] if len(parts) == 2 else name).replace("_", " ").title()


# --- leitura ao vivo -------------------------------------------------------

DEFAULT_DIRS = [r"C:\Gravity\Ragnarok\Replay", r"C:\Gravity\Ragnarok Online\Replay",
                r"C:\Program Files (x86)\Gravity\Ragnarok\Replay"]
# pastas de instalação comuns, procuradas em todos os discos fixos
GAME_SUBDIRS = [r"Gravity\Ragnarok", r"Gravity\Ragnarok Online", r"Gravity\ROLatam",
                r"Program Files (x86)\Gravity\Ragnarok", r"Program Files\Gravity\Ragnarok", "Ragnarok",
                "Ragnarok Online", "ROLatam", r"Games\Ragnarok", r"Jogos\Ragnarok", r"Juegos\Ragnarok"]
UNINSTALL_KEYS = [r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
                  r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"]


def _registry_game_dirs():
    """Onde o instalador do jogo disse que instalou (só leitura do registro do Windows)."""
    try:
        import winreg
    except ImportError:
        return []
    out = []
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        for path in UNINSTALL_KEYS:
            try:
                key = winreg.OpenKey(root, path)
            except OSError:
                continue
            for i in range(winreg.QueryInfoKey(key)[0]):
                try:
                    sub = winreg.OpenKey(key, winreg.EnumKey(key, i))
                    name = str(winreg.QueryValueEx(sub, "DisplayName")[0])
                except OSError:
                    continue
                if "ragnarok" not in name.lower():
                    continue
                for field in ("InstallLocation", "DisplayIcon"):
                    try:
                        v = str(winreg.QueryValueEx(sub, field)[0]).strip().strip('"').split(",")[0]
                    except OSError:
                        continue
                    if v:
                        out.append(os.path.dirname(v) if field == "DisplayIcon" else v)
    return out


def _fixed_drives():
    if os.name != "nt":
        return []
    try:
        import ctypes
        mask = ctypes.windll.kernel32.GetLogicalDrives()
        drives = [chr(65 + i) + ":\\" for i in range(26) if mask >> i & 1]
        return [d for d in drives if ctypes.windll.kernel32.GetDriveTypeW(d) == 3]      # 3 = disco fixo
    except (AttributeError, OSError):
        return ["C:\\"]


def game_dirs():
    out = []
    for d in _registry_game_dirs() + [os.path.join(drive, rel) for drive in _fixed_drives() for rel in GAME_SUBDIRS]:
        d = os.path.normpath(d)
        if d.lower() not in (x.lower() for x in out):
            out.append(d)
    return out


def is_game_dir(d):
    return any(os.path.exists(os.path.join(d, x)) for x in ("data.grf", "Ragexe.exe", "Ragnarok.exe", "Replay"))


def replay_dir_for(path):
    """Pasta escolhida pelo usuário: aceita a pasta Replay ou a pasta do jogo."""
    path = os.path.normpath(path)
    if os.path.basename(path).lower() != "replay" and is_game_dir(path):
        return os.path.join(path, "Replay")
    return path


def find_replay_dirs():
    """Todas as pastas Replay que dá para achar (há quem tenha várias instalações do jogo).
    A pasta de uma instalação sem gravações ainda não existe: o jogo cria na primeira."""
    out = []
    for d in [x for x in DEFAULT_DIRS if os.path.isdir(x)] + \
            [os.path.join(g, "Replay") for g in game_dirs() if is_game_dir(g)]:
        d = os.path.normpath(d)
        if d.lower() not in (x.lower() for x in out):
            out.append(d)
    return out


def find_replay_dir():
    dirs = find_replay_dirs()
    return dirs[0] if dirs else None


class ReplayFile:
    """Um .rrf sendo lido de forma incremental. O arquivo e aberto e fechado a cada
    leitura, para nunca atrapalhar o jogo quando ele quiser escrever ou fechar."""

    def __init__(self, path, gap_ms=10000, targets="all"):
        self.path = path
        clientdata.NAMES.use_folder(os.path.dirname(path))
        self.gap_ms = gap_ms
        self.targets = targets
        self.header = self.session = self.reader = self.combat = None
        self.pos = 0
        self.size = 0
        self.error = None
        self.alert_floor = 0

    @property
    def ready(self):
        return self.combat is not None

    def poll(self, max_bytes=8 << 20):
        """Le o que ha de novo. Devolve True se algo mudou."""
        try:
            with open(self.path, "rb") as fh:
                size = os.fstat(fh.fileno()).st_size
                if self.header is None:
                    buf = fh.read()
                    try:
                        h = rrf.Header(buf)
                    except ValueError as e:
                        self.error = str(e)
                        return False
                    if not h.stream_offset or h.stream_offset > len(buf):
                        return False
                    self.header = h
                    self.session = rrf.Session(h, buf)
                    self.reader = rrf.StreamReader(h.keys, rrf.WANTED)
                    self.combat = Combat(self.session, self.gap_ms, self.targets)
                    for e in rrf.initial_entities(h, buf):
                        self.combat.add_entity(e)
                    self.combat.start_statuses(rrf.statuses_at_start(h, buf))
                    self.combat.set_items(*rrf.items_at_start(h, buf))
                    self.pos = h.stream_offset
                    catching_up = True
                    self.error = None
                else:
                    catching_up = False
                changed = False
                while size > self.pos:
                    fh.seek(self.pos)
                    data = fh.read(min(size - self.pos, max_bytes))
                    if not data:
                        break
                    self.pos += len(data)
                    self.combat.feed(self.reader.feed(data), self.reader.last_time)
                    changed = True
                if catching_up:
                    # avisos do que já tinha acontecido antes de abrir o arquivo não aparecem
                    self.alert_floor = self.combat.alert_seq
                self.size = size
                return changed
        except OSError as e:
            self.error = str(e)
            return False


class Watcher:
    """Segue a gravacao mais recente entre as pastas Replay (a escolhida e todas as que achar)."""

    ACTIVE_S = 15.0     # arquivo modificado ha menos que isso = gravando
    FIND_S = 30.0       # de quanto em quanto tempo procura instalações novas

    def __init__(self, folder=None, gap_ms=10000, targets="all", auto=True):
        self.targets = targets
        self.extra = replay_dir_for(folder) if folder else None     # escolhida pelo usuário
        self.auto = auto
        self.folders = []
        self._next_find = 0.0
        self.refresh_folders()
        self.gap_ms = gap_ms
        self.file = None
        self.pinned = False           # True quando o usuario abriu um arquivo manualmente
        self.known = {}
        self.last_change = 0.0

    def open(self, path):
        self.file = ReplayFile(path, self.gap_ms, self.targets)
        self.pinned = True
        self.file.poll(max_bytes=64 << 20)
        if self.file.ready:
            self.file.combat.finished = True
        return self.file

    def follow(self):
        self.pinned = False
        self.file = None

    @property
    def folder(self):
        """A pasta principal (a escolhida, ou a primeira que achou)."""
        return self.folders[0] if self.folders else None

    def refresh_folders(self):
        found = find_replay_dirs() if self.auto else []
        out = []
        for d in ([self.extra] if self.extra else []) + found:
            if d.lower() not in (x.lower() for x in out):
                out.append(d)
        self.folders = out
        for d in out:
            clientdata.NAMES.use_folder(d)

    def set_folder(self, folder):
        self.extra = replay_dir_for(folder) if folder else None
        self.refresh_folders()
        self.follow()

    def scan(self, now):
        best = None
        for folder in self.folders:
            try:
                files = os.listdir(folder)
            except OSError:
                continue                              # pasta que o jogo ainda não criou
            for f in files:
                if not f.lower().endswith(".rrf"):
                    continue
                p = os.path.join(folder, f)
                try:
                    st = os.stat(p)
                except OSError:
                    continue
                if now - st.st_mtime <= self.ACTIVE_S and (best is None or st.st_mtime > best[1]):
                    best = (p, st.st_mtime)
        return best[0] if best else None

    def poll(self, now):
        """Devolve True se houve dado novo."""
        if now >= self._next_find:
            self._next_find = now + self.FIND_S      # instalação nova, disco novo, pasta criada
            self.refresh_folders()
        if not self.pinned:
            path = self.scan(now)
            if path and (self.file is None or os.path.normcase(path) != os.path.normcase(self.file.path)):
                self.file = ReplayFile(path, self.gap_ms, self.targets)
        if self.file is None:
            return False
        changed = self.file.poll()
        if changed:
            self.last_change = now
        return changed

    def recording(self, now):
        return (self.file is not None and not self.pinned and self.file.ready
                and now - self.last_change <= self.ACTIVE_S)

    # Medido em 22/10/2026: o cliente escreve cada pacote no arquivo na hora (atraso
    # < 1 s), mas a entrada do fluxo na tabela do cabecalho so aparece ~9 s depois
    # do inicio da gravacao. Ate la `ReplayFile.poll` tenta de novo a cada leitura.
