import asyncio
import sys
import os
import socket
import termios
import tty

from rich.live import Live
from rich.console import Console

from core.classes import MagoGelo, MagoFogo, MagoAr, MagoTerra, MagoNegro
from core.classes.actions import handle_attack, handle_skill, handle_ultimate
from core.engine import GameEngine
from network.dht_handler import DHTHandler
from network.grpc_server import serve
from network.grpc_client import MageClient
from ui.interface import Interface

CLASSES = {
    "GELO":  MagoGelo,
    "FOGO":  MagoFogo,
    "AR":    MagoAr,
    "TERRA": MagoTerra,
    "NEGRO": MagoNegro,
}

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
        self._running = False

    def start(self):
        self._old_termios = termios.tcgetattr(self._fd)
        tty.setcbreak(self._fd)
        self._running = True
        loop = asyncio.get_event_loop()
        loop.add_reader(self._fd, self._on_readable)

    def _on_readable(self):
        try:
            data = os.read(self._fd, 4096).decode(errors="ignore")
        except (IOError, OSError):
            return
        if not data:
            return

        i = 0
        while i < len(data):
            ch = data[i]
            i += 1
            if ch == "\r":
                continue
            if ch == "\n":
                line, self._buffer = self._buffer, ""
                Interface.set_input_buffer("")
                self.queue.put_nowait(line)
            elif ch in ("\x7f", "\b"):
                self._buffer = self._buffer[:-1]
                Interface.set_input_buffer(self._buffer)
            elif ch == "\x03":
                self.queue.put_nowait("SAIR")
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
        self._running = False
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
    """Redesenha o Live a 10fps com dados frescos — elimina piscar e lag de input."""
    while True:
        try:
            live.update(
                Interface.render(
                    in_lobby=ctx["in_lobby"],
                    lobby_peers=ctx.get("lobby_peers"),
                ),
                refresh=True,
            )
        except Exception:
            pass
        await asyncio.sleep(0.1)


async def run_lobby(mage, engine, dht, client, player_id, meu_ip, grpc_port, live, live_input, ctx):
    start_task = asyncio.create_task(mage.game_started_event.wait())

    while mage.in_lobby:
        await dht.announce_presence(player_id, meu_ip, grpc_port, "LOBBY")
        lobby_peers = await dht.get_players_in_room("LOBBY")
        ctx["lobby_peers"] = lobby_peers  # _refresh_loop pega daqui

        cmd_task = asyncio.create_task(live_input.get_command())
        done, pending = await asyncio.wait(
            [cmd_task, start_task],
            return_when=asyncio.FIRST_COMPLETED,
            timeout=3.0,
        )

        if not done:
            cmd_task.cancel()
            continue

        if start_task in done:
            cmd_task.cancel()
            old_room = mage.room_id
            mage.room_id = "SALA_1"
            await dht.remove_from_room(player_id, old_room)
            await dht.announce_presence(player_id, meu_ip, grpc_port, "SALA_1")
            Interface.show_message("[LOBBY] Jogo iniciado! A mover para SALA_1...")
            return True

        comando_raw = cmd_task.result()
        partes = comando_raw.upper().split()
        if partes:
            cmd = partes[0]
            if cmd == "START":
                fresh_peers = await dht.get_players_in_room("LOBBY")
                broadcast_tasks = [
                    client.broadcast_start_game(addr)
                    for pid, addr in fresh_peers.items()
                    if pid != player_id
                ]
                await asyncio.gather(*broadcast_tasks, return_exceptions=True)
                start_task.cancel()
                old_room = mage.room_id
                mage.room_id = "SALA_1"
                await dht.remove_from_room(player_id, old_room)
                await dht.announce_presence(player_id, meu_ip, grpc_port, "SALA_1")
                Interface.show_message("[LOBBY] Jogo iniciado por ti! A mover para SALA_1...")
                return True

            elif cmd in ("ATACAR1", "ATACAR2", "SKILL", "ULTIMATE"):
                Interface.show_message("O jogo ainda não começou.")

            elif cmd == "SAIR":
                start_task.cancel()
                return False

    return True


async def run_game(mage, engine, dht, client, player_id, meu_ip, grpc_port, live, live_input, ctx):
    ctx["in_lobby"] = False
    death_task = asyncio.create_task(mage.death_event.wait())

    try:
        while mage.is_alive:
            cmd_task = asyncio.create_task(live_input.get_command())
            done, pending = await asyncio.wait(
                [cmd_task, death_task],
                return_when=asyncio.FIRST_COMPLETED,
                timeout=2.0,
            )

            if not done:
                cmd_task.cancel()
                continue

            if death_task in done:
                cmd_task.cancel()
                Interface.show_message("################################")
                Interface.show_message("       MORRESTE! GAME OVER")
                Interface.show_message("################################")
                inimigos = await dht.get_players_in_room(mage.room_id)
                for pid, addr in inimigos.items():
                    if pid != player_id:
                        try:
                            await client.notify_death(addr, player_id)
                        except Exception:
                            pass
                await asyncio.sleep(2)
                break

            comando_raw = cmd_task.result()
            partes = comando_raw.upper().split()
            if not partes:
                continue

            cmd = partes[0]

            if cmd == "MOVER" and len(partes) > 1:
                nova = f"SALA_{partes[1]}"
                if engine.validar_movimento(mage.room_id, nova):
                    old_room = mage.room_id
                    mage.room_id = nova
                    await dht.remove_from_room(player_id, old_room)
                    await dht.announce_presence(player_id, meu_ip, grpc_port, nova)
                else:
                    Interface.show_message("Caminho bloqueado!")

            elif cmd in ("ATACAR1", "ATACAR2"):
                mage.attack_mode = "ataque1" if cmd == "ATACAR1" else "ataque2"
                # ... lógica de escolha do alvo igual ao que já tens ...
                if target_pid:
                    dano, custo, skill = mage.get_attack_info()
                    await handle_attack(mage, skill, dano, custo, alvos, client, player_id, Interface)

            elif cmd == "SKILL":
                destino = await handle_skill(mage, engine, dht, client, player_id, meu_ip, grpc_port, Interface)
                if destino:
                    old_room = mage.room_id
                    mage.room_id = destino
                    await dht.remove_from_room(player_id, old_room)
                    await dht.announce_presence(player_id, meu_ip, grpc_port, destino)

            elif cmd == "ULTIMATE":
                await handle_ultimate(mage, engine, dht, client, player_id, Interface)

            elif cmd == "SAIR":
                break

    finally:
        death_task.cancel()


async def main():
    if len(sys.argv) < 4:
        print("Uso: python3 main.py [ID] [ELEMENTO] [PORTA_GRPC] [IP_BOOTSTRAP(opcional)]")
        return

    player_id = sys.argv[1]
    element = sys.argv[2].upper()
    grpc_port = int(sys.argv[3])
    bootstrap_ip = sys.argv[4] if len(sys.argv) > 4 else None

    mage_class = CLASSES.get(element, MagoFogo)
    mage = mage_class(player_id, player_id)

    engine = GameEngine()
    dht = DHTHandler()
    client = MageClient(player_id, player_id)

    Interface.attach(mage, engine)

    dht_port = 8468 if bootstrap_ip is None else (grpc_port + 1000)
    await dht.start(dht_port, bootstrap_ip)

    server = await serve(mage, engine, grpc_port)
    meu_ip = get_local_ip()

    await dht.announce_presence(player_id, meu_ip, grpc_port, mage.room_id)
    await asyncio.sleep(2)

    mana_task = asyncio.create_task(mage.regen_mana_loop())

    console = Console(force_terminal=True)
    live_input = LiveInput()
    ctx = {"in_lobby": True, "lobby_peers": {}}

    try:
        with Live(
            Interface.render(in_lobby=True),
            console=console,
            screen=True,
            auto_refresh=False,
        ) as live:
            live_input.start()
            refresh_task = asyncio.create_task(_refresh_loop(live, ctx))
            try:
                jogo_comecou = await run_lobby(
                    mage, engine, dht, client, player_id, meu_ip, grpc_port, live, live_input, ctx
                )
                if not jogo_comecou:
                    return

                await run_game(
                    mage, engine, dht, client, player_id, meu_ip, grpc_port, live, live_input, ctx
                )
            finally:
                refresh_task.cancel()
    finally:
        live_input.stop()
        mana_task.cancel()
        todos = engine.get_all_known_addresses()
        for addr in todos:
            try:
                await client.leave_game(addr)
            except Exception:
                pass
        dht.stop()
        await server.stop(0)
        print("Jogo terminado.")


if __name__ == "__main__":
    asyncio.run(main())