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
        # Recebe a instância do Mago e o motor do jogo
        self.mage = mage_instance
        self.engine = game_engine
        self.lock = asyncio.Lock()

    async def CastSpell(self, request, context):
        """Chamado quando outro jogador lança um feitiço contra ti."""
        async with self.lock:
            # Consulta a sala no motor de jogo
            attacker_room = self.engine.get_player_room(request.attacker_name)
            
            # Validação: Só bloqueamos se soubermos onde o jogador está E for uma sala diferente.
            # Se attacker_room for None (desconhecido), permitimos o ataque para não bloquear o jogo.
            if attacker_room is not None and attacker_room != self.mage.room_id:
                return game_pb2.SpellResponse(
                    shielded=True, 
                    current_hp=self.mage.hp, 
                    message="Ataque bloqueado: Estás noutra sala!"
                )

            # Aplica o dano no objeto Mage
            hit, current_hp = self.mage.take_damage(request.damage)
            
            if hit:
                status_msg = f"Foste atingido por {request.attacker_name} com {request.element_type}!"
            else:
                status_msg = f"Absorveste o ataque de {request.attacker_name} usando o Escudo!"
            
            # Feedback visual
            Interface.show_message(status_msg)
            print(f"\n[COMBATE] {status_msg} (HP Atual: {current_hp})")

            # Resposta gRPC
            return game_pb2.SpellResponse(
                shielded=not hit,
                current_hp=current_hp,
                message=status_msg
            )

    async def UpdatePosition(self, request, context):
        """Chamado quando um colega te avisa que mudou de sala."""
        self.engine.update_player_room(request.player_id, request.room_id)
        Interface.show_message(f"O jogador {request.player_id} moveu-se para a sala {request.room_id}.")
        return empty_pb2.Empty()

    async def SendMessage(self, request, context):
        """Chamado quando alguém envia uma mensagem de chat."""
        if request.room_id == self.mage.room_id:
            Interface.show_message(f"[{request.room_id}] {request.sender_name}: {request.content}")
        return empty_pb2.Empty()

    async def SyncState(self, request, context):
        """Chamado quando outro jogador entra e pede dados."""
        self.engine.register_or_update_player(
            player_id=request.player_id,
            name=request.player_name,
            room_id=request.room_id,
            hp=request.hp,
            mana=request.mana
        )
        return empty_pb2.Empty()

    async def LeaveGame(self, request, context):
        """Chamado quando um jogador sai do jogo voluntariamente."""
        self.engine.remove_player(request.player_id)
        Interface.show_message(f"O jogador {request.player_id} desconectou-se.")
        return empty_pb2.Empty()
    
    async def PlayerDied(self, request, context):
        """ADICIONADO: Chamado quando outro jogador morre."""
        self.engine.remove_player(request.player_id)
        Interface.show_message(f"O jogador {request.player_id} foi derrotado!")
        return empty_pb2.Empty()

    async def Heartbeat(self, request, context):
        """Mantém a rede P2P ciente de que ainda estás online."""
        return game_pb2.Pong(alive=True)


async def serve(mage_instance, game_engine, port):
    """Inicia o servidor gRPC assíncrono."""
    server = grpc.aio.server()
    game_pb2_grpc.add_MageServiceServicer_to_server(
        MageServicer(mage_instance, game_engine), server
    )
    
    listen_addr = f'0.0.0.0:{port}'
    server.add_insecure_port(listen_addr)
    
    print(f"[REDE] Servidor gRPC P2P iniciado em {listen_addr}")
    await server.start()
    return server