/* R31: use the author's current indexed registry to validate a bounded snapshot.
   The converter is derived from the live FirstOfGroup tail call, not an old RVA. */
typedef struct FCItemRow {
    uint64_t full,object;uint32_t rawcode,reserved;uint64_t native;
    uint32_t before_x,before_y,after_x,after_y,charges,eligible,moved,error;
} FCItemRow;
typedef struct FCItemsWork {
    uint64_t (*convert)(uint64_t,uint8_t);
    uint32_t (*type_id)(uint64_t);
    uint8_t (*owned)(uint64_t),(*visible)(uint64_t);
    uint32_t (*life)(uint64_t);
    void (*move)(uint64_t,float*,float*);
    uint32_t (*x)(uint64_t),(*y)(uint64_t);
    int32_t (*charges)(uint64_t);
    uint64_t base;void *tls;float target_x,target_y;
    uint32_t count,preview,error,completed,changed,visited;uint64_t item_tag;
    FCItemRow rows[];
} FCItemsWork;
_Static_assert(sizeof(FCItemRow)==64,"FCItemRow ABI");
_Static_assert(sizeof(FCItemsWork)==128,"FCItemsWork ABI");
__declspec(dllexport) const uint32_t fullclone_items_abi[3]={0x46333102,216,0};
static int FCItemIdentity(FCItemsWork*w,FCItemRow*r){
    uint64_t owner=BridgeProfileResolveOwner(w->base,r->full,1);
    return owner && *(uint64_t*)(uintptr_t)(owner+0x18)==w->item_tag &&
        *(uint64_t*)(uintptr_t)(owner+bridge_profile.owner_data)==r->object &&
        *(uint64_t*)(uintptr_t)(r->object+bridge_profile.object_handle)==r->full &&
        *(uint32_t*)(uintptr_t)(r->object+bridge_profile.object_rawcode)==r->rawcode;
}
__declspec(dllexport) uint64_t BridgeFullCloneItemsQuery(void){
    FCItemsWork*w=(FCItemsWork*)g_dispatch->work;uint64_t start=GetTickCount64();
    if(!w || w->tls!=g_dispatch->tls_value || w->count>100000 || w->preview>1 ||
       !w->convert || !w->type_id || !w->owned || !w->visible || !w->life ||
       !w->move || !w->x || !w->y || !w->charges){if(w)w->error=1100;return 0;}
    __try{
        /* Finish capturing eligibility before the first move. No new map item
           created by a later trigger can enter this request's fixed set. */
        for(uint32_t i=0;i<w->count;i++){
            FCItemRow*r=&w->rows[i];union{uint32_t bits;float value;}life;
            if(GetTickCount64()-start>5000){w->error=1460;return w->changed;}
            if(!FCItemIdentity(w,r))continue;
            uint64_t h=w->convert(r->object,1);r->native=h;
            if(!h || w->type_id(h)!=r->rawcode || !FCItemIdentity(w,r)){w->error=1101;return w->changed;}
            ++w->visited;life.bits=w->life(h);
            if(w->owned(h) || !w->visible(h) || !(life.value>0.405f))continue;
            r->eligible=1;r->before_x=w->x(h);r->before_y=w->y(h);r->charges=(uint32_t)w->charges(h);
        }
        for(uint32_t i=0;i<w->count;i++){
            FCItemRow*r=&w->rows[i];uint64_t h=r->native;
            if(!r->eligible)continue;
            if(GetTickCount64()-start>5000){w->error=1460;return w->changed;}
            if(!FCItemIdentity(w,r) || w->type_id(h)!=r->rawcode || w->owned(h) || !w->visible(h))continue;
            if(!w->preview){
                w->move(h,&w->target_x,&w->target_y);r->moved=1;++w->changed;
                union{uint32_t bits;float value;}x,y;
                x.bits=w->x(h);y.bits=w->y(h);r->after_x=x.bits;r->after_y=y.bits;
                if(!FCItemIdentity(w,r) || w->type_id(h)!=r->rawcode || (uint32_t)w->charges(h)!=r->charges ||
                    !(x.value-w->target_x<256.f && w->target_x-x.value<256.f &&
                      y.value-w->target_y<256.f && w->target_y-y.value<256.f)){w->error=1102;return w->changed;}
            }else ++w->changed;
        }
        w->completed=1;return w->changed;
    }__except(EXCEPTION_EXECUTE_HANDLER){w->error=GetExceptionCode();return w->changed;}
}
