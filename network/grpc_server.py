import grpc
import asyncio
import logging
import game_pb2
import game_pb2_grpc

class MageServicer(game_pb2_grpc.MageServiceServicer):
    def __init__(self, mage_instance):
        # Recebe a instância do Mago (do core/mage.py) para alterar o HP/Mana
        self.mage = mage_instance
        # Lock para evitar que dois ataques em simultâneo corrompam o valor do HP
        self.lock = asyncio.Lock()

    async def CastSpell(self, request, context):
        """Chamado quando outro jogador lança um feitiço contra ti."""
        async with self.lock:
            # Tenta aplicar dano (o método take_damage já gere o escudo)
            hit, current_hp = self.mage.take_damage(request.damage)
            
            status_msg = f"Foste atingido por {request.element_type}!" if hit else "Escudo absorveu o ataque!"
            print(f"\n[SERVER] {status_msg} HP atual: {current_hp}")

            return game_pb2.SpellResponse(
                shielded=not hit,
                current_hp=current_hp,
                message=status_msg
            )

    async def UpdatePosition(self, request, context):
        """Chamado quando um colega avisa que mudou de sala."""
        print(f"\n[SERVER] O jogador {request.player_id} moveu-se para {request.room_id}.")
        # Aqui poderias atualizar uma lista local de "quem está onde"
        return game_pb2.Empty()

    async def Heartbeat(self, request, context):
        """Mantém a rede P2P ciente de que ainda estás online."""
        return game_pb2.Pong(alive=True)

async def serve(mage_instance, port):
    """Inicia o servidor gRPC assíncrono."""
    server = grpc.aio.server()
    game_pb2_grpc.add_MageServiceServicer_to_server(
        MageServicer(mage_instance), server
    )
    
    # ALTERAÇÃO: '0.0.0.0' garante que o servidor escuta pedidos de qualquer PC na rede LAN.
    # '[::]' seria apenas para IPv6 e poderia causar falhas em redes IPv4.
    listen_addr = f'0.0.0.0:{port}'
    server.add_insecure_port(listen_addr)
    
    print(f"[SERVER] Servidor gRPC iniciado em {listen_addr}")
    await server.start()
    return server