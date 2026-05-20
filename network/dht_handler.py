import logging
import asyncio
import json
from kademlia.network import Server

logging.getLogger("kademlia").setLevel(logging.WARNING)

class DHTHandler:
    def __init__(self):
        self.server = Server()
        
    async def start(self, port, bootstrap_ip=None, bootstrap_port=8468):
        await self.server.listen(port, interface='0.0.0.0')
        if bootstrap_ip:
            # Tenta conectar ao bootstrap; usa um timeout para não bloquear
            await self.server.bootstrap([(bootstrap_ip, bootstrap_port)])
            print(f"[DHT] Conectado à rede DHT em {bootstrap_ip}:{bootstrap_port}")
        else:
            print(f"[DHT] Nó semente iniciado na porta {port}")

    async def register_player(self, player_id, ip, port, room):
        # Guarda: IP:PORTA|SALA
        data = f"{ip}:{port}|{room}"
        await self.server.set(player_id, data)
        # Pequena pausa para permitir a propagação na rede DHT
        await asyncio.sleep(0.5)

    async def get_player_data(self, player_id):
        val = await self.server.get(player_id)
        if val:
            try:
                addr, room = val.split('|')
                return addr, room
            except ValueError:
                return None, None
        return None, None

    async def register_player_globally(self, player_id):
        """Atualiza a lista global de jogadores de forma simples."""
        raw = await self.server.get("__players__")
        players = raw.split(",") if raw else []
        if player_id not in players:
            players.append(player_id)
            await self.server.set("__players__", ",".join(players))
            await asyncio.sleep(0.5)

    async def get_all_players(self):
        raw = await self.server.get("__players__")
        return raw.split(",") if raw else []

    async def announce_presence(self, player_id, ip, port, room_id):
        key = f"ROOM_{room_id}"
        val = await self.server.get(key)
        players = json.loads(val) if val else {}
        players[player_id] = f"{ip}:{port}"
        await self.server.set(key, json.dumps(players))
        await asyncio.sleep(0.5)

    async def remove_from_room(self, player_id, room_id):
        key = f"ROOM_{room_id}"
        val = await self.server.get(key)
        players = json.loads(val) if val else {}
        if player_id in players:
            del players[player_id]
            await self.server.set(key, json.dumps(players))

    # ADICIONADO: Obtém quem está na sala
    async def get_players_in_room(self, room_id):
        print(f"\n>>>>>>> DEBUG DHT: A BUSCAR SALA {room_id} <<<<<<<")
        key = f"ROOM_{room_id}"
        val = await self.server.get(key)
        data = json.loads(val) if val else {}
        print(f"[DEBUG DHT] Sala: {room_id} | Dados encontrados: {data}")
        return json.loads(val) if val else {}

    def stop(self):
        self.server.stop()