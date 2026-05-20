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
    """Descobre o IP da máquina na rede local."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Tenta conectar a um IP externo (não envia dados) para descobrir o IP local da interface
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

    # Inicialização da instância do Mago
    mage_instance = Mage(player_id, element)
    engine = GameEngine()
    dht = DHTHandler()
    client = MageClient(player_id)
    interface = Interface()

    # Logica de portas
    if bootstrap_ip is None:
        dht_port = 8468 
    else:
        dht_port = grpc_port + 1000

    # Iniciar componentes de rede
    await dht.start(dht_port, bootstrap_ip)
    # AQUI: Chamada com a instância correta
    server = await serve(mage_instance, grpc_port)
    
    # AQUI: IP Dinâmico para a LAN
    meu_ip = get_local_ip()
    print(f"[!] Mago iniciado no IP: {meu_ip}:{grpc_port}")
    
    await dht.register_player(player_id, meu_ip, grpc_port, mage_instance.current_room)

    jogadores_na_rede = ["Joao", "Ana", "Pedro", "Mago1", "Mago2", "Maria"]
    mana_task = asyncio.create_task(mage_instance.regen_mana_loop())

    try:
        while mage_instance.is_alive:
            interface.clear_screen()
            interface.render_map(mage_instance.current_room)
            interface.display_status(mage_instance)
            
            comando_raw = await interface.get_input()
            partes = comando_raw.upper().split()
            if not partes: continue

            cmd = partes[0]
            if cmd == "MOVER" and len(partes) > 1:
                nova = f"SALA_{partes[1]}"
                if engine.validar_movimento(mage_instance.current_room, nova):
                    mage_instance.current_room = nova
                    # Registar nova posição na DHT com o IP correto
                    await dht.register_player(player_id, meu_ip, grpc_port, nova)
                else:
                    interface.show_message("Caminho bloqueado!")

            elif cmd == "ATACAR":
                if mage_instance.use_mana(mage_instance.skills['custo']):
                    inimigos = await dht.find_enemies_in_room(player_id, mage_instance.current_room, jogadores_na_rede)
                    if not inimigos:
                        interface.show_message("Sala vazia...")
                    else:
                        for ini in inimigos:
                            # O client vai conectar-se ao IP real obtido da DHT
                            res = await client.cast_spell(ini['addr'], mage_instance.skills['dano'], mage_instance.element)
                            if res:
                                msg = "Defesa!" if res.shielded else f"Dano! HP: {res.current_hp}"
                                interface.show_message(f"Alvo {ini['id']}: {msg}")
                else:
                    interface.show_message("Sem mana!")

            elif cmd == "ESCUDO":
                if mage_instance.use_mana(20):
                    mage_instance.shielded = True
                    interface.show_message("Escudo ativo!")

            elif cmd == "SAIR": break
            await asyncio.sleep(1.2)

    finally:
        mana_task.cancel()
        dht.stop()
        await server.stop(0)

if __name__ == "__main__":
    asyncio.run(main())