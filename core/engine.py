class GameEngine:
    def __init__(self):
        # Define as salas e as suas conexões (quem liga a quem)
        self.mapa = {
            "SALA_1": ["SALA_2", "SALA_3"],
            "SALA_2": ["SALA_1", "SALA_4"],
            "SALA_3": ["SALA_1", "SALA_4"],
            "SALA_4": ["SALA_2", "SALA_3"]
        }

    def validar_movimento(self, sala_atual, sala_destino):
        """Verifica se o mago pode realmente ir para a sala que escolheu."""
        if sala_destino in self.mapa.get(sala_atual, []):
            return True
        return False

    def calcular_dano_elemental(self, tipo_ataque, tipo_defesa):
        """
        Opcional: Podes adicionar lógica de fraquezas aqui.
        Ex: Fogo dá +10 de dano contra Gelo.
        """
        # Por agora, retorna apenas o dano base
        return 0