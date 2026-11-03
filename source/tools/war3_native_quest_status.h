/* R25: read-only scalar quest globals. Reuses the R23 exact-build VM/symbol
   layout, with no trigger binding, dispatch, setter or execution ledger. */
typedef uint64_t (__fastcall *War3QuestStatusResolveFn)(uint32_t);
typedef uint8_t (__fastcall *War3QuestStatusBoolFn)(uint32_t);

static DWORD war3_quest_status_vm(uint8_t **image_out,uint64_t *vm_out) {
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

static DWORD war3_quest_status_symbol(uint8_t *image,uint64_t vm,const char *name,size_t length,uint64_t *out) {
    uint64_t table=*(uint64_t *)(uintptr_t)(vm+0x4878);*out=0;
    if(!war3_readable_span(table,0x48) || *(uint64_t *)(uintptr_t)table!=(uintptr_t)image+0x2466598u)
        return ERROR_INVALID_DATA;
    uint32_t hash=((War3NameHashFn)(void *)(image+WAR3_BOOTSTRAP_HASH_RVA))(name);
    uint32_t mask=*(uint32_t *)(uintptr_t)(table+0x40);
    if(mask==UINT32_MAX)return ERROR_NOT_FOUND;
    if(mask>65535u || ((mask+1u)&mask))return ERROR_INVALID_DATA;
    uint64_t buckets=*(uint64_t *)(uintptr_t)(table+0x30);
    if(!war3_readable_span(buckets,((size_t)mask+1u)*24u))return ERROR_INVALID_ADDRESS;
    uint64_t bucket=buckets+(hash&mask)*24u;
    int32_t offset=*(int32_t *)(uintptr_t)bucket;
    if(offset< -0x100 || offset>0x100 || (offset&7))return ERROR_INVALID_DATA;
    uint64_t node=*(uint64_t *)(uintptr_t)(bucket+0x10);
    for(unsigned step=0;step<4096u;++step) {
        if(!node || (node&1))return *out?ERROR_SUCCESS:ERROR_NOT_FOUND;
        if((node&7) || !war3_readable_span(node,0x40) ||
           !war3_readable_span(node+(int64_t)offset+8u,8))return ERROR_INVALID_ADDRESS;
        if(*(uint32_t *)(uintptr_t)node==hash) {
            uint64_t actual=*(uint64_t *)(uintptr_t)(node+0x28);
            if(!war3_readable_span(actual,length+1u))return ERROR_INVALID_ADDRESS;
            if(!memcmp((void *)(uintptr_t)actual,name,length+1u)) {
                if(*out)return ERROR_DUP_NAME; /* Never accept a duplicate exact global. */
                *out=node;
            }
        }
        node=*(uint64_t *)(uintptr_t)(node+(int64_t)offset+8u);
    }
    return ERROR_INVALID_DATA;
}

static DWORD war3_quest_status_one(uint8_t *image,uint64_t vm,const char *name,size_t length,
    uint64_t completed,uint64_t failed,uint64_t *row) {
    uint64_t node=0;DWORD error=war3_quest_status_symbol(image,vm,name,length,&node);
    if(error)return error;
    if(*(uint32_t *)(uintptr_t)(node+0x30)!=7 || *(uint32_t *)(uintptr_t)(node+0x34)!=7)
        return ERROR_INVALID_DATA;
    uint64_t handle=*(uint64_t *)(uintptr_t)(node+0x38);
    if(!handle || handle>UINT32_MAX)return ERROR_INVALID_HANDLE;
    uint64_t object=((War3QuestStatusResolveFn)(void *)(image+0xa0f100u))((uint32_t)handle);
    if(!war3_readable_span(object,0xa0) || *(uint64_t *)(uintptr_t)object!=(uintptr_t)image+0x23d8fe0u)
        return ERROR_INVALID_HANDLE;
    uint64_t full=*(uint64_t *)(uintptr_t)(object+0x18);
    if(!full)return ERROR_INVALID_HANDLE;
    /* These natives may only write AL. A 32/64-bit return type reads stale high bits. */
    uint8_t is_completed=((War3QuestStatusBoolFn)(uintptr_t)completed)((uint32_t)handle);
    uint8_t is_failed=((War3QuestStatusBoolFn)(uintptr_t)failed)((uint32_t)handle);
    if(is_completed>1 || is_failed>1)return ERROR_INVALID_DATA;
    if(*(uint64_t *)(uintptr_t)(node+0x38)!=handle ||
       *(uint64_t *)(uintptr_t)(object+0x18)!=full)return ERROR_RETRY;
    row[1]=handle;row[2]=object;row[3]=full;row[4]=is_completed|((uint64_t)is_failed<<1);
    return ERROR_SUCCESS;
}

static DWORD war3_quest_status_query(NativeCommand *cmd,NativeOp *op,const uint64_t *input,uint32_t input_count,
    uint64_t **extra,uint32_t *extra_count) {
    if(cmd->unit_handle || cmd->op_count!=1 || op->rawcode || op->handler || !op->arg0 || op->arg1 ||
       input_count<3 || input_count>28 || cmd->reserved!=input_count || !input[0] || input[0]>16)
        return ERROR_INVALID_PARAMETER;
    uint32_t count=(uint32_t)input[0],cursor=1;char names[16][128];size_t lengths[16];
    for(uint32_t n=0;n<count;++n) {
        if(cursor>=input_count || !input[cursor] || input[cursor]>127)return ERROR_INVALID_DATA;
        size_t length=(size_t)input[cursor++],words=(length+7u)/8u;
        if(words>input_count-cursor)return ERROR_INVALID_DATA;
        memcpy(names[n],input+cursor,length);names[n][length]=0;lengths[n]=length;
        for(size_t k=0;k<length;++k) {
            unsigned char c=(unsigned char)names[n][k];
            if(!(c=='_' || (c>='A' && c<='Z') || (c>='a' && c<='z') || (k && c>='0' && c<='9')))
                return ERROR_INVALID_DATA;
        }
        for(size_t k=length;k<words*8u;++k)if(((const uint8_t *)(input+cursor))[k])return ERROR_INVALID_DATA;
        cursor+=(uint32_t)words;
    }
    if(cursor!=input_count)return ERROR_INVALID_DATA;
    uint64_t *reply=(uint64_t *)HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,(4u+count*5u)*8u);
    if(!reply)return ERROR_OUTOFMEMORY;
    DWORD error=ERROR_INVALID_DATA;
    __try {
        NativeCommand catalog_cmd={0};NativeOp catalog_op={0};uint64_t *catalog=NULL;uint32_t catalog_count=0;
        catalog_cmd.op_count=1;catalog_op.kind=WAR3_NATIVE_OP_EXT_QUERY_CATALOG_HEADER;
        error=war3_catalog_query(&catalog_cmd,&catalog_op,&catalog,&catalog_count);
        if(!error && (catalog_count!=6 || catalog[2]!=op->arg0))error=ERROR_RETRY;
        if(catalog)HeapFree(GetProcessHeap(),0,catalog);
        if(error)__leave;
        uint8_t *image,*table;uint64_t vm,completed=0,failed=0;
        if((error=war3_quest_status_vm(&image,&vm)))__leave;
        static const War3BootstrapCodeCheck checks[]={
            {0xa0f100u,612u,0x787dc7783def1d00ULL},
            {0xc50003u,62u,0xa13bc516c90ae996ULL},
            {0x9dde50u,39u,0x9afa250dca103fd3ULL},
        };
        for(unsigned n=0;n<sizeof(checks)/sizeof(checks[0]);++n) {
            if(!war3_readable_span((uintptr_t)(image+checks[n].rva),checks[n].size) ||
               war3_bootstrap_hash(image+checks[n].rva,checks[n].size)!=checks[n].hash) {
                error=ERROR_REVISION_MISMATCH;break;
            }
        }
        if(error)__leave;
        uint8_t *current_image;
        if((error=war3_bootstrap_context(&current_image,&table)))__leave;
        if(current_image!=image) {error=ERROR_RETRY;__leave;}
        int ci=war3_bootstrap_index("IsQuestCompleted"),fi=war3_bootstrap_index("IsQuestFailed");
        if(ci<0 || fi<0) {error=ERROR_PROC_NOT_FOUND;__leave;}
        if((error=war3_bootstrap_query(image,table,(uint32_t)ci,&completed)) ||
           (error=war3_bootstrap_query(image,table,(uint32_t)fi,&failed)))__leave;
        for(uint32_t n=0;n<count;++n) {
            uint64_t *row=reply+4u+n*5u;DWORD item_error;
            __try {item_error=war3_quest_status_one(image,vm,names[n],lengths[n],completed,failed,row);}
            __except(EXCEPTION_EXECUTE_HANDLER) {item_error=GetExceptionCode();}
            if(item_error) {ZeroMemory(row,5u*8u);row[0]=item_error;}
        }
        uint8_t *after_image;uint64_t after_vm;
        if((error=war3_quest_status_vm(&after_image,&after_vm)))__leave;
        if(after_image!=image || after_vm!=vm) {error=ERROR_RETRY;__leave;}
        reply[0]=0x31535152u;reply[1]=1;reply[2]=op->arg0;reply[3]=count;
    } __except(EXCEPTION_EXECUTE_HANDLER) {error=GetExceptionCode();}
    if(error) {HeapFree(GetProcessHeap(),0,reply);return error;}
    *extra=reply;*extra_count=4u+count*5u;return ERROR_SUCCESS;
}
