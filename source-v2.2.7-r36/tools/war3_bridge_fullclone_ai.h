/* Single, bounded combat assistance tick for GetLocalPlayer() only. */
enum { FC_AI_OPENING_FACTIONS=4, FC_AI_OPENING_STEPS=4, FC_AI_MAX_DESTRUCTIBLE_TYPES=4096 };
typedef struct FCAIOpeningStep {
    uint32_t kind,count,workers;
} FCAIOpeningStep;
typedef struct FCAIOpening {
    uint32_t worker_target;
    FCAIOpeningStep steps[FC_AI_OPENING_STEPS];
} FCAIOpening;

typedef struct FCAIBuildSite {
    uint32_t code;
    float x,y;
} FCAIBuildSite;

typedef struct FCAIWorldBindings {
    uint64_t base;
    uint64_t (*convert)(uint64_t,uint8_t);
    uint64_t (*location)(float*,float*);
    void (*move_location)(uint64_t,float*,float*);
    uint8_t (*location_visible)(uint64_t,uint64_t);
    void (*remove_location)(uint64_t);
    uint32_t (*item_type)(uint64_t),(*item_x)(uint64_t),(*item_y)(uint64_t);
    uint8_t (*item_invulnerable)(uint64_t),(*item_visible)(uint64_t),(*item_owned)(uint64_t);
    int32_t (*inventory_size)(uint64_t);
    uint64_t (*inventory_item)(uint64_t,int32_t);
    uint64_t (*item_boolean_field)(uint32_t);
    uint8_t (*item_boolean)(uint64_t,uint64_t);
    uint64_t (*unit_integer_field)(uint32_t);
    int32_t (*unit_integer)(uint64_t,uint64_t);
    uint64_t (*item_ability)(uint64_t,int32_t),(*ability_integer_field)(uint32_t);
    int32_t (*ability_integer)(uint64_t,uint64_t,int32_t);
    uint32_t (*destructible_type)(uint64_t),(*destructible_x)(uint64_t),(*destructible_y)(uint64_t);
    uint8_t (*destructible_invulnerable)(uint64_t);
} FCAIWorldBindings;

typedef struct FCLocalAIWork {
    SelectionWork selection;
    uint64_t (*controller)(uint64_t);
    uint64_t (*map_control)(int32_t);
    uint64_t (*slot_state)(uint64_t);
    uint64_t (*player_slot_state)(int32_t);
    void (*enum_owner)(uint64_t,uint64_t,uint64_t);
    void (*enum_nearby)(uint64_t,float*,float*,float*,uint64_t,int32_t);
    void (*group_clear)(uint64_t);
    uint64_t (*owning_player)(uint64_t);
    uint32_t (*current_order)(uint64_t);
    uint32_t (*life)(uint64_t);
    uint8_t (*hidden)(uint64_t);
    uint8_t (*paused)(uint64_t);
    uint8_t (*is_type)(uint64_t,uint64_t);
    uint64_t (*unit_type)(int32_t);
    uint32_t (*x)(uint64_t);
    uint32_t (*y)(uint64_t);
    uint8_t (*enemy)(uint64_t,uint64_t);
    uint8_t (*visible)(uint64_t,uint64_t);
    uint8_t (*invisible)(uint64_t,uint64_t);
    uint8_t (*detected)(uint64_t,uint64_t);
    uint8_t (*invulnerable)(uint64_t);
    uint8_t (*attack)(uint64_t,uint32_t,uint64_t);
    int32_t (*resource_amount)(uint64_t);
    int32_t (*player_id)(uint64_t),(*neutral_passive)(void);
    int32_t (*player_state)(uint64_t,uint64_t);
    uint64_t (*convert_player_state)(int32_t),(*convert_pathing)(int32_t);
    uint8_t (*terrain_blocked)(float*,float*,uint64_t);
    uint8_t (*build)(uint64_t,uint32_t,float*,float*);
    int32_t (*ability_level)(uint64_t,uint32_t);
    uint32_t (*cooldown)(uint64_t,uint32_t);
    int32_t (*mana_cost)(uint64_t,uint32_t,int32_t);
    uint32_t (*unit_state)(uint64_t,uint64_t);
    uint64_t (*convert_unit_state)(int32_t);
    uint64_t (*get_ability)(uint64_t,uint32_t);
    uint32_t (*ability_real)(uint64_t,uint64_t,int32_t);
    uint64_t (*convert_ability_real)(uint32_t);
    int32_t (*max_life)(uint64_t);
    uint8_t (*immediate)(uint64_t,uint32_t);
    int32_t (*neutral_hostile)(void);
    int32_t (*tech_count)(uint64_t,uint32_t,uint32_t);
    int32_t (*tech_max)(uint64_t,uint32_t);
    int32_t (*order_count)(uint64_t);
    uint8_t (*point_blighted)(float*,float*);
    uint8_t (*point_order)(uint64_t,uint32_t,float*,float*);
    uint64_t (*player)(int32_t);
    uint8_t (*player_enemy)(uint64_t,uint64_t);
    int32_t (*start_location)(uint64_t);
    uint32_t (*start_x)(int32_t),(*start_y)(int32_t);
    int32_t (*unit_level)(uint64_t);
    void *tls;
    uint64_t expected_owner,owner;
    uint32_t cursor,radius,features,allow_build,allow_research,inspect,allow_train;
    uint32_t status,mined,wood,spells,built,researched,creeps,trained,changed,error,done,blocked_builds,built_kind;
    uint32_t blocked_train,train_kind,train_wait,hero_seed;
    FCAIOpening openings[FC_AI_OPENING_FACTIONS];
    uint32_t wave_troops[FC_AI_OPENING_FACTIONS];
    uint32_t tactics_issued,tactics_mode,tactics_ready,tactics_reserved;
    FCAIBuildSite pending_site,avoid_site,ordered_site;
    uint32_t build_started;
    FCAIWorldBindings world;
    uint32_t world_stage,world_items,world_destructibles,world_reserved;
    uint32_t destructible_type_count,destructible_reserved;
    uint32_t selectable_destructibles[FC_AI_MAX_DESTRUCTIBLE_TYPES];
} FCLocalAIWork;

_Static_assert(offsetof(FCLocalAIWork,tls)==896,"Local AI header");
_Static_assert(offsetof(FCLocalAIWork,openings)==1016,"Local AI opening plan");
_Static_assert(offsetof(FCLocalAIWork,pending_site)==1256,"Local AI building sites");
_Static_assert(offsetof(FCLocalAIWork,world)==1296,"Local AI world handlers");
_Static_assert(sizeof(FCLocalAIWork)==17904,"Local AI work");
__declspec(dllexport) const uint32_t fullclone_local_ai_abi[3]={0x46414911,216,17904};

enum {
    FC_AI_HERO=0, FC_AI_DEAD=1, FC_AI_STRUCTURE=2, FC_AI_FLYING=3, FC_AI_ATTACKS_FLYING=5,
    FC_AI_ATTACKS_GROUND=6, FC_AI_PEON=16, FC_AI_ORDER_ATTACK=851983,
    FC_AI_COMBAT=1, FC_AI_HARVEST=2, FC_AI_BUILD=4, FC_AI_SPELLS=8,
    FC_AI_RESEARCH=16, FC_AI_CREEPS=32, FC_AI_TRAIN=64, FC_AI_TACTICS=128,
    FC_AI_PICKUP=256, FC_AI_DESTRUCTIBLES=512, FC_AI_NEUTRAL_CREATURES=1024, FC_AI_NEUTRAL_BUILDINGS=2048,
    FC_AI_WORLD_TARGETS=FC_AI_PICKUP|FC_AI_DESTRUCTIBLES,
    FC_AI_NEUTRAL_TARGETS=FC_AI_NEUTRAL_CREATURES|FC_AI_NEUTRAL_BUILDINGS,
    FC_AI_ORDER_SMART=851971, FC_AI_ORDER_REVIVE=852039, FC_AI_MAX_VISITS=4096, FC_AI_MAX_UNITS=24,
    FC_AI_MAX_TARGETS=192, FC_AI_MAX_COMBAT_TARGETS=4096, FC_AI_TARGET_SHORTLIST=8
};
enum {FC_AI_HAS_WORKER=1, FC_AI_WORKER_AVAILABLE=2, FC_AI_LOW_FOOD=4,
      FC_AI_HAS_RESOURCES=8, FC_AI_HAS_HALL=16, FC_AI_HAS_SITE=32, FC_AI_HAS_MINE=64,
      FC_AI_BUILDER_AVAILABLE=128, FC_AI_RESEARCH_BUILDING=256,
      FC_AI_TRAIN_BUILDING=512, FC_AI_TRAIN_FOOD=1024, FC_AI_TRAIN_RESOURCES=2048,
      FC_AI_TRAIN_REJECTED=4096, FC_AI_BUILD_INTENT=8192, FC_AI_TIER_ORDER=16384,
      FC_AI_REVIVE_ORDER=32768, FC_AI_REVIVE_WAIT=65536};

static int FCLocalAIActivePlayer(FCLocalAIWork *w) {
    return w->owner && w->selection.local_player()==w->owner &&
        w->controller(w->owner)==w->map_control(0) &&
        w->slot_state(w->owner)==w->player_slot_state(1);
}

static int FCLocalAIAlive(FCLocalAIWork *w,uint64_t unit) {
    if(!w->selection.unit_type_id(unit) || w->hidden(unit))return 0;
    float life=FullCloneReal(w->life(unit));
    return FullCloneFinite(life) && life>0.405f;
}

static int FCLocalAIOwnUsable(FCLocalAIWork *w,uint64_t unit) {
    return FCLocalAIAlive(w,unit) && w->owning_player(unit)==w->owner &&
        !w->paused(unit);
}

static int FCAIGatheringOrder(uint32_t order) {
    return order==852018 || order==852021 || order==852022 || order==852185 || order==852214;
}

static int FCLocalAICanOrder(FCLocalAIWork *w,uint64_t unit,int reassign_gatherer) {
    if(w->inspect)return 0;
    /* Orders can run map triggers. Recheck the local slot before every write. */
    if(!FCLocalAIActivePlayer(w)){w->error=1237;return 0;}
    if(!FCLocalAIOwnUsable(w,unit))return 0;
    uint32_t order=w->current_order(unit);
    return !order || (reassign_gatherer && FCAIGatheringOrder(order));
}

static int FCLocalAICanSee(FCLocalAIWork *w,uint64_t unit) {
    return w->visible(unit,w->owner) && (!w->invisible(unit,w->owner) || w->detected(unit,w->owner));
}

static int FCAIAttackableUnit(FCLocalAIWork *w,uint64_t unit) {
    return FCLocalAIAlive(w,unit) && !w->invulnerable(unit) && FCLocalAICanSee(w,unit);
}

static uint64_t FCLocalAIPop(FCLocalAIWork *w,uint64_t group) {
    uint64_t unit=w->selection.first_of_group(group);
    if(unit && !((uint8_t (*)(uint64_t,uint64_t))w->selection.remove_from_group)(group,unit)){
        w->error=1003;
        return 0;
    }
    return unit;
}

enum { FC_AI_TARGET_UNIT, FC_AI_TARGET_CREEP, FC_AI_TARGET_ITEM, FC_AI_TARGET_DESTRUCTIBLE };
struct FCAIWidget;
typedef struct FCAITarget {
    uint64_t unit;
    struct FCAIWidget *widget;
    float distance;
    uint32_t kind;
} FCAITarget;

typedef struct FCAITargetList {
    FCAITarget rows[FC_AI_TARGET_SHORTLIST];
    unsigned count;
} FCAITargetList;

static void FCAIConsiderTarget(FCAITargetList *list,FCAITarget candidate,float maximum) {
    if(!FullCloneFinite(candidate.distance) || candidate.distance>maximum)return;
    unsigned at=0;
    int is_creep=candidate.kind==FC_AI_TARGET_CREEP;
    while(at<list->count){
        FCAITarget previous=list->rows[at];
        int previous_creep=previous.kind==FC_AI_TARGET_CREEP;
        if(is_creep>previous_creep ||
           (is_creep==previous_creep && candidate.distance<previous.distance))break;
        ++at;
    }
    if(at==FC_AI_TARGET_SHORTLIST)return;
    if(list->count<FC_AI_TARGET_SHORTLIST)++list->count;
    for(unsigned i=list->count-1;i>at;--i)list->rows[i]=list->rows[i-1];
    list->rows[at]=candidate;
}

static void FCAICollectCombatTargets(FCLocalAIWork *w,uint64_t group,uint64_t source,
                                     uint64_t flying,int hits_ground,int hits_flying,uint32_t mode,
                                     float x,float y,FCAITargetList *list) {
    float radius=(float)w->radius,maximum=radius*radius;
    uint64_t structure=w->unit_type(FC_AI_STRUCTURE);
    int32_t hostile=w->neutral_hostile(),passive=w->neutral_passive();
    w->group_clear(group);
    w->enum_nearby(group,&x,&y,&radius,0,FC_AI_MAX_COMBAT_TARGETS);
    for(uint32_t i=0;i<FC_AI_MAX_COMBAT_TARGETS;++i){
        uint64_t target=FCLocalAIPop(w,group);
        if(!target)break;
        uint64_t player=w->owning_player(target);
        if(target==source || !player || player==w->owner)continue;
        if(w->is_type(target,flying) ? !hits_flying : !hits_ground)continue;
        int32_t slot=w->player_id(player);
        int enemy=w->enemy(target,w->owner);
        int building=w->is_type(target,structure);
        uint32_t neutral_kind=building?FC_AI_NEUTRAL_BUILDINGS:FC_AI_NEUTRAL_CREATURES;
        int creep=(mode&FC_AI_CREEPS) && enemy && slot==hostile && !building;
        if(!creep && !((mode&FC_AI_COMBAT) && enemy) &&
           !((mode&neutral_kind) && hostile>=0 && passive==hostile+3 && slot>=hostile && slot<=passive))continue;
        if(!FCAIAttackableUnit(w,target))continue;
        float dx=FullCloneReal(w->x(target))-x,dy=FullCloneReal(w->y(target))-y;
        FCAIConsiderTarget(list,(FCAITarget){target,0,dx*dx+dy*dy,
                           creep?FC_AI_TARGET_CREEP:FC_AI_TARGET_UNIT},maximum);
    }
}

#include "war3_bridge_fullclone_ai_world.h"
#include "war3_bridge_fullclone_ai_orders.h"
#include "war3_bridge_fullclone_ai_research.h"
#include "war3_bridge_fullclone_ai_battle.h"

static int FCAIValidSite(FCAIBuildSite site) {
    if(!site.code)return !site.x && !site.y;
    return site.x>=-1000000.f && site.x<=1000000.f && site.y>=-1000000.f && site.y<=1000000.f;
}

static int FCAIValidOpeningPlans(const FCLocalAIWork *w) {
    if(w->tactics_issued || w->tactics_mode || w->tactics_ready || w->tactics_reserved)return 0;
    for(unsigned race=0;race<FC_AI_OPENING_FACTIONS;++race){
        if(w->wave_troops[race]>12 || (w->wave_troops[race] && !(w->features&FC_AI_TACTICS)))return 0;
    }
    for(unsigned race=0;race<FC_AI_OPENING_FACTIONS;++race){
        const FCAIOpening *plan=&w->openings[race];
        if(plan->worker_target>24 || (plan->worker_target && (w->features&(FC_AI_BUILD|FC_AI_TRAIN))!=(FC_AI_BUILD|FC_AI_TRAIN)))
            return 0;
        for(unsigned i=0;i<FC_AI_OPENING_STEPS;++i){
            const FCAIOpeningStep *step=&plan->steps[i];
            if(!step->kind && !step->count && !step->workers)continue;
            if(!plan->worker_target || step->workers>plan->worker_target ||
               (step->kind!=FC_AI_BUILD_SUPPLY && step->kind!=FC_AI_BUILD_FACTORY && step->kind!=FC_AI_BUILD_ALTAR) ||
               !step->count || step->count>(step->kind==FC_AI_BUILD_SUPPLY ? 2u : 1u))return 0;
        }
    }
    return 1;
}

__declspec(dllexport) uint64_t BridgeFullCloneLocalAIQuery(void) {
    FCLocalAIWork *w=(FCLocalAIWork*)g_dispatch->work;
    if(!w || w->tls!=g_dispatch->tls_value || w->owner || w->changed || w->error ||
       w->done || w->built || w->status || w->mined || w->wood || w->spells ||
       w->researched || w->creeps || w->trained || w->built_kind || w->blocked_builds>127 || w->blocked_train>31 ||
       w->train_kind || w->train_wait || (w->hero_seed && !w->allow_train) ||
       w->build_started || w->ordered_site.code || w->ordered_site.x || w->ordered_site.y ||
       !FCAIValidSite(w->pending_site) || !FCAIValidSite(w->avoid_site) ||
       (w->pending_site.code && (w->allow_build || !w->expected_owner || !(w->features&FC_AI_BUILD))) ||
       (w->avoid_site.code && !w->allow_build) ||
       w->cursor>=FC_AI_MAX_VISITS ||
       (!w->expected_owner && (w->cursor || w->allow_build || w->allow_research || w->inspect || w->allow_train)) ||
       (w->radius!=900 && w->radius!=1600 && w->radius!=2400 && w->radius!=3200 &&
        w->radius!=4000 && w->radius!=4800 && w->radius!=6400 && w->radius!=9600 &&
        w->radius!=12800 && w->radius!=19200 && w->radius!=25600) ||
       w->world_stage || w->world_items || w->world_destructibles || w->world_reserved ||
       !FCAIValidWorldBindings(w) || !FCAIValidDestructibleTypes(w) || !w->features || w->features>4095 || w->allow_build>1 || w->allow_research>1 || w->inspect>1 || w->allow_train>1 ||
       (w->allow_build && !(w->features&FC_AI_BUILD)) ||
       (w->blocked_builds && !w->allow_build) || (w->blocked_train && !w->allow_train) ||
       (w->allow_research && !(w->features&FC_AI_RESEARCH)) ||
       (w->allow_train && !(w->features&FC_AI_TRAIN)) || !FCAIValidOpeningPlans(w)){
        if(w)w->error=1000;
        return 0;
    }
    uint64_t own=0,nearby=0;
    FCAIWorldTargets targets={0};
    FCAIPickupRoster pickup={0};
    __try {
        __try {
            w->owner=w->selection.local_player();
            if(!FCLocalAIActivePlayer(w)){w->error=1001;return 0;}
            if(!w->expected_owner){w->done=1;return 0;}
            if(w->owner!=w->expected_owner){w->error=1237;return 0;}
            if(w->inspect && w->world.base){
                FCAICollectWorld(w,&targets);
                w->done=!w->error;
                return 0;
            }
            own=w->selection.create_group();
            nearby=w->selection.create_group();
            if(!own || !nearby){w->error=1008;return 0;}
            if(w->pending_site.code)
                w->build_started=FCAIFindStartedBuild(w,nearby);
            FCAIProductionState production[FC_AI_FACTIONS]={0};
            FCAIHeroRoster roster={0};
            if((w->features&FC_AI_TRAIN) ||
               (w->features&(FC_AI_TACTICS|FC_AI_HARVEST))==(FC_AI_TACTICS|FC_AI_HARVEST)){
                w->enum_owner(own,w->owner,0);
                FCAISurveyProduction(w,own,production,&roster);
                if(w->error)return 0;
                w->group_clear(own);
            }
            unsigned heroes=roster.count;
            if(!w->inspect && (w->features&FC_AI_PICKUP)){
                FCAICollectPickupHeroes(w,nearby,&pickup);
                if(w->error)return 0;
            }
            w->enum_owner(own,w->owner,0);
            uint64_t building=w->unit_type(FC_AI_STRUCTURE),worker=w->unit_type(FC_AI_PEON);
            uint64_t hero=w->unit_type(FC_AI_HERO);
            uint64_t flying=w->unit_type(FC_AI_FLYING);
            uint64_t ground_attack=w->unit_type(FC_AI_ATTACKS_GROUND);
            uint64_t flying_attack=w->unit_type(FC_AI_ATTACKS_FLYING);
            uint32_t resume=w->cursor,checked=0;
            uint32_t combat=w->features&FC_AI_NEUTRAL_TARGETS;
            if(!(w->features&FC_AI_TACTICS))combat|=w->features&(FC_AI_COMBAT|FC_AI_CREEPS);
            int world_scanned=0;
            uint64_t gatherers[4]={0};
            uint32_t gathering=0;
            int builder_reserved=0;
            int reserve_acolyte=(w->features&(FC_AI_BUILD|FC_AI_TRAIN|FC_AI_HARVEST))==
                (FC_AI_BUILD|FC_AI_TRAIN|FC_AI_HARVEST);
            w->cursor=0;
            for(uint32_t i=0;i<FC_AI_MAX_VISITS;++i){
                uint64_t unit=FCLocalAIPop(w,own);
                if(!unit)break;
                if(i<resume || !FCLocalAIOwnUsable(w,unit))continue;
                if(w->is_type(unit,building)){
                    if(!w->built && (w->features&FC_AI_RESEARCH) &&
                       (!(w->features&FC_AI_TRAIN) || FCAIProductionIdle(w,unit)) &&
                       FCAIResearchOrder(w,unit))++w->changed;
                    if(w->error)break;
                    if(w->changed>=FC_AI_MAX_UNITS){
                        if(i+1<FC_AI_MAX_VISITS && w->selection.first_of_group(own))w->cursor=i+1;
                        break;
                    }
                    continue;
                }
                const FCAIWorker *details=FCAIWorkerType(w,unit,worker);
                if(details)w->status|=FC_AI_HAS_WORKER;
                uint32_t order=w->current_order(unit);
                if(order){
                    if(details && details->supply && w->allow_build && !w->built &&
                       gathering<4 && FCAIGatheringOrder(order))gatherers[gathering++]=unit;
                    continue;
                }
                int ordered=0,eligible=0;
                /* Preserve a lumber crew while leaving the other stock ghouls free to fight. */
                int reserve_ghoul=details && (w->features&FC_AI_TACTICS) && details->unit==FC_AI_ID("ugho");
                int worker_task=details && (!reserve_ghoul || production[FC_AI_UNDEAD].ghoul_lumber<2) &&
                    ((w->features&FC_AI_HARVEST) || (details->supply && w->allow_build && !w->built));
                if(worker_task){
                    /* Keep an available Acolyte outside the mine, including between projects. */
                    int build_only=reserve_acolyte && !builder_reserved && details->unit==FC_AI_ID("uaco");
                    builder_reserved|=build_only;
                    eligible=1;
                    ordered=FCAIWorkerOrder(w,nearby,unit,details,production,heroes,build_only);
                    if(ordered && reserve_ghoul)++production[FC_AI_UNDEAD].ghoul_lumber;
                }
                int combat_unit=!worker_task && !w->is_type(unit,worker);
                if(!ordered && !w->error && combat_unit && (w->features&FC_AI_SPELLS) && w->is_type(unit,hero)){
                    eligible=1;
                    ordered=FCAIHeroOrder(w,nearby,unit);
                }
                FCAIPickupHero *picker=FCAIFindPickupHero(&pickup,unit);
                if(!ordered && !w->error && !w->inspect){
                    int hits_ground=combat_unit && w->is_type(unit,ground_attack);
                    int hits_flying=combat_unit && w->is_type(unit,flying_attack);
                    int attacks=hits_ground || hits_flying;
                    eligible|=picker!=0 || (attacks && combat) || (hits_ground && w->destructible_type_count);
                    if(!world_scanned && (picker || (hits_ground && w->destructible_type_count))){
                        world_scanned=1;
                        FCAICollectWorld(w,&targets);
                    }
                    if(!w->error && eligible)
                        ordered=FCAIOrderClosestTarget(w,nearby,unit,flying,hits_ground,hits_flying,
                                                       attacks?combat:0,&targets,&pickup,picker);
                }
                if(ordered){
                    if(picker)picker->unit=0;
                    ++w->changed;
                }
                if(w->error)break;
                if((eligible && ++checked==FC_AI_MAX_UNITS) || w->changed>=FC_AI_MAX_UNITS){
                    if(i+1<FC_AI_MAX_VISITS && w->selection.first_of_group(own))w->cursor=i+1;
                    break;
                }
            }
            /* Prefer an idle builder. A normal harvesting order is the only
               existing order that construction may replace as a fallback. */
            for(uint32_t i=0;i<gathering && !w->error && !w->built && w->changed<FC_AI_MAX_UNITS;++i){
                uint64_t unit=gatherers[i];
                const FCAIWorker *details=FCAIWorkerType(w,unit,worker);
                if(details && details->supply && FCLocalAIOwnUsable(w,unit) &&
                   FCAIWorkerOrder(w,nearby,unit,details,production,heroes,1))++w->changed;
            }
            if(w->allow_train && !w->built && !w->inspect && !w->error && w->changed<FC_AI_MAX_UNITS &&
               FCAITrain(w,production,&roster))++w->changed;
            if((w->features&FC_AI_TACTICS) && !w->inspect && !w->error && w->changed<FC_AI_MAX_UNITS)
                FCAIBattleOrders(w,own,nearby);
        } __finally {
            if(targets.items)HeapFree(GetProcessHeap(),0,targets.items);
            if(targets.destructibles)HeapFree(GetProcessHeap(),0,targets.destructibles);
            if(targets.location)w->world.remove_location(targets.location);
            if(nearby)w->selection.destroy_group(nearby);
            if(own)w->selection.destroy_group(own);
        }
        w->done=!w->error;
    } __except(BridgeExceptionFilter(GetExceptionInformation())) {w->error=GetExceptionCode();}
    return w->changed;
}
