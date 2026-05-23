"""
Interface visual do Wizard Duels — versão LIVE (rich), apenas cores.

Diferença face à versão antiga:
  - Já NÃO imprime nada para o terminal nem usa clear_screen/aioconsole.
  - Constrói e devolve objetos `rich` (Layout/Panel). É o `rich.Live` no
    main.py que desenha tudo continuamente, sem piscar.
  - O texto que o utilizador está a escrever vive numa caixa de input
    desenhada por nós (set_input_buffer), porque com o Live ativo não se
    pode imprimir o prompt diretamente no terminal.
"""

from rich.console import Group
from rich.panel import Panel
from rich.layout import Layout
from rich.text import Text
from rich.table import Table
from rich.align import Align
from rich.box import ROUNDED, DOUBLE


# ----------------------------------------------------------------------
# Cores por elemento (sem emojis, conforme pedido)
# ----------------------------------------------------------------------
ELEMENT_COLORS = {
    "FOGO":  "bright_red",
    "GELO":  "bright_cyan",
    "TERRA": "yellow",
    "AR":    "bright_white",
}


def _elem_color(element):
    return ELEMENT_COLORS.get((element or "").upper(), "magenta")


def _elem_label(element):
    el = (element or "?").upper()
    return f"[bold {_elem_color(el)}]{el}[/]"


# ASCII art do título (sem emojis)
_BANNER_ART = r"""
 __        __ _                      _   ____               _
 \ \      / /(_) ____  __ _  _ __  __| | |  _ \  _   _   ___| | ___
  \ \ /\ / / | ||_  / / _` || '__|/ _` | | | | || | | | / _ \ |/ __|
   \ V  V /  | | / / | (_| || |  | (_| | | |_| || |_| ||  __/ |\__ \
    \_/\_/   |_|/___| \__,_||_|   \__,_| |____/  \__,_| \___|_||___/
"""


class Interface:
    """API estática. O main.py liga o estado via attach() e depois chama
    render() a cada refresh do Live."""

    log_buffer = []

    # Estado ligado pelo main.py
    _mage = None
    _engine = None

    # Linha de comando atual (preenchida pelo leitor de input do main.py)
    _input_buffer = ""
    _input_prompt = ">>"

    # Placeholder da leaderboard (sem implementação real ainda)
    leaderboard = [
        ("---", 0),
        ("---", 0),
        ("---", 0),
        ("---", 0),
        ("---", 0),
    ]

    # ------------------------------------------------------------------
    # Ligacoes de estado (chamadas pelo main.py)
    # ------------------------------------------------------------------
    @staticmethod
    def attach(mage, engine=None):
        Interface._mage = mage
        Interface._engine = engine

    @staticmethod
    def set_input_buffer(text, prompt=">>"):
        Interface._input_buffer = text
        Interface._input_prompt = prompt

    @staticmethod
    def show_message(msg):
        Interface.log_buffer.append(msg)

    # ------------------------------------------------------------------
    # Barras HP / Mana
    # ------------------------------------------------------------------
    @staticmethod
    def _bar(value, maximum, color, width=16):
        value = max(0, min(value, maximum))
        filled = int(round((value / maximum) * width)) if maximum else 0
        bar = Text()
        bar.append("\u2588" * filled, style=color)
        bar.append("\u2591" * (width - filled), style="grey37")
        bar.append(f" {value}/{maximum}", style="bold white")
        return bar

    # ------------------------------------------------------------------
    # Paineis
    # ------------------------------------------------------------------
    @staticmethod
    def _banner_panel():
        banner = Text(_BANNER_ART, style="bold magenta", justify="center")
        sub = Text("Duelo de Magos em Rede P2P", style="italic bright_cyan", justify="center")
        return Panel(
            Align.center(Group(banner, sub)),
            box=DOUBLE, border_style="bright_magenta", padding=(0, 2),
        )

    @staticmethod
    def _leaderboard_panel():
        t = Table.grid(padding=(0, 1), expand=True)
        t.add_column(justify="left", ratio=1)
        t.add_column(justify="right")
        for i, (name, score) in enumerate(Interface.leaderboard[:5]):
            rank = f"{i + 1}."
            style = "bold yellow" if i < 3 else "white"
            t.add_row(Text(f"{rank} {name}", style=style),
                      Text(str(score), style="bright_green"))
        return Panel(t, title="[bold yellow]LEADERBOARD[/]",
                     border_style="yellow", box=ROUNDED, padding=(1, 1))

    @staticmethod
    def _map_grid(current_room):
        grid = Table.grid(expand=True)
        for _ in range(3):
            grid.add_column(justify="center", ratio=1)

        def cell(i):
            here = current_room == f"SALA_{i}"
            mark = "[bold bright_green]TU[/]" if here else "[grey50].[/]"
            inner = Text.from_markup(f"SALA {i}\n{mark}", justify="center")
            return Panel(inner, box=ROUNDED,
                         border_style="bright_green" if here else "grey37",
                         style="on grey19" if here else "", padding=(0, 0))

        grid.add_row(cell(1), cell(2), cell(3))
        grid.add_row(cell(4), cell(5), cell(6))
        grid.add_row(cell(7), cell(8), cell(9))
        return grid

    @staticmethod
    def _stats_grid(mage):
        if mage is None:
            return Text("(sem dados)", style="grey50")
        t = Table.grid(padding=(0, 1))
        t.add_column(justify="right", style="bold")
        t.add_column()
        t.add_row(Text("HP", style="bold red"),
                  Interface._bar(mage.hp, mage.max_hp, "red"))
        t.add_row(Text("MANA", style="bold blue"),
                  Interface._bar(mage.mana, mage.max_mana, "blue"))
        shield = "[bold cyan]ATIVO[/]" if getattr(mage, "shielded", False) else "[grey50]inativo[/]"
        t.add_row(Text("ESCUDO", style="bold cyan"), Text.from_markup(shield))
        t.add_row(Text("SALA", style="bold green"),
                  Text.from_markup(f"[bright_green]{mage.room_id}[/]"))
        return t

    @staticmethod
    def _map_stats_panel(mage):
        room = mage.room_id if mage else None
        body = Align.center(Interface._map_grid(room))
        return Panel(body, title="[bold green]MAPA & ESTADO[/]",
                     border_style="green", box=ROUNDED, padding=(1, 1))

    @staticmethod
    def _log_panel():
        lines = Interface.log_buffer[-9:]
        body = Text()
        if lines:
            for msg in lines:
                body.append("\u00bb ", style="bright_magenta")
                body.append(f"{msg}\n", style="white")
        else:
            body.append("(sem eventos ainda)\n", style="grey50")

        cmds = Text.from_markup(
            "[grey50]COMANDOS:[/]  "
            "[bold bright_green]MOVER <N>[/]  [grey50]|[/]  "
            "[bold bright_green]ATACAR1[/]  [grey50]|[/]  "
            "[bold bright_green]ATACAR2[/]  [grey50]|[/]  "
            "[bold bright_green]SKILL[/]  [grey50]|[/]  "
            "[bold bright_green]ULTIMATE[/]  [grey50]|[/]  "
            "[bold bright_green]SAIR[/]"
        )

        cursor = "[blink bright_green]\u258c[/]"
        input_line = Text.from_markup(
            f"[bold bright_green]{Interface._input_prompt}[/] "
            f"[white]{Interface._input_buffer}[/]{cursor}"
        )
        input_box = Panel(input_line, box=ROUNDED, border_style="bright_green", padding=(0, 1))
        return Panel(
            Group(body, cmds, Text(""), input_box),
            title="[bold magenta]LOG & COMANDOS[/]",
            border_style="magenta", box=ROUNDED, padding=(1, 1),
        )

    @staticmethod
    def _peers_in_room(mage):
        engine = Interface._engine
        if engine is None or mage is None:
            return {}
        peers = {}
        try:
            for pid, data in engine.players.items():
                if pid == mage.player_id:
                    continue
                if data.get("room_id") == mage.room_id:
                    peers[pid] = data.get("element", "?")
        except Exception:
            return {}
        return peers

    @staticmethod
    def _players_panel(mage):
        body = Table.grid(padding=(0, 0))
        body.add_column()
        
        if mage is not None:
            # NOVO: Inserir o estado vital (HP, Mana, Escudo, Sala) no topo absoluto do painel
            body.add_row(Interface._stats_grid(mage))
            body.add_row(Text("")) # Linha em branco para separar as barras do resto do texto
            
            body.add_row(Text.from_markup(
                f"[bold]O teu mago:[/]  {_elem_label(mage.element)}  "
                f"[grey62]({mage.player_id})[/]"))
        
        body.add_row(Text(""))
        body.add_row(Text("Jogadores nesta sala:", style="bold underline"))

        peers = Interface._peers_in_room(mage)
        if peers:
            for pid, element in peers.items():
                body.add_row(Text.from_markup(f"  - [white]{pid}[/]   {_elem_label(element)}"))
        else:
            body.add_row(Text("  (estas sozinho aqui)", style="grey50"))
            
        return Panel(body, title="[bold cyan]MAGOS NA SALA[/]",
                     border_style="cyan", box=ROUNDED, padding=(1, 1))

    @staticmethod
    def _lobby_panel(lobby_peers):
        peer_ids = list(lobby_peers.keys()) if lobby_peers else []
        t = Table.grid(padding=(0, 1))
        t.add_column()
        t.add_row(Text(f"Jogadores na sala: {len(peer_ids)}", style="bold bright_white"))
        t.add_row(Text(""))
        if peer_ids:
            for pid in peer_ids:
                t.add_row(Text.from_markup(f"  [bright_cyan]\u00bb[/] {pid}"))
        else:
            t.add_row(Text("  (a espera de jogadores...)", style="grey50"))
        t.add_row(Text(""))
        t.add_row(Text.from_markup(
            "[grey70]Aguarda o HOST ou escreve[/] [bold bright_green]START[/]"))

        cmds = Text.from_markup(
            "[grey50]COMANDOS:[/]  "
            "[bold bright_green]START[/]  [grey50]|[/]  "
            "[bold bright_green]SAIR[/]"
        )

        cursor = "[blink bright_green]\u258c[/]"
        input_line = Text.from_markup(
            f"[bold bright_green]{Interface._input_prompt}[/] "
            f"[white]{Interface._input_buffer}[/]{cursor}")
        input_box = Panel(input_line, box=ROUNDED, border_style="bright_green", padding=(0, 1))

        return Panel(
            Group(t, Text(""), cmds, Text(""), input_box),
            title="[bold bright_white]SALA DE ESPERA[/]",
            border_style="bright_blue", box=ROUNDED, padding=(1, 2),
        )
    

    @staticmethod
    def render(in_lobby, lobby_peers=None):
        if in_lobby:
            lower = Layout()
            lower.split_row(
                Layout(Interface._lobby_panel(lobby_peers or {}), name="lobby", ratio=2),
                Layout(Interface._leaderboard_panel(), name="lb", ratio=1),
            )
            root = Layout()
            root.split_column(
                Layout(Interface._banner_panel(), name="banner", size=9),
                Layout(lower, name="lower"),
            )
            return root

        mage = Interface._mage
        top = Layout()
        top.split_row(
            Layout(Interface._map_stats_panel(mage), name="map", ratio=3),
            Layout(Interface._leaderboard_panel(), name="lb", ratio=2),
        )
        bottom = Layout()
        bottom.split_row(
            Layout(Interface._log_panel(), name="log", ratio=3),
            Layout(Interface._players_panel(mage), name="players", ratio=2),
        )
        title = Align.center(Text("\u2694  WIZARD DUELS  \u2694", style="bold magenta"))
        root = Layout()
        root.split_column(
            Layout(title, name="title", size=1),
            Layout(top, name="top"),
            Layout(bottom, name="bottom"),
        )
        return root