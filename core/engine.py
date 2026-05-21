class GameEngine:
    def __init__(self):
        # Grelha 3x3:
        # SALA_1 -- SALA_2 -- SALA_3
        #   |          |          |
        # SALA_4 -- SALA_5 -- SALA_6
        #   |          |          |
        # SALA_7 -- SALA_8 -- SALA_9
        self.mapa = {
            "SALA_1": ["SALA_2", "SALA_4"],
            "SALA_2": ["SALA_1", "SALA_3", "SALA_5"],
            "SALA_3": ["SALA_2", "SALA_6"],
            "SALA_4": ["SALA_1", "SALA_5", "SALA_7"],
            "SALA_5": ["SALA_2", "SALA_4", "SALA_6", "SALA_8"],
            "SALA_6": ["SALA_3", "SALA_5", "SALA_9"],
            "SALA_7": ["SALA_4", "SALA_8"],
            "SALA_8": ["SALA_5", "SALA_7", "SALA_9"],
            "SALA_9": ["SALA_6", "SALA_8"],
        }
        
        self.players = {}

    def validar_movimento(self, sala_atual, sala_destino):
        """Verifica se o mago pode ir para a sala que escolheu."""
        if sala_destino in self.mapa.get(sala_atual, []):
            return True
        return False

    def calcular_dano_elemental(self, tipo_ataque, tipo_defesa):
        """Opcional: Lógica de fraquezas (Ex: Fogo dá +10 de dano contra Gelo)."""
        return 0

    # ==========================================
    # NOVO: GESTÃO DE ESTADO DESCENTRALIZADO
    # ==========================================

    def register_or_update_player(self, player_id, name, addr, room_id, hp, mana):
        """Adiciona um novo jogador à lista ou atualiza os seus dados se já existir."""
        self.players[player_id] = {
            "name": name,
            "addr": addr,      # O IP e a Porta gRPC deste jogador
            "room_id": room_id,
            "hp": hp,
            "mana": mana
        }

    def update_player_room(self, player_id, new_room_id):
        """Atualiza apenas a sala de um jogador (usado quando alguém se move)."""
        if player_id in self.players:
            self.players[player_id]["room_id"] = new_room_id

    def remove_player(self, player_id):
        """Remove um jogador da nossa visão do mundo (usado quando ele sai do jogo)."""
        if player_id in self.players:
            del self.players[player_id]

    def get_players_in_room(self, room_id, exclude_id=None):
        """
        Retorna uma lista com os 'endereços (IP:Porta)' de todos os jogadores
        que estão numa sala específica. Útil para Broadcast (Chat, Combate, etc).
        """
        addresses = []
        for pid, data in self.players.items():
            if data["room_id"] == room_id:
                if pid != exclude_id: # Para não enviarmos mensagens a nós próprios
                    addresses.append(data["addr"])
        return addresses

    def get_player_room(self, player_id):
        """Retorna a sala do jogador pelo ID, ou None se o jogador não existir."""
        player_data = self.players.get(player_id)
        if player_data:
            return player_data.get("room_id")
        return None
        
    def get_all_known_addresses(self):
        """Retorna os endereços de toda a gente na rede que nós conhecemos."""
        return [data["addr"] for data in self.players.values()]