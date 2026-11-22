/* R31 owner choice, preserving the author's complete clone implementation.
   Enumeration still uses the real local selection. Only the destination field
   changes after enumeration, before the original transaction's first creation. */
typedef struct FCCloneWork {
    CloneStateWork state;
    uint64_t (*player)(int32_t),(*slot_state)(uint64_t),(*slot_enum)(int32_t);
    uint32_t player_index,error;uint64_t owner;
} FCCloneWork;
_Static_assert(sizeof(FCCloneWork)==176048,"FCCloneWork ABI");
__declspec(dllexport) const uint32_t fullclone_clone_abi[3]={0x46333104,216,176048};
static FCCloneWork *fc_clone_active;
static void (*fc_clone_enum_original)(uint64_t,uint64_t,uint64_t);
static uint64_t fc_clone_local;
static void FCCloneEnumerate(uint64_t group,uint64_t player,uint64_t filter){
    fc_clone_local=player;
    fc_clone_enum_original(group,player,filter);
    fc_clone_active->state.bound.clone.selection.player=fc_clone_active->owner;
}
__declspec(dllexport) uint64_t BridgeFullCloneCloneQuery(void){
    FCCloneWork*w=(FCCloneWork*)g_dispatch->work;uint64_t count=0;
    if(!w || fc_clone_active || !w->player || !w->slot_state || !w->slot_enum ||
       (w->player_index>=24 && w->player_index!=24 && w->player_index!=27)){
        if(w)w->error=1300;return 0;
    }
    __try{
        w->owner=w->player((int32_t)w->player_index);
        if(!w->owner || (w->player_index<24 && w->slot_state(w->owner)!=w->slot_enum(1))){w->error=1168;return 0;}
        fc_clone_active=w;fc_clone_enum_original=w->state.bound.clone.selection.enum_selected;
        w->state.bound.clone.selection.enum_selected=FCCloneEnumerate;fc_clone_local=0;
        count=BridgeCloneStateQuery();
    }__finally{
        if(fc_clone_active==w){
            w->state.bound.clone.selection.enum_selected=fc_clone_enum_original;
            /* The output player is the requested destination, as checked by
               the original clone decoder in this independent operation. */
            fc_clone_active=0;fc_clone_enum_original=0;fc_clone_local=0;
        }
    }
    return count;
}
