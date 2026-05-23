
import asyncio
from core.mage import Mage
import random

class MagoNegro(Mage):
    def __init__(self, player_id, player_name):
        super().__init__(player_id, player_name, "NEGRO")
        self.max_mana = 80
        self.mana = 80
        self.skills = {
            "ataque1": {"skill": "Dark Orb",    "dano": 45, "custo": 30},
            "ataque2": {"skill": "Chained",     "dano": 0,  "custo": 20},
            "skill":   {"skill": "Teleport",    "dano": 0,  "custo": 15},
            "ultimate": {"skill": "Dark Ritual","dano": 0,  "custo": 40},
        }
        self.attack_mode = "ataque1"
        self.ultimate_cooldown = False
        self.invisible = False      # modo Dark Ritual

    def get_attack_info(self):
        atk = self.skills[self.attack_mode]
        dano = atk["dano"]

        # Dark Orb escala com HP perdido
        if self.attack_mode == "ataque1":
            hp_ratio = self.hp / self.max_hp
            bonus = int((1.0 - hp_ratio) * 30)
            dano += bonus
            self.hp = max(1, self.hp - 5)  # custo de sangue

        self.attack_mode = "ataque2" if self.attack_mode == "ataque1" else "ataque1"
        return dano, atk["custo"], atk["skill"]

    def activate_shield(self):
        return False, "Mago Negro não tem escudo!"

    def break_invisibility(self):
        """Chamado sempre que o Mago Negro executa qualquer ação."""
        if self.invisible:
            self.invisible = False
            return True  # indica que saiu da invisibilidade
        return False

    async def use_skill(self, mage, engine):
        """
        Teleport — move para uma sala aleatória (pode ser a mesma).
        Medida de emergência.
        """
        sk = self.skills["skill"]
        if not self.use_mana(sk["custo"]):
            return False, "Mana insuficiente para Teleport! (Custo: 15)", None

        self.break_invisibility()
        todas_salas = list(engine.mapa.keys())
        destino = random.choice(todas_salas)
        return True, f"Teleport! Foste para {destino}.", destino

    async def use_ultimate(self, mage, engine, dht, client, player_id):
        """
        Dark Ritual — ativa invisibilidade.
        O mago não aparece na lista de jogadores da sala.
        Ao executar qualquer ação sai da invisibilidade E executa a ação.
        """
        if self.ultimate_cooldown:
            return False, "Dark Ritual em cooldown!"
        sk = self.skills["ultimate"]
        if not self.use_mana(sk["custo"]):
            return False, "Mana insuficiente para Dark Ritual! (Custo: 40)"

        self.invisible = True
        self.ultimate_cooldown = True
        asyncio.create_task(self._reset_ultimate(45))
        return True, "Dark Ritual ativado! Estaes invisivel. A proxima acao revela-te."

    async def _reset_ultimate(self, seconds):
        await asyncio.sleep(seconds)
        self.ultimate_cooldown = False
        self.invisible = False  # segurança: sai da invisibilidade ao fim do cooldown