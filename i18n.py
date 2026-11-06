# -*- coding: utf-8 -*-
"""Idiomas: português (padrão), inglês e espanhol.

`_("texto em português")` devolve o texto no idioma escolhido. O idioma vem da variável
RODPS_LANG, da configuração do medidor ("lang") ou do idioma do Windows, e vale a partir
da abertura do programa (trocar no menu reabre o medidor).

Nomes do jogo (skills, monstros, itens, buffs) vêm dos arquivos do cliente da LATAM em
português e não são traduzidos aqui.
"""

import json
import os

LANGS = [("pt", "Português"), ("en", "English"), ("es", "Español")]


def config_path():
    return os.environ.get("RODPS_CONFIG") or os.path.join(
        os.environ.get("APPDATA") or os.path.expanduser("~"), "RODpsMeter", "config.json")


def _from_config():
    try:
        with open(config_path(), encoding="utf-8") as f:
            v = json.load(f).get("lang")
        return v if v in dict(LANGS) else None
    except (OSError, ValueError, AttributeError):
        return None


def _from_windows():
    try:
        import ctypes
        primary = ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF
    except (AttributeError, OSError):
        return "pt"
    return {0x16: "pt", 0x0A: "es"}.get(primary, "en")


def detect():
    env = os.environ.get("RODPS_LANG")
    if env in dict(LANGS):
        return env
    return _from_config() or _from_windows()


LANG = detect()
TERM_HOOK = None        # o meter instala: troca nomes do jogo citados no texto pelos do idioma escolhido


def _(text):
    if LANG == "pt":
        return text
    t = CATALOG.get(text)
    t = text if t is None else (t[0] if LANG == "en" else t[1])
    return TERM_HOOK(t) if TERM_HOOK else t


# português -> (inglês, espanhol)
CATALOG = {
    # --- widget ---------------------------------------------------------------
    "Grafite": ("Graphite", "Grafito"),
    "Meia-noite": ("Midnight", "Medianoche"),
    "Roxo": ("Purple", "Morado"),
    "Floresta": ("Forest", "Bosque"),
    "Oceano": ("Ocean", "Océano"),
    "Vinho": ("Wine", "Vino"),
    "Âmbar": ("Amber", "Ámbar"),
    "Neon": ("Neon", "Neón"),
    "Claro": ("Light", "Claro"),
    "Pequeno": ("Small", "Pequeño"),
    "Médio": ("Medium", "Mediano"),
    "Grande": ("Large", "Grande"),
    "Muito grande": ("Extra large", "Muy grande"),
    "estreita": ("narrow", "estrecho"),
    "normal": ("normal", "normal"),
    "larga": ("wide", "ancho"),
    "muito larga": ("extra wide", "muy ancho"),
    "5 segundos sem dano": ("5 seconds without damage", "5 segundos sin daño"),
    "10 segundos sem dano": ("10 seconds without damage", "10 segundos sin daño"),
    "15 segundos sem dano": ("15 seconds without damage", "15 segundos sin daño"),
    "30 segundos sem dano": ("30 seconds without damage", "30 segundos sin daño"),
    "1 minuto sem dano": ("1 minute without damage", "1 minuto sin daño"),
    "Todos os monstros": ("All monsters", "Todos los monstruos"),
    "Só MVPs e bonecos de treino": ("MVPs and training dummies only", "Solo MVPs y muñecos de entrenamiento"),
    "Fixar sempre por cima das outras janelas": ("Keep on top of other windows", "Mantener sobre las demás ventanas"),
    "Análise completa (abre outra janela)": ("Full analysis (opens another window)",
                                             "Análisis completo (abre otra ventana)"),
    "Opções": ("Options", "Opciones"),
    "Minimizar": ("Minimize", "Minimizar"),
    "Fechar o medidor": ("Close the meter", "Cerrar el medidor"),
    "Zerar: começa a contar de novo": ("Reset: start counting again", "Reiniciar: empieza a contar de nuevo"),
    "Escolher o que mostrar: tudo ou uma luta": ("Choose what to show: everything or one fight",
                                                 "Elegir qué mostrar: todo o una pelea"),
    "Luta anterior": ("Previous fight", "Pelea anterior"),
    "Próxima luta": ("Next fight", "Pelea siguiente"),
    "Dano de cada jogador": ("Damage by player", "Daño de cada jugador"),
    "O seu dano por skill": ("Your damage by skill", "Tu daño por skill"),
    "Em quem você bateu": ("Who you hit", "A quién le pegaste"),
    "Arraste para mudar a largura e o número de linhas": ("Drag to change the width and number of rows",
                                                          "Arrastra para cambiar el ancho y el número de filas"),
    "Grupo": ("Party", "Grupo"),
    "Skills": ("Skills", "Skills"),
    "Alvos": ("Targets", "Objetivos"),
    "Replay Master": ("Replay Master", "Replay Master"),
    "Zerar": ("Reset", "Reiniciar"),
    "Tudo": ("All", "Todo"),
    "Luta atual": ("Current fight", "Pelea actual"),
    "Luta %d de %d": ("Fight %d of %d", "Pelea %d de %d"),
    "Pasta Replay não encontrada (botão direito › Pasta)": ("Replay folder not found (right-click › Folder)",
                                                            "Carpeta Replay no encontrada (clic derecho › Carpeta)"),
    "Aguardando gravação de replay…": ("Waiting for a replay recording…", "Esperando una grabación de replay…"),
    "Abrindo %s…": ("Opening %s…", "Abriendo %s…"),
    "Gravação começou · aguardando o jogo (~10 s)": ("Recording started · waiting for the game (~10 s)",
                                                     "La grabación empezó · esperando al juego (~10 s)"),
    "Gravando · %s": ("Recording · %s", "Grabando · %s"),
    "Gravação encerrada · %s": ("Recording ended · %s", "Grabación terminada · %s"),
    "Personagem": ("Character", "Personaje"),
    "Medidor de DPS": ("DPS meter", "Medidor de DPS"),
    "agora %s/s": ("now %s/s", "ahora %s/s"),
    "total %s": ("total %s", "total %s"),
    "em combate": ("in combat", "en combate"),
    "ao vivo": ("live", "en vivo"),
    "duração": ("duration", "duración"),
    "Luta %d/%d · %s": ("Fight %d/%d · %s", "Pelea %d/%d · %s"),
    "Zerado.": ("Reset.", "Reiniciado."),
    "O próximo dano começa um encontro novo.": ("The next hit starts a new encounter.",
                                                "El próximo golpe empieza un encuentro nuevo."),
    "Nenhum dano ainda.": ("No damage yet.", "Todavía no hay daño."),
    "Ataque algo enquanto grava o replay.": ("Attack something while recording the replay.",
                                             "Ataca algo mientras grabas el replay."),
    "No jogo, comece a gravar um replay.": ("In the game, start recording a replay.",
                                            "En el juego, empieza a grabar un replay."),
    "O medidor acha o arquivo sozinho.": ("The meter finds the file by itself.",
                                          "El medidor encuentra el archivo solo."),
    "Nenhum dano neste encontro.": ("No damage in this encounter.", "No hay daño en este encuentro."),
    "%.0f%% · %d acertos": ("%.0f%% · %d hits", "%.0f%% · %d golpes"),
    "Você não causou dano aqui.": ("You dealt no damage here.", "No hiciste daño aquí."),
    "Tudo (desde o início ou desde Zerar)": ("Everything (since the start or since Reset)",
                                             "Todo (desde el inicio o desde Reiniciar)"),
    "Luta atual (a mais recente)": ("Current fight (the latest)", "Pelea actual (la más reciente)"),
    "Lutas anteriores:": ("Previous fights:", "Peleas anteriores:"),
    "Luta %d · %s · %s": ("Fight %d · %s · %s", "Pelea %d · %s · %s"),
    "Uma luta termina após": ("A fight ends after", "Una pelea termina tras"),
    "Contar dano em": ("Count damage on", "Contar daño en"),
    "As fases de um MVP contam como uma luta só": ("An MVP's phases count as a single fight",
                                                   "Las fases de un MVP cuentan como una sola pelea"),
    "Invocações de jogadores (ex.: Esfera Marinha) nunca contam": (
        "Player summons (e.g. Esfera Marinha) never count",
        "Las invocaciones de jugadores (ej.: Esfera Marinha) nunca cuentan"),
    "Abrir replay": ("Open replay", "Abrir replay"),
    "Replay do Ragnarok": ("Ragnarok replay", "Replay de Ragnarok"),
    "Todos": ("All", "Todos"),
    "Pasta Replay do Ragnarok": ("Ragnarok Replay folder", "Carpeta Replay de Ragnarok"),
    "Fixar sempre no topo": ("Always on top", "Siempre encima"),
    "Mostrar": ("Show", "Mostrar"),
    "Grupo: mostrar % em vez de DPS": ("Party: show % instead of DPS", "Grupo: mostrar % en vez de DPS"),
    "Análise completa…": ("Full analysis…", "Análisis completo…"),
    "Avisar quando um buff acabar na luta": ("Warn when a buff ends during a fight",
                                             "Avisar cuando un buff termine en la pelea"),
    "Avisar quando eu morrer (com overkill)": ("Warn when I die (with overkill)",
                                               "Avisar cuando muera (con overkill)"),
    "Avisar HP baixo com a União Solar (Mestre Taekwon)": ("Warn on low HP with União Solar (Mestre Taekwon)",
                                                           "Avisar HP bajo con União Solar (Mestre Taekwon)"),
    "Salvar testes no boneco sozinho": ("Save dummy tests automatically",
                                        "Guardar pruebas en el muñeco automáticamente"),
    "Abrir replay salvo…": ("Open saved replay…", "Abrir replay guardado…"),
    "Voltar a seguir a gravação": ("Go back to following the recording", "Volver a seguir la grabación"),
    "Pasta dos replays…": ("Replay folder…", "Carpeta de replays…"),
    "(não encontrada)": ("(not found)", "(no encontrada)"),
    "Cor": ("Color", "Color"),
    "Largura: %s": ("Width: %s", "Ancho: %s"),
    "Arraste o canto: largura e linhas": ("Drag the corner: width and rows", "Arrastra la esquina: ancho y filas"),
    "Ctrl + roda (ou Shift + arrastar): zoom": ("Ctrl + wheel (or Shift + drag): zoom",
                                                "Ctrl + rueda (o Shift + arrastrar): zoom"),
    "Tamanho": ("Size", "Tamaño"),
    "%d linhas": ("%d rows", "%d filas"),
    "Linhas": ("Rows", "Filas"),
    "Opacidade": ("Opacity", "Opacidad"),
    "Fechar": ("Close", "Cerrar"),
    "Idioma": ("Language", "Idioma"),
    "Sobre": ("About", "Acerca de"),
    "Medidor de DPS para Ragnarok Online (ROLatam) · versão %s": (
        "DPS meter for Ragnarok Online (ROLatam) · version %s",
        "Medidor de DPS para Ragnarok Online (ROLatam) · versión %s"),
    "Só lê o arquivo de replay que o jogo grava. Não lê a memória do jogo, não mexe na rede e não "
    "manda nada para a internet.": (
        "It only reads the replay file the game records. It doesn't read game memory, touch the network "
        "or send anything to the internet.",
        "Solo lee el archivo de replay que graba el juego. No lee la memoria del juego, no toca la red y no "
        "envía nada a internet."),
    # --- avisos do widget e nomes gerais (meter.py) ----------------------------
    "HP %d%% com a União: abaixo de 20%% o próximo ataque mata": (
        "HP %d%% with União: below 20%% the next attack kills you",
        "HP %d%% con la União: por debajo del 20%% el próximo ataque te mata"),
    "HP %d%% com a União: o próximo ataque pode matar!": ("HP %d%% with União: the next attack may kill you!",
                                                          "HP %d%% con la União: ¡el próximo ataque puede matarte!"),
    "Ataque básico": ("Basic attack", "Ataque básico"),
    "Monstro %d": ("Monster %d", "Monstruo %d"),
    # complementos dos nomes de skill da base do medidor ("Dor Máxima (ataque)") e rótulos próprios
    "ataque": ("attack", "ataque"),
    "água": ("water", "agua"),
    "fogo": ("fire", "fuego"),
    "vento": ("wind", "viento"),
    "terra": ("earth", "tierra"),
    "explosão": ("explosion", "explosión"),
    "bônus": ("bonus", "bono"),
    "ativar": ("on", "activar"),
    "desativar": ("off", "desactivar"),
    "Alívio": ("Relieve", "Alivio"),
    "Quebra Aleatória": ("Random Break", "Ruptura Aleatoria"),
    "Redução de dano do chefe": ("Boss damage reduction", "Reducción de daño del jefe"),
    # skills de monstro que o cliente não nomeia (em inglês o resto vem da descrição do rAthena)
    "Ataque Guiado": ("Guided Attack", "Ataque Guiado"),
    "Ataque de Fogo": ("Fire Attack", "Ataque de Fuego"),
    "Golpe Sombrio": ("Dark Strike", "Golpe Oscuro"),
    "Aumentar Poder": ("Power Up", "Aumentar Poder"),
    "Encantar Arma": ("Weapon Enchantment", "Encantar Arma"),
    "Invencibilidade": ("Invincible", "Invencibilidad"),
    "Mover para Coordenada": ("Move Coordinate", "Mover a Coordenada"),
    "Sangramento": ("Bleeding", "Sangrado"),
    "Remover Equipamento Sombrio": ("Remove Shadow Equipment", "Quitar Equipo de Sombra"),
    "Aura Assassina": ("Killing Aura", "Aura Asesina"),
    "Barreira": ("Barrier", "Barrera"),
    # skills das invocações do Cientista (o cliente não dá nome; invocações como em "Criar ..." do cliente)
    "Arremesso de Pedra (Bárbaro)": ("Throw Rock (Wooden Warrior)", "Lanzar Roca (Guerrero de Madera)"),
    "Ataque de Madeira (Bárbaro)": ("Wooden Attack (Wooden Warrior)", "Ataque de Madera (Guerrero de Madera)"),
    "Uivo Infernal (Árvore Infernal)": ("Hell Howling (Hell Tree)", "Aullido Infernal (Árbol Infernal)"),
    "Poeira Infernal (Árvore Infernal)": ("Hell Dust (Hell Tree)", "Polvo Infernal (Árbol Infernal)"),
    "Em Fúria!": ("Berserk Potion", "¡En Furia!"),
    "Comida de Precisão": ("Accuracy food", "Comida de precisión"),
    "Comida de Crítico": ("Critical food", "Comida de crítico"),
    "Pasta Replay não encontrada": ("Replay folder not found", "Carpeta Replay no encontrada"),
    "Não achei a pasta Replay do jogo.": ("I couldn't find the game's Replay folder.",
                                          "No encontré la carpeta Replay del juego."),
    "Clique aqui e escolha a pasta do Ragnarok.": ("Click here and pick the Ragnarok folder.",
                                                   "Haz clic aquí y elige la carpeta de Ragnarok."),
    "%d pastas Replay": ("%d Replay folders", "%d carpetas Replay"),
    "Olhando em %s": ("Watching %s", "Mirando en %s"),
    "Escolha a pasta do Ragnarok (ou a pasta Replay dentro dela)": (
        "Pick the Ragnarok folder (or the Replay folder inside it)",
        "Elige la carpeta de Ragnarok (o la carpeta Replay dentro de ella)"),
    "Você": ("You", "Tú"),
    "%s acabou": ("%s ended", "%s terminó"),
    "Você morreu": ("You died", "Moriste"),
    ": armadilha do mapa": (": map trap", ": trampa del mapa"),
    ": União Solar (atacou com %s de HP)": (": União Solar (attacked at %s HP)", ": União Solar (atacó con %s de HP)"),
    "pouco": ("low", "poco"),
    "Topo": ("Upper headgear", "Casco superior"),
    "Meio": ("Middle headgear", "Casco medio"),
    "Baixo": ("Lower headgear", "Casco inferior"),
    "Armadura": ("Armor", "Armadura"),
    "Arma": ("Weapon", "Arma"),
    "Escudo": ("Shield", "Escudo"),
    "Capa": ("Garment", "Capa"),
    "Sapato": ("Shoes", "Zapatos"),
    "Acessório esq.": ("Accessory L", "Accesorio izq."),
    "Acessório dir.": ("Accessory R", "Accesorio der."),
    "Munição": ("Ammo", "Munición"),
    "Visual topo": ("Costume upper", "Visual superior"),
    "Visual meio": ("Costume middle", "Visual medio"),
    "Visual baixo": ("Costume lower", "Visual inferior"),
    "Visual capa": ("Costume garment", "Visual capa"),
    "Sombrio armadura": ("Shadow armor", "Sombrío armadura"),
    "Sombrio arma": ("Shadow weapon", "Sombrío arma"),
    "Sombrio escudo": ("Shadow shield", "Sombrío escudo"),
    "Sombrio sapato": ("Shadow shoes", "Sombrío zapatos"),
    "Sombrio acess. dir.": ("Shadow acc. R", "Sombrío acc. der."),
    "Sombrio acess. esq.": ("Shadow acc. L", "Sombrío acc. izq."),
    " · grau %s": (" · grade %s", " · grado %s"),
    # tipos de status (chaves internas em português; só a tela traduz)
    "Sistema": ("System", "Sistema"),
    "Grupo/suporte": ("Party/support", "Grupo/soporte"),
    "Consumível": ("Consumable", "Consumible"),
    "Serviço": ("Service", "Servicio"),
    "Outro": ("Other", "Otro"),
    "Classe/outros": ("Class/other", "Clase/otros"),
    # --- análise (analysis.py) ---------------------------------------------------
    "Homúnculo": ("Homunculus", "Homúnculo"),
    "Mercenário": ("Mercenary", "Mercenario"),
    "Elemental": ("Elemental", "Elemental"),
    "Planta": ("Plant", "Planta"),
    "Invocação": ("Summon", "Invocación"),
    " (%d fases)": (" (%d phases)", " (%d fases)"),
    " ★ (%d fases)": (" ★ (%d phases)", " ★ (%d fases)"),
    "%s — %s em combate": ("%s — %s in combat", "%s — %s en combate"),
    "Armadilha do mapa": ("Map trap", "Trampa del mapa"),
    "Armadilha": ("Trap", "Trampa"),
    " (errou)": (" (missed)", " (falló)"),
    "HP atualizado": ("HP updated", "HP actualizado"),
    " (%d%% do HP máx.)": (" (%d%% of max HP)", " (%d%% del HP máx.)"),
    " (~%d%% do HP máx.)": (" (~%d%% of max HP)", " (~%d%% del HP máx.)"),
    "Sem golpe visível": ("No visible hit", "Sin golpe visible"),
    "HP perdido (efeitos no momento: %s)": ("HP lost (effects at that moment: %s)",
                                            "HP perdido (efectos en ese momento: %s)"),
    # --- testes ------------------------------------------------------------------
    "DPS (em combate)": ("DPS (in combat)", "DPS (en combate)"),
    "DPS do 1º ao último golpe": ("DPS from first to last hit", "DPS del 1.º al último golpe"),
    "Dano": ("Damage", "Daño"),
    "Tempo em combate": ("Time in combat", "Tiempo en combate"),
    "Acertos": ("Hits", "Golpes"),
    "Maior golpe": ("Biggest hit", "Golpe más grande"),
    # --- janela de análise ------------------------------------------------------
    "Sessão inteira": ("Whole session", "Sesión completa"),
    "Último encontro (acompanha)": ("Latest encounter (follows)", "Último encuentro (sigue)"),
    "Sem eventos de dano para exibir.": ("No damage events to show.", "No hay eventos de daño para mostrar."),
    "Nenhum dano neste recorte.": ("No damage in this range.", "No hay daño en este rango."),
    "Análise — Replay Master   (Ctrl + roda do mouse: tamanho)": (
        "Analysis — Replay Master   (Ctrl + mouse wheel: size)", "Análisis — Replay Master   (Ctrl + rueda: tamaño)"),
    "Análise": ("Analysis", "Análisis"),
    "Copiar ranking": ("Copy ranking", "Copiar ranking"),
    "Recorte:": ("Range:", "Rango:"),
    "Agrupar fases dos MVPs": ("Group MVP phases", "Agrupar fases de los MVPs"),
    "Dano do grupo": ("Party damage", "Daño del grupo"),
    "DPS do grupo": ("Party DPS", "DPS del grupo"),
    "Em combate": ("In combat", "En combate"),
    "Jogadores": ("Players", "Jugadores"),
    "Eventos de dano": ("Damage events", "Eventos de daño"),
    "Gravação": ("Recording", "Grabación"),
    "Resumo": ("Summary", "Resumen"),
    "Seu dano": ("Your damage", "Tu daño"),
    "Seu DPS (em combate)": ("Your DPS (in combat)", "Tu DPS (en combate)"),
    "Skill mais usada": ("Most used skill", "Skill más usada"),
    "Abates (golpe fatal)": ("Kills (killing blow)", "Muertes causadas (golpe final)"),
    "Dano recebido": ("Damage taken", "Daño recibido"),
    "Mortes": ("Deaths", "Muertes"),
    "Seus maiores golpes": ("Your biggest hits", "Tus golpes más grandes"),
    "Tempo": ("Time", "Tiempo"),
    "Habilidade": ("Skill", "Habilidad"),
    "Alvo": ("Target", "Objetivo"),
    "Hits": ("Hits", "Hits"),
    "Fonte": ("Source", "Fuente"),
    "De onde veio o dano que você levou": ("Where the damage you took came from",
                                           "De dónde vino el daño que recibiste"),
    "Jogadores — dano de invocações e skills de chão conta para o dono": (
        "Players — damage from summons and ground skills counts for the owner",
        "Jugadores — el daño de invocaciones y skills de suelo cuenta para el dueño"),
    "Jogador": ("Player", "Jugador"),
    "Classe": ("Class", "Clase"),
    "Erros": ("Misses", "Fallos"),
    "Monstros": ("Monsters", "Monstruos"),
    "Abates": ("Kills", "Muertes causadas"),
    "Habilidades": ("Skills", "Habilidades"),
    "Dano total": ("Total damage", "Daño total"),
    "Dano médio": ("Average damage", "Daño medio"),
    "Hits médios": ("Average hits", "Hits medios"),
    "Cast médio": ("Average cast", "Cast medio"),
    "Monstros atingidos": ("Monsters hit", "Monstruos golpeados"),
    "Monstro": ("Monster", "Monstruo"),
    "Dano ao longo do tempo (todos)": ("Damage over time (everyone)", "Daño a lo largo del tiempo (todos)"),
    "Dano a cada": ("Damage every", "Daño cada"),
    "Monstros atacados — clique para ver o confronto": ("Monsters attacked — click to see the fight",
                                                        "Monstruos atacados — haz clic para ver el combate"),
    "ID do mob": ("Mob ID", "ID del mob"),
    "Atacantes": ("Attackers", "Atacantes"),
    "HP máx.": ("Max HP", "HP máx."),
    "Tempo até abate": ("Time to kill", "Tiempo hasta matarlo"),
    "Abatido por": ("Killed by", "Matado por"),
    "Dano por jogador": ("Damage by player", "Daño por jugador"),
    "Linha do tempo": ("Timeline", "Línea de tiempo"),
    "uma linha por jogador · tracejado = troca de fase": ("one line per player · dashed = phase change",
                                                          "una línea por jugador · discontinua = cambio de fase"),
    "Habilidades usadas contra ele": ("Skills used against it", "Habilidades usadas contra él"),
    "Habilidades do monstro": ("Monster skills", "Habilidades del monstruo"),
    "Com dano e de suporte/debuff.   Filtrar por alvo:": ("With damage and support/debuff.   Filter by target:",
                                                          "Con daño y de soporte/debuff.   Filtrar por objetivo:"),
    "Todos os alvos": ("All targets", "Todos los objetivos"),
    "ID": ("ID", "ID"),
    "Usos sem dano": ("Uses without damage", "Usos sin daño"),
    "Análise de DPS": ("DPS analysis", "Análisis de DPS"),
    "Jogador:": ("Player:", "Jugador:"),
    "  Barras a cada": ("  Bars every", "  Barras cada"),
    "Limpar seleção": ("Clear selection", "Borrar selección"),
    "Estatísticas da janela": ("Window stats", "Estadísticas del tramo"),
    "Janela": ("Window", "Tramo"),
    "DPS médio": ("Average DPS", "DPS medio"),
    "Intervalo médio": ("Average interval", "Intervalo medio"),
    "Dano por golpe": ("Damage per hit", "Daño por golpe"),
    "Maior intervalo": ("Longest interval", "Intervalo más largo"),
    "Skills distintas": ("Distinct skills", "Skills distintas"),
    "Skill com mais dano": ("Top damage skill", "Skill con más daño"),
    "Habilidades no trecho": ("Skills in the window", "Habilidades en el tramo"),
    "Encontro %d · %s–%s · %s": ("Encounter %d · %s–%s · %s", "Encuentro %d · %s–%s · %s"),
    "sem replay aberto — comece a gravar no jogo ou abra um replay salvo": (
        "no replay open — start recording in the game or open a saved replay",
        "sin replay abierto — empieza a grabar en el juego o abre un replay guardado"),
    "● ao vivo": ("● live", "● en vivo"),
    "gravando": ("recording", "grabando"),
    "replay encerrado": ("replay ended", "replay terminado"),
    "%s · gravado %02d/%02d às %02d:%02d": ("%s · recorded %02d/%02d at %02d:%02d",
                                            "%s · grabado %02d/%02d a las %02d:%02d"),
    "%s · %s · nível %d": ("%s · %s · level %d", "%s · %s · nivel %d"),
    "%s do grupo": ("%s of the party", "%s del grupo"),
    "tempo em combate %s": ("time in combat %s", "tiempo en combate %s"),
    "como no Ragna Recap": ("same as Ragna Recap", "igual que en Ragna Recap"),
    "%d erros · %d críticos": ("%d misses · %d crits", "%d fallos · %d críticos"),
    "%d usos": ("%d uses", "%d usos"),
    "%d chefes": ("%d bosses", "%d jefes"),
    "%d acertos": ("%d hits", "%d golpes"),
    "dano %s": ("damage %s", "daño %s"),
    "Fase %d": ("Phase %d", "Fase %d"),
    "Nenhum monstro atacado neste recorte.": ("No monsters attacked in this range.",
                                              "Ningún monstruo atacado en este rango."),
    "HP máx. %s": ("Max HP %s", "HP máx. %s"),
    "abatido em %s por %s": ("killed in %s by %s", "matado en %s por %s"),
    "%s (você)": ("%s (you)", "%s (tú)"),
    "DPS móvel (5 s)": ("Rolling DPS (5 s)", "DPS móvil (5 s)"),
    "média da janela: %s": ("window average: %s", "promedio del tramo: %s"),
    "Nenhum dano deste jogador no recorte.": ("No damage from this player in the range.",
                                              "Ningún daño de este jugador en el rango."),
    "Estatísticas da janela — %s": ("Window stats — %s", "Estadísticas del tramo — %s"),
    "recorte inteiro (arraste no gráfico para escolher)": ("whole range (drag on the chart to pick)",
                                                           "rango completo (arrastra en el gráfico para elegir)"),
    "do 1º ao último golpe": ("from first to last hit", "del 1.º al último golpe"),
    "tudo": ("all", "todo"),
    "Buffs": ("Buffs", "Buffs"),
    "Seus buffs": ("Your buffs", "Tus buffs"),
    "Buff": ("Buff", "Buff"),
    "Tipo": ("Type", "Tipo"),
    "Tempo ativo em combate": ("Uptime in combat", "Tiempo activo en combate"),
    "Aplicações": ("Applications", "Aplicaciones"),
    "Já estava no início": ("Already on at start", "Ya estaba al inicio"),
    "Agora": ("Now", "Ahora"),
    "Debuffs no monstro": ("Debuffs on the monster", "Debuffs en el monstruo"),
    "Debuff": ("Debuff", "Debuff"),
    "Tempo ativo enquanto apanhava": ("Uptime while being hit", "Tiempo activo mientras recibía golpes"),
    "Importante": ("Important", "Importante"),
    "sim": ("yes", "sí"),
    "ativo · %s": ("active · %s", "activo · %s"),
    "ativo": ("active", "activo"),
    "Seus buffs — %% do tempo em combate, vivo (%s). Em vermelho: buff de grupo ou consumível ativo em "
    "menos de 80%% desse tempo.": (
        "Your buffs — %% of the time in combat, alive (%s). In red: party buff or consumable active for "
        "less than 80%% of that time.",
        "Tus buffs — %% del tiempo en combate, vivo (%s). En rojo: buff de grupo o consumible activo menos "
        "del 80%% de ese tiempo."),
    "apanhou durante %s": ("was hit for %s", "recibió golpes durante %s"),
    "Mortes de jogadores — HP só é conhecido para você e para quem está no seu grupo": (
        "Player deaths — HP is only known for you and your party",
        "Muertes de jugadores — el HP solo se conoce para ti y para tu grupo"),
    "Causa": ("Cause", "Causa"),
    "Golpe": ("Hit", "Golpe"),
    "HP antes": ("HP before", "HP antes"),
    "Overkill": ("Overkill", "Overkill"),
    "Dano em 5 s": ("Damage in 5 s", "Daño en 5 s"),
    "Antes da morte": ("Before death", "Antes de morir"),
    "Habilidade / evento": ("Skill / event", "Habilidad / evento"),
    "HP": ("HP", "HP"),
    "União Solar, Lunar e Estelar (atacou com %s de HP)": ("União Solar, Lunar e Estelar (attacked at %s HP)",
                                                           "União Solar, Lunar e Estelar (atacó con %s de HP)"),
    "20% ou menos": ("20% or less", "20% o menos"),
    "sem golpe visível (efeito, debuff ou algo fora da tela)": (
        "no visible hit (effect, debuff or something off screen)",
        "sin golpe visible (efecto, debuff o algo fuera de pantalla)"),
    "último golpe: %s · %s (não bastava sozinho)": ("last hit: %s · %s (not enough on its own)",
                                                    "último golpe: %s · %s (no bastaba solo)"),
    "Nenhuma morte de jogador neste recorte.": ("No player deaths in this range.",
                                                "Ninguna muerte de jugador en este rango."),
    "%s morreu em %s": ("%s died at %s", "%s murió en %s"),
    " — armadilha do mapa": (" — map trap", " — trampa del mapa"),
    " · overkill ~%s": (" · overkill ~%s", " · overkill ~%s"),
    " — União Solar, Lunar e Estelar": (" — União Solar, Lunar e Estelar", " — União Solar, Lunar e Estelar"),
    " — %s de %s: %s": (" — %s from %s: %s", " — %s de %s: %s"),
    " · overkill %s": (" · overkill %s", " · overkill %s"),
    " (o golpe foi %.1f× o HP que restava)": (" (the hit was %.1f× the HP left)",
                                              " (el golpe fue %.1f× el HP que quedaba)"),
    "as armadilhas da Torre da Constelação tiram uma %% fixa do HP máx. (irredutível), que sobe com a "
    "dificuldade e conforme o chefe perde vida; a %% vem das armadilhas que não mataram%s": (
        "the Constellation Tower traps take a fixed %% of max HP (irreducible), which grows with the difficulty "
        "and as the boss loses HP; the %% comes from the traps that didn't kill%s",
        "las trampas de la Torre de la Constelación quitan un %% fijo del HP máx. (irreducible), que sube con la "
        "dificultad y a medida que el jefe pierde vida; el %% viene de las trampas que no mataron%s"),
    " — HP antes: %s": (" — HP before: %s", " — HP antes: %s"),
    "a armadilha estimada era menor que o último HP conhecido: o HP do grupo chega com atraso, então algum "
    "golpe pode ter vindo antes": (
        "the estimated trap was smaller than the last known HP: party HP arrives late, so some hit may have "
        "come first",
        "la trampa estimada era menor que el último HP conocido: el HP del grupo llega con retraso, así que "
        "algún golpe pudo llegar antes"),
    "com a União, cada ataque físico custa 2%% do HP máx. e atacar com 20%% de HP ou menos mata na hora. HP no "
    "último registro: %s%s": (
        "with União, each physical attack costs 2%% of max HP and attacking at 20%% HP or less kills instantly. "
        "HP at last record: %s%s",
        "con la União, cada ataque físico cuesta el 2%% del HP máx. y atacar con 20%% de HP o menos mata al "
        "instante. HP en el último registro: %s%s"),
    " (%d%% de %s)": (" (%d%% of %s)", " (%d%% de %s)"),
    "HP gasto pela União nos 10 s antes: %s": ("HP spent by União in the 10 s before: %s",
                                               "HP gastado por la União en los 10 s anteriores: %s"),
    "HP antes do último golpe: %s%s": ("HP before the last hit: %s%s", "HP antes del último golpe: %s%s"),
    " de %s": (" of %s", " de %s"),
    "perdeu %s de HP sem golpe visível": ("lost %s HP with no visible hit", "perdió %s de HP sin golpe visible"),
    "o último golpe visível (%s) era menor que o HP: a causa real não apareceu no replay": (
        "the last visible hit (%s) was smaller than the HP: the real cause isn't in the replay",
        "el último golpe visible (%s) era menor que el HP: la causa real no aparece en el replay"),
    "dano recebido nos últimos 5 s: %s em %d golpes": ("damage taken in the last 5 s: %s in %d hits",
                                                       "daño recibido en los últimos 5 s: %s en %d golpes"),
    "efeitos ativos: ": ("active effects: ", "efectos activos: "),
    "Testes": ("Tests", "Pruebas"),
    "Salvar recorte atual": ("Save current range", "Guardar rango actual"),
    "Renomear": ("Rename", "Renombrar"),
    "Excluir": ("Delete", "Borrar"),
    "Gravado em": ("Recorded", "Grabado el"),
    "Rótulo": ("Label", "Etiqueta"),
    "Métrica": ("Metric", "Métrica"),
    "Skill": ("Skill", "Skill"),
    "A dano": ("A damage", "A daño"),
    "B dano": ("B damage", "B daño"),
    "Equipamento": ("Equipment", "Equipo"),
    "Slot": ("Slot", "Slot"),
    "A tempo ativo": ("A uptime", "A tiempo activo"),
    "B tempo ativo": ("B uptime", "B tiempo activo"),
    "%d teste(s). Os encontros contra bonecos de treino são salvos sozinhos. Ctrl + clique escolhe dois para "
    "comparar.": (
        "%d test(s). Fights against training dummies are saved automatically. Ctrl + click picks two to compare.",
        "%d prueba(s). Las peleas contra muñecos de entrenamiento se guardan solas. Ctrl + clic elige dos para "
        "comparar."),
    "Escolha um teste (compara com o anterior do mesmo personagem) ou dois.": (
        "Pick a test (compares with the previous one of the same character) or two.",
        "Elige una prueba (compara con la anterior del mismo personaje) o dos."),
    "A: %s     B: %s": ("A: %s     B: %s", "A: %s     B: %s"),
    "Salvar teste": ("Save test", "Guardar prueba"),
    "Rótulo (ex.: com Coroa +12, sem Impositio):": ("Label (e.g. with +12 Crown, no Impositio):",
                                                    "Etiqueta (ej.: con Corona +12, sin Impositio):"),
    "Renomear teste": ("Rename test", "Renombrar prueba"),
    "Rótulo:": ("Label:", "Etiqueta:"),
    "Copiado!": ("Copied!", "¡Copiado!"),
    "Encontro": ("Encounter", "Encuentro"),
    # --- Dedo Duro (aba) -----------------------------------------------------------
    "Dedo Duro": ("Snitch", "Soplón"),
    "Chefe:": ("Boss:", "Jefe:"),
    "Copiar relatório": ("Copy report", "Copiar informe"),
    "Fora do grupo": ("Outside the party", "Fuera del grupo"),
    "Gravidade": ("Severity", "Gravedad"),
    "Fase": ("Phase", "Fase"),
    "O quê": ("What", "Qué"),
    "Quem": ("Who", "Quién"),
    "Detalhe": ("Detail", "Detalle"),
    "Fase 1": ("Phase 1", "Fase 1"),
    "Fase 2": ("Phase 2", "Fase 2"),
    "Fase 3": ("Phase 3", "Fase 3"),
    "Buffs no clímax": ("Buffs at the climax", "Buffs en el clímax"),
    "Recarga / AP": ("Cooldown / AP", "Recarga / AP"),
    "Debuffs no chefe": ("Debuffs on the boss", "Debuffs en el jefe"),
    "Quem aplica": ("Who applies", "Quién aplica"),
    "Observação": ("Note", "Nota"),
    "Início": ("Start", "Inicio"),
    "Sem Garra": ("No Garra Sombria", "Sin Garra Sombria"),
    "Dor Máxima": ("Dor Máxima", "Dor Máxima"),
    "Refletidos": ("Reflected", "Reflejados"),
    "Executores": ("Executor", "Executor"),
    "Morreu": ("Died", "Murió"),
    "Tempo morto": ("Time dead", "Tiempo muerto"),
    "Volta": ("Back", "Vuelta"),
    "Buffs que não voltaram em 15 s": ("Buffs not back within 15 s", "Buffs que no volvieron en 15 s"),
    "Elemento": ("Element", "Elemento"),
    "Dano no Florescer": ("Damage during Florescer", "Daño durante Florescer"),
    "Com fogo": ("With fire", "Con fuego"),
    "Sem conversor": ("No converter", "Sin conversor"),
    "Não visível": ("Not visible", "No visible"),
    "Situação": ("Status", "Situación"),
    "Papel": ("Role", "Rol"),
    "Dano no chefe": ("Damage on the boss", "Daño al jefe"),
    "% do dano": ("% of damage", "% del daño"),
    "Maior tempo morto": ("Longest time dead", "Mayor tiempo muerto"),
    "Veneno": ("Poison", "Veneno"),
    "Arma com veneno": ("Poisoned weapon", "Arma con veneno"),
    "Chefe c/ Potencializar Veneno": ("Boss with Potencializar Veneno", "Jefe con Potencializar Veneno"),
    "Os dois juntos": ("Both together", "Los dos juntos"),
    "Só o que faltou (abaixo de 50% em alguma fase)": ("Only what was missing (below 50% in some phase)",
                                                       "Solo lo que faltó (debajo del 50% en alguna fase)"),
    "Nenhuma luta contra chefe neste recorte": ("No boss fights in this range", "Ninguna pelea contra jefes en este rango"),
    "O Dedo Duro olha as lutas contra MVPs, chefes de instância e bonecos de treino.": (
        "The Snitch looks at fights against MVPs, instance bosses and training dummies.",
        "El Soplón mira las peleas contra MVPs, jefes de instancia y muñecos de entrenamiento."),
    "MVP": ("MVP", "MVP"),
    "boneco de treino": ("training dummy", "muñeco de entrenamiento"),
    "chefe": ("boss", "jefe"),
    "não morreu": ("not killed", "no murió"),
    "morto em %s": ("killed in %s", "muerto en %s"),
    "elemento %s %d%s": ("element %s %d%s", "elemento %s %d%s"),
    " (vantagem: %s)": (" (advantage: %s)", " (ventaja: %s)"),
    " (nenhum elemento tem vantagem; só o Florescer muda isso)": (
        " (no element has an advantage; only Florescer changes that)",
        " (ningún elemento tiene ventaja; solo Florescer cambia eso)"),
    "elemento do chefe desconhecido: só a regra do Florescer vale": (
        "boss element unknown: only the Florescer rule applies",
        "elemento del jefe desconocido: solo vale la regla de Florescer"),
    "usa Dor Máxima (reflete dano)": ("uses Dor Máxima (reflects damage)", "usa Dor Máxima (refleja daño)"),
    "grupo: ● %d grave%s   ◐ %d atenção": ("party: ● %d serious%.0s   ◐ %d warning", "grupo: ● %d grave%s   ◐ %d atención"),
    "Grupo (%d)": ("Party (%d)", "Grupo (%d)"),
    "Fora do grupo (%d)": ("Outside the party (%d)", "Fuera del grupo (%d)"),
    "O que faltou e o que deu errado — %d grave(s), %d de atenção, %d informativo(s)": (
        "What was missing and what went wrong — %d serious, %d warning(s), %d info",
        "Qué faltó y qué salió mal — %d grave(s), %d de atención, %d informativo(s)"),
    "Só no clímax, por fase e com quem está vivo; só é cobrado o que alguma classe do grupo dá. De quem gravou, "
    "todos os buffs aparecem. Dos outros, buff dado antes de começar a gravar só aparece quando acaba (? = não dá "
    "para saber; grave antes de buffar). Competentia, Benedictum, Presens Acies, Argutus, Lauda, Reencarnação das "
    "Almas e Talismã do Guerreiro/Mago o jogo não mostra nos outros jogadores: desses, só se cobra de quem gravou.": (
        "Climax only, per phase and only while alive; something is only flagged if a class in the party provides "
        "it. All of the recorder's buffs are visible. For others, a buff given before recording started only shows "
        "up when it ends (? = can't tell; record before buffing). Competentia, Benedictum, Presens Acies, Argutus, "
        "Lauda, Reencarnação das Almas, Talismã do Guerreiro and Talismã do Mago are not shown on other players by "
        "the game: "
        "those are only checked on the recorder.",
        "Solo en el clímax, por fase y con quien está vivo; solo se exige lo que alguna clase del grupo da. De "
        "quien grabó, todos los buffs aparecen. De los demás, un buff dado antes de empezar a grabar solo aparece "
        "cuando termina (? = no se puede saber; graba antes de buffear). Competentia, Benedictum, Presens Acies, "
        "Argutus, Lauda, Reencarnação das Almas, Talismã do Guerreiro y Talismã do Mago el juego no los muestra en los demás "
        "jugadores: de esos solo se exige a quien grabó."),
    "Jogadores fora do grupo — %d grave(s), %d de atenção": ("Players outside the party — %d serious, %d warning(s)",
                                                             "Jugadores fuera del grupo — %d grave(s), %d de atención"),
    "Ninguém de fora do grupo bateu neste chefe": ("Nobody outside the party hit this boss",
                                                   "Nadie de fuera del grupo golpeó a este jefe"),
    "Buffs e debuffs de quem está fora do grupo não chegam no replay: aqui só aparecem dano, mortes, a Garra "
    "Sombria e o elemento das skills de elemento fixo.": (
        "Buffs and debuffs of players outside the party don't reach the replay: only damage, deaths, Garra "
        "Sombria and fixed-element skills show up here.",
        "Los buffs y debuffs de quien está fuera del grupo no llegan al replay: aquí solo aparecen daño, muertes, "
        "la Garra Sombria y el elemento de las skills de elemento fijo."),
    "Garra Sombria": ("Garra Sombria", "Garra Sombria"),
    " (sem Executor)": (" (no Executor)", " (sin Executor)"),
    "Mortes (%d)": ("Deaths (%d)", "Muertes (%d)"),
    "Elemento e veneno": ("Element and poison", "Elemento y veneno"),
    # --- Dedo Duro (regras) -----------------------------------------------------------
    "● grave": ("● serious", "● grave"),
    "◐ atenção": ("◐ warning", "◐ atención"),
    "○ info": ("○ info", "○ info"),
    "Neutro": ("Neutral", "Neutro"),
    "Água": ("Water", "Agua"),
    "Terra": ("Earth", "Tierra"),
    "Fogo": ("Fire", "Fuego"),
    "Vento": ("Wind", "Viento"),
    "Sagrado": ("Holy", "Sagrado"),
    "Sombrio": ("Shadow", "Sombra"),
    "Fantasma": ("Ghost", "Fantasma"),
    "Maldito": ("Undead", "Maldito"),
    "dos outros jogadores o jogo não mostra esse buff: só dá para ver em quem gravou": (
        "the game doesn't show this buff on other players: it can only be seen on the recorder",
        "el juego no muestra este buff en los demás jugadores: solo se ve en quien grabó"),
    "recarga %d s": ("cooldown %d s", "recarga %d s"),
    "%d AP": ("%d AP", "%d AP"),
    "precisa do Clímax (%s)": ("needs Clímax (%s)", "necesita el Clímax (%s)"),
    "Pólen (Florescer)": ("Pólen (Florescer)", "Pólen (Florescer)"),
    "MVP ": ("MVP ", "MVP "),
    "boneco": ("dummy", "muñeco"),
    "Todas as fases": ("All phases", "Todas las fases"),
    "Luta inteira": ("Whole fight", "Pelea completa"),
    "Clímax": ("Climax", "Clímax"),
    "Antes do clímax": ("Before the climax", "Antes del clímax"),
    "troca de fase": ("phase change", "cambio de fase"),
    "%s: recarga de %d s, usado em %s, só voltaria em %s": ("%s: %d s cooldown, used at %s, only back at %s",
                                                            "%s: recarga de %d s, usado en %s, solo volvería en %s"),
    " (depois do fim da fase)": (" (after the phase ended)", " (después del final de la fase)"),
    "sai ao morrer e custa AP demais: só conta até a 1ª morte (%s)": (
        "lost on death and costs too much AP: only counts until the 1st death (%s)",
        "se pierde al morir y cuesta demasiado AP: solo cuenta hasta la 1.ª muerte (%s)"),
    "tem que ficar o tempo todo": ("must be up all the time", "tiene que estar todo el tiempo"),
    "%s é de alvo único: quem gravou talvez não precise%s": (
        "%s is single-target: the recorder may not need it%s",
        "%s es de objetivo único: quizás quien grabó no lo necesite%s"),
    " (em quem recebe, tem que ficar o tempo todo)": (" (on whoever gets it, it must be up all the time)",
                                                      " (en quien lo recibe, tiene que estar todo el tiempo)"),
    "%s tem que ficar o tempo todo": ("%s must be up all the time", "%s tiene que estar todo el tiempo"),
    "%s dura 60 s ou menos": ("%s lasts 60 s or less", "%s dura 60 s o menos"),
    "nenhum membro do grupo recebeu em nenhuma fase (os buffs de quem está no grupo aparecem no replay, não só os "
    "de quem gravou)": (
        "no party member got it in any phase (party members' buffs show up in the replay, not only the "
        "recorder's)",
        "ningún miembro del grupo lo recibió en ninguna fase (los buffs de quien está en el grupo aparecen en el "
        "replay, no solo los de quien grabó)"),
    "não apareceu em ninguém do grupo; no começo da gravação não dá para saber (buff dado antes de gravar só "
    "aparece quando acaba)": (
        "it didn't show up on anyone in the party; at the start of the recording it can't be told (a buff given "
        "before recording only shows up when it ends)",
        "no apareció en nadie del grupo; al inicio de la grabación no se puede saber (un buff dado antes de grabar "
        "solo aparece cuando termina)"),
    "Ninguém do grupo recebeu ": ("Nobody in the party got ", "Nadie del grupo recibió "),
    "a classe que dá está no grupo, mas ": ("the class that gives it is in the party, but ",
                                            "la clase que lo da está en el grupo, pero "),
    "Sem %s depois de morrer": ("No %s after dying", "Sin %s después de morir"),
    "Faltou %s": ("Missing %s", "Faltó %s"),
    "quem dá: %s": ("given by: %s", "lo da: %s"),
    " · estava com o buff antes da 1ª morte, mas não recebeu de novo depois de ressuscitar": (
        " · had the buff before the 1st death, but didn't get it again after being resurrected",
        " · tenía el buff antes de la 1.ª muerte, pero no lo recibió de nuevo después de resucitar"),
    "da classe": ("class", "de clase"),
    "%s sumiu": ("%s vanished", "%s desapareció"),
    "estava em %s de outra fase · %s": ("was up %s of another phase · %s", "estuvo %s de otra fase · %s"),
    "%s fora do clímax": ("%s outside the climax", "%s fuera del clímax"),
    "usou na luta, mas ficou ativo em no máximo %s do clímax · %s": (
        "used in the fight, but active for at most %s of the climax · %s",
        "lo usó en la pelea, pero estuvo activo como máximo %s del clímax · %s"),
    "a fase é um monstro novo e chega sem Pólen: não foi aplicado de novo": (
        "the phase is a new monster and arrives without Pólen: it wasn't applied again",
        "la fase es un monstruo nuevo y llega sin Pólen: no se aplicó de nuevo"),
    "a fase é um monstro novo e chega sem Pólen: só foi aplicado em %s (a fase começou em %s)": (
        "the phase is a new monster and arrives without Pólen: it was only applied at %s (the phase started at %s)",
        "la fase es un monstruo nuevo y llega sin Pólen: solo se aplicó en %s (la fase empezó en %s)"),
    "%s estava com Clímax em %s do clímax da fase: dava para usar o Florescer (recarga 6 s)": (
        "%s had Clímax for %s of the phase climax: Florescer could have been used (6 s cooldown)",
        "%s tenía Clímax en %s del clímax de la fase: se podía usar Florescer (recarga 6 s)"),
    "%s morreu em %s e perdeu o Clímax — sem AP para usar de novo depois de ressuscitar": (
        "%s died at %s and lost Clímax — no AP to use it again after being resurrected",
        "%s murió en %s y perdió el Clímax — sin AP para usarlo de nuevo después de resucitar"),
    "Clímax de %s em recarga até %s": ("%s's Clímax on cooldown until %s", "Clímax de %s en recarga hasta %s"),
    "%s sem Clímax nesta fase (o Pólen só tira 100%% da resistência a fogo com Clímax nv 4)": (
        "%s without Clímax in this phase (Pólen only removes 100%% of fire resistance with Clímax lv 4)",
        "%s sin Clímax en esta fase (el Pólen solo quita el 100%% de la resistencia al fuego con Clímax nv 4)"),
    "o chefe usa Dor Máxima: tem que ficar o tempo todo": ("the boss uses Dor Máxima: it must be up all the time",
                                                           "el jefe usa Dor Máxima: tiene que estar todo el tiempo"),
    "tem que ficar o tempo todo; cada fase chega sem Pólen; o Pólen fica se o Magus morre, o Clímax não": (
        "must be up all the time; each phase arrives without Pólen; Pólen stays if the Magus dies, Clímax doesn't",
        "tiene que estar todo el tiempo; cada fase llega sin Pólen; el Pólen se queda si el Magus muere, el Clímax "
        "no"),
    "ninguém com veneno na arma": ("nobody with a poisoned weapon", "nadie con veneno en el arma"),
    "com veneno na arma: ": ("with a poisoned weapon: ", "con veneno en el arma: "),
    "Garra Sombria nunca apareceu no chefe": ("Garra Sombria never showed up on the boss",
                                              "Garra Sombria nunca apareció en el jefe"),
    "o chefe usa Dor Máxima: %d golpes refletidos (%s de dano)": (
        "the boss uses Dor Máxima: %d hits reflected (%s damage)",
        "el jefe usa Dor Máxima: %d golpes reflejados (%s de daño)"),
    "Potencializar Veneno nunca apareceu no chefe": ("Potencializar Veneno never showed up on the boss",
                                                     "Potencializar Veneno nunca apareció en el jefe"),
    "bateram com veneno na arma: %s": ("hit with a poisoned weapon: %s", "golpearon con veneno en el arma: %s"),
    "%s nunca apareceu no chefe": ("%s never showed up on the boss", "%s nunca apareció en el jefe"),
    "pode ser imunidade do chefe ou a skill não foi usada": ("the boss may be immune or the skill wasn't used",
                                                             "puede ser inmunidad del jefe o no se usó la skill"),
    "o chefe usa Dor Máxima e a Garra Sombria ficou só %s do clímax · %s": (
        "the boss uses Dor Máxima and Garra Sombria was up only %s of the climax · %s",
        "el jefe usa Dor Máxima y la Garra Sombria estuvo solo %s del clímax · %s"),
    " · no maior buraco (%s, %s): %s": (" · in the biggest gap (%s, %s): %s", " · en el hueco más grande (%s, %s): %s"),
    "no chefe só %s do clímax · quem aplica: %s": ("on the boss only %s of the climax · applied by: %s",
                                                   "en el jefe solo %s del clímax · lo aplica: %s"),
    "faltou": ("missing", "faltó"),
    "durou pouco": ("too short", "duró poco"),
    "%s %s": ("%s %s", "%s %s"),
    "Dor Máxima refletiu sem Garra Sombria": ("Dor Máxima reflected without Garra Sombria",
                                              "Dor Máxima reflejó sin Garra Sombria"),
    "%d golpes refletidos (%s de dano) com a Garra Sombria desligada": (
        "%d hits reflected (%s damage) with Garra Sombria off",
        "%d golpes reflejados (%s de daño) con la Garra Sombria apagada"),
    "em recarga (%d s)": ("on cooldown (%d s)", "en recarga (%d s)"),
    ", depois disponível por %s": (", then available for %s", ", luego disponible por %s"),
    "disponível (usou em %s)": ("available (used at %s)", "disponible (la usó en %s)"),
    "disponível? (nenhum uso visto desde o começo da gravação)": (
        "available? (no use seen since the recording started)",
        "¿disponible? (ningún uso visto desde el inicio de la grabación)"),
    "disponível (ainda não tinha usado na luta)": ("available (not used yet in the fight)",
                                                   "disponible (todavía no la había usado en la pelea)"),
    "disponível": ("available", "disponible"),
    " e ": (" and ", " y "),
    "de %s %s": ("%s's %s", "de %s %s"),
    "estava disponível": ("was available", "estaba disponible"),
    "estavam disponíveis": ("were available", "estaban disponibles"),
    "estava morto": ("was dead", "estaba muerto"),
    "estavam mortos": ("were dead", "estaban muertos"),
    "de %s %s %s": ("%s's %s %s", "de %s %s %s"),
    "estava": ("was", "estaba"),
    "estavam": ("were", "estaban"),
    "Garra Sombria ": ("Garra Sombria ", "Garra Sombria "),
    "de ": ("of ", "de "),
    "com Dor Máxima no chefe": ("with Dor Máxima on the boss", "con Dor Máxima en el jefe"),
    "no clímax": ("in the climax", "en el clímax"),
    "Garra Sombria pronta e sem usar": ("Garra Sombria ready and unused", "Garra Sombria lista y sin usar"),
    "ficou %s disponível enquanto o chefe estava sem Garra (%s); usou %d× na luta": (
        "was available for %s while the boss had no Garra (%s); used it %d× in the fight",
        "estuvo %s disponible mientras el jefe no tenía Garra (%s); la usó %d× en la pelea"),
    "não voltou": ("didn't come back", "no volvió"),
    "voltou (sem aviso de ressurreição)": ("came back (no resurrection packet)", "volvió (sin aviso de resurrección)"),
    "na hora": ("instantly", "al instante"),
    "ressuscitado": ("resurrected", "resucitado"),
    " · provável wipe": (" · likely wipe", " · probable wipe"),
    "Morreu e não voltou": ("Died and didn't come back", "Murió y no volvió"),
    "morreu em %s e ficou %s morto até o fim da luta": ("died at %s and stayed dead %s until the fight ended",
                                                        "murió en %s y estuvo %s muerto hasta el final de la pelea"),
    "Demorou para ressuscitar": ("Slow to be resurrected", "Tardó en resucitar"),
    " (%d×)": (" (%d×)", " (%d×)"),
    "ficou ": ("was ", "estuvo "),
    "%s%s morto em %s": ("%s%s dead at %s", "%s%s muerto en %s"),
    "Perdeu buffs ao morrer": ("Lost buffs on death", "Perdió buffs al morir"),
    "não voltaram em %d s: %s": ("not back within %d s: %s", "no volvieron en %d s: %s"),
    "arma de %s no Florescer": ("%s weapon during Florescer", "arma de %s durante Florescer"),
    "Sem fogo no Florescer": ("No fire during Florescer", "Sin fuego durante Florescer"),
    "%s do dano no Florescer saiu com arma de %s; o chefe estava sem resistência a fogo": (
        "%s of the damage during Florescer came from a %s weapon; the boss had no fire resistance",
        "%s del daño durante Florescer salió con arma de %s; el jefe no tenía resistencia al fuego"),
    "sem fogo visível na arma": ("no visible fire on the weapon", "sin fuego visible en el arma"),
    "Sem fogo no Florescer?": ("No fire during Florescer?", "¿Sin fuego durante Florescer?"),
    "nenhum conversor ou encantamento de fogo durante o Florescer (%s do dano dele ali usava o elemento da arma). "
    "Se a arma já é de fogo, ignore": (
        "no fire converter or endow during Florescer (%s of their damage there used the weapon element). "
        "If the weapon is already fire, ignore this",
        "ningún conversor o encantamiento de fuego durante Florescer (%s de su daño ahí usaba el elemento del "
        "arma). Si el arma ya es de fuego, ignóralo"),
    "fogo em %s do dano no Florescer": ("fire on %s of the damage during Florescer",
                                        "fuego en %s del daño durante Florescer"),
    "elemento da arma não visível em %s": ("weapon element not visible for %s", "elemento del arma no visible en %s"),
    "%s com skill de elemento fixo": ("%s with fixed-element skills", "%s con skills de elemento fijo"),
    "desvantagem: %s": ("disadvantage: %s", "desventaja: %s"),
    "Atacou com desvantagem elemental": ("Attacked at an elemental disadvantage", "Atacó con desventaja elemental"),
    "%s do dano com %s contra %s %d (%d%% do dano)": ("%s of the damage with %s against %s %d (%d%% damage)",
                                                      "%s del daño con %s contra %s %d (%d%% del daño)"),
    "arma com veneno, chefe sem Potencializar Veneno": ("poisoned weapon, boss without Potencializar Veneno",
                                                        "arma con veneno, jefe sin Potencializar Veneno"),
    "Veneno sem Potencializar Veneno": ("Poison without Potencializar Veneno", "Veneno sin Potencializar Veneno"),
    "arma com veneno em %s do clímax, mas o chefe teve Potencializar Veneno só %s · quem aplica: %s": (
        "poisoned weapon for %s of the climax, but the boss had Potencializar Veneno only %s · applied by: %s",
        "arma con veneno en %s del clímax, pero el jefe tuvo Potencializar Veneno solo %s · lo aplica: %s"),
    "chefe com Potencializar Veneno, arma sem veneno": ("boss with Potencializar Veneno, weapon without poison",
                                                        "jefe con Potencializar Veneno, arma sin veneno"),
    "Arma sem veneno": ("Weapon without poison", "Arma sin veneno"),
    "o chefe estava com Potencializar Veneno em %s do clímax e a arma com veneno só %s": (
        "the boss had Potencializar Veneno for %s of the climax and the weapon was poisoned only %s",
        "el jefe tuvo Potencializar Veneno en %s del clímax y el arma con veneno solo %s"),
    "os dois juntos em %s do clímax": ("both together for %s of the climax", "los dos juntos en %s del clímax"),
    "Florescer fraco": ("Weak Florescer", "Florescer débil"),
    "o chefe perdeu só %d%% de resistência a fogo (com Clímax nv 4 seriam 100%%)": (
        "the boss lost only %d%% fire resistance (with Clímax lv 4 it would be 100%%)",
        "el jefe perdió solo %d%% de resistencia al fuego (con Clímax nv 4 sería 100%%)"),
    "proteção": ("defense", "protección"),
    "grupo": ("party", "grupo"),
    "físico": ("physical", "físico"),
    "mágico": ("magic", "mágico"),
    "suporte": ("support", "soporte"),
    "o chefe morreu: HP = dano total": ("the boss died: HP = total damage", "el jefe murió: HP = daño total"),
    "estimado: o chefe não morreu, conta o dano feito até agora": (
        "estimated: the boss didn't die, counting the damage done so far",
        "estimado: el jefe no murió, cuenta el daño hecho hasta ahora"),
    "Clímax a partir de %s, depois dos primeiros %d%% do HP (%s)": (
        "Climax from %s, after the first %d%% of HP (%s)", "Clímax desde %s, después del primer %d%% del HP (%s)"),
    "clímax a partir de %s, depois dos primeiros %d%% do HP (%s)": (
        "climax from %s, after the first %d%% of HP (%s)", "clímax desde %s, después del primer %d%% del HP (%s)"),
    "Dedo Duro — %s · %s–%s%s": ("Snitch — %s · %s–%s%s", "Soplón — %s · %s–%s%s"),
    " · morto": (" · killed", " · muerto"),
    "Grupo:": ("Party:", "Grupo:"),
    "Grupo: nada para apontar.": ("Party: nothing to point out.", "Grupo: nada que señalar."),
    "Fora do grupo:": ("Outside the party:", "Fuera del grupo:"),
    # 1.1: Dedo Duro (Garra Sombria antes de bater, Elo Celestial)
    "Atacou antes da Garra Sombria": ("Attacked before Garra Sombria", "Atacó antes de la Garra Sombria"),
    "dano no chefe antes da Garra Sombria (limite: %s do HP, %s)": (
        "damage on the boss before Garra Sombria (limit: %s of HP, %s)",
        "daño al jefe antes de la Garra Sombria (límite: %s del HP, %s)"),
    "a Garra só chegou em %s, %s depois do começo da fase": (
        "Garra Sombria only landed at %s, %s after the phase started",
        "la Garra Sombria solo llegó en %s, %s después del inicio de la fase"),
    "Dor Máxima no chefe desde %s: esse dano volta para o grupo": (
        "Dor Máxima on the boss since %s: that damage comes back to the party",
        "Dor Máxima en el jefe desde %s: ese daño vuelve al grupo"),
    "maior golpe de %s: %s %s em %s": ("%s's biggest hit: %s %s at %s", "golpe más fuerte de %s: %s %s en %s"),
    "sai ao morrer e custa 120 AP: só conta até a 1ª morte (%s)": (
        "lost on death and costs 120 AP: only counts until the 1st death (%s)",
        "se pierde al morir y cuesta 120 AP: solo cuenta hasta la 1.ª muerte (%s)"),
    "buff do próprio Mestre Celestial: tem que ficar o tempo todo até a 1ª morte (dura até 15 min; depois de "
    "morrer não tem AP para usar de novo)": (
        "the Mestre Celestial's own buff: must be up all the time until the 1st death (lasts up to 15 min; after "
        "dying there's no AP to use it again)",
        "buff del propio Mestre Celestial: tiene que estar todo el tiempo hasta la 1.ª muerte (dura hasta 15 min; "
        "después de morir no hay AP para usarlo de nuevo)"),
    "buff do próprio Mestre Celestial: dura até 15 min, sai ao morrer e custa 120 AP": (
        "the Mestre Celestial's own buff: lasts up to 15 min, lost on death, costs 120 AP",
        "buff del propio Mestre Celestial: dura hasta 15 min, se pierde al morir y cuesta 120 AP"),
    # 1.1: DPS ativo
    "Seu DPS ativo": ("Your active DPS", "Tu DPS activo"),
    "DPS ativo": ("Active DPS", "DPS activo"),
    "só o tempo batendo: %s": ("only the time attacking: %s", "solo el tiempo atacando: %s"),
    "DPS": ("DPS", "DPS"),
    "Em combate (dano ÷ tempo da luta)": ("In combat (damage ÷ fight time)", "En combate (daño ÷ tiempo de la pelea)"),
    "Ativo (dano ÷ tempo em que cada um estava batendo)": (
        "Active (damage ÷ time each player was attacking)", "Activo (daño ÷ tiempo en que cada uno estaba atacando)"),
    "Ativo: pausas de mais de 5 s sem bater não contam (morto, esperando, correndo)": (
        "Active: pauses of more than 5 s without attacking don't count (dead, waiting, running)",
        "Activo: las pausas de más de 5 s sin atacar no cuentan (muerto, esperando, corriendo)"),
    "batendo %s": ("attacking %s", "atacando %s"),
    # 1.1: Linha do tempo
    "morreu": ("died", "murió"),
    "ressuscitou": ("resurrected", "resucitó"),
    "Dano refletido": ("Reflected damage", "Daño reflejado"),
    "Golpes fortes (≥ 0,5% do HP)": ("Strong hits (≥ 0.5% of HP)", "Golpes fuertes (≥ 0,5% del HP)"),
    "Usos da %s": ("%s uses", "Usos de %s"),
    "usou %s": ("used %s", "usó %s"),
    "Dor Máxima devolveu %s": ("Dor Máxima returned %s", "Dor Máxima devolvió %s"),
    "%d jogadores atingidos, maior: %s": ("%d players hit, biggest: %s", "%d jugadores alcanzados, mayor: %s"),
    "%s começou": ("%s started", "%s empezó"),
    "durou %s": ("lasted %s", "duró %s"),
    "sem média": ("no average", "sin promedio"),
    "média de 1 s": ("1 s average", "promedio de 1 s"),
    "média de 3 s": ("3 s average", "promedio de 3 s"),
    "média de 5 s": ("5 s average", "promedio de 5 s"),
    "HP do chefe (estimado)": ("Boss HP (estimated)", "HP del jefe (estimado)"),
    "Dano recebido pelo grupo": ("Damage taken by the party", "Daño recibido por el grupo"),
    "Eventos (só os das marcações ligadas)": ("Events (only from the markers turned on)",
                                              "Eventos (solo los de las marcas activadas)"),
    "Curvas": ("Curves", "Curvas"),
    "DPS de cada jogador": ("Each player's DPS", "DPS de cada jugador"),
    "Marcações de fase": ("Phase markers", "Marcas de fase"),
    "Fases e clímax": ("Phases and climax", "Fases y clímax"),
    " (fora do grupo)": (" (outside the party)", " (fuera del grupo)"),
    "No chefe": ("On the boss", "En el jefe"),
    "Eventos": ("Events", "Eventos"),
    "Escolha uma luta contra chefe.": ("Pick a boss fight.", "Elige una pelea contra un jefe."),
    "Luta:": ("Fight:", "Pelea:"),
    "Arraste no gráfico ou gire a roda do mouse para aproximar; duplo clique volta. Passe o mouse para ver o que "
    "acontecia em cada instante.": (
        "Drag on the chart or turn the mouse wheel to zoom in; double-click goes back. Hover to see what was "
        "happening at each moment.",
        "Arrastra en el gráfico o gira la rueda del ratón para acercar; doble clic vuelve. Pasa el ratón para ver qué "
        "pasaba en cada momento."),
    "Ver a luta toda": ("See the whole fight", "Ver toda la pelea"),
    # 1.1: HP do chefe pela dificuldade
    "Selado": ("Sealed", "Sellado"),
    "Nível 1": ("Level 1", "Nivel 1"),
    "Nível 2": ("Level 2", "Nivel 2"),
    "Nível 3": ("Level 3", "Nivel 3"),
    "Nível 4": ("Level 4", "Nivel 4"),
    "Nível 5": ("Level 5", "Nivel 5"),
    "Dificuldade:": ("Difficulty:", "Dificultad:"),
    "deduzir pelo dano": ("infer from damage", "deducir por el daño"),
    "escolhido": ("picked", "elegido"),
    "deduzido: morreu com %s de dano em %s de luta": ("inferred: died after %s damage in %s of fighting",
                                                      "deducido: murió con %s de daño en %s de pelea"),
    "deduzido: %s, %s de dano visto em %s de luta (o nível mais comum)": (
        "inferred: %s, %s damage seen in %s of fighting (the most common level)",
        "deducido: %s, %s de daño visto en %s de pelea (el nivel más común)"),
    "deduzido: %s, %s de dano visto em %s de luta (no mínimo este nível)": (
        "inferred: %s, %s damage seen in %s of fighting (at least this level)",
        "deducido: %s, %s de daño visto en %s de pelea (como mínimo este nivel)"),
    "não morreu": ("didn't die", "no murió"),
    "a gravação começou com a luta em andamento": ("the recording started with the fight underway",
                                                   "la grabación empezó con la pelea en curso"),
    "no mínimo o dano visto (a gravação começou com a luta em andamento)": (
        "at least the damage seen (the recording started with the fight underway)",
        "como mínimo el daño visto (la grabación empezó con la pelea en curso)"),
    "Alívio (redução de dano)": ("Relieve (damage reduction)", "Alivio (reducción de daño)"),
    "informado pelo servidor": ("sent by the server", "informado por el servidor"),
    "dano até morrer": ("damage until death", "daño hasta morir"),
    "da base de dados": ("from the database", "de la base de datos"),
    "no mínimo o dano visto": ("at least the damage seen", "como mínimo el daño visto"),
    "HP %s, %s — %s": ("HP %s, %s — %s", "HP %s, %s — %s"),
    "HP do chefe (%s)": ("Boss HP (%s)", "HP del jefe (%s)"),
    "%s depois do começo da %s (%s de luta)": ("%s after %s started (%s into the fight)",
                                               "%s después del inicio de la %s (%s de pelea)"),
    "%s depois do começo da %s": ("%s after %s started", "%s después del inicio de la %s"),
    "%s antes do começo da luta": ("%s before the fight started", "%s antes del inicio de la pelea"),
    "%s de luta": ("%s into the fight", "%s de pelea"),
    "Desde o começo": ("Since start", "Desde el inicio"),
    # zona de risco (fase 3 do Betelgeuse)
    "em cima do Betel": ("on top of Betel", "encima de Betel"),
    "Ficou na zona de risco das armadilhas": ("Stood in the trap danger zone", "Se quedó en la zona de riesgo de las trampas"),
    "de 1 s antes a 16 s depois de o Betel aparecer; segura é a coluna 2 ← abaixo do Betel (2 ← 1 ↓ a 2 ← 6 ↓), "
    "1 → 1 ↓ de 7,5 a 14,5 s ou fora do alcance das armadilhas (canto esquerdo da arena)": (
        "from 1 s before to 16 s after Betel appears; safe is the column 2 ← below Betel (2 ← 1 ↓ to 2 ← 6 ↓), "
        "1 → 1 ↓ from 7.5 to 14.5 s, or out of the traps' reach (left corner of the arena)",
        "de 1 s antes a 16 s después de que aparece Betel; seguro es la columna 2 ← debajo de Betel (2 ← 1 ↓ a "
        "2 ← 6 ↓), 1 → 1 ↓ de 7,5 a 14,5 s o fuera del alcance de las trampas (esquina izquierda de la arena)"),
    "%s %s (%d golpe(s))": ("%s %s (%d hit(s))", "%s %s (%d golpe(s))"),
    "Zona de risco": ("Danger zone", "Zona de riesgo"),
    "Zona de risco (sem fase 3)": ("Danger zone (no phase 3)", "Zona de riesgo (sin fase 3)"),
    "Só na fase 3 do Betelgeuse, de 1 s antes a 16 s depois de ele aparecer. Zona segura: a coluna 2 ← abaixo do "
    "Betel (de 2 ← 1 ↓ a 2 ← 6 ↓), 1 → 1 ↓ de 7,5 a 14,5 s e tudo fora do alcance das armadilhas (o canto esquerdo "
    "da arena). Atenção para quem passou 40% do tempo ou mais (e 2 s ou mais) fora dela.": (
        "Only in Betelgeuse's phase 3, from 1 s before to 16 s after it appears. Safe zone: the column 2 ← below "
        "Betel (2 ← 1 ↓ to 2 ← 6 ↓), 1 → 1 ↓ from 7.5 to 14.5 s, and anything out of the traps' reach (the left "
        "corner of the arena). Warning for whoever spent 40% of the time or more (and 2 s or more) outside it.",
        "Solo en la fase 3 de Betelgeuse, de 1 s antes a 16 s después de que aparece. Zona segura: la columna 2 ← "
        "debajo de Betel (de 2 ← 1 ↓ a 2 ← 6 ↓), 1 → 1 ↓ de 7,5 a 14,5 s y todo lo que está fuera del alcance de "
        "las trampas (la esquina izquierda de la arena). Atención para quien pasó 40% del tiempo o más (y 2 s o "
        "más) fuera de ella."),
    "Tempo olhado": ("Time checked", "Tiempo revisado"),
    "Na zona de risco": ("In the danger zone", "En la zona de riesgo"),
    "% em risco": ("% at risk", "% en riesgo"),
    "Golpes de armadilha": ("Trap hits", "Golpes de trampa"),
    "Golpes na zona de risco": ("Hits in the danger zone", "Golpes en la zona de riesgo"),
    "Onde mais ficou": ("Where they stood most", "Dónde estuvo más"),
    # assincronia entre os DPS
    "Golpes fortes fora da rajada dos outros DPS": ("Strong hits outside the other DPS's burst",
                                                    "Golpes fuertes fuera de la ráfaga de los otros DPS"),
    "golpe de %s ou mais (%s do HP) mais de %s longe de qualquer golpe forte dos outros DPS vivos": (
        "hit of %s or more (%s of HP) more than %s away from any strong hit by the other living DPS",
        "golpe de %s o más (%s del HP) a más de %s de cualquier golpe fuerte de los otros DPS vivos"),
    "%s %d×": ("%s %d×", "%s %d×"),
    "%s: %s": ("%s: %s", "%s: %s"),
    "%s (sozinho)": ("%s (alone)", "%s (solo)"),
    "%s (%s do mais perto)": ("%s (%s from the nearest)", "%s (%s del más cercano)"),
    # Cinzas Vulcânicas
    "%s (de %s)": ("%s (%s's)", "%s (de %s)"),
    "fogo dá 150%% do dano no chefe com as cinzas · %d uso(s)": (
        "fire deals 150%% damage to the boss in the ash · %d use(s)",
        "el fuego hace 150%% de daño al jefe con las cenizas · %d uso(s)"),
    "o status nunca apareceu no chefe em %d uso(s): chefe imune": (
        "the status never showed on the boss in %d use(s): boss is immune",
        "el estado nunca apareció en el jefe en %d uso(s): jefe inmune"),
    "Cinzas Vulcânicas não pegaram no chefe": ("Volcanic Ash didn't stick to the boss",
                                               "Cenizas Volcánicas no afectaron al jefe"),
    "a nuvem foi usada %d vez(es), mas o status das cinzas nunca apareceu no chefe (Garra Sombria, Pólen e Vício "
    "Mágico aparecem); chefes costumam ser imunes: o turno do homúnculo pode ir para outra skill": (
        "the cloud was used %d time(s), but the ash status never showed on the boss (Dark Claw, Pollen and Magic "
        "Poison do); bosses are usually immune: the homunculus's turn can go to another skill",
        "la nube se usó %d vez(es), pero el estado de cenizas nunca apareció en el jefe (Garra Sombría, Polen y "
        "Vicio Mágico sí aparecen); los jefes suelen ser inmunes: el turno del homúnculo puede ir a otra habilidad"),
    # linha do tempo: eventos individuais e filtros
    "ataque básico": ("basic attack", "ataque básico"),
    "Golpes dos jogadores": ("Players' hits", "Golpes de los jugadores"),
    "Skills dos jogadores": ("Players' skills", "Habilidades de los jugadores"),
    "Golpes dos monstros": ("Monsters' hits", "Golpes de los monstruos"),
    "Skills dos monstros": ("Monsters' skills", "Habilidades de los monstruos"),
    "errou %s": ("missed %s", "falló a %s"),
    "conjurou %s (%s)": ("cast %s (%s)", "conjuró %s (%s)"),
    "%s em %s": ("%s on %s", "%s a %s"),
    " (crítico)": (" (critical)", " (crítico)"),
    " em %s": (" on %s", " a %s"),
    "em %s": ("on %s", "a %s"),
    "Só na lista de eventos": ("Event list only", "Solo en la lista de eventos"),
    "Quem:": ("Who:", "Quién:"),
    "Chefe e monstros": ("Boss and monsters", "Jefe y monstruos"),
    "Só o trecho visível do gráfico": ("Only the visible part of the chart", "Solo el tramo visible del gráfico"),
    "Eventos — %d no trecho visível": ("Events — %d in the visible part", "Eventos — %d en el tramo visible"),
    "Eventos — %d": ("Events — %d", "Eventos — %d"),
    "golpe forte": ("strong hit", "golpe fuerte"),
    # dano por fase
    "Dano por fase": ("Damage per phase", "Daño por fase"),
    "%s: %s em %s (%s/s), %d jogador(es)": ("%s: %s in %s (%s/s), %d player(s)", "%s: %s en %s (%s/s), %d jugador(es)"),
    "% da luta": ("% of fight", "% de la pelea"),
    "Por fase (lutas contra chefe no recorte)": ("Per phase (boss fights in the selection)",
                                                 "Por fase (peleas contra jefes en la selección)"),
    "Por fase: nenhuma luta contra chefe no recorte": ("Per phase: no boss fight in the selection",
                                                       "Por fase: ninguna pelea contra jefe en la selección"),
    "Luta": ("Fight", "Pelea"),
    "Dano do grupo": ("Group damage", "Daño del grupo"),
    "DPS do grupo": ("Group DPS", "DPS del grupo"),
    "Dano do jogador": ("Player damage", "Daño del jugador"),
    "% do jogador": ("Player %", "% del jugador"),
    "DPS do jogador": ("Player DPS", "DPS del jugador"),
    "Total": ("Total", "Total"),
    # /where no widget
    "Onde quem grava está (mapa e coordenadas). Clique para copiar o /navi": (
        "Where the recorder is (map and coordinates). Click to copy the /navi",
        "Dónde está quien graba (mapa y coordenadas). Haz clic para copiar el /navi"),
    "Copiado: %s": ("Copied: %s", "Copiado: %s"),
    # salvar qualquer luta como teste
    "Salvar luta como teste…": ("Save fight as test…", "Guardar pelea como prueba…"),
    "Salvar luta como teste": ("Save fight as test", "Guardar pelea como prueba"),
    "Gravado por %s · o equipamento salvo é o dessa pessoa": ("Recorded by %s · the saved equipment is theirs",
                                                            "Grabado por %s · el equipo guardado es el de esa persona"),
    "Rótulo:": ("Label:", "Etiqueta:"),
    "ex.: com Coroa +12, sem Impositio": ("e.g. with +12 Crown, no Impositio", "ej.: con Corona +12, sin Impositio"),
    "Cancelar": ("Cancel", "Cancelar"),
    "Salvar": ("Save", "Guardar"),
    "%d teste(s). Os encontros contra bonecos de treino são salvos sozinhos; qualquer outra luta (inclusive de replays "
    "de outras pessoas) dá para salvar no botão. Ctrl + clique escolhe dois para comparar.": (
        "%d test(s). Fights against training dummies are saved on their own; any other fight (including from other "
        "people's replays) can be saved with the button. Ctrl + click picks two to compare.",
        "%d prueba(s). Las peleas contra muñecos de entrenamiento se guardan solas; cualquier otra pelea (incluso de "
        "replays de otras personas) se puede guardar con el botón. Ctrl + clic elige dos para comparar."),
    # drops
    "Drops": ("Drops", "Drops"),
    "Itens que caíram": ("Items dropped", "Objetos que cayeron"),
    "Pegos por você": ("Picked by you", "Recogidos por ti"),
    "Pegos por outros": ("Picked by others", "Recogidos por otros"),
    "Prêmios de MVP": ("MVP rewards", "Premios de MVP"),
    "Itens diferentes": ("Different items", "Objetos distintos"),
    "Itens que caíram de monstros no recorte. \"Pego por\" vem da ação de pegar do jogo; quando ela não aparece, "
    "vale o item que entrou na bolsa de quem grava logo depois de sumir do chão. A experiência ganha não fica gravada "
    "no replay (só o total no começo da gravação), então não dá para mostrar XP.": (
        "Items monsters dropped in the selection. \"Picked by\" comes from the game's pick-up action; when it isn't "
        "there, an item that entered the recorder's bag right after leaving the ground counts. Experience gained isn't "
        "saved in the replay (only the total when recording starts), so XP can't be shown.",
        "Objetos que soltaron los monstruos en la selección. \"Recogido por\" viene de la acción de recoger del juego; "
        "cuando no aparece, cuenta el objeto que entró en la bolsa de quien graba justo después de salir del suelo. La "
        "experiencia ganada no queda grabada en el replay (solo el total al comenzar la grabación), así que no se "
        "puede mostrar la XP."),
    "Por item": ("By item", "Por objeto"),
    "Item": ("Item", "Objeto"),
    "Caíram": ("Dropped", "Cayeron"),
    "Você pegou": ("You picked", "Recogiste"),
    "MVP": ("MVP", "MVP"),
    "Cada drop": ("Each drop", "Cada drop"),
    "Qtd.": ("Qty.", "Cant."),
    "Monstro": ("Monster", "Monstruo"),
    "Onde": ("Where", "Dónde"),
    "Destino": ("Outcome", "Destino"),
    "pego por você": ("picked by you", "recogido por ti"),
    "pego por %s": ("picked by %s", "recogido por %s"),
    "sumiu %s depois": ("gone %s later", "desapareció %s después"),
    "ainda no chão": ("still on the ground", "todavía en el suelo"),
    "prêmio de MVP": ("MVP reward", "premio de MVP"),
    "na sua bolsa": ("in your bag", "en tu bolsa"),
    "Itens que caíram e quantos você pegou": ("Items dropped and how many you picked",
                                             "Objetos que cayeron y cuántos recogiste"),
    "você pegou %d": ("you picked %d", "recogiste %d"),
    "ninguém pegou ainda": ("nobody picked yet", "nadie lo recogió aún"),
    "Nenhum drop neste recorte.": ("No drops in this selection.", "Ningún drop en esta selección."),
    "Os itens que caírem de monstros aparecem aqui.": ("Items dropped by monsters show up here.",
                                                       "Los objetos que suelten los monstruos aparecen aquí."),
    # buffs e debuffs: quanto cada efeito rendeu
    "Buffs e Debuffs": ("Buffs and Debuffs", "Buffs y Debuffs"),
    "Rendeu = quanto o dano cairia sem o efeito, pela fórmula de cada um (rAthena e textos do jogo), golpe a golpe e "
    "só onde ele vale (fogo, físico, corpo a corpo...). É estimativa: os que não mudam o dano direto (Bênção, "
    "Agilidade...) aparecem só com o tempo ativo.": (
        "Gain = how much damage would drop without the effect, by each one's formula (rAthena and the game's texts), "
        "hit by hit and only where it applies (fire, physical, melee...). It's an estimate: the ones that don't change "
        "damage directly (Blessing, Agility...) only show their active time.",
        "Rindió = cuánto bajaría el daño sin el efecto, según la fórmula de cada uno (rAthena y textos del juego), "
        "golpe a golpe y solo donde aplica (fuego, físico, cuerpo a cuerpo...). Es una estimación: los que no cambian "
        "el daño directo (Bendición, Agilidad...) solo muestran el tiempo activo."),
    "Rendeu": ("Gain", "Rindió"),
    "Ativo": ("Active", "Activo"),
    "Como conta": ("How it counts", "Cómo cuenta"),
    "Debuffs no chefe — escolha uma luta contra chefe": ("Debuffs on the boss — pick a boss fight",
                                                         "Debuffs en el jefe — elige una pelea contra jefe"),
    "Debuffs no chefe — %s de dano olhado": ("Debuffs on the boss — %s of damage checked",
                                             "Debuffs en el jefe — %s de daño revisado"),
    "Buffs de %s — %% do tempo em combate, vivo (%s)": ("%s's buffs — %% of time in combat, alive (%s)",
                                                       "Buffs de %s — %% del tiempo en combate, vivo (%s)"),
    "Nenhum efeito com dano estimado nesta luta (ou nenhuma luta contra chefe no recorte).": (
        "No effect with estimated damage in this fight (or no boss fight in the selection).",
        "Ningún efecto con daño estimado en esta pelea (o ninguna pelea contra jefe en la selección)."),
    "%s do dano · %s · ativo %s": ("%s of damage · %s · active %s", "%s del daño · %s · activo %s"),
    "sem estimativa de dano": ("no damage estimate", "sin estimación de daño"),
    "+50% em todo o dano (todas as propriedades)": ("+50% to all damage (every element)",
                                                   "+50% a todo el daño (todas las propiedades)"),
    "+100% no dano de fogo (resistência a fogo −100%)": ("+100% fire damage (fire resistance −100%)",
                                                        "+100% al daño de fuego (resistencia a fuego −100%)"),
    "+100% no dano de terra": ("+100% earth damage", "+100% al daño de tierra"),
    "+50% no dano de fogo (iRO Wiki); chefes costumam ser imunes": (
        "+50% fire damage (iRO Wiki); bosses are usually immune",
        "+50% al daño de fuego (iRO Wiki); los jefes suelen ser inmunes"),
    "+30% por nível no dano físico corpo a corpo (metade em chefe)": (
        "+30% per level to physical melee damage (half on bosses)",
        "+30% por nivel al daño físico cuerpo a cuerpo (la mitad en jefes)"),
    "+50% no dano físico": ("+50% physical damage", "+50% al daño físico"),
    "+5% no dano físico de longe em chefe (+10% nos outros)": (
        "+5% ranged physical damage on bosses (+10% on others)",
        "+5% al daño físico a distancia en jefes (+10% en los demás)"),
    "+5% por nível no dano físico": ("+5% per level to physical damage", "+5% por nivel al daño físico"),
    "dobra o 1º golpe depois de aplicada": ("doubles the 1st hit after it's applied",
                                            "duplica el 1er golpe después de aplicarla"),
    "usada, mas o status nunca apareceu no chefe: imune": ("used, but the status never showed on the boss: immune",
                                                           "usada, pero el estado nunca apareció en el jefe: inmune"),
    # aba Equipamento: lista do que quem gravou vestia e o visual montado com os sprites do jogo
    "Momento:": ("Moment:", "Momento:"),
    "Início da gravação": ("Start of the recording", "Inicio de la grabación"),
    "%s · trocou %s": ("%s · changed %s", "%s · cambió %s"),
    "Equipamento de %s": ("%s's equipment", "Equipo de %s"),
    "quem gravou": ("the recorder", "quien grabó"),
    "Equipamento — o replay não trouxe a lista de itens de quem gravou": (
        "Equipment — the replay didn't include the recorder's item list",
        "Equipo — el replay no trajo la lista de ítems de quien grabó"),
    "Cabeça:": ("Head:", "Cabeza:"),
    "Parado": ("Standing", "Quieto"),
    "Andando": ("Walking", "Caminando"),
    "Sentado": ("Sitting", "Sentado"),
    "Em guarda": ("Ready", "En guardia"),
    "Atacando": ("Attacking", "Atacando"),
    "Conjurando": ("Casting", "Conjurando"),
    "Levando dano": ("Taking damage", "Recibiendo daño"),
    "Caído": ("Down", "Caído"),
    "Frente": ("Front", "Frente"),
    "Esquerda": ("Left", "Izquierda"),
    "Direita": ("Right", "Derecha"),
    "Carregando os sprites do jogo…": ("Loading the game's sprites…", "Cargando los sprites del juego…"),
    "Não deu para ler o data.grf do jogo (%s).": ("Couldn't read the game's data.grf (%s).",
                                                  "No se pudo leer el data.grf del juego (%s)."),
    "Jogo não encontrado: o visual é montado com os sprites do data.grf da instalação.": (
        "Game not found: the look is built from the installation's data.grf sprites.",
        "Juego no encontrado: el aspecto se arma con los sprites del data.grf de la instalación."),
    "Sem sprite para esta classe.": ("No sprite for this class.", "Sin sprite para esta clase."),
    "cabelo %d, cor %d · roupa cor %d": ("hair %d, color %d · outfit color %d", "pelo %d, color %d · ropa color %d"),
    "direção %s": ("facing %s", "dirección %s"),
    "sem sprite no jogo: %s": ("no sprite in the game: %s", "sin sprite en el juego: %s"),
    "corpo": ("body", "cuerpo"),
    "cabeça": ("head", "cabeza"),
    "chapéu de baixo": ("lower headgear", "casco inferior"),
    "chapéu do meio": ("middle headgear", "casco medio"),
    "chapéu de cima": ("upper headgear", "casco superior"),
    "capa": ("garment", "capa"),
    # XP: nível no início da gravação e XP exata até a próxima gravação
    "Drops e XP": ("Drops and XP", "Drops y XP"),
    "Nível no início": ("Level at start", "Nivel al inicio"),
    "XP até a próxima gravação": ("XP until the next recording", "XP hasta la próxima grabación"),
    "sem gravação depois desta": ("no recording after this one", "sin grabación después de esta"),
    "até %02d/%02d %02d:%02d": ("until %02d/%02d %02d:%02d", "hasta %02d/%02d %02d:%02d"),
    "+%d níveis": ("+%d levels", "+%d niveles"),
    "Nível %d": ("Level %d", "Nivel %d"),
    "+%s XP até a próx. gravação": ("+%s XP until next recording", "+%s XP hasta la próx. grabación"),
    "XP no início": ("XP at start", "XP al inicio"),
    "Itens que caíram de monstros no recorte. \"Pego por\" vem da ação de pegar do jogo; quando ela não aparece, vale "
    "o item que entrou na bolsa de quem grava logo depois de sumir do chão. A XP ganha não fica no replay: o jogo "
    "guarda só a XP total no início de cada gravação. Por isso a XP exata vai do início desta gravação ao início da "
    "próxima do mesmo personagem (na mesma pasta), incluindo o que você fez entre as duas.": (
        "Items that dropped from monsters in the selection. \"Picked by\" comes from the game's pick-up action; when "
        "it's missing, it's the item that entered the recorder's bag right after leaving the ground. XP gained isn't "
        "in the replay: the game only stores the total XP at the start of each recording. So the exact XP goes from "
        "the start of this recording to the start of the same character's next one (same folder), including whatever "
        "you did in between.",
        "Ítems que cayeron de monstruos en la selección. \"Recogido por\" viene de la acción de recoger del juego; "
        "cuando no aparece, vale el ítem que entró en la bolsa de quien graba justo después de salir del suelo. La XP "
        "ganada no queda en el replay: el juego guarda solo la XP total al inicio de cada grabación. Por eso la XP "
        "exacta va del inicio de esta grabación al inicio de la próxima del mismo personaje (misma carpeta), "
        "incluyendo lo que hiciste entre las dos."),
    "Efeito": ("Effect", "Efecto"),
    # drops separados por destino e XP estimada (widget e análise)
    "XP": ("XP", "XP"),
    "Itens que você pegou": ("Items you picked up", "Ítems que recogiste"),
    "XP estimada dos seus abates e seu nível": ("Estimated XP from your kills and your level",
                                                "XP estimada de tus muertes y tu nivel"),
    "Você não pegou nenhum item aqui.": ("You didn't pick up any item here.", "No recogiste ningún ítem aquí."),
    "O que caiu no chão e o que outros pegaram fica na análise (aba Drops).": (
        "What stayed on the ground or others picked up is in the analysis (Drops tab).",
        "Lo que quedó en el suelo o recogieron otros está en el análisis (pestaña Drops)."),
    "×%s calibrado": ("×%s calibrated", "×%s calibrado"),
    "×%s (bônus +%d%%)": ("×%s (bonus +%d%%)", "×%s (bono +%d%%)"),
    "sem bônus (calibre na análise)": ("no bonus (calibrate in the analysis)", "sin bono (calibra en el análisis)"),
    "sem bônus": ("no bonus", "sin bono"),
    "XP estimada": ("Estimated XP", "XP estimada"),
    "XP por hora": ("XP per hour", "XP por hora"),
    "no início da gravação": ("at the start of the recording", "al inicio de la grabación"),
    "XP real até a próxima gravação": ("Real XP until the next recording", "XP real hasta la próxima grabación"),
    "%d sem XP conhecida": ("%d with unknown XP", "%d sin XP conocida"),
    "Pegos por outros jogadores": ("Picked up by other players", "Recogidos por otros jugadores"),
    "Pegos por outros jogadores — %d": ("Picked up by other players — %d", "Recogidos por otros jugadores — %d"),
    "Ficaram no chão": ("Left on the ground", "Quedaron en el suelo"),
    "Ficaram no chão — %d": ("Left on the ground — %d", "Quedaron en el suelo — %d"),
    "Você pegou — %d": ("You picked up — %d", "Recogiste — %d"),
    "De onde": ("From", "De dónde"),
    "Quem pegou": ("Picked up by", "Quién recogió"),
    "Por monstro": ("Per monster", "Por monstruo"),
    "XP estimada no recorte": ("Estimated XP in selection", "XP estimada en la selección"),
    "Fator de bônus": ("Bonus factor", "Factor de bono"),
    "Bônus de XP somado (%):": ("Total XP bonus (%):", "Bono de XP sumado (%):"),
    "Usar": ("Use", "Usar"),
    "Esquecer calibração": ("Forget calibration", "Olvidar calibración"),
    "calibrado com %s": ("calibrated with %s", "calibrado con %s"),
    "calibrado em %s": ("calibrated on %s", "calibrado el %s"),
    "bônus informado: +%g%%": ("bonus entered: +%g%%", "bono informado: +%g%%"),
    "desconhecida": ("unknown", "desconocida"),
    "Nível": ("Level", "Nivel"),
    "Penalidade": ("Penalty", "Penalización"),
    "Por abate": ("Per kill", "Por muerte"),
    "Itens que caíram de monstros no recorte. \"Pego por\" vem da ação de pegar do jogo; quando ela não aparece, vale "
    "o item que entrou na bolsa de quem grava logo depois de sumir do chão.": (
        "Items that dropped from monsters in the selection. \"Picked up by\" comes from the game's pick-up action; "
        "when it's missing, it's the item that entered the recorder's bag right after leaving the ground.",
        "Ítems que cayeron de monstruos en la selección. \"Recogido por\" viene de la acción de recoger del juego; "
        "cuando no aparece, vale el ítem que entró en la bolsa de quien graba justo después de salir del suelo."),
    "O replay não grava a XP ganha: só a XP total no início de cada gravação. A estimativa soma a XP de cada monstro "
    "que você ajudou a matar (rAthena e Divine Pride), com a penalidade de nível e a sua parte do dano, vezes o fator "
    "de bônus (servidor, VIP, manuais, equipamentos...). O replay só mostra que um bônus está ativo, não quanto ele "
    "dá: o fator é calibrado sozinho quando uma gravação começa logo depois de outra do mesmo personagem (a XP exata "
    "entre as duas ÷ a XP estimada). Sem calibração, vale o bônus que você informar (os bônus de XP somam: 100% do "
    "servidor + 20% do VIP + 50% do manual = 170%).": (
        "The replay doesn't store XP gained: only the total XP at the start of each recording. The estimate adds up "
        "the XP of each monster you helped kill (rAthena and Divine Pride), with the level penalty and your share of "
        "the damage, times the bonus factor (server, VIP, manuals, equipment...). The replay only shows that a bonus "
        "is active, not how much it gives: the factor calibrates itself when a recording starts right after another "
        "one of the same character (the exact XP between them ÷ the estimated XP). Without calibration, the bonus you "
        "enter is used (XP bonuses add up: 100% server + 20% VIP + 50% manual = 170%).",
        "El replay no graba la XP ganada: solo la XP total al inicio de cada grabación. La estimación suma la XP de "
        "cada monstruo que ayudaste a matar (rAthena y Divine Pride), con la penalización de nivel y tu parte del "
        "daño, por el factor de bono (servidor, VIP, manuales, equipos...). El replay solo muestra que un bono está "
        "activo, no cuánto da: el factor se calibra solo cuando una grabación empieza justo después de otra del mismo "
        "personaje (la XP exacta entre las dos ÷ la XP estimada). Sin calibración, vale el bono que informes (los "
        "bonos de XP se suman: 100% del servidor + 20% del VIP + 50% del manual = 170%)."),
    # XP: lista de bônus, XP por minuto e gráfico
    "Bônus de XP": ("XP bonuses", "Bonos de XP"),
    "XP ao longo do tempo": ("XP over time", "XP a lo largo del tiempo"),
    "Pela lista abaixo": ("From the list below", "Según la lista de abajo"),
    "Medido nas gravações": ("Measured from recordings", "Medido en las grabaciones"),
    "Valor fixo (%):": ("Fixed value (%):", "Valor fijo (%):"),
    "recorte curto demais": ("selection too short", "selección demasiado corta"),
    "medido em %s": ("measured on %s", "medido el %s"),
    "pela lista de bônus": ("from the bonus list", "según la lista de bonos"),
    "marque se valia": ("tick it if it applied",
                        "márcalo si aplicaba"),
    "Pela lista: ×%s": ("From the list: ×%s", "Según la lista: ×%s"),
    "/min": ("/min", "/min"),
    "total": ("total", "total"),
    "XP por minuto": ("XP per minute", "XP por minuto"),
    "Manual usado:": ("Manual used:", "Manual usado:"),
    "valor fixo: +%g%%": ("fixed value: +%g%%", "valor fijo: +%g%%"),
    "não apareceu nesta gravação": ("didn't show in this recording", "no apareció en esta grabación"),
    "ainda sem duas gravações seguidas": ("no back-to-back recordings yet", "todavía sin dos grabaciones seguidas"),
    "medido: ×%s (%s%% da lista)": ("measured: ×%s (%s%% vs. the list)", "medido: ×%s (%s%% respecto a la lista)"),
    "Nenhum abate com XP conhecida no recorte.": ("No kill with known XP in the selection.",
                                                  "Ninguna muerte con XP conocida en la selección."),
    "do nível · %s/min": ("of the level · %s/min", "del nivel · %s/min"),
    "detectado (%s da gravação)": ("detected (%s of the recording)", "detectado (%s de la grabación)"),
    "×%s (%s)": ("×%s (%s)", "×%s (%s)"),
    "Esquecer": ("Forget", "Olvidar"),
    "×%s pela lista": ("×%s from list", "×%s según lista"),
    "×%s medido": ("×%s measured", "×%s medido"),
    "×%s fixo": ("×%s fixed", "×%s fijo"),
    "%s/h": ("%s/h", "%s/h"),
    "Evento do servidor": ("Server event", "Evento del servidor"),
    "VIP (Bônus de EXP II, 30 dias)": ("VIP (EXP Bonus II, 30 days)", "VIP (Bono de EXP II, 30 días)"),
    "Cetro do Coração Lunar (Bônus de EXP, 24 h)": ("Lunar Heart Scepter (EXP Bonus, 24 h)",
                                                    "Cetro del Corazón Lunar (Bono de EXP, 24 h)"),
    "Kafra Buff / Manual Kafra (7 dias)": ("Kafra Buff / Kafra Manual (7 days)", "Kafra Buff / Manual Kafra (7 días)"),
    "Manual de combate (consumível)": ("Battle manual (consumable)", "Manual de combate (consumible)"),
    "Banquete de Njord": ("Njord's Feast", "Banquete de Njord"),
    "Milagre Solar, Lunar e Estelar (multiplica os outros bônus)": (
        "Miracle of the Sun, Moon and Stars (multiplies the other bonuses)",
        "Milagro Solar, Lunar y Estelar (multiplica los otros bonos)"),
    "%s no replay": ("%s in the replay", "%s en el replay"),
    "Outros (equipamentos, cartas, alvos do ódio...)": ("Others (equipment, cards, hatred targets...)",
                                                        "Otros (equipos, cartas, objetivos del odio...)"),
    "Manual de Combate": ("Field Manual", "Manual de Combate"),
    "Manual de Combate com Chiclete": ("Field x Gum Manual", "Manual de Combate con Chicle"),
    "Manual de Campo Avançado": ("Advanced Field Manual", "Manual de Campo Avanzado"),
    "Enciclopédia de Combate": ("Battle Tome", "Enciclopedia de Combate"),
    "Manual de Combate HE": ("HE Battle Manual", "Manual de Combate HE"),
    "Manual de Combate x3": ("Battle Manual X3", "Manual de Combate x3"),
    "O replay não grava a XP ganha: só a XP total no início de cada gravação. A estimativa soma a XP de cada monstro "
    "que você ajudou a matar (rAthena e Divine Pride), com a penalidade de nível e a sua parte do dano, vezes os "
    "bônus. Os bônus de XP somam entre si, e o Milagre multiplica o total (com +100%, dobra); os manuais e outros "
    "consumíveis competem entre si (vale o maior). O replay mostra quando VIP, Cetro, Kafra Buff, manual, Banquete de "
    "Njord e Milagre estão ativos, mas não o evento do servidor: marque-o. \"Medido\" usa a XP exata entre duas "
    "gravações seguidas do mesmo personagem.": (
        "The replay doesn't store XP gained: only the total XP at the start of each recording. The estimate adds up "
        "the XP of each monster you helped kill (rAthena and Divine Pride), with the level penalty and your share of "
        "the damage, times the bonuses. XP bonuses add up, and the Miracle multiplies the total (+100% doubles it); "
        "manuals and other consumables compete (the highest one counts). The replay shows when VIP, Scepter, Kafra "
        "Buff, a manual, Njord's Feast and the Miracle are active, but not the server event: tick it. \"Measured\" "
        "uses the exact XP between two back-to-back recordings of the same character.",
        "El replay no graba la XP ganada: solo la XP total al inicio de cada grabación. La estimación suma la XP de "
        "cada monstruo que ayudaste a matar (rAthena y Divine Pride), con la penalización de nivel y tu parte del "
        "daño, por los bonos. Los bonos de XP se suman, y el Milagro multiplica el total (con +100%, lo duplica); "
        "los manuales y otros consumibles compiten entre sí (vale el mayor). El replay muestra cuándo están activos "
        "VIP, Cetro, Kafra Buff, un manual, el Banquete de Njord y el Milagro, pero no el evento del servidor: "
        "márcalo. \"Medido\" usa la XP exacta entre dos grabaciones seguidas del mismo personaje."),
    # Milagre Solar, Lunar e Estelar e bônus de XP dos itens
    "auto": ("auto", "auto"),
    "lendo os itens do jogo…": ("reading the game's items…", "leyendo los ítems del juego…"),
    "nenhum item vestido dá XP": ("no worn item gives XP", "ningún ítem equipado da XP"),
    "+%d%%: %s": ("+%d%%: %s", "+%d%%: %s"),
    "★ MILAGRE ★": ("★ MIRACLE ★", "★ MILAGRO ★"),
    "todos os monstros são alvos estelares por 1 hora": ("every monster is a star target for 1 hour",
                                                         "todos los monstruos son objetivos estelares por 1 hora"),
    "Festejar o Milagre Solar, Lunar e Estelar (Mestre Taekwon)": (
        "Celebrate the Miracle of the Sun, Moon and Stars (Star Gladiator)",
        "Festejar el Milagro Solar, Lunar y Estelar (Maestro Taekwon)"),
    "★ Milagre · %d min": ("★ Miracle · %d min", "★ Milagro · %d min"),
    "Milagre Solar, Lunar e Estelar": ("Miracle of the Sun, Moon and Stars", "Milagro Solar, Lunar y Estelar"),
    "Todos os monstros viram alvos estelares por 1 hora (+XP com a Bênção Estelar)": (
        "Every monster becomes a star target for 1 hour (+XP with Blessing of the Stars)",
        "Todos los monstruos se vuelven objetivos estelares por 1 hora (+XP con la Bendición Estelar)"),
    "★ MILAGRE! Todos os monstros viraram alvos estelares por 1 hora": (
        "★ MIRACLE! Every monster is now a star target for 1 hour",
        "★ ¡MILAGRO! Todos los monstruos son objetivos estelares por 1 hora"),
    "Equipamentos, visuais e cartas (texto dos itens)": ("Equipment, costumes and cards (item texts)",
                                                         "Equipos, visuales y cartas (texto de los ítems)"),
    "Tocar um som no Milagre": ("Play a sound on the Miracle", "Tocar un sonido en el Milagro"),
    "Fase:": ("Phase:", "Fase:"),
    "Jogadores marcados": ("Ticked players", "Jugadores marcados"),
    "Volume do som do Milagre": ("Miracle sound volume", "Volumen del sonido del Milagro"),
    "Tocar o som agora": ("Play the sound now", "Tocar el sonido ahora"),
    "★ MILAGRE de novo! Mais 1 hora de alvos estelares": ("★ MIRACLE again! One more hour of star targets",
                                                           "★ ¡MILAGRO otra vez! Una hora más de objetivos estelares"),
    "Bônus de evento dos itens ([Durante o Evento])": ("Item event bonuses ([Durante o Evento])",
                                                       "Bonos de evento de los ítems ([Durante o Evento])"),
    "+%d%% se o evento dos itens ainda vale: %s": ("+%d%% if the items' event still runs: %s",
                                                  "+%d%% si el evento de los ítems sigue: %s"),
    "nenhum item vestido tem bônus de evento": ("no worn item has an event bonus", "ningún ítem equipado tiene bono de evento"),
    "XP nesta luta": ("XP in this fight", "XP en esta pelea"),
    "★ Milagre? · %d min (a confirmar)": ("★ Miracle? · %d min (unconfirmed)", "★ ¿Milagro? · %d min (por confirmar)"),
    "detectado (%s); a confirmar depois de morte ou troca de mapa": (
        "detected (%s); unconfirmed after a death or map change",
        "detectado (%s); por confirmar después de morir o cambiar de mapa"),
    "Contar · Bônus": ("Count · Bonus", "Contar · Bono"),
    "Nesta gravação": ("In this recording", "En esta grabación"),
    "ativo em %s da gravação": ("active for %s of the recording", "activo en %s de la grabación"),
    "não estava ativo": ("wasn't active", "no estaba activo"),
    "Até o próximo nível": ("Time to next level", "Hasta el próximo nivel"),
    "já subiu": ("already up", "ya subió"),
    "faltam %s XP": ("%s XP to go", "faltan %s XP"),
    "sem ritmo de XP no recorte": ("no XP pace in the selection", "sin ritmo de XP en la selección"),
    "pela XP estimada": ("by the estimated XP", "según la XP estimada"),
    "%d min": ("%d min", "%d min"),
    "%d h %02d min": ("%d h %02d min", "%d h %02d min"),
    "%d dias %d h": ("%d days %d h", "%d días %d h"),
    # --- 1.3.0: drops ocultos e coloridos, faixa fixa, comparar XP, som da União, linha do tempo -----------
    "minuto %d: %s · total %s": ("minute %d: %s · total %s", "minuto %d: %s · total %s"),
    "Escolher cor…": ("Pick a color…", "Elegir color…"),
    "Sem cor": ("No color", "Sin color"),
    "Cor padrão": ("Default color", "Color predeterminado"),
    "Cores padrão": ("Default colors", "Colores predeterminados"),
    "Ocultar até fechar o programa": ("Hide until the program closes", "Ocultar hasta cerrar el programa"),
    "Ocultar sempre": ("Always hide", "Ocultar siempre"),
    "Comparar com outra gravação": ("Compare with another recording", "Comparar con otra grabación"),
    "%s por minuto": ("%s per minute", "%s por minuto"),
    "Marque os itens cujo evento ainda está valendo.": ("Tick the items whose event is still running.",
                                                        "Marca los objetos cuyo evento sigue activo."),
    "Duração": ("Duration", "Duración"),
    "Abates por minuto": ("Kills per minute", "Muertes por minuto"),
    "XP acumulada": ("Total XP", "XP acumulada"),
    "Itens que caíram de monstros no recorte. \"Pego por\" vem da ação de pegar do jogo; quando ela não aparece, "
    "vale o item que entrou na bolsa de quem grava logo depois de sumir do chão. Botão direito num item: favoritar, "
    "fixar no widget ou ocultar.": (
        "Items that dropped from monsters in the range. \"Picked by\" comes from the game's pick-up action; when it "
        "is missing, the item that entered the recorder's bag right after leaving the ground counts. Right-click an "
        "item: favorite, pin to the widget or hide.",
        "Objetos que soltaron los monstruos en el recorte. \"Recogido por\" viene de la acción de recoger del "
        "juego; cuando no aparece, cuenta el objeto que entró en la bolsa de quien graba justo después de "
        "desaparecer del suelo. Clic derecho en un objeto: favorito, fijar en el widget u ocultar."),
    "Cores (clique para trocar):": ("Colors (click to change):", "Colores (clic para cambiar):"),
    "Tirar dos favoritos": ("Remove from favorites", "Quitar de favoritos"),
    "Favoritar (fica no topo)": ("Favorite (stays on top)", "Favorito (queda arriba)"),
    "Desafixar do widget": ("Unpin from the widget", "Desfijar del widget"),
    "Fixar no widget": ("Pin to the widget", "Fijar en el widget"),
    "Itens ocultos": ("Hidden items", "Objetos ocultos"),
    "Nenhum item oculto": ("No hidden items", "Ningún objeto oculto"),
    "Itens ocultos (%d) ▾": ("Hidden items (%d) ▾", "Objetos ocultos (%d) ▾"),
    "Gravação:": ("Recording:", "Grabación:"),
    "Esta gravação": ("This recording", "Esta grabación"),
    "A outra": ("The other", "La otra"),
    "Diferença": ("Difference", "Diferencia"),
    "As duas usam a mesma lista de bônus. A outra gravação é sempre inteira.": (
        "Both use the same bonus list. The other recording is always whole.",
        "Las dos usan la misma lista de bonos. La otra grabación siempre es completa."),
    "do nível · %s XP": ("of the level · %s XP", "del nivel · %s XP"),
    "nenhuma gravação anterior deste personagem na pasta": ("no earlier recording of this character in the folder",
                                                            "ninguna grabación anterior de este personaje en la carpeta"),
    "lendo a gravação…": ("reading the recording…", "leyendo la grabación…"),
    "não consegui ler essa gravação": ("couldn't read that recording", "no pude leer esa grabación"),
    "nível %s · %s": ("level %s · %s", "nivel %s · %s"),
    "Itens ▾": ("Items ▾", "Objetos ▾"),
    "do nível · %s/h": ("of the level · %s/h", "del nivel · %s/h"),
    "nenhum item de evento marcado (botão Itens)": ("no event item ticked (Items button)",
                                                    "ningún objeto de evento marcado (botón Objetos)"),
    "+%d%% se o evento ainda vale: %s": ("+%d%% if the event still runs: %s", "+%d%% si el evento sigue: %s"),
    "(%d de %d itens)": ("(%d of %d items)", "(%d de %d objetos)"),
    "Informação fixada · botão direito para desafixar": ("Pinned info · right-click to unpin",
                                                         "Información fijada · clic derecho para desfijar"),
    "Botão direito: fixar no widget, ocultar...": ("Right-click: pin to the widget, hide...",
                                                   "Clic derecho: fijar en el widget, ocultar..."),
    "XP/min": ("XP/min", "XP/min"),
    "XP/h": ("XP/h", "XP/h"),
    "Próx. nível": ("Next level", "Próx. nivel"),
    "Clique: favorito · botão direito: fixar ou ocultar": ("Click: favorite · right-click: pin or hide",
                                                           "Clic: favorito · clic derecho: fijar u ocultar"),
    "%s/min": ("%s/min", "%s/min"),
    "sempre": ("always", "siempre"),
    "até fechar o programa": ("until the program closes", "hasta cerrar el programa"),
    "Mostrar todos os itens ocultos": ("Show all hidden items", "Mostrar todos los objetos ocultos"),
    "Volume do Milagre": ("Miracle volume", "Volumen del Milagro"),
    "Tocar um som com HP baixo na União": ("Play a sound on low HP with União", "Tocar un sonido con HP bajo en União"),
    "Volume da União": ("União volume", "Volumen de União"),
    "Os sons só tocam com o aviso do Milagre ou da União ligado.": (
        "Sounds only play with the Miracle or União alert on.",
        "Los sonidos solo suenan con el aviso del Milagro o de União activado."),
    "Todas as opções": ("All options", "Todas las opciones"),
    "Sons": ("Sounds", "Sonidos"),
    "Faixa fixa": ("Pinned bar", "Barra fija"),
    "%d sem XP": ("%d without XP", "%d sin XP"),
    "Até %d. Também dá para fixar com o botão direito numa linha das abas XP e Drops.": (
        "Up to %d. You can also pin with a right-click on a row of the XP and Drops tabs.",
        "Hasta %d. También se puede fijar con clic derecho en una fila de las pestañas XP y Drops."),
    "Desafixar tudo": ("Unpin all", "Desfijar todo"),
    "Desafixar": ("Unpin", "Desfijar"),
    "Drops ocultos": ("Hidden drops", "Drops ocultos"),
    "Mostrar de novo: %s (%s)": ("Show again: %s (%s)", "Mostrar de nuevo: %s (%s)"),
    "Drop: %s": ("Drop: %s", "Drop: %s"),
    "faltam %s": ("%s to go", "faltan %s"),
    "%d itens ocultos: botão direito › Itens ocultos": ("%d hidden items: right-click › Hidden items",
                                                        "%d objetos ocultos: clic derecho › Objetos ocultos"),
    "Dano dos jogadores, golpe a golpe": ("Players' damage, hit by hit", "Daño de los jugadores, golpe a golpe"),
    "Outras skills dos jogadores": ("Players' other skills", "Otras habilidades de los jugadores"),
    "Dano dos monstros, golpe a golpe": ("Monsters' damage, hit by hit", "Daño de los monstruos, golpe a golpe"),
    "Outras skills dos monstros": ("Monsters' other skills", "Otras habilidades de los monstruos"),
    "recebeu cura de um efeito": ("healed by an effect", "curado por un efecto"),
    "recebeu %s de um efeito": ("got %s from an effect", "recibió %s de un efecto"),
    "No chefe: %s começou": ("On the boss: %s started", "En el jefe: %s empezó"),
    "No chefe: %s acabou": ("On the boss: %s ended", "En el jefe: %s terminó"),
    "No chefe: %s %s": ("On the boss: %s %s", "En el jefe: %s %s"),
    "de %s": ("from %s", "de %s"),
    "provavelmente de %s": ("probably from %s", "probablemente de %s"),
    "Dano: cada golpe, que acertou ou errou. Outras skills: o que foi usado sem causar dano (buffs, curas, debuffs) "
    "e as conjurações.": (
        "Damage: every hit, landed or missed. Other skills: what was used without dealing damage (buffs, heals, "
        "debuffs) and the casts.",
        "Daño: cada golpe, acertado o fallado. Otras habilidades: lo que se usó sin causar daño (buffs, curas, "
        "debuffs) y los lanzamientos."),
    "Equipamentos": ("Equipment", "Equipos"),
    "Cartas": ("Cards", "Cartas"),
    "Cartas de MVP": ("MVP cards", "Cartas de MVP"),
    "Refino, grau e reforma": ("Refine, grade and reform", "Refinamiento, grado y reforma"),
    "Alquimia e culinária": ("Alchemy and cooking", "Alquimia y cocina"),
    "Episódios 17 em diante": ("Episode 17 onward", "Episodios 17 en adelante"),
}
