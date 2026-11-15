/* R31 isolated additions. Existing bridge transactions/readers stay intact.
   All public handlers come from the current native table, never old RVAs. */
#include <stddef.h>

typedef struct FullCloneRow {
    uint64_t unit,created,owner;
    uint32_t rawcode;
    int32_t level,a,b,c,team;
} FullCloneRow;
typedef struct FullCloneWork {
    SelectionWork selection;
    void *fn[64];
    void *tls;
    uint32_t action;int32_t value;uint32_t rawcode;float x,y;
    uint32_t count,error,completed,changed;
    uint64_t target,expected_owner;
    uint32_t verified_faults,last_fault;uint8_t pad[24];
    FullCloneRow rows[24];
    uint32_t matrix[560];
    int32_t peer_teams[28];
} FullCloneWork;
_Static_assert(sizeof(FullCloneRow)==48,"FullCloneRow ABI");
_Static_assert(offsetof(FullCloneWork,rows)==1088,"FullClone header ABI");
_Static_assert(sizeof(FullCloneWork)==4592,"FullCloneWork ABI");
__declspec(dllexport) const uint32_t fullclone_abi[3]={0x46333101,216,4592};

#define FC_FN(i,result,args) ((result (*)args)w->fn[i])
#define FC_OWNER(u) FC_FN(0,uint64_t,(uint64_t))(u)
#define FC_PLAYER(i) FC_FN(2,uint64_t,(int32_t))(i)
#define FC_ID(p) FC_FN(1,int32_t,(uint64_t))(p)
#define FC_TEAM(p) FC_FN(3,int32_t,(uint64_t))(p)
#define FC_ALLIANCE(i) FC_FN(25,uint64_t,(int32_t))(i)
#define FC_GET(a,b,i) FC_FN(26,uint8_t,(uint64_t,uint64_t,uint64_t))(a,b,FC_ALLIANCE(i))
#define FC_SET(a,b,i,v) FC_FN(27,void,(uint64_t,uint64_t,uint64_t,uint32_t))(a,b,FC_ALLIANCE(i),v)

static int FullClonePlayerExists(FullCloneWork*w,uint64_t p,int32_t id) {
    return p && (id==24 || id==27 || (id>=0 && id<24 &&
        FC_FN(4,uint64_t,(uint64_t))(p)==FC_FN(5,uint64_t,(int32_t))(1)));
}

/* A setter can fault after its side effect. Skip unchanged flags and accept
   the known access-fault case only when the requested flag actually changed
   and its independent getter confirms it. Never replay the setter. */
static uint32_t FullCloneSetAllianceChecked(FullCloneWork*w,uint64_t a,uint64_t b,uint32_t flag,uint32_t value) {
    uint32_t fault=0;
    if(FC_GET(a,b,flag)==value)return 0;
    __try{FC_SET(a,b,flag,value);}
    __except(EXCEPTION_EXECUTE_HANDLER){fault=GetExceptionCode();}
    if(FC_GET(a,b,flag)!=value)return fault?fault:1006;
    if(fault){
        if(fault!=EXCEPTION_ACCESS_VIOLATION)return fault;
        ++w->verified_faults;w->last_fault=fault;
    }
    return 0;
}

static float FullCloneReal(uint32_t bits) {
    union{uint32_t bits;float value;}r;r.bits=bits;return r.value;
}
static int FullCloneFinite(float value) {
    union{uint32_t bits;float value;}r;r.value=value;
    return (r.bits&0x7f800000u)!=0x7f800000u;
}

/* R30 replacement contract, resolved through current signatures. Do not
   remove the old instance until every transferable field has been checked. */
static uint32_t FullCloneReplace(FullCloneWork*w,FullCloneRow*r) {
    uint64_t u=r->unit,v=0,moved[6]={0};uint32_t n=0,error=0,hidden=0,commit=0;
    float x,y,f,life[4];int32_t gold;
    __try{
        x=FullCloneReal(FC_FN(29,uint32_t,(uint64_t))(u));
        y=FullCloneReal(FC_FN(30,uint32_t,(uint64_t))(u));
        f=FullCloneReal(FC_FN(31,uint32_t,(uint64_t))(u));
        if(!FullCloneFinite(x)||!FullCloneFinite(y)||!FullCloneFinite(f)){error=1025;__leave;}
        for(int k=0;k<4;k++){
            life[k]=FullCloneReal(FC_FN(7,uint32_t,(uint64_t,uint64_t))(u,FC_FN(9,uint64_t,(int32_t))(k)));
            if(!FullCloneFinite(life[k])){error=1025;__leave;}
        }
        gold=FC_FN(49,int32_t,(uint64_t))(u);
        hidden=FC_FN(54,uint8_t,(uint64_t))(u);
        FC_FN(55,void,(uint64_t,uint32_t))(u,0);
        v=w->rawcode==0x75676f6c
            ?FC_FN(46,uint64_t,(uint64_t,float*,float*,float*))(r->owner,&x,&y,&f)
            :FC_FN(32,uint64_t,(uint64_t,uint32_t,float*,float*,float*))(r->owner,w->rawcode,&x,&y,&f);
        if(!v||w->selection.unit_type_id(v)!=w->rawcode||FC_OWNER(v)!=r->owner){error=1017;__leave;}
        for(int k=0;k<=2;k+=2){
            if(life[k+1]<=0.f)continue;
            float maximum=FullCloneReal(FC_FN(7,uint32_t,(uint64_t,uint64_t))(v,FC_FN(9,uint64_t,(int32_t))(k+1)));
            if(!FullCloneFinite(maximum)||maximum<0.f||(k==0&&maximum==0.f)){error=1025;__leave;}
            float value=life[k]/life[k+1]*maximum;
            FC_FN(8,void,(uint64_t,uint64_t,float*))(v,FC_FN(9,uint64_t,(int32_t))(k),&value);
            float after=FullCloneReal(FC_FN(7,uint32_t,(uint64_t,uint64_t))(v,FC_FN(9,uint64_t,(int32_t))(k)));
            if(!FullCloneFinite(after)){error=1026;__leave;}
        }
        FC_FN(50,void,(uint64_t,int32_t))(v,gold);
        if(FC_FN(49,int32_t,(uint64_t))(v)!=gold){error=1026;__leave;}
        uint64_t hero=FC_FN(15,uint64_t,(int32_t))(0);
        if(FC_FN(14,uint8_t,(uint64_t,uint64_t))(u,hero)&&FC_FN(14,uint8_t,(uint64_t,uint64_t))(v,hero)){
            int32_t xp=FC_FN(47,int32_t,(uint64_t))(u);
            FC_FN(48,void,(uint64_t,int32_t,uint32_t))(v,xp,0);
            if(FC_FN(47,int32_t,(uint64_t))(v)!=xp){error=1026;__leave;}
            for(int32_t slot=0;slot<6;slot++){
                uint64_t item=FC_FN(51,uint64_t,(uint64_t,int32_t))(u,slot);
                if(!item)continue;
                moved[n++]=item;
                FC_FN(52,void,(uint64_t,uint64_t))(u,item);
                if(!FC_FN(53,uint8_t,(uint64_t,uint64_t))(v,item)){error=1026;__leave;}
            }
            if(error)__leave;
        }
        /* Removal may run map callbacks. Once begun, do not guess rollback
           or delete the successfully prepared replacement on an exception. */
        commit=1;r->created=v;
        if(hidden)FC_FN(56,void,(uint64_t))(u);
        FC_FN(33,void,(uint64_t))(u);
        r->b=(int32_t)n;
    }__except(EXCEPTION_EXECUTE_HANDLER){error=GetExceptionCode();}
    if(error&&!commit){
        __try{
            for(uint32_t i=0;i<n;i++){uint64_t item=moved[i];FC_FN(52,void,(uint64_t,uint64_t))(v,item);FC_FN(53,uint8_t,(uint64_t,uint64_t))(u,item);}
            if(v)FC_FN(33,void,(uint64_t))(v);
            FC_FN(55,void,(uint64_t,uint32_t))(u,!hidden);
        }__except(EXCEPTION_EXECUTE_HANDLER){/* Keep the original failure. */}
    }
    return error;
}

__declspec(dllexport) uint64_t BridgeFullCloneQuery(void) {
    FullCloneWork*w=(FullCloneWork*)g_dispatch->work;
    uint64_t count=0,local=0,owner=0;
    if(!w || w->tls!=g_dispatch->tls_value || w->action>20 || w->action==13 || w->count>24) {
        if(w)w->error=1000;return 0;
    }
    __try {
        local=w->selection.local_player();
        if(!local){w->error=1001;return 0;}
        if(w->action>=16 && w->action<=18){
            uint64_t caster=w->target,object=0;float facing=270.f,mana=100000.f;
            if(!w->fn[63]){w->error=1020;return 0;}
            if(w->action==16){
                caster=FC_FN(32,uint64_t,(uint64_t,uint32_t,float*,float*,float*))(local,0x68666f6f,&w->x,&w->y,&facing);
                if(!caster){w->error=1021;return 0;}
                /* Hidden/unselectable carrier, no timed-life bar or footman is
                   presented to the user. Real AUin owns the meteor and stun. */
                FC_FN(41,void,(uint64_t,uint32_t,uint32_t,uint32_t,uint32_t))(caster,255,255,255,0);
                FC_FN(37,void,(uint64_t,uint32_t))(caster,0);
                if(!FC_FN(39,uint8_t,(uint64_t,uint32_t))(caster,0x416c6f63) ||
                   !FC_FN(39,uint8_t,(uint64_t,uint32_t))(caster,0x4155696e)){
                    FC_FN(33,void,(uint64_t))(caster);w->error=1022;return 0;
                }
                FC_FN(40,void,(uint64_t,int32_t))(caster,100000);
                FC_FN(8,void,(uint64_t,uint64_t,float*))(caster,FC_FN(9,uint64_t,(int32_t))(2),&mana);
                object=FC_FN(63,uint64_t,(uint64_t))(caster);
                if(!object){FC_FN(33,void,(uint64_t))(caster);w->error=1023;return 0;}
                w->rows[0].unit=caster;w->rows[0].created=*(uint64_t*)(uintptr_t)(object+bridge_profile.object_handle);
                w->rows[0].owner=local;w->rows[0].rawcode=0x68666f6f;w->count=1;
            }else{
                object=FC_FN(63,uint64_t,(uint64_t))(caster);
                if(!object || *(uint64_t*)(uintptr_t)(object+bridge_profile.object_handle)!=w->expected_owner ||
                    w->selection.unit_type_id(caster)!=0x68666f6f || FC_OWNER(caster)!=local){w->error=1237;return 0;}
                if(w->action==17){
                    if(!FC_FN(42,uint8_t,(uint64_t,uint32_t,float*,float*))(caster,852224,&w->x,&w->y)){w->error=1024;return 0;}
                }else FC_FN(33,void,(uint64_t))(caster);
            }
            w->changed=1;w->completed=1;return 1;
        }
        if(w->action==15){
            float time=0.35f;
            FC_FN(36,void,(float*,float*,float*))(&w->x,&w->y,&time);
            w->changed=1;w->completed=1;return 1;
        }
        if(w->action==11){
            uint64_t p=w->value==-1?local:FC_PLAYER(w->value);float facing=0.;
            if(!FullClonePlayerExists(w,p,w->value==-1?0:w->value)){w->error=1168;return 0;}
            uint64_t u=FC_FN(32,uint64_t,(uint64_t,uint32_t,float*,float*,float*))(p,w->rawcode,&w->x,&w->y,&facing);
            if(!u || w->selection.unit_type_id(u)!=w->rawcode || FC_OWNER(u)!=p){w->error=1002;return 0;}
            w->rows[0].created=u;w->rows[0].unit=u;w->rows[0].owner=p;w->rows[0].rawcode=w->rawcode;
            w->count=1;w->changed=1;w->completed=1;return 1;
        }
        /* R31.12 explicit-player diplomacy. It does not select a game unit or
           alter the existing selected-owner actions 8/9. */
        uint32_t direct=w->action==19 || w->action==20;
        if(direct){
            if(w->target>=28 || w->count){w->error=1000;return 0;}
            owner=FC_PLAYER((int32_t)w->target);
            if(!owner || FC_ID(owner)!=(int32_t)w->target || (w->expected_owner && owner!=w->expected_owner)){w->error=1237;return 0;}
            if(w->action==20 && (!w->expected_owner || !FullClonePlayerExists(w,owner,(int32_t)w->target))){w->error=1168;return 0;}
            count=1;w->count=1;w->rows[0].b=FC_ID(local);
            /* Control is outside this entry's scope, including requests that
               bypass the Python facade. Validate before the first setter. */
            if(w->action==20){
                for(uint32_t p=0;p<28;p++){
                    uint64_t peer=FC_PLAYER(p);if(!peer){w->error=1005;return 0;}
                    for(uint32_t a=0;a<10;a++){
                        uint32_t k=p*20+a;
                        if(w->matrix[k]>1 || w->matrix[k+10]>1){w->error=1000;return 0;}
                        if((a==6 || a==7) && (w->matrix[k]!=FC_GET(owner,peer,a) || w->matrix[k+10]!=FC_GET(peer,owner,a))){w->error=1007;return 0;}
                    }
                }
            }
        }else if(w->count){
            /* Explicit handles are emitted by the author's clone transaction.
               Recheck type before every extension; never infer a handle from rawcode. */
            count=w->count;
            for(uint32_t i=0;i<count;i++){
                uint64_t u=w->rows[i].unit;uint32_t code=w->selection.unit_type_id(u);
                if(!u || !code){w->error=1003;return 0;}
                w->rows[i].rawcode=code;w->rows[i].level=w->selection.hero_level(u);
            }
        }else{
            count=BridgeSelect();
            if(w->selection.error || !w->selection.destroyed){w->error=1004;return 0;}
            w->count=(uint32_t)count;
            for(uint32_t i=0;i<count;i++){
                w->rows[i].unit=w->selection.rows[i].unit;
                w->rows[i].rawcode=w->selection.rows[i].rawcode;
                w->rows[i].level=w->selection.rows[i].level;
            }
        }
        if(!count){w->completed=1;return 0;}
        if(w->fn[0] && !direct){
            owner=FC_OWNER(w->rows[0].unit);
            if(w->expected_owner && owner!=w->expected_owner){w->error=1237;return count;}
        }
        if(w->action==8 || w->action==9 || direct){
            uint32_t write=w->action==9 || w->action==20;
            if(w->action==8 && w->target==1){
                if(w->value<0 || w->value>=28){w->error=1000;return count;}
                owner=FC_PLAYER(w->value);
            }
            w->rows[0].owner=owner;w->rows[0].a=FC_ID(owner);w->rows[0].team=FC_TEAM(owner);
            /* Keep native team index unchanged. As in R12-R30 this applies a
               diplomacy template; saved original relations are restored exactly. */
            for(uint32_t p=0;p<28;p++){
                uint64_t peer=FC_PLAYER(p);
                if(!peer){w->error=1005;return count;}
                w->peer_teams[p]=FC_TEAM(peer);
                for(uint32_t a=0;a<10;a++){
                    uint32_t k=p*20+a;
                    if(write && peer!=owner){
                        w->error=FullCloneSetAllianceChecked(w,owner,peer,a,w->matrix[k]);
                        if(w->error)return count;
                        w->error=FullCloneSetAllianceChecked(w,peer,owner,a,w->matrix[k+10]);
                        if(w->error)return count;
                    }
                    uint32_t f=FC_GET(owner,peer,a),b=FC_GET(peer,owner,a);
                    if(write && peer!=owner && (f!=w->matrix[k] || b!=w->matrix[k+10])){w->error=1006;return count;}
                    w->matrix[k]=f;w->matrix[k+10]=b;
                }
            }
            if(write){
                /* Later flag setters can affect earlier flags. Confirm the
                   entire final matrix, not just each intermediate write. */
                for(uint32_t p=0;p<28;p++){
                    uint64_t peer=FC_PLAYER(p);if(peer==owner)continue;
                    for(uint32_t a=0;a<10;a++){
                        uint32_t k=p*20+a;
                        if(FC_GET(owner,peer,a)!=w->matrix[k] || FC_GET(peer,owner,a)!=w->matrix[k+10]){w->error=1006;return count;}
                    }
                }
            }
            w->changed=write;w->completed=1;return count;
        }
        if(w->action==10){
            w->rows[0].owner=owner;w->rows[0].a=FC_ID(owner);
            if(owner==local){w->completed=1;return count;}
            w->rows[0].b=FC_GET(owner,local,6);w->rows[0].c=FC_GET(owner,local,7);
            if(w->value>=0){
                w->error=FullCloneSetAllianceChecked(w,owner,local,6,w->value&1);
                if(w->error)return count;
                w->error=FullCloneSetAllianceChecked(w,owner,local,7,(w->value>>1)&1);
                if(w->error)return count;
                if(FC_GET(owner,local,6)!=(uint32_t)(w->value&1) || FC_GET(owner,local,7)!=(uint32_t)((w->value>>1)&1)){w->error=1007;return count;}
                w->changed=1;
            }
            w->completed=1;return count;
        }
        if(w->action==5){
            uint64_t g=w->selection.create_group(),u=0;uint32_t seen=0;
            if(!g){w->error=1008;return count;}
            __try{
                FC_FN(13,void,(uint64_t,uint64_t,uint64_t))(g,owner,0);
                while((u=w->selection.first_of_group(g)) && ++seen<=100000){
                    w->selection.remove_from_group(g,u);
                    union{uint32_t bits;float value;} life;
                    life.bits=FC_FN(17,uint32_t,(uint64_t))(u);
                    if(FC_FN(14,uint8_t,(uint64_t,uint64_t))(u,FC_FN(15,uint64_t,(int32_t))(0)) && life.value<=0.405f){
                        if(!FC_FN(16,uint8_t,(uint64_t,float*,float*,uint32_t))(u,&w->x,&w->y,1)){w->error=1009;break;}
                        ++w->changed;
                    }
                }
                if(seen>100000)w->error=1010;
            }__finally{w->selection.destroy_group(g);}
            w->completed=!w->error;return count;
        }
        for(uint32_t i=0;i<count;i++){
            FullCloneRow*r=&w->rows[i];uint64_t u=r->unit;
            if(w->selection.unit_type_id(u)!=r->rawcode){w->error=1237;return count;}
            if(w->fn[0]){
                r->owner=FC_OWNER(u);
                if(w->fn[1])r->a=FC_ID(r->owner);
                if(w->fn[3])r->team=FC_TEAM(r->owner);
            }
            if(w->action==0)continue;
            if(w->action==1){
                uint64_t p=w->value==-1?local:FC_PLAYER(w->value);
                if(!FullClonePlayerExists(w,p,w->value==-1?0:w->value)){w->error=1168;return count;}
                FC_FN(6,void,(uint64_t,uint64_t,uint32_t))(u,p,1);
                if(FC_OWNER(u)!=p){w->error=1011;return count;}
                ++w->changed;
            }else if(w->action==2){
                for(int k=0;k<=2;k+=2){
                    uint64_t maximum=FC_FN(9,uint64_t,(int32_t))(k+1),state=FC_FN(9,uint64_t,(int32_t))(k);
                    union{uint32_t bits;float value;} v,after;
                    v.bits=FC_FN(7,uint32_t,(uint64_t,uint64_t))(u,maximum);
                    if(!(v.value>0.f))continue;
                    FC_FN(8,void,(uint64_t,uint64_t,float*))(u,state,&v.value);
                    after.bits=FC_FN(7,uint32_t,(uint64_t,uint64_t))(u,state);
                    if(after.value+0.01f<v.value){w->error=1012;return count;}
                }++w->changed;
            }else if(w->action==3 || w->action==4){
                uint64_t color=FC_FN(10,uint64_t,(int32_t))(w->value);
                if(w->action==3)FC_FN(11,void,(uint64_t,uint64_t))(u,color);
                else FC_FN(12,void,(uint64_t,uint64_t))(r->owner,color);
                ++w->changed;
            }else if(w->action==6 && r->level>0){
                int32_t target=w->value?w->value:r->level+1;
                if(target>100000){w->error=1013;return count;}
                uint8_t xp=FC_FN(44,uint8_t,(uint64_t))(u);uint32_t operation_error=0;
                __try{
                    if(xp)FC_FN(43,void,(uint64_t,uint32_t))(u,0);
                    FC_FN(24,void,(uint64_t,int32_t,uint32_t))(u,target,1);
                }__except(EXCEPTION_EXECUTE_HANDLER){operation_error=GetExceptionCode();}
                if(xp){
                    __try{FC_FN(43,void,(uint64_t,uint32_t))(u,1);}
                    __except(EXCEPTION_EXECUTE_HANDLER){operation_error=GetExceptionCode();}
                }
                if(w->selection.hero_level(u)!=target || FC_FN(44,uint8_t,(uint64_t))(u)!=xp){w->error=operation_error?operation_error:1014;return count;}
                r->level=target;++w->changed;
            }else if(w->action==7 && r->level>0){
                int32_t values[3];
                for(int k=0;k<3;k++){
                    int32_t old=FC_FN(18+k,int32_t,(uint64_t,uint32_t))(u,0);
                    if(old<0 || old>999999998){w->error=1015;return count;}
                    values[k]=w->value<0?old+2:w->value;
                }
                for(int k=0;k<3;k++){
                    FC_FN(21+k,void,(uint64_t,int32_t,uint32_t))(u,values[k],1);
                    if(FC_FN(18+k,int32_t,(uint64_t,uint32_t))(u,0)!=values[k]){w->error=1016;return count;}
                }
                r->a=values[0];r->b=values[1];r->c=values[2];++w->changed;
            }else if(w->action==12){
                w->error=FullCloneReplace(w,r);if(w->error)return count;++w->changed;
            }else if(w->action==14){FC_FN(37,void,(uint64_t,uint32_t))(u,w->value!=0);++w->changed;}
        }
        w->completed=1;return count;
    }__except(EXCEPTION_EXECUTE_HANDLER){w->error=GetExceptionCode();return count;}
}
#undef FC_FN
#undef FC_OWNER
#undef FC_PLAYER
#undef FC_ID
#undef FC_TEAM
#undef FC_ALLIANCE
#undef FC_GET
#undef FC_SET
