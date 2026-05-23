
import asyncio
from core.mage import Mage

class MagoFogo(Mage):
    def __init__(self, player_id, player_name):
        super().__init__(player_id, player_name, "FOGO")
        self.skills = {
            "ataque1": {"skill": "Fire Ball",   "dano": 40, "custo": 40},
            "ataque2": {"skill": "Flame Dart",  "dano": 25, "custo": 20},
            "skill":   None,  # ainda não definida
            "ultimate": {"skill": "Eruption",   "dano": 30, "custo": 60},
        }
        self.attack_mode = "ataque1"
        self.ultimate_cooldown = False

    def get_attack_info(self):
        atk = self.skills[self.attack_mode]
        self.attack_mode = "ataque2" if self.attack_mode == "ataque1" else "ataque1"
        return atk["dano"], atk["custo"], atk["skill"]

    def activate_shield(self):
        return False, "Mago de Fogo não tem escudo!"

    async def use_ultimate(self, mage, engine, dht, client, player_id):
        if self.ultimate_cooldown:
            return False, "Eruption em cooldown!"
        sk = self.skills["ultimate"]
        if not self.use_mana(sk["custo"]):
            return False, "Mana insuficiente para Eruption! (Custo: 60)"

        self.ultimate_cooldown = True
        sala_lava = mage.room_id
        asyncio.create_task(self._eruption_loop(
            mage, engine, dht, client, player_id, sala_lava
        ))
        asyncio.create_task(self._reset_ultimate(30))
        return True, "Eruption ativada! A sala está a encher de lava!"

    async def _eruption_loop(self, mage, engine, dht, client, player_id, sala_lava):
        dano_tick = 10
        duracao = 12
        elapsed = 0
        burn_targets = set()  # jogadores que saíram da sala com queimadura

        while elapsed < duracao:
            await asyncio.sleep(2)
            elapsed += 2
            dano_tick += 5  # dano cresce a cada tick

            inimigos = await dht.get_players_in_room(sala_lava)
            for pid, addr in inimigos.items():
                if pid == player_id:
                    continue
                try:
                    await client.cast_spell(addr, dano_tick, "FOGO", pid)
                except Exception:
                    pass

            # verifica quem saiu da sala para aplicar queimadura
            todos = engine.players
            for pid, data in list(todos.items()):
                if pid == player_id or pid in burn_targets:
                    continue
                if data.get("room_id") != sala_lava:
                    # saiu da sala — aplica queimadura
                    burn_targets.add(pid)
                    addr = data.get("addr")
                    if addr:
                        asyncio.create_task(
                            self._apply_burn(client, addr, pid)
                        )

    async def _apply_burn(self, client, addr, pid):
        """Queimadura: 5 de dano a cada 2s durante 6s."""
        for _ in range(3):
            await asyncio.sleep(2)
            try:
                await client.cast_spell(addr, 5, "FOGO", pid)
            except Exception:
                pass

    async def _reset_ultimate(self, seconds):
        await asyncio.sleep(seconds)
        self.ultimate_cooldown = False