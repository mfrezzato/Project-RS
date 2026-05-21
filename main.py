import asyncio
import sys
import socket
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


async def run_lobby(mage, engine, dht, client, interface, player_id, meu_ip, grpc_port):
    """
    Fase 1 — Lobby.
    FIX 1: input_task fora do loop + timeout=3s → re-fetcha DHT sem depender de input.
    FIX 2: asyncio.gather para broadcast simultâneo a todos os peers.
    FIX 5: ">> " impresso manualmente após cada render.
    """
    start_task = asyncio.create_task(mage.game_started_event.wait())
    input_task = asyncio.create_task(interface.get_input())  # FIX 1: um único leitor de stdin

    while mage.in_lobby:
        # FIX 1: DHT é consultada a cada iteração (inclui refreshes por timeout)
        await dht.announce_presence(player_id, meu_ip, grpc_port, "LOBBY")

        lobby_peers = await dht.get_players_in_room("LOBBY")
        interface.clear_screen()
        interface.render_lobby(lobby_peers)
        interface.display_status(mage)
        sys.stdout.write(">> ")  # FIX 5: prompt sempre visível após clear_screen
        sys.stdout.flush()

        done, pending = await asyncio.wait(
            [input_task, start_task],
            return_when=asyncio.FIRST_COMPLETED,
            timeout=10.0  # FIX 1: re-renderiza e re-fetcha DHT a cada 3s
        )

        # FIX 1: Timeout — ninguém interagiu, mas podemos ter novos peers na DHT
        if not done:
            continue  # input_task continua ativo (mesmo leitor de stdin)

        # Outro jogador iniciou o jogo via gRPC → game_started_event foi setado
        if start_task in done:
            input_task.cancel()
            old_room = mage.room_id
            mage.room_id = "SALA_1"
            await dht.remove_from_room(player_id, old_room)
            await dht.announce_presence(player_id, meu_ip, grpc_port, "SALA_1")
            interface.show_message("[LOBBY] Jogo iniciado! A mover para SALA_1...")
            return True

        # Input local do utilizador
        if input_task in done:
            comando_raw = input_task.result()
            partes = comando_raw.upper().split()

            if partes:
                cmd = partes[0]

                if cmd == "START":
                    # FIX 2: Buscar peers frescos e broadcastar todos em simultâneo
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
                    interface.show_message("[LOBBY] Jogo iniciado por ti! A mover para SALA_1...")
                    return True

                elif cmd in ("ATACAR", "ESCUDO"):
                    interface.show_message("O jogo ainda não começou.")

                elif cmd == "SAIR":
                    input_task.cancel()
                    start_task.cancel()
                    return False

            # Criar novo input_task APENAS depois de processar o anterior
            input_task = asyncio.create_task(interface.get_input())

    return True


async def run_game(mage, engine, dht, client, interface, player_id, meu_ip, grpc_port):
    """
    Fase 2 — Jogo.
    FIX 3: timeout=2s no asyncio.wait → stats atualizam sem depender de input.
    FIX 4: Targeting no ATACAR com sub-input para escolha do alvo.
    FIX 5: ">> " impresso manualmente após cada render.
    """
    death_task = asyncio.create_task(mage.death_event.wait())
    input_task = asyncio.create_task(interface.get_input())  # FIX 3: um único leitor de stdin

    try:
        while mage.is_alive:
            interface.clear_screen()
            interface.render_map(mage.room_id)
            interface.display_status(mage)
            sys.stdout.write(">> ")  # FIX 5: prompt sempre visível
            sys.stdout.flush()

            done, pending = await asyncio.wait(
                [input_task, death_task],
                return_when=asyncio.FIRST_COMPLETED,
                timeout=10.0  # FIX 3: atualiza HP/Mana a cada 2s mesmo sem input
            )

            # FIX 3: Timeout → loop volta ao início, re-renderiza stats atualizados
            if not done:
                continue  # input_task continua ativo (mesmo leitor de stdin)

            # Morte em tempo real
            if death_task in done:
                print("\n\n###############################")
                print("       MORRESTE! GAME OVER     ")
                print("###############################\n")
                inimigos = await dht.get_players_in_room(mage.room_id)
                for pid, addr in inimigos.items():
                    if pid != player_id:
                        try:
                            await client.notify_death(addr, player_id)
                        except Exception:
                            pass
                input_task.cancel()
                await asyncio.sleep(2)
                break

            # Processamento de comando
            if input_task not in done:
                continue

            comando_raw = input_task.result()
            partes = comando_raw.upper().split()

            if not partes:
                input_task = asyncio.create_task(interface.get_input())
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
                    interface.show_message("Caminho bloqueado!")

            elif cmd == "ATACAR":
                inimigos = await dht.get_players_in_room(mage.room_id)
                alvos = {pid: addr for pid, addr in inimigos.items() if pid != player_id}

                if not alvos:
                    interface.show_message("Sala vazia...")
                else:
                    # FIX 4: Mostrar lista de alvos e pedir escolha
                    lista_ids = list(alvos.keys())

                    if len(lista_ids) == 1:
                        # Único alvo → sem necessidade de perguntar
                        target_pid = lista_ids[0]
                    else:
                        interface.show_message("=== ESCOLHE UM ALVO ===")
                        for i, pid in enumerate(lista_ids):
                            interface.show_message(f"  [{i + 1}] {pid}")

                        # Re-renderizar para mostrar a lista no log
                        interface.clear_screen()
                        interface.render_map(mage.room_id)
                        interface.display_status(mage)
                        sys.stdout.write("Alvo >> ")
                        sys.stdout.flush()

                        # Sub-input para seleção do alvo (inclui death_task por segurança)
                        target_task = asyncio.create_task(interface.get_input())
                        t_done, _ = await asyncio.wait(
                            [target_task, death_task],
                            return_when=asyncio.FIRST_COMPLETED,
                            timeout=15.0
                        )

                        target_pid = None
                        if not t_done:
                            target_task.cancel()
                            interface.show_message("Tempo esgotado. Ataque cancelado.")
                        elif death_task in t_done:
                            target_task.cancel()
                            # Morte durante seleção → próxima iteração do loop trata
                        else:
                            escolha = target_task.result().strip()
                            if escolha.isdigit():
                                idx = int(escolha) - 1
                                if 0 <= idx < len(lista_ids):
                                    target_pid = lista_ids[idx]
                                else:
                                    interface.show_message("Número inválido.")
                            else:
                                tpid = escolha.upper()
                                if tpid in alvos:
                                    target_pid = tpid
                                else:
                                    interface.show_message(f"'{escolha}' não está na sala.")

                    if target_pid:
                        dano, custo, skill = mage.get_attack_info()
                        if mage.use_mana(custo):
                            res = await client.cast_spell(
                                alvos[target_pid], dano, mage.element, target_pid
                            )
                            if res:
                                interface.show_message(f"[{skill}] → {target_pid}: {res.message}")
                        else:
                            interface.show_message("Mana insuficiente!")

            elif cmd == "ESCUDO":
                sucesso, msg = mage.activate_shield()
                interface.show_message(msg)

            elif cmd == "SAIR":
                break

            # FIX 3: Novo input_task APENAS após processar o anterior (evita múltiplos leitores)
            input_task = asyncio.create_task(interface.get_input())

    finally:
        death_task.cancel()
        if not input_task.done():
            input_task.cancel()


async def main():
    if len(sys.argv) < 4:
        print("Uso: python3 main.py [ID] [ELEMENTO] [PORTA_GRPC] [IP_BOOTSTRAP(opcional)]")
        return

    player_id = sys.argv[1]
    element = sys.argv[2].upper()
    grpc_port = int(sys.argv[3])
    bootstrap_ip = sys.argv[4] if len(sys.argv) > 4 else None

    mage = Mage(player_id, player_id, element)
    engine = GameEngine()
    dht = DHTHandler()
    client = MageClient(player_id, player_id)
    interface = Interface()

    dht_port = 8468 if bootstrap_ip is None else (grpc_port + 1000)
    await dht.start(dht_port, bootstrap_ip)

    server = await serve(mage, engine, grpc_port)
    meu_ip = get_local_ip()

    await dht.announce_presence(player_id, meu_ip, grpc_port, mage.room_id)
    await asyncio.sleep(2)

    mana_task = asyncio.create_task(mage.regen_mana_loop())

    try:
        jogo_comecou = await run_lobby(
            mage, engine, dht, client, interface, player_id, meu_ip, grpc_port
        )

        if not jogo_comecou:
            return

        await run_game(
            mage, engine, dht, client, interface, player_id, meu_ip, grpc_port
        )

    finally:
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