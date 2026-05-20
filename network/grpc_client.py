import grpc
import game_pb2
import game_pb2_grpc
import asyncio
import logging

# Configuração de logging para sabermos o que se passa na rede
logging.basicConfig(level=logging.INFO)

class MageClient:
    def __init__(self, my_id):
        self.my_id = my_id

    async def cast_spell(self, target_addr, damage, element):
        """
        Envia um ataque para o IP:PORTA de um adversário.
        target_addr deve estar no formato '192.168.x.x:50051'
        """
        try:
            # Estabelece o canal de comunicação para o endereço fornecido
            async with grpc.aio.insecure_channel(target_addr) as channel:
                stub = game_pb2_grpc.MageServiceStub(channel)
                
                # Chamada gRPC assíncrona com timeout para não congelar o jogo
                response = await stub.CastSpell(game_pb2.SpellRequest(
                    attacker_id=self.my_id,
                    damage=damage,
                    element_type=element
                ), timeout=2.0)
                
                return response
        except grpc.aio.AioRpcError as e:
            logging.warning(f"[CLIENT] Falha ao atacar {target_addr}: {e.code()}")
            return None
        except Exception as e:
            logging.error(f"[CLIENT] Erro inesperado ao atacar {target_addr}: {e}")
            return None

    async def notify_move(self, target_addr, new_room):
        """Avisa um vizinho de que mudaste de sala."""
        try:
            async with grpc.aio.insecure_channel(target_addr) as channel:
                stub = game_pb2_grpc.MageServiceStub(channel)
                # Timeout curto para notificações de movimento não bloquearem o jogo
                await stub.UpdatePosition(game_pb2.MoveRequest(
                    player_id=self.my_id,
                    room_id=new_room
                ), timeout=1.0)
        except grpc.aio.AioRpcError:
            # Se o vizinho estiver offline ou com firewall ativa, ignoramos
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