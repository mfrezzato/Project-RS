import asyncio

class Mage:
    def __init__(self, player_id, player_name, element):
        self.player_id = player_id
        self.player_name = player_name
        self.element = element
        self.death_event = asyncio.Event()
        self.game_started_event = asyncio.Event()  # NOVO: sinaliza início do jogo

        # Atributos base
        self.max_hp = 100
        self.hp = 100
        self.max_mana = 100
        self.mana = 100

        # Configuração por elemento
        self.skills = self._setup_skills()
        self.shielded = False

        # Status do jogo
        self.is_alive = True
        self.room_id = "LOBBY"  # começa no lobby, não em SALA_1

    @property
    def in_lobby(self):
        """True enquanto o jogo ainda não começou."""
        return self.room_id == "LOBBY"

    def _setup_skills(self):
        """Define os custos e danos base de cada tipo de mago."""
        configs = {
            "FOGO":  {"skill": "Bola de Fogo", "dano": 40, "custo": 40},
            "GELO":  {"skill": "Nevasca",      "dano": 25, "custo": 30},
            "TERRA": {"skill": "Pedrada",      "dano": 35, "custo": 25},
            "AR":    {"skill": "Tornado",      "dano": 20, "custo": 20}
        }
        return configs.get(self.element, configs["FOGO"])

    async def regen_mana_loop(self):
        """Loop assíncrono que regenera mana a cada 2 segundos."""
        while self.is_alive:
            if self.mana < self.max_mana:
                self.mana = min(self.max_mana, self.mana + 5)
            await asyncio.sleep(2)

    def take_damage(self, amount):
        """Aplica dano (chamado pelo gRPC Server), verificando se o escudo está ativo."""
        if self.shielded:
            self.shielded = False  # O escudo absorve um ataque e quebra
            return False, self.hp  # hit=False, Não sofreu dano
        
        self.hp = max(0, self.hp - amount)
        if self.hp <= 0:
            self.is_alive = False
            self.death_event.set()
        return True, self.hp

    def activate_shield(self):
        """Tenta ativar o escudo gastando mana localmente."""
        custo_escudo = 20
        if not self.shielded:
            if self.use_mana(custo_escudo):
                self.shielded = True
                return True, "Escudo mágico ativado! Absorverá o próximo ataque."
            return False, "Mana insuficiente para ativar escudo (Custo: 20)."
        return False, "O teu escudo já está ativo!"

    def get_attack_info(self):
        """Retorna o dano, custo e nome da skill do mago."""
        return self.skills["dano"], self.skills["custo"], self.skills["skill"]

    def use_mana(self, amount):
        """Verifica se tem mana suficiente e subtrai."""
        if self.mana >= amount:
            self.mana -= amount
            return True
        return False