import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import grpc
import game_pb2
import game_pb2_grpc
import asyncio
import logging

logging.basicConfig(level=logging.WARNING)


class MageClient:
    def __init__(self, my_id, my_name):
        self.my_id   = my_id
        self.my_name = my_name

    async def cast_spell(self, target_addr, damage, element, target_id=""):
        try:
            async with grpc.aio.insecure_channel(target_addr) as ch:
                stub = game_pb2_grpc.MageServiceStub(ch)
                return await stub.CastSpell(game_pb2.SpellRequest(
                    attacker_id=self.my_id, attacker_name=self.my_name,
                    damage=damage, element_type=element, target_id=target_id,
                ), timeout=2.0)
        except Exception as e:
            logging.warning(f"[CLIENT] cast_spell -> {target_addr}: {e}")
            return None

    async def notify_move(self, target_addr, new_room):
        try:
            async with grpc.aio.insecure_channel(target_addr) as ch:
                await game_pb2_grpc.MageServiceStub(ch).UpdatePosition(
                    game_pb2.MoveRequest(player_id=self.my_id, room_id=new_room),
                    timeout=1.0)
        except Exception:
            pass

    async def send_chat_message(self, target_addr, room_id, content):
        try:
            async with grpc.aio.insecure_channel(target_addr) as ch:
                await game_pb2_grpc.MageServiceStub(ch).SendMessage(
                    game_pb2.ChatMessage(player_id=self.my_id,
                                        sender_name=self.my_name,
                                        content=content, room_id=room_id),
                    timeout=1.0)
        except Exception:
            pass

    async def sync_state(self, target_addr, room_id, hp, mana, class_type="MAGE"):
        try:
            async with grpc.aio.insecure_channel(target_addr) as ch:
                await game_pb2_grpc.MageServiceStub(ch).SyncState(
                    game_pb2.StateRequest(
                        player_id=self.my_id, player_name=self.my_name,
                        class_type=class_type, hp=hp, mana=mana, room_id=room_id),
                    timeout=1.0)
        except Exception:
            pass

    async def leave_game(self, target_addr):
        try:
            async with grpc.aio.insecure_channel(target_addr) as ch:
                await game_pb2_grpc.MageServiceStub(ch).LeaveGame(
                    game_pb2.LeaveRequest(player_id=self.my_id), timeout=1.0)
        except Exception:
            pass

    async def ping_player(self, target_addr):
        try:
            async with grpc.aio.insecure_channel(target_addr) as ch:
                res = await game_pb2_grpc.MageServiceStub(ch).Heartbeat(
                    game_pb2.Ping(player_id=self.my_id), timeout=1.0)
                return res.alive
        except Exception:
            return False

    async def notify_death(self, target_addr, dead_player_id):
        try:
            async with grpc.aio.insecure_channel(target_addr) as ch:
                await game_pb2_grpc.MageServiceStub(ch).PlayerDied(
                    game_pb2.PlayerDiedRequest(player_id=dead_player_id),
                    timeout=1.0)
        except Exception:
            pass

    # ── Sentinelas de jogo ────────────────────────────────────────────────────
    async def broadcast_start_game(self, target_addr):
        await self.send_chat_message(target_addr, "LOBBY", "__START_GAME__")

    async def broadcast_round_win(self, target_addr, winner_id, round_num):
        await self.send_chat_message(
            target_addr, "GAME", f"__ROUND_WIN__:{winner_id}:{round_num}")

    async def send_debuff(self, target_addr, debuff_name, duration):
        """Aplica debuff no peer: __DEBUFF__:nome:duracao"""
        await self.send_chat_message(
            target_addr, "GAME", f"__DEBUFF__:{debuff_name}:{duration}")

    async def broadcast_room_effect(self, target_addr, effect, room_id, duration):
        """Notifica efeito de sala: __ROOM_EFFECT__:efeito:sala:duracao"""
        await self.send_chat_message(
            target_addr, "GAME",
            f"__ROOM_EFFECT__:{effect}:{room_id}:{duration}")

    async def send_force_move(self, target_addr, dest_room_id):
        """Força movimento do peer: __FORCE_MOVE__:sala"""
        await self.send_chat_message(
            target_addr, "GAME", f"__FORCE_MOVE__:{dest_room_id}")