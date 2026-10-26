/* R23 exact 23745 symbol and callback layout; caller holds the game-thread
   transaction and SEH boundary. Never invoke the resolved JASS bytecode. */
#ifndef WAR3_QUEST_BINDING_H
#define WAR3_QUEST_BINDING_H
#include "war3_quest_wire.h"
static DWORD war3_quest_symbol(uint64_t table,War3NameHashFn hash_fn,War3QuestName name,uint64_t *out) {
    char text[128];*out=0;
    if(!name.length || name.length>=sizeof(text) || !war3_readable_span(table,0x48))return ERROR_INVALID_DATA;
    memcpy(text,name.text,name.length);text[name.length]=0;uint32_t hash=hash_fn(text);
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
        if(!node || (node&1))return ERROR_NOT_FOUND;
        if((node&7) || !war3_readable_span(node,0x40) ||
           !war3_readable_span(node+(int64_t)offset+8u,8))return ERROR_INVALID_ADDRESS;
        if(*(uint32_t *)(uintptr_t)node==hash) {
            uint64_t actual=*(uint64_t *)(uintptr_t)(node+0x28);
            if(!war3_readable_span(actual,(size_t)name.length+1u))return ERROR_INVALID_ADDRESS;
            if(!memcmp((void *)(uintptr_t)actual,text,(size_t)name.length+1u)) {*out=node;return ERROR_SUCCESS;}
        }
        node=*(uint64_t *)(uintptr_t)(node+(int64_t)offset+8u);
    }
    return ERROR_INVALID_DATA;
}

static DWORD war3_quest_function(uint8_t *image,uint64_t vm,War3NameHashFn hash_fn,
    War3QuestName name,uint64_t *code,uint64_t *fingerprint) {
    uint64_t table=*(uint64_t *)(uintptr_t)(vm+0x48c8),node=0;
    if(!war3_readable_span(table,0x48) || *(uint64_t *)(uintptr_t)table!=(uintptr_t)image+0x2466638u)
        return ERROR_INVALID_DATA;
    DWORD error=war3_quest_symbol(table,hash_fn,name,&node);if(error)return error;
    *code=*(uint64_t *)(uintptr_t)(node+0x30);
    if(!war3_readable_span(*code,16))return ERROR_INVALID_ADDRESS;
    *fingerprint=war3_catalog_mix(*fingerprint,node);
    *fingerprint=war3_catalog_mix(*fingerprint,*code);
    return ERROR_SUCCESS;
}

static DWORD war3_quest_check_binding(uint8_t *image,uint64_t vm,uint64_t trigger,
    const War3QuestBinding *binding,War3NameHashFn hash_fn,uint64_t *fingerprint) {
    if(!war3_readable_span(vm,0x48d8) || !war3_readable_span(trigger,0xa0) ||
       !binding || !binding->count || binding->count>WAR3_QUEST_MAX_ACTIONS)return ERROR_INVALID_DATA;
    /* TriggerRemoveCondition at d33310 proves +80, zero/low-bit sentinel.
       Reject added runtime conditions too: TriggerExecute bypasses them. */
    uint64_t conditions=*(uint64_t *)(uintptr_t)(trigger+0x80);
    if(conditions && !(conditions&1))return ERROR_NOT_SUPPORTED;
    *fingerprint=war3_catalog_mix(*fingerprint,conditions);
    uint64_t array=*(uint64_t *)(uintptr_t)(vm+0x48d0);
    if(!war3_readable_span(array,24))return ERROR_INVALID_ADDRESS;
    uint32_t length=*(uint32_t *)(uintptr_t)array,capacity=*(uint32_t *)(uintptr_t)(array+16);
    uint64_t values=*(uint64_t *)(uintptr_t)(array+8);
    if(length>capacity || capacity>1000000u || !war3_readable_span(values,(size_t)length*8u))return ERROR_INVALID_DATA;
    uint64_t node=*(uint64_t *)(uintptr_t)(trigger+0x98),seen[WAR3_QUEST_MAX_ACTIONS];
    for(uint32_t n=0;n<binding->count;++n) {
        if(!node || (node&7) || !war3_readable_span(node,24))return ERROR_INVALID_ADDRESS;
        for(uint32_t k=0;k<n;++k)if(seen[k]==node)return ERROR_INVALID_DATA;
        seen[n]=node;uint64_t action=*(uint64_t *)(uintptr_t)(node+0x10);
        if(!war3_readable_span(action,0x60) || *(uint64_t *)(uintptr_t)action!=(uintptr_t)image+0x23d8448u ||
           !*(uint64_t *)(uintptr_t)(action+0x18))return ERROR_INVALID_DATA;
        uint64_t callback=*(uint64_t *)(uintptr_t)(action+0x58);
        if(!war3_readable_span(callback,0x60) || *(uint64_t *)(uintptr_t)callback!=(uintptr_t)image+0x23d7d50u ||
           !*(uint64_t *)(uintptr_t)(callback+0x18))return ERROR_INVALID_DATA;
        uint32_t index=*(uint32_t *)(uintptr_t)(callback+0x58);uint64_t code=0;
        if(index>=length)return ERROR_INVALID_DATA;
        DWORD error=war3_quest_function(image,vm,hash_fn,binding->actions[n],&code,fingerprint);
        if(error)return error;
        if(*(uint64_t *)(uintptr_t)(values+(size_t)index*8u)!=code)return ERROR_INVALID_DATA;
        *fingerprint=war3_catalog_mix(*fingerprint,node);
        *fingerprint=war3_catalog_mix(*fingerprint,*(uint64_t *)(uintptr_t)(action+0x18));
        *fingerprint=war3_catalog_mix(*fingerprint,*(uint64_t *)(uintptr_t)(callback+0x18));
        *fingerprint=war3_catalog_mix(*fingerprint,index);
        node=*(uint64_t *)(uintptr_t)(node+8);
    }
    return !node || (node&1)?ERROR_SUCCESS:ERROR_INVALID_DATA;
}
#endif
