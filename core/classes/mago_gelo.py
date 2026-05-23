
import asyncio
from core.mage import Mage

class MagoGelo(Mage):
    def __init__(self, player_id, player_name):
        super().__init__(player_id, player_name, "GELO")
        self.skills = {
            "ataque1": {"skill": "Ice Spear",  "dano": 35, "custo": 35},
            "ataque2": {"skill": "Frostbite",  "dano": 25, "custo": 30},
            "skill":   None,  # ainda não definida
            "ultimate": {"skill": "Avalanche", "dano": 0,  "custo": 55},
        }
        self.attack_mode = "ataque1"
        self.ultimate_cooldown = False
        # salas bloqueadas pela Avalanche: {sala: task}
        self._salas_bloqueadas = {}

    def get_attack_info(self):
        atk = self.skills[self.attack_mode]
        self.attack_mode = "ataque2" if self.attack_mode == "ataque1" else "ataque1"
        return atk["dano"], atk["custo"], atk["skill"]

    def activate_shield(self):
        return False, "Mago de Gelo não tem escudo!"

    def is_sala_bloqueada(self, sala):
        return sala in self._salas_bloqueadas

    async def use_ultimate(self, mage, engine, dht, client, player_id):
        """
        Avalanche — bloqueia entradas e saídas da sala atual por 15s.
        Players dentro regeneram mana mais devagar.
        O caster pode sair livremente.
        """
        if self.ultimate_cooldown:
            return False, "Avalanche em cooldown!"
        sk = self.skills["ultimate"]
        if not self.use_mana(sk["custo"]):
            return False, "Mana insuficiente para Avalanche! (Custo: 55)"

        self.ultimate_cooldown = True
        sala = mage.room_id
        self._salas_bloqueadas[sala] = True
        asyncio.create_task(self._avalanche_loop(sala, player_id, engine))
        asyncio.create_task(self._reset_ultimate(35))
        return True, f"Avalanche! {sala} está bloqueada por 15 segundos!"

    async def _avalanche_loop(self, sala, caster_id, engine):
        """Durante 15s: bloqueia movimentos e reduz regen de mana dos presos."""
        duracao = 15
        elapsed = 0
        while elapsed < duracao:
            await asyncio.sleep(2)
            elapsed += 2
            # penaliza regen de mana de quem está na sala (exceto caster)
            for pid, data in engine.players.items():
                if pid == caster_id:
                    continue
                if data.get("room_id") == sala:
                    # marca o jogador como "frozen" — o regen_mana_loop
                    # do Mage base não tem este estado, então usamos
                    # uma flag no engine para comunicar ao grpc_server
                    data["mana_slow"] = True

        # desbloqueia
        self._salas_bloqueadas.pop(sala, None)
        for pid, data in engine.players.items():
            data.pop("mana_slow", None)

    async def _reset_ultimate(self, seconds):
        await asyncio.sleep(seconds)
        self.ultimate_cooldown = False