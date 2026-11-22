"""Map-session history for verified owner and diplomacy changes."""
from time import time
from uuid import uuid4

from war3_contracts import format_rawcode
from war3_fullclone_protocol import ALL_TEAM_SLOTS, DiplomacySlotUnavailable


HISTORY_KEY = 'fullclone_operation_history'
HISTORY_LIMIT = 30
_OWNER_RESULTS = {2: 'unit_changed', 3: 'player_unavailable',
                  4: 'owner_changed', 5: 'unconfirmed'}


def _append(cache, kind, targets):
    entries = cache.setdefault(HISTORY_KEY, [])
    entries.append(dict(id=uuid4().hex, kind=kind, time=int(time() * 1000), targets=targets))
    del entries[:-HISTORY_LIMIT]


def record_owners(cache, snapshots, moves, receipts, originals):
    changes = {move[1]: (move, receipt['b']) for move, receipt in zip(moves, receipts, strict=True)}
    targets = []
    for row in snapshots:
        if row['b'] != 1:
            targets.append(dict(unit=format_rawcode(row['rawcode']), status='unit_changed', keys=()))
            continue
        identity = row['created']
        if identity not in changes:
            continue
        move, status = changes[identity]
        unit, _, before, rawcode, destination, after, _ = move
        targets.append(dict(unit=format_rawcode(rawcode), source=row['a'], destination=destination,
            status='pending' if status == 1 else _OWNER_RESULTS[status],
            keys=(('owner', identity),), original=originals[identity],
            move=(unit, identity, after, rawcode, row['a'], before, 0)))
        if status == 5:
            invalidate_owners(cache, {identity})
    _append(cache, 'owner', targets)


def _invalidate(cache, affected):
    for entry in cache.get(HISTORY_KEY, ()):
        for target in entry['targets']:
            if target['status'] == 'pending' and affected(target['keys']):
                target['status'] = 'superseded'


def invalidate_owners(cache, identities):
    _invalidate(cache, lambda keys: any(key[0] == 'owner' and key[1] in identities for key in keys))


def invalidate_teams(cache, players):
    _invalidate(cache, lambda keys: any(key[0] != 'owner' and players.intersection(key[1:]) for key in keys))


def record_team(cache, before, after, source, destination):
    rows = after.get('rows')
    matrix = after.get('matrix', ())
    if not rows or len(matrix) != 560:
        return
    row = before['rows'][0]
    player, owner = row['a'], row['owner']
    present = row.get('c', ALL_TEAM_SLOTS)
    if rows[0]['a'] != player or rows[0]['owner'] != owner or rows[0].get('c', present) != present:
        return
    changes = {i: (old, new) for i, (old, new) in enumerate(zip(before['matrix'], matrix, strict=True))
               if old != new and i % 10 not in (6, 7) and i // 20 != player and present & (1 << (i // 20))}
    if not changes and source == destination:
        return
    peers = {i // 20 for i in changes}
    pairs = tuple(('pair', min(player, peer), max(player, peer)) for peer in sorted(peers))
    _append(cache, 'team', [dict(player=player, owner=owner, source=source, destination=destination,
        status='pending', keys=(('template', player), *pairs), changes=changes)])


def snapshot(cache):
    later = set()
    results = []
    for entry in reversed(cache.get(HISTORY_KEY, ())):
        targets = []
        for target in entry['targets']:
            row = {key: target[key] for key in ('unit', 'player', 'source', 'destination', 'status') if key in target}
            if target['status'] == 'pending' and later.intersection(target['keys']):
                row['status'] = 'newer'
            targets.append(row)
        results.append(dict(id=entry['id'], kind=entry['kind'], time=entry['time'], targets=targets))
        later.update(key for target in entry['targets'] if target['status'] == 'pending' for key in target['keys'])
    return results


def _keep_uncertain_owner(cache, target):
    _, identity, expected, _, _, destination, _ = target['move']
    originals = cache.setdefault('fullclone_original_owners', {})
    prior = originals.get(identity) or target['original']
    if prior is not None:
        originals[identity] = dict(prior, last_owner=expected, prior_owner=destination)
    invalidate_owners(cache, {identity})


def _undo_owners(engine, targets, epoch):
    from war3_services.fullclone import write_owner_moves

    try:
        rows = write_owner_moves(engine, [target['move'] for target in targets], epoch, restore=True)
    except Exception:
        for target in targets:
            target['status'] = 'unconfirmed'
            if engine.session.epoch == epoch:
                _keep_uncertain_owner(engine.session.cache, target)
        raise
    originals = engine.session.cache.get('fullclone_original_owners', {})
    for target, row in zip(targets, rows, strict=True):
        target['status'] = 'undone' if row['b'] == 1 else _OWNER_RESULTS[row['b']]
        if row['b'] == 1:
            identity = row['created']
            previous = target['original']
            if previous is None:
                originals.pop(identity, None)
            else:
                originals[identity] = previous.copy()
        elif row['b'] == 5:
            _keep_uncertain_owner(engine.session.cache, target)


def _undo_team(engine, target, epoch):
    player, owner = target['player'], target['owner']
    records = engine.session.cache.get('fullclone_teams', {})
    original = records.get(owner)
    if original is None or original['applied'] != target['destination']:
        target['status'] = 'relations_changed'
        return
    try:
        result = engine.fullclone(19, target=player, expected_epoch=epoch)
    except Exception as exc:
        if not isinstance(exc, DiplomacySlotUnavailable) and not isinstance(exc.__cause__, DiplomacySlotUnavailable):
            raise
        target['status'] = 'player_unavailable'
        return
    row = result['rows'][0] if result['rows'] else {}
    present = row.get('c', 0)
    matrix = list(result['matrix'])
    if (row.get('a') != player or row.get('owner') != owner or len(matrix) != 560 or
            any(not present & (1 << (i // 20)) or matrix[i] != after
                for i, (_, after) in target['changes'].items())):
        target['status'] = 'relations_changed'
        return
    for i, (before, _) in target['changes'].items():
        matrix[i] = before
    if target['changes']:
        try:
            result = engine.fullclone(20, target=player, expected_epoch=epoch, matrix=matrix,
                                      expected_owner=owner, rawcode=present)
            receipt = result['rows'][0] if result['rows'] else {}
            if (not result['changed'] or engine.session.epoch != epoch or len(result['matrix']) != 560 or
                    receipt.get('a') != player or receipt.get('owner') != owner or receipt.get('c') != present or
                    any(result['matrix'][i] != before for i, (before, _) in target['changes'].items())):
                raise ValueError('外交撤销回执无法确认，请重新读取当前外交状态')
        except Exception:
            target['status'] = 'unconfirmed'
            if engine.session.epoch == epoch:
                invalidate_teams(engine.session.cache, {player})
            raise
    original['applied'] = target['source']
    target['status'] = 'undone'


def undo(engine, operation_id):
    if type(operation_id) is not str or len(operation_id) != 32:
        raise ValueError('操作记录无效')
    cache = engine.session.cache
    entries = cache.get(HISTORY_KEY, [])
    entry = next((row for row in entries if row['id'] == operation_id), None)
    if entry is None:
        raise ValueError('该操作记录已过期，请读取当前地图的操作历史')
    visible = next(row for row in snapshot(cache) if row['id'] == operation_id)
    targets = [target for target, status in zip(entry['targets'], visible['targets'], strict=True)
               if status['status'] == 'pending']
    if not targets:
        return dict(undone=0, entries=snapshot(cache))
    epoch = engine.session.epoch
    if entry['kind'] == 'owner':
        _undo_owners(engine, targets, epoch)
    else:
        _undo_team(engine, targets[0], epoch)
    undone = sum(target['status'] == 'undone' for target in targets)
    result = dict(undone=undone, kind=entry['kind'], entries=snapshot(cache))
    if undone and entry['kind'] == 'team':
        identity = engine.session.identity
        target = targets[0]
        result['team'] = dict(player=target['player'], template=target['source'],
                              context=f'{identity.pid}:{identity.created}:{epoch}')
    return result
