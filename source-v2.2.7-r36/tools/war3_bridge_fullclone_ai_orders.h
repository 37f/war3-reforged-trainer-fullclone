/* Stock economy and target spells. Orders leave costs and target validation to
   Warcraft III. Standard order IDs follow https://github.com/WarRaft/Order. */
#define FC_AI_CODE(a,b,c,d) (((uint32_t)(a)<<24)|((uint32_t)(b)<<16)|((uint32_t)(c)<<8)|(uint32_t)(d))
#define FC_AI_ID(code) FC_AI_CODE((code)[0],(code)[1],(code)[2],(code)[3])

typedef struct FCAIWorker {
    uint32_t unit,mine,harvest,supply,build_ability,halls[3];
    uint16_t gold,lumber;
    uint8_t can_cut,blight;
} FCAIWorker;

static const FCAIWorker FCAIWorkers[]={
        {FC_AI_CODE('h','p','e','a'),FC_AI_CODE('n','g','o','l'),852018,FC_AI_CODE('h','h','o','u'),
         FC_AI_CODE('A','H','b','u'),{FC_AI_CODE('h','t','o','w'),FC_AI_CODE('h','k','e','e'),FC_AI_CODE('h','c','a','s')},80,20,1,0},
        {FC_AI_CODE('o','p','e','o'),FC_AI_CODE('n','g','o','l'),852018,FC_AI_CODE('o','t','r','b'),
         FC_AI_CODE('A','O','b','u'),{FC_AI_CODE('o','g','r','e'),FC_AI_CODE('o','s','t','r'),FC_AI_CODE('o','f','r','t')},160,40,1,0},
        {FC_AI_CODE('u','a','c','o'),FC_AI_CODE('u','g','o','l'),851971,FC_AI_CODE('u','z','i','g'),
         FC_AI_CODE('A','U','b','u'),{FC_AI_CODE('u','n','p','l'),FC_AI_CODE('u','n','p','1'),FC_AI_CODE('u','n','p','2')},150,50,0,1},
        {FC_AI_CODE('e','w','s','p'),FC_AI_CODE('e','g','o','l'),851971,FC_AI_CODE('e','m','o','w'),
         FC_AI_CODE('A','E','b','u'),{FC_AI_CODE('e','t','o','l'),FC_AI_CODE('e','t','o','a'),FC_AI_CODE('e','t','o','e')},180,40,1,0},
        {FC_AI_CODE('u','g','h','o'),0,0,0,0,{0,0,0},0,0,1,0}
};

static const FCAIWorker *FCAIWorkerType(FCLocalAIWork *w,uint64_t unit,uint64_t worker_type) {
    uint32_t code=w->selection.unit_type_id(unit);
    for(uint32_t i=0;i<sizeof(FCAIWorkers)/sizeof(FCAIWorkers[0]);++i)
        if(FCAIWorkers[i].unit==code)return &FCAIWorkers[i];
    if(!w->is_type(unit,worker_type))return 0;
    for(uint32_t i=0;i<4;++i)
        if(w->ability_level(unit,FCAIWorkers[i].build_ability)>0)return &FCAIWorkers[i];
    return 0;
}

static int FCAIHasGatherAbility(FCLocalAIWork *w,uint64_t unit) {
    static const uint32_t stock[]={
        FC_AI_CODE('A','h','a','r'), FC_AI_CODE('A','h','r','2'), FC_AI_CODE('A','h','r','3'),
        FC_AI_CODE('A','a','h','a'), FC_AI_CODE('A','w','h','a'), FC_AI_CODE('A','w','h','2')
    };
    for(uint32_t i=0;i<sizeof(stock)/sizeof(stock[0]);++i)
        if(w->ability_level(unit,stock[i])>0)return 1;
    return 0;
}

static void FCAIEnumerate(FCLocalAIWork *w,uint64_t group,float x,float y,float radius,int limit) {
    w->group_clear(group);
    w->enum_nearby(group,&x,&y,&radius,0,limit);
}

static float FCAIDistance(FCLocalAIWork *w,uint64_t unit,float x,float y) {
    float dx=FullCloneReal(w->x(unit))-x,dy=FullCloneReal(w->y(unit))-y;
    return dx*dx+dy*dy;
}

static int32_t FCAIPlayerState(FCLocalAIWork *w,int field) {
    return w->player_state(w->owner,w->convert_player_state(field));
}

#include "war3_bridge_fullclone_ai_production.h"

static int FCAIFindStartedBuild(FCLocalAIWork *w,uint64_t group) {
    FCAIBuildSite site=w->pending_site;
    uint64_t structure=w->unit_type(FC_AI_STRUCTURE);
    FCAIEnumerate(w,group,site.x,site.y,96.f,32);
    for(unsigned i=0;i<32;++i){
        uint64_t unit=FCLocalAIPop(w,group);
        if(!unit)break;
        if(w->selection.unit_type_id(unit)==site.code && w->owning_player(unit)==w->owner &&
           w->is_type(unit,structure) && FCLocalAIAlive(w,unit) &&
           FCAIDistance(w,unit,site.x,site.y)<=96.f*96.f)return 1;
    }
    return 0;
}

static int FCAIBuildNearby(FCLocalAIWork *w,uint64_t group,uint64_t unit,uint64_t hall,
                           const FCAIWorker *worker,FCAIBuildChoice building) {
    static const int16_t offsets[][2]={{512,0},{0,512},{-512,0},{0,-512},
        {384,384},{-384,384},{-384,-384},{384,-384},
        {768,0},{0,768},{-768,0},{0,-768},{576,576},{-576,576},{-576,-576},{576,-576},
        {320,0},{0,320},{-320,0},{0,-320},{256,256},{-256,256},{-256,-256},{256,-256},
        {256,0},{0,256},{-256,0},{0,-256},{384,192},{-384,-192},{192,-384},{-192,384},
        {384,-192},{-384,192},{192,384},{-192,-384},{352,96},{-352,-96},{96,-352},{-96,352},
        {352,-96},{-352,96},{96,352},{-96,-352},{640,224},{-640,-224},{224,-640},{-224,640},
        {640,-224},{-640,224},{224,640},{-224,-640}};
    float hx=FullCloneReal(w->x(hall)),hy=FullCloneReal(w->y(hall));
    if(!FullCloneFinite(hx) || !FullCloneFinite(hy) || hx>1000000.f || hx< -1000000.f ||
       hy>1000000.f || hy< -1000000.f)return 0;
    uint64_t buildable=w->convert_pathing(3);
    uint64_t structure=w->unit_type(FC_AI_STRUCTURE);
    for(uint32_t i=0;i<sizeof(offsets)/sizeof(offsets[0]);++i){
        float grid=i<32 ? 64.f : 32.f;
        float x=(float)(int32_t)((hx+offsets[i][0])/grid)*grid;
        float y=(float)(int32_t)((hy+offsets[i][1])/grid)*grid;
        if(building.code==w->avoid_site.code){
            float dx=x-w->avoid_site.x,dy=y-w->avoid_site.y;
            if(dx*dx+dy*dy<=96.f*96.f)continue;
        }
        float x0=x-48.f,x1=x+48.f,y0=y-48.f,y1=y+48.f;
        if(w->terrain_blocked(&x,&y,buildable) || w->terrain_blocked(&x0,&y0,buildable) ||
           w->terrain_blocked(&x1,&y1,buildable) || w->terrain_blocked(&x0,&y1,buildable) ||
           w->terrain_blocked(&x1,&y0,buildable) || (worker->blight && !w->point_blighted(&x,&y)))continue;
        FCAIEnumerate(w,group,x,y,160.f,32);
        int occupied=0;
        for(uint32_t j=0;j<32;++j){
            uint64_t occupant=FCLocalAIPop(w,group);
            if(!occupant)break;
            if(w->is_type(occupant,structure) && FCLocalAIAlive(w,occupant)){occupied=1;break;}
        }
        if(w->error)return 0;
        if(occupied)continue;
        w->status|=FC_AI_HAS_SITE;
        if(!FCLocalAICanOrder(w,unit,1))return 0;
        if(w->build(unit,building.code,&x,&y)){
            w->built=1;
            w->built_kind=building.kind;
            w->ordered_site=(FCAIBuildSite){building.code,x,y};
            return 1;
        }
    }
    return 0;
}

static int FCAIWorkerOrder(FCLocalAIWork *w,uint64_t group,uint64_t unit,
                           const FCAIWorker *worker,const FCAIProductionState production[FC_AI_FACTIONS],
                           unsigned heroes,int build_only) {
    float x=FullCloneReal(w->x(unit)),y=FullCloneReal(w->y(unit));
    if(!FullCloneFinite(x) || !FullCloneFinite(y))return 0;
    int harvest=!build_only && (w->features&FC_AI_HARVEST) &&
        (w->selection.unit_type_id(unit)==worker->unit || FCAIHasGatherAbility(w,unit));
    if(harvest)w->status|=FC_AI_WORKER_AVAILABLE;
    if(w->allow_build && worker->supply)w->status|=FC_AI_BUILDER_AVAILABLE;
    int32_t gold=FCAIPlayerState(w,1),wood=FCAIPlayerState(w,2);
    int32_t cap=FCAIPlayerState(w,4),used=FCAIPlayerState(w,5),ceiling=FCAIPlayerState(w,6);
    int headroom=cap>=used && used>=0 ? cap-used : 0;
    int has_capacity=cap>0 && cap<(ceiling>0 ? ceiling : 100);
    int low_food=has_capacity && headroom<=((w->features&FC_AI_TRAIN) ? 5 : 3);
    FCAIBuildChoice build=FCAIConstruction(w,worker,production,heroes,low_food,headroom,has_capacity,gold,wood);
    if(low_food)w->status|=FC_AI_LOW_FOOD;
    uint64_t mine=0,hall=0;
    float mine_dist=2400.f*2400.f,hall_dist=2400.f*2400.f;
    if(build.code || (harvest && worker->mine)){
        FCAIEnumerate(w,group,x,y,2400.f,FC_AI_MAX_TARGETS);
        for(uint32_t i=0;i<FC_AI_MAX_TARGETS;++i){
            uint64_t target=FCLocalAIPop(w,group);
            if(!target)break;
            uint32_t code=w->selection.unit_type_id(target);
            int is_mine=harvest && code==worker->mine && worker->mine;
            int is_hall=build.code && (code==worker->halls[0] || code==worker->halls[1] || code==worker->halls[2]);
            if((!is_mine && !is_hall) || !FCLocalAIAlive(w,target))continue;
            uint64_t owner=w->owning_player(target);
            float distance=FCAIDistance(w,target,x,y);
            if(!FullCloneFinite(distance))continue;
            if(is_hall && owner==w->owner && distance<hall_dist){hall=target;hall_dist=distance;}
            int ordinary_mine=code==FC_AI_CODE('n','g','o','l');
            int reachable_owner=owner==w->owner ||
                (ordinary_mine && owner && w->player_id(owner)==w->neutral_passive());
            /* Entangled/haunted mines can be proxy units. Their underlying
               gold count is not reliable through GetResourceAmount(proxy). */
            if(is_mine && distance<mine_dist && reachable_owner && FCLocalAICanSee(w,target) &&
               (!ordinary_mine || w->resource_amount(target)>0)){mine=target;mine_dist=distance;}
        }
    }
    if(w->error)return 0;
    if(mine)w->status|=FC_AI_HAS_MINE;
    if(hall)w->status|=FC_AI_HAS_HALL;
    if(hall && FCAIBuildNearby(w,group,unit,hall,worker,build))return 1;
    if(!harvest || w->error || !FCLocalAICanOrder(w,unit,0))return 0;
    /* Warcraft can reject this order when the worker or map has no usable trees. */
    if(worker->can_cut && (!mine || (gold>=150 && wood<100)) &&
       w->immediate(unit,852022)){++w->wood;return 1;}
    if(!mine || !FCLocalAICanOrder(w,unit,0))return 0;
    if(w->attack(unit,worker->harvest,mine) ||
       (worker->harvest!=851971 && FCLocalAICanOrder(w,unit,0) && w->attack(unit,851971,mine))){
        ++w->mined;
        return 1;
    }
    return 0;
}

enum {FC_AI_ANY_ENEMY,FC_AI_ENEMY_LIVING,FC_AI_ENEMY_UNDEAD,FC_AI_ENEMY_MANA,
      FC_AI_HEAL_LIVING,FC_AI_HEAL_UNDEAD};
typedef struct FCAISpell {uint32_t code,order;int target;} FCAISpell;

static uint64_t FCAISpellTarget(FCLocalAIWork *w,uint64_t group,uint64_t unit,float range,int mode) {
    float x=FullCloneReal(w->x(unit)),y=FullCloneReal(w->y(unit)),best=range*range;
    if(!FullCloneFinite(x) || !FullCloneFinite(y))return 0;
    uint64_t nearest=0,structure=w->unit_type(FC_AI_STRUCTURE),undead=w->unit_type(14);
    uint64_t mechanical=w->unit_type(15),immune=w->unit_type(26),mana=w->convert_unit_state(2);
    FCAIEnumerate(w,group,x,y,range,FC_AI_MAX_TARGETS);
    for(uint32_t i=0;i<FC_AI_MAX_TARGETS;++i){
        uint64_t target=FCLocalAIPop(w,group);
        if(!target)break;
        if(!FCLocalAIAlive(w,target) || !FCLocalAICanSee(w,target) ||
           w->is_type(target,structure) || w->is_type(target,mechanical) ||
           w->is_type(target,immune) || w->invulnerable(target))continue;
        int is_undead=w->is_type(target,undead);
        if(mode==FC_AI_HEAL_LIVING || mode==FC_AI_HEAL_UNDEAD){
            if(target==unit || w->owning_player(target)!=w->owner ||
               is_undead!=(mode==FC_AI_HEAL_UNDEAD))continue;
            int32_t max=w->max_life(target);
            if(max<=0 || FullCloneReal(w->life(target))>0.65f*(float)max)continue;
        }else if(w->owning_player(target)==w->owner || !w->enemy(target,w->owner) ||
                 (mode==FC_AI_ENEMY_LIVING && is_undead) || (mode==FC_AI_ENEMY_UNDEAD && !is_undead) ||
                 (mode==FC_AI_ENEMY_MANA && !(FullCloneReal(w->unit_state(target,mana))>0)))continue;
        float distance=FCAIDistance(w,target,x,y);
        if(!FullCloneFinite(distance) || distance>best)continue;
        best=distance;
        nearest=target;
    }
    return nearest;
}

static int FCAIHeroOrder(FCLocalAIWork *w,uint64_t group,uint64_t unit) {
    static const FCAISpell spells[]={
        {FC_AI_CODE('A','H','h','b'),852092,FC_AI_HEAL_LIVING},
        {FC_AI_CODE('A','U','d','c'),852222,FC_AI_HEAL_UNDEAD},
        {FC_AI_CODE('A','H','t','b'),852095,FC_AI_ANY_ENEMY},
        {FC_AI_CODE('A','O','c','l'),852119,FC_AI_ANY_ENEMY},
        {FC_AI_CODE('A','U','f','n'),852226,FC_AI_ANY_ENEMY},
        {FC_AI_CODE('A','E','s','h'),852527,FC_AI_ANY_ENEMY},
        {FC_AI_CODE('A','N','f','l'),852587,FC_AI_ANY_ENEMY},
        {FC_AI_CODE('A','E','m','b'),852179,FC_AI_ENEMY_MANA},
        {FC_AI_CODE('A','H','h','b'),852092,FC_AI_ENEMY_UNDEAD},
        {FC_AI_CODE('A','U','d','c'),852222,FC_AI_ENEMY_LIVING}
    };
    float mana=FullCloneReal(w->unit_state(unit,w->convert_unit_state(2)));
    if(!FullCloneFinite(mana) || mana<0)return 0;
    uint64_t range_field=w->convert_ability_real(FC_AI_CODE('a','r','a','n'));
    for(uint32_t i=0;i<sizeof(spells)/sizeof(spells[0]);++i){
        const FCAISpell *spell=&spells[i];
        int32_t level=w->ability_level(unit,spell->code);
        if(level<=0 || level>100000)continue;
        float cooldown=FullCloneReal(w->cooldown(unit,spell->code));
        if(!FullCloneFinite(cooldown) || cooldown>0.01f)continue;
        int32_t cost=w->mana_cost(unit,spell->code,level-1);
        uint64_t ability=w->get_ability(unit,spell->code);
        if(cost<0 || (float)cost>mana || !ability)continue;
        float range=FullCloneReal(w->ability_real(ability,range_field,level-1));
        if(!FullCloneFinite(range) || range<=0)continue;
        if(range>(float)w->radius)range=(float)w->radius;
        uint64_t target=FCAISpellTarget(w,group,unit,range,spell->target);
        if(w->error)return 0;
        if(target && FCLocalAICanOrder(w,unit,0) && FCAIAttackableUnit(w,target) &&
           w->attack(unit,spell->order,target)){
            ++w->spells;
            return 1;
        }
        if(w->error)return 0;
    }
    return 0;
}
