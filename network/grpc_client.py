import sys
import os
# Isto força o Python a olhar para a pasta raiz (Project-RS/)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


import grpc
import game_pb2
import game_pb2_grpc
import asyncio
import logging

# Configuração de logging
logging.basicConfig(level=logging.INFO)

class MageClient:
    def __init__(self, my_id, my_name):
        self.my_id = my_id
        self.my_name = my_name  # NOVO: Guardamos o nome do jogador

    async def cast_spell(self, target_addr, damage, element):
        """Envia um ataque para o IP:PORTA de um adversário."""
        print(f"[DEBUG] A tentar conectar ao servidor em: {target_addr}")
        try:
            async with grpc.aio.insecure_channel(target_addr) as channel:
                stub = game_pb2_grpc.MageServiceStub(channel)
                
                response = await stub.CastSpell(game_pb2.SpellRequest(
                    attacker_id=self.my_id,
                    attacker_name=self.my_name, # NOVO: Envia o nome
                    damage=damage,
                    element_type=element
                ), timeout=2.0)
                print(f"[DEBUG] Resposta recebida do servidor: {response.message}")
                return response
        except grpc.aio.AioRpcError as e:
            logging.warning(f"[CLIENT] Falha ao atacar {target_addr}. Pode estar offline.")
            return None
        except Exception as e:
            logging.error(f"[CLIENT] Erro inesperado ao atacar {target_addr}: {e}")
            print(f"[ERRO GRPCCLIENT] Falha ao conectar a {target_addr}: {e}")
            return None

    async def notify_move(self, target_addr, new_room):
        """Avisa um vizinho de que mudaste de sala."""
        try:
            async with grpc.aio.insecure_channel(target_addr) as channel:
                stub = game_pb2_grpc.MageServiceStub(channel)
                await stub.UpdatePosition(game_pb2.MoveRequest(
                    player_id=self.my_id,
                    room_id=new_room
                ), timeout=1.0)
        except grpc.aio.AioRpcError:
            pass

    async def send_chat_message(self, target_addr, room_id, message_content):
        """NOVO: Envia uma mensagem de texto para outro jogador."""
        try:
            async with grpc.aio.insecure_channel(target_addr) as channel:
                stub = game_pb2_grpc.MageServiceStub(channel)
                await stub.SendMessage(game_pb2.ChatMessage(
                    player_id=self.my_id,
                    sender_name=self.my_name,
                    content=message_content,
                    room_id=room_id
                ), timeout=1.0)
        except grpc.aio.AioRpcError:
            pass

    async def sync_state(self, target_addr, room_id, hp, mana, class_type="MAGE"):
        """NOVO: Envia os teus dados vitais para um vizinho que acabou de aparecer."""
        try:
            async with grpc.aio.insecure_channel(target_addr) as channel:
                stub = game_pb2_grpc.MageServiceStub(channel)
                await stub.SyncState(game_pb2.StateRequest(
                    player_id=self.my_id,
                    player_name=self.my_name,
                    class_type=class_type,
                    hp=hp,
                    mana=mana,
                    room_id=room_id
                ), timeout=1.0)
        except grpc.aio.AioRpcError:
            pass

    async def leave_game(self, target_addr):
        """NOVO: Avisa um vizinho de que vais fechar o jogo."""
        try:
            async with grpc.aio.insecure_channel(target_addr) as channel:
                stub = game_pb2_grpc.MageServiceStub(channel)
                await stub.LeaveGame(game_pb2.LeaveRequest(
                    player_id=self.my_id
                ), timeout=1.0)
        except grpc.aio.AioRpcError:
            pass

    async def ping_player(self, target_addr):
        """Verifica se um jogador ainda está ativo na rede."""
        try:
            async with grpc.aio.insecure_channel(target_addr) as channel:
                stub = game_pb2_grpc.MageServiceStub(channel)
                response = await stub.Heartbeat(game_pb2.Ping(player_id=self.my_id), timeout=1.0)
                return response.alive
        except grpc.aio.AioRpcError:
            return False