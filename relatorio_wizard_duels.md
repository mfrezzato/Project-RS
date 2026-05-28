# Wizard Duels — Relatório Técnico de Desenvolvimento

**Disciplina:** Redes e Sistemas Distribuídos  
**Projecto:** Jogo multiplayer P2P em rede local  
**Stack:** Python · asyncio · gRPC · Kademlia DHT · Rich TUI  

---

## Índice

1. [Visão Geral do Projecto](#1-visão-geral-do-projecto)
2. [Arquitectura do Sistema](#2-arquitectura-do-sistema)
3. [Kademlia DHT — Como Funciona](#3-kademlia-dht--como-funciona)
4. [gRPC — Comunicação Entre Pares](#4-grpc--comunicação-entre-pares)
5. [Componentes do Código](#5-componentes-do-código)
6. [Mecânicas de Jogo](#6-mecânicas-de-jogo)
7. [Bugs Encontrados e Soluções](#7-bugs-encontrados-e-soluções)
8. [Alternativas de Implementação Consideradas](#8-alternativas-de-implementação-consideradas)
9. [Fluxo Completo de uma Sessão](#9-fluxo-completo-de-uma-sessão)
10. [Conclusões e Lições Aprendidas](#10-conclusões-e-lições-aprendidas)

---

## 1. Visão Geral do Projecto

**Wizard Duels** é um jogo de duelo de magos em tempo real jogado inteiramente no terminal, comunicando por rede local sem qualquer servidor central. Cada jogador executa o mesmo programa e os processos comunicam directamente entre si (P2P — *Peer-to-Peer*).

### 1.1 Objectivos do Projecto

| Objectivo | Tecnologia usada |
|-----------|-----------------|
| Comunicação em rede sem servidor | Kademlia DHT + gRPC |
| Descoberta de jogadores na rede | Kademlia DHT |
| Troca de mensagens de jogo (ataques, movimentos) | gRPC (Protocol Buffers) |
| Interface de terminal em tempo real | Rich (Python) |
| Concorrência (rede + input + lógica) | asyncio (Python) |

### 1.2 O Que o Jogo Faz

- Até N jogadores entram num **lobby** e esperam o início.
- Ao iniciar, cada jogador é teletransportado para uma **sala aleatória** de um mapa 3×3.
- Cada jogador escolhe um **elemento** (FOGO, GELO, AR, TERRA, NEGRO), cada um com ataques, skills e ultimatos diferentes.
- Os jogadores movem-se pelo mapa, encontram-se em salas e atacam-se.
- Quem morrer espera o fim da ronda. O último a sobreviver ganha a ronda.
- **4 vitórias de ronda** = campeão do torneio.

---

## 2. Arquitectura do Sistema

### 2.1 P2P Puro vs Servidor Central

A decisão mais importante do projecto foi **não ter servidor central**.

```
ABORDAGEM CLÁSSICA (cliente-servidor):

  Jogador A ──► Servidor ◄── Jogador B
                   │
               Estado do jogo
               (HP, salas, etc.)


ABORDAGEM DO PROJECTO (P2P puro):

  Jogador A ◄──────────────► Jogador B
      │                           │
  Estado local               Estado local
  (engine.py)                (engine.py)
      │                           │
      └──────── DHT ──────────────┘
             (descoberta)
```

**Vantagens do P2P escolhido:**
- Não existe ponto único de falha — o jogo continua mesmo que um jogador saia a meio.
- Cada máquina só precisa de comunicar com os outros jogadores directamente.
- Demonstra tecnologias distribuídas reais (DHT, gRPC assíncrono).

**Desvantagens:**
- Estado distribuído é mais difícil de sincronizar — cada máquina tem a sua cópia.
- Sem árbitro central, é necessário um protocolo de consenso para decidir quem ganhou.
- Mais propenso a inconsistências temporárias (dados "stale").

### 2.2 Dois Sistemas de Rede em Paralelo

O jogo usa **dois sistemas de rede completamente diferentes** ao mesmo tempo:

```
┌─────────────────────────────────────────────────────────┐
│                    WIZARD DUELS                         │
│                                                         │
│  ┌──────────────────┐      ┌───────────────────────┐   │
│  │   Kademlia DHT   │      │        gRPC           │   │
│  │  (porta 8468+)   │      │  (porta do utilizador)│   │
│  │                  │      │                       │   │
│  │ • Descoberta     │      │ • CastSpell           │   │
│  │ • Localização    │      │ • UpdatePosition      │   │
│  │   dos jogadores  │      │ • SendMessage         │   │
│  │ • Anúncio de     │      │ • SyncState           │   │
│  │   presença       │      │ • PlayerDied          │   │
│  │ • Sala actual    │      │ • Heartbeat           │   │
│  └──────────────────┘      └───────────────────────┘   │
│         │                            │                  │
│         └──── usados em conjunto ────┘                  │
└─────────────────────────────────────────────────────────┘
```

- **DHT** → "onde está o jogador X?" / "quem está na SALA_3?"
- **gRPC** → "o jogador X atacou-te com 22 de dano" / "o jogador X moveu-se para SALA_5"

---

## 3. Kademlia DHT — Como Funciona

### 3.1 O Que é uma DHT?

Uma **Distributed Hash Table** (Tabela de Hash Distribuída) é uma estrutura de dados distribuída que permite armazenar e recuperar pares chave-valor sem servidor central. Cada nó (processo) guarda uma parte dos dados e colabora na localização do resto.

**Analogia:** imagina uma lista telefónica partida em pedaços e distribuída por várias pessoas. Para encontrar o número de alguém, perguntas à pessoa mais próxima alfabeticamente e ela encaminha para quem sabe.

### 3.2 Kademlia Especificamente

Kademlia é o algoritmo DHT mais popular — usado no BitTorrent, Ethereum e IPFS.

**Princípios fundamentais:**

**1. Cada nó tem um ID de 160 bits** gerado aleatoriamente.

**2. Distância XOR:** a "distância" entre dois nós não é geográfica — é calculada com XOR nos seus IDs. Isto cria uma topologia de rede virtual.

```
dist(A, B) = ID_A XOR ID_B
```

**3. k-buckets:** cada nó mantém uma tabela de contactos organizada por distância XOR. Conhece bem os nós "próximos" e menos os "afastados".

**4. Lookup iterativo:** para encontrar um valor, contactas os k nós mais próximos da chave; eles devolvem os seus nós mais próximos, e assim por diante até chegar ao nó que guarda o valor.

```
LOOKUP("PLAYER_Jogador3"):

  Nó A → "não tenho, mas B e C estão mais perto"
  Nó B → "não tenho, mas D está ainda mais perto"
  Nó D → "tenho! valor = SALA_5|192.168.1.5:50052"
```

### 3.3 Como Usámos no Jogo

```
Estrutura dos valores na DHT:

  Chave:  "PLAYER_{player_id}"
  Valor:  "{room_id}|{ip}:{grpc_port}"

  Exemplo:
    "PLAYER_Jogador1" → "SALA_3|192.168.1.4:50051"
    "PLAYER_Jogador2" → "LOBBY|192.168.1.7:50052"
```

**Operações usadas no jogo:**

| Operação | Quando | O Que Faz |
|----------|--------|-----------|
| `announce_presence(id, ip, port, room)` | Ao entrar numa sala | Publica localização na DHT |
| `get_players_in_room(room)` | Ao atacar / mover | Descobre quem está na mesma sala |
| `remove_player(id)` | Ao morrer / sair | Remove da DHT (fica invisível) |
| `remove_from_room(id, room)` | Ao mudar de sala | Actualiza sala anterior |

### 3.4 Bootstrap Node — O Primeiro Jogador

O primeiro jogador a entrar é o **bootstrap node** — o "semente" da rede Kademlia. Quando outros jogadores se ligam, passam o IP do bootstrap para encontrar a rede.

```
python main.py JogadorA FOGO 50051             ← bootstrap (sem IP extra)
python main.py JogadorB GELO 50052 192.168.1.X ← cliente (passa IP do bootstrap)
```

**Problema descoberto durante o desenvolvimento:** o bootstrap node tem queries DHT menos fiáveis porque a replicação Kademlia demora algum tempo a propagar-se para o nó semente. Isto causava que o host não conseguia ver os outros como alvos.

**Solução:** usar `engine.players` (populado via gRPC SyncState, sempre fiável) como fonte primária para targeting, e DHT apenas como suplemento para jogadores ainda não sincronizados.

---

## 4. gRPC — Comunicação Entre Pares

### 4.1 O Que é gRPC?

**gRPC** (Google Remote Procedure Call) é um framework de comunicação que permite chamar funções noutros processos/máquinas como se fossem funções locais. Usa **Protocol Buffers (protobuf)** para serialização — um formato binário muito mais compacto e rápido que JSON ou XML.

```
SEM gRPC (sockets raw):

  bytes = struct.pack("!HI", damage, hp)
  socket.send(bytes)
  # do outro lado: struct.unpack("!HI", bytes)
  # frágil, sem validação de tipos, difícil de manter


COM gRPC:

  await client.cast_spell(addr, damage=22, element="FOGO", target_id="Jogador3")
  # automaticamente serializado, enviado, desserializado
  # tipos verificados, versionamento suportado, erros claros
```

### 4.2 O Ficheiro .proto

Define os "contratos" da comunicação — funciona como uma interface que todos os nós concordam em respeitar:

```protobuf
service MageService {
  rpc CastSpell       (SpellRequest)    returns (SpellResponse);
  rpc UpdatePosition  (PositionRequest) returns (Empty);
  rpc SendMessage     (ChatRequest)     returns (Empty);
  rpc SyncState       (StateRequest)    returns (Empty);
  rpc PlayerDied      (PlayerRequest)   returns (Empty);
  rpc LeaveGame       (PlayerRequest)   returns (Empty);
  rpc Heartbeat       (Ping)            returns (Pong);
}
```

### 4.3 RPCs Implementados

| RPC | Quando é Chamado | O Que Faz |
|-----|-----------------|-----------|
| `CastSpell` | Ao atacar | Aplica dano no alvo; devolve HP actual e se o escudo absorveu |
| `UpdatePosition` | Ao mover de sala | Actualiza localização do emissor no engine do receptor |
| `SendMessage` | Vários contextos | Mensagens de jogo e sentinelas de protocolo |
| `SyncState` | Início de ronda / ao mover | Partilha HP, mana, elemento e sala actual |
| `PlayerDied` | Ao chegar a 0 HP | Notifica todos que este jogador morreu |
| `LeaveGame` | Ao sair do jogo | Remove jogador do engine dos outros |
| `Heartbeat` | Verificação de conectividade | Testa se o par ainda está activo |

### 4.4 Protocolo de Mensagens Sentinela

O RPC `SendMessage` tem um campo `content` (string) que é reutilizado para enviar vários tipos de eventos de jogo codificados como strings especiais. Isto evita criar um RPC separado para cada tipo de evento.

```
"__START_GAME__"
    → Sinal para todos os clientes no lobby iniciarem o jogo

"__ROUND_WIN__:Jogador1:3"
    → Jogador1 ganhou a ronda número 3

"__DEBUFF__:burn:8"
    → Aplica debuff "burn" por 8 segundos no receptor

"__ROOM_EFFECT__:lava:SALA_3:30"
    → Sala 3 fica em lava por 30 segundos

"__FORCE_MOVE__:SALA_7"
    → Tornado expulsa o receptor para SALA_7
```

---

## 5. Componentes do Código

### 5.1 `core/mage.py` — O Jogador Local

Representa o estado completo do jogador na máquina local.

```
Mage
├── Atributos de estado
│   ├── hp, mana, max_hp, max_mana
│   ├── shielded, shield_hp      (Iron Shield do TERRA)
│   ├── invisible                (Dark Ritual do NEGRO)
│   ├── forced_room              (destino do Tornado)
│   └── room_id                  (sala actual)
│
├── Sistema de Eventos (asyncio.Event)
│   ├── death_event              → dispara ao chegar a 0 HP
│   ├── game_started_event       → dispara ao receber __START_GAME__
│   ├── round_end_event          → dispara ao receber __ROUND_WIN__
│   └── round_won_event          → dispara quando és o último vivo
│
├── Cooldowns
│   ├── COOLDOWNS = {move:3s, ataque:2s, skill:8s, ulti:20s}
│   ├── check_cooldown(action)   → (pronto: bool, restante: float)
│   └── set_cooldown(action)     → regista timestamp actual
│
├── Debuffs
│   ├── apply_debuff(name, dur)  → regista timestamp de expiração
│   ├── has_debuff(name)         → verifica se ainda activo
│   └── active_debuffs()         → lista de debuffs activos
│
└── Skills (configuradas por elemento no _setup_skills)
    ├── FOGO:  Fire Ball / Flame Dart / Eruption
    ├── GELO:  Ice Spear / Frostbite / Avalanche
    ├── AR:    Windburst / Wind Slash / Tornadoes
    ├── TERRA: Earthquake / Iron Shield / WasteLand
    └── NEGRO: Dark Orb / Chained / Dark Ritual
```

### 5.2 `core/engine.py` — Estado Partilhado do Jogo

Mantém o estado global do jogo na perspectiva do jogador local: mapa, jogadores conhecidos, efeitos de sala e pontuações de ronda.

```
GameEngine
│
├── mapa: dicionário de adjacências (grafo 3×3 sem diagonais)
│   SALA_1 ↔ SALA_2 ↔ SALA_3
│   SALA_4 ↔ SALA_5 ↔ SALA_6
│   SALA_7 ↔ SALA_8 ↔ SALA_9
│
├── players: {player_id: {addr, room_id, hp, mana, element, alive}}
│   ├── Populado por: SyncState gRPC + _sync_dht_to_engine
│   ├── alive=False quando morto (mantém addr para broadcasts)
│   └── room_id="" no início de cada ronda (reset de stale data)
│
├── room_effects: {room_id: {effect: timestamp_expiração}}
│   ├── "lava"       → dano escalante a cada 3s (FOGO imune)
│   ├── "locked"     → impossível entrar ou sair
│   └── "wasteland"  → +50% custo de mana, -20% dano
│
└── Sistema de Rondas
    ├── alive_this_round: set de IDs ainda vivos na ronda
    ├── round_scores: {player_id: número de vitórias}
    ├── start_new_round(ids) → reset alive + limpa room_id obsoleto
    └── is_last_alive(id)    → True se for o único sobrevivente
```

### 5.3 `network/grpc_server.py` — Receptor de RPCs

Cada instância do jogo tem um servidor gRPC a correr em background. Quando outro jogador envia `CastSpell`, `UpdatePosition`, etc., este servidor recebe e processa.

```python
# Exemplo simplificado do handler CastSpell:
async def CastSpell(self, request, context):
    # Verifica se o ataque é para este jogador
    if request.target_id and request.target_id != self.mage.player_id:
        return SpellResponse(message="Ataque não te atingiu.")

    # Verifica se o atacante está na mesma sala
    attacker_room = self.engine.get_player_room(request.attacker_id)
    if attacker_room != self.mage.room_id:
        return SpellResponse(shielded=True, message="Bloqueado: outra sala!")

    # Aplica o dano
    hit, current_hp = self.mage.take_damage(request.damage)
    return SpellResponse(shielded=not hit, current_hp=current_hp)
```

### 5.4 `network/grpc_client.py` — Emissor de RPCs

Fornece métodos assíncronos de alto nível para comunicar com outros jogadores. Cada chamada cria um canal gRPC para o endereço do alvo.

```python
await client.cast_spell(addr, damage, element, target_id)
await client.notify_move(addr, new_room)
await client.sync_state(addr, room_id, hp, mana, class_type)
await client.notify_death(addr, player_id)
await client.send_debuff(addr, debuff_name, duration)
await client.broadcast_room_effect(addr, effect, room_id, duration)
await client.send_force_move(addr, destination_room)
```

### 5.5 `network/dht_handler.py` — Interface com Kademlia

Abstrai a biblioteca `kademlia` em operações de alto nível orientadas ao jogo:

```python
await dht.announce_presence(player_id, ip, port, room_id)
await dht.get_players_in_room(room_id)  # → {player_id: "ip:port"}
await dht.remove_player(player_id)
await dht.remove_from_room(player_id, room_id)
```

### 5.6 `ui/interface.py` — Interface Rich

Usa a biblioteca **Rich** para renderizar o terminal com layouts, painéis e barras de progresso. A interface actualiza a **10 FPS** (loop de 100ms) sem bloquear o input. O input é lido em modo raw (`termios`/`tty`) de forma assíncrona.

```
┌─────────────────────┬──────────────────────┐
│      MAPA           │    LEADERBOARD       │
│  (grid 3×3 de salas)│  (ranking de vitórias)│
│  [TU] em destaque   │  elemento + vitórias  │
├─────────────────────┼──────────────────────┤
│   LOG & COMANDOS    │   ESTADO & SALA      │
│  mensagens do jogo  │  HP/Mana bars        │
│  alvos na sala      │  skills + cooldowns  │
│  linha de input     │  jogadores na sala   │
└─────────────────────┴──────────────────────┘
```

### 5.7 `main.py` — Orquestrador Principal

Ficheiro central que:
1. Inicializa todos os componentes (Mage, GameEngine, DHTHandler, MageClient)
2. Inicia o servidor gRPC e o nó DHT
3. Executa o loop do lobby (`run_lobby`)
4. Executa o loop de rondas (`run_rounds`)
5. Para cada ronda, executa o loop de jogo (`run_round`)
6. Gere todos os eventos concorrentes com `asyncio.wait`

**Padrão de concorrência principal usado em todo o jogo:**

```python
# Espera pelo PRIMEIRO evento que aconteça (timeout de 2s):
cmd_task = asyncio.create_task(live_input.get_command())

done, _ = await asyncio.wait(
    [cmd_task, death_task, round_won_task],
    return_when=asyncio.FIRST_COMPLETED,
    timeout=2.0)

if death_task in done:
    # jogador morreu
elif round_won_task in done:
    # jogador ganhou a ronda
elif not done:
    # timeout — nenhum evento, continua o loop
else:
    # processou comando do teclado
```

---

## 6. Mecânicas de Jogo

### 6.1 Os 5 Elementos

| Elemento | Ataque Base | Skill (8s CD) | Ultimato (20s CD) |
|----------|-------------|---------------|-------------------|
| **FOGO** | Fire Ball — 22dmg, 15mp | Flame Dart — 18dmg + burn 8s | Eruption — sala em lava 30s + AoE 20dmg |
| **GELO** | Ice Spear — 22dmg, 15mp | Frostbite — 25dmg + mana_slow 15s | Avalanche — sala bloqueada 12s + mana_slow AoE |
| **AR** | Windburst — 20dmg, 12mp | Wind Slash — AoE + regen de mana por hit | Tornadoes — expulsa todos para salas adjacentes |
| **TERRA** | Earthquake — AoE + dmg_reduce 8s | Iron Shield — 50 HP de escudo | WasteLand — salas adjacentes em wasteland 20s |
| **NEGRO** | Dark Orb — 25dmg, 18mp | Chained — imobiliza 6s (sem atacar) | Dark Ritual — invisível + sai da DHT |

### 6.2 Sistema de Cooldowns

```
Movimento:   3 segundos
Ataque:      2 segundos
Skill:       8 segundos
Ultimato:   20 segundos
```

**Detalhe importante:** o cooldown só é activado se a mana for efectivamente gasta. Se o ataque falhar (sem alvo, mana insuficiente), não há penalização.

```python
mana_antes = mage.mana
# ... tenta executar a acção ...
if mage.mana < mana_antes:   # só activa se gastou mana
    mage.set_cooldown(tipo)
```

### 6.3 Sistema de Debuffs

| Debuff | Efeito | Origem |
|--------|--------|--------|
| `burn` | -3 HP a cada 2 segundos | Flame Dart (FOGO) ou sair de sala em lava |
| `mana_slow` | Regen de mana reduzida (2/tick em vez de 5) | Frostbite (GELO) ou Avalanche |
| `chained` | Não pode usar ataques ou skills | Chained (NEGRO) |
| `dmg_reduce` | Dano dado reduzido em 30% | Earthquake (TERRA) |

### 6.4 Efeitos de Sala

| Efeito | Duração | Impacto |
|--------|---------|---------|
| **Lava** | 30s | Dano escalante a cada 3s (começa em 10, +5 por tick). FOGO é imune. Queimadura ao sair. |
| **Locked** | 12s | Impossível entrar ou sair. Criado por Avalanche (GELO). |
| **WasteLand** | 20s | +50% custo de mana, -20% dano. Afecta salas adjacentes à posição do TERRA. |

### 6.5 Sistema de Rondas

```
Início da Ronda
     │
     ├─ Spawn aleatório (SALA_1 a SALA_9, independente por jogador)
     ├─ Reset: HP=100, Mana=100, cooldowns=0, debuffs={}
     ├─ Broadcast SyncState a TODOS (elemento + sala nova)
     │
     │   ┌─── LOOP DE JOGO ─────────────────────────────────┐
     │   │                                                   │
     │   │  1. Movimento forçado? (Tornado) → mover         │
     │   │  2. Na lava? → aplicar dano escalante            │
     │   │  3. Aguardar evento (até 2s):                    │
     │   │     ├─ m <N>  → mover para sala adjacente        │
     │   │     ├─ a [N]  → ataque base                      │
     │   │     ├─ s [N]  → skill                            │
     │   │     ├─ u [N]  → ultimato                         │
     │   │     └─ q      → sair do jogo                     │
     │   └───────────────────────────────────────────────────┘
     │
     ├─── HP = 0?
     │      └─ broadcast PlayerDied a todos
     │         aguardar round_end_event (ou 'q' para sair)
     │
     └─── último vivo?
            └─ broadcast __ROUND_WIN__:id:N
               incrementa score
               nova ronda (até 4 vitórias = campeão)
```

---

## 7. Bugs Encontrados e Soluções

### Bug 1 — Elemento "?" no próprio leaderboard

**Descrição:** O próprio jogador aparecia com "?" na sua classe no leaderboard no início do jogo.

**Causa:** O leaderboard fazia `early return` quando `round_scores` estava vazio, antes de adicionar a entrada do próprio jogador.

**Solução:** Sempre construir a entrada do jogador local a partir de `mage.element` directamente, antes de qualquer verificação de scores vazios, garantindo que o próprio jogador aparece sempre.

---

### Bug 2 — Target IDs errados para o host (bootstrap node)

**Descrição:** O primeiro jogador a entrar no jogo não via os outros como alvos. Os target IDs estavam errados ou vazios.

**Causa:** A função `_resolve_target` usava apenas a DHT para encontrar alvos na sala. O bootstrap node tem queries DHT menos fiáveis porque os dados demoram a propagar-se para o nó semente (problema de replicação Kademlia).

**Solução:** Criar `_get_room_targets` que usa `engine.players` como fonte primária (populado via SyncState gRPC, 100% fiável) e DHT apenas como suplemento.

```python
async def _get_room_targets(mage, engine, dht, player_id):
    # Fonte primária: engine.players (via SyncState gRPC — fiável para todos)
    alvos = {
        pid: data["addr"]
        for pid, data in engine.players.items()
        if data.get("room_id") == mage.room_id
        and data.get("alive", True)
        and data.get("addr")
        and pid != player_id
    }
    # Suplemento: DHT (para jogadores recém-chegados ainda não sincronizados)
    try:
        for pid, addr in (await dht.get_players_in_room(mage.room_id)).items():
            if pid != player_id and pid not in alvos:
                alvos[pid] = addr
    except Exception:
        pass
    return alvos
```

Esta função passou a ser usada em **todos** os ataques — tanto os de alvo único (`_resolve_target`) como os de área (Eruption, Avalanche, Wind Slash, Tornadoes, Earthquake).

---

### Bug 3 — Timeout de 120s para jogadores mortos

**Descrição:** Quando um jogador morria, havia um timeout máximo de 120 segundos. Se os outros jogadores ainda estivessem a combater, o jogo terminava a ronda prematuramente.

**Causa:** `asyncio.wait_for(mage.round_end_event.wait(), timeout=120)`.

**Solução:** Remover o timeout. A ronda termina naturalmente quando o último sobrevivente transmite `__ROUND_WIN__`, que dispara `round_end_event` em todos os jogadores mortos. Sem limite de tempo — uma ronda pode durar o tempo que for necessário.

---

### Bug 4 — Não conseguia sair do jogo estando morto

**Descrição:** Após morrer, o jogo ficava bloqueado a aguardar `round_end_event` sem possibilidade de premir `q` para sair.

**Causa:** `await mage.round_end_event.wait()` bloqueava indefinidamente sem observar o teclado.

**Solução:** Usar `asyncio.wait` com duas tasks simultâneas — uma para o evento de fim de ronda, outra para aguardar o comando `q`:

```python
async def _wait_quit():
    while True:
        c = await live_input.get_command()
        if c and c.strip().lower() == "q":
            return

quit_t = asyncio.create_task(_wait_quit())
end_t  = asyncio.create_task(mage.round_end_event.wait())

done, pending = await asyncio.wait(
    [quit_t, end_t], return_when=asyncio.FIRST_COMPLETED)

for t in pending:
    t.cancel()

if quit_t in done:
    break   # sai do loop de rondas
```

---

### Bug 5 — FOGO sofria dano da própria Eruption/lava

**Descrição:** O mago FOGO activava o ultimato Eruption (que põe a sala em lava) e depois sofria dano da sua própria lava.

**Causa:** O bloco de dano de lava em `run_round` não verificava o elemento do jogador local.

**Solução:** Adicionar verificação `mage.element != "FOGO"` no bloco de dano:

```python
if engine.is_room_lava(mage.room_id) and mage.element != "FOGO":
    # aplica dano escalante...
```

---

### Bug 6 — Cooldown activava em acções falhadas

**Descrição:** Se o jogador tentasse usar uma skill sem mana suficiente, o cooldown era activado mesmo sem o ataque ter acontecido.

**Causa:** `mage.set_cooldown(tipo)` era chamado sempre após o dispatch da acção, independentemente do resultado.

**Solução:** Guardar snapshot de mana antes do dispatch e só activar o cooldown se a mana diminuiu:

```python
mana_antes = mage.mana
# ... executa acção ...
if mage.mana < mana_antes:
    mage.set_cooldown(tipo)
```

---

### Bug 7 — Spawn fixo em SALA_1

**Descrição:** Todos os jogadores começavam sempre na SALA_1, tornando o início previsível e estrategicamente desequilibrado.

**Causa:** `mage.room_id = "SALA_1"` hardcoded no loop de rondas.

**Solução:** Spawn aleatório independente por jogador a cada ronda:

```python
spawn_room = random.choice(list(engine.mapa.keys()))
mage.room_id = spawn_room
await dht.announce_presence(player_id, meu_ip, grpc_port, spawn_room)
```

---

### Bug 8 — Salas obsoletas / "players fantasma"

**Descrição:** Após uma ronda, `engine.players[pid]["room_id"]` ficava com o valor da ronda anterior. Na próxima ronda, jogadores apareciam erroneamente em salas onde já não estavam, podendo até aparecer como alvos válidos.

**Causa:** `engine.start_new_round` não limpava o `room_id` dos jogadores registados.

**Solução:** Limpar `room_id` para `""` em `start_new_round`. O valor vazio não corresponde a nenhuma sala real — o jogador não aparece em nenhuma sala até enviar um novo SyncState com a localização correcta.

```python
def start_new_round(self, all_player_ids):
    for pid in all_player_ids:
        if pid in self.players:
            self.players[pid]["alive"]   = True
            self.players[pid]["room_id"] = ""   # limpa sala obsoleta
```

---

### Bug 9 — Elementos "?" após introdução do spawn aleatório

**Descrição:** Com spawn aleatório, os elementos dos outros jogadores ficavam permanentemente a "?" no leaderboard e no painel de sala.

**Causa:** O `_broadcast_state` envia SyncState (com o elemento) apenas aos jogadores na **mesma sala de spawn**. Com spawn aleatório, muitos jogadores ficam em salas diferentes e nunca recebem o SyncState uns dos outros.

**Solução:** No início de cada ronda, fazer broadcast de SyncState a **todos** os peers conhecidos, não apenas aos da sala de spawn:

```python
await _broadcast_to_all_peers(
    client, engine, player_id,
    lambda addr: client.sync_state(
        addr,
        room_id=mage.room_id,
        hp=mage.hp,
        mana=mage.mana,
        class_type=mage.element
    )
)
```

---

### Bug 10 — `engine.players` vazio ao início (lobby não sincronizava)

**Descrição:** Mesmo com o broadcast global do Bug 9, os elementos continuavam "?" porque `engine.players` estava **vazio** quando o jogo começava. O `_broadcast_to_all_peers` iterava um dicionário vazio e não enviava nada.

**Causa:** O lobby consultava a DHT para mostrar peers na UI (`ctx["lobby_peers"]`) mas **nunca chamava `_sync_dht_to_engine`**. Os endereços dos outros jogadores ficavam apenas na variável da UI e nunca entravam em `engine.players`.

**Solução:** No loop do lobby, sincronizar os peers para `engine.players` em cada ciclo:

```python
while mage.in_lobby:
    lobby_peers = await dht.get_players_in_room("LOBBY")
    ctx["lobby_peers"] = lobby_peers
    # NOVO: popula engine.players com endereços de todos os peers do lobby
    _sync_dht_to_engine(engine, "LOBBY", lobby_peers, player_id)
```

Com isto, quando a ronda começa, `engine.players` já tem todos os endereços e o broadcast global (Bug 9) funciona correctamente, resolvendo os elementos "?".

---

## 8. Alternativas de Implementação Consideradas

### 8.1 Servidor Central vs P2P

| Critério | Servidor Central | P2P (escolhido) |
|----------|-----------------|-----------------|
| Consistência | Garantida (única fonte de verdade) | Eventual (inconsistências temporárias) |
| Ponto de falha | Sim — servidor cai, jogo para | Não — qualquer nó pode sair |
| Complexidade de implementação | Menor (estado centralizado) | Maior (sincronização distribuída) |
| Relevância académica | Baixa | Alta (demonstra conceitos de SD reais) |

### 8.2 WebSockets vs gRPC

| Critério | WebSockets | gRPC (escolhido) |
|----------|-----------|-----------------|
| Protocolo | TCP + HTTP upgrade | HTTP/2 |
| Serialização | JSON (texto legível) | Protocol Buffers (binário compacto) |
| Eficiência | Menor | ~3-5x mais compacto que JSON |
| Tipagem | Manual | Gerada automaticamente do .proto |
| Contratos explícitos | Não | Sim (.proto como documentação) |

### 8.3 Redis Pub/Sub vs DHT para Descoberta

| Critério | Redis Pub/Sub | Kademlia DHT (escolhido) |
|----------|--------------|------------------------|
| Servidor central | Sim (Redis) | Não |
| Facilidade de uso | Muito simples | Complexo |
| Tolerância a falhas | Depende do Redis | Alta — sem ponto central |
| Relevância académica | Baixa | Alta — demonstra P2P real |

### 8.4 curses vs Rich para a TUI

| Critério | curses | Rich (escolhido) |
|----------|--------|-----------------|
| Nível de abstracção | Baixo (controlo total) | Alto (abstracção conveniente) |
| Cores e estilos | Básico | 256 cores + negrito + itálico |
| Layouts | Manual (posição x,y) | Layout engine automático |
| Portabilidade | Apenas Unix | Windows + Linux + Mac |

### 8.5 Threading vs asyncio

| Critério | Threading | asyncio (escolhido) |
|----------|-----------|-------------------|
| Modelo | Paralelo real (GIL limita em Python) | Concorrência cooperativa single-thread |
| Adequação para I/O | Funciona mas com overhead | Ideal — zero overhead de contexto |
| Race conditions | Frequentes sem locks | Raras — só há conflito em `await` points |
| Suporte gRPC async | Complicado | Nativo com `grpc.aio` |

---

## 9. Fluxo Completo de uma Sessão

```
MÁQUINA A (host/bootstrap)              MÁQUINA B (cliente)
──────────────────────────────────      ──────────────────────────────────
$ python main.py JogadorA FOGO 50051
  │
  ├─ Inicia DHT na porta 8468
  ├─ Inicia gRPC na porta 50051
  ├─ Anuncia no DHT: room="LOBBY"
  └─ Aguarda no lobby

                                        $ python main.py JogadorB GELO 50052 192.168.1.X
                                          │
                                          ├─ Liga-se à DHT de A (bootstrap)
                                          ├─ Inicia gRPC na porta 50052
                                          ├─ Anuncia no DHT: room="LOBBY"
                                          └─ Aguarda no lobby

  ← UI de A: "JogadorB" aparece no lobby
  ← Lobby loop: _sync_dht_to_engine
      engine.players["JogadorB"] = {addr: "192.168.1.X:50052", ...}

                                          ← UI de B: "JogadorA" aparece no lobby
                                          ← engine.players["JogadorA"] = {addr: ...}

  [A digita "start"]
  │
  ├─ Consulta DHT: peers no LOBBY
  ├─ _sync_dht_to_engine (sync final)
  ├─ Envia broadcast_start_game → B
  │                                       B recebe __START_GAME__
  │                                       game_started_event.set()
  │
  ├─ A: spawn aleatório → SALA_3          B: spawn aleatório → SALA_7
  ├─ A anuncia DHT: SALA_3                B anuncia DHT: SALA_7
  ├─ engine.start_new_round()             engine.start_new_round()
  │     └─ room_id de B = ""                  └─ room_id de A = ""
  │
  ├─ A _broadcast_to_all_peers →          B _broadcast_to_all_peers →
  │   SyncState(B, room=SALA_3, elem=FOGO)   SyncState(A, room=SALA_7, elem=GELO)
  │
  │   B recebe SyncState de A:            A recebe SyncState de B:
  │   players["A"] = {room:"SALA_3",      players["B"] = {room:"SALA_7",
  │                   element:"FOGO"} ✓               element:"GELO"} ✓
  │
  │   Leaderboard de B: FOGO ✓            Leaderboard de A: GELO ✓
  │
  [Ambos jogam livremente pelo mapa...]
  │
  ├─ A move para SALA_7 (mesma sala que B)
  │   ├─ UpdatePosition(B, nova_sala=SALA_7)
  │   │                                   engine.players["A"]["room_id"] = "SALA_7"
  │   └─ _get_room_targets retorna {B: addr_B}
  │
  ├─ A digita "a" (ataque)
  │   ├─ CastSpell(B, damage=22, element="FOGO", target="JogadorB")
  │   │                                   take_damage(22) → hp = 78
  │   │                                   SpellResponse: {hp:78, shielded:false}
  │   └─ UI de A: "[Fire Ball] JogadorB: 22dmg!"
  │
  [... combate continua até alguém chegar a 0 HP ...]
  │
  [B chega a 0 HP]
  │                                       B.death_event.set()
  │                                       B → PlayerDied(player_id="JogadorB") → A
  │
  ├─ A recebe PlayerDied:
  │   engine.mark_player_dead("JogadorB")
  │   is_last_alive("JogadorA") = True
  │   round_won_event.set()
  │
  ├─ A ganha ronda 1:
  │   ├─ round_scores["JogadorA"]++
  │   └─ broadcast __ROUND_WIN__:JogadorA:1 → B
  │                                       B recebe __ROUND_WIN__
  │                                       round_end_event.set()
  │                                       B deixa de estar bloqueado
  │
  [nova ronda começa... até 4 vitórias]
  │
  [ao fim de 4 vitórias de A]
  ├─ Interface.set_champion({winner: "JogadorA", ...})
  └─ Ecrã final com ranking e coroa
```

---

## 10. Conclusões e Lições Aprendidas

### 10.1 O Que Funcionou Bem

**asyncio** revelou-se a escolha certa para este projecto. A capacidade de aguardar simultaneamente por input do utilizador, eventos de rede e timers sem threading simplificou imensamente a lógica de controlo do jogo. O padrão `asyncio.wait([task1, task2], return_when=FIRST_COMPLETED)` foi usado extensivamente e provou ser muito expressivo.

**gRPC com Protocol Buffers** tornou a comunicação entre nós robusta e fácil de manter. A definição explícita de contratos no `.proto` evitou muitos bugs de serialização. A compatibilidade com `asyncio` via `grpc.aio` integrou-se perfeitamente.

**Rich** permitiu criar uma interface de terminal visualmente rica e estruturada em poucos dias, algo que com `curses` teria demorado muito mais tempo.

**A separação DHT (descoberta) + gRPC (comunicação directa)** foi uma separação de responsabilidades limpa que simplificou muito o código. DHT para "onde está X?" e gRPC para "diz ao X que...".

### 10.2 Os Maiores Desafios Técnicos

**Estado distribuído sem servidor central** foi o maior desafio conceptual. Cada nó tem a sua cópia do estado do jogo, e manter essas cópias consistentes requereu múltiplos mecanismos: SyncState no início de cada ronda, UpdatePosition em cada movimento, e a combinação DHT+engine para targeting fiável.

**O bootstrap node da DHT** causou vários bugs subtis porque o nó semente tem comportamento diferente dos outros nós durante os primeiros segundos (replicação incompleta). A lição: nunca depender de um único mecanismo de rede para dados críticos de jogo.

**Dados "stale" entre rondas** foram uma fonte recorrente de bugs. Com spawn aleatório, dados da ronda anterior (sala de um jogador, etc.) causavam comportamentos incorrectos na ronda seguinte. A solução de limpar explicitamente o estado no início de cada ronda foi essencial.

**O problema do "lobby não sincronizava"** foi o mais subtil: a UI mostrava os peers do lobby correctamente, mas o engine nunca ficava populado — dois sistemas paralelos que mostravam a mesma informação de fontes diferentes, mas apenas um era usado para comunicação. Isto realça a importância de ter uma única fonte de verdade para cada tipo de dado.

### 10.3 Lições para Futuros Projectos

1. **Nunca assumir que o estado remoto está actualizado.** Dados da DHT e de outras máquinas podem estar desactualizados. Usar sempre a fonte mais fiável disponível.

2. **Testar sempre com o bootstrap node** como jogador principal. Bugs que só afectam o primeiro nó a entrar na rede são difíceis de descobrir se só se testa com jogadores não-bootstrap.

3. **Reset explícito de estado entre fases do jogo.** Dados obsoletos de rondas anteriores causam bugs que só aparecem na segunda ronda em diante — os mais difíceis de diagnosticar.

4. **Separar descoberta de comunicação** é um bom princípio arquitectural. DHT para localização, gRPC para mensagens directas — cada um faz o que faz melhor.

5. **O asyncio resolve a maioria dos problemas de I/O concorrente** sem a complexidade dos threads. Para aplicações de rede em Python, é a escolha natural — especialmente quando se usa gRPC, que tem suporte asyncio nativo.

---

*Documento de suporte à apresentação do projecto Wizard Duels.*  
*Desenvolvido para a disciplina de Redes e Sistemas Distribuídos.*
