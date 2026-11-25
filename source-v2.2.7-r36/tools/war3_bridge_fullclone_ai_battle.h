/* A bounded squad uses normal attack-move orders. Town and unit targets come
   from the current map, and existing player orders stay in place. */
enum {FC_AI_DEFEND=1,FC_AI_RALLY=2,FC_AI_CREEP_WAVE=3,FC_AI_ADVANCE=4};
enum {FC_AI_MAX_HOMES=4,FC_AI_ORDER_MOVE=851986};

typedef struct FCAIBattlePoint {
    float x,y;
} FCAIBattlePoint;

typedef struct FCAIBattleTarget {
    FCAIBattlePoint point,center;
    uint64_t unit;
    float radius;
    int creep_level,allow_air;
} FCAIBattleTarget;

typedef struct FCAIBattleUnit {
    uint64_t unit;
    FCAIBattlePoint pos;
    uint8_t hero;
} FCAIBattleUnit;

typedef struct FCAIBattleGroup {
    FCAIBattlePoint homes[FC_AI_MAX_HOMES];
    FCAIBattleUnit units[FC_AI_MAX_UNITS];
    unsigned home_count,count,faction;
} FCAIBattleGroup;

static int FCAIBattlePosition(FCLocalAIWork *w,uint64_t unit,FCAIBattlePoint *point) {
    point->x=FullCloneReal(w->x(unit));
    point->y=FullCloneReal(w->y(unit));
    return FullCloneFinite(point->x) && FullCloneFinite(point->y) &&
        point->x>=-1000000.f && point->x<=1000000.f &&
        point->y>=-1000000.f && point->y<=1000000.f;
}

static float FCAIBattleDistance(FCAIBattlePoint a,FCAIBattlePoint b) {
    float dx=a.x-b.x,dy=a.y-b.y;
    return dx*dx+dy*dy;
}

static unsigned FCAIBattleFaction(uint32_t code) {
    for(unsigned f=0;f<FC_AI_FACTIONS;++f){
        const uint32_t *halls=FCAIWorkers[f].halls;
        if(code==halls[0] || code==halls[1] || code==halls[2])return f;
    }
    return FC_AI_FACTIONS;
}

static void FCAICollectBattleGroup(FCLocalAIWork *w,uint64_t own,FCAIBattleGroup *group) {
    uint64_t structure=w->unit_type(FC_AI_STRUCTURE),worker=w->unit_type(FC_AI_PEON),hero=w->unit_type(FC_AI_HERO);
    uint64_t ground=w->unit_type(FC_AI_ATTACKS_GROUND),air=w->unit_type(FC_AI_ATTACKS_FLYING);
    w->group_clear(own);
    w->enum_owner(own,w->owner,0);
    for(uint32_t i=0;i<FC_AI_MAX_VISITS;++i){
        uint64_t unit=FCLocalAIPop(w,own);
        if(!unit)break;
        if(!FCLocalAIOwnUsable(w,unit))continue;
        FCAIBattlePoint pos;
        if(!FCAIBattlePosition(w,unit,&pos))continue;
        if(w->is_type(unit,structure)){
            unsigned faction=FCAIBattleFaction(w->selection.unit_type_id(unit));
            if(faction==FC_AI_FACTIONS || group->home_count>=FC_AI_MAX_HOMES)continue;
            if(!group->home_count)group->faction=faction;
            group->homes[group->home_count++]=pos;
            continue;
        }
        if(group->count>=FC_AI_MAX_UNITS ||
           (w->is_type(unit,worker) && w->selection.unit_type_id(unit)!=FC_AI_ID("ugho")) ||
           w->current_order(unit) || w->order_count(unit)!=0)continue;
        if(!w->is_type(unit,ground) && !w->is_type(unit,air))continue;
        int32_t maximum=w->max_life(unit);
        if(maximum<=0 || FullCloneReal(w->life(unit))<0.60f*(float)maximum)continue;
        group->units[group->count++]=(FCAIBattleUnit){unit,pos,w->is_type(unit,hero)};
    }
}

/* A visible town threat takes precedence over a new raid. The neutral scan
   selects only ordinary creeps the ready force has a chance to defeat. */
static int FCAIVisibleBattleTarget(FCLocalAIWork *w,uint64_t nearby,FCAIBattleTarget *target) {
    int32_t neutral=w->neutral_hostile();
    FCAIBattlePoint center=target->center;
    float radius=target->radius;
    int creep_level=target->creep_level;
    target->unit=0;
    uint64_t flying=w->unit_type(FC_AI_FLYING),structure=w->unit_type(FC_AI_STRUCTURE);
    float nearest=radius*radius;
    FCAIEnumerate(w,nearby,center.x,center.y,radius,FC_AI_MAX_COMBAT_TARGETS);
    for(unsigned i=0;i<FC_AI_MAX_COMBAT_TARGETS;++i){
        uint64_t unit=FCLocalAIPop(w,nearby);
        if(!unit)break;
        if(!w->enemy(unit,w->owner) || !FCAIAttackableUnit(w,unit))continue;
        if(!target->allow_air && w->is_type(unit,flying))continue;
        uint64_t player=w->owning_player(unit);
        if(!player || player==w->owner)continue;
        int neutral_creep=w->player_id(player)==neutral;
        if(creep_level){
            if(!neutral_creep || w->is_type(unit,structure))continue;
            int32_t level=w->unit_level(unit);
            if(level<1 || level>creep_level)continue;
        }else if(neutral_creep || !w->player_enemy(w->owner,player)){
            continue;
        }
        FCAIBattlePoint point;
        if(!FCAIBattlePosition(w,unit,&point))continue;
        float range=FCAIBattleDistance(center,point);
        if(range>nearest)continue;
        nearest=range;
        target->unit=unit;
        target->point=point;
    }
    return target->unit && !w->error;
}

static int FCAIComputerStart(FCLocalAIWork *w,FCAIBattlePoint center,FCAIBattlePoint *target) {
    float nearest=1.0e12f;
    int found=0;
    uint64_t playing=w->player_slot_state(1),computer=w->map_control(1);
    for(int32_t slot=0;slot<24;++slot){
        uint64_t player=w->player(slot);
        if(!player || player==w->owner || w->slot_state(player)!=playing ||
           w->controller(player)!=computer || !w->player_enemy(w->owner,player))continue;
        int32_t index=w->start_location(player);
        if(index<0 || index>=24)continue;
        FCAIBattlePoint point={FullCloneReal(w->start_x(index)),FullCloneReal(w->start_y(index))};
        if(!FullCloneFinite(point.x) || !FullCloneFinite(point.y) ||
           point.x< -1000000.f || point.x>1000000.f || point.y< -1000000.f || point.y>1000000.f ||
           (point.x==0.f && point.y==0.f))continue;
        float range=FCAIBattleDistance(center,point);
        if(range<1200.f*1200.f || range>nearest)continue;
        found=1;
        nearest=range;
        *target=point;
    }
    return found;
}

static void FCAISendBattleGroup(FCLocalAIWork *w,const FCAIBattleGroup *group,uint64_t nearby,unsigned mode,
                                FCAIBattleTarget *target,FCAIBattlePoint leader) {
    int rally=mode==FC_AI_RALLY;
    float ready_radius=1050.f*1050.f;
    uint32_t order=rally ? FC_AI_ORDER_MOVE : FC_AI_ORDER_ATTACK;
    w->tactics_mode=mode;
    for(unsigned i=0;i<group->count && !w->error && w->changed<FC_AI_MAX_UNITS;++i){
        const FCAIBattleUnit *unit=&group->units[i];
        float range=FCAIBattleDistance(unit->pos,leader);
        if(rally && (range<=ready_radius || unit->hero))continue;
        if((mode==FC_AI_ADVANCE || mode==FC_AI_CREEP_WAVE) && range>ready_radius)continue;
        if(!FCLocalAICanOrder(w,unit->unit,0) || w->order_count(unit->unit)!=0)continue;
        if(target->unit && !FCAIAttackableUnit(w,target->unit) &&
           !FCAIVisibleBattleTarget(w,nearby,target))break;
        if(w->point_order(unit->unit,order,&target->point.x,&target->point.y)){
            ++w->tactics_issued;
            ++w->changed;
        }
    }
}

static void FCAIBattleOrders(FCLocalAIWork *w,uint64_t own,uint64_t nearby) {
    FCAIBattleGroup group={0};
    FCAICollectBattleGroup(w,own,&group);
    if(w->error || !group.home_count || !group.count)return;

    FCAIBattlePoint leader=group.homes[0];
    FCAIBattleTarget target={0};
    int has_hero=0,allow_air=0;
    uint64_t attacks_air=w->unit_type(FC_AI_ATTACKS_FLYING);
    for(unsigned i=0;i<group.count;++i){
        const FCAIBattleUnit *unit=&group.units[i];
        if(unit->hero && !has_hero){leader=unit->pos;has_hero=1;}
        if(w->is_type(unit->unit,attacks_air))allow_air=1;
    }
    for(unsigned i=0;i<group.home_count;++i){
        target=(FCAIBattleTarget){.center=group.homes[i],.radius=1200.f,.allow_air=allow_air};
        if(FCAIVisibleBattleTarget(w,nearby,&target)){
            FCAISendBattleGroup(w,&group,nearby,FC_AI_DEFEND,&target,leader);
            return;
        }
        if(w->error)return;
    }
    unsigned ready=0,total=0;
    for(unsigned i=0;i<group.count;++i){
        const FCAIBattleUnit *unit=&group.units[i];
        if(unit->hero)continue;
        ++total;
        if(FCAIBattleDistance(unit->pos,leader)<=1050.f*1050.f)++ready;
    }
    w->tactics_ready=ready;
    static const unsigned defaults[FC_AI_FACTIONS]={2,2,6,2};
    unsigned minimum=w->wave_troops[group.faction] ? w->wave_troops[group.faction] : defaults[group.faction];
    if(!has_hero || total<minimum)return;
    if(ready<minimum){
        target=(FCAIBattleTarget){.point=leader};
        FCAISendBattleGroup(w,&group,nearby,FC_AI_RALLY,&target,leader);
        return;
    }
    target=(FCAIBattleTarget){.center=leader,.radius=(float)w->radius,.allow_air=allow_air};
    if(w->features&FC_AI_CREEPS){
        target.creep_level=2+(int)ready/2;
        if(FCAIVisibleBattleTarget(w,nearby,&target)){
            FCAISendBattleGroup(w,&group,nearby,FC_AI_CREEP_WAVE,&target,leader);
            return;
        }
    }
    if(w->error)return;
    target.creep_level=0;
    if(FCAIVisibleBattleTarget(w,nearby,&target) ||
       (!w->error && FCAIComputerStart(w,leader,&target.point))){
        FCAISendBattleGroup(w,&group,nearby,FC_AI_ADVANCE,&target,leader);
    }
}
