/* Four stock openings. Costs come from this build's UnitBalance.slk.
   These are normal orders; the game checks scenario restrictions and costs. */
typedef struct FCAITrainUnit {
    uint32_t code;
    uint16_t gold,lumber;
    uint8_t food,seconds;
} FCAITrainUnit;

typedef struct FCAIProductionRule {
    uint32_t factory,altar;
    uint16_t factory_gold,factory_lumber;
    uint8_t workers;
    FCAITrainUnit worker,army,alternate;
} FCAIProductionRule;

static const FCAIProductionRule FCAIProductionRules[]={
    {FC_AI_ID("hbar"),FC_AI_ID("halt"),160,60,8,
        {FC_AI_ID("hpea"),75,0,1,15},{FC_AI_ID("hfoo"),135,0,2,20},
        {FC_AI_ID("hrif"),205,30,3,26}},
    {FC_AI_ID("obar"),FC_AI_ID("oalt"),180,50,8,
        {FC_AI_ID("opeo"),75,0,1,15},{FC_AI_ID("ogru"),200,0,3,30},
        {FC_AI_ID("ohun"),140,20,2,22}},
    {FC_AI_ID("usep"),FC_AI_ID("uaod"),200,50,5,
        {FC_AI_ID("uaco"),75,0,1,15},{FC_AI_ID("ugho"),120,0,2,18},
        {FC_AI_ID("ucry"),215,40,3,30}},
    {FC_AI_ID("eaom"),FC_AI_ID("eate"),150,60,8,
        {FC_AI_ID("ewsp"),60,0,1,14},{FC_AI_ID("earc"),130,10,2,20},
        {FC_AI_ID("esen"),195,20,3,30}},
};
enum {FC_AI_FACTIONS=sizeof(FCAIProductionRules)/sizeof(FCAIProductionRules[0])};
_Static_assert((unsigned)FC_AI_FACTIONS==(unsigned)FC_AI_OPENING_FACTIONS,"Local AI faction count");

/* common.ai's PickMeleeHero uses these pools, drawing without replacement. */
static const uint32_t FCAIHeroPools[FC_AI_FACTIONS][4]={
    {FC_AI_ID("Hamg"),FC_AI_ID("Hmkg"),FC_AI_ID("Hpal"),FC_AI_ID("Hblm")},
    {FC_AI_ID("Obla"),FC_AI_ID("Ofar"),FC_AI_ID("Otch"),FC_AI_ID("Oshd")},
    {FC_AI_ID("Udea"),FC_AI_ID("Udre"),FC_AI_ID("Ulic"),FC_AI_ID("Ucrl")},
    {FC_AI_ID("Edem"),FC_AI_ID("Ekee"),FC_AI_ID("Emoo"),FC_AI_ID("Ewar")},
};

typedef struct FCAIHeroRoster {
    unsigned count,used_types,fallen_count;
    uint64_t fallen[3];
} FCAIHeroRoster;

typedef struct FCAIDevelopmentBuilding {
    uint32_t code;
    uint16_t gold,lumber;
} FCAIDevelopmentBuilding;

typedef struct FCAIDevelopmentPlan {
    FCAIDevelopmentBuilding prerequisite,utility,support,late;
    FCAITrainUnit tier_two,tier_three,support_unit,late_unit;
} FCAIDevelopmentPlan;

/* Read from the 3.0.1 UnitBalance and UnitFunc tables. Upgrades use the
   difference between the two town hall entries, rather than total cost. */
static const FCAIDevelopmentPlan FCAIDevelopmentPlans[FC_AI_FACTIONS]={
    {
        {FC_AI_ID("hbla"),140,40},{FC_AI_ID("hlum"),120,0},
        {FC_AI_ID("hars"),150,140},{FC_AI_ID("hgra"),140,150},
        {FC_AI_ID("hkee"),320,210,0,140},{FC_AI_ID("hcas"),320,210,0,140},
        {FC_AI_ID("hmpr"),135,10,2,28},{FC_AI_ID("hgry"),280,70,4,45},
    },
    {
        {FC_AI_ID("ofor"),205,0},{0},
        {FC_AI_ID("obea"),145,140},{FC_AI_ID("otto"),135,155},
        {FC_AI_ID("ostr"),315,190,0,140},{FC_AI_ID("ofrt"),325,190,0,140},
        {FC_AI_ID("orai"),180,40,3,28},{FC_AI_ID("otau"),300,100,5,39},
    },
    {0}, /* The tested Undead opening has its own build and army rules. */
    {
        {FC_AI_ID("edob"),210,100},{0},
        {FC_AI_ID("eaoe"),155,145},{FC_AI_ID("edos"),140,190},
        {FC_AI_ID("etoa"),320,180,0,140},{FC_AI_ID("etoe"),330,200,0,140},
        {FC_AI_ID("edry"),145,60,3,30},{FC_AI_ID("echm"),330,70,5,60},
    },
};

typedef struct FCAIProductionState {
    uint64_t hall,factory,altar,slaughterhouse,boneyard,support_factory,late_factory;
    uint32_t workers,army,alternate,hall_code,statues,abominations,wyrms,support_count,late_count,supplies;
    uint32_t ghoul_lumber;
    int has_factory,has_altar,has_graveyard,has_tomb,has_slaughterhouse,has_boneyard;
    int has_prerequisite,has_utility,has_support,has_late;
} FCAIProductionState;

typedef struct FCAIBuildChoice {
    uint32_t code;
    uint32_t kind;
} FCAIBuildChoice;

enum {
    FC_AI_UNDEAD=2,
    FC_AI_BUILD_SUPPLY=1, FC_AI_BUILD_FACTORY=2, FC_AI_BUILD_ALTAR=4,
    FC_AI_BUILD_PREREQUISITE=8, FC_AI_BUILD_UTILITY=16, FC_AI_BUILD_SUPPORT=32,
    FC_AI_BUILD_LATE=64,
    FC_AI_PRODUCE_HALL=1, FC_AI_PRODUCE_FACTORY=2, FC_AI_PRODUCE_ALTAR=4,
    FC_AI_PRODUCE_SUPPORT=8, FC_AI_PRODUCE_LATE=16
};

static int FCAIProductionIdle(FCLocalAIWork *w,uint64_t unit) {
    return !w->current_order(unit) && w->order_count(unit)==0;
}

static void FCAISurveyProduction(FCLocalAIWork *w,uint64_t group,
                                 FCAIProductionState states[FC_AI_FACTIONS],FCAIHeroRoster *heroes) {
    uint64_t hero=w->unit_type(FC_AI_HERO),dead=w->unit_type(FC_AI_DEAD);
    for(uint32_t i=0;i<FC_AI_MAX_VISITS;++i){
        uint64_t unit=FCLocalAIPop(w,group);
        if(!unit)break;
        uint32_t code=w->selection.unit_type_id(unit);
        if(!code || w->owning_player(unit)!=w->owner)continue;
        float life=FullCloneReal(w->life(unit));
        if(w->is_type(unit,hero)){
            /* A fallen hero retains their slot and their original hero type. */
            ++heroes->count;
            for(unsigned f=0;f<FC_AI_FACTIONS;++f)
                for(unsigned h=0;h<4;++h)
                    if(code==FCAIHeroPools[f][h])heroes->used_types|=1u<<(4*f+h);
            if(heroes->fallen_count<3 && life<=0.405f && w->is_type(unit,dead))
                heroes->fallen[heroes->fallen_count++]=unit;
        }
        /* Workers can be hidden in mines, so count them by ownership and life. */
        if(!FullCloneFinite(life) || life<=0.405f)continue;
        for(unsigned f=0;f<FC_AI_FACTIONS;++f){
            const FCAIProductionRule *rule=&FCAIProductionRules[f];
            FCAIProductionState *state=&states[f];
            const uint32_t *halls=FCAIWorkers[f].halls;
            const FCAIDevelopmentPlan *plan=&FCAIDevelopmentPlans[f];
            if(code==FCAIWorkers[f].supply || (f==FC_AI_UNDEAD &&
               (code==FC_AI_ID("uzg1") || code==FC_AI_ID("uzg2")))){++state->supplies;break;}
            if(code==rule->worker.code){++state->workers;break;}
            if(code==rule->army.code){
                ++state->army;
                if(f==FC_AI_UNDEAD && (w->features&FC_AI_TACTICS)){
                    uint32_t order=w->current_order(unit);
                    if(FCAIGatheringOrder(order) || order==852020)++state->ghoul_lumber;
                }
                break;
            }
            if(code==rule->alternate.code){++state->alternate;break;}
            uint64_t *producer=0;
            if(code==rule->factory){state->has_factory=1;producer=&state->factory;}
            else if(code==rule->altar){state->has_altar=1;producer=&state->altar;}
            else if(code==halls[0] || code==halls[1] || code==halls[2]){
                if(!state->hall_code || code==halls[2] || (code==halls[1] && state->hall_code==halls[0]))
                    state->hall_code=code;
                producer=&state->hall;
            }else if(f==FC_AI_UNDEAD){
                switch(code){
                    case FC_AI_ID("ugrv"):state->has_graveyard=1;break;
                    case FC_AI_ID("utom"):state->has_tomb=1;break;
                    case FC_AI_ID("uslh"):state->has_slaughterhouse=1;producer=&state->slaughterhouse;break;
                    case FC_AI_ID("ubon"):state->has_boneyard=1;producer=&state->boneyard;break;
                    case FC_AI_ID("uobs"):++state->statues;break;
                    case FC_AI_ID("uabo"):++state->abominations;break;
                    case FC_AI_ID("ufro"):++state->wyrms;break;
                }
            }else{
                if(code==plan->prerequisite.code){state->has_prerequisite=1;break;}
                if(code==plan->utility.code){state->has_utility=1;break;}
                if(code==plan->support_unit.code){++state->support_count;break;}
                if(code==plan->late_unit.code){++state->late_count;break;}
                if(code==plan->support.code){state->has_support=1;producer=&state->support_factory;}
                if(code==plan->late.code){state->has_late=1;producer=&state->late_factory;}
            }
            if(!producer)continue;
            w->status|=FC_AI_TRAIN_BUILDING;
            if(!w->paused(unit) && !w->hidden(unit) && FCAIProductionIdle(w,unit) &&
               (!*producer || (producer==&state->hall && code==state->hall_code)))
                *producer=unit;
            break;
        }
    }
}

static int FCAITrainFrom(FCLocalAIWork *w,uint64_t producer,const FCAITrainUnit *unit,uint32_t kind,int upgrade) {
    if(!producer || !w->allow_train || (w->blocked_train&kind))return 0;
    int32_t cap=FCAIPlayerState(w,4),used=FCAIPlayerState(w,5);
    if(unit->food && (used<0 || cap<used || cap-used<unit->food)){w->status|=FC_AI_TRAIN_FOOD;return 0;}
    if((unit->gold && FCAIPlayerState(w,1)<unit->gold) ||
       (unit->lumber && FCAIPlayerState(w,2)<unit->lumber)){
        w->status|=FC_AI_TRAIN_RESOURCES;
        return 0;
    }
    if(!FCLocalAICanOrder(w,producer,0) || !FCAIProductionIdle(w,producer))return 0;
    if(!w->immediate(producer,unit->code)){w->status|=FC_AI_TRAIN_REJECTED;return 0;}
    w->train_kind=kind;
    w->train_wait=unit->seconds;
    if(upgrade)w->status|=FC_AI_TIER_ORDER;
    else w->trained=1;
    return 1;
}

static int FCAITrainHero(FCLocalAIWork *w,const FCAIProductionState *state,unsigned faction,
                         const FCAIHeroRoster *heroes) {
    if(!state->altar || heroes->fallen_count || (w->blocked_train&FC_AI_PRODUCE_ALTAR))return 0;
    const uint32_t *halls=FCAIWorkers[faction].halls;
    unsigned tier=state->hall_code==halls[2] ? 3 : state->hall_code==halls[1] ? 2 : 1;
    int32_t limit=w->tech_max(w->owner,FC_AI_ID("HERO"));
    if(heroes->count>=tier || (limit>=0 && heroes->count>=(unsigned)limit))return 0;
    unsigned pool[]={0,1,2,3};
    unsigned order=(w->hero_seed>>(8*faction))%24;
    for(unsigned count=4;count && !w->error;--count){
        unsigned pick=order%count, index=pool[pick];
        pool[pick]=pool[count-1];
        order/=count;
        uint32_t code=FCAIHeroPools[faction][index];
        if((heroes->used_types&(1u<<(4*faction+index))) || w->tech_max(w->owner,code)==0)continue;
        /* Game orders apply the map's actual costs, including a free first hero. */
        FCAITrainUnit unit={code,0,0,5,55};
        if(FCAITrainFrom(w,state->altar,&unit,FC_AI_PRODUCE_ALTAR,0))return 1;
        if(w->status&FC_AI_TRAIN_FOOD)break;
    }
    return 0;
}

static int FCAIQueueRevive(FCLocalAIWork *w,uint64_t altar,const FCAIHeroRoster *heroes) {
    if(!altar || (w->blocked_train&FC_AI_PRODUCE_ALTAR))return 0;
    uint64_t dead=w->unit_type(FC_AI_DEAD);
    for(unsigned i=0;i<heroes->fallen_count && !w->error;++i){
        uint64_t unit=heroes->fallen[i];
        if(!FCLocalAICanOrder(w,altar,0) || !FCAIProductionIdle(w,altar))return 0;
        if(w->owning_player(unit)!=w->owner || !w->is_type(unit,dead))continue;
        /* Normal altar order: Warcraft checks eligibility, pays and queues the revive. */
        if(!w->attack(altar,FC_AI_ORDER_REVIVE,unit))continue;
        w->status|=FC_AI_REVIVE_ORDER;
        w->train_kind=FC_AI_PRODUCE_ALTAR;
        w->train_wait=3;
        return 1;
    }
    return 0;
}

static int FCAIUndeadReadyToTech(const FCAIProductionState *s,unsigned heroes) {
    return heroes && s->has_altar && s->has_graveyard && s->army+s->alternate>=4;
}

static int FCAIUndeadTech(FCLocalAIWork *w,const FCAIProductionState *s,unsigned heroes) {
    static const FCAITrainUnit tier_two={FC_AI_ID("unp1"),320,210,0,140};
    static const FCAITrainUnit tier_three={FC_AI_ID("unp2"),325,230,0,140};
    if(!FCAIUndeadReadyToTech(s,heroes) || w->selection.unit_type_id(s->hall)!=s->hall_code)return 0;
    if(s->hall_code==FC_AI_ID("unpl"))return FCAITrainFrom(w,s->hall,&tier_two,FC_AI_PRODUCE_HALL,1);
    if(s->hall_code==FC_AI_ID("unp1") && s->has_slaughterhouse)
        return FCAITrainFrom(w,s->hall,&tier_three,FC_AI_PRODUCE_HALL,1);
    return 0;
}

static int FCAIUndeadSupport(FCLocalAIWork *w,const FCAIProductionState *s) {
    static const FCAITrainUnit statue={FC_AI_ID("uobs"),200,35,3,35};
    static const FCAITrainUnit abomination={FC_AI_ID("uabo"),240,70,4,40};
    static const FCAITrainUnit wyrm={FC_AI_ID("ufro"),385,120,7,65};
    if(s->has_tomb && s->statues<1 && FCAITrainFrom(w,s->slaughterhouse,&statue,FC_AI_PRODUCE_SUPPORT,0))return 1;
    if(w->error || s->hall_code!=FC_AI_ID("unp2"))return 0;
    if(s->abominations<2 && FCAITrainFrom(w,s->slaughterhouse,&abomination,FC_AI_PRODUCE_SUPPORT,0))return 1;
    if(w->error)return 0;
    return s->wyrms<2 && FCAITrainFrom(w,s->boneyard,&wyrm,FC_AI_PRODUCE_LATE,0);
}


/* Use the same reservations as Undead so an upgrade and worker training
   cannot be counted as independent jobs at the same building. */
static int FCAIDevelopmentReady(const FCAIProductionState *state,unsigned heroes) {
    return heroes && state->has_altar && state->has_prerequisite && state->army+state->alternate>=4;
}

static int FCAIDevelopmentTrain(FCLocalAIWork *w,const FCAIProductionState *state,
                                const FCAIDevelopmentPlan *plan,unsigned heroes) {
    if(!plan->tier_two.code)return 0;
    if(FCAIDevelopmentReady(state,heroes) && state->hall &&
       w->selection.unit_type_id(state->hall)==state->hall_code){
        if(state->hall_code!=plan->tier_two.code && state->hall_code!=plan->tier_three.code &&
           FCAITrainFrom(w,state->hall,&plan->tier_two,FC_AI_PRODUCE_HALL,1))return 1;
        if(w->error)return 0;
        if(state->hall_code==plan->tier_two.code && state->has_support &&
           FCAITrainFrom(w,state->hall,&plan->tier_three,FC_AI_PRODUCE_HALL,1))return 1;
        if(w->error)return 0;
    }
    if(state->support_count<2 &&
       FCAITrainFrom(w,state->support_factory,&plan->support_unit,FC_AI_PRODUCE_SUPPORT,0))return 1;
    if(w->error)return 0;
    return state->hall_code==plan->tier_three.code && state->late_count<2 &&
        FCAITrainFrom(w,state->late_factory,&plan->late_unit,FC_AI_PRODUCE_LATE,0);
}


static int FCAIOpeningNeeded(const FCAIOpeningStep *step,const FCAIProductionState *state) {
    switch(step->kind){
        case FC_AI_BUILD_SUPPLY:return state->supplies<step->count;
        case FC_AI_BUILD_FACTORY:return !state->has_factory;
        case FC_AI_BUILD_ALTAR:return !state->has_altar;
        default:return 0;
    }
}

static uint32_t FCAIWorkerGoal(FCLocalAIWork *w,unsigned faction,const FCAIProductionState *state) {
    const FCAIOpening *plan=&w->openings[faction];
    uint32_t reserve=faction==FC_AI_UNDEAD &&
        (w->features&(FC_AI_BUILD|FC_AI_HARVEST))==(FC_AI_BUILD|FC_AI_HARVEST);
    if(!(w->features&FC_AI_BUILD) || !plan->worker_target)
        return FCAIProductionRules[faction].workers+reserve;
    for(unsigned i=0;i<FC_AI_OPENING_STEPS;++i){
        const FCAIOpeningStep *step=&plan->steps[i];
        if(FCAIOpeningNeeded(step,state))return (step->workers ? step->workers : 1)+reserve;
    }
    return plan->worker_target+reserve;
}

static int FCAITrain(FCLocalAIWork *w,const FCAIProductionState states[FC_AI_FACTIONS],const FCAIHeroRoster *roster) {
    unsigned heroes=roster->count;
    if(roster->fallen_count){
        w->status|=FC_AI_REVIVE_WAIT;
        for(unsigned f=0;f<FC_AI_FACTIONS && !w->error;++f)
            if(FCAIQueueRevive(w,states[f].altar,roster))return 1;
    }
    for(unsigned f=0;f<FC_AI_FACTIONS && !w->error;++f){
        const FCAIProductionRule *rule=&FCAIProductionRules[f];
        const FCAIProductionState *state=&states[f];
        if(state->workers<FCAIWorkerGoal(w,f,state) && FCAITrainFrom(w,state->hall,&rule->worker,FC_AI_PRODUCE_HALL,0))return 1;
    }
    for(unsigned f=0;f<FC_AI_FACTIONS && !w->error;++f){
        const FCAIProductionRule *rule=&FCAIProductionRules[f];
        const FCAIProductionState *state=&states[f];
        if(FCAITrainHero(w,state,f,roster))return 1;
        if(w->error)return 0;
        if(f==FC_AI_UNDEAD && (w->features&FC_AI_BUILD)){
            if(state->hall && FCAIUndeadTech(w,state,heroes))return 1;
            if(w->error)return 0;
            if(FCAIUndeadSupport(w,state))return 1;
            if(w->error)return 0;
            /* Save for the next town level once a starting army is available. */
            int saving=(state->hall_code==FC_AI_ID("unpl") && FCAIUndeadReadyToTech(state,heroes)) ||
                (state->hall_code==FC_AI_ID("unp1") && state->has_slaughterhouse);
            if(saving && state->army+state->alternate>=8)continue;
        }else if(w->features&FC_AI_BUILD){
            const FCAIDevelopmentPlan *plan=&FCAIDevelopmentPlans[f];
            if(FCAIDevelopmentTrain(w,state,plan,heroes))return 1;
            if(w->error)return 0;
            if(FCAIDevelopmentReady(state,heroes) && state->army+state->alternate>=8 &&
               state->hall_code!=plan->tier_three.code &&
               (state->hall_code!=plan->tier_two.code || state->has_support))continue;
        }
        unsigned mix_after=f==FC_AI_UNDEAD && (w->features&FC_AI_TACTICS) ? 8 : 4;
        if(state->army>=mix_after && state->alternate*2<state->army &&
           FCAITrainFrom(w,state->factory,&rule->alternate,FC_AI_PRODUCE_FACTORY,0))return 1;
        if(w->error)return 0;
        if(FCAITrainFrom(w,state->factory,&rule->army,FC_AI_PRODUCE_FACTORY,0))return 1;
    }
    return 0;
}

static FCAIBuildChoice FCAIConsiderBuild(FCLocalAIWork *w,uint32_t code,uint32_t kind,
                                       int32_t gold,int32_t wood,int32_t cost,int32_t wood_cost) {
    if(w->blocked_builds&kind)return (FCAIBuildChoice){0};
    w->status|=FC_AI_BUILD_INTENT;
    if(gold<cost || wood<wood_cost)return (FCAIBuildChoice){0};
    w->status|=FC_AI_HAS_RESOURCES;
    return (FCAIBuildChoice){code,kind};
}


static FCAIBuildChoice FCAIDevelopmentBuild(FCLocalAIWork *w,const FCAIProductionState *state,
                                            const FCAIDevelopmentPlan *plan,unsigned heroes,
                                            int32_t gold,int32_t wood) {
    if(!plan->prerequisite.code)return (FCAIBuildChoice){0};
    if(!state->has_prerequisite && heroes && state->army+state->alternate>=2){
        const FCAIDevelopmentBuilding *b=&plan->prerequisite;
        return FCAIConsiderBuild(w,b->code,FC_AI_BUILD_PREREQUISITE,gold,wood,b->gold,b->lumber);
    }
    if(state->hall_code!=plan->tier_two.code && state->hall_code!=plan->tier_three.code)
        return (FCAIBuildChoice){0};
    if(!state->has_support){
        const FCAIDevelopmentBuilding *b=&plan->support;
        return FCAIConsiderBuild(w,b->code,FC_AI_BUILD_SUPPORT,gold,wood,b->gold,b->lumber);
    }
    if(plan->utility.code && !state->has_utility){
        const FCAIDevelopmentBuilding *b=&plan->utility;
        return FCAIConsiderBuild(w,b->code,FC_AI_BUILD_UTILITY,gold,wood,b->gold,b->lumber);
    }
    if(state->hall_code==plan->tier_three.code && !state->has_late){
        const FCAIDevelopmentBuilding *b=&plan->late;
        return FCAIConsiderBuild(w,b->code,FC_AI_BUILD_LATE,gold,wood,b->gold,b->lumber);
    }
    return (FCAIBuildChoice){0};
}


static FCAIBuildChoice FCAIStockOpeningBuild(FCLocalAIWork *w,const FCAIOpening *opening,
                                             const FCAIProductionState *state,const FCAIProductionRule *rule,
                                             const FCAIWorker *worker,int has_capacity,int32_t gold,int32_t wood,
                                             int *opening_pending) {
    for(unsigned i=0;i<FC_AI_OPENING_STEPS;++i){
        const FCAIOpeningStep *step=&opening->steps[i];
        if(!FCAIOpeningNeeded(step,state) || (step->kind==FC_AI_BUILD_SUPPLY && !has_capacity))continue;
        *opening_pending=1;
        if(w->blocked_builds&step->kind)continue;
        switch(step->kind){
            case FC_AI_BUILD_SUPPLY:
                return FCAIConsiderBuild(w,worker->supply,step->kind,gold,wood,worker->gold,worker->lumber);
            case FC_AI_BUILD_FACTORY:
                return FCAIConsiderBuild(w,rule->factory,step->kind,gold,wood,rule->factory_gold,rule->factory_lumber);
            case FC_AI_BUILD_ALTAR:
                return FCAIConsiderBuild(w,rule->altar,step->kind,gold,wood,180,50);
        }
    }
    return (FCAIBuildChoice){0};
}

static FCAIBuildChoice FCAIConstruction(FCLocalAIWork *w,const FCAIWorker *worker,
                                       const FCAIProductionState states[FC_AI_FACTIONS],
                                       unsigned heroes,int low_food,int headroom,int has_capacity,int32_t gold,int32_t wood) {
    if(!w->allow_build || w->built || !worker->supply)return (FCAIBuildChoice){0};
    unsigned faction=(unsigned)(worker-FCAIWorkers);
    const int plan=(w->features&FC_AI_TRAIN) && faction<FC_AI_FACTIONS;
    const FCAIProductionRule *rule=plan ? &FCAIProductionRules[faction] : 0;
    const FCAIProductionState *s=plan ? &states[faction] : 0;
    const int undead=plan && faction==FC_AI_UNDEAD;
    FCAIBuildChoice choice;
    if(plan && s->hall_code && w->openings[faction].worker_target){
        if(low_food && headroom<=1){
            choice=FCAIConsiderBuild(w,worker->supply,FC_AI_BUILD_SUPPLY,gold,wood,worker->gold,worker->lumber);
            if(choice.code)return choice;
        }
        int pending=0;
        choice=FCAIStockOpeningBuild(w,&w->openings[faction],s,rule,worker,has_capacity,gold,wood,&pending);
        if(pending)return choice;
    }
    /* One Ziggurat cannot fit the first hero, six combat Ghouls and a lumber crew. */
    if(undead && (w->features&FC_AI_TACTICS) && has_capacity &&
       s->supplies==1 && s->has_factory && s->has_altar){
        choice=FCAIConsiderBuild(w,worker->supply,FC_AI_BUILD_SUPPLY,gold,wood,worker->gold,worker->lumber);
        if(choice.code)return choice;
    }
    /* Before the first Ziggurat, the stock opening starts a Crypt with three
       Acolytes. Full supply still takes priority when training is blocked. */
    if(undead && !s->has_factory && s->workers>=3 && headroom>=2){
        choice=FCAIConsiderBuild(w,rule->factory,FC_AI_BUILD_FACTORY,gold,wood,rule->factory_gold,rule->factory_lumber);
        if(choice.code)return choice;
    }
    if(low_food){
        choice=FCAIConsiderBuild(w,worker->supply,FC_AI_BUILD_SUPPLY,gold,wood,worker->gold,worker->lumber);
        if(choice.code || !plan)return choice;
    }
    if(!plan || s->workers<(undead ? 3u : 5u))return (FCAIBuildChoice){0};
    if(!s->has_factory)
        return FCAIConsiderBuild(w,rule->factory,FC_AI_BUILD_FACTORY,gold,wood,rule->factory_gold,rule->factory_lumber);
    if(!heroes && !s->has_altar && (undead || s->army+s->alternate>=2))
        return FCAIConsiderBuild(w,rule->altar,FC_AI_BUILD_ALTAR,gold,wood,180,50);
    if(!undead)return FCAIDevelopmentBuild(w,s,&FCAIDevelopmentPlans[faction],heroes,gold,wood);
    if(!s->has_graveyard && heroes && s->army>=3)
        return FCAIConsiderBuild(w,FC_AI_ID("ugrv"),FC_AI_BUILD_PREREQUISITE,gold,wood,215,0);
    const int tier_two=s->hall_code==FC_AI_ID("unp1") || s->hall_code==FC_AI_ID("unp2");
    if(tier_two && !s->has_tomb)
        return FCAIConsiderBuild(w,FC_AI_ID("utom"),FC_AI_BUILD_UTILITY,gold,wood,130,30);
    if(tier_two && s->has_graveyard && !s->has_slaughterhouse)
        return FCAIConsiderBuild(w,FC_AI_ID("uslh"),FC_AI_BUILD_SUPPORT,gold,wood,140,135);
    if(s->hall_code==FC_AI_ID("unp2") && !s->has_boneyard)
        return FCAIConsiderBuild(w,FC_AI_ID("ubon"),FC_AI_BUILD_LATE,gold,wood,150,200);
    return (FCAIBuildChoice){0};
}
