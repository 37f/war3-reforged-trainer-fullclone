/* R34 independent operation: never changes the old selection/heal entries. */
typedef struct FCArmyWork {
    SelectionWork selection;
    void *fn[11],*tls;
    uint32_t mode,error,completed,changed,eligible,visited,skipped_dead,skipped_hidden;
    uint64_t owner;int32_t player;uint32_t attempted;
    uint64_t reserved[2];
} FCArmyWork;
_Static_assert(offsetof(FCArmyWork,tls)==568,"Army TLS ABI");
_Static_assert(offsetof(FCArmyWork,owner)==608,"Army owner ABI");
_Static_assert(sizeof(FCArmyWork)==640,"Army work ABI");
__declspec(dllexport) const uint32_t fullclone_army_abi[3]={0x46333401,216,640};
#define FCA_FN(i,result,args) ((result (*)args)w->fn[i])

static int FCArmyMatches(FCArmyWork*w,uint64_t unit,uint32_t rawcode) {
    return w->selection.unit_type_id(unit)==rawcode && FCA_FN(0,uint64_t,(uint64_t))(unit)==w->owner;
}

__declspec(dllexport) uint64_t BridgeFullCloneArmyQuery(void) {
    FCArmyWork*w=(FCArmyWork*)g_dispatch->work;uint64_t group=0;
    if(!w || w->tls!=g_dispatch->tls_value || w->mode>2 || w->error || w->completed ||
       w->changed || w->eligible || w->visited || w->skipped_dead || w->skipped_hidden ||
       w->owner || w->player!=-1 || w->attempted || w->reserved[0] || w->reserved[1]) {
        if(w)w->error=1000;return 0;
    }
    __try {
        uint64_t selected=BridgeSelect();
        if(w->selection.error || !w->selection.destroyed){w->error=1004;return 0;}
        if(!selected){w->completed=1;return 0;}
        uint64_t source=w->selection.rows[0].unit;
        w->owner=FCA_FN(0,uint64_t,(uint64_t))(source);
        w->player=FCA_FN(1,int32_t,(uint64_t))(w->owner);
        if(!w->owner || w->player<0 || w->player>=28 || FCA_FN(2,uint64_t,(int32_t))(w->player)!=w->owner){w->error=1237;return 0;}
        group=w->selection.create_group();
        if(!group){w->error=1008;return 0;}
        __try {
            FCA_FN(3,void,(uint64_t,uint64_t,uint64_t))(group,w->owner,0);
            uint64_t unit=0;
            while((unit=w->selection.first_of_group(group))) {
                if(w->visited>=100000){w->error=1010;break;}
                ++w->visited;
                if(!((uint8_t (*)(uint64_t,uint64_t))w->selection.remove_from_group)(group,unit)){w->error=1003;break;}
                uint32_t rawcode=w->selection.unit_type_id(unit);
                if(!rawcode || FCA_FN(0,uint64_t,(uint64_t))(unit)!=w->owner)continue;
                float life=FullCloneReal(FCA_FN(7,uint32_t,(uint64_t))(unit));
                if(!FullCloneFinite(life)){w->error=1025;break;}
                if(life<=0.405f){++w->skipped_dead;continue;}
                if(FCA_FN(10,uint8_t,(uint64_t))(unit)){++w->skipped_hidden;continue;}
                if(w->mode){
                    uint8_t hero=FCA_FN(8,uint8_t,(uint64_t,uint64_t))(unit,FCA_FN(9,uint64_t,(int32_t))(0));
                    if((w->mode==1&&!hero)||(w->mode==2&&hero))continue;
                }
                float values[4];
                for(int k=0;k<4;k++)values[k]=FullCloneReal(FCA_FN(4,uint32_t,(uint64_t,uint64_t))(unit,FCA_FN(6,uint64_t,(int32_t))(k)));
                if(!FullCloneFinite(values[0])||!FullCloneFinite(values[1])||!FullCloneFinite(values[2])||!FullCloneFinite(values[3])||values[1]<=0.405f||values[3]<0.f){w->error=1025;break;}
                ++w->eligible;uint32_t touched=0;
                for(int k=0;k<=2;k+=2){
                    if(values[k+1]<=0.f || values[k]==values[k+1])continue;
                    if(!FCArmyMatches(w,unit,rawcode)){w->error=1237;break;}
                    if(!touched){touched=1;++w->attempted;}
                    uint64_t state=FCA_FN(6,uint64_t,(int32_t))(k),maximum=FCA_FN(6,uint64_t,(int32_t))(k+1);
                    FCA_FN(5,void,(uint64_t,uint64_t,float*))(unit,state,&values[k+1]);
                    /* Setters can run map callbacks. Do not continue to mana
                       after removal, ownership change, death or max changes. */
                    if(!FCArmyMatches(w,unit,rawcode)){w->error=1237;break;}
                    float alive=FullCloneReal(FCA_FN(7,uint32_t,(uint64_t))(unit));
                    float after=FullCloneReal(FCA_FN(4,uint32_t,(uint64_t,uint64_t))(unit,state));
                    float max_after=FullCloneReal(FCA_FN(4,uint32_t,(uint64_t,uint64_t))(unit,maximum));
                    if(!FullCloneFinite(alive)||alive<=0.405f||!FullCloneFinite(after)||max_after!=values[k+1]||after+0.01f<values[k+1]||after>values[k+1]+0.01f){w->error=1026;break;}
                }
                if(w->error)break;
                if(touched)++w->changed;
            }
        } __finally {w->selection.destroy_group(group);group=0;}
        w->completed=!w->error;
    } __except(EXCEPTION_EXECUTE_HANDLER) {w->error=GetExceptionCode();}
    return w->changed;
}
