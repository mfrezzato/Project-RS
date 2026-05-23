
import asyncio
from core.mage import Mage
import random

class MagoAr(Mage):
    def __init__(self, player_id, player_name):
        super().__init__(player_id, player_name, "AR")
        self.skills = {
            "ataque1": {"skill": "Windburst",  "dano": 20, "custo": 20},
            "ataque2": {"skill": "Wind Slash", "dano": 25, "custo": 25},
            "skill":   None,  # ainda não definida
            "ultimate": {"skill": "Tornadoes", "dano": 0,  "custo": 45},
        }
        self.attack_mode = "ataque1"
        self.ultimate_cooldown = False
        self.wind_slash_regen = False  # flag de regen ativa

    def get_attack_info(self):
        atk = self.skills[self.attack_mode]
        # Wind Slash tem lógica especial de regen — tratada no main.py
        self.attack_mode = "ataque2" if self.attack_mode == "ataque1" else "ataque1"
        return atk["dano"], atk["custo"], atk["skill"]

    def activate_shield(self):
        return False, "Mago de Ar não tem escudo!"

    async def regen_mana_loop(self):
        """Regenera mana a cada 1s (mais rápido que os outros)."""
        while self.is_alive:
            if self.mana < self.max_mana:
                self.mana = min(self.max_mana, self.mana + 5)
            await asyncio.sleep(1)

    async def apply_wind_slash_regen(self, hits):
        """
        Wind Slash — recupera mana por 8s baseado em quantas pessoas foram acertadas.
        Chamado pelo main.py após contar os hits.
        """
        regen_por_hit = 5
        ticks = 4  # 4 ticks de 2s = 8s
        bonus = regen_por_hit * hits
        self.wind_slash_regen = True
        for _ in range(ticks):
            await asyncio.sleep(2)
            self.mana = min(self.max_mana, self.mana + bonus)
        self.wind_slash_regen = False

    async def use_ultimate(self, mage, engine, dht, client, player_id):
        """
        Tornadoes — expulsa todos os players da sala para salas adjacentes.
        O caster fica na sala. Informa o caster para onde cada um foi.
        """
        if self.ultimate_cooldown:
            return False, "Tornadoes em cooldown!"
        sk = self.skills["ultimate"]
        if not self.use_mana(sk["custo"]):
            return False, "Mana insuficiente para Tornadoes! (Custo: 45)"

        self.ultimate_cooldown = True
        sala_atual = mage.room_id
        adjacentes = engine.mapa.get(sala_atual, [])

        inimigos = await dht.get_players_in_room(sala_atual)
        expulsos = {}
        for pid, addr in inimigos.items():
            if pid == player_id:
                continue
            destino = random.choice(adjacentes)
            expulsos[pid] = destino
            try:
                # notifica o player para se mover para a sala destino
                await client.force_move(addr, destino)
            except Exception:
                pass

        asyncio.create_task(self._reset_ultimate(25))

        if expulsos:
            msgs = [f"{pid} -> {sala}" for pid, sala in expulsos.items()]
            return True, "Tornadoes! Expulsos: " + ", ".join(msgs)
        return True, "Tornadoes! Mas não havia ninguém na sala."

    async def _reset_ultimate(self, seconds):
        await asyncio.sleep(seconds)
        self.ultimate_cooldown = False