/* Apply the existing ability primitives to a captured object, without selecting it. */
typedef struct FCHeroSkillWork {
    BridgeAbilityAddFn add, remove;
    BridgeAbilityLevelSetFn set_level;
    BridgeAbilityLevelGetFn get_level;
    BridgeAbilityLookupFn ability;
    BridgeAbilityIdFn ability_id;
    BridgeAbilityIndexFn ability_index;
    uint32_t (*unit_type)(uint64_t);
    void *tls;
    uint64_t (*resolve)(uint64_t);
    uint64_t object,full,unit;
    uint32_t kind,code,action,prior,level;
    int32_t before,after;
    uint32_t error,done,reserved;
    uint64_t before_handle,after_handle;
} FCHeroSkillWork;
_Static_assert(sizeof(FCHeroSkillWork)==160,"Bound hero skill ABI");
__declspec(dllexport) const uint32_t hero_skill_bound_abi[3]={0x46485301,216,160};

static int FCHeroSkillIdentity(FCHeroSkillWork *w) {
    return w->resolve(w->unit)==w->object &&
        *(uint64_t *)(uintptr_t)(w->object+bridge_profile.object_handle)==w->full &&
        *(uint32_t *)(uintptr_t)(w->object+bridge_profile.object_rawcode)==w->kind &&
        w->unit_type(w->unit)==w->kind;
}

__declspec(dllexport) uint64_t BridgeHeroSkillBoundQuery(void) {
    FCHeroSkillWork *w=(FCHeroSkillWork *)g_dispatch->work;
    if(!w || w->tls!=g_dispatch->tls_value || !w->resolve || !w->object ||
       !w->full || !w->unit || !w->kind || !w->code || w->action>3 ||
       w->prior>100000 || w->level>100000 || w->error || w->done || w->reserved ||
       w->before || w->after || w->before_handle || w->after_handle ||
       (w->action==0 && (w->prior || w->level)) ||
       (w->action==1 && (w->prior || !w->level)) ||
       (w->action==2 && (!w->prior || w->level)) ||
       (w->action==3 && (!w->prior || !w->level))){
        if(w)w->error=1000;
        return 0;
    }
    __try {
        if(!FCHeroSkillIdentity(w)){w->error=1237;return 0;}
        int error=0;
        w->before=BridgeObservedLevel(w->get_level,w->unit,w->code);
        w->before_handle=BridgeFindUnitAbility(w->ability,w->ability_index,w->ability_id,w->unit,w->code,&error);
        if(error || w->before<0){w->error=error ? (uint32_t)error : 23;return 0;}
        if(w->action){
            if(w->before!=(int32_t)w->prior || (!w->before && w->before_handle)){
                w->error=24;return 0;
            }
            if(w->action==1){
                BridgeAbilityWitness witness={0};
                error=BridgeEnsureUnitAbilityNative(w->ability,w->ability_index,w->ability_id,
                    w->add,w->get_level,w->set_level,w->unit,w->code,(int32_t)w->level,&witness);
                if(error){w->error=(uint32_t)error;return 0;}
            }else if(w->action==2){
                if(!BridgeObservedRemoveAbility(w->remove,w->unit,w->code)){w->error=27;return 0;}
            }else if(BridgeNativeSetAbilityLevelChecked(w->set_level,w->get_level,w->unit,w->code,
                       (int32_t)w->level)!=(int32_t)w->level){
                w->error=26;return 0;
            }
        }
        if(!FCHeroSkillIdentity(w)){w->error=1237;return 0;}
        w->after=BridgeObservedLevel(w->get_level,w->unit,w->code);
        w->after_handle=BridgeFindUnitAbility(w->ability,w->ability_index,w->ability_id,w->unit,w->code,&error);
        if(error){w->error=(uint32_t)error;return 0;}
        w->done=1;
    } __except(BridgeExceptionFilter(GetExceptionInformation())) {w->error=GetExceptionCode();}
    return w->done;
}
