import asyncio

class Mage:
    def __init__(self, player_id, player_name, element):
        self.player_id = player_id
        self.player_name = player_name  # NOVO: Guardamos o nome para passar à Interface
        self.element = element  # "FOGO", "GELO", "TERRA", "AR"
        
        # Atributos base
        self.max_hp = 100
        self.hp = 100
        self.max_mana = 100
        self.mana = 100  # ALTERAÇÃO: Começar com a mana cheia para ser mais fácil testar!
        
        # Configuração por elemento
        self.skills = self._setup_skills()
        self.shielded = False
        
        # Status do jogo
        self.is_alive = True
        self.room_id = "SALA_1" # Mudei o nome para bater certo com os outros ficheiros

    def _setup_skills(self):
        """Define os custos e danos base de cada tipo de mago."""
        configs = {
            "FOGO":  {"skill": "Bola de Fogo", "dano": 40, "custo": 40},
            "GELO":  {"skill": "Nevasca",      "dano": 25, "custo": 30},
            "TERRA": {"skill": "Pedrada",      "dano": 35, "custo": 25}, # Mudei isto para ser um ataque
            "AR":    {"skill": "Tornado",      "dano": 20, "custo": 20}
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
        """Aplica dano (chamado pelo gRPC Server), verificando se o escudo está ativo."""
        if self.shielded:
            self.shielded = False  # O escudo absorve um ataque e quebra
            return False, self.hp  # hit=False, Não sofreu dano
        
        self.hp = max(0, self.hp - amount)
        if self.hp == 0:
            self.is_alive = False
        return True, self.hp

    def activate_shield(self):
        """NOVO: Tenta ativar o escudo gastando mana localmente."""
        custo_escudo = 20
        if not self.shielded:
            if self.use_mana(custo_escudo):
                self.shielded = True
                return True, "Escudo mágico ativado! Absorverá o próximo ataque."
            return False, "Mana insuficiente para ativar escudo (Custo: 20)."
        return False, "O teu escudo já está ativo!"

    def get_attack_info(self):
        """NOVO: Retorna o dano, custo e nome da skill do mago para ser usada pela UI."""
        return self.skills["dano"], self.skills["custo"], self.skills["skill"]

    def use_mana(self, amount):
        """Verifica se tem mana suficiente e subtrai."""
        if self.mana >= amount:
            self.mana -= amount
            return True
        return False