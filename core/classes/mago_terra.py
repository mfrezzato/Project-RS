
import asyncio
from core.mage import Mage


class MagoTerra(Mage):
    def __init__(self, player_id, player_name):
        super().__init__(player_id, player_name, "TERRA")
        self.skills = {
            "ataque1": {"skill": "Earthquake",  "dano": 30, "custo": 35},
            "ataque2": {"skill": "Rock Throw",  "dano": 35, "custo": 25},
            "skill":   {"skill": "Iron Shield", "dano": 0,  "custo": 30},
            "ultimate": {"skill": "WasteLand",  "dano": 0,  "custo": 55},
        }
        self.attack_mode = "ataque1"
        self.ultimate_cooldown = False
        self.shield_hp = 0          # vida do Iron Shield
        self.damage_reduction = 0   # % de redução de dano ativa (Earthquake)

    def get_attack_info(self):
        atk = self.skills[self.attack_mode]
        self.attack_mode = "ataque2" if self.attack_mode == "ataque1" else "ataque1"
        return atk["dano"], atk["custo"], atk["skill"]

    def activate_shield(self):
        """Iron Shield — absorve até 60 de dano antes de quebrar."""
        sk = self.skills["skill"]
        if self.shield_hp > 0:
            return False, f"Iron Shield já ativo! ({self.shield_hp} HP restantes)"
        if not self.use_mana(sk["custo"]):
            return False, "Mana insuficiente para Iron Shield! (Custo: 30)"
        self.shield_hp = 60
        self.shielded = True
        return True, "Iron Shield ativado! (60 HP de escudo)"

    def take_damage(self, amount):
        """Iron Shield absorve dano gradualmente até quebrar."""
        if self.shield_hp > 0:
            if amount <= self.shield_hp:
                self.shield_hp -= amount
                if self.shield_hp == 0:
                    self.shielded = False
                return False, self.hp  # escudo absorveu tudo
            else:
                amount -= self.shield_hp
                self.shield_hp = 0
                self.shielded = False
                # dano restante vai para o HP

        self.hp = max(0, self.hp - amount)
        if self.hp <= 0:
            self.is_alive = False
            self.death_event.set()
        return True, self.hp

    async def use_ultimate(self, mage, engine, dht, client, player_id):
        """
        WasteLand — sala atual e adjacentes tornam-se wasteland por 20s:
        - Todas as ações custam mais mana
        - Dano reduzido ligeiramente
        - O caster é imune
        """
        if self.ultimate_cooldown:
            return False, "WasteLand em cooldown!"
        sk = self.skills["ultimate"]
        if not self.use_mana(sk["custo"]):
            return False, "Mana insuficiente para WasteLand! (Custo: 55)"

        self.ultimate_cooldown = True
        sala_atual = mage.room_id
        salas_afetadas = [sala_atual] + engine.mapa.get(sala_atual, [])

        # marca as salas no engine
        for sala in salas_afetadas:
            engine.wasteland_rooms = getattr(engine, "wasteland_rooms", {})
            engine.wasteland_rooms[sala] = {
                "caster": player_id,
                "mana_extra": 10,      # custo extra por ação
                "dano_reduzido": 0.15, # 15% menos dano
            }

        asyncio.create_task(self._wasteland_loop(engine, salas_afetadas, 20))
        asyncio.create_task(self._reset_ultimate(40))
        return True, f"WasteLand! Salas afetadas: {', '.join(salas_afetadas)}"

    async def _wasteland_loop(self, engine, salas, duracao):
        await asyncio.sleep(duracao)
        for sala in salas:
            if hasattr(engine, "wasteland_rooms"):
                engine.wasteland_rooms.pop(sala, None)

    async def _reset_ultimate(self, seconds):
        await asyncio.sleep(seconds)
        self.ultimate_cooldown = False