# Changelog / Registro de mudanças

Português · [English](#english) · [Español](#español)

## 1.6.0

Aviso de item com som e lugar, sessões longas sem ficar pesado e a vida do Aquila refeita.

- Aviso de item: marque um item com o botão direito na aba Drops (no widget ou na análise). Quando ele cair, o widget toca um som curto e mostra um cartão com o mapa e as coordenadas.
- Um clique no cartão copia o /navi para colar no jogo.
- Se você sair de perto sem pegar o item (telou sem querer, foi puxado), o cartão volta até o item sumir do chão.
- Janela "Avisos de item", na aba Drops da análise: busca na lista de itens do próprio jogo, pelo nome ou pelo número, para marcar itens que ainda não caíram.
- Volume e tom do som à escolha, na mesma janela ou em Sons no menu do widget. Sem item marcado, nada toca.
- Sessões longas: o widget não fica mais pesado depois de muito tempo gravando. Numa gravação de 2 h e meia ele responde como nos primeiros minutos.
- A janela de análise aberta durante a gravação não prende mais o widget.
- Dois clientes gravando ao mesmo tempo não deixam mais o programa lento.
- Pasta Replay com centenas de gravações pesa menos.
- Aquila: vida e regeneração refeitas com mais lutas. A curva de vida da Linha do tempo acompanha a luta mesmo com o chefe fora da tela.

## 1.5.0

Avisos do chefe e resumo da luta no widget, botão de copiar imagem, XP automática e as áreas do Mestre Elemental.

- Cartão do chefe: o widget mostra por 5 s quando o chefe troca de propriedade, fica imune a uma ou muda de tamanho, com o que bater, o que evitar e quanto o seu ataque rende. Dá para desligar no menu ou com o botão direito no cartão.
- Avisos de mecânica no mesmo cartão: Dor Máxima ligou ou acabou, Aliviar muito alto com o número de Almas ativas, e modo defesa e defesa caída do Aquila.
- O aviso de Dor Máxima aparece mesmo quando o chefe a usa fora da tela.
- Resumo no fim da luta contra chefe: tempo, a sua parte do dano e as principais conclusões do Dedo Duro por alguns segundos. Clique para abrir o Dedo Duro.
- Copiar imagem: um botão no widget e outro na análise deixam a imagem pronta para colar no Discord. Ctrl+Shift+C copia só o gráfico sob o mouse, e dá para esconder os nomes dos jogadores.
- Lembrete de gravação desligada quando o jogo está aberto e nada está sendo gravado.
- XP: no Ragnarok, bônus de evento, VIP e Cetro somam; itens e Banquete multiplicam esse grupo; manual e Kafra somam por fora; Milagre dobra tudo. A nova versão reflete esta regra.
- XP: modo automático, agora o padrão. Usa a lista de bônus, corrige a conta com a XP exata e marca sozinho o evento do servidor.
- XP: o manual que já estava ativo no começo da gravação vale pelo último manual que você usou.
- XP: a entrega de missões não distorce mais a calibração, e o programa avisa que a XP delas fica fora da estimativa.
- XP: o progresso das caças aparece na aba XP do widget e pode ser fixado.
- XP: o alvo da Oposição rende mais no dia certo do mês, quando não há Milagre.
- Mestre Elemental: Vulcão, Insígnias, Proteger Terreno e Prisão de Teia são lidos do replay.
- Linha do tempo: faixas das áreas no chão, com quem pôs, quanto durou e o que apagou.
- Linha do tempo: as skills que o chefe joga no chão aparecem, com o jogador em cima de quem caíram.
- Buffs e Debuffs: quanto cada área rendeu e o dano creditado a quem a pôs.
- Dedo Duro: alerta amarelo de "faltou" ou "durou pouco" para Vulcão e Insígnia, e um resumo de quando o Ganbantein apagou áreas do grupo.
- Dedo Duro: Oposição errada ou esquecida no chefe é erro grave.
- Mortes: o resumo aponta o golpe que realmente matou, e reconhece a explosão dos Robovacs e o golpe do Aquila vindo de fora da tela.
- Aquila: o suporte à luta foi aprimorado.

## 1.4.0

Resumo da morte no widget, previsão de XP muito mais precisa em sessões longas e a vida do Aquila na Linha do tempo.

- Quando você morre, o widget mostra por 10 s o que te matou: o monstro com o sprite do jogo, o golpe final com a propriedade e as maiores fontes de dano dos 5 s antes. Clique para fechar; dá para desligar no menu.
- O resumo também cobre armadilha, União Solar, Dor Máxima (com o golpe que foi refletido) e vida perdida sem golpe visível, e a mensagem muda se você morrer de novo na mesma luta.
- XP: previsão do próximo nível bem mais precisa. Nas duas sessões de quase 1 hora que testamos, o erro médio caiu de 5 a 12 min para 1 a 2,5 min, e a previsão ficou a até 2 min do horário real em 52% a 90% do tempo (antes, 10% a 20%). A XP estimada, que errava uns 20%, passou a errar uns 3%.
- XP: cada subida de nível acerta a estimativa na hora, e a conta continua no nível novo.
- XP: gravações com menos de 10 min ou 1% do nível não calibram mais, e a previsão aparece depois desse tempo.
- Aquila: a dificuldade é reconhecida sozinha, e a Linha do tempo mostra a vida dele com a regeneração e as quebras de defesa (valores estimados com as lutas que temos).
- Mortes: overkill e causa certos mesmo quando a vida cai com atraso, como na Dor Máxima.
- Linha do tempo: conjurações instantâneas não aparecem mais repetidas.
- Buffs e Debuffs: os gráficos explicam quais buffs ficam de fora.
- Milagre no rodapé legível no tema Claro.

## 1.3.1

Lex Aeterna contada certo, dano creditado a cada jogador e o grupo todo na Linha do tempo.

- Buffs e Debuffs: cada Lex Aeterna dobra o próximo golpe, mesmo com o Cardeal usando várias por segundo. Antes só a primeira de cada sequência contava.
- Linha do tempo: o grupo todo aparece na lista de jogadores, inclusive quem não bate, como o Cardeal.
- Buffs e Debuffs: a tabela de buffs mede a luta escolhida, não a sessão inteira (o combate de antes derrubava o tempo ativo).
- Buffs e Debuffs: novo gráfico com o dano creditado a cada jogador, somando o que os efeitos dele renderam (Cometa e Pólen do Magus, Garra do Executor, Lex do Cardeal...).

## 1.3.0

Drops coloridos e que dá para ocultar, informações fixas no widget e XP comparada entre gravações.

- Drops com cores por tipo: equipamento, carta, carta de MVP, refino, alquimia/culinária e itens dos episódios 17 em diante. Dá para trocar as cores na análise.
- Botão direito num drop: ocultar até fechar o programa ou para sempre. Dá para desfazer em "Itens ocultos".
- Drops favoritos ficam na ordem em que você marcou.
- Fixe até duas informações no widget, como a XP por minuto, e veja em qualquer aba.
- XP: compare com outra gravação do mesmo personagem.
- XP: % do nível primeiro e o número depois, abates por minuto e um gráfico mais fácil de ler.
- XP: escolha quais itens de evento ainda valem.
- Som curto opcional para HP baixo com a União (desligado; ⋯ › Sons).
- Linha do tempo: "Jogadores marcados" mostra só esses jogadores, e as curas de efeitos aparecem como cura recebida.

## 1.2.5

Estimativa de XP mais precisa.

- O Milagre multiplica os outros bônus.
- O bônus do manual vem do replay.

## 1.2.4

Corrige o widget que parava de atualizar.

- Passar o mouse na estrela dos drops não trava mais o widget.
- Estrela mais fácil de clicar e lista de drops rolando mais rápido.
- Replays grandes abrem bem mais rápido.
- XP: tempo até o próximo nível.
- A lista de bônus de XP mostra se cada bônus estava ativo.

## 1.2.3

Milagre mais fiel ao jogo e drops favoritos.

- Um novo Milagre renova a hora, e o Milagre continua depois de morrer ou trocar de mapa.
- Bônus de evento dos itens ficam desligados até você marcar.
- Drops: marque favoritos com a estrela; eles ficam no topo.
- Linha do tempo: as skills dos jogadores aparecem na lista desde o início.
- Nomes das skills novas do último patch.

## 1.2.2

XP dos monstros novos.

- Monstros do episódio 19 e da Biosfera [Eco] com XP.
- Evento do servidor: escolha rápida de +50%, +100% ou +200%.
- Som do Milagre mais baixo, com volume ajustável.

## 1.2.1

Abas da análise sem nomes cortados.

- Os nomes das abas cabem na janela.

## 1.2.0

Novo nome, Replay Master, e as abas Equipamento, Drops e XP.

- Equipamento: o que você vestia, com o personagem desenhado.
- Drops: o que você pegou, o que outros pegaram e o que ficou no chão.
- XP: estimativa dos abates, com bônus, XP por minuto e por hora e gráfico.
- Buffs e Debuffs: quanto dano cada efeito rendeu.
- Milagre: o widget festeja e mostra quanto tempo falta.
- Dedo Duro: zona de risco, golpes fora de sincronia e Cinzas Vulcânicas.
- Botão /where com o mapa e as coordenadas.
- Testes de qualquer replay, não só do boneco.

## 1.1.0

Linha do tempo das lutas contra chefe.

- Linha do tempo: DPS, HP do chefe, debuffs, mortes e skills na mesma tela.
- DPS ativo: o DPS só no tempo em que cada um estava batendo.
- HP do chefe pela dificuldade, deduzida pelo dano.
- Dedo Duro: quem atacou antes da Garra Sombria e Elo Celestial.

## 1.0.3

Corrige o erro "número ordinal 380", que impedia o programa de abrir em alguns PCs.

## 1.0.2

Pequenas correções nos nomes em inglês e espanhol.

## 1.0.1

Nomes no seu idioma e monstros novos.

- Skills, buffs, classes, monstros e itens com os nomes do jogo em inglês e espanhol.
- Nomes certos para os monstros novos.
- Acha as pastas Replay de todas as instalações do jogo.

## 1.0.0

Primeira versão pública.

- Widget de DPS ao vivo, janela de análise e Dedo Duro, em português, inglês e espanhol.

---

## English

### 1.6.0

Item alert with sound and place, long sessions that stay light and Aquila's HP redone.

- Item alert: mark an item by right-clicking it on the Drops tab (widget or analysis). When it drops, the widget plays a short sound and shows a card with the map and the coordinates.
- One click on the card copies the /navi to paste in the game.
- If you leave without picking the item up (a teleport by mistake, a recall), the card comes back until the item leaves the ground.
- "Item alerts" window, on the analysis Drops tab: search the game's own item list, by name or by number, to mark items that have not dropped yet.
- Volume and tone of the sound are yours to choose, in the same window or under Sounds in the widget menu. With no item marked, nothing plays.
- Long sessions: the widget no longer gets heavy after a long time recording. In a 2.5-hour recording it responds as in the first minutes.
- The analysis window open while recording no longer holds the widget.
- Two clients recording at the same time no longer make the program slow.
- A Replay folder with hundreds of recordings weighs less.
- Aquila: HP and regeneration redone with more fights. The HP curve on the Timeline follows the fight even with the boss off screen.

### 1.5.0

Boss alerts and a fight summary on the widget, a copy-image button, automatic XP and the Elemental Master ground areas.

- Boss card: the widget shows for 5 s when the boss changes property, becomes immune to one or changes size, with what to hit with, what to avoid and how much your attack does. You can turn it off in the menu or by right-clicking the card.
- Mechanic alerts on the same card: Max Pain started or ended, Relieve very high with the number of Souls alive, and Aquila in defense mode or with its defense down.
- The Max Pain alert shows up even when the boss uses it off screen.
- Summary at the end of a boss fight: time, your share of the damage and the main Snitch findings for a few seconds. Click to open the Snitch.
- Copy image: a button on the widget and another in the analysis leave the image ready to paste on Discord. Ctrl+Shift+C copies only the chart under the mouse, and you can hide player names.
- Recording-off reminder when the game is open and nothing is being recorded.
- XP: in Ragnarok, the event, VIP and Scepter bonuses add up; items and the Banquet multiply that group; the manual and Kafra are added on top; the Miracle doubles everything. The new version follows this rule.
- XP: automatic mode, now the default. It uses the bonus list, corrects the math with the exact XP and ticks the server event by itself.
- XP: a manual that was already active when the recording started counts as the last manual you used.
- XP: quest turn-ins no longer skew the calibration, and the program warns that their XP is left out of the estimate.
- XP: hunt progress shows on the XP tab of the widget and can be pinned.
- XP: the Opposition target gives more on the right day of the month, when there is no Miracle.
- Elemental Master: Volcano, Insignias, Land Protector and Spider Web are read from the replay.
- Timeline: lanes for the ground areas, with who placed them, how long they lasted and what erased them.
- Timeline: the skills the boss throws on the ground show up, with the player they landed on.
- Buffs and Debuffs: how much each area gave and the damage credited to whoever placed it.
- Snitch: yellow alert for "missing" or "too short" Volcano and Insignia, and a summary of when Ganbantein erased the areas of the party.
- Snitch: a wrong or forgotten Opposition on the boss is a serious mistake.
- Deaths: the summary points to the hit that actually killed you, and recognises the Robovac explosion and Aquila's hit coming from off screen.
- Aquila: support for the fight was improved.

### 1.4.0

Death summary on the widget, a much more accurate XP forecast in long sessions and Aquila's HP on the Timeline.

- When you die, the widget shows what killed you for 10 s: the monster with its in-game sprite, the final blow with its element and the biggest damage sources of the 5 s before. Click to close; you can turn it off in the menu.
- The summary also covers traps, Solar Union, Max Pain (with the hit that was reflected) and HP lost with no visible hit, and the message changes if you die again in the same fight.
- XP: a much more accurate next-level forecast. In the two almost hour-long sessions we tested, the average error fell from 5–12 min to 1–2.5 min, and the forecast stayed within 2 min of the real time 52%–90% of the time (before, 10%–20%). The estimated XP, which was off by about 20%, is now off by about 3%.
- XP: every level-up corrects the estimate on the spot, and the count carries on in the new level.
- XP: recordings shorter than 10 min or 1% of a level no longer calibrate, and the forecast shows up after that.
- Aquila: the difficulty is recognized on its own, and the Timeline shows its HP with the regeneration and the defense breaks (values estimated from the fights we have).
- Deaths: correct overkill and cause even when HP drops late, as with Max Pain.
- Timeline: instant casts no longer show up twice.
- Buffs and Debuffs: the charts explain which buffs are left out.
- Miracle footer readable on the Light theme.

### 1.3.1

Lex Aeterna counted right, damage credited to each player and the whole party on the Timeline.

- Buffs and Debuffs: each Lex Aeterna doubles the next hit, even with the Cardinal casting several per second. Before, only the first of each streak counted.
- Timeline: the whole party shows in the player list, including those who don't attack, like the Cardinal.
- Buffs and Debuffs: the buff table measures the chosen fight, not the whole session (earlier combat pulled the active time down).
- Buffs and Debuffs: new chart with the damage credited to each player, including what their effects added (the Arch Mage's Comet and All Bloom, Dark Claw, the Cardinal's Lex...).

### 1.3.0

Colored drops you can hide, pinned info on the widget and XP compared between recordings.

- Drops colored by type: equipment, card, MVP card, refine, alchemy/cooking and episode 17+ items. Change the colors in the analysis.
- Right-click a drop: hide it until the program closes or for good. Undo it in "Hidden items".
- Favorite drops stay in the order you marked them.
- Pin up to two pieces of info to the widget, like XP per minute, and see them on any tab.
- XP: compare with another recording of the same character.
- XP: % of the level first and the number after, kills per minute and an easier-to-read chart.
- XP: choose which event items still count.
- Optional short sound for low HP with União (off; ⋯ › Sounds).
- Timeline: "Ticked players" shows only those players, and heals from effects show as heals received.

### 1.2.5

More accurate XP estimate.

- The Miracle multiplies the other bonuses.
- The manual's bonus comes from the replay.

### 1.2.4

Fixes the widget that stopped updating.

- Hovering the drops star no longer freezes the widget.
- Easier-to-click star and faster drops scrolling.
- Big replays open much faster.
- XP: time to the next level.
- The XP bonus list shows whether each bonus was active.

### 1.2.3

Miracle closer to the game, and favorite drops.

- A new Miracle renews the hour, and the Miracle keeps going after dying or changing maps.
- Event bonuses from items stay off until you tick them.
- Drops: mark favorites with the star; they stay on top.
- Timeline: players' skills show in the list from the start.
- Names for the new skills from the last patch.

### 1.2.2

XP for the new monsters.

- Episode 19 and [Eco] Biosphere monsters have XP.
- Server event: quick pick of +50%, +100% or +200%.
- Quieter Miracle sound, with adjustable volume.

### 1.2.1

Analysis tabs without cut-off names.

- The tab names fit in the window.

### 1.2.0

New name, Replay Master, and the Equipment, Drops and XP tabs.

- Equipment: what you wore, with your character drawn.
- Drops: what you picked up, what others picked up and what stayed on the ground.
- XP: estimate from your kills, with bonuses, XP per minute and per hour, and a chart.
- Buffs and Debuffs: how much damage each effect added.
- Miracle: the widget celebrates and shows the time left.
- Snitch: risk zone, out-of-sync hits and Volcanic Ash.
- /where button with the map and coordinates.
- Tests from any replay, not just the training dummy.

### 1.1.0

Timeline of boss fights.

- Timeline: DPS, boss HP, debuffs, deaths and skills on one screen.
- Active DPS: DPS only over the time each player was hitting.
- Boss HP by difficulty, worked out from the damage.
- Snitch: who attacked before Dark Claw, and Enchanting Sky.

### 1.0.3

Fixes the "ordinal 380" error that kept the program from opening on some PCs.

### 1.0.2

Small fixes to English and Spanish names.

### 1.0.1

Names in your language and new monsters.

- Skills, buffs, classes, monsters and items with the game's English and Spanish names.
- Correct names for the new monsters.
- Finds the Replay folders of every game install.

### 1.0.0

First public version.

- Live DPS widget, analysis window and Snitch, in Portuguese, English and Spanish.

---

## Español

### 1.6.0

Aviso de objeto con sonido y lugar, sesiones largas sin ponerse pesado y la vida del Aquila rehecha.

- Aviso de objeto: marca un objeto con clic derecho en la pestaña Drops (en el widget o en el análisis). Cuando caiga, el widget toca un sonido corto y muestra una tarjeta con el mapa y las coordenadas.
- Un clic en la tarjeta copia el /navi para pegar en el juego.
- Si te alejas sin recogerlo (un teletransporte sin querer, una llamada), la tarjeta vuelve hasta que el objeto desaparezca del suelo.
- Ventana "Avisos de objeto", en la pestaña Drops del análisis: busca en la lista de objetos del propio juego, por nombre o por número, para marcar objetos que todavía no cayeron.
- Volumen y tono del sonido a elección, en la misma ventana o en Sonidos en el menú del widget. Sin objeto marcado, no suena nada.
- Sesiones largas: el widget ya no se pone pesado después de mucho tiempo grabando. En una grabación de 2 h y media responde como en los primeros minutos.
- La ventana de análisis abierta durante la grabación ya no traba el widget.
- Dos clientes grabando al mismo tiempo ya no dejan lento el programa.
- Una carpeta Replay con cientos de grabaciones pesa menos.
- Aquila: vida y regeneración rehechas con más peleas. La curva de vida de la Línea de tiempo sigue la pelea incluso con el jefe fuera de la pantalla.

### 1.5.0

Avisos del jefe y resumen de la pelea en el widget, botón de copiar imagen, XP automática y las áreas del Maestro Elemental.

- Tarjeta del jefe: el widget muestra por 5 s cuando el jefe cambia de propiedad, se vuelve inmune a una o cambia de tamaño, con qué pegarle, qué evitar y cuánto rinde tu ataque. Se puede desactivar en el menú o con clic derecho en la tarjeta.
- Avisos de mecánica en la misma tarjeta: Dolor Máximo empezó o terminó, Aliviar muy alto con el número de Almas activas, y modo defensa y defensa caída del Aquila.
- El aviso de Dolor Máximo aparece aunque el jefe lo use fuera de pantalla.
- Resumen al final de la pelea contra jefe: tiempo, tu parte del daño y las principales conclusiones del Soplón por unos segundos. Clic para abrir el Soplón.
- Copiar imagen: un botón en el widget y otro en el análisis dejan la imagen lista para pegar en Discord. Ctrl+Shift+C copia solo el gráfico bajo el ratón, y se pueden ocultar los nombres de los jugadores.
- Recordatorio de grabación apagada cuando el juego está abierto y no se está grabando nada.
- XP: en Ragnarok, los bonos de evento, VIP y Cetro se suman; los objetos y el Banquete multiplican ese grupo; el manual y Kafra se suman aparte; el Milagro lo duplica todo. La nueva versión refleja esta regla.
- XP: modo automático, ahora el predeterminado. Usa la lista de bonos, corrige la cuenta con la XP exacta y marca solo el evento del servidor.
- XP: el manual que ya estaba activo al empezar la grabación vale por el último manual que usaste.
- XP: la entrega de misiones ya no distorsiona la calibración, y el programa avisa que su XP queda fuera de la estimación.
- XP: el progreso de las cazas aparece en la pestaña XP del widget y se puede fijar.
- XP: el objetivo de la Oposición rinde más en el día correcto del mes, cuando no hay Milagro.
- Maestro Elemental: Volcán, Insignias, Proteger Terreno y Telaraña se leen del replay.
- Línea de tiempo: franjas de las áreas en el suelo, con quién las puso, cuánto duraron y qué las borró.
- Línea de tiempo: aparecen las habilidades que el jefe lanza al suelo, con el jugador sobre el que cayeron.
- Buffs y Debuffs: cuánto rindió cada área y el daño acreditado a quien la puso.
- Soplón: alerta amarilla de "faltó" o "duró poco" para Volcán e Insignia, y un resumen de cuándo el Ganbantein borró áreas del grupo.
- Soplón: una Oposición equivocada u olvidada en el jefe es un error grave.
- Muertes: el resumen señala el golpe que realmente mató, y reconoce la explosión de los Robovacs y el golpe del Aquila desde fuera de pantalla.
- Aquila: se mejoró el soporte de la pelea.

### 1.4.0

Resumen de la muerte en el widget, una previsión de XP mucho más precisa en sesiones largas y la vida del Aquila en la Línea de tiempo.

- Cuando mueres, el widget muestra por 10 s qué te mató: el monstruo con el sprite del juego, el golpe final con su propiedad y las mayores fuentes de daño de los 5 s anteriores. Clic para cerrar; se puede desactivar en el menú.
- El resumen también cubre trampas, Unión Solar, Dolor Máximo (con el golpe que se reflejó) y vida perdida sin golpe visible, y el mensaje cambia si vuelves a morir en la misma pelea.
- XP: previsión del próximo nivel mucho más precisa. En las dos sesiones de casi 1 hora que probamos, el error medio bajó de 5 a 12 min a 1 a 2,5 min, y la previsión quedó a menos de 2 min de la hora real en el 52% al 90% del tiempo (antes, 10% a 20%). La XP estimada, que fallaba un 20%, ahora falla un 3%.
- XP: cada subida de nivel corrige la estimación al momento, y la cuenta sigue en el nivel nuevo.
- XP: las grabaciones de menos de 10 min o 1% del nivel ya no calibran, y la previsión aparece después de ese tiempo.
- Aquila: la dificultad se reconoce sola, y la Línea de tiempo muestra su vida con la regeneración y las rupturas de defensa (valores estimados con las peleas que tenemos).
- Muertes: overkill y causa correctos aunque la vida baje con retraso, como con Dolor Máximo.
- Línea de tiempo: los lanzamientos instantáneos ya no aparecen repetidos.
- Buffs y Debuffs: los gráficos explican qué buffs quedan fuera.
- Milagro en el pie legible en el tema Claro.

### 1.3.1

Lex Aeterna contada bien, daño atribuido a cada jugador y todo el grupo en la Línea de tiempo.

- Buffs y Debuffs: cada Lex Aeterna duplica el próximo golpe, aunque el Cardenal use varias por segundo. Antes solo contaba la primera de cada secuencia.
- Línea de tiempo: todo el grupo aparece en la lista de jugadores, incluso quien no ataca, como el Cardenal.
- Buffs y Debuffs: la tabla de buffs mide la pelea elegida, no la sesión entera (el combate de antes bajaba el tiempo activo).
- Buffs y Debuffs: nuevo gráfico con el daño atribuido a cada jugador, sumando lo que aportaron sus efectos (Cometa y Explosión Floreciente del Archimago, Garra Tenebrosa, Lex del Cardenal...).

### 1.3.0

Drops con colores que se pueden ocultar, información fija en el widget y XP comparada entre grabaciones.

- Drops con colores por tipo: equipo, carta, carta de MVP, refinamiento, alquimia/cocina y objetos de los episodios 17 en adelante. Los colores se cambian en el análisis.
- Clic derecho en un drop: ocultarlo hasta cerrar el programa o para siempre. Se deshace en "Objetos ocultos".
- Los drops favoritos quedan en el orden en que los marcaste.
- Fija hasta dos datos en el widget, como la XP por minuto, y velos en cualquier pestaña.
- XP: compara con otra grabación del mismo personaje.
- XP: % del nivel primero y el número después, muertes por minuto y un gráfico más fácil de leer.
- XP: elige qué objetos de evento siguen valiendo.
- Sonido corto opcional con HP bajo en União (apagado; ⋯ › Sonidos).
- Línea de tiempo: "Jugadores marcados" muestra solo a esos jugadores, y las curas de efectos aparecen como cura recibida.

### 1.2.5

Estimación de XP más precisa.

- El Milagro multiplica los otros bonos.
- El bono del manual viene del replay.

### 1.2.4

Corrige el widget que dejaba de actualizarse.

- Pasar el mouse por la estrella de los drops ya no congela el widget.
- Estrella más fácil de clicar y lista de drops que se desplaza más rápido.
- Los replays grandes abren mucho más rápido.
- XP: tiempo hasta el próximo nivel.
- La lista de bonos de XP muestra si cada bono estaba activo.

### 1.2.3

Milagro más fiel al juego y drops favoritos.

- Un nuevo Milagro renueva la hora, y el Milagro sigue después de morir o cambiar de mapa.
- Los bonos de evento de los objetos quedan apagados hasta que los marques.
- Drops: marca favoritos con la estrella; quedan arriba.
- Línea de tiempo: las habilidades de los jugadores aparecen en la lista desde el inicio.
- Nombres de las habilidades nuevas del último parche.

### 1.2.2

XP de los monstruos nuevos.

- Monstruos del episodio 19 y de la Biosfera [Eco] con XP.
- Evento del servidor: elección rápida de +50%, +100% o +200%.
- Sonido del Milagro más bajo, con volumen ajustable.

### 1.2.1

Pestañas del análisis sin nombres cortados.

- Los nombres de las pestañas caben en la ventana.

### 1.2.0

Nuevo nombre, Replay Master, y las pestañas Equipo, Drops y XP.

- Equipo: lo que llevabas puesto, con el personaje dibujado.
- Drops: lo que recogiste, lo que recogieron otros y lo que quedó en el suelo.
- XP: estimación de tus muertes, con bonos, XP por minuto y por hora, y gráfico.
- Buffs y Debuffs: cuánto daño aportó cada efecto.
- Milagro: el widget lo celebra y muestra cuánto falta.
- Soplón: zona de riesgo, golpes fuera de sincronía y Cenizas Volcánicas.
- Botón /where con el mapa y las coordenadas.
- Pruebas de cualquier replay, no solo del muñeco.

### 1.1.0

Línea de tiempo de las peleas contra jefes.

- Línea de tiempo: DPS, HP del jefe, debuffs, muertes y habilidades en la misma pantalla.
- DPS activo: el DPS solo en el tiempo en que cada uno estaba golpeando.
- HP del jefe por la dificultad, deducida del daño.
- Soplón: quién atacó antes de la Garra Tenebrosa y Vínculo Celestial.

### 1.0.3

Corrige el error "ordinal 380" que impedía abrir el programa en algunos PCs.

### 1.0.2

Pequeñas correcciones en los nombres en inglés y español.

### 1.0.1

Nombres en tu idioma y monstruos nuevos.

- Habilidades, buffs, clases, monstruos y objetos con los nombres del juego en inglés y español.
- Nombres correctos para los monstruos nuevos.
- Encuentra las carpetas Replay de todas las instalaciones del juego.

### 1.0.0

Primera versión pública.

- Widget de DPS en vivo, ventana de análisis y Soplón, en portugués, inglés y español.
