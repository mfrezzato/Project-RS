import logging
import asyncio
from kademlia.network import Server

# Silenciar logs da biblioteca kademlia
logging.getLogger("kademlia").setLevel(logging.WARNING)

class DHTHandler:
    def __init__(self):
        self.server = Server()
        
    async def start(self, port, bootstrap_ip=None, bootstrap_port=8468):
        """
        Inicia o servidor DHT.
        A alteração crucial para LAN é 'interface="0.0.0.0"'.
        """
        # Escuta em todas as interfaces de rede para receber pacotes de outros PCs
        await self.server.listen(port, interface='0.0.0.0')
        
        if bootstrap_ip:
            # Conecta ao host da partida na rede local
            await self.server.bootstrap([(bootstrap_ip, bootstrap_port)])
            print(f"[DHT] Conectado ao bootstrap em {bootstrap_ip}:{bootstrap_port}")
        else:
            print(f"[DHT] Nó semente iniciado na porta {port}")

    async def register_player(self, player_id, ip, port, room):
        """Guarda IP:PORTA|SALA na rede P2P."""
        # O 'ip' aqui deve ser o IP da tua máquina na LAN (ex: 192.168.1.x)
        data = f"{ip}:{port}|{room}"
        await self.server.set(player_id, data)

    async def get_player_data(self, player_id):
        """Recupera dados de um jogador."""
        val = await self.server.get(player_id)
        if val:
            try:
                addr, room = val.split('|')
                return addr, room
            except ValueError:
                return None, None
        return None, None

    async def find_enemies_in_room(self, my_id, my_room, all_ids):
        """Procura magos na mesma sala."""
        enemies = []
        for pid in all_ids:
            if pid == my_id: continue
            addr, room = await self.get_player_data(pid)
            if room == my_room:
                enemies.append({"id": pid, "addr": addr})
        return enemies

    def stop(self):
        self.server.stop()