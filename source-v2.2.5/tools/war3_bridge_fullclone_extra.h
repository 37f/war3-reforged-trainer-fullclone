/* R35 isolated freeze, supplies and fixed point spells. No old ABI changes. */
typedef struct FCR35Row {
    uint64_t unit,full,owner,item;
    uint32_t rawcode,paused,desired,status;float x,y;uint64_t reserved;
} FCR35Row;
typedef struct FCR35Work {
    SelectionWork selection;void *fn[32],*tls;uint64_t (*resolve)(uint64_t);
    uint32_t action,flag,scope,requested,count,changed,error,done;
    uint64_t target,owner;int32_t player;uint32_t rawcode,capacity;int32_t charges;
    float x,y;uint64_t full;FCR35Row rows[4096];
} FCR35Work;
_Static_assert(sizeof(FCR35Row)==64,"R35 row");
_Static_assert(offsetof(FCR35Work,rows)==832,"R35 header");
_Static_assert(sizeof(FCR35Work)==262976,"R35 work");
__declspec(dllexport) const uint32_t fullclone_extra_abi[3]={0x46333501,216,0};
#define F35(i,r,args) ((r (*)args)w->fn[i])
static uint64_t F35Full(FCR35Work*w,uint64_t u){
    uint64_t object=w->resolve(u);return object?*(uint64_t*)(uintptr_t)(object+bridge_profile.object_handle):0;
}
static int F35Identity(FCR35Work*w,FCR35Row*r){
    return w->selection.unit_type_id(r->unit)==r->rawcode && F35Full(w,r->unit)==r->full && F35(0,uint64_t,(uint64_t))(r->unit)==r->owner;
}
static uint32_t F35Order(uint32_t code){
    /* Fixed point-target orders; reference: github.com/WarRaft/Order. */
    return code==0x4155696e?852224:code==0x4148627a?852089:code==0x41486673?852488:code==0x414e7266?852238:0;
}
__declspec(dllexport) uint64_t BridgeFullCloneExtraQuery(void){
    FCR35Work*w=(FCR35Work*)g_dispatch->work;uint64_t group=0;
    if(!w||w->tls!=g_dispatch->tls_value||!w->resolve||w->action<1||w->action>6||w->flag>1||w->scope>2||w->capacity>4096||w->requested>w->capacity||w->count||w->changed||w->error||w->done){if(w)w->error=1000;return 0;}
    __try{__try{
        if(w->action==1){
            uint64_t n=BridgeSelect();
            if(w->selection.error||!w->selection.destroyed){w->error=1004;return 0;}
            if(!n){w->done=1;return 0;}
            w->owner=F35(0,uint64_t,(uint64_t))(w->selection.rows[0].unit);
            w->player=F35(1,int32_t,(uint64_t))(w->owner);
            if(!w->owner||w->player<0||w->player>=28||F35(2,uint64_t,(int32_t))(w->player)!=w->owner){w->error=1237;return 0;}
            group=w->selection.create_group();if(!group){w->error=1008;return 0;}
            __try{
                F35(3,void,(uint64_t,uint64_t,uint64_t))(group,w->owner,0);uint64_t u;uint32_t visited=0;
                while((u=w->selection.first_of_group(group))){
                    if(++visited>100000){w->error=1010;break;}
                    if(!((uint8_t(*)(uint64_t,uint64_t))w->selection.remove_from_group)(group,u)){w->error=1003;break;}
                    uint32_t type=w->selection.unit_type_id(u);if(!type||F35(0,uint64_t,(uint64_t))(u)!=w->owner)continue;
                    float life=FullCloneReal(F35(4,uint32_t,(uint64_t))(u));if(!FullCloneFinite(life)){w->error=1025;break;}
                    if(life<=0.405f||F35(7,uint8_t,(uint64_t))(u))continue;
                    if(!w->flag&&F35(5,uint8_t,(uint64_t,uint64_t))(u,F35(6,uint64_t,(int32_t))(2)))continue;
                    uint32_t hero=F35(5,uint8_t,(uint64_t,uint64_t))(u,F35(6,uint64_t,(int32_t))(0));
                    if((w->scope==1&&!hero)||(w->scope==2&&hero))continue;
                    if(w->count>=w->capacity){w->error=1010;break;}
                    FCR35Row*r=&w->rows[w->count++];r->unit=u;r->rawcode=type;r->owner=w->owner;r->full=F35Full(w,u);
                    if(!r->full){w->error=1237;break;}r->paused=F35(8,uint8_t,(uint64_t))(u);r->status=1;
                }
            }__finally{w->selection.destroy_group(group);}
        }else if(w->action==2){
            w->count=1;FCR35Row*r=&w->rows[0];
            if(w->requested!=1||r->paused>1||r->desired>1){w->error=1000;return 0;}
            if(!F35Identity(w,r)||FullCloneReal(F35(4,uint32_t,(uint64_t))(r->unit))<=0.405f){r->status=2;w->done=1;return 1;}
            if(!FullCloneFinite(FullCloneReal(F35(4,uint32_t,(uint64_t))(r->unit)))){w->error=1025;return 1;}
            uint32_t paused=F35(8,uint8_t,(uint64_t))(r->unit);
            if(paused!=r->paused){r->status=3;w->done=1;return 1;}
            if(paused!=r->desired)F35(9,void,(uint64_t,uint32_t))(r->unit,r->desired);
            if(!F35Identity(w,r)||F35(8,uint8_t,(uint64_t))(r->unit)!=r->desired){w->error=1026;return 1;}
            r->status=1;w->changed=paused!=r->desired;
        }else if(w->action==3){
            if(!w->requested||w->requested>32){w->error=1000;return 0;}
            FCR35Row hero={0};
            if(!w->flag){
                uint64_t n=BridgeSelect();if(n!=1||w->selection.error||!w->selection.destroyed){w->error=1101;return 0;}
                hero.unit=w->selection.rows[0].unit;hero.rawcode=w->selection.rows[0].rawcode;
                hero.owner=F35(0,uint64_t,(uint64_t))(hero.unit);hero.full=F35Full(w,hero.unit);
                if(!hero.full||!F35(5,uint8_t,(uint64_t,uint64_t))(hero.unit,F35(6,uint64_t,(int32_t))(0))||FullCloneReal(F35(4,uint32_t,(uint64_t))(hero.unit))<=0.405f||F35(7,uint8_t,(uint64_t))(hero.unit)){w->error=1101;return 0;}
                int32_t size=F35(16,int32_t,(uint64_t))(hero.unit),free=0;
                if(size<1||size>6){w->error=1102;return 0;}
                for(int32_t k=0;k<size;k++)if(!F35(15,uint64_t,(uint64_t,int32_t))(hero.unit,k))++free;
                if((uint32_t)free<w->requested){w->error=1102;return 0;}
                w->x=FullCloneReal(F35(26,uint32_t,(uint64_t))(hero.unit));w->y=FullCloneReal(F35(27,uint32_t,(uint64_t))(hero.unit));
            }
            if(!FullCloneFinite(w->x)||!FullCloneFinite(w->y)){w->error=1025;return 0;}
            for(uint32_t i=0;i<w->requested;i++)if(!w->rows[i].rawcode||w->rows[i].desired>1000000001u){w->error=1000;return 0;}
            w->count=w->requested;
            for(uint32_t i=0;i<w->requested;i++){
                FCR35Row*r=&w->rows[i];if(!w->flag&&!F35Identity(w,&hero)){w->error=1237;break;}
                r->item=F35(10,uint64_t,(uint32_t,float*,float*))(r->rawcode,&w->x,&w->y);
                if(!r->item||F35(11,uint32_t,(uint64_t))(r->item)!=r->rawcode){w->error=1103;break;}
                if(r->desired){F35(12,void,(uint64_t,int32_t))(r->item,(int32_t)r->desired-1);if(F35(13,int32_t,(uint64_t))(r->item)!=(int32_t)r->desired-1){w->error=1026;break;}}
                if(!w->flag){
                    if(!F35Identity(w,&hero)||!F35(14,uint8_t,(uint64_t,uint64_t))(hero.unit,r->item)){w->error=1104;break;}
                    uint32_t found=0;for(int k=0;k<6;k++)if(F35(15,uint64_t,(uint64_t,int32_t))(hero.unit,k)==r->item)found=1;
                    if(!found){w->error=1104;break;}
                }else{
                    r->x=FullCloneReal(F35(29,uint32_t,(uint64_t))(r->item));r->y=FullCloneReal(F35(30,uint32_t,(uint64_t))(r->item));
                    if(!FullCloneFinite(r->x)||!FullCloneFinite(r->y)){w->error=1026;break;}
                }
                if(F35(11,uint32_t,(uint64_t))(r->item)!=r->rawcode||(r->desired&&F35(13,int32_t,(uint64_t))(r->item)!=(int32_t)r->desired-1)){w->error=1237;break;}r->status=1;++w->changed;
            }
        }else{
            if(!F35Order(w->rawcode)||!FullCloneFinite(w->x)||!FullCloneFinite(w->y)){w->error=1000;return 0;}
            uint64_t caster=w->target,local=w->selection.local_player();
            if(!local){w->error=1001;return 0;}
            if(w->action==4){
                float facing=270.f,mana=100000.f;
                caster=F35(17,uint64_t,(uint64_t,uint32_t,float*,float*,float*))(local,0x68666f6f,&w->x,&w->y,&facing);
                if(!caster){w->error=1021;return 0;}
                /* Return ownership immediately, even if setup faults, so Python
                   can try identity-bound cleanup without repeating creation. */
                w->target=caster;w->owner=local;w->full=F35Full(w,caster);w->count=1;
                if(!w->full){w->error=1237;return 1;}
                F35(31,void,(uint64_t,uint32_t))(caster,0);
                F35(23,void,(uint64_t,uint32_t,uint32_t,uint32_t,uint32_t))(caster,255,255,255,0);
                F35(24,void,(uint64_t,uint32_t))(caster,0);
                if(!F35(19,uint8_t,(uint64_t,uint32_t))(caster,0x416c6f63)||!F35(19,uint8_t,(uint64_t,uint32_t))(caster,w->rawcode)){w->error=1022;return 1;}
                F35(20,void,(uint64_t,int32_t))(caster,100000);
                F35(21,void,(uint64_t,uint64_t,float*))(caster,F35(22,uint64_t,(int32_t))(2),&mana);
                if(F35(28,int32_t,(uint64_t,uint32_t))(caster,w->rawcode)<=0){w->error=1022;return 1;}
            }else{
                FCR35Row r={0};r.unit=caster;r.full=w->full;r.owner=w->owner;r.rawcode=0x68666f6f;
                if(local!=w->owner||!F35Identity(w,&r)){w->error=1237;return 0;}
                w->count=1;
                if(w->action==5){
                    if(F35(28,int32_t,(uint64_t,uint32_t))(caster,w->rawcode)<=0||!F35(25,uint8_t,(uint64_t,uint32_t,float*,float*))(caster,F35Order(w->rawcode),&w->x,&w->y)){w->error=1024;return 1;}
                }else F35(18,void,(uint64_t))(caster);
            }
            w->changed=1;
        }
        w->done=!w->error;
    }__except(EXCEPTION_EXECUTE_HANDLER){w->error=GetExceptionCode();}
    }__finally{
        if(w->action==4&&w->error&&w->target&&w->full){
            __try{
                FCR35Row r={0};r.unit=w->target;r.full=w->full;r.owner=w->owner;r.rawcode=0x68666f6f;
                if(F35Identity(w,&r))F35(18,void,(uint64_t))(w->target);
            }__except(EXCEPTION_EXECUTE_HANDLER){w->charges=-2;}
        }
    }
    return w->count;
}
#undef F35
