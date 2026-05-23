# core/classes/actions.py
import asyncio
from core.classes import MagoAr, MagoNegro, MagoTerra

async def handle_attack(mage, skill, dano, custo, alvos, client, player_id, Interface):
    """Lógica de ataque diferente por classe."""

    # Mago Negro sai da invisibilidade ao atacar
    saiu_invis = mage.break_invisibility() if hasattr(mage, 'break_invisibility') else False
    if saiu_invis:
        Interface.show_message("Saiste da invisibilidade!")

    if not mage.use_mana(custo):
        Interface.show_message("Mana insuficiente!")
        return

    # Wind Slash do Ar atinge todos
    if isinstance(mage, MagoAr) and skill == "Wind Slash":
        hits = 0
        for tid, addr in alvos.items():
            res = await client.cast_spell(addr, dano, mage.element, tid)
            if res:
                hits += 1
                Interface.show_message(f"[{skill}] -> {tid}: {res.message}")
        asyncio.create_task(mage.apply_wind_slash_regen(hits))

    else:
        # ataque normal a um alvo só
        target_pid = list(alvos.keys())[0]
        res = await client.cast_spell(alvos[target_pid], dano, mage.element, target_pid)
        if res:
            Interface.show_message(f"[{skill}] -> {target_pid}: {res.message}")


async def handle_skill(mage, engine, dht, client, player_id, meu_ip, grpc_port, Interface):
    """Skill do meio — diferente por classe."""

    # Terra: Iron Shield
    if isinstance(mage, MagoTerra):
        sucesso, msg = mage.activate_shield()
        Interface.show_message(msg)

    # Negro: Teleport
    elif isinstance(mage, MagoNegro):
        sucesso, msg, destino = await mage.use_skill(mage, engine)
        Interface.show_message(msg)
        if sucesso and destino:
            return destino  # main.py trata do movimento

    else:
        Interface.show_message("Esta classe não tem skill!")

    return None


async def handle_ultimate(mage, engine, dht, client, player_id, Interface):
    """Ultimate — diferente por classe."""
    sucesso, msg = await mage.use_ultimate(mage, engine, dht, client, player_id)
    Interface.show_message(msg)