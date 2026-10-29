# Changelog / Registro de mudanças

Português · [English](#english) · [Español](#español)

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
