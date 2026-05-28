import asyncio
import sys
import os
import socket
import termios
import tty
import random

from rich.live import Live
from rich.console import Console

from core.mage import Mage
from core.engine import GameEngine
from network.dht_handler import DHTHandler
from network.grpc_server import serve
from network.grpc_client import MageClient
from ui.interface import Interface


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


class LiveInput:
    def __init__(self):
        self.queue: asyncio.Queue = asyncio.Queue()
        self._buffer = ""
        self._old_termios = None
        self._fd = sys.stdin.fileno()

    def start(self):
        self._old_termios = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        asyncio.get_event_loop().add_reader(self._fd, self._on_readable)

    def _on_readable(self):
        try:
            data = os.read(self._fd, 4096).decode(errors="ignore")
        except (IOError, OSError):
            return
        if not data:
            return
        i = 0
        while i < len(data):
            ch = data[i]; i += 1
            if ch == "\r":
                continue
            elif ch == "\n":
                line, self._buffer = self._buffer, ""
                Interface.set_input_buffer("")
                self.queue.put_nowait(line)
            elif ch in ("\x7f", "\b"):
                self._buffer = self._buffer[:-1]
                Interface.set_input_buffer(self._buffer)
            elif ch == "\x03":
                self.queue.put_nowait("q")
            elif ch == "\x1b":
                while i < len(data) and not data[i].isalpha():
                    i += 1
                if i < len(data):
                    i += 1
            elif ch.isprintable():
                self._buffer += ch
                Interface.set_input_buffer(self._buffer)

    async def get_command(self, timeout=None):
        try:
            if timeout is None:
                return await self.queue.get()
            return await asyncio.wait_for(self.queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def stop(self):
        try:
            asyncio.get_event_loop().remove_reader(self._fd)
        except Exception:
            pass
        if self._old_termios is not None:
            try:
                termios.tcsetattr(self._fd, termios.TCSADRAIN, self._old_termios)
            except Exception:
                pass


async def _refresh_loop(live, ctx):
    while True:
        try:
            live.update(Interface.render(
                in_lobby=ctx["in_lobby"],
                lobby_peers=ctx.get("lobby_peers"),
            ), refresh=True)
        except Exception:
            pass
        await asyncio.sleep(0.1)


def _sync_dht_to_engine(engine, room_id, dht_peers, exclude_id=None):
    for pid, addr in dht_peers.items():
        if pid == exclude_id:
            continue
        if pid not in engine.players:
            engine.register_or_update_player(
                player_id=pid, name=pid, addr=addr,
                room_id=room_id, hp=100, mana=100, element="?")
        else:
            engine.players[pid]["addr"]    = addr
            engine.players[pid]["room_id"] = room_id


async def _broadcast_state(client, mage, peers, player_id):
    tasks = [
        client.sync_state(addr, room_id=mage.room_id, hp=mage.hp,
                          mana=mage.mana, class_type=mage.element)
        for pid, addr in peers.items() if pid != player_id
    ]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


async def _broadcast_to_all_peers(client, engine, player_id, coro_fn):
    tasks = [
        coro_fn(data["addr"])
        for pid, data in list(engine.players.items())
        if pid != player_id and data.get("addr")
    ]
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


# ─────────────────────────────────────────────────────────────────────────────
# BUG 3 FIX: helper engine-primary + DHT-supplemented para alvos na sala atual
# ─────────────────────────────────────────────────────────────────────────────
async def _get_room_targets(mage, engine, dht, player_id):
    """Alvos vivos na sala actual. engine.players é a fonte primária (fiável
    para o host/bootstrap); DHT acrescenta jogadores ainda não sincronizados."""
    alvos = {
        pid: data["addr"]
        for pid, data in list(engine.players.items())
        if data.get("room_id") == mage.room_id
        and data.get("alive", True)
        and data.get("addr")
        and pid != player_id
    }
    try:
        for pid, addr in (await dht.get_players_in_room(mage.room_id)).items():
            if pid != player_id and pid not in alvos:
                alvos[pid] = addr
    except Exception:
        pass
    return alvos


def _apply_modifiers(mage, engine, dano, custo):
    if mage.has_debuff("dmg_reduce"):
        dano = int(dano * 0.70)
    if engine.is_room_wasteland(mage.room_id):
        custo = int(custo * 1.5)
        dano  = int(dano  * 0.80)
    return dano, custo


async def _resolve_target(args, mage, engine, dht, player_id, cmd_letter="s"):
    # BUG 3 FIX: usa _get_room_targets em vez de DHT directo
    alvos     = await _get_room_targets(mage, engine, dht, player_id)
    lista_ids = list(alvos.keys())

    if not alvos:
        Interface.show_message("Sala vazia — sem alvos.")
        return None, None

    if len(lista_ids) == 1:
        return lista_ids[0], alvos[lista_ids[0]]

    if args:
        arg = args[0]
        if arg.isdigit():
            idx = int(arg) - 1
            if 0 <= idx < len(lista_ids):
                pid = lista_ids[idx]
                return pid, alvos[pid]
            choices = "  ".join(f"[{i+1}]{p}" for i, p in enumerate(lista_ids))
            Interface.show_message(f"Invalido. Alvos: {choices}")
            return None, None
        else:
            tpid = arg.upper()
            if tpid in alvos:
                return tpid, alvos[tpid]
            Interface.show_message(f"'{arg}' nao esta na sala.")
            return None, None

    choices = "  ".join(f"[{i+1}]{p}" for i, p in enumerate(lista_ids))
    Interface.show_message(f"Varios alvos: {choices}  —  ex: {cmd_letter} 1")
    return None, None


async def _do_attack(tipo, args, mage, engine, dht, client, player_id):
    cmd = {"ataque": "a", "skill": "s", "ulti": "u"}.get(tipo, "a")
    target_pid, target_addr = await _resolve_target(
        args, mage, engine, dht, player_id, cmd)
    if not target_pid:
        return
    dano, custo, nome = mage.get_attack_info(tipo)
    dano, custo = _apply_modifiers(mage, engine, dano, custo)
    if not mage.use_mana(custo):
        Interface.show_message(f"Mana insuficiente! {nome} custa {custo}mp.")
        return
    try:
        res = await client.cast_spell(target_addr, dano, mage.element, target_pid)
    except Exception as e:
        Interface.show_message(f"[ERRO] {e}")
        mage.mana += custo
        return
    if res:
        Interface.show_message(f"[{nome}] {target_pid}: {res.message}")
        engine.update_player_hp(target_pid, res.current_hp)
    else:
        Interface.show_message(f"[{nome}] {target_pid}: sem resposta.")
        mage.mana += custo


# ── FOGO ──────────────────────────────────────────────────────────────────────
async def _do_flame_dart(args, mage, engine, dht, client, player_id):
    target_pid, target_addr = await _resolve_target(
        args, mage, engine, dht, player_id, "s")
    if not target_pid:
        return
    dano, custo, nome = mage.get_attack_info("skill")
    dano, custo = _apply_modifiers(mage, engine, dano, custo)
    if not mage.use_mana(custo):
        Interface.show_message(f"Mana insuficiente! {nome} custa {custo}mp.")
        return
    res = await client.cast_spell(target_addr, dano, mage.element, target_pid)
    if res:
        engine.update_player_hp(target_pid, res.current_hp)
        await client.send_debuff(target_addr, "burn", 8)
        Interface.show_message(f"[{nome}] {target_pid}: {dano}dmg + queimadura 8s!")
    else:
        Interface.show_message(f"[{nome}] Sem resposta.")
        mage.mana += custo


async def _do_eruption(mage, engine, dht, client, player_id):
    dano_inicial = mage.skills["ulti"]["dano"]
    custo        = mage.skills["ulti"]["custo"]
    if engine.is_room_wasteland(mage.room_id):
        custo = int(custo * 1.5)
    if not mage.use_mana(custo):
        Interface.show_message(f"Mana insuficiente! Eruption custa {custo}mp.")
        return
    room = mage.room_id
    engine.set_room_effect(room, "lava", 30)
    await _broadcast_to_all_peers(
        client, engine, player_id,
        lambda addr: client.broadcast_room_effect(addr, "lava", room, 30))
    # BUG 3 FIX: usa _get_room_targets
    alvos = await _get_room_targets(mage, engine, dht, player_id)
    hit_count = 0
    for pid, addr in alvos.items():
        res = await client.cast_spell(addr, dano_inicial, mage.element, pid)
        if res:
            hit_count += 1
            engine.update_player_hp(pid, res.current_hp)
    Interface.show_message(
        f"[Eruption] Sala em LAVA 30s! {hit_count} atingidos com {dano_inicial}dmg.")


# ── GELO ──────────────────────────────────────────────────────────────────────
async def _do_frostbite(args, mage, engine, dht, client, player_id):
    target_pid, target_addr = await _resolve_target(
        args, mage, engine, dht, player_id, "s")
    if not target_pid:
        return
    dano, custo, nome = mage.get_attack_info("skill")
    dano, custo = _apply_modifiers(mage, engine, dano, custo)
    if not mage.use_mana(custo):
        Interface.show_message(f"Mana insuficiente! {nome} custa {custo}mp.")
        return
    res = await client.cast_spell(target_addr, dano, mage.element, target_pid)
    if res:
        engine.update_player_hp(target_pid, res.current_hp)
        await client.send_debuff(target_addr, "mana_slow", 15)
        Interface.show_message(f"[{nome}] {target_pid}: {dano}dmg + mana_slow 15s!")
    else:
        Interface.show_message(f"[{nome}] Sem resposta.")
        mage.mana += custo


async def _do_avalanche(mage, engine, dht, client, player_id):
    custo = mage.skills["ulti"]["custo"]
    if engine.is_room_wasteland(mage.room_id):
        custo = int(custo * 1.5)
    if not mage.use_mana(custo):
        Interface.show_message(f"Mana insuficiente! Avalanche custa {custo}mp.")
        return
    room = mage.room_id
    engine.set_room_effect(room, "locked", 12)
    await _broadcast_to_all_peers(
        client, engine, player_id,
        lambda addr: client.broadcast_room_effect(addr, "locked", room, 12))
    # BUG 3 FIX: usa _get_room_targets
    alvos = await _get_room_targets(mage, engine, dht, player_id)
    for pid, addr in alvos.items():
        await client.send_debuff(addr, "mana_slow", 15)
    Interface.show_message(f"[Avalanche] Sala {room} bloqueada 12s! Mana_slow em todos.")


# ── AR ────────────────────────────────────────────────────────────────────────
async def _do_wind_slash(mage, engine, dht, client, player_id):
    dano, custo, nome = mage.get_attack_info("skill")
    dano, custo = _apply_modifiers(mage, engine, dano, custo)
    if not mage.use_mana(custo):
        Interface.show_message(f"Mana insuficiente! {nome} custa {custo}mp.")
        return
    # BUG 3 FIX: usa _get_room_targets (já filtra player_id e mortos)
    alvos = await _get_room_targets(mage, engine, dht, player_id)
    if not alvos:
        Interface.show_message(f"[{nome}] Sala vazia.")
        mage.mana += custo
        return
    hit_count = 0
    for pid, addr in alvos.items():
        res = await client.cast_spell(addr, dano, mage.element, pid)
        if res:
            hit_count += 1
            engine.update_player_hp(pid, res.current_hp)
    mana_regen = hit_count * 8
    mage.mana = min(mage.max_mana, mage.mana + mana_regen)
    Interface.show_message(f"[{nome}] {hit_count} atingidos! +{mana_regen}mp recuperados.")


async def _do_tornadoes(mage, engine, dht, client, player_id):
    custo = mage.skills["ulti"]["custo"]
    if engine.is_room_wasteland(mage.room_id):
        custo = int(custo * 1.5)
    if not mage.use_mana(custo):
        Interface.show_message(f"Mana insuficiente! Tornadoes custa {custo}mp.")
        return
    adjacentes = engine.mapa.get(mage.room_id, [])
    if not adjacentes:
        Interface.show_message("[Tornadoes] Sem salas adjacentes!")
        mage.mana += custo
        return
    # BUG 3 FIX: usa _get_room_targets
    alvos = await _get_room_targets(mage, engine, dht, player_id)
    enviados = []
    for pid, addr in alvos.items():
        dest = random.choice(adjacentes)
        await client.send_force_move(addr, dest)
        enviados.append(f"{pid}->{dest}")
    if enviados:
        Interface.show_message(f"[Tornadoes] Expulsos: {', '.join(enviados)}")
    else:
        Interface.show_message("[Tornadoes] Sala vazia — sem efeito.")
        mage.mana += custo


# ── TERRA ─────────────────────────────────────────────────────────────────────
async def _do_earthquake(mage, engine, dht, client, player_id):
    dano, custo, nome = mage.get_attack_info("ataque")
    dano, custo = _apply_modifiers(mage, engine, dano, custo)
    if not mage.use_mana(custo):
        Interface.show_message(f"Mana insuficiente! {nome} custa {custo}mp.")
        return
    # BUG 3 FIX: usa _get_room_targets (já filtra player_id e mortos)
    alvos = await _get_room_targets(mage, engine, dht, player_id)
    if not alvos:
        Interface.show_message(f"[{nome}] Sala vazia.")
        mage.mana += custo
        return
    hit_count = 0
    for pid, addr in alvos.items():
        res = await client.cast_spell(addr, dano, mage.element, pid)
        if res:
            hit_count += 1
            engine.update_player_hp(pid, res.current_hp)
            await client.send_debuff(addr, "dmg_reduce", 8)
    Interface.show_message(f"[{nome}] {hit_count} atingidos! Dano reduzido por 8s.")


async def _do_iron_shield(mage):
    ok, msg = mage.activate_iron_shield(shield_hp=50)
    Interface.show_message(msg)


async def _do_wasteland(mage, engine, dht, client, player_id):
    custo = mage.skills["ulti"]["custo"]
    if engine.is_room_wasteland(mage.room_id):
        custo = int(custo * 1.5)
    if not mage.use_mana(custo):
        Interface.show_message(f"Mana insuficiente! WasteLand custa {custo}mp.")
        return
    adjacentes = engine.mapa.get(mage.room_id, [])
    if not adjacentes:
        Interface.show_message("[WasteLand] Sem salas adjacentes.")
        mage.mana += custo
        return
    for adj in adjacentes:
        engine.set_room_effect(adj, "wasteland", 20)
    tasks = []
    for pid, data in list(engine.players.items()):
        if pid != player_id and data.get("addr"):
            for adj in adjacentes:
                tasks.append(
                    client.broadcast_room_effect(data["addr"], "wasteland", adj, 20))
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)
    Interface.show_message(f"[WasteLand] {len(adjacentes)} salas em WasteLand por 20s!")


# ── NEGRO ─────────────────────────────────────────────────────────────────────
async def _do_chained(args, mage, engine, dht, client, player_id):
    target_pid, target_addr = await _resolve_target(
        args, mage, engine, dht, player_id, "s")
    if not target_pid:
        return
    custo = mage.skills["skill"]["custo"]
    if engine.is_room_wasteland(mage.room_id):
        custo = int(custo * 1.5)
    if not mage.use_mana(custo):
        Interface.show_message(f"Mana insuficiente! Chained custa {custo}mp.")
        return
    await client.send_debuff(target_addr, "chained", 6)
    Interface.show_message(f"[Chained] {target_pid} acorrentado por 6s!")


async def _do_dark_ritual(mage, dht, player_id):
    custo = mage.skills["ulti"]["custo"]
    if not mage.use_mana(custo):
        Interface.show_message(f"Mana insuficiente! Dark Ritual custa {custo}mp.")
        return
    mage.invisible = True
    await dht.remove_player(player_id)
    Interface.show_message("[Dark Ritual] Invisivel! Qualquer acao quebrara o estado.")


# ── Dispatcher ────────────────────────────────────────────────────────────────
async def _dispatch_ability(tipo, args, mage, engine, dht, client,
                             player_id, meu_ip, grpc_port):
    if mage.invisible:
        mage.invisible = False
        await dht.announce_presence(player_id, meu_ip, grpc_port, mage.room_id)
        Interface.show_message("[NEGRO] Invisibilidade quebrada!")

    ready, rem = mage.check_cooldown(tipo)
    if not ready:
        labels = {"ataque": "Ataque", "skill": "Skill", "ulti": "Ulti"}
        Interface.show_message(f"[CD] {labels.get(tipo, tipo)} em recarga — {rem:.1f}s")
        return

    mana_antes = mage.mana
    key = (mage.element, tipo)

    if   key == ("FOGO",  "skill"): await _do_flame_dart(args, mage, engine, dht, client, player_id)
    elif key == ("FOGO",  "ulti"):  await _do_eruption(mage, engine, dht, client, player_id)
    elif key == ("GELO",  "skill"): await _do_frostbite(args, mage, engine, dht, client, player_id)
    elif key == ("GELO",  "ulti"):  await _do_avalanche(mage, engine, dht, client, player_id)
    elif key == ("AR",    "skill"): await _do_wind_slash(mage, engine, dht, client, player_id)
    elif key == ("AR",    "ulti"):  await _do_tornadoes(mage, engine, dht, client, player_id)
    elif key == ("TERRA", "ataque"):await _do_earthquake(mage, engine, dht, client, player_id)
    elif key == ("TERRA", "skill"): await _do_iron_shield(mage)
    elif key == ("TERRA", "ulti"):  await _do_wasteland(mage, engine, dht, client, player_id)
    elif key == ("NEGRO", "skill"): await _do_chained(args, mage, engine, dht, client, player_id)
    elif key == ("NEGRO", "ulti"):  await _do_dark_ritual(mage, dht, player_id)
    else:
        await _do_attack(tipo, args, mage, engine, dht, client, player_id)

    if mage.mana < mana_antes:
        mage.set_cooldown(tipo)


# ─────────────────────────────────────────────────────────────────────────────
# Lobby
# ─────────────────────────────────────────────────────────────────────────────
async def run_lobby(mage, engine, dht, client, player_id, meu_ip, grpc_port,
                    live, live_input, ctx):
    start_task = asyncio.create_task(mage.game_started_event.wait())

    while mage.in_lobby:
        await dht.announce_presence(player_id, meu_ip, grpc_port, "LOBBY")
        lobby_peers = await dht.get_players_in_room("LOBBY")
        ctx["lobby_peers"] = lobby_peers
        # Sincroniza endereços dos peers do lobby para engine.players.
        # Sem isto, _broadcast_to_all_peers no início da ronda não chega
        # a ninguém (engine vazio) → elementos ficam "?" para sempre.
        _sync_dht_to_engine(engine, "LOBBY", lobby_peers, player_id)

        cmd_task = asyncio.create_task(live_input.get_command())
        done, _ = await asyncio.wait(
            [cmd_task, start_task],
            return_when=asyncio.FIRST_COMPLETED, timeout=3.0)

        if not done:
            cmd_task.cancel(); continue

        if start_task in done:
            cmd_task.cancel()
            spawn_room = random.choice(list(engine.mapa.keys()))
            mage.room_id = spawn_room
            await dht.remove_from_room(player_id, "LOBBY")
            await dht.announce_presence(player_id, meu_ip, grpc_port, spawn_room)
            Interface.show_message("[LOBBY] Jogo iniciado!")
            return True

        partes = cmd_task.result().strip().lower().split()
        if not partes: continue
        cmd = partes[0]

        if cmd == "start":
            fresh = await dht.get_players_in_room("LOBBY")
            # Sync final antes de sair: garante que todos os peers estão em
            # engine.players com o addr correcto antes do broadcast da ronda.
            _sync_dht_to_engine(engine, "LOBBY", fresh, player_id)
            await asyncio.gather(*[
                client.broadcast_start_game(addr)
                for pid, addr in fresh.items() if pid != player_id
            ], return_exceptions=True)
            start_task.cancel()
            spawn_room = random.choice(list(engine.mapa.keys()))
            mage.room_id = spawn_room
            await dht.remove_from_room(player_id, "LOBBY")
            await dht.announce_presence(player_id, meu_ip, grpc_port, spawn_room)
            Interface.show_message("[LOBBY] Iniciaste o jogo!")
            return True
        elif cmd == "q":
            start_task.cancel()
            return False
        else:
            Interface.show_message("Comandos lobby: start | q")

    return True


# ─────────────────────────────────────────────────────────────────────────────
# Uma ronda
# ─────────────────────────────────────────────────────────────────────────────
async def run_round(mage, engine, dht, client, player_id, meu_ip, grpc_port,
                    live_input):
    death_task     = asyncio.create_task(mage.death_event.wait())
    round_won_task = asyncio.create_task(mage.round_won_event.wait())
    lava_state     = {"enter": None, "last_tick": None}

    try:
        while mage.is_alive:

            # ── Movimento forçado (Tornadoes) ─────────────────────────────────
            if mage.forced_room:
                dest = mage.forced_room
                mage.forced_room = None
                old = mage.room_id
                mage.room_id = dest
                lava_state["enter"] = None
                lava_state["last_tick"] = None
                await dht.remove_from_room(player_id, old)
                await dht.announce_presence(player_id, meu_ip, grpc_port, dest)
                try:
                    new_peers = await dht.get_players_in_room(dest)
                    _sync_dht_to_engine(engine, dest, new_peers, player_id)
                    await _broadcast_state(client, mage, new_peers, player_id)
                except Exception:
                    pass
                Interface.show_message(f"[TORNADO] Foste expulso para {dest}!")

            # ── Dano de lava (FOGO imune) ─────────────────────────────────────
            now = asyncio.get_event_loop().time()
            if engine.is_room_lava(mage.room_id) and mage.element != "FOGO":
                if lava_state["enter"] is None:
                    lava_state["enter"]     = now
                    lava_state["last_tick"] = now
                    hit, new_hp = mage.take_damage(10)
                    Interface.show_message(f"[LAVA] Sala em chamas! -10 HP ({new_hp})")
                elif now - lava_state["last_tick"] >= 3.0:
                    ticks = int((now - lava_state["enter"]) / 3)
                    dmg   = 5 + ticks * 5
                    lava_state["last_tick"] = now
                    hit, new_hp = mage.take_damage(dmg)
                    Interface.show_message(
                        f"[LAVA] Escalante -{dmg} HP ({new_hp}) — sai ja!")
            else:
                if lava_state["enter"] is not None:
                    lava_state["enter"]     = None
                    lava_state["last_tick"] = None
                    mage.apply_debuff("burn", 10)
                    Interface.show_message("[LAVA] Queimadura! Dano por 10s.")

            cmd_task = asyncio.create_task(live_input.get_command())
            done, _ = await asyncio.wait(
                [cmd_task, death_task, round_won_task],
                return_when=asyncio.FIRST_COMPLETED, timeout=2.0)

            if round_won_task in done:
                cmd_task.cancel()
                return True

            if not done:
                cmd_task.cancel(); continue

            if death_task in done:
                cmd_task.cancel()
                Interface.show_message("Morreste! Aguarda o fim da ronda...")
                await dht.remove_player(player_id)
                await _broadcast_to_all_peers(
                    client, engine, player_id,
                    lambda addr: client.notify_death(addr, player_id))
                return False

            partes = cmd_task.result().strip().lower().split()
            if not partes: continue
            cmd = partes[0]

            if cmd == "m":
                if len(partes) < 2:
                    Interface.show_message("Uso: m <N>  (ex: m 3)")
                    continue
                ready, rem = mage.check_cooldown("move")
                if not ready:
                    Interface.show_message(f"[CD] Movimento em recarga — {rem:.1f}s")
                    continue
                nova = f"SALA_{partes[1].upper()}"
                if mage.invisible:
                    mage.invisible = False
                    await dht.announce_presence(
                        player_id, meu_ip, grpc_port, mage.room_id)
                    Interface.show_message("[NEGRO] Invisibilidade quebrada!")
                if engine.is_room_locked(mage.room_id):
                    Interface.show_message(
                        f"[AVALANCHE] {mage.room_id} bloqueada! Nao podes sair.")
                    continue
                if engine.is_room_locked(nova):
                    Interface.show_message(
                        f"[AVALANCHE] {nova} bloqueada! Nao podes entrar.")
                    continue
                if engine.validar_movimento(mage.room_id, nova):
                    old      = mage.room_id
                    was_lava = engine.is_room_lava(old)
                    mage.room_id = nova
                    if was_lava and mage.element != "FOGO":
                        lava_state["enter"]     = None
                        lava_state["last_tick"] = None
                        mage.apply_debuff("burn", 10)
                        Interface.show_message("[LAVA] Queimadura! Dano por 10s.")
                    mage.set_cooldown("move")
                    await dht.remove_from_room(player_id, old)
                    await dht.announce_presence(player_id, meu_ip, grpc_port, nova)
                    try:
                        old_peers = await dht.get_players_in_room(old)
                        for pid, addr in old_peers.items():
                            if pid != player_id:
                                await client.notify_move(addr, nova)
                        new_peers = await dht.get_players_in_room(nova)
                        _sync_dht_to_engine(engine, nova, new_peers, player_id)
                        await _broadcast_state(client, mage, new_peers, player_id)
                    except Exception:
                        pass
                    Interface.show_message(f"Moveste-te para {nova}.")
                else:
                    Interface.show_message(
                        f"Nao podes ir de {mage.room_id} para {nova}.")

            elif cmd in ("a", "s", "u"):
                tipo = {"a": "ataque", "s": "skill", "u": "ulti"}[cmd]
                if mage.has_debuff("chained"):
                    rem = mage.debuff_remaining("chained")
                    Interface.show_message(f"Estas acorrentado! ({rem:.1f}s restante)")
                    continue
                await _dispatch_ability(
                    tipo, partes[1:], mage, engine, dht, client,
                    player_id, meu_ip, grpc_port)

            elif cmd == "q":
                return False

            else:
                Interface.show_message("Comandos: m <N> | a [N] | s [N] | u [N] | q")

    finally:
        death_task.cancel()
        round_won_task.cancel()

    return False


# ─────────────────────────────────────────────────────────────────────────────
# Loop de rondas
# ─────────────────────────────────────────────────────────────────────────────
async def run_rounds(mage, engine, dht, client, player_id, meu_ip, grpc_port,
                     live, live_input, ctx):
    ctx["in_lobby"] = False

    try:
        peers = await dht.get_players_in_room(mage.room_id)
        _sync_dht_to_engine(engine, mage.room_id, peers, player_id)
        await _broadcast_state(client, mage, peers, player_id)
    except Exception:
        pass

    while True:
        mage.reset_for_round()
        spawn_room = random.choice(list(engine.mapa.keys()))
        mage.room_id = spawn_room
        await dht.announce_presence(player_id, meu_ip, grpc_port, spawn_room)

        all_known = set(engine.players.keys()) | {player_id}
        engine.start_new_round(all_known)   # ← limpa room_id obsoleto de todos
        Interface.show_message(
            f"=== RONDA {engine.current_round} — PREPARA-TE! (spawn: {spawn_room}) ===")

        
        await _broadcast_to_all_peers(
            client, engine, player_id,
            lambda addr: client.sync_state(addr, room_id=mage.room_id, hp=mage.hp,
                                            mana=mage.mana, class_type=mage.element))

        try:
            peers = await dht.get_players_in_room(spawn_room)
            _sync_dht_to_engine(engine, spawn_room, peers, player_id)
            await _broadcast_state(client, mage, peers, player_id)
        except Exception:
            pass

        survived = await run_round(
            mage, engine, dht, client, player_id, meu_ip, grpc_port, live_input)

        if not survived and not mage.is_alive:
            Interface.show_message("A aguardar resultado da ronda... (q para sair)")

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
                break
        elif not survived:
            break

        if survived:
            engine.add_round_win(player_id)
            wins = engine.round_scores.get(player_id, 0)
            Interface.show_message(
                f"VENCESTE a ronda {engine.current_round}! "
                f"({wins}/{engine.MAX_WINS} para o campeonato)")
            rn = engine.current_round
            await _broadcast_to_all_peers(
                client, engine, player_id,
                lambda addr: client.broadcast_round_win(addr, player_id, rn))

        champion_id = engine.get_champion()
        if champion_id:
            ranking = engine.get_leaderboard(top_n=10)
            if not any(r[0] == player_id for r in ranking):
                ranking.append((player_id,
                                engine.round_scores.get(player_id, 0),
                                mage.element))
                ranking.sort(key=lambda x: x[1], reverse=True)
            champ_elem = (
                engine.players.get(champion_id, {}).get("element")
                or (mage.element if champion_id == player_id else "?"))
            Interface.set_champion({
                "winner_id":      champion_id,
                "winner_element": champ_elem,
                "ranking":        ranking,
            })
            Interface.show_message("Prima ENTER para sair...")
            await live_input.get_command(timeout=30.0)
            break

        await asyncio.sleep(3)


# ─────────────────────────────────────────────────────────────────────────────
async def main():
    if len(sys.argv) < 4:
        print("Uso: python3 main.py [ID] [ELEMENTO] [PORTA_GRPC] [IP_BOOTSTRAP]")
        print("Elementos: FOGO | GELO | TERRA | AR | NEGRO")
        return

    player_id    = sys.argv[1]
    element      = sys.argv[2].upper()
    grpc_port    = int(sys.argv[3])
    bootstrap_ip = sys.argv[4] if len(sys.argv) > 4 else None

    mage   = Mage(player_id, player_id, element)
    engine = GameEngine()
    dht    = DHTHandler()
    client = MageClient(player_id, player_id)

    Interface.attach(mage, engine)

    dht_port = 8468 if bootstrap_ip is None else (grpc_port + 1000)
    await dht.start(dht_port, bootstrap_ip)

    server = await serve(mage, engine, grpc_port)
    meu_ip = get_local_ip()

    await dht.announce_presence(player_id, meu_ip, grpc_port, mage.room_id)
    await asyncio.sleep(2)

    mana_task  = asyncio.create_task(mage.regen_mana_loop())
    console    = Console(force_terminal=True)
    live_input = LiveInput()
    ctx        = {"in_lobby": True, "lobby_peers": {}}

    try:
        with Live(Interface.render(in_lobby=True), console=console,
                  screen=True, auto_refresh=False) as live:
            live_input.start()
            refresh_task = asyncio.create_task(_refresh_loop(live, ctx))
            try:
                ok = await run_lobby(mage, engine, dht, client, player_id,
                                     meu_ip, grpc_port, live, live_input, ctx)
                if ok:
                    await run_rounds(mage, engine, dht, client, player_id,
                                     meu_ip, grpc_port, live, live_input, ctx)
            finally:
                refresh_task.cancel()
    finally:
        live_input.stop()
        mana_task.cancel()
        for addr in engine.get_all_known_addresses():
            try:
                await client.leave_game(addr)
            except Exception:
                pass
        await dht.remove_player(player_id)
        dht.stop()
        await server.stop(0)
        print("Jogo terminado.")


if __name__ == "__main__":
    asyncio.run(main())