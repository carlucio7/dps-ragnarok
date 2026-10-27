# Changelog / Registro de mudanças

Português · [English](#english) · [Español](#español)

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
