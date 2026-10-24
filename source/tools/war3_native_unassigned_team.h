#ifndef WAR3_NATIVE_UNASSIGNED_TEAM_H
#define WAR3_NATIVE_UNASSIGNED_TEAM_H

/* R19.3: explicit -1 tag; never alias it to the valid six-bit team 63. */
#define WAR3_UNASSIGNED_TEAM_TAG (1ULL << 36u)

static uint64_t war3_team_pack_unassigned_peer(const War3TeamPeerSnapshot *source) {
    War3TeamPeerSnapshot value = *source;
    if (value.team < -1 || value.team >= 64) return 0;
    if (value.team == -1) {
        value.team = 0;
        return war3_team_pack(&value) | WAR3_UNASSIGNED_TEAM_TAG;
    }
    return war3_team_pack(&value);
}

static int war3_team_unpack_unassigned_peer(uint64_t packed, War3TeamPeerSnapshot *value) {
    int unassigned = !!(packed & WAR3_UNASSIGNED_TEAM_TAG);
    if ((packed >> 37u) || (unassigned && ((packed >> 12u) & 0x3fu))) return 0;
    if (!war3_team_unpack(packed & ~WAR3_UNASSIGNED_TEAM_TAG, value)) return 0;
    if (unassigned) value->team = -1;
    return 1;
}

static DWORD war3_validate_unit_identity(const NativeCommand *, const NativeOp *);
static int war3_repair_alliance_mask(uint64_t, uint64_t, int32_t, uint32_t);

/* R19.3: only diplomacy changes here; there is deliberately no team setter. */
static DWORD war3_ext_unassigned_team(
    NativeCommand *cmd, NativeOp *op, uint32_t index,
    const uint64_t *input, uint32_t input_count,
    uint64_t **output, uint32_t *output_count
) {
    JassGetOwningPlayerFn get_owner = (JassGetOwningPlayerFn)(uintptr_t)war3_persistent_native_handler("GetOwningPlayer");
    JassGetPlayerTeamFn get_team = (JassGetPlayerTeamFn)(uintptr_t)war3_persistent_native_handler("GetPlayerTeam");
    JassGetPlayerIdFn get_id = (JassGetPlayerIdFn)(uintptr_t)war3_persistent_native_handler("GetPlayerId");
    JassPlayerFn player = (JassPlayerFn)(uintptr_t)war3_persistent_native_handler("Player");
    JassGetPlayerSlotStateFn get_slot = (JassGetPlayerSlotStateFn)(uintptr_t)war3_persistent_native_handler("GetPlayerSlotState");
    JassConvertPlayerSlotStateFn slot = (JassConvertPlayerSlotStateFn)(uintptr_t)war3_persistent_native_handler("ConvertPlayerSlotState");
    JassSetPlayerAllianceFn set = (JassSetPlayerAllianceFn)(uintptr_t)war3_persistent_native_handler("SetPlayerAlliance");
    JassGetPlayerAllianceFn get = (JassGetPlayerAllianceFn)(uintptr_t)war3_persistent_native_handler("GetPlayerAlliance");
    War3TeamPeerSnapshot peers[28];
    int restoring = op->kind == WAR3_NATIVE_OP_EXT_RESTORE_SELECTED_OWNER_TEAM;
    uint64_t owner = restoring ? op->arg1 : op->handler, reference = 0, playing;
    uint64_t *allocated = NULL;
    uint32_t target = restoring ? (uint32_t)op->handler : op->rawcode;
    uint32_t owner_id = (uint32_t)op->arg0, count = 0, touched = 0, seen = 0, allied = 0;
    DWORD error = ERROR_SUCCESS, rollback_error = ERROR_SUCCESS, phase = 1;
    op->result = (0x554e4153ULL << 32u) | phase; op->reserved = 0;
    if (index != 1u || cmd->op_count != 2u || cmd->ops[0].kind != WAR3_NATIVE_OP_VALIDATE_UNIT_IDENTITY ||
        !owner || op->arg0 >= 24u || target >= 14u || input_count > 28u ||
        (!restoring && (op->kind != WAR3_NATIVE_OP_EXT_SET_SELECTED_OWNER_TEAM || op->arg1 > 1u || input_count)) ||
        (restoring && (op->rawcode != UINT32_MAX || !input_count || !input || op->handler >= 14u)))
        return ERROR_INVALID_DATA;
    if (!get_owner || !get_team || !get_id || !player || !get_slot || !slot || !set || !get)
        return ERROR_PROC_NOT_FOUND;
    ZeroMemory(peers, sizeof(peers));
    __try {
        error = war3_validate_unit_identity(cmd, &cmd->ops[0]);
        if (error) return error;
        if (get_owner(cmd->unit_handle) != owner || get_id(owner) != (int32_t)owner_id ||
            player((int32_t)owner_id) != owner || get_team(owner) != -1) return ERROR_RETRY;
        if (restoring) {
            count = input_count;
            for (uint32_t n = 0; n < count; ++n) {
                War3TeamPeerSnapshot *p = &peers[n];
                if (!war3_team_unpack_unassigned_peer(input[n], p) || p->player_index == owner_id ||
                    (p->player_index >= 24u && p->player_index != 24u && p->player_index != 27u) ||
                    (seen & (1u << p->player_index))) return ERROR_INVALID_DATA;
                seen |= 1u << p->player_index;
                p->player = player((int32_t)p->player_index);
                if (!p->player || get_id(p->player) != (int32_t)p->player_index) return ERROR_RETRY;
                p->current_owner_to_peer_mask = war3_team_read_mask(get, owner, p->player);
                p->current_peer_to_owner_mask = war3_team_read_mask(get, p->player, owner);
                if (p->current_owner_to_peer_mask != p->assigned_owner_to_peer_mask ||
                    p->current_peer_to_owner_mask != p->assigned_peer_to_owner_mask) return ERROR_RETRY;
            }
        } else {
            playing = slot(1);
            if (!playing) return ERROR_INVALID_DATA;
            if (target == 12u || target == 13u) reference = player(target == 12u ? 24 : 27);
            else for (uint32_t n = 0; n < 24u; ++n) {
                uint64_t p = player((int32_t)n);
                if (p && n != owner_id && get_slot(p) == playing && get_team(p) == (int32_t)target) {
                    reference = p; break;
                }
            }
            if (target >= 12u && !reference) return ERROR_NOT_FOUND;
            for (uint32_t n = 0; n < 28u; ++n) {
                uint64_t p;
                War3TeamPeerSnapshot *entry;
                int special = n == 24u || n == 27u;
                if (n == owner_id || (n >= 24u && !special)) continue;
                p = player((int32_t)n);
                if (!p || (!special && get_slot(p) != playing)) continue;
                entry = &peers[count]; entry->player_index = n; entry->player = p;
                entry->team = get_team(p);
                if (entry->team < -1 || entry->team >= 64 || get_id(p) != (int32_t)n) return ERROR_INVALID_DATA;
                entry->owner_to_peer_mask = entry->current_owner_to_peer_mask = war3_team_read_mask(get, owner, p);
                entry->peer_to_owner_mask = entry->current_peer_to_owner_mask = war3_team_read_mask(get, p, owner);
                if (reference) {
                    entry->assigned_owner_to_peer_mask = war3_team_read_mask(get, reference, p);
                    entry->assigned_peer_to_owner_mask = war3_team_read_mask(get, p, reference);
                } else {
                    entry->assigned_owner_to_peer_mask = entry->assigned_peer_to_owner_mask =
                        n < 24u && entry->team == (int32_t)target ? 0x3fu : 0u;
                }
                ++count;
            }
            if (!count) return ERROR_NOT_FOUND;
            allocated = (uint64_t *)HeapAlloc(GetProcessHeap(), 0, count * sizeof(uint64_t));
            if (!allocated) return ERROR_OUTOFMEMORY;
            for (uint32_t n = 0; n < count; ++n) allocated[n] = war3_team_pack_unassigned_peer(&peers[n]);
        }
        phase = 2;
        for (uint32_t n = 0; n < count; ++n) {
            War3TeamPeerSnapshot *p = &peers[n];
            uint32_t forward = restoring ? p->owner_to_peer_mask : p->assigned_owner_to_peer_mask;
            uint32_t reverse = restoring ? p->peer_to_owner_mask : p->assigned_peer_to_owner_mask;
            error = war3_validate_unit_identity(cmd, &cmd->ops[0]);
            if (error) break;
            if (get_owner(cmd->unit_handle) != owner || get_id(owner) != (int32_t)owner_id ||
                get_team(owner) != -1) { error = ERROR_RETRY; break; }
            touched = n + 1u; /* setters can fail halfway through a pair */
            war3_team_write_mask(set, owner, p->player, forward);
            war3_team_write_mask(set, p->player, owner, reverse);
            /* Same guarded neutral compatibility as the existing team path. */
            if ((p->player_index == 24u || p->player_index == 27u) &&
                (war3_team_read_mask(get, owner, p->player) != forward ||
                 war3_team_read_mask(get, p->player, owner) != reverse)) {
                war3_repair_alliance_mask((uint64_t)(uintptr_t)get, owner, (int32_t)p->player_index, forward);
                war3_repair_alliance_mask((uint64_t)(uintptr_t)get, p->player, (int32_t)owner_id, reverse);
            }
            if (war3_team_read_mask(get, owner, p->player) != forward ||
                war3_team_read_mask(get, p->player, owner) != reverse) { error = ERROR_WRITE_FAULT; break; }
            if (forward) ++allied;
        }
        if (!error) {
            phase = 3;
            error = war3_validate_unit_identity(cmd, &cmd->ops[0]);
            if (!error && (get_owner(cmd->unit_handle) != owner || get_id(owner) != (int32_t)owner_id ||
                get_team(owner) != -1)) error = ERROR_RETRY;
            for (uint32_t n = 0; !error && n < count; ++n) {
                War3TeamPeerSnapshot *p = &peers[n];
                if (war3_team_read_mask(get, owner, p->player) != (restoring ? p->owner_to_peer_mask : p->assigned_owner_to_peer_mask) ||
                    war3_team_read_mask(get, p->player, owner) != (restoring ? p->peer_to_owner_mask : p->assigned_peer_to_owner_mask))
                    error = ERROR_WRITE_FAULT;
            }
        }
    } __except (EXCEPTION_EXECUTE_HANDLER) { error = GetExceptionCode(); }
    if (error) {
        for (uint32_t n = touched; n-- > 0u;) {
            War3TeamPeerSnapshot *p = &peers[n];
            __try {
                war3_team_write_mask(set, owner, p->player, p->current_owner_to_peer_mask);
                war3_team_write_mask(set, p->player, owner, p->current_peer_to_owner_mask);
            } __except (EXCEPTION_EXECUTE_HANDLER) { rollback_error = GetExceptionCode(); }
            __try {
                if ((p->player_index == 24u || p->player_index == 27u) &&
                    (war3_team_read_mask(get, owner, p->player) != p->current_owner_to_peer_mask ||
                     war3_team_read_mask(get, p->player, owner) != p->current_peer_to_owner_mask)) {
                    war3_repair_alliance_mask((uint64_t)(uintptr_t)get, owner,
                        (int32_t)p->player_index, p->current_owner_to_peer_mask);
                    war3_repair_alliance_mask((uint64_t)(uintptr_t)get, p->player,
                        (int32_t)owner_id, p->current_peer_to_owner_mask);
                }
            } __except (EXCEPTION_EXECUTE_HANDLER) { rollback_error = GetExceptionCode(); }
        }
        /* Final readback, not a transient setter failure, decides recovery. */
        rollback_error = ERROR_SUCCESS;
        for (uint32_t n = 0; n < touched; ++n) {
            __try {
                if (war3_team_read_mask(get, owner, peers[n].player) != peers[n].current_owner_to_peer_mask ||
                    war3_team_read_mask(get, peers[n].player, owner) != peers[n].current_peer_to_owner_mask)
                    rollback_error = ERROR_WRITE_FAULT;
            } __except (EXCEPTION_EXECUTE_HANDLER) { rollback_error = GetExceptionCode(); }
        }
        if (allocated) HeapFree(GetProcessHeap(), 0, allocated);
        op->result = (0x554e4153ULL << 32u) | (rollback_error ? 4u : phase);
        op->reserved = rollback_error;
        return error;
    }
    op->result = restoring ? UINT32_MAX : target;
    op->arg0 = owner;
    op->arg1 = (restoring ? target : 0xffu) | ((uint64_t)owner_id << 8u) |
        ((uint64_t)count << 16u) | ((uint64_t)allied << 24u) | (1ULL << 32u);
    *output = allocated; *output_count = restoring ? 0u : count;
    return ERROR_SUCCESS;
}

/* Pure readback for status 317; keeps name payload and restore records separate. */
static DWORD war3_query_unassigned_team_peers(
    NativeCommand *cmd, NativeOp *op, uint32_t index, uint64_t **output, uint32_t *output_count
) {
    JassGetOwningPlayerFn get_owner = (JassGetOwningPlayerFn)(uintptr_t)war3_persistent_native_handler("GetOwningPlayer");
    JassGetPlayerTeamFn get_team = (JassGetPlayerTeamFn)(uintptr_t)war3_persistent_native_handler("GetPlayerTeam");
    JassGetPlayerIdFn get_id = (JassGetPlayerIdFn)(uintptr_t)war3_persistent_native_handler("GetPlayerId");
    JassPlayerFn player = (JassPlayerFn)(uintptr_t)war3_persistent_native_handler("Player");
    JassGetPlayerSlotStateFn get_slot = (JassGetPlayerSlotStateFn)(uintptr_t)war3_persistent_native_handler("GetPlayerSlotState");
    JassConvertPlayerSlotStateFn slot = (JassConvertPlayerSlotStateFn)(uintptr_t)war3_persistent_native_handler("ConvertPlayerSlotState");
    JassGetPlayerAllianceFn get = (JassGetPlayerAllianceFn)(uintptr_t)war3_persistent_native_handler("GetPlayerAlliance");
    War3TeamPeerSnapshot peers[28];
    uint32_t count = 0;
    uint64_t owner, playing;
    int32_t owner_id;
    DWORD error;
    if (index != 1u || cmd->op_count != 2u || cmd->ops[0].kind != 136u ||
        op->kind != 317u || op->rawcode || op->handler || op->arg0 || op->arg1 || cmd->reserved)
        return ERROR_INVALID_DATA;
    if (!get_owner || !get_team || !get_id || !player || !get_slot || !slot || !get)
        return ERROR_PROC_NOT_FOUND;
    ZeroMemory(peers, sizeof(peers));
    __try {
        error = war3_validate_unit_identity(cmd, &cmd->ops[0]);
        if (error) return error;
        owner = get_owner(cmd->unit_handle); owner_id = get_id(owner);
        if (!owner || owner_id < 0 || owner_id >= 24 || get_team(owner) != -1) return ERROR_RETRY;
        playing = slot(1);
        if (!playing) return ERROR_INVALID_DATA;
        for (uint32_t n = 0; n < 28u; ++n) {
            uint64_t p;
            War3TeamPeerSnapshot *entry;
            int special = n == 24u || n == 27u;
            if (n == (uint32_t)owner_id || (n >= 24u && !special)) continue;
            p = player((int32_t)n);
            if (!p || (!special && get_slot(p) != playing)) continue;
            entry = &peers[count]; entry->player = p; entry->player_index = n; entry->team = get_team(p);
            if (entry->team < -1 || entry->team >= 64 || get_id(p) != (int32_t)n) return ERROR_INVALID_DATA;
            entry->owner_to_peer_mask = war3_team_read_mask(get, owner, p);
            entry->peer_to_owner_mask = war3_team_read_mask(get, p, owner);
            ++count;
        }
        error = war3_validate_unit_identity(cmd, &cmd->ops[0]);
        if (error) return error;
        if (get_owner(cmd->unit_handle) != owner || get_id(owner) != owner_id || get_team(owner) != -1)
            return ERROR_RETRY;
    } __except (EXCEPTION_EXECUTE_HANDLER) { return GetExceptionCode(); }
    *output = count ? (uint64_t *)HeapAlloc(GetProcessHeap(), 0, count * sizeof(uint64_t)) : NULL;
    if (count && !*output) return ERROR_OUTOFMEMORY;
    for (uint32_t n = 0; n < count; ++n) (*output)[n] = war3_team_pack_unassigned_peer(&peers[n]);
    *output_count = count; op->result = UINT32_MAX; op->arg0 = owner;
    op->arg1 = (uint32_t)owner_id | ((uint64_t)count << 8u);
    return ERROR_SUCCESS;
}
#endif
