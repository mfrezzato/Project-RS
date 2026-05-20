import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import grpc
import asyncio
from google.protobuf import empty_pb2
import game_pb2
import game_pb2_grpc
from ui.interface import Interface

class MageServicer(game_pb2_grpc.MageServiceServicer):
    def __init__(self, mage_instance, game_engine):
        self.mage = mage_instance
        self.engine = game_engine
        self.lock = asyncio.Lock()

    async def CastSpell(self, request, context):
        async with self.lock:
            hit, current_hp = self.mage.take_damage(request.damage)
            status_msg = f"{request.attacker_name} atingiu-te!" if hit else "Escudo ativado!"
            Interface.show_message(status_msg)
            print(f"\n[SERVER] {status_msg} HP: {current_hp}")
            return game_pb2.SpellResponse(shielded=not hit, current_hp=current_hp, message=status_msg)

    async def UpdatePosition(self, request, context):
        self.engine.update_player_room(request.player_id, request.room_id)
        Interface.show_message(f"O jogador {request.player_id} moveu-se para {request.room_id}.")
        return empty_pb2.Empty()

    async def SendMessage(self, request, context):
        if request.room_id == self.mage.room_id:
            Interface.show_message(f"{request.sender_name}: {request.content}")
        return empty_pb2.Empty()

    async def SyncState(self, request, context):
        self.engine.register_or_update_player(
            request.player_id, request.player_name, "", request.room_id, request.hp, request.mana
        )
        return empty_pb2.Empty()

    async def LeaveGame(self, request, context):
        self.engine.remove_player(request.player_id)
        Interface.show_message(f"O jogador {request.player_id} desconectou-se.")
        return empty_pb2.Empty()

    async def Heartbeat(self, request, context):
        return game_pb2.Pong(alive=True)

async def serve(mage_instance, game_engine, port):
    server = grpc.aio.server()
    game_pb2_grpc.add_MageServiceServicer_to_server(MageServicer(mage_instance, game_engine), server)
    listen_addr = f'0.0.0.0:{port}'
    server.add_insecure_port(listen_addr)
    print(f"[REDE] Servidor gRPC iniciado em {listen_addr}")
    await server.start()
    return server