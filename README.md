# DPS Ragnarok — medidor de DPS para Ragnarok Online (ROLatam)

**[⬇ Baixar a versão mais recente / Download the latest version / Descargar la última versión](https://github.com/carlucio7/dps-ragnarok/releases/latest)**
(Windows · `DpsRagnarok-…-win.zip` · confira o SHA-256 da página da release / check the SHA-256 on the release page / comprueba el SHA-256 en la página de la release)

- 🇧🇷 Widget que mostra o seu DPS e o ranking do grupo em tempo real, lendo a gravação de replay do próprio jogo. Tem análise completa e a aba Dedo Duro (o que faltou nas lutas contra chefes).
- 🇺🇸 Widget that shows your DPS and the party ranking in real time by reading the game's own replay recording. Includes a full analysis window and the Snitch tab (what was missing in boss fights).
- 🇪🇸 Widget que muestra tu DPS y el ranking del grupo en tiempo real, leyendo la grabación de replay del propio juego. Incluye análisis completo y la pestaña Soplón (qué faltó en las peleas contra jefes).

Programa em português, inglês e espanhol · Licença / License / Licencia: [GPL-3.0](LICENSE) · Não oficial / Unofficial / No oficial.

---

Widget que mostra o seu DPS e o ranking de dano de todo mundo que está no seu
campo de visão, em tempo real, lendo a **gravação de replay** do próprio jogo.

Não lê memória do jogo, não captura pacotes de rede e não usa OCR. Ele só lê o
arquivo `.rrf` que o cliente grava em `C:\Gravity\Ragnarok\Replay`, por isso
não interage com o GameGuard.

## Como usar

1. Baixe o `.zip` da [página de releases](https://github.com/carlucio7/dps-ragnarok/releases/latest),
   extraia e abra o `DpsRagnarok.exe` (ou rode `python dpsmeter.py` a partir do código).
2. No jogo, comece a gravar um replay.
3. O medidor acha o arquivo novo sozinho e começa a contar. Quando a gravação
   termina, o último resultado continua na tela.

Também dá para abrir um replay já salvo (botão direito › *Abrir replay salvo…*,
ou arrastar o `.rrf` em cima do `.exe`).

**Pasta do jogo:** o medidor acha sozinho as pastas Replay de todas as
instalações do jogo: pelo registro do Windows (onde o instalador disse que
instalou) e pelas pastas de costume em todos os discos fixos. Ele segue a
gravação mais nova de qualquer uma delas. Se não achar nenhuma, o meio do widget
avisa, e um clique ali abre a escolha da pasta (vale a pasta do jogo ou a pasta
Replay dela).

**Monstros novos:** alguns monstros (os da Biosfera de Varmundt e, daqui para
frente, os do episódio 19) chegam no replay com uma chave no lugar do nome,
como `␜VpIB␜`. O medidor traduz a chave com as tabelas `data/i18n/sc/*.csv` que
ficam dentro do `data.grf` do próprio jogo, em português, inglês ou espanhol.
Ele lê o arquivo uma vez, em segundo plano e só para leitura, e guarda um cache
em `%APPDATA%\RODpsMeter\nomes_do_jogo.json`, que é refeito quando o jogo é
atualizado (`clientdata.py`). Monstro sem nome em lugar nenhum aparece como
"Monstro 21559" (o id do monstro). As mesmas tabelas dão os nomes de skills,
buffs, classes, monstros e itens em inglês e espanhol.

Novidades de cada versão: [CHANGELOG.md](CHANGELOG.md).

O widget é controlado só pelo mouse (não tem teclas de atalho) e clicar nele
não tira o foco do jogo: as teclas continuam indo para o Ragnarok. Passe o mouse
sobre um botão para ver no rodapé o que ele faz; o botão direito abre todas as
opções.

## O que aparece

- **Número grande:** o seu DPS (em tudo ou na luta escolhida).
- **agora:** dano dos últimos 5 s (só enquanto a luta está acontecendo).
- **Abas:**
  - **Grupo:** dano de todos os jogadores visíveis. O dano de invocações,
    homúnculos e skills de chão conta para o dono.
  - **Skills:** o seu dano por skill (% e número de acertos).
  - **Alvos:** em quem você bateu.
- **Tudo ▾ / Luta atual ▾:** o botão mostra o que está na tela; clique para
  escolher.
  - *Tudo* (padrão) soma desde o início (ou desde *Zerar*) e divide só pelo
    tempo em combate.
  - *Luta atual* mostra só a luta mais recente. Uma luta termina depois de 15 s
    sem dano (configurável no mesmo menu). As lutas anteriores aparecem na
    lista pelo nome do alvo, e ‹ › no rodapé passa de uma para outra.
- **Contar dano em:** *Todos os monstros* ou *Só MVPs e bonecos de treino*
  (ignora monstros normais e minions, como as Almas Mortas do Betelgeuse).
  Invocações de jogadores (ex.: Esfera Marinha) nunca contam como alvo: bater
  nelas não é dano no chefe, e a explosão delas conta para o dono.
- **MVPs em fases (Betelgeuse):** cada fase nasce com um AID novo. As fases são
  juntadas numa luta só ("Betelgeuse ★ (3 fases)"), e o tempo de troca de fase
  não entra no DPS. Mesma regra do Ragna Recap / ragreplaystats. A lista de
  chefes com fases fica em `meter.PHASED_BOSSES`.
- **Tamanho:** arraste o canto de baixo à direita para mudar largura e número
  de linhas. Ctrl + roda (ou Shift + arrastar o canto) muda o zoom. Em larguras
  maiores, o Grupo mostra DPS e % juntos e a aba Skills mostra "acertos" por
  extenso; o número grande encolhe se não couber.

## Análise completa (botão de gráfico)

Janela separada, atualizada ao vivo, com as mesmas contas do Ragna Recap
(conferidas contra o site com o mesmo replay). O recorte pode ser a sessão
inteira, o último encontro (acompanha a luta) ou um encontro anterior. Cada
jogador tem uma cor fixa em todas as tabelas e gráficos. Ctrl + roda muda o
tamanho de tudo; os cartões se reorganizam conforme a largura. **Copiar
ranking** copia o ranking do recorte em texto (para colar no Discord/WhatsApp).

- **Resumo:** o seu dano e % do grupo, DPS em combate e do 1º ao último golpe,
  acertos/erros, maior golpe (skill e alvo), skill mais usada, abates, dano
  recebido, mortes, seus maiores golpes e de onde veio o dano que você levou.
- **Jogadores:** dano, DPS, %, acertos, erros, maior golpe, monstros atingidos
  e abates (golpe fatal). Para o jogador escolhido: habilidades (acertos, dano
  total e médio, hits médios, cast médio), monstros atingidos e a linha do
  tempo de todos.
- **Monstros:** dano recebido, acertos, atacantes, HP máx., tempo até abate e
  quem abateu. Para o monstro escolhido:
  - dano por jogador (barras);
  - linha do tempo, uma linha por jogador, com as trocas de fase marcadas;
  - habilidades usadas contra ele (por jogador e classe);
  - habilidades do próprio monstro: com dano, de suporte/debuff ("usos sem
    dano"), alvos e tempo de conjuração, com filtro por alvo.
- **Análise de DPS:** gráfico de DPS de qualquer jogador, com a média móvel de
  5 s e a média da janela. Arraste para escolher um trecho e veja as
  estatísticas dele (dano, DPS do 1º ao último golpe, intervalo médio, maior
  intervalo, maior golpe) e qual habilidade deu mais dano ali.
- **Buffs:** seus buffs com o % do tempo em combate (vivo) em que estiveram
  ativos, quantas vezes foram aplicados, se já estavam no início e quanto falta
  para acabar (ao vivo). Buffs de grupo (a lista do simulador da LATAM Tools) e
  consumíveis com menos de 80% aparecem em vermelho. Embaixo, os debuffs no
  monstro escolhido com o % do tempo em que ele estava apanhando, com os nomes
  do simulador (Cometa, Pólen, Gravitação, Geladinho, Empalamento, Infecção,
  Intoxicação, Oratio, Ataque Surpresa...) e o nome do cliente entre parênteses.
  O Impacto Explosivo não aparece: o jogo não manda um status para ele. Status
  de sistema (pós-conjuração, recarga de item) ficam de fora.
- **Mortes:** cada morte de jogador com a causa, o golpe fatal, o HP antes e o
  **overkill** (quanto o golpe passou do HP que restava). O recap mostra os 10 s
  antes da morte: golpes recebidos, HP e efeitos ativos. HP só é conhecido para
  você e para o seu grupo. Mortes pela **União Solar, Lunar e Estelar** (Mestre
  Taekwon: cada ataque custa 2% do HP máx. e atacar com 20% ou menos mata) são
  reconhecidas pela opção "voando" que o servidor manda, com o HP no ataque e o
  HP gasto pela União. **Armadilhas do mapa** (Torre da Constelação: dano em %
  do HP máx., irredutível, de 8% a 80% conforme a dificuldade e o HP do chefe)
  não mandam pacote de dano, só um efeito (537) e a queda de HP no mesmo
  instante; o recap mostra a % e estima o overkill da armadilha que matou a
  partir das que não mataram. Outras quedas de HP sem golpe aparecem como "HP
  perdido (efeitos no momento: N)" — os efeitos de outros encontros (ex.: OGH)
  ganham nome em `rrf.MAP_DAMAGE_EFFECTS` quando forem identificados. Quando
  não há explicação no replay, o recap diz isso em vez de inventar uma causa.
- **Testes:** histórico de testes de build guardado no PC
  (`%APPDATA%\RODpsMeter\testes.json`). Encontros contra os bonecos de treino
  são salvos sozinhos; qualquer recorte pode ser salvo com um rótulo. Cada teste
  guarda DPS, skills, buffs e o equipamento vestido (refino, cartas,
  encantamentos, grau e opções). Escolha um teste para comparar com o anterior
  do mesmo personagem, ou dois com Ctrl + clique: resumo (A × B em %), skills,
  equipamento (slots diferentes em destaque) e buffs.

- **Dedo Duro:** o que faltou e o que deu errado em cada luta contra chefe. MVPs e
  chefes de instância vêm primeiro e em destaque (depois os bonecos de treino).
  Quem está no grupo e quem está fora ficam em listas separadas: buffs de quem
  está fora do grupo não chegam no replay, então ali só aparecem dano, mortes,
  Garra Sombria e elemento das skills. Tudo é olhado só no **clímax** (depois
  que o chefe perdeu os primeiros 10% do HP — as 3 fases do Betelgeuse são uma
  barra só; enquanto ele não morre, a conta usa o dano feito até agora),
  separado por fase e só com quem está vivo. **Copiar relatório** copia o texto
  para colar no Discord/WhatsApp.
  - **Buffs de grupo** que faltaram em quem bate (físico ou mágico, pelo tipo de
    dano), só quando a classe que dá o buff está no grupo (ex.: Manejo Perfeito
    e Avanço Sísmico só com Engenheiro). Os alertas juntam os buffs que
    faltaram nas mesmas pessoas e dizem quem dá; se a recarga (ou o AP) ainda
    não tinha voltado no começo da fase, diz quando voltaria. Bênção e Aumentar
    Agilidade contam também quando vêm da Clementia e do Canto Candidus.
    - **Grave (vermelho):** Manejo Perfeito (com Engenheiro) tem que ficar o
      tempo todo: abaixo de 90% já é grave. Os outros buffs principais,
      abaixo de 50%. Bênção, Aumentar Agilidade e Grito de Guerra (saem ao
      morrer) são graves quando faltaram antes da primeira morte; não renovar
      depois de ressuscitar é atenção.
    - **Atenção (amarelo):** buffs e debuffs de recarga alta ou que gastam AP
      (ex.: Avanço Sísmico: o que foi usado numa fase pode não voltar na
      seguinte; Reencarnação das Almas: nem todo Asceta tem) e buffs de 60 s
      ou menos (Impositio Manus, Lauda Agnus, Lauda Ramus).
    - **Alvo único nunca é vermelho** (Talismã dos Elementos, Encanto de
      Órion e os do Cardeal: Benedictum, Religio, Presens Acies, Argutus Telum
      e Argutus Vita): quem gravou talvez não precise. O Talismã dos Elementos
      é cobrado o tempo todo em quem recebe, mas como atenção. Benedictum e
      Argutus Telum só são cobrados de quem bate físico; Religio e Argutus
      Vita, de quem bate mágico.
    - **Competentia** sai ao morrer e custa AP demais: só é cobrada até a
      primeira morte de cada um.
    - Força Violenta ficou de fora (quase não muda o dano).
  - **Debuffs no chefe** que faltaram ou duraram pouco. Cada fase é um monstro
    novo e chega sem nada. O **Pólen (Florescer)** tem que ficar o tempo todo:
    o alerta diz se o Magus estava com Clímax (dava para usar o Florescer:
    grave) ou se morreu e perdeu o Clímax (o Pólen fica no chefe até acabar,
    mas o Clímax sai na morte e o Magus volta sem AP para usar de novo: só
    atenção).
  - **Garra Sombria:** se o chefe usa Dor Máxima (reflete dano), ela tem que
    ficar o tempo todo. Cada buraco sem Garra mostra, para cada Executor, se a
    dele estava em recarga (e quanto faltava), disponível ou se ele estava
    morto, e quantos golpes foram refletidos ali. A recarga sai dos usos da
    skill que aparecem no replay (60 s).
  - **Mortes:** de 2 a 7 s morto até ressuscitar, e os buffs de recarga longa
    ou AP alto que não voltaram depois de ressuscitar. Mais de 7 s morto é
    tratado como provável wipe (o grupo vai se reagrupar ou desistir) e fica
    fora do relatório, assim como quem morreu no fim e não voltou; essas
    mortes continuam na tabela de mortes.
  - **Elemento:** fogo durante o Florescer (pelos conversores e encantamentos
    visíveis; o elemento próprio da arma não aparece no replay) e ataques com
    desvantagem contra o elemento do chefe (Betelgeuse: Neutro 2, do Divine
    Pride; os outros vêm do rAthena).
  - **Veneno:** arma com veneno × chefe com Potencializar Veneno.
  - Na coluna Fase, "Todas as fases" (ou "Luta inteira", com chefe de uma
    fase só) é a luta toda, não a fase 1.
  - De quem gravou, todos os buffs aparecem, inclusive os que já estavam
    ativos quando a gravação começou. Dos outros membros do grupo, a maioria
    dos buffs aparece quando começa e quando acaba. "Ninguém do grupo
    recebeu" diz se isso foi verificado na luta toda ou se o começo da
    gravação ficou sem dar para saber. O Avanço Sísmico (Investida) só
    aparece no próprio Engenheiro, então não é cobrado como buff de grupo.
  - Alguns buffs o jogo **não mostra nos outros jogadores**: o início nunca
    chega e o fim só chega quando acaba sozinho (na morte, nem isso).
    Competentia, Benedictum, Presens Acies, Argutus Vita e Telum, Lauda Agnus
    e Ramus, Reencarnação das Almas e Talismã do Guerreiro e do Mago só são
    cobrados de quem gravou; nos outros aparecem como "?".
  - Buffs que os outros já tinham quando a gravação começou só aparecem no
    replay quando acabam. Até lá o estado é "?" e não vira acusação; se a
    gravação passa de 6 min sem nenhum aviso de um buff, ele não estava
    ativo. Para o Dedo Duro ver tudo, comece a gravar antes de buffar.

O widget também avisa no rodapé quando um buff importante acaba no meio da luta,
quando você morre (com a causa e o overkill) e, com a União Solar ativa, quando o
HP chega a 28% e a 22% (abaixo de 20% o próximo ataque mata). Os avisos e o
salvamento automático podem ser desligados no botão direito.

## Mouse

| Ação | O que faz |
|---|---|
| clique nas abas / botões | trocar aba, Tudo ⇄ Luta, zerar, análise, fixar |
| ‹ › no rodapé | luta anterior / próxima |
| arrastar o widget | mover |
| arrastar o canto | largura e número de linhas |
| Ctrl + roda (ou Shift + arrastar o canto) | zoom (no widget e na análise) |
| botão direito | todas as opções (mostrar, contar dano em, cor, tamanho, avisos, pasta) |

Configuração e `erros.log` ficam em `%APPDATA%\RODpsMeter` (ou na variável
`RODPS_CONFIG`).

## Limites

- Só aparece o dano que o seu cliente recebe: jogadores fora da tela não são
  contados.
- Com vários clientes gravando ao mesmo tempo, o medidor segue a gravação
  mais nova. Para escolher outra, abra o arquivo manualmente.
- Crítico: o servidor da LATAM quase nunca marca o acerto como crítico, então
  a contagem de críticos não é confiável.
- Nomes em inglês e espanhol vêm do jogo instalado. Sem o jogo, o medidor usa a
  cópia do pacote (`data/names.json`), que pode estar desatualizada. Skills de
  monstro que o cliente não nomeia usam a descrição do rAthena (inglês) ou o
  catálogo do `i18n.py` (espanhol); o que faltar aparece em português.

## Como funciona (resumo do formato `.rrf`)

- Cabeçalho com a data da gravação. A chave do XOR vem dessa data:
  palavra *i* = `(k1 + i + 1) * k2`.
- O cliente escreve cada pacote no arquivo na hora (atraso < 1 s), mas só
  preenche a tabela do cabeçalho ~9 s depois de começar a gravar. Até lá o
  medidor acha os containers e o início do fluxo percorrendo o arquivo: cada
  container abre com um chunk marcador (id próprio, tamanho 0), o que funciona
  mesmo quando a gravação começa à 0 h e a chave XOR fica fraca.
- Containers com o estado inicial: personagem (AID), nome, mapa, entidades
  visíveis e a lista de skills.
- No fim do arquivo fica o fluxo de pacotes servidor→cliente. Cada registro é
  `id, tempo_ms, tamanho, pacote`, e o fluxo cresce durante a gravação.
- Pacotes usados:
  - dano: `0x008a`, `0x02e1`, `0x08c8`, `0x01de`
  - spawns: `0x09fe`, `0x09ff`, `0x0915`, `0x09fd`, `0x0857`
  - skill de chão: `0x09ca`
  - buffs/debuffs: `0x0196`, `0x043f`, `0x0983` (com o nível/força do efeito),
    e o container 18 (o que já estava ativo no início); HP: `0x00b0` (você) e
    `0x080e` (grupo — é também como o medidor sabe quem está no grupo)
  - ressurreição: `0x0148`
  - equipamento: container 8 (itens no início, registros tag/tamanho/valor) e
    `0x0999`/`0x099a`/`0x0a37` (trocas e itens novos)
  - skill sem dano: `0x011a`, `0x09cb`; conjuração: `0x013e`, `0x07fb`
    (repetições em até 200 ms são ignoradas, como no rrfparser)
  - morte: `0x0080`

O formato foi entendido com a ajuda do projeto
[rrfparser](https://github.com/adsonpleal/rrfparser) / [ragreplaystats](https://github.com/adsonpleal/ragreplaystats)
(MIT, Adson Leal). Os nomes em `data/` (skills, classes, monstros, status, itens, opções) vêm desse
projeto, que os extraiu do cliente do jogo (© Gravity). `data/efst.json` (ids de
status e as skills que aplicam cada um) é gerado do [rAthena](https://github.com/rathena/rathena)
(GPL-3.0) por `tools/build_efst.py`, e `data/rathena.json` (skills de cada classe,
recarga, custo de AP, elemento das skills e dos monstros, tabela elemental) por
`tools/build_rathena.py`; os nomes de buffs/debuffs da lista do
[simulador da LATAM Tools](https://simulador.latam-tools.com.br/) foram ligados a esses ids pela skill.

## Desenvolvimento

```
python tests\logic_test.py                    # decodificador e agregador (sem janela)
python tests\visual_test.py SAIDA [replay]    # prints de todas as telas (janela fica atrás)
python tests\sizes_test.py SAIDA [replay]     # prints do widget em vários tamanhos, larguras e linhas
python tools\summary.py replay.rrf --all      # resumo no terminal
python tools\tail_test.py                     # mede o atraso de escrita numa gravação nova
python make_icon.py                           # gera dpsmeter.ico
python tools\build_efst.py PASTA_RATHENA      # gera data\efst.json (status.hpp, status.yml, skill_db.yml)
python tools\build_rathena.py PASTA_RATHENA   # gera data\rathena.json (classes, skills, monstros, elementos)
python -m PyInstaller --noconfirm --onefile --windowed --name DpsRagnarok --icon dpsmeter.ico --add-data "dpsmeter.ico;." --add-data "data;data" dpsmeter.py
python tools\build_names.py [PASTA_DO_JOGO]   # gera data\names.json (nomes em inglês e espanhol do cliente)
python tools\build_release.py                 # pacote para compartilhar: release\DpsRagnarok-VERSÃO-win.zip + SHA-256
python tools\demo_shots.py SAIDA              # prints de divulgação (nomes fictícios) em pt, en e es
```

Idiomas: os textos ficam em português no código, dentro de `_()`, e as traduções
para inglês e espanhol ficam em `i18n.py`. Texto novo na tela precisa de `_()` e de
uma linha no catálogo. Os testes rodam em português (`RODPS_LANG=pt`); para ver
outro idioma, rode com `RODPS_LANG=en` ou `es`. A versão fica em `version.py` e as
mudanças de cada versão no [CHANGELOG.md](CHANGELOG.md).

Nomes do jogo em inglês e espanhol: `clientdata.py` lê do `data.grf` as tabelas do
cliente (`skillinfolist`, `stateiconinfo`, `pcjobnamegender`,
`addrandomoptionnametable`, `iteminfo_new` e `data/i18n/sc/*.csv`), que são Lua
compilado; `lub.py` executa esse bytecode só o bastante para montar as tabelas.

O `python` aqui é o Python 32 bits que já tem PyInstaller.
