/* R23 exact-build adapter. Included after bootstrap/catalog definitions.
   Source/script qualification stays in the Python client; every mutable game
   identity is independently rebound here in the serialized game thread. */
#include "war3_quest_wire.h"
#include "war3_quest_binding.h"
#include "war3_quest_dispatch.h"
#include "war3_quest_policy.h"

typedef uint64_t (__fastcall *War3QuestResolveFn)(uint32_t);
typedef void (__fastcall *War3QuestExecuteFn)(uint32_t);

/* Live validation found that the host and game can see different values for
   the same logical HKCU path. Return a read-only target-process policy proof. */
static DWORD war3_quest_source_policy_query(NativeCommand *cmd,NativeOp *op,uint64_t **extra,uint32_t *count) {
    if(cmd->unit_handle || cmd->reserved || cmd->op_count!=1 || op->rawcode || op->handler || op->arg0 || op->arg1)
        return ERROR_INVALID_PARAMETER;
    uint64_t created=0;DWORD error=war3_quest_process_created(&created);if(error)return error;
    uint64_t *words=(uint64_t *)HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,6u*8u);
    if(!words)return ERROR_OUTOFMEMORY;
    words[0]=0x31505352u;words[1]=1;words[2]=GetCurrentProcessId();words[3]=created;
    words[4]=war3_quest_no_local_override(created);*extra=words;*count=6;return ERROR_SUCCESS;
}

static DWORD war3_quest_profile(uint8_t *image,uint64_t *execute) {
    DWORD error;
    {
        static const War3BootstrapCodeCheck checks[]={
            {0xa0f100u,612u,0x787dc7783def1d00ULL},
            {0xa10e40u,612u,0x7deedd5c88fa98cbULL},
            {0xd31e30u,320u,0x208c785e7e3d1e07ULL},
            {0xd33240u,207u,0x535b3cfed5d053d4ULL},
            {0xd33310u,207u,0x76e72fb4e5eac671ULL},
            {0xc50003u,62u,0xa13bc516c90ae996ULL},
            {0x9dde50u,39u,0x9afa250dca103fd3ULL},
        };
        for(unsigned n=0;n<sizeof(checks)/sizeof(checks[0]);++n)
            if(!war3_readable_span((uintptr_t)(image+checks[n].rva),checks[n].size) ||
               war3_bootstrap_hash(image+checks[n].rva,checks[n].size)!=checks[n].hash)
                return ERROR_REVISION_MISMATCH;
    }
    uint8_t *current_image,*table;
    error=war3_bootstrap_context(&current_image,&table);if(error)return error;
    if(current_image!=image)return ERROR_RETRY;
    uint64_t predicate=0;
    int qi=war3_bootstrap_index("IsQuestCompleted"),ti=war3_bootstrap_index("TriggerExecute");
    if(qi<0 || ti<0)return ERROR_PROC_NOT_FOUND;
    if((error=war3_bootstrap_query(image,table,(uint32_t)qi,&predicate)) ||
       (error=war3_bootstrap_query(image,table,(uint32_t)ti,execute)))return error;
    if(*(uint8_t *)(uintptr_t)(predicate+4)!=0xe8 ||
       predicate+9+(int64_t)*(int32_t *)(uintptr_t)(predicate+5)!=(uintptr_t)image+0xa0f100u ||
       *(uint8_t *)(uintptr_t)(*execute+4)!=0xe8 ||
       *execute+9+(int64_t)*(int32_t *)(uintptr_t)(*execute+5)!=(uintptr_t)image+0xa10e40u)
        return ERROR_REVISION_MISMATCH;
    return ERROR_SUCCESS;
}

static DWORD war3_quest_source(const uint64_t *h,uint32_t *message) {
    uint64_t created=0;DWORD error=war3_quest_process_created(&created);
    if(error)return error;
    if(created!=h[9])return ERROR_RETRY;
    if((error=war3_quest_no_local_override(created))) {*message=15;return error;}
    HANDLE file=(HANDLE)(uintptr_t)h[4];BY_HANDLE_FILE_INFORMATION info;
    if(GetFileType(file)!=FILE_TYPE_DISK || !GetFileInformationByHandle(file,&info))return ERROR_INVALID_HANDLE;
    uint64_t index=((uint64_t)info.nFileIndexHigh<<32)|info.nFileIndexLow;
    uint64_t size=((uint64_t)info.nFileSizeHigh<<32)|info.nFileSizeLow;
    uint64_t modified=((uint64_t)info.ftLastWriteTime.dwHighDateTime<<32)|info.ftLastWriteTime.dwLowDateTime;
    return info.dwVolumeSerialNumber==h[5] && index==h[6] && size==h[7] && modified==h[8] &&
        modified<=created?ERROR_SUCCESS:ERROR_RETRY;
}

static DWORD war3_quest_current_vm(uint8_t **image_out,uint64_t *vm_out) {
    uint8_t *image,*native_table;DWORD error=war3_bootstrap_context(&image,&native_table);
    if(error)return error;
    uint64_t context=(uintptr_t)native_table-0x28u;
    if(!war3_readable_span(context,0xf8) || *(uint64_t *)(uintptr_t)context!=(uintptr_t)image+0x24667c8u)
        return ERROR_REVISION_MISMATCH;
    uint64_t world=*(uint64_t *)(void *)(image+0x2b59964u)^0x363abbfd3defaec9ULL^
        *(uint64_t *)(void *)(image+0x2bd7bc8u);
    if(!war3_readable_span(world,0x25f0) || *(uint64_t *)(uintptr_t)world!=(uintptr_t)image+0x23d0690u)
        return ERROR_NOT_READY;
    uint64_t host=*(uint64_t *)(uintptr_t)(world+0x25e8);
    if(!war3_readable_span(host,16) || *(uint64_t *)(uintptr_t)host!=(uintptr_t)image+0x2449bf0u)
        return ERROR_NOT_READY;
    uint32_t index=*(uint32_t *)(uintptr_t)(host+8),count=*(uint32_t *)(uintptr_t)(context+0xe8);
    uint64_t array=*(uint64_t *)(uintptr_t)(context+0xf0);
    if(count>4096u || index>=count || !war3_readable_span(array,(size_t)count*8u))return ERROR_INVALID_DATA;
    uint64_t vm=*(uint64_t *)(uintptr_t)(array+(size_t)index*8u);
    if(!war3_readable_span(vm,0x48d8) || *(uint64_t *)(uintptr_t)(vm+0x4868)!=host)return ERROR_RETRY;
    *image_out=image;*vm_out=vm;return ERROR_SUCCESS;
}

static DWORD war3_quest_handle(uint8_t *image,uint64_t vm,War3NameHashFn hash_fn,War3QuestName name,
    uint32_t resolver_rva,uint32_t vtable_rva,uint64_t *handle,uint64_t *object,uint64_t *full) {
    uint64_t table=*(uint64_t *)(uintptr_t)(vm+0x4878),node=0;
    if(!war3_readable_span(table,0x48) || *(uint64_t *)(uintptr_t)table!=(uintptr_t)image+0x2466598u)
        return ERROR_INVALID_DATA;
    DWORD error=war3_quest_symbol(table,hash_fn,name,&node);if(error)return error;
    if(*(uint32_t *)(uintptr_t)(node+0x30)!=7 || *(uint32_t *)(uintptr_t)(node+0x34)!=7)return ERROR_INVALID_DATA;
    *handle=*(uint64_t *)(uintptr_t)(node+0x38);
    if(!*handle || *handle>UINT32_MAX)return ERROR_INVALID_HANDLE;
    *object=((War3QuestResolveFn)(void *)(image+resolver_rva))((uint32_t)*handle);
    if(!war3_readable_span(*object,0xa0) || *(uint64_t *)(uintptr_t)*object!=(uintptr_t)image+vtable_rva)
        return ERROR_INVALID_HANDLE;
    *full=*(uint64_t *)(uintptr_t)(*object+0x18);
    return *full?ERROR_SUCCESS:ERROR_INVALID_HANDLE;
}

static DWORD war3_quest_collect(const War3QuestWire *wire,War3QuestView *view,uint32_t *message) {
    uint8_t *image=NULL;uint64_t vm=0,execute=0;const uint64_t *h=wire->header;
    *message=1;DWORD error=war3_quest_source(h,message);if(error)return error;
    *message=2;
    NativeCommand cmd={0};NativeOp op={0};uint64_t *catalog=NULL;uint32_t count=0;
    cmd.op_count=1;op.kind=WAR3_NATIVE_OP_EXT_QUERY_CATALOG_HEADER;
    error=war3_catalog_query(&cmd,&op,&catalog,&count);
    if(!error && (count!=6 || catalog[2]!=h[3]))error=ERROR_RETRY;
    if(catalog)HeapFree(GetProcessHeap(),0,catalog);
    if(error)return error;
    if((error=war3_quest_current_vm(&image,&vm)))return error;
    *message=8;if((error=war3_quest_profile(image,&execute)))return error;
    War3NameHashFn hash_fn=(War3NameHashFn)(void *)(image+WAR3_BOOTSTRAP_HASH_RVA);
    ZeroMemory(view,sizeof(*view));view->resolved[0]=vm;view->execute_handler=execute;
    *message=4;
    if((error=war3_quest_handle(image,vm,hash_fn,wire->quest,0xa0f100u,0x23d8fe0u,
        &view->resolved[1],&view->resolved[2],&view->resolved[3])))return error;
    if((error=war3_quest_handle(image,vm,hash_fn,wire->entry_trigger,0xa10e40u,0x23d8698u,
        &view->resolved[4],&view->resolved[5],&view->resolved[6])))return error;
    uint8_t flags=*(uint8_t *)(uintptr_t)(view->resolved[2]+0x58);
    view->flags=(flags&1u)|((flags&8u)?2u:0u)|(flags&4u);
    uint64_t fingerprint=14695981039346656037ULL;
    *message=5;
    for(uint32_t n=0;n<wire->function_count;++n) {
        uint64_t code=0;
        if((error=war3_quest_function(image,vm,hash_fn,wire->functions[n],&code,&fingerprint)))return error;
    }
    for(uint32_t n=0;n<wire->binding_count;++n) {
        uint64_t handle,trigger,full;
        if((error=war3_quest_handle(image,vm,hash_fn,wire->bindings[n].trigger,0xa10e40u,0x23d8698u,
            &handle,&trigger,&full)))return error;
        fingerprint=war3_catalog_mix(fingerprint,handle);fingerprint=war3_catalog_mix(fingerprint,full);
        if((error=war3_quest_check_binding(image,vm,trigger,&wire->bindings[n],hash_fn,&fingerprint)))return error;
    }
    view->resolved[7]=fingerprint?fingerprint:1;
    /* All calls above are read-only; still bind the source again at the end. */
    *message=1;if((error=war3_quest_source(h,message)))return error;
    uint8_t *after_image;uint64_t after_vm;
    *message=2;if((error=war3_quest_current_vm(&after_image,&after_vm)))return error;
    return after_image==image && after_vm==vm?ERROR_SUCCESS:ERROR_RETRY;
}

static DWORD war3_quest_execute_original(const War3QuestView *view) {
    /* Handler was looked up in the verified native table, never supplied by
       the request. The game creates the original trigger's JASS context. */
    ((War3QuestExecuteFn)(uintptr_t)view->execute_handler)((uint32_t)view->resolved[4]);
    return ERROR_SUCCESS;
}

static DWORD war3_quest_query(NativeCommand *cmd,NativeOp *op,const uint64_t *input,uint32_t input_count,
    uint64_t **extra,uint32_t *extra_count) {
    if(!cmd || !op || cmd->unit_handle || cmd->op_count!=1 || op->handler || op->rawcode ||
       op->arg0 || op->arg1 || op->kind<320u || op->kind>322u)return ERROR_INVALID_PARAMETER;
    War3QuestWire *wire=(War3QuestWire *)HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,sizeof(*wire));
    if(!wire)return ERROR_OUTOFMEMORY;
    DWORD error=ERROR_INVALID_DATA;
    if(war3_quest_wire_parse(input,input_count,wire) && input[2]==op->kind-320u) {
        uint64_t *reply=(uint64_t *)HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,32u*8u);
        if(!reply)error=ERROR_OUTOFMEMORY;
        else {
            error=war3_quest_transaction(wire,reply,war3_quest_collect,war3_quest_execute_original);
            if(error)HeapFree(GetProcessHeap(),0,reply);
            else {*extra=reply;*extra_count=32;}
        }
    }
    HeapFree(GetProcessHeap(),0,wire);return error;
}
