import logging
import asyncio
import json
from kademlia.network import Server

logging.getLogger("kademlia").setLevel(logging.WARNING)

class DHTHandler:
    def __init__(self):
        self.server = Server()
        # Local cache: this node is always visible to itself
        # Format: { room_id: { player_id: "ip:port" } }
        self._local_presence = {}

    async def start(self, port, bootstrap_ip=None, bootstrap_port=8468):
        await self.server.listen(port, interface='0.0.0.0')
        if bootstrap_ip:
            await self.server.bootstrap([(bootstrap_ip, bootstrap_port)])
            print(f"[DHT] Conectado à rede DHT em {bootstrap_ip}:{bootstrap_port}")
            await asyncio.sleep(1.0)  # aguarda estabilização da routing table
        else:
            print(f"[DHT] Nó semente iniciado na porta {port}")

    async def announce_presence(self, player_id, ip, port, room_id):
        # 1. Cache local primeiro (visibilidade imediata)
        if room_id not in self._local_presence:
            self._local_presence[room_id] = {}
        self._local_presence[room_id][player_id] = f"{ip}:{port}"

        # 2. Escreve APENAS a chave própria — sem chave partilhada, sem race condition
        await self.server.set(f"PLAYER_{player_id}", f"{room_id}|{ip}:{port}")
        await asyncio.sleep(0.3)

        # 3. Insere o próprio ID no índice de descoberta global
        await self._upsert_index(player_id)

    async def _upsert_index(self, player_id):
        raw = await self.server.get("__players__")
        ids = set(raw.split(",")) if raw else set()
        if player_id not in ids:
            ids.add(player_id)
            await self.server.set("__players__", ",".join(ids))
            await asyncio.sleep(0.3)

    async def remove_from_room(self, player_id, room_id):
        # Limpa cache local; a chave individual é sobrescrita pelo próximo announce_presence
        if room_id in self._local_presence:
            self._local_presence[room_id].pop(player_id, None)

    async def get_players_in_room(self, room_id):
        result = {}

        # Lê o índice global de jogadores
        raw = await self.server.get("__players__")
        all_ids = [p for p in raw.split(",") if p] if raw else []

        # Para cada jogador conhecido, lê a sua chave individual e filtra por sala
        for pid in all_ids:
            val = await self.server.get(f"PLAYER_{pid}")
            if val:
                try:
                    proom, addr = val.split("|", 1)
                    if proom == room_id:
                        result[pid] = addr
                except ValueError:
                    pass

        # Funde com cache local (garante visibilidade própria sempre)
        local = self._local_presence.get(room_id, {})
        result.update(local)

        print(f"[DEBUG DHT] Sala: {room_id} | índice: {all_ids} | local: {local} | final: {result}")
        return result

    async def register_player(self, player_id, ip, port, room):
        data = f"{ip}:{port}|{room}"
        await self.server.set(player_id, data)
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
        await self._upsert_index(player_id)

    async def get_all_players(self):
        raw = await self.server.get("__players__")
        return [p for p in raw.split(",") if p] if raw else []

    def stop(self):
        self.server.stop()