import logging
import asyncio
from kademlia.network import Server

logging.getLogger("kademlia").setLevel(logging.WARNING)


class DHTHandler:
    def __init__(self):
        self.server = Server()
        self._local_presence = {}

    async def start(self, port, bootstrap_ip=None, bootstrap_port=8468):
        await self.server.listen(port, interface='0.0.0.0')
        if bootstrap_ip:
            await self.server.bootstrap([(bootstrap_ip, bootstrap_port)])
            print(f"[DHT] Conectado a rede DHT em {bootstrap_ip}:{bootstrap_port}")
            await asyncio.sleep(1.0)
        else:
            print(f"[DHT] No semente iniciado na porta {port}")

    async def announce_presence(self, player_id, ip, port, room_id):
        if room_id not in self._local_presence:
            self._local_presence[room_id] = {}
        self._local_presence[room_id][player_id] = f"{ip}:{port}"

        await self.server.set(f"PLAYER_{player_id}", f"{room_id}|{ip}:{port}")
        await asyncio.sleep(0.3)
        await self._upsert_index(player_id)

    async def _upsert_index(self, player_id):
        raw = await self.server.get("__players__")
        ids = set(raw.split(",")) if raw else set()
        if player_id not in ids:
            ids.add(player_id)
            await self.server.set("__players__", ",".join(ids))
            await asyncio.sleep(0.3)

    async def remove_from_room(self, player_id, room_id):
        """Remove apenas da cache local. A DHT e atualizada pelo proximo announce."""
        if room_id in self._local_presence:
            self._local_presence[room_id].pop(player_id, None)

    async def remove_player(self, player_id):
        """Marca o jogador como GONE na DHT e remove do indice global.
        Chamado quando o jogador sai do jogo — corrige o bug de visibilidade no lobby."""
        # Limpa cache local em todas as salas
        for room_peers in self._local_presence.values():
            room_peers.pop(player_id, None)

        # Marca como GONE (Kademlia nao suporta delete, mas proom="GONE" e filtrado)
        try:
            await self.server.set(f"PLAYER_{player_id}", "GONE|")
        except Exception:
            pass

        # Remove do indice global
        try:
            raw = await self.server.get("__players__")
            ids = set(raw.split(",")) if raw else set()
            ids.discard(player_id)
            await self.server.set("__players__", ",".join(ids))
        except Exception:
            pass

    async def get_players_in_room(self, room_id):
        result = {}

        raw = await self.server.get("__players__")
        all_ids = [p for p in raw.split(",") if p] if raw else []

        for pid in all_ids:
            val = await self.server.get(f"PLAYER_{pid}")
            if val:
                try:
                    proom, addr = val.split("|", 1)
                    # Filtra GONE (addr vazio) e sala errada
                    if proom == room_id and addr:
                        result[pid] = addr
                except ValueError:
                    pass

        # Funde com cache local (garante visibilidade propria imediata)
        local = self._local_presence.get(room_id, {})
        result.update(local)
        return result

    async def get_player_data(self, player_id):
        val = await self.server.get(player_id)
        if val:
            try:
                addr, room = val.split('|')
                return addr, room
            except ValueError:
                return None, None
        return None, None

    async def get_all_players(self):
        raw = await self.server.get("__players__")
        return [p for p in raw.split(",") if p] if raw else []

    def stop(self):
        self.server.stop()