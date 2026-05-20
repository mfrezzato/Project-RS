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

async def main():
    if len(sys.argv) < 4:
        print("Uso: python3 main.py [ID] [ELEMENTO] [PORTA_GRPC] [IP_BOOTSTRAP(opcional)]")
        return

    player_id = sys.argv[1]
    element = sys.argv[2].upper()
    grpc_port = int(sys.argv[3])
    bootstrap_ip = sys.argv[4] if len(sys.argv) > 4 else None

    # Inicializar instâncias
    mage = Mage(player_id, player_id, element)
    engine = GameEngine()
    dht = DHTHandler()
    client = MageClient(player_id, player_id)
    interface = Interface()

    # Configuração de rede
    dht_port = 8468 if bootstrap_ip is None else (grpc_port + 1000)
    await dht.start(dht_port, bootstrap_ip)
    
    server = await serve(mage, engine, grpc_port)
    meu_ip = get_local_ip()
    
    # Registar presença inicial
    await dht.announce_presence(player_id, meu_ip, grpc_port, mage.room_id)
    await asyncio.sleep(2)

    mana_task = asyncio.create_task(mage.regen_mana_loop())

    # Criar tarefas para o input e para o evento de morte
    death_task = asyncio.create_task(mage.death_event.wait())

    try:
        while mage.is_alive:
            interface.clear_screen()
            interface.render_map(mage.room_id)
            interface.display_status(mage)

            input_task = asyncio.create_task(interface.get_input())
            
            # ESPERA PELO INPUT OU PELA MORTE (O que acontecer primeiro)
            done, pending = await asyncio.wait(
                [input_task, death_task],
                return_when=asyncio.FIRST_COMPLETED
            )

            # --- VERIFICAÇÃO DE MORTE EM TEMPO REAL ---
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

            # --- PROCESSAMENTO DE COMANDO ---
            comando_raw = input_task.result()
            
            partes = comando_raw.upper().split()
            if not partes: continue

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
                    dano, custo, skill = mage.get_attack_info()
                    if mage.use_mana(custo):
                        for pid, addr in alvos.items():
                            res = await client.cast_spell(addr, dano, mage.element)
                            if res:
                                interface.show_message(f"Ataque a {pid}: {res.message}")
                    else:
                        interface.show_message("Mana insuficiente!")

            elif cmd == "ESCUDO":
                sucesso, msg = mage.activate_shield()
                interface.show_message(msg)
            
            elif cmd == "SAIR":
                break
            
            await asyncio.sleep(0.1)

    finally:
        mana_task.cancel()
        dht.stop()
        await server.stop(0)
        print("Jogo terminado.")

if __name__ == "__main__":
    asyncio.run(main())