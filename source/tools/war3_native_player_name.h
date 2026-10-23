/* R19 read-only names. See analysis/R19_PLAYER_NAME_ABI.md for code evidence.
   Do not call GetPlayerName's JASS string interner or its lazy-writing getter. */
#define WAR3_PLAYER_NAME_MAX_BYTES 512u
typedef uint64_t (__fastcall *War3PlayerNameResolveFn)(uint64_t);
static HMODULE g_player_name_module = NULL;
static uint64_t g_player_name_resolver = 0;

static DWORD war3_bind_player_name_reader(uint64_t *resolver_out) {
    static const uint8_t accessor[15] = {
        0x48,0x8b,0x41,0x10,0x48,0x85,0xc0,0x74,0x05,0x48,0x8b,0x40,0x38,0xc3,0xc3
    };
    uint8_t *image, *table;
    uint64_t name, id, resolver, getter, string_reader;
    int index;
    DWORD error;
    HMODULE module = GetModuleHandleW(NULL);
    if (!resolver_out || !module) return ERROR_INVALID_PARAMETER;
    if (g_player_name_module == module && war3_executable_pointer(g_player_name_resolver)) {
        *resolver_out = g_player_name_resolver;
        return ERROR_SUCCESS;
    }
    /* Optional lookup: a missing name interface must not break bootstrap or 316. */
    error = war3_bootstrap_context(&image, &table);
    if (error) return error;
    index = war3_bootstrap_index("GetPlayerName");
    if (index < 0) return ERROR_PROC_NOT_FOUND;
    error = war3_bootstrap_query(image, table, (uint32_t)index, &name);
    if (error) return error;
    id = war3_persistent_native_handler("GetPlayerId");
    if (!id || !war3_readable_span(name, 64) || !war3_readable_span(id, 64))
        return ERROR_PROC_NOT_FOUND;
    __try {
        if (*(uint8_t *)(uintptr_t)(name+4) != 0xe8 ||
            *(uint8_t *)(uintptr_t)(name+0x18) != 0xe8 ||
            *(uint8_t *)(uintptr_t)(id+4) != 0xe8) return ERROR_INVALID_DATA;
        resolver = name+9+(int64_t)*(int32_t *)(uintptr_t)(name+5);
        getter = name+0x1d+(int64_t)*(int32_t *)(uintptr_t)(name+0x19);
        if (resolver != id+9+(int64_t)*(int32_t *)(uintptr_t)(id+5) ||
            !war3_executable_pointer(resolver) || !war3_executable_pointer(getter) ||
            !war3_readable_span(getter, 64) ||
            war3_bootstrap_hash((uint8_t *)(uintptr_t)getter,64) != 0xb1a49ce378624016ULL ||
            *(uint8_t *)(uintptr_t)(getter+0x28) != 0xe8) return ERROR_INVALID_DATA;
        string_reader = getter+0x2d+(int64_t)*(int32_t *)(uintptr_t)(getter+0x29);
        if (!war3_executable_pointer(string_reader) ||
            !war3_readable_span(string_reader,sizeof(accessor)) ||
            memcmp((void *)(uintptr_t)string_reader,accessor,sizeof(accessor))) return ERROR_INVALID_DATA;
    } __except (EXCEPTION_EXECUTE_HANDLER) { return GetExceptionCode(); }
    g_player_name_module = module;
    g_player_name_resolver = resolver;
    *resolver_out = resolver;
    return ERROR_SUCCESS;
}

static DWORD war3_read_bound_player_name(
    const NativeCommand *cmd, uint64_t owner_handle,
    unsigned char *output, uint32_t capacity, uint32_t *byte_length
) {
    JassGetOwningPlayerFn get_owner = (JassGetOwningPlayerFn)(uintptr_t)
        war3_persistent_native_handler("GetOwningPlayer");
    uint64_t resolver, player, storage, bytes;
    uint32_t length = 0;
    DWORD error;
    if (byte_length) *byte_length = 0;
    if (!cmd || !owner_handle || !output || !byte_length ||
        !capacity || capacity > WAR3_PLAYER_NAME_MAX_BYTES) return ERROR_INVALID_PARAMETER;
    if (!get_owner) return ERROR_PROC_NOT_FOUND;
    error = war3_validate_unit_identity(cmd,&cmd->ops[0]);
    if (error) return error;
    error = war3_bind_player_name_reader(&resolver);
    if (error) return error;
    __try {
        if (get_owner(cmd->unit_handle) != owner_handle) return ERROR_INVALID_HANDLE;
        player = ((War3PlayerNameResolveFn)(uintptr_t)resolver)(owner_handle);
        if (!war3_readable_span(player,0x88)) return ERROR_INVALID_ADDRESS;
        storage = *(uint64_t *)(uintptr_t)(player+0x80);
        if (!storage) return ERROR_NOT_FOUND;
        if (!war3_readable_span(storage,0x40)) return ERROR_INVALID_ADDRESS;
        bytes = *(uint64_t *)(uintptr_t)(storage+0x38);
        if (!bytes) return ERROR_NOT_FOUND;
        for (;;) {
            uint8_t byte;
            if (!war3_readable_span(bytes+length,1)) return ERROR_INVALID_ADDRESS;
            byte = *(uint8_t *)(uintptr_t)(bytes+length);
            if (!byte) break;
            if (length == capacity) return ERROR_INSUFFICIENT_BUFFER;
            output[length++] = byte;
        }
        if (!length) return ERROR_NOT_FOUND;
        if (!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,(const char *)output,(int)length,NULL,0))
            return ERROR_NO_UNICODE_TRANSLATION;
        /* No stale pointer or name may escape a changed owner/object context. */
        if (((War3PlayerNameResolveFn)(uintptr_t)resolver)(owner_handle) != player ||
            get_owner(cmd->unit_handle) != owner_handle ||
            *(uint64_t *)(uintptr_t)(player+0x80) != storage ||
            *(uint64_t *)(uintptr_t)(storage+0x38) != bytes) return ERROR_INVALID_HANDLE;
        error = war3_validate_unit_identity(cmd,&cmd->ops[0]);
        if (error) return error;
        *byte_length = length;
    } __except (EXCEPTION_EXECUTE_HANDLER) { return GetExceptionCode(); }
    return ERROR_SUCCESS;
}

static DWORD war3_ext_query_selected_owner_status(
    NativeCommand *cmd, NativeOp *op, uint32_t index,
    uint64_t **output_extra, uint32_t *output_count
) {
    unsigned char name[WAR3_PLAYER_NAME_MAX_BYTES] = {0};
    uint32_t length = 0, name_words, peer_count;
    uint64_t *combined;
    JassGetOwningPlayerFn get_owner;
    JassGetPlayerIdFn get_id;
    JassGetPlayerTeamFn get_team;
    DWORD error, name_error;
    /* This preserves every legacy validation and the exact 316 snapshot. */
    error = war3_ext_query_selected_owner_team(cmd,op,index,output_extra,output_count);
    if (error) return error;
    peer_count = *output_count;
    name_error = war3_read_bound_player_name(cmd,op->arg0,name,sizeof(name),&length);
    get_owner = (JassGetOwningPlayerFn)(uintptr_t)war3_persistent_native_handler("GetOwningPlayer");
    get_id = (JassGetPlayerIdFn)(uintptr_t)war3_persistent_native_handler("GetPlayerId");
    get_team = (JassGetPlayerTeamFn)(uintptr_t)war3_persistent_native_handler("GetPlayerTeam");
    error = war3_validate_unit_identity(cmd,&cmd->ops[0]);
    if (error) return error;
    __try {
        if (get_owner(cmd->unit_handle) != op->arg0 || get_id(op->arg0) != (int32_t)(op->arg1&0xffu) ||
            get_team(op->arg0) != (int32_t)op->result) return ERROR_INVALID_HANDLE;
    } __except (EXCEPTION_EXECUTE_HANDLER) { return GetExceptionCode(); }
    if (name_error) length = 0;
    name_words = (length+7u)/8u;
    combined = (uint64_t *)HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,
                                    (peer_count+2u+name_words)*sizeof(uint64_t));
    if (!combined) return ERROR_OUTOFMEMORY;
    if (peer_count) memcpy(combined,*output_extra,peer_count*sizeof(uint64_t));
    combined[peer_count] = name_error;
    combined[peer_count+1] = length;
    if (length) memcpy(combined+peer_count+2,name,length);
    if (*output_extra) HeapFree(GetProcessHeap(),0,*output_extra);
    *output_extra = combined;
    *output_count = peer_count+2u+name_words;
    return ERROR_SUCCESS;
}
