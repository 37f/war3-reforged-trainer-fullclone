/* R21: current-map definitions, read-only. Exact 2.0.4.23745 layout evidence
   is recorded in docs/r21-runtime-catalog-feasibility.md. No lazy getters. */
#define WAR3_CATALOG_MAGIC 0x31544352u
#define WAR3_CATALOG_MAX_OBJECTS 100000u
#define WAR3_CATALOG_MAX_NAMES 128u
#define WAR3_CATALOG_MAX_NAME 65536u
#define WAR3_CATALOG_MAX_WORDS (32u*1024u*1024u/8u)
#define WAR3_CATALOG_PAGE 16u

typedef struct War3CatalogRoots {
    uint8_t *image;
    uint64_t context,state,jass,ui;
    uint64_t definitions[3];
} War3CatalogRoots;

typedef struct War3CatalogBuffer {
    uint64_t *data;
    uint32_t count,capacity;
} War3CatalogBuffer;

static uint64_t g_catalog_epoch=1,g_catalog_fingerprint=0,g_catalog_token=0;
static uint64_t g_catalog_context_signature=0;
static ULONGLONG g_catalog_last_observation=0;
static int g_catalog_active=0;
static uint64_t g_catalog_diagnostic=0; /* failure location, never a game pointer */
static uint8_t *g_catalog_ui_module=NULL;
static War3GetGameUIFn g_catalog_ui_getter=NULL;

static DWORD war3_catalog_existing_ui(uint8_t *image,uint64_t *value) {
    if(g_catalog_ui_module!=image || !g_catalog_ui_getter) {
        /* BlzGetMouseFocusUnit's verified first call is GetGameUI.
           Its create flag is deliberately ZERO: the observed allocation
           branch at +0xebe921 is gated on that flag. */
        uint8_t *entry=image+0xc52120u;
        if(!war3_readable_span((uint64_t)(uintptr_t)entry,64) ||
           war3_bootstrap_hash(entry,64)!=0x618030e9e2c08901ULL || entry[10]!=0xe8)
            return ERROR_REVISION_MISMATCH;
        uint8_t *getter=entry+15+(int64_t)*(int32_t *)(void *)(entry+11);
        if(getter!=image+0xebe740u || !war3_executable_pointer((uint64_t)(uintptr_t)getter))
            return ERROR_REVISION_MISMATCH;
        g_catalog_ui_getter=(War3GetGameUIFn)(void *)getter;g_catalog_ui_module=image;
    }
    *value=(uint64_t)(uintptr_t)g_catalog_ui_getter(0,0);
    return war3_readable_span(*value,0x10)?ERROR_SUCCESS:ERROR_NOT_READY;
}

static void war3_catalog_retire(void) {
    ++g_catalog_epoch;
    if(!g_catalog_epoch) ++g_catalog_epoch;
    g_catalog_fingerprint=g_catalog_token=0;
}

static uint64_t war3_catalog_mix(uint64_t hash,uint64_t value) {
    for(unsigned n=0;n<8;++n) {hash=(hash^(uint8_t)value)*1099511628211ULL;value>>=8;}
    return hash;
}

static DWORD war3_catalog_push(War3CatalogBuffer *buffer,uint64_t value) {
    if(buffer->count==WAR3_CATALOG_MAX_WORDS) return ERROR_INSUFFICIENT_BUFFER;
    if(buffer->count==buffer->capacity) {
        uint32_t capacity=buffer->capacity?buffer->capacity*2u:128u;
        if(capacity>WAR3_CATALOG_MAX_WORDS) capacity=WAR3_CATALOG_MAX_WORDS;
        void *next=buffer->data?HeapReAlloc(GetProcessHeap(),0,buffer->data,capacity*8u):
            HeapAlloc(GetProcessHeap(),0,capacity*8u);
        if(!next) return ERROR_OUTOFMEMORY;
        buffer->data=next;buffer->capacity=capacity;
    }
    buffer->data[buffer->count++]=value;
    return ERROR_SUCCESS;
}

/* Caller owns SEH boundary; validate each whole span before dereferencing. */
static DWORD war3_catalog_read_roots(War3CatalogRoots *view) {
    static const uint32_t slots[3]={0x230,0x238,0x338};
    static const uint32_t types[3]={0,1,4};
    static const uint32_t vtables[3]={0x242c410,0x242c470,0x242c4d0};
    uint8_t *image,*table;
    DWORD error=war3_bootstrap_context(&image,&table);
    if(error) return error;
    ZeroMemory(view,sizeof(*view));view->image=image;view->jass=(uint64_t)(uintptr_t)table;
    error=war3_catalog_existing_ui(image,&view->ui);
    if(error) return error;
    view->context=(uint64_t)(uintptr_t)((War3ContextGetFn)(void *)(image+WAR3_BOOTSTRAP_CONTEXT_RVA))(13);
    if(!war3_readable_span(view->context,0x28)) return ERROR_NOT_READY;
    view->state=*(uint64_t *)(uintptr_t)(view->context+0x20);
    if(!war3_readable_span(view->state,0x340)) return ERROR_NOT_READY;
    for(unsigned k=0;k<3;++k) {
        uint64_t manager=*(uint64_t *)(uintptr_t)(view->state+slots[k]);
        if(!war3_readable_span(manager,0x25c0)) return ERROR_NOT_READY;
        if(*(uint64_t *)(uintptr_t)manager!=(uint64_t)(uintptr_t)(image+vtables[k]) ||
           *(uint32_t *)(uintptr_t)(manager+0x25a8)!=types[k]) return ERROR_REVISION_MISMATCH;
        view->definitions[k]=*(uint64_t *)(uintptr_t)(manager+0x25b0);
    }
    return ERROR_SUCCESS;
}

static uint64_t war3_catalog_root_signature(const War3CatalogRoots *view) {
    uint64_t hash=14695981039346656037ULL;
    hash=war3_catalog_mix(hash,view->context);hash=war3_catalog_mix(hash,view->state);
    hash=war3_catalog_mix(hash,view->jass);
    hash=war3_catalog_mix(hash,view->ui);
    for(unsigned k=0;k<3;++k) {
        uint64_t root=view->definitions[k];hash=war3_catalog_mix(hash,root);
        if(root) {
            if(!war3_readable_span(root,0x40)) return 0;
            /* Hash the full headers, including arrays/counts/capacities. */
            for(unsigned n=0;n<8;++n) hash=war3_catalog_mix(hash,((uint64_t *)(uintptr_t)root)[n]);
        }
    }
    return hash?hash:1;
}

/* No directory scan here: observe context/header transitions between queries.
   This runs only after first directory use, at most four times per second. */
static void war3_catalog_observe(void) {
    War3CatalogRoots view;uint64_t signature=0;
    ULONGLONG now=GetTickCount64();
    if(!g_catalog_active || now-g_catalog_last_observation<250u) return;
    g_catalog_last_observation=now;
    __try {if(!war3_catalog_read_roots(&view)) signature=war3_catalog_root_signature(&view);}
    __except(EXCEPTION_EXECUTE_HANDLER) {signature=0;}
    if(signature!=g_catalog_context_signature) {
        war3_catalog_retire();g_catalog_context_signature=signature;
    }
}

static DWORD war3_catalog_record(
    uint64_t row,unsigned kind,int custom,uint64_t *hash,War3CatalogBuffer *output,
    ULONGLONG deadline,uint32_t *modifications
) {
    uint64_t seen[128],buckets,table,size;uint32_t found=0,names=0,name_slot=0;
    uint32_t base=*(uint32_t *)(uintptr_t)row,new_id=*(uint32_t *)(uintptr_t)(row+4);
    DWORD error;
    g_catalog_diagnostic=0x0100000000000000ULL|base;
    if(!base || (custom?!new_id:new_id!=0)) return ERROR_INVALID_DATA;
    *hash=war3_catalog_mix(*hash,base);*hash=war3_catalog_mix(*hash,custom?new_id:base);
    *hash=war3_catalog_mix(*hash,(uint64_t)custom);
    if(output) {
        if((error=war3_catalog_push(output,base)) || (error=war3_catalog_push(output,custom?new_id:base)) ||
           (error=war3_catalog_push(output,custom))) return error;
        name_slot=output->count;if((error=war3_catalog_push(output,0))) return error;
    }
    buckets=*(uint64_t *)(uintptr_t)(row+8);table=*(uint64_t *)(uintptr_t)(row+16);
    g_catalog_diagnostic=0x0200000000000000ULL|base;
    size=*(uint64_t *)(uintptr_t)(row+24);
    if(buckets>65536u || size>128u || (size && !buckets) ||
       (buckets && !war3_readable_span(table,(size_t)buckets*8u))) return ERROR_INVALID_DATA;
    for(uint64_t bucket=0;bucket<buckets;++bucket) {
        uint64_t node=((uint64_t *)(uintptr_t)table)[bucket];
        while(node) {
            g_catalog_diagnostic=0x0300000000000000ULL|base;
            uint32_t count,capacity,key;uint64_t mods;
            if(found>=size || found>=128u || !war3_readable_span(node,0x28)) return ERROR_INVALID_DATA;
            for(unsigned n=0;n<found;++n) if(seen[n]==node) return ERROR_INVALID_DATA;
            seen[found++]=node;key=*(uint32_t *)(uintptr_t)(node+8);
            count=*(uint32_t *)(uintptr_t)(node+16);mods=*(uint64_t *)(uintptr_t)(node+24);
            capacity=*(uint32_t *)(uintptr_t)(node+32);
            g_catalog_diagnostic=0x0400000000000000ULL|base;
            if(count>capacity || capacity>1000000u || *modifications>1000000u-count ||
               (count && !war3_readable_span(mods,(size_t)count*72u))) return ERROR_INVALID_DATA;
            *modifications+=count;
            for(uint32_t n=0;n<count;++n) {
                uint8_t *field=(uint8_t *)(uintptr_t)(mods+(uint64_t)n*72u);
                uint32_t id=*(uint32_t *)(void *)field;
                if((n&255u)==0 && GetTickCount64()>deadline) return ERROR_TIMEOUT;
                if(id!=(kind==2?0x6d616e61u:0x6d616e75u)) continue; /* anam / unam */
                g_catalog_diagnostic=0x0500000000000000ULL|base;
                uint64_t text=*(uint64_t *)(void *)(field+24),length=*(uint64_t *)(void *)(field+32);
                uint32_t level=*(uint32_t *)(void *)(field+8),pointer=*(uint32_t *)(void *)(field+12);
                if(*(uint32_t *)(void *)(field+4)!=3u || ++names>WAR3_CATALOG_MAX_NAMES ||
                   length>WAR3_CATALOG_MAX_NAME || !war3_readable_span(text,(size_t)length+1u) ||
                   *(uint8_t *)(uintptr_t)(text+length)!=0) return ERROR_INVALID_DATA;
                *hash=war3_catalog_mix(*hash,key);*hash=war3_catalog_mix(*hash,level);
                *hash=war3_catalog_mix(*hash,pointer);*hash=war3_catalog_mix(*hash,length);
                if(output && ((error=war3_catalog_push(output,key)) || (error=war3_catalog_push(output,level)) ||
                    (error=war3_catalog_push(output,pointer)) || (error=war3_catalog_push(output,length)))) return error;
                for(uint64_t offset=0;offset<length;offset+=8u) {
                    uint64_t word=0,bytes=length-offset<8u?length-offset:8u;
                    memcpy(&word,(void *)(uintptr_t)(text+offset),(size_t)bytes);
                    for(uint64_t j=0;j<bytes;++j) if(!((uint8_t *)&word)[j]) return ERROR_INVALID_DATA;
                    *hash=war3_catalog_mix(*hash,word);
                    if(output && (error=war3_catalog_push(output,word))) return error;
                }
            }
            node=*(uint64_t *)(uintptr_t)node;
        }
        if((bucket&255u)==0 && GetTickCount64()>deadline) return ERROR_TIMEOUT;
    }
    if(found!=size) return ERROR_INVALID_DATA;
    *hash=war3_catalog_mix(*hash,names);
    if(output) output->data[name_slot]=names;
    return ERROR_SUCCESS;
}

static DWORD war3_catalog_from_roots(
    const War3CatalogRoots *view,unsigned op,unsigned kind,uint64_t start,uint64_t expected,
    uint64_t **extra,uint32_t *extra_count
) {
    static const uint32_t vtables[3]={0x242c6b0,0x242c708,0x242c760};
    War3CatalogBuffer buffer={0};uint32_t totals[3]={0},total=0,mods=0,returned=0;
    uint64_t signature=0,hash=14695981039346656037ULL,token=0;
    DWORD error=ERROR_SUCCESS;ULONGLONG deadline=GetTickCount64()+50u;
    if(!view || !extra || !extra_count || (op!=318u && op!=319u) || (op==319u && kind>2u)) return ERROR_INVALID_PARAMETER;
    *extra=NULL;*extra_count=0;
    __try {
        signature=war3_catalog_root_signature(view);
        if(!signature) {error=ERROR_INVALID_ADDRESS;__leave;}
        hash=war3_catalog_mix(hash,signature);
        if(op==319u) for(unsigned n=0;n<7;++n) if((error=war3_catalog_push(&buffer,0))) __leave;
        for(unsigned k=0;k<3;++k) {
            uint64_t root=view->definitions[k];
            if(!root) continue;
            if(*(uint64_t *)(uintptr_t)root!=(uint64_t)(uintptr_t)(view->image+vtables[k])) {error=ERROR_REVISION_MISMATCH;__leave;}
            for(unsigned custom=0;custom<2;++custom) {
                g_catalog_diagnostic=0x1000000000000000ULL|((uint64_t)k<<8)|custom;
                uint64_t offset=custom?32u:8u;
                uint32_t count=*(uint32_t *)(uintptr_t)(root+offset),capacity=*(uint32_t *)(uintptr_t)(root+offset+16);
                uint64_t rows=*(uint64_t *)(uintptr_t)(root+offset+8);
                if(count>WAR3_CATALOG_MAX_OBJECTS || count>capacity || capacity>WAR3_CATALOG_MAX_OBJECTS ||
                   total>WAR3_CATALOG_MAX_OBJECTS-count || (count && !war3_readable_span(rows,(size_t)count*40u))) {
                    error=ERROR_INVALID_DATA;__leave;
                }
                total+=count;
                for(uint32_t n=0;n<count;++n) {
                    uint32_t index=totals[k]+n;
                    int selected=op==319u && k==kind && index>=start && index-start<WAR3_CATALOG_PAGE;
                    error=war3_catalog_record(rows+(uint64_t)n*40u,k,custom,&hash,selected?&buffer:NULL,deadline,&mods);
                    if(error) __leave;
                    if(selected) ++returned;
                }
                totals[k]+=count;
            }
        }
        if(op==319u && (!returned || start>=totals[kind])) {error=ERROR_INVALID_PARAMETER;__leave;}
        if(signature!=war3_catalog_root_signature(view)) {error=ERROR_RETRY;__leave;}
        if(hash!=g_catalog_fingerprint) {
            war3_catalog_retire();g_catalog_fingerprint=hash;
            token=war3_catalog_mix(hash,g_catalog_epoch);
            token=war3_catalog_mix(token,GetCurrentProcessId());
            g_catalog_token=token?token:1;
        }
        token=g_catalog_token;
        if(op==319u && expected!=token) {error=ERROR_RETRY;__leave;}
        if(op==318u) {
            uint64_t header[6]={WAR3_CATALOG_MAGIC,1,token,totals[0],totals[1],totals[2]};
            for(unsigned n=0;n<6;++n) if((error=war3_catalog_push(&buffer,header[n]))) __leave;
        } else {
            uint64_t header[7]={WAR3_CATALOG_MAGIC,1,token,kind,totals[kind],start,returned};
            memcpy(buffer.data,header,sizeof(header));
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) {error=GetExceptionCode();}
    if(error) {if(buffer.data) HeapFree(GetProcessHeap(),0,buffer.data);war3_catalog_retire();return error;}
    *extra=buffer.data;*extra_count=buffer.count;return ERROR_SUCCESS;
}

static DWORD war3_catalog_query(NativeCommand *cmd,NativeOp *op,uint64_t **extra,uint32_t *count) {
    War3CatalogRoots before,after;DWORD error;
    if(!cmd || cmd->unit_handle || cmd->op_count!=1u || op->handler || cmd->reserved ||
       (op->kind==318u && (op->rawcode || op->arg0 || op->arg1))) return ERROR_INVALID_PARAMETER;
    g_catalog_active=1;
    g_catalog_diagnostic=0x2000000000000000ULL;
    __try {
        error=war3_catalog_read_roots(&before);
        if(error) {war3_catalog_retire();return error;}
        uint64_t signature=war3_catalog_root_signature(&before);
        if(signature!=g_catalog_context_signature) {war3_catalog_retire();g_catalog_context_signature=signature;}
        error=war3_catalog_from_roots(&before,op->kind,op->rawcode,op->arg0,op->arg1,extra,count);
        if(!error) {
            error=war3_catalog_read_roots(&after);
            if(!error && memcmp(&before,&after,sizeof(before))) error=ERROR_RETRY;
        }
    } __except(EXCEPTION_EXECUTE_HANDLER) {error=GetExceptionCode();}
    if(error) {war3_catalog_retire();op->result=g_catalog_diagnostic;}
    return error;
}
