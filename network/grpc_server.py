import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import grpc
import asyncio
from google.protobuf import empty_pb2
import game_pb2
import game_pb2_grpc
from ui.interface import Interface


class MageServicer(game_pb2_grpc.MageServiceServicer):
    def __init__(self, mage_instance, game_engine):
        self.mage   = mage_instance
        self.engine = game_engine
        self.lock   = asyncio.Lock()

    async def CastSpell(self, request, context):
        async with self.lock:
            if request.target_id and request.target_id != self.mage.player_id:
                return game_pb2.SpellResponse(
                    shielded=False, current_hp=self.mage.hp,
                    message="Ataque nao te atingiu.")

            attacker_room = self.engine.get_player_room(request.attacker_id)
            if attacker_room is not None and attacker_room != self.mage.room_id:
                return game_pb2.SpellResponse(
                    shielded=True, current_hp=self.mage.hp,
                    message="Ataque bloqueado: Estas noutra sala!")

            hit, current_hp = self.mage.take_damage(request.damage)
            if hit:
                msg = (f"[{request.element_type}] {request.attacker_name} "
                       f"causou {request.damage}dmg! HP: {current_hp}")
            else:
                msg = f"Escudo absorveu o ataque de {request.attacker_name}!"
            Interface.show_message(msg)
            return game_pb2.SpellResponse(
                shielded=not hit, current_hp=current_hp, message=msg)

    async def UpdatePosition(self, request, context):
        self.engine.update_player_room(request.player_id, request.room_id)
        Interface.show_message(f"[MAPA] {request.player_id} -> {request.room_id}")
        return empty_pb2.Empty()

    async def SendMessage(self, request, context):
        content = request.content

        if content == "__START_GAME__" and request.room_id == "LOBBY":
            self.mage.game_started_event.set()
            return empty_pb2.Empty()

        if content.startswith("__ROUND_WIN__:"):
            parts     = content.split(":", 2)
            winner_id = parts[1]
            round_num = parts[2] if len(parts) > 2 else "?"
            self.engine.add_round_win(winner_id)
            wins = self.engine.round_scores.get(winner_id, 0)
            Interface.show_message(
                f"=== Ronda {round_num}: {winner_id} venceu! "
                f"({wins}/{self.engine.MAX_WINS}) ===")
            self.mage.round_end_event.set()
            return empty_pb2.Empty()

        if content.startswith("__DEBUFF__:"):
            parts = content.split(":", 2)
            if len(parts) == 3:
                try:
                    self.mage.apply_debuff(parts[1], float(parts[2]))
                    Interface.show_message(f"[DEBUFF] {parts[1]} por {parts[2]}s!")
                except (ValueError, IndexError):
                    pass
            return empty_pb2.Empty()

        if content.startswith("__ROOM_EFFECT__:"):
            parts = content.split(":", 3)
            if len(parts) == 4:
                try:
                    self.engine.set_room_effect(parts[2], parts[1], float(parts[3]))
                    Interface.show_message(
                        f"[SALA] {parts[2]} -> {parts[1]} por {parts[3]}s")
                except (ValueError, IndexError):
                    pass
            return empty_pb2.Empty()

        if content.startswith("__FORCE_MOVE__:"):
            parts = content.split(":", 1)
            if len(parts) == 2:
                self.mage.forced_room = parts[1]
                Interface.show_message(f"[TORNADO] Vais ser expulso para {parts[1]}!")
            return empty_pb2.Empty()

        if request.room_id == self.mage.room_id:
            Interface.show_message(
                f"[{request.room_id}] {request.sender_name}: {content}")
        return empty_pb2.Empty()

    async def SyncState(self, request, context):
        self.engine.register_or_update_player(
            player_id=request.player_id,
            name=request.player_name,
            addr=None,
            room_id=request.room_id,
            hp=request.hp,
            mana=request.mana,
            element=request.class_type,
        )
        return empty_pb2.Empty()

    async def LeaveGame(self, request, context):
        self.engine.remove_player(request.player_id)
        Interface.show_message(f"[REDE] {request.player_id} desconectou-se.")
        return empty_pb2.Empty()

    async def PlayerDied(self, request, context):
        dead_id = request.player_id
        # mark_player_dead: tira do alive_this_round E marca alive=False em players
        # → desaparece dos alvos e da UI, mas addr é mantido para broadcasts
        self.engine.mark_player_dead(dead_id)
        Interface.show_message(f"[COMBATE] {dead_id} foi derrotado!")
        if self.mage.is_alive and self.engine.is_last_alive(self.mage.player_id):
            self.mage.round_won_event.set()
        return empty_pb2.Empty()

    async def Heartbeat(self, request, context):
        return game_pb2.Pong(alive=True)


async def serve(mage_instance, game_engine, port):
    server = grpc.aio.server()
    game_pb2_grpc.add_MageServiceServicer_to_server(
        MageServicer(mage_instance, game_engine), server)
    server.add_insecure_port(f'0.0.0.0:{port}')
    await server.start()
    return server