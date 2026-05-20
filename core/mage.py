import asyncio

class Mage:
    def __init__(self, player_id, element):
        self.player_id = player_id
        self.element = element  # "FOGO", "GELO", "TERRA", "AR"
        
        # Atributos base
        self.max_hp = 100
        self.hp = 100
        self.max_mana = 100
        self.mana = 0
        
        # Configuração por elemento
        self.skills = self._setup_skills()
        self.shielded = False
        
        # Status do jogo
        self.is_alive = True
        self.current_room = "SALA_1"

    def _setup_skills(self):
        """Define os custos e danos base de cada tipo de mago."""
        configs = {
            "FOGO":  {"skill": "Bola de Fogo", "dano": 40, "custo": 40},
            "GELO":  {"skill": "Nevasca",      "dano": 25, "custo": 30},
            "TERRA": {"skill": "Escudo",       "dano": 0,  "custo": 20},
            "AR":    {"skill": "Teleporte",    "dano": 10, "custo": 25}
        }
        return configs.get(self.element, configs["FOGO"])

    async def regen_mana_loop(self):
        """Loop assíncrono que regenera mana a cada 2 segundos."""
        while self.is_alive:
            if self.mana < self.max_mana:
                # Recupera 5 de mana por ciclo
                self.mana = min(self.max_mana, self.mana + 5)
            await asyncio.sleep(2)

    def take_damage(self, amount):
        """Aplica dano, verificando se o escudo está ativo."""
        if self.shielded:
            self.shielded = False  # O escudo absorve um ataque e quebra
            return False, self.hp  # Não sofreu dano
        
        self.hp = max(0, self.hp - amount)
        if self.hp == 0:
            self.is_alive = False
        return True, self.hp

    def use_mana(self, amount):
        """Verifica se tem mana suficiente e subtrai."""
        if self.mana >= amount:
            self.mana -= amount
            return True
        return False