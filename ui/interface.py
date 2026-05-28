"""Interface visual do Wizard Duels — LIVE (rich)."""

from rich.console import Group
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.table import Table
from rich.align import Align
from rich.box import ROUNDED, DOUBLE

ELEMENT_COLORS = {
    "FOGO":  "bright_red",
    "GELO":  "bright_cyan",
    "TERRA": "yellow",
    "AR":    "bright_white",
    "NEGRO": "magenta",
}

_DEBUFF_LABELS = {
    "burn":       ("burn",       "red"),
    "mana_slow":  ("mana_slow",  "cyan"),
    "chained":    ("chained",    "magenta"),
    "dmg_reduce": ("dmg_reduce", "yellow"),
}


def _elem_color(e):
    return ELEMENT_COLORS.get((e or "").upper(), "magenta")

def _elem_label(e):
    el = (e or "?").upper()
    return f"[bold {_elem_color(el)}]{el}[/]"

_BANNER_ART = r"""
 __        __ _                      _   ____               _
 \ \      / /(_) ____  __ _  _ __  __| | |  _ \  _   _   ___| | ___
  \ \ /\ / / | ||_  / / _` || '__|/ _` | | | | || | | | / _ \ |/ __|
   \ V  V /  | | / / | (_| || |  | (_| | | |_| || |_| ||  __/ |\__ \
    \_/\_/   |_|/___| \__,_||_|   \__,_| |____/  \__,_| \___|_||___/
"""

_CROWN_ART = (
    "  /\\  /\\  /\\\n"
    " /  \\/  \\/  \\\n"
    "|____________|\n"
)


class Interface:
    log_buffer     = []
    _mage          = None
    _engine        = None
    _input_buffer  = ""
    _input_prompt  = ">>"
    _champion_data = None

    @staticmethod
    def attach(mage, engine=None):
        Interface._mage   = mage
        Interface._engine = engine

    @staticmethod
    def set_input_buffer(text, prompt=">>"):
        Interface._input_buffer = text
        Interface._input_prompt = prompt

    @staticmethod
    def show_message(msg):
        if len(Interface.log_buffer) >= 6:
            Interface.log_buffer.clear()
        Interface.log_buffer.append(str(msg))

    @staticmethod
    def set_champion(data):
        Interface._champion_data = data

    @staticmethod
    def _bar(value, maximum, color, width=16):
        value  = max(0, min(value, maximum))
        filled = int(round(value / maximum * width)) if maximum else 0
        b = Text()
        b.append("\u2588" * filled,           style=color)
        b.append("\u2591" * (width - filled), style="grey37")
        b.append(f" {value}/{maximum}",       style="bold white")
        return b

    @staticmethod
    def _banner_panel():
        banner = Text(_BANNER_ART, style="bold magenta", justify="center")
        sub    = Text("Duelo de Magos em Rede P2P",
                      style="italic bright_cyan", justify="center")
        return Panel(Align.center(Group(banner, sub)),
                     box=DOUBLE, border_style="bright_magenta", padding=(0, 2))

    @staticmethod
    def _leaderboard_panel():
        MAX_WINS = 4
        t = Table.grid(padding=(0, 1), expand=True)
        t.add_column(justify="left",   ratio=2)
        t.add_column(justify="center", ratio=1)
        t.add_column(justify="right",  ratio=1)

        mage   = Interface._mage
        engine = Interface._engine

        entries = []
        if mage:
            wins = (engine.round_scores.get(mage.player_id, 0)
                    if engine else 0)
            entries.append((mage.player_id, wins, mage.element))
        if engine:
            for pid, data in list(engine.players.items()):
                if mage and pid == mage.player_id:
                    continue
                wins = engine.round_scores.get(pid, 0)
                entries.append((pid, wins, data.get("element", "?")))

        if not entries:
            for i in range(5):
                t.add_row(Text(f"{i+1}. ---", style="grey50"),
                          Text("?",  style="grey50"),
                          Text("0v", style="grey50"))
            return Panel(
                t, title=f"[bold yellow]LEADERBOARD  (meta: {MAX_WINS}v)[/]",
                border_style="yellow", box=ROUNDED, padding=(1, 1))

        entries.sort(key=lambda x: x[1], reverse=True)
        for i, (name, wins, element) in enumerate(entries[:5]):
            style = "bold yellow" if i == 0 else ("bold white" if i < 3 else "white")
            col   = "bright_green" if wins >= MAX_WINS - 1 else "white"
            bar   = "\u25cf" * wins + "\u25cb" * (MAX_WINS - wins)
            t.add_row(
                Text.from_markup(f"[{style}]{i+1}. {name}[/]"),
                Text.from_markup(_elem_label(element)),
                Text.from_markup(f"[bold {col}]{wins}v[/] [grey50]{bar}[/]"),
            )
        return Panel(t, title=f"[bold yellow]LEADERBOARD  (meta: {MAX_WINS}v)[/]",
                     border_style="yellow", box=ROUNDED, padding=(1, 1))

    @staticmethod
    def _map_grid(current_room, engine=None):
        grid = Table.grid(expand=True)
        for _ in range(3): grid.add_column(justify="center", ratio=1)

        def cell(i):
            sala    = f"SALA_{i}"
            here    = current_room == sala
            effects = engine.active_room_effects(sala) if engine else []
            if   "lava"      in effects: fx = "[red]LAVA[/]"
            elif "locked"    in effects: fx = "[cyan]LOCK[/]"
            elif "wasteland" in effects: fx = "[yellow]WASTE[/]"
            else:                        fx = ""
            mark  = "[bold bright_green]TU[/]" if here else "[grey50].[/]"
            inner = Text.from_markup(
                f"SALA {i}\n{mark}" + (f"\n{fx}" if fx else ""),
                justify="center")
            return Panel(inner, box=ROUNDED,
                         border_style="bright_green" if here else "grey37",
                         style="on grey19" if here else "", padding=(0, 0))

        grid.add_row(cell(1), cell(2), cell(3))
        grid.add_row(cell(4), cell(5), cell(6))
        grid.add_row(cell(7), cell(8), cell(9))
        return grid

    @staticmethod
    def _map_stats_panel(mage):
        engine = Interface._engine
        room   = mage.room_id if mage else None
        return Panel(
            Align.center(Interface._map_grid(room, engine)),
            title="[bold green]MAPA[/]",
            border_style="green", box=ROUNDED, padding=(1, 1))

    @staticmethod
    def _stats_grid(mage):
        if mage is None:
            return Text("(sem dados)", style="grey50")
        t = Table.grid(padding=(0, 1))
        t.add_column(justify="right", style="bold")
        t.add_column()
        t.add_row(Text("HP",   style="bold red"),
                  Interface._bar(mage.hp,   mage.max_hp,   "red"))
        t.add_row(Text("MANA", style="bold blue"),
                  Interface._bar(mage.mana, mage.max_mana, "blue"))
        shield_hp = getattr(mage, "shield_hp", 0)
        if shield_hp > 0:
            t.add_row(Text("ESCUDO", style="bold cyan"),
                      Interface._bar(shield_hp, 50, "cyan", width=10))
        elif getattr(mage, "shielded", False):
            t.add_row(Text("ESCUDO", style="bold cyan"),
                      Text.from_markup("[bold cyan]ATIVO[/]"))
        t.add_row(Text("SALA", style="bold green"),
                  Text.from_markup(f"[bright_green]{mage.room_id}[/]"))
        debuffs = mage.active_debuffs() if hasattr(mage, "active_debuffs") else []
        if debuffs:
            parts = []
            for d in debuffs:
                rem  = mage.debuff_remaining(d) if hasattr(mage, "debuff_remaining") else 0
                _, c = _DEBUFF_LABELS.get(d, (d, "white"))
                parts.append(f"[bold {c}]{d}[/][grey50]{rem:.0f}s[/]")
            t.add_row(Text("DEBUFFS", style="bold magenta"),
                      Text.from_markup("  ".join(parts)))
        if getattr(mage, "invisible", False):
            t.add_row(Text("", style=""),
                      Text.from_markup("[bold magenta]INVISIVEL[/]"))
        return t

    @staticmethod
    def _skills_grid(mage):
        if mage is None or not isinstance(mage.skills.get("ataque"), dict):
            return Text("")
        sk = mage.skills
        t  = Table.grid(padding=(0, 1))
        t.add_column(justify="left")
        t.add_column(justify="right")
        t.add_column(justify="right", min_width=7)
        for key, lbl in (("ataque", "a"), ("skill", "s"), ("ulti", "u")):
            s   = sk[key]
            dmg = (f"[red]{s['dano']}dmg[/]" if s["dano"] > 0 else "[grey50]---[/]")
            if hasattr(mage, "check_cooldown"):
                ready, rem = mage.check_cooldown(key)
                cd = "[green]OK[/]" if ready else f"[yellow]{rem:.1f}s[/]"
            else:
                cd = ""
            t.add_row(
                Text.from_markup(f"[bold bright_green]{lbl}[/] [white]{s['nome']}[/]"),
                Text.from_markup(f"{dmg} [blue]{s['custo']}mp[/]"),
                Text.from_markup(cd))
        if hasattr(mage, "check_cooldown"):
            ready, rem = mage.check_cooldown("move")
            if not ready:
                t.add_row(
                    Text.from_markup("[bold bright_green]m[/] [grey50]Mover[/]"),
                    Text(""),
                    Text.from_markup(f"[yellow]{rem:.1f}s[/]"))
        return t

    @staticmethod
    def _players_panel(mage):
        body = Table.grid(padding=(0, 0))
        body.add_column()
        if mage is not None:
            color = _elem_color(mage.element)
            body.add_row(Text.from_markup(
                f"[bold {color}]{mage.element}[/]  [grey62]{mage.player_id}[/]"))
            body.add_row(Text(""))
            body.add_row(Interface._stats_grid(mage))
            body.add_row(Text(""))
            body.add_row(Interface._skills_grid(mage))
        body.add_row(Text(""))
        body.add_row(Text("Jogadores nesta sala:", style="bold underline"))

        engine = Interface._engine
        peers  = {}
        if engine and mage:
            try:
                peers = {
                    pid: data for pid, data in list(engine.players.items())
                    if pid != mage.player_id
                    and data.get("room_id") == mage.room_id
                    and data.get("alive", True)   # mortos não aparecem como alvos
                }
            except Exception:
                peers = {}

        if peers:
            for i, (pid, data) in enumerate(peers.items()):
                hp     = data.get("hp", "?")
                elem   = data.get("element", "?")
                hp_col = ("bright_green" if isinstance(hp, int) and hp > 50
                          else "yellow"  if isinstance(hp, int) and hp > 25
                          else "red")
                body.add_row(Text.from_markup(
                    f"  [bold bright_green][{i+1}][/] "
                    f"[bold white]{pid}[/]  "
                    f"{_elem_label(elem)}  "
                    f"[bold {hp_col}]{hp}HP[/]"))
        else:
            body.add_row(Text("  (estas sozinho aqui)", style="grey50"))

        return Panel(body, title="[bold cyan]ESTADO & SALA[/]",
                     border_style="cyan", box=ROUNDED, padding=(1, 1))

    @staticmethod
    def _log_panel():
        mage   = Interface._mage
        engine = Interface._engine

        body = Text()
        if Interface.log_buffer:
            for msg in Interface.log_buffer:
                body.append("\u00bb ", style="bright_magenta")
                body.append(f"{msg}\n", style="white")
        else:
            body.append("(sem eventos ainda)\n", style="grey50")

        if mage and engine:
            try:
                peers = {
                    pid: data for pid, data in list(engine.players.items())
                    if pid != mage.player_id
                    and data.get("room_id") == mage.room_id
                    and data.get("alive", True)   # mortos não aparecem como alvos
                }
            except Exception:
                peers = {}
            if peers:
                parts = []
                for i, (pid, data) in enumerate(peers.items()):
                    elem = data.get("element", "?")
                    parts.append(
                        f"[bold bright_green][{i+1}][/] "
                        f"[bold white]{pid}[/] {_elem_label(elem)}")
                alvos_line = Text.from_markup(
                    "[grey50]Alvos:[/]  " + "   ".join(parts))
            else:
                alvos_line = Text.from_markup(
                    "[grey50 italic](sem alvos nesta sala)[/]")
        else:
            alvos_line = Text("")

        cmds = Text.from_markup(
            "[grey50]CMD:[/]  "
            "[bold bright_green]m <N>[/][grey50]mover[/]  "
            "[bold bright_green]a[N][/][grey50]atq[/]  "
            "[bold bright_green]s[N][/][grey50]skill[/]  "
            "[bold bright_green]u[N][/][grey50]ulti[/]  "
            "[bold bright_green]q[/][grey50]sair[/]"
        )
        cursor     = "[blink bright_green]\u258c[/]"
        input_line = Text.from_markup(
            f"[bold bright_green]{Interface._input_prompt}[/] "
            f"[white]{Interface._input_buffer}[/]{cursor}")
        input_box = Panel(input_line, box=ROUNDED,
                          border_style="bright_green", padding=(0, 1))
        return Panel(
            Group(body, alvos_line, Text(""), cmds, Text(""), input_box),
            title="[bold magenta]LOG & COMANDOS[/]",
            border_style="magenta", box=ROUNDED, padding=(1, 1))

    @staticmethod
    def _lobby_panel(lobby_peers):
        peer_ids = list(lobby_peers.keys()) if lobby_peers else []
        t = Table.grid(padding=(0, 1))
        t.add_column()
        t.add_row(Text(f"Jogadores no lobby: {len(peer_ids)}",
                       style="bold bright_white"))
        t.add_row(Text(""))
        if peer_ids:
            for pid in peer_ids:
                t.add_row(Text.from_markup(f"  [bright_cyan]\u00bb[/] {pid}"))
        else:
            t.add_row(Text("  (a espera de jogadores...)", style="grey50"))
        t.add_row(Text(""))
        cmds = Text.from_markup(
            "[grey50]COMANDOS:[/]  "
            "[bold bright_green]start[/][grey50] iniciar[/]  "
            "[bold bright_green]q[/][grey50] sair[/]")
        cursor     = "[blink bright_green]\u258c[/]"
        input_line = Text.from_markup(
            f"[bold bright_green]{Interface._input_prompt}[/] "
            f"[white]{Interface._input_buffer}[/]{cursor}")
        input_box = Panel(input_line, box=ROUNDED,
                          border_style="bright_green", padding=(0, 1))
        return Panel(Group(t, Text(""), cmds, Text(""), input_box),
                     title="[bold bright_white]SALA DE ESPERA[/]",
                     border_style="bright_blue", box=ROUNDED, padding=(1, 2))

    @staticmethod
    def _championship_panel(data):
        winner_id = data["winner_id"]
        winner_el = data.get("winner_element", "?")
        ranking   = data.get("ranking", [])
        color     = _elem_color(winner_el)
        crown = Text(_CROWN_ART, style="bold yellow", justify="center")
        title = Text("CAMPEONATO ENCERRADO!",
                     style="bold bright_yellow", justify="center")
        sub   = Text("CAMPEAO DO TORNEIO", style="bold white", justify="center")
        t = Table.grid(padding=(0, 3))
        t.add_column(justify="right"); t.add_column(justify="left")
        t.add_column(justify="center"); t.add_column(justify="right")
        medals = {0: "[bold yellow]#1[/]", 1: "[bold white]#2[/]",
                  2: "[bold white]#3[/]"}
        for i, (pid, wins, element) in enumerate(ranking):
            medal    = medals.get(i, f"[grey50]#{i+1}[/]")
            pid_col  = color if pid == winner_id else "white"
            wins_col = "bright_green" if wins >= 4 else "white"
            t.add_row(
                Text.from_markup(medal),
                Text.from_markup(f"[bold {pid_col}]{pid}[/]"),
                Text.from_markup(_elem_label(element)),
                Text.from_markup(f"[bold {wins_col}]{wins}v[/]"),
            )
        body = Group(
            Text(""),
            Align.center(crown),
            Text(""),
            Align.center(title),
            Text(""),
            Align.center(Text.from_markup(
                f"[bold {color}]\u2657  {winner_id}  \u2657[/]",
                justify="center")),
            Align.center(sub),
            Text(""),
            Align.center(t),
            Text(""),
            Align.center(Text("[ Prima ENTER para sair ]",
                              style="grey50 italic")),
        )
        return Panel(body, box=DOUBLE, border_style="bold yellow",
                     title="[bold bright_yellow]  WIZARD DUELS  [/]",
                     padding=(1, 6))

    @staticmethod
    def render(in_lobby, lobby_peers=None):
        if Interface._champion_data is not None:
            root = Layout()
            root.update(Interface._championship_panel(Interface._champion_data))
            return root

        if in_lobby:
            root = Layout()
            root.split_column(
                Layout(Interface._banner_panel(), name="banner", size=9),
                Layout(Interface._lobby_panel(lobby_peers or {}), name="lobby"),
            )
            return root

        mage = Interface._mage
        top  = Layout()
        top.split_row(
            Layout(Interface._map_stats_panel(mage), name="map", ratio=3),
            Layout(Interface._leaderboard_panel(),   name="lb",  ratio=2),
        )
        bottom = Layout()
        bottom.split_row(
            Layout(Interface._log_panel(),          name="log",     ratio=3),
            Layout(Interface._players_panel(mage),  name="players", ratio=2),
        )
        title = Align.center(
            Text("\u2694  WIZARD DUELS  \u2694", style="bold magenta"))
        root = Layout()
        root.split_column(
            Layout(title,  name="title",  size=1),
            Layout(top,    name="top"),
            Layout(bottom, name="bottom"),
        )
        return root