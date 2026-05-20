import os
import aioconsole

class Interface:
    # Buffer para as mensagens (para não perderes o histórico)
    log_buffer = []

    @staticmethod
    def clear_screen():
        os.system('cls' if os.name == 'nt' else 'clear')

    @staticmethod
    def render_map(current_room):
        rooms = {"SALA_1": " ", "SALA_2": " ", "SALA_3": " ", "SALA_4": " "}
        rooms[current_room] = "@"
        print("       PLANTA DO LABORATÓRIO")
        print("      +-----------+-----------+")
        print(f"      |           |           |")
        print(f"      |  SALA 1   |  SALA 2   |")
        print(f"      |    [{rooms['SALA_1']}]    |    [{rooms['SALA_2']}]    |")
        print("      |           |           |")
        print("      +-----------+-----------+")
        print(f"      |           |           |")
        print(f"      |  SALA 3   |  SALA 4   |")
        print(f"      |    [{rooms['SALA_3']}]    |    [{rooms['SALA_4']}]    |")
        print("      |           |           |")
        print("      +-----------+-----------+")

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
        
        # Log visual das últimas 10 mensagens
        for msg in Interface.log_buffer[-10:]:
            print(f"[LOG]: {msg}")
            
        print("------------------------------------------")
        print(" COMANDOS: MOVER [1-4] | ATACAR | ESCUDO | SAIR")

    @staticmethod
    async def get_input():
        return await aioconsole.ainput(">> ")

    @staticmethod
    def show_message(msg):
        Interface.log_buffer.append(msg)