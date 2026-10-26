/* R24: read-only source policy; no quest setter or trigger execution. */
#include "war3_quest_policy.h"
static inline DWORD war3_quest_process_created(uint64_t *created) {
    FILETIME c,e,k,u;
    if(!GetProcessTimes(GetCurrentProcess(),&c,&e,&k,&u))return GetLastError();
    *created=((uint64_t)c.dwHighDateTime<<32)|c.dwLowDateTime;return ERROR_SUCCESS;
}

static DWORD war3_quest_source_policy_query(NativeCommand *cmd,NativeOp *op,uint64_t **extra,uint32_t *count) {
    if(cmd->unit_handle || cmd->reserved || cmd->op_count!=1 || op->rawcode || op->handler || op->arg0 || op->arg1)
        return ERROR_INVALID_PARAMETER;
    uint64_t created=0;DWORD error=war3_quest_process_created(&created);if(error)return error;
    uint64_t *words=(uint64_t *)HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,6u*8u);
    if(!words)return ERROR_OUTOFMEMORY;
    words[0]=0x31505352u;words[1]=1;words[2]=GetCurrentProcessId();words[3]=created;
    words[4]=war3_quest_no_local_override(created);*extra=words;*count=6;return ERROR_SUCCESS;
}
