# Changelog / Registro de mudanças

Português · [English](#english) · [Español](#español)

## [1.2.0] — 2026-11-05

- **Novo nome: Replay Master** (antes DPS Ragnarok). O programa já faz bem mais
  do que medir DPS. O .exe agora é `ReplayMaster.exe`; as configurações e o
  histórico de testes continuam em `%APPDATA%\RODpsMeter`.
- **Equipamento** (nova aba na análise): tudo o que quem gravou vestia (refino,
  cartas, opções, grau, visuais e sombrios) e o personagem montado com os
  sprites do próprio jogo instalado: classe, cabelo e cores, roupa, chapéus,
  capa, arma e escudo. O boneco anda por padrão; gire e escolha a ação
  (parado, andando, sentado, atacando, conjurando...). Sem o jogo no PC, mostra só a lista.
- **Drops** (nova aba na análise e no widget, ao lado de Grupo/Skills/Alvos): no
  widget, só o que você pegou; na análise, um quadro para cada destino (você
  pegou, outros jogadores pegaram, ficaram no chão) e o resumo por item, com
  prêmios de MVP. "Pego por" vem da ação de pegar do jogo.
- **XP** (nova aba na análise e no widget, separada dos drops): o replay não
  grava a XP ganha, só a XP total no início de cada gravação. O medidor mostra o
  nível e o % do nível, a XP exata do início desta gravação até o início da
  próxima do mesmo personagem e uma **estimativa** dos abates: XP de cada
  monstro (rAthena e Divine Pride) com a penalidade de nível e a sua parte do
  dano, vezes os bônus. XP por minuto em % do nível, XP por hora, XP por monstro
  e um gráfico da XP ao longo do tempo.
  - Lista de bônus para marcar, todos somando: evento do servidor, VIP (+20%),
    Cetro do Coração Lunar (+30%, 24 h), Kafra Buff (+50%, 7 dias), manuais de
    combate (consumíveis: competem entre si, vale o maior), Banquete de Njord
    (o % vem do próprio buff), Milagre Solar, Lunar e Estelar, equipamentos e
    visuais e outros. VIP, Cetro, Kafra Buff, manual, Njord e Milagre são
    detectados no replay e só contam enquanto estão ativos (os de conta, os
    manuais e o Milagre não acabam com a morte); o evento do servidor a pessoa
    marca. O bônus dos equipamentos, visuais e cartas vem do texto dos itens no
    jogo instalado ("EXP obtida por monstros +5%", inclusive de conjunto e
    "[Durante o Evento]").
  - Também dá para usar o fator **medido** (a XP exata entre duas gravações
    seguidas do mesmo personagem ÷ a XP estimada) ou um **valor fixo**.
- **Buffs e Debuffs** (antes Buffs): ranking do quanto cada efeito rendeu de
  dano, pela fórmula de cada um (Cometa, Pólen, Avanço Sísmico, Garra Sombria,
  Lex Aeterna...), com gráfico. Os buffs ficam em ordem: o que rendeu dano,
  depois suporte do grupo, buffs de classe, consumíveis e serviços. Nova coluna
  Efeito com a descrição do próprio jogo; nomes em português que antes
  apareciam com o código interno ("Plusattackpower" agora é "ATQ aumentado");
  status de sistema (venda, transformação...) não aparecem mais. Dá para
  escolher a fase da luta (Fase 1, Fase 3...).
- **Linha do tempo:** o filtro vale também para a lista de eventos, que mostra
  cada golpe e skill (inclusive dos monstros) e segue os jogadores marcados em
  "DPS de cada jogador". Nova sub-aba Dano por fase.
- **Análise de DPS:** dano total de cada fase e de cada jogador por fase.
- **Fases do Betelgeuse:** quando a fase 2 é pulada, a última aparece como
  Fase 3 (e não Fase 2).
- **Dedo Duro:**
  - Zona de risco (amarelo, aba própria): na fase 3 do Betelgeuse, quem ficou
    no alcance das armadilhas de 1 s antes a 16 s depois de o Betelgeuse
    aparecer, com a posição segura.
  - Assincronia (vermelho): golpes fortes (0,5% do HP do chefe ou mais) a mais
    de 0,5 s de qualquer golpe forte dos outros DPS vivos, em toda janela de
    ataque.
  - Cinzas Vulcânicas (Dieter): aparece nos debuffs e avisa quando a skill foi
    usada mas o status nunca apareceu no chefe (o Betelgeuse é imune).
- **Milagre Solar, Lunar e Estelar:** o medidor reconhece o Milagre (o jogo liga
  um status de 1 hora sem ícone) e festeja no widget: faixa dourada com
  estrelas, cores pulsando e um som curto. Depois mostra quanto falta no rodapé
  ("★ Milagre · 54 min"). Dá para desligar tudo, ou só o som, no menu ⋯.
- **Widget:** botão /where com o mapa e as coordenadas de quem grava; um clique
  copia no formato do navegador do jogo (`/navi icas_in 82/120`).
- **Testes:** dá para salvar uma luta de qualquer replay, não só dos bonecos de
  treino (o equipamento salvo é o de quem gravou).

## [1.1.0] — 2026-10-28

- **Linha do tempo** (nova aba na análise): uma luta contra chefe no tempo, com
  gráficos e marcações sobrepostos. Curvas de DPS do grupo e de cada jogador, HP
  estimado do chefe e dano recebido; faixas com a Garra Sombria, o Pólen, o
  Avanço Sísmico (Quake), a Dor Máxima e os outros debuffs no chefe; o Alívio
  do chefe com a redução de dano de cada trecho (sobe 10% por Alma viva); mortes e
  ressurreições, skills do chefe, dano refletido, usos da Garra, golpes fortes e
  Elo Celestial. Dá para aproximar até décimos de segundo e passar o mouse para
  ver o que acontecia em cada instante, inclusive quanto tempo depois do começo
  da fase (que conta de quando o monstro da fase aparece).
- **DPS ativo:** além do dano total e do DPS em combate, o DPS de cada um só no
  tempo em que estava de fato batendo (sem o tempo morto, esperando ou
  correndo). No widget (botão direito › DPS), no Resumo e na tabela de
  Jogadores.
- **HP do chefe pela dificuldade:** o replay não diz a dificuldade, então o
  medidor deduz pelo dano (Betelgeuse: de Selado, 500M, a Nível 5, 2B, pela
  calculadora da LATAM Tools). Morto, o nível que bate com o dano; vivo, o
  Nível 1 ou o mínimo que comporta o dano visto. A conta inclui a regeneração
  que os abates mostram (~6% do HP por minuto), então luta longa não vira nível
  mais alto. Se a gravação começou com a luta em andamento (o chefe já estava na
  tela), o abate só diz o mínimo do HP. Dá para escolher a dificuldade
  no Dedo Duro e na Linha do tempo. O HP vale para o clímax (10%), os golpes
  antes da Garra (0,5%), a curva de HP e a tabela de Monstros (antes, o
  Betelgeuse aparecia sempre com 2B).
- **Dedo Duro:**
  - Atacou antes da Garra Sombria: quem fez, somando os golpes, 0,5% ou mais do
    HP do chefe numa fase antes de a Garra chegar (o pouco de um Cometa ou de um
    Avanço Sísmico não chega lá). Grave quando o chefe usa Dor Máxima.
  - Elo Celestial: Mestre Celestial sem o Elo é grave (começar a luta sem ele,
    ou deixar acabar). Só conta até a primeira morte: depois de morrer ele não tem
    os 120 AP para usar de novo.

## [1.0.3] — 2026-10-26

- Corrige o erro "Não foi possível localizar o número ordinal 380", que impedia o
  programa de abrir em alguns PCs. O lançador do .exe agora é compilado sem a
  função da comctl32 que só existe quando o Windows aplica o manifesto do
  programa, coisa que alguns PCs não fazem. Um lançador próprio também costuma
  ser menos marcado por antivírus que o padrão do PyInstaller.

## [1.0.2] — 2026-10-24

- Nomes em inglês e espanhol sem os espaços que o cliente do jogo deixa sobrando
  ("Solar, Lunar and Stellar Union ." nos avisos).
- Espanhol: "durante Explosión Floreciente" no Dedo Duro, em vez de "en el
  Explosión Floreciente".

## [1.0.1] — 2026-10-24

- **Nomes no seu idioma:** em inglês e espanhol, skills, buffs, debuffs, classes,
  monstros, itens e opções aleatórias aparecem com os nomes que o jogo usa nesse
  idioma, inclusive nos textos do Dedo Duro. Os nomes vêm do `data.grf` da sua
  instalação (sempre atualizados); sem o jogo no PC, o pacote traz uma cópia.
- **Monstros novos (Biosfera de Varmundt, episódio 19):** monstros que chegam no
  replay com uma chave no lugar do nome (`#685`, `␜VpIB␜`) agora aparecem com o
  nome certo, lido das tabelas do jogo. Sem nome em lugar nenhum, aparece
  "Monstro 21559".
- **Pasta do jogo:** acha as pastas Replay de todas as instalações (registro do
  Windows e pastas de costume em todos os discos) e segue a gravação mais nova.
  Se não achar nenhuma, o widget avisa e um clique abre a escolha da pasta.
- Skills de monstro sem nome no cliente ganharam nomes legíveis em inglês e
  espanhol ("Guided Attack", "Aura Asesina").
- Classes que o cliente grafa diferente (Arquimago, Elementalista) e as montarias
  da 4ª classe expandida têm nome em inglês e espanhol.
- Correções: "HP máx." mostrava 0 para monstros sem HP conhecido; colunas do
  Dedo Duro mais largas em espanhol.

## [1.0.0] — 2026-10-24

Primeira versão pública: widget de DPS ao vivo, janela de análise (resumo,
jogadores, monstros, DPS, buffs, mortes, testes) e a aba Dedo Duro. Em português,
inglês e espanhol.

---

## English

### [1.2.0] — 2026-11-05

- **New name: Replay Master** (formerly DPS Ragnarok). The program does a lot
  more than measure DPS now. The .exe is now `ReplayMaster.exe`; settings and
  the test history stay in `%APPDATA%\RODpsMeter`.
- **Equipment** (new analysis tab): everything the recorder wore (refine,
  cards, options, grade, costumes and shadow gear) and the character drawn with
  the installed game's own sprites: class, hair and colors, outfit, headgears,
  garment, weapon and shield. The character walks by default; turn it and pick
  the action (standing, walking, sitting, attacking, casting...). Without the game on the
  PC, it shows only the list.
- **Drops** (new tab in the analysis and the widget, next to Party/Skills/Targets):
  the widget shows only what you picked up; the analysis has one frame per
  outcome (you picked up, other players picked up, left on the ground) and the
  per-item summary, with MVP rewards. "Picked up by" comes from the game's
  pick-up action.
- **XP** (new tab in the analysis and the widget, separate from drops): the
  replay doesn't store XP gained, only the total XP at the start of each
  recording. The meter shows the level and level %, the exact XP from the start
  of this recording to the start of the same character's next one, and an
  **estimate** from kills: each monster's XP (rAthena and Divine Pride) with the
  level penalty and your share of the damage, times the bonuses. XP per minute as
  % of the level, XP per hour, XP per monster and a chart of XP over time.
  - Bonus list to tick, all adding up: server event, VIP (+20%), Lunar Heart
    Scepter (+30%, 24 h), Kafra Buff (+50%, 7 days), battle manuals
    (consumables: they compete, the highest counts), Njord's Feast (the % comes
    from the buff itself), Miracle of the Sun, Moon and Stars, equipment and
    costumes, and others. VIP, Scepter, Kafra Buff, manuals, Njord and the
    Miracle are detected in the replay and only count while active (account
    bonuses, manuals and the Miracle survive death); the server event is ticked
    by hand. Equipment, costume and card bonuses come from the item texts in the
    installed game ("EXP obtida por monstros +5%", set and "[Durante o Evento]"
    bonuses included).
  - The **measured** factor (exact XP between two back-to-back recordings of the
    same character ÷ estimated XP) or a **fixed value** can be used instead.
- **Buffs and Debuffs** (formerly Buffs): ranking of how much damage each effect
  added, by each one's formula (Comet, Pollen, Rush Quake, Dark Claw, Lex
  Aeterna...), with a chart. Buffs are ordered: damage gain first, then party
  support, class buffs, consumables and services. New Effect column with the
  game's own description; names that showed the internal code now use the
  game's name; system statuses (vending, transformation...) are hidden. You can
  pick the fight phase (Phase 1, Phase 3...).
- **Timeline:** the filter now applies to the event list too, which shows every
  hit and skill (monsters' included) and follows the players ticked under "DPS
  of each player". New Damage per phase sub-tab.
- **DPS analysis:** total damage per phase and per player per phase.
- **Betelgeuse phases:** when phase 2 is skipped, the last one shows as Phase 3
  (not Phase 2).
- **Snitch:**
  - Risk zone (yellow, own tab): in Betelgeuse's phase 3, who stood within trap
    range from 1 s before to 16 s after Betelgeuse appears, with the safe spot.
  - Desync (red): strong hits (0.5% of the boss HP or more) more than 0.5 s away
    from any strong hit by the other living DPS, in every attack window.
  - Volcanic Ash (Dieter): listed among the debuffs, with a warning when the
    skill was used but the status never showed on the boss (Betelgeuse is
    immune).
- **Miracle of the Sun, Moon and Stars:** the meter recognizes the Miracle (the
  game turns on a 1-hour status with no icon) and celebrates on the widget: a
  gold banner with stars, pulsing colors and a short sound. Then the footer shows
  the time left ("★ Miracle · 54 min"). Turn it all off, or just the sound, in
  the ⋯ menu.
- **Widget:** /where button with the recorder's map and coordinates; one click
  copies it in the game's navigation format (`/navi icas_in 82/120`).
- **Tests:** a fight from any replay can be saved, not only training dummies
  (the saved equipment is the recorder's).

### [1.1.0] — 2026-10-28

- **Timeline** (new analysis tab): a boss fight over time, with overlaid charts
  and markers. Curves for party DPS and each player's DPS, estimated boss HP and
  damage taken; lanes for Dark Claw, All Bloom, Quake, Max Pain and the other
  debuffs on the boss; the boss's Relieve with each stretch's damage reduction
  (10% more per living Soul); deaths and resurrections, boss skills, reflected damage,
  Dark Claw uses, strong hits and Enchanting Sky. You can zoom down to tenths of
  a second and hover to see what was happening at each moment, including how long
  after the phase started (counted from when the phase's monster appears).
- **Active DPS:** besides total damage and combat DPS, each player's DPS only
  over the time they were actually attacking (without time dead, waiting or
  running). In the widget (right-click › DPS), the Summary and the Players
  table.
- **Boss HP by difficulty:** the replay doesn't say the difficulty, so the meter
  infers it from the damage (Betelgeuse: from Sealed, 500M, to Level 5, 2B, from
  the LATAM Tools calculator). Killed, the level that matches the damage; alive,
  Level 1 or the lowest level that fits the damage seen. It accounts for the
  regeneration the kills show (~6% of HP per minute), so a long fight doesn't
  turn into a higher level. If the recording started with the fight underway
  (the boss was already on screen), a kill only gives the minimum HP. You can pick the
  difficulty in the Snitch and the Timeline. The HP is used for the climax
  (10%), hits before Dark Claw (0.5%), the HP curve and the Monsters table
  (before, Betelgeuse always showed 2B).
- **Snitch:**
  - Attacked before Dark Claw: whoever dealt, adding up their hits, 0.5% or more
    of the boss's HP in a phase before Dark Claw landed (the little from a Comet
    or a Quake doesn't get there). Serious when the boss uses Max Pain.
  - Enchanting Sky: a Sky Emperor without it is serious (starting the fight
    without it, or letting it run out). It only counts until the first death:
    after dying there aren't 120 AP to use it again.

### [1.0.3] — 2026-10-26

- Fixes the "The ordinal 380 could not be located" error that kept the program
  from opening on some PCs. The .exe launcher is now built without the comctl32
  function that only exists when Windows applies the program's manifest, which
  some PCs don't do. A custom launcher also tends to be flagged by antivirus less
  often than PyInstaller's default one.

### [1.0.2] — 2026-10-24

- English and Spanish names without the extra spaces the game client leaves in
  some of them ("Solar, Lunar and Stellar Union ." in the warnings).
- Spanish: "durante Explosión Floreciente" in the Snitch tab, instead of "en el
  Explosión Floreciente".

### [1.0.1] — 2026-10-24

- **Names in your language:** in English and Spanish, skills, buffs, debuffs,
  classes, monsters, items and random options use the names the game uses in that
  language, including in the Snitch texts. Names come from your install's
  `data.grf` (always up to date); without the game on the PC, the package ships a
  copy.
- **New monsters (Varmundt Biosphere, episode 19):** monsters that arrive in the
  replay with a key instead of a name (`#685`, `␜VpIB␜`) now show the right name,
  read from the game's tables. With no name anywhere, it shows "Monster 21559".
- **Game folder:** finds the Replay folders of every install (Windows registry and
  the usual folders on every drive) and follows the newest recording. If none is
  found, the widget says so and a click opens the folder picker.
- Monster skills with no name in the client got readable English and Spanish
  names ("Guided Attack", "Aura Asesina").
- Classes the client spells differently (Arch Mage, Elemental Master) and the
  expanded 4th class mounts have English and Spanish names.
- Fixes: "Max HP" showed 0 for monsters with unknown HP; wider Snitch columns in
  Spanish.

### [1.0.0] — 2026-10-24

First public release: live DPS widget, analysis window (summary, players,
monsters, DPS, buffs, deaths, tests) and the Snitch tab. In Portuguese, English
and Spanish.

---

## Español

### [1.2.0] — 2026-11-05

- **Nuevo nombre: Replay Master** (antes DPS Ragnarok). El programa ya hace
  mucho más que medir DPS. El .exe ahora es `ReplayMaster.exe`; la
  configuración y el historial de pruebas siguen en `%APPDATA%\RODpsMeter`.
- **Equipo** (nueva pestaña del análisis): todo lo que llevaba quien grabó
  (refinamiento, cartas, opciones, grado, visuales y sombríos) y el personaje
  armado con los sprites del propio juego instalado: clase, pelo y colores,
  ropa, cascos, capa, arma y escudo. El personaje camina por defecto; gíralo y
  elige la acción (quieto, caminando, sentado, atacando, conjurando...). Sin el juego en la PC,
  muestra solo la lista.
- **Drops** (nueva pestaña en el análisis y en el widget, junto a
  Grupo/Skills/Objetivos): el widget muestra solo lo que recogiste; el análisis
  tiene un cuadro para cada destino (recogiste, otros jugadores recogieron,
  quedaron en el suelo) y el resumen por ítem, con premios de MVP. "Recogido
  por" viene de la acción de recoger del juego.
- **XP** (nueva pestaña en el análisis y en el widget, separada de los drops): el
  replay no graba la XP ganada, solo la XP total al inicio de cada grabación. El
  medidor muestra el nivel y el % del nivel, la XP exacta desde el inicio de esta
  grabación hasta el inicio de la próxima del mismo personaje y una
  **estimación** de las muertes: la XP de cada monstruo (rAthena y Divine Pride)
  con la penalización de nivel y tu parte del daño, por los bonos. XP por minuto
  en % del nivel, XP por hora, XP por monstruo y un gráfico de la XP en el tiempo.
  - Lista de bonos para marcar, todos sumando: evento del servidor, VIP (+20%),
    Cetro del Corazón Lunar (+30%, 24 h), Kafra Buff (+50%, 7 días), manuales de
    combate (consumibles: compiten entre sí, vale el mayor), Banquete de Njord
    (el % viene del propio buff), Milagro Solar, Lunar y Estelar, equipos y
    visuales y otros. VIP, Cetro, Kafra Buff, manual, Njord y el Milagro se
    detectan en el replay y solo cuentan mientras están activos (los de cuenta,
    los manuales y el Milagro no terminan con la muerte); el evento del servidor
    se marca a mano. El bono de equipos, visuales y cartas viene del texto de los
    ítems en el juego instalado ("EXP obtida por monstros +5%", incluso de
    conjunto y "[Durante o Evento]").
  - También se puede usar el factor **medido** (la XP exacta entre dos
    grabaciones seguidas del mismo personaje ÷ la XP estimada) o un **valor
    fijo**.
- **Buffs y Debuffs** (antes Buffs): ranking de cuánto daño rindió cada efecto,
  según la fórmula de cada uno (Cometa, Polen, Avance Sísmico, Garra Sombría,
  Lex Aeterna...), con gráfico. Los buffs quedan en orden: lo que rindió daño,
  luego apoyo del grupo, buffs de clase, consumibles y servicios. Nueva columna
  Efecto con la descripción del propio juego; los nombres que mostraban el
  código interno ahora usan el nombre del juego; los estados de sistema (venta,
  transformación...) ya no aparecen. Se puede elegir la fase de la pelea (Fase
  1, Fase 3...).
- **Línea de tiempo:** el filtro también vale para la lista de eventos, que
  muestra cada golpe y skill (también de los monstruos) y sigue a los jugadores
  marcados en "DPS de cada jugador". Nueva subpestaña Daño por fase.
- **Análisis de DPS:** daño total de cada fase y de cada jugador por fase.
- **Fases de Betelgeuse:** cuando se salta la fase 2, la última aparece como
  Fase 3 (y no Fase 2).
- **Soplón (Dedo Duro):**
  - Zona de riesgo (amarillo, pestaña propia): en la fase 3 de Betelgeuse,
    quién quedó al alcance de las trampas desde 1 s antes hasta 16 s después de
    que aparece Betelgeuse, con la posición segura.
  - Asincronía (rojo): golpes fuertes (0,5% del HP del jefe o más) a más de
    0,5 s de cualquier golpe fuerte de los otros DPS vivos, en toda ventana de
    ataque.
  - Cenizas Volcánicas (Dieter): aparece en los debuffs y avisa cuando la skill
    se usó pero el estado nunca apareció en el jefe (Betelgeuse es inmune).
- **Milagro Solar, Lunar y Estelar:** el medidor reconoce el Milagro (el juego
  activa un estado de 1 hora sin ícono) y lo festeja en el widget: franja
  dorada con estrellas, colores que laten y un sonido corto. Después el pie
  muestra cuánto falta ("★ Milagro · 54 min"). Se puede apagar todo, o solo el
  sonido, en el menú ⋯.
- **Widget:** botón /where con el mapa y las coordenadas de quien graba; un
  clic lo copia en el formato del navegador del juego (`/navi icas_in 82/120`).
- **Pruebas:** se puede guardar una pelea de cualquier replay, no solo de los
  muñecos de entrenamiento (el equipo guardado es el de quien grabó).

### [1.1.0] — 2026-10-28

- **Línea de tiempo** (nueva pestaña del análisis): una pelea contra un jefe en
  el tiempo, con gráficos y marcas superpuestos. Curvas de DPS del grupo y de
  cada jugador, HP estimado del jefe y daño recibido; franjas con la Garra
  Tenebrosa, el Polen, el Sismo, la Dolor Máxima y los otros debuffs en el
  jefe; el Alivio del jefe con la reducción de daño de cada tramo (10% más por
  Alma viva); muertes y resurrecciones, skills del jefe, daño reflejado, usos de la
  Garra, golpes fuertes y Vínculo Celestial. Se puede acercar hasta décimas de
  segundo y pasar el ratón para ver qué pasaba en cada momento, incluso cuánto
  tiempo después del inicio de la fase (que cuenta desde que aparece el monstruo
  de la fase).
- **DPS activo:** además del daño total y del DPS en combate, el DPS de cada uno
  solo en el tiempo en que estaba atacando de verdad (sin el tiempo muerto,
  esperando o corriendo). En el widget (clic derecho › DPS), el Resumen y la
  tabla de Jugadores.
- **HP del jefe por dificultad:** el replay no dice la dificultad, así que el
  medidor la deduce por el daño (Betelgeuse: de Sellado, 500M, a Nivel 5, 2B,
  según la calculadora de LATAM Tools). Muerto, el nivel que coincide con el
  daño; vivo, el Nivel 1 o el mínimo que soporta el daño visto. La cuenta incluye
  la regeneración que muestran los abates (~6% del HP por minuto), así que una
  pelea larga no se vuelve un nivel más alto. Si la grabación empezó con la pelea
  en curso (el jefe ya estaba en pantalla), el abate solo da el HP mínimo. Se puede elegir
  la dificultad en el Soplón y en la Línea de tiempo. El HP vale para el clímax
  (10%), los golpes antes de la Garra (0,5%), la curva de HP y la tabla de
  Monstruos (antes, el Betelgeuse aparecía siempre con 2B).
- **Soplón:**
  - Atacó antes de la Garra Tenebrosa: quien hizo, sumando sus golpes, 0,5% o
    más del HP del jefe en una fase antes de que llegara la Garra (lo poco de un
    Cometa o de un Sismo no llega). Grave cuando el jefe usa Dolor Máxima.
  - Vínculo Celestial: Emperador Celestial sin el Vínculo es grave (empezar la
    pelea sin él, o dejar que se acabe). Solo cuenta hasta la primera muerte:
    después de morir no tiene los 120 AP para usarlo de nuevo.

### [1.0.3] — 2026-10-26

- Corrige el error "No se encontró el ordinal 380", que impedía abrir el programa
  en algunos PC. El lanzador del .exe ahora se compila sin la función de comctl32
  que solo existe cuando Windows aplica el manifiesto del programa, algo que
  algunos PC no hacen. Un lanzador propio además suele ser marcado por los
  antivirus menos que el estándar de PyInstaller.

### [1.0.2] — 2026-10-24

- Nombres en inglés y español sin los espacios que el cliente del juego deja de
  más en algunos ("Unión Solar, Lunar y Estelar ." en los avisos).
- Español: "durante Explosión Floreciente" en el Soplón, en lugar de "en el
  Explosión Floreciente".

### [1.0.1] — 2026-10-24

- **Nombres en tu idioma:** en inglés y español, skills, buffs, debuffs, clases,
  monstruos, ítems y opciones aleatorias usan los nombres que el juego usa en ese
  idioma, también en los textos del Soplón. Los nombres vienen del `data.grf` de
  tu instalación (siempre al día); sin el juego en el PC, el paquete trae una
  copia.
- **Monstruos nuevos (Biosfera de Varmundt, episodio 19):** los monstruos que
  llegan al replay con una clave en lugar del nombre (`#685`, `␜VpIB␜`) ahora
  aparecen con el nombre correcto, leído de las tablas del juego. Sin nombre en
  ninguna parte, aparece "Monstruo 21559".
- **Carpeta del juego:** encuentra las carpetas Replay de todas las instalaciones
  (registro de Windows y carpetas habituales en todos los discos) y sigue la
  grabación más nueva. Si no encuentra ninguna, el widget avisa y un clic abre la
  elección de carpeta.
- Las skills de monstruo sin nombre en el cliente tienen nombres legibles en
  inglés y español ("Guided Attack", "Aura Asesina").
- Las clases que el cliente escribe distinto (Archimago, Elementalista) y las
  monturas de la 4ª clase expandida tienen nombre en inglés y español.
- Correcciones: "HP máx." mostraba 0 en monstruos sin HP conocido; columnas del
  Soplón más anchas en español.

### [1.0.0] — 2026-10-24

Primera versión pública: widget de DPS en vivo, ventana de análisis (resumen,
jugadores, monstruos, DPS, buffs, muertes, pruebas) y la pestaña Soplón. En
portugués, inglés y español.
