"""Project literal opening and attack rules from the installed AI scripts."""

from pathlib import Path
import re
from time import monotonic

from war3_fullclone_casc import CascArchive, CascUnavailable, read_build_identity


# Only these worker and construction targets can cross into the order planner.
# Keep faction order and building kinds aligned with the local AI bridge.
FACTIONS = (
    ('human.ai', 'hpea', 'hhou', 'hbar', 'halt', 'hkee'),
    ('orc.ai', 'opeo', 'otrb', 'obar', 'oalt', 'ostr'),
    ('undead.ai', 'uaco', 'uzig', 'usep', 'uaod', 'unp1'),
    ('elf.ai', 'ewsp', 'emow', 'eaom', 'eate', 'etoa'),
)
_CONST = re.compile(r"^\s*constant\s+integer\s+(\w+)\s*=\s*('[A-Za-z0-9]{4}'|[A-Za-z]\w*)\s*$")
_ORDER = re.compile(r"^call\s+SetBuild(?:Unit|Next)\s*\(\s*(\d{1,2})\s*,\s*(\w+|'[A-Za-z0-9]{4}')\s*\)$")
WAVE_VARIABLES = ('c_footman_done', 'c_grunt_done', 'c_ghoul_done', 'c_archer_done')


def _code(value, constants):
    seen = set()
    while value in constants and value not in seen:
        seen.add(value)
        value = constants[value]
    return value[1:-1] if re.fullmatch(r"'[A-Za-z0-9]{4}'", value) else ''


def _opening_calls(script):
    """Read unconditional literal orders inside build_sequence's basic opening."""
    in_builder = False
    depth = 0
    for source in script.splitlines():
        line = source.partition('//')[0].strip()
        if not in_builder:
            in_builder = bool(re.fullmatch(r'function\s+build_sequence\s+takes\s+.*', line))
            continue
        if line == 'endfunction':
            return
        if not depth:
            if re.fullmatch(r'if\s+basic_opening\s+then', line):
                depth = 1
            continue
        if re.match(r'if\s+.+\s+then$', line):
            depth += 1
        elif line == 'endif':
            depth -= 1
            if not depth:
                return
        elif depth == 1:
            if line == 'return' or line == 'else' or line.startswith('elseif '):
                return
            order = _ORDER.fullmatch(line)
            if order:
                yield int(order.group(1)), order.group(2)


def project_opening(common, script, faction):
    _, worker, supply, factory, altar, upgrade = faction
    constants = dict(match.groups() for row in common.splitlines()
                     if (match := _CONST.fullmatch(row.partition('//')[0])))
    worker_target = 0
    steps = []
    amounts = {}
    kinds = {supply: 1, factory: 2, altar: 4}
    for count, value in _opening_calls(script):
        code = _code(value, constants)
        if code == upgrade:
            break
        if code == worker:
            worker_target = max(worker_target, count)
        elif code in kinds and count:
            # Preserve the extra population building the stock script orders
            # before its first factory, and leave later supply to food logic.
            if code == supply and factory in amounts and supply in amounts:
                continue
            if code in amounts and (code != supply or count <= amounts[code]):
                continue
            if len(steps) >= 4:
                return None
            amounts[code] = count
            steps.append((kinds[code], count, worker_target))
    if (not 1 <= worker_target <= 24 or set(amounts) != set(kinds) or
            any(not 1 <= count <= (2 if kind == 1 else 1) for kind, count, _ in steps)):
        return None
    return worker_target, tuple(steps)


def project_wave(script, variable):
    """Read the first literal troop threshold in the stock attack sequence."""
    pattern = re.compile(rf'\b{re.escape(variable)}\s*>=\s*(\d+)\s*(?=$|\)|and\b)')
    in_attack = False
    for source in script.splitlines():
        line = source.partition('//')[0].strip()
        if not in_attack:
            in_attack = bool(re.fullmatch(r'function\s+attack_sequence\s+takes\s+.*', line))
        elif line == 'endfunction':
            break
        elif line.startswith('exitwhen ') and (match := pattern.search(line)):
            count = int(match.group(1))
            return count if 1 <= count <= 12 else 0
    return 0


def read_stock_rules(executable, game_version):
    """Use the official CASC bundle associated with this exact game build."""
    if not executable or not game_version:
        return (), ()
    executable = Path(executable).resolve()
    root = next((folder for folder in executable.parents[:5]
                 if (folder / '.build.info').is_file()), None)
    if root is None:
        return (), ()
    identity = read_build_identity(root)
    if identity.version != game_version:
        return (), ()
    with CascArchive(root, identity, deadline=monotonic() + 6) as archive:
        common = archive.read(r'war3.w3mod:scripts\common.ai', max_bytes=256*1024).decode('utf-8-sig')
        plans = []
        waves = []
        for faction, variable in zip(FACTIONS, WAVE_VARIABLES):
            try:
                member = 'war3.w3mod:scripts\\' + faction[0]
                script = archive.read(member, max_bytes=128*1024).decode('utf-8-sig')
            except (CascUnavailable, UnicodeError, OSError):
                script = ''
            plans.append(project_opening(common, script, faction))
            waves.append(project_wave(script, variable))
    if read_build_identity(root) != identity:
        return (), ()
    return (tuple(plans) if any(plans) else (), tuple(waves) if any(waves) else ())


def stock_rules_for_session(trainer, session):
    """Read once for this map session. Static rules remain available on failure."""
    key = 'fullclone_ai_stock_rules'
    if key not in session.cache:
        profile = getattr(session, 'profile', None)
        try:
            session.cache[key] = read_stock_rules(getattr(trainer, '_executable_path', ''),
                                                  profile.data.get('game_version') if profile else '')
        except (CascUnavailable, UnicodeError, OSError, ValueError):
            session.cache[key] = (), ()
    return session.cache[key]


def read_openings(executable, game_version):
    return read_stock_rules(executable, game_version)[0]
