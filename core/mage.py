import asyncio


COOLDOWNS = {
    "move":   3.0,
    "ataque": 2.0,
    "skill":  8.0,
    "ulti":   20.0,
}


class Mage:
    def __init__(self, player_id, player_name, element):
        self.player_id   = player_id
        self.player_name = player_name
        self.element     = element

        self.death_event        = asyncio.Event()
        self.game_started_event = asyncio.Event()
        self.round_end_event    = asyncio.Event()
        self.round_won_event    = asyncio.Event()

        self.max_hp   = 100
        self.hp       = 100
        self.max_mana = 100
        self.mana     = 100

        self.skills    = self._setup_skills()
        self.shielded  = False
        self.shield_hp = 0
        self.is_alive  = True
        self.room_id   = "LOBBY"

        self.debuffs     = {}
        self.invisible   = False
        self.forced_room = None
        self.cooldowns   = {}

    @property
    def in_lobby(self):
        return self.room_id == "LOBBY"

    # ── Setup de skills ───────────────────────────────────────────────────────
    def _setup_skills(self):
        configs = {
            "FOGO": {
                "ataque": {"nome": "Fire Ball",   "dano": 22, "custo": 15},
                "skill":  {"nome": "Flame Dart",  "dano": 18, "custo": 12,
                           "efeito": "burn"},
                "ulti":   {"nome": "Eruption",    "dano": 20, "custo": 55,
                           "efeito": "lava_room"},
            },
            "GELO": {
                "ataque": {"nome": "Ice Spear",   "dano": 22, "custo": 15},
                "skill":  {"nome": "Frostbite",   "dano": 25, "custo": 20,
                           "efeito": "mana_slow"},
                "ulti":   {"nome": "Avalanche",   "dano":  0, "custo": 50,
                           "efeito": "room_lock"},
            },
            "AR": {
                "ataque": {"nome": "Windburst",   "dano": 20, "custo": 12},
                "skill":  {"nome": "Wind Slash",  "dano": 15, "custo": 25,
                           "efeito": "aoe_regen"},
                "ulti":   {"nome": "Tornadoes",   "dano":  0, "custo": 55,
                           "efeito": "force_move"},
            },
            "TERRA": {
                "ataque": {"nome": "Earthquake",  "dano": 20, "custo": 28,
                           "efeito": "dmg_reduce"},
                "skill":  {"nome": "Iron Shield", "dano":  0, "custo": 25,
                           "efeito": "shield"},
                "ulti":   {"nome": "WasteLand",   "dano":  0, "custo": 55,
                           "efeito": "wasteland"},
            },
            "NEGRO": {
                "ataque": {"nome": "Dark Orb",    "dano": 25, "custo": 18},
                "skill":  {"nome": "Chained",     "dano":  0, "custo": 20,
                           "efeito": "chain"},
                "ulti":   {"nome": "Dark Ritual", "dano":  0, "custo": 35,
                           "efeito": "invisible"},
            },
        }
        return configs.get(self.element, configs["FOGO"])

    def get_attack_info(self, tipo="ataque"):
        s = self.skills.get(tipo, self.skills["ataque"])
        return s["dano"], s["custo"], s["nome"]

    def get_skill_effect(self, tipo="ataque"):
        return self.skills.get(tipo, {}).get("efeito")

    # ── Cooldowns ─────────────────────────────────────────────────────────────
    def _now(self):
        try:
            return asyncio.get_event_loop().time()
        except RuntimeError:
            import time
            return time.monotonic()

    def check_cooldown(self, action):
        """Retorna (pronto: bool, restante: float)."""
        cd   = COOLDOWNS.get(action, 0)
        last = self.cooldowns.get(action, 0)
        rem  = cd - (self._now() - last)
        return (True, 0.0) if rem <= 0 else (False, rem)

    def set_cooldown(self, action):
        self.cooldowns[action] = self._now()

    # ── Debuffs ───────────────────────────────────────────────────────────────
    def apply_debuff(self, name, duration):
        self.debuffs[name] = self._now() + duration

    def has_debuff(self, name):
        expire = self.debuffs.get(name)
        if expire is None:
            return False
        if self._now() >= expire:
            self.debuffs.pop(name, None)
            return False
        return True

    def active_debuffs(self):
        return [n for n in list(self.debuffs.keys()) if self.has_debuff(n)]

    def debuff_remaining(self, name):
        return max(0.0, self.debuffs.get(name, 0) - self._now())

    # ── Dano & escudo ─────────────────────────────────────────────────────────
    def take_damage(self, amount):
        if self.shield_hp > 0:
            self.shield_hp = max(0, self.shield_hp - amount)
            return False, self.hp
        if self.shielded:
            self.shielded = False
            return False, self.hp
        self.hp = max(0, self.hp - amount)
        if self.hp <= 0:
            self.is_alive = False
            self.death_event.set()
        return True, self.hp

    def activate_iron_shield(self, shield_hp=50):
        custo = self.skills["skill"]["custo"]
        if not self.use_mana(custo):
            return False, f"Mana insuficiente! Iron Shield custa {custo}mp."
        self.shield_hp = shield_hp
        return True, f"Iron Shield ativado! ({shield_hp} HP de escudo)"

    # ── Mana ─────────────────────────────────────────────────────────────────
    def use_mana(self, amount):
        if self.mana >= amount:
            self.mana -= amount
            return True
        return False

    # ── Regen loop ───────────────────────────────────────────────────────────
    async def regen_mana_loop(self):
        tick      = 0
        burn_tick = 0.0
        while True:
            await asyncio.sleep(1)
            if not self.is_alive:
                continue
            tick += 1
            now = asyncio.get_event_loop().time()

            if self.has_debuff("burn") and now >= burn_tick:
                self.hp   = max(0, self.hp - 3)
                burn_tick = now + 2.0
                if self.hp <= 0 and self.is_alive:
                    self.is_alive = False
                    self.death_event.set()

            if tick % 2 == 0 and self.mana < self.max_mana:
                regen = 2 if self.has_debuff("mana_slow") else 5
                self.mana = min(self.max_mana, self.mana + regen)

    # ── Reset de ronda ────────────────────────────────────────────────────────
    def reset_for_round(self):
        self.hp          = self.max_hp
        self.mana        = self.max_mana
        self.shielded    = False
        self.shield_hp   = 0
        self.is_alive    = True
        self.invisible   = False
        self.forced_room = None
        self.debuffs     = {}
        self.cooldowns   = {}   # cooldowns reset a cada ronda
        self.death_event.clear()
        self.round_end_event.clear()
        self.round_won_event.clear()