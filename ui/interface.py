import os
import aioconsole

class Interface:
    log_buffer = []

    @staticmethod
    def clear_screen():
        os.system('cls' if os.name == 'nt' else 'clear')

    @staticmethod
    def render_lobby(lobby_peers=None):
        """Ecrã de espera antes do jogo começar."""
        peer_ids = list(lobby_peers.keys()) if lobby_peers else []
        count = len(peer_ids)
        print("  ╔══════════════════════════════════╗")
        print("  ║         SALA DE ESPERA           ║")
        print("  ╠══════════════════════════════════╣")
        print(f"  ║  Jogadores na sala: {count:<13}║")
        for pid in peer_ids:
            print(f"  ║   » {pid:<29}║")
        print("  ╠══════════════════════════════════╣")
        print("  ║  Aguarda o HOST ou escreve START ║")
        print("  ║  Comandos: START | SAIR          ║")
        print("  ╚══════════════════════════════════╝")

    @staticmethod
    def render_map(current_room):
        rooms = {f"SALA_{i}": " " for i in range(1, 10)}
        if current_room in rooms:
            rooms[current_room] = "@"
        r = rooms
        print("         MAPA (3x3)")
        print("  +-----------+-----------+-----------+")
        print(f"  |  SALA  1  |  SALA  2  |  SALA  3  |")
        print(f"  |    [{r['SALA_1']}]    |    [{r['SALA_2']}]    |    [{r['SALA_3']}]    |")
        print("  +-----------+-----------+-----------+")
        print(f"  |  SALA  4  |  SALA  5  |  SALA  6  |")
        print(f"  |    [{r['SALA_4']}]    |    [{r['SALA_5']}]    |    [{r['SALA_6']}]    |")
        print("  +-----------+-----------+-----------+")
        print(f"  |  SALA  7  |  SALA  8  |  SALA  9  |")
        print(f"  |    [{r['SALA_7']}]    |    [{r['SALA_8']}]    |    [{r['SALA_9']}]    |")
        print("  +-----------+-----------+-----------+")

    @staticmethod
    def display_status(mage):
        hp_bar = "█" * (mage.hp // 10) + "-" * (10 - (mage.hp // 10))
        mana_bar = "█" * (mage.mana // 10) + "-" * (10 - (mage.mana // 10))

        print("\n==========================================")
        print(f" MAGO DE {mage.element} | ID: {mage.player_id}")
        print(f" HP:   [{hp_bar}] {mage.hp}/100")
        print(f" MANA: [{mana_bar}] {mage.mana}/100")
        print(f" SALA ATUAL: {mage.room_id}")
        print("==========================================")

        for msg in Interface.log_buffer[-10:]:
            print(f"[LOG]: {msg}")

        print("------------------------------------------")
        if mage.in_lobby:
            print(" COMANDOS: START | SAIR")
        else:
            print(" COMANDOS: MOVER [1-9] | ATACAR | ESCUDO | SAIR")

    @staticmethod
    async def get_input():
        # o ">> " é impresso pelo main loop após cada render
        return await aioconsole.ainput("")

    @staticmethod
    def show_message(msg):
        Interface.log_buffer.append(msg)