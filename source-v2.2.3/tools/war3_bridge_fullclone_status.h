/* Read-only scalar quest globals. No quest setters/trigger entrypoints. */
typedef struct FCQuestStatusRow {uint64_t node,handle;uint32_t completed,failed,discovered,error;} FCQuestStatusRow;
typedef struct FCQuestStatusWork {
    uint8_t (*completed_fn)(uint64_t),(*failed_fn)(uint64_t),(*discovered_fn)(uint64_t);
    void *tls;uint64_t vm,symbols,host;
    uint32_t count,error,completed,reserved[3];FCQuestStatusRow rows[];
} FCQuestStatusWork;
_Static_assert(sizeof(FCQuestStatusWork)==80,"FCQuestStatusWork ABI");
__declspec(dllexport) const uint32_t fullclone_status_abi[3]={0x46333103,216,0};
__declspec(dllexport) uint64_t BridgeFullCloneStatusQuery(void){
    FCQuestStatusWork*w=(FCQuestStatusWork*)g_dispatch->work;
    if(!w || w->tls!=g_dispatch->tls_value || !w->count || w->count>128 || !w->completed_fn || !w->failed_fn || !w->discovered_fn){if(w)w->error=1200;return 0;}
    __try{
        if(*(uint64_t*)(uintptr_t)(w->vm+0x4878)!=w->symbols || *(uint64_t*)(uintptr_t)(w->vm+0x4868)!=w->host){w->error=1237;return 0;}
        for(uint32_t i=0;i<w->count;i++){
            FCQuestStatusRow*r=&w->rows[i];uint64_t n=r->node;
            if(*(uint32_t*)(uintptr_t)(n+0x30)!=7 || *(uint32_t*)(uintptr_t)(n+0x34)!=7 || *(uint64_t*)(uintptr_t)(n+0x38)!=r->handle){r->error=1237;continue;}
            r->completed=w->completed_fn(r->handle);r->failed=w->failed_fn(r->handle);r->discovered=w->discovered_fn(r->handle);
            if(*(uint64_t*)(uintptr_t)(n+0x38)!=r->handle || (r->completed && r->failed))r->error=1237;
        }
        w->completed=1;return w->count;
    }__except(EXCEPTION_EXECUTE_HANDLER){w->error=GetExceptionCode();return 0;}
}
