# Replay Master

Medidor de DPS e análise de replays para Ragnarok Online (ROLatam).

**[⬇ Baixar / Download / Descargar](https://github.com/carlucio7/dps-ragnarok/releases/latest)** · Windows · português, English, español

[Português](#português) · [English](#english) · [Español](#español) · [Novidades](CHANGELOG.md)

---

## Português

Um widget que mostra o seu DPS e o ranking do grupo em tempo real, lendo a gravação de replay do próprio jogo.

- **Widget:** DPS ao vivo, ranking do grupo, skills, alvos, drops e XP. Fixe até duas informações para ver em qualquer aba. Ele avisa quando o chefe muda (propriedade, tamanho, Dor Máxima, defesa), mostra o que te matou e resume a luta quando o chefe morre.
- **Análise completa:** jogadores, monstros, equipamento, drops, XP, DPS no tempo, buffs, mortes e testes de build.
- **Linha do tempo:** cada luta contra chefe com DPS, HP do chefe, debuffs, mortes e skills.
- **Dedo Duro:** o que faltou nas lutas contra chefe (buffs, debuffs, Garra Sombria, Oposição, Vulcão e Insígnia, mortes).
- **XP:** estimativa por minuto e por hora, tempo até o próximo nível, progresso das caças e comparação entre gravações. O modo automático se corrige com a XP exata.
- **Copiar imagem:** o widget e a análise viram imagem pronta para colar no Discord, com a opção de esconder os nomes.
- **Drops:** coloridos por tipo, com favoritos e itens ocultos.

### Como usar

1. Baixe o `.zip`, extraia e abra o `ReplayMaster.exe`. Não precisa instalar.
2. No jogo, comece a gravar um replay. O widget acha a gravação sozinho.
3. Botão direito no widget abre as opções; o botão de gráfico abre a análise.

### Segurança

- Só lê os arquivos de replay e os dados do jogo instalado. Não mexe na memória do jogo, não captura a rede e não acessa a internet. Para o lembrete de gravação desligada, olha apenas se o jogo está aberto.
- Confira o SHA-256 do `.exe` com o da página da release. Baixe só pelo link oficial.
- Não é oficial da Gravity nem da ROLatam.

### Limites

- Só conta o que aparece na sua tela.
- A XP é uma estimativa: o replay não grava a XP ganha.

---

## English

A widget that shows your DPS and the party ranking in real time by reading the game's own replay recording.

- **Widget:** live DPS, party ranking, skills, targets, drops and XP. Pin up to two pieces of info to see on any tab. It warns when the boss changes (property, size, Max Pain, defense), shows what killed you and sums up the fight when the boss dies.
- **Full analysis:** players, monsters, equipment, drops, XP, DPS over time, buffs, deaths and build tests.
- **Timeline:** each boss fight with DPS, boss HP, debuffs, deaths and skills.
- **Snitch:** what was missing in boss fights (buffs, debuffs, Dark Claw, Opposition, Volcano and Insignia, deaths).
- **XP:** estimate per minute and per hour, time to the next level, hunt progress and comparison between recordings. The automatic mode corrects itself with the exact XP.
- **Copy image:** the widget and the analysis become an image ready to paste on Discord, with the option to hide names.
- **Drops:** colored by type, with favorites and hidden items.

**How to use:** download the `.zip`, extract it and open `ReplayMaster.exe`. Start recording a replay in the game. Right-click the widget for options.

**Safety:** it only reads replay files and the installed game's data. It doesn't touch the game's memory, capture the network or go online. For the recording-off reminder it only checks whether the game is open. Check the `.exe` SHA-256 against the release page. Unofficial.

---

## Español

Un widget que muestra tu DPS y el ranking del grupo en tiempo real, leyendo la grabación de replay del propio juego.

- **Widget:** DPS en vivo, ranking del grupo, habilidades, objetivos, drops y XP. Fija hasta dos datos para verlos en cualquier pestaña. Avisa cuando el jefe cambia (propiedad, tamaño, Dolor Máximo, defensa), muestra qué te mató y resume la pelea cuando el jefe muere.
- **Análisis completo:** jugadores, monstruos, equipo, drops, XP, DPS en el tiempo, buffs, muertes y pruebas de build.
- **Línea de tiempo:** cada pelea contra jefe con DPS, HP del jefe, debuffs, muertes y habilidades.
- **Soplón:** qué faltó en las peleas contra jefes (buffs, debuffs, Garra Tenebrosa, Oposición, Volcán e Insignia, muertes).
- **XP:** estimación por minuto y por hora, tiempo hasta el próximo nivel, progreso de las cazas y comparación entre grabaciones. El modo automático se corrige con la XP exacta.
- **Copiar imagen:** el widget y el análisis se convierten en una imagen lista para pegar en Discord, con la opción de ocultar los nombres.
- **Drops:** con colores por tipo, favoritos y objetos ocultos.

**Cómo usar:** descarga el `.zip`, extráelo y abre `ReplayMaster.exe`. Empieza a grabar un replay en el juego. Clic derecho en el widget para las opciones.

**Seguridad:** solo lee los archivos de replay y los datos del juego instalado. No toca la memoria del juego, no captura la red y no se conecta a internet. Para el recordatorio de grabación apagada solo mira si el juego está abierto. Comprueba el SHA-256 del `.exe` con la página de la release. No oficial.

---

## Para desenvolvedores

Python 3 (32 bits) com Tkinter. Detalhes de como cada número é calculado, o formato `.rrf` e as regras do Dedo Duro: [docs/TECNICO.md](docs/TECNICO.md).

```
python tests\logic_test.py      # testes sem janela
python tests\visual_test.py     # prints de todas as telas
python tools\build_release.py   # pacote release\ReplayMaster-VERSÃO-win.zip + SHA-256
```

O formato foi entendido com a ajuda do [rrfparser](https://github.com/adsonpleal/rrfparser) (MIT, Adson Leal). Dados de skills, monstros e itens do [rAthena](https://github.com/rathena/rathena) (GPL-3.0) e do jogo instalado (© Gravity).

Licença: [GPL-3.0](LICENSE).
