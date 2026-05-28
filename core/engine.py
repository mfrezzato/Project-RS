import time as _time


class GameEngine:
    MAX_WINS = 4

    def __init__(self):
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
        self.players          = {}
        self.round_scores     = {}
        self.alive_this_round = set()
        self.current_round    = 0
        self.room_effects     = {}

    # ── Mapa ─────────────────────────────────────────────────────────────────
    def validar_movimento(self, sala_atual, sala_destino):
        return sala_destino in self.mapa.get(sala_atual, [])

    # ── Jogadores ─────────────────────────────────────────────────────────────
    def register_or_update_player(self, player_id, name, addr=None,
                                   room_id="", hp=100, mana=100, element="?"):
        existing = self.players.get(player_id, {})
        self.players[player_id] = {
            "name":    name,
            "addr":    addr if addr else existing.get("addr", ""),
            "room_id": room_id,
            "hp":      hp,
            "mana":    mana,
            "element": (element if element and element != "?"
                        else existing.get("element", "?")),
            # preserva alive=False se já estava marcado como morto
            "alive":   existing.get("alive", True),
        }

    def update_player_room(self, player_id, new_room_id):
        if player_id in self.players:
            self.players[player_id]["room_id"] = new_room_id

    def update_player_hp(self, player_id, hp):
        if player_id in self.players:
            self.players[player_id]["hp"] = max(0, hp)

    def remove_player(self, player_id):
        self.players.pop(player_id, None)
        self.alive_this_round.discard(player_id)

    def mark_player_dead(self, player_id):
        """Marca como morto (some dos alvos/UI) mas mantém addr para broadcasts."""
        if player_id in self.players:
            self.players[player_id]["alive"] = False
        self.alive_this_round.discard(player_id)

    def get_players_in_room(self, room_id, exclude_id=None):
        """Endereços de jogadores vivos numa sala (para notificações internas)."""
        return [
            d["addr"] for pid, d in list(self.players.items())
            if d["room_id"] == room_id
            and pid != exclude_id
            and d.get("addr")
            and d.get("alive", True)
        ]

    def get_player_room(self, player_id):
        d = self.players.get(player_id)
        return d.get("room_id") if d else None

    def get_all_known_addresses(self):
        """Todos os endereços incluindo mortos — usado para broadcasts de ronda."""
        return [d["addr"] for d in self.players.values() if d.get("addr")]

    # ── Efeitos de sala ───────────────────────────────────────────────────────
    def set_room_effect(self, room_id, effect, duration):
        if room_id not in self.room_effects:
            self.room_effects[room_id] = {}
        self.room_effects[room_id][effect] = _time.monotonic() + duration

    def _room_has_effect(self, room_id, effect):
        effects = self.room_effects.get(room_id, {})
        expire  = effects.get(effect)
        if expire is None:
            return False
        if _time.monotonic() >= expire:
            effects.pop(effect, None)
            return False
        return True

    def is_room_locked(self, room_id):
        return self._room_has_effect(room_id, "locked")

    def is_room_lava(self, room_id):
        return self._room_has_effect(room_id, "lava")

    def is_room_wasteland(self, room_id):
        return self._room_has_effect(room_id, "wasteland")

    def active_room_effects(self, room_id):
        return [e for e in list(self.room_effects.get(room_id, {}).keys())
                if self._room_has_effect(room_id, e)]

    # ── Sistema de rondas ─────────────────────────────────────────────────────
    def start_new_round(self, all_player_ids):
        self.current_round += 1
        self.alive_this_round = set(all_player_ids)
        for pid in all_player_ids:
            self.round_scores.setdefault(pid, 0)
            if pid in self.players:
                self.players[pid]["alive"]   = True
                self.players[pid]["room_id"] = ""  # limpa sala obsoleta — preenchida via SyncState

    def remove_from_alive(self, player_id):
        self.alive_this_round.discard(player_id)

    def is_last_alive(self, player_id):
        return (player_id in self.alive_this_round
                and len(self.alive_this_round) == 1)

    def add_round_win(self, player_id):
        self.round_scores[player_id] = self.round_scores.get(player_id, 0) + 1

    def get_champion(self):
        for pid, wins in self.round_scores.items():
            if wins >= self.MAX_WINS:
                return pid
        return None

    def get_leaderboard(self, top_n=8):
        ranked = sorted(self.round_scores.items(),
                        key=lambda x: x[1], reverse=True)
        result = []
        for pid, wins in ranked[:top_n]:
            data = self.players.get(pid, {})
            result.append((pid, wins, data.get("element", "?")))
        return result