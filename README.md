# Replay Master

Medidor de DPS e análise de replays para Ragnarok Online (ROLatam).

**[⬇ Baixar / Download / Descargar](https://github.com/carlucio7/dps-ragnarok/releases/latest)** · Windows · português, English, español

[Português](#português) · [English](#english) · [Español](#español) · [Novidades](CHANGELOG.md)

---

## Português

Um widget que mostra o seu DPS e o ranking do grupo em tempo real, lendo a gravação de replay do próprio jogo.

- **Widget:** DPS ao vivo, ranking do grupo, skills, alvos, drops e XP. Fixe até duas informações para ver em qualquer aba. Quando você morre, ele mostra o que te matou.
- **Análise completa:** jogadores, monstros, equipamento, drops, XP, DPS no tempo, buffs, mortes e testes de build.
- **Linha do tempo:** cada luta contra chefe com DPS, HP do chefe, debuffs, mortes e skills.
- **Dedo Duro:** o que faltou nas lutas contra chefe (buffs, debuffs, Garra Sombria, mortes).
- **XP:** estimativa por minuto e por hora, tempo até o próximo nível e comparação entre gravações.
- **Drops:** coloridos por tipo, com favoritos e itens ocultos.

### Como usar

1. Baixe o `.zip`, extraia e abra o `ReplayMaster.exe`. Não precisa instalar.
2. No jogo, comece a gravar um replay. O widget acha a gravação sozinho.
3. Botão direito no widget abre as opções; o botão de gráfico abre a análise.

### Segurança

- Só lê os arquivos de replay e os dados do jogo instalado. Não mexe na memória do jogo, não captura a rede e não acessa a internet.
- Confira o SHA-256 do `.exe` com o da página da release. Baixe só pelo link oficial.
- Não é oficial da Gravity nem da ROLatam.

### Limites

- Só conta o que aparece na sua tela.
- A XP é uma estimativa: o replay não grava a XP ganha.

---

## English

A widget that shows your DPS and the party ranking in real time by reading the game's own replay recording.

- **Widget:** live DPS, party ranking, skills, targets, drops and XP. Pin up to two pieces of info to see on any tab. When you die, it shows what killed you.
- **Full analysis:** players, monsters, equipment, drops, XP, DPS over time, buffs, deaths and build tests.
- **Timeline:** each boss fight with DPS, boss HP, debuffs, deaths and skills.
- **Snitch:** what was missing in boss fights (buffs, debuffs, Dark Claw, deaths).
- **XP:** estimate per minute and per hour, time to the next level and comparison between recordings.
- **Drops:** colored by type, with favorites and hidden items.

**How to use:** download the `.zip`, extract it and open `ReplayMaster.exe`. Start recording a replay in the game. Right-click the widget for options.

**Safety:** it only reads replay files and the installed game's data. It doesn't touch the game's memory, capture the network or go online. Check the `.exe` SHA-256 against the release page. Unofficial.

---

## Español

Un widget que muestra tu DPS y el ranking del grupo en tiempo real, leyendo la grabación de replay del propio juego.

- **Widget:** DPS en vivo, ranking del grupo, habilidades, objetivos, drops y XP. Fija hasta dos datos para verlos en cualquier pestaña. Cuando mueres, muestra qué te mató.
- **Análisis completo:** jugadores, monstruos, equipo, drops, XP, DPS en el tiempo, buffs, muertes y pruebas de build.
- **Línea de tiempo:** cada pelea contra jefe con DPS, HP del jefe, debuffs, muertes y habilidades.
- **Soplón:** qué faltó en las peleas contra jefes (buffs, debuffs, Garra Tenebrosa, muertes).
- **XP:** estimación por minuto y por hora, tiempo hasta el próximo nivel y comparación entre grabaciones.
- **Drops:** con colores por tipo, favoritos y objetos ocultos.

**Cómo usar:** descarga el `.zip`, extráelo y abre `ReplayMaster.exe`. Empieza a grabar un replay en el juego. Clic derecho en el widget para las opciones.

**Seguridad:** solo lee los archivos de replay y los datos del juego instalado. No toca la memoria del juego, no captura la red y no se conecta a internet. Comprueba el SHA-256 del `.exe` con la página de la release. No oficial.

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
