/* Keep item and destructible orders on the same visible, typed widgets that
   were observed on this tick. Never call a widget native on an untyped handle. */
#define FCAI_ITEM_TAG UINT64_C(0x6974656d2b61676c)
#define FCAI_DESTRUCTIBLE_TAG UINT64_C(0x2b7733642b61676c)

enum { FC_AI_MAX_WORLD_ITEMS=512, FC_AI_MAX_WORLD_DESTRUCTIBLES=8192,
       FC_AI_MAX_REGISTRY_SLOTS=1000000, FC_AI_MAX_PICKUP_HEROES=64 };

typedef struct FCAIWidget {
    uint64_t full,native;
    uint32_t rawcode;
    float x,y;
    uint8_t instant,primary;
} FCAIWidget;

typedef struct FCAIWorldTargets {
    FCAIWidget *items,*destructibles;
    uint64_t location,auto_use_field,book_fields[3];
    uint32_t item_count,destructible_count;
} FCAIWorldTargets;

typedef struct FCAIPickupHero {
    uint64_t unit;
    float x,y;
    int space;
    uint32_t primary;
} FCAIPickupHero;

typedef struct FCAIPickupRoster {
    FCAIPickupHero heroes[FC_AI_MAX_PICKUP_HEROES];
    unsigned count;
} FCAIPickupRoster;

static int FCAIValidWorldBindings(const FCLocalAIWork *w) {
    const FCAIWorldBindings *b=&w->world;
    if((w->inspect && !b->base) || !w->expected_owner || !(w->features&FC_AI_WORLD_TARGETS))
        return !b->base && !b->convert && !b->location && !b->move_location &&
               !b->location_visible && !b->remove_location;
    return b->base && b->convert && b->location && b->move_location &&
        b->location_visible && b->remove_location &&
        (!(w->features&FC_AI_PICKUP) ||
         (b->item_type && b->item_x && b->item_y && b->item_invulnerable && b->item_visible &&
          b->item_owned && b->inventory_size && b->inventory_item && b->item_boolean_field &&
          b->item_boolean && b->unit_integer_field && b->unit_integer && b->item_ability &&
          b->ability_integer_field && b->ability_integer)) &&
        (!(w->features&FC_AI_DESTRUCTIBLES) ||
         (b->destructible_type && b->destructible_x && b->destructible_y && b->destructible_invulnerable));
}

static int FCAIValidDestructibleTypes(const FCLocalAIWork *w) {
    uint32_t count=w->destructible_type_count;
    if(w->destructible_reserved || count>FC_AI_MAX_DESTRUCTIBLE_TYPES ||
       (count && (!w->world.base || !(w->features&FC_AI_DESTRUCTIBLES))))return 0;
    uint32_t last=0;
    for(uint32_t i=0;i<count;++i){
        uint32_t code=w->selectable_destructibles[i];
        if(code<=last)return 0;
        last=code;
    }
    return 1;
}

static int FCAIDestructibleSelectable(const FCLocalAIWork *w,uint32_t rawcode) {
    uint32_t low=0,high=w->destructible_type_count;
    while(low<high){
        uint32_t mid=low+(high-low)/2,code=w->selectable_destructibles[mid];
        if(code==rawcode)return 1;
        if(code<rawcode)low=mid+1;
        else high=mid;
    }
    return 0;
}

/* -1 means no inventory ability. A full active inventory can still use a powerup. */
static int FCAIInventorySpace(FCLocalAIWork *w,uint64_t unit) {
    w->world_stage=1;
    int32_t size=w->world.inventory_size(unit);
    int available=size>0?0:-1;
    for(int32_t i=0;i<size && i<32;++i){
        if(!w->world.inventory_item(unit,i)){available=1;break;}
    }
    w->world_stage=0;
    return available;
}

static void FCAICollectPickupHeroes(FCLocalAIWork *w,uint64_t group,FCAIPickupRoster *roster) {
    uint64_t hero=w->unit_type(FC_AI_HERO);
    uint64_t primary=w->world.unit_integer_field(0x75707261u); /* upra */
    w->group_clear(group);
    w->enum_owner(group,w->owner,0);
    for(unsigned i=0;i<FC_AI_MAX_VISITS && roster->count<FC_AI_MAX_PICKUP_HEROES;++i){
        uint64_t unit=FCLocalAIPop(w,group);
        if(!unit)break;
        if(!FCLocalAIOwnUsable(w,unit) || !w->is_type(unit,hero) ||
           w->current_order(unit) || w->order_count(unit)!=0)continue;
        int space=FCAIInventorySpace(w,unit);
        if(space<0)continue;
        float x=FullCloneReal(w->x(unit)),y=FullCloneReal(w->y(unit));
        if(!FullCloneFinite(x) || !FullCloneFinite(y))continue;
        /* The runtime values are 1 strength, 2 intelligence, 3 agility. */
        int32_t attr=primary?w->world.unit_integer(unit,primary):0;
        uint32_t bit=attr>=1 && attr<=3 ? 1u<<(attr-1) : 0;
        roster->heroes[roster->count++]=(FCAIPickupHero){unit,x,y,space,bit};
    }
    w->group_clear(group);
}

static FCAIPickupHero *FCAIFindPickupHero(FCAIPickupRoster *roster,uint64_t unit) {
    for(unsigned i=0;i<roster->count;++i)
        if(roster->heroes[i].unit==unit)return &roster->heroes[i];
    return 0;
}

static int FCAIItemCanUseOnPickup(FCLocalAIWork *w,const FCAIWorldTargets *targets,uint64_t item) {
    return targets->auto_use_field && w->world.item_boolean(item,targets->auto_use_field);
}

static uint8_t FCAIBookAttribute(FCLocalAIWork *w,const FCAIWorldTargets *targets,uint64_t item) {
    uint8_t attributes=0;
    for(int32_t i=0;i<16;++i){
        uint64_t ability=w->world.item_ability(item,i);
        if(!ability)break;
        for(unsigned stat=0;stat<3;++stat)
            if(targets->book_fields[stat] && w->world.ability_integer(ability,targets->book_fields[stat],0)>0)
                attributes|=(uint8_t)(1u<<stat);
    }
    /* A boost to several stats, like a Tome of Knowledge, goes to the nearest hero. */
    return attributes && !(attributes&(attributes-1))?attributes:0;
}

static int FCAIIsBestPickupHero(const FCAIPickupRoster *roster,const FCAIPickupHero *picker,
                               const FCAIWidget *item,float maximum) {
    float best=maximum;
    uint64_t chosen=0;
    int matching=0;
    for(unsigned i=0;i<roster->count;++i){
        const FCAIPickupHero *hero=&roster->heroes[i];
        if(!hero->unit || (!hero->space && !item->instant))continue;
        float dx=hero->x-item->x,dy=hero->y-item->y,distance=dx*dx+dy*dy;
        if(!FullCloneFinite(distance) || distance>maximum)continue;
        int match=(hero->primary&item->primary)!=0;
        if(!chosen || match>matching || (match==matching &&
           (distance<best || (distance==best && hero->unit<chosen)))){
            chosen=hero->unit;
            matching=match;
            best=distance;
        }
    }
    return chosen==picker->unit;
}

static int FCAIWidgetVisible(FCLocalAIWork *w,uint64_t location,FCAIWidget *target,int item) {
    const FCAIWorldBindings *b=&w->world;
    uint64_t h=target->native;
    w->world_stage=5;
    int32_t rawcode=item?b->item_type(h):b->destructible_type(h);
    if(!rawcode || (uint32_t)rawcode!=target->rawcode)return 0;
    w->world_stage=6;
    float life=FullCloneReal(w->life(h));
    if(!FullCloneFinite(life) || !(life>0.405f))return 0;
    w->world_stage=7;
    if(item){
        if(b->item_invulnerable(h) || !b->item_visible(h) || b->item_owned(h))return 0;
        target->x=FullCloneReal(b->item_x(h));
        target->y=FullCloneReal(b->item_y(h));
    }else{
        if(!FCAIDestructibleSelectable(w,target->rawcode) || b->destructible_invulnerable(h))return 0;
        target->x=FullCloneReal(b->destructible_x(h));
        target->y=FullCloneReal(b->destructible_y(h));
    }
    w->world_stage=8;
    if(!FullCloneFinite(target->x) || !FullCloneFinite(target->y))return 0;
    b->move_location(location,&target->x,&target->y);
    return b->location_visible(location,w->owner);
}

static uint64_t FCAIWidgetObject(uint64_t owner,uint64_t full,uint32_t rawcode,uint64_t tag) {
    if(!owner || *(uint64_t*)(uintptr_t)(owner+0x18)!=tag)return 0;
    uint64_t obj=*(uint64_t*)(uintptr_t)(owner+bridge_profile.owner_data);
    if(!obj || *(uint64_t*)(uintptr_t)(obj+bridge_profile.object_handle)!=full ||
       *(uint32_t*)(uintptr_t)(obj+bridge_profile.object_rawcode)!=rawcode)return 0;
    return obj;
}

static void FCAICollectWorld(FCLocalAIWork *w,FCAIWorldTargets *targets) {
    w->world_stage=2;
    HANDLE heap=GetProcessHeap();
    if(w->features&FC_AI_PICKUP){
        targets->items=HeapAlloc(heap,0,sizeof(*targets->items)*FC_AI_MAX_WORLD_ITEMS);
        targets->auto_use_field=w->world.item_boolean_field(0x69706f77u); /* ipow */
        static const uint32_t fields[]={0x49737472u,0x49696e74u,0x49616769u}; /* Istr, Iint, Iagi */
        for(unsigned i=0;i<3;++i)targets->book_fields[i]=w->world.ability_integer_field(fields[i]);
    }
    if(w->destructible_type_count)
        targets->destructibles=HeapAlloc(heap,0,sizeof(*targets->destructibles)*FC_AI_MAX_WORLD_DESTRUCTIBLES);
    if(((w->features&FC_AI_PICKUP) && !targets->items) ||
       (w->destructible_type_count && !targets->destructibles)){
        w->error=1008;
        return;
    }
    const FCAIWorldBindings *b=&w->world;
    float origin=0;
    targets->location=b->location(&origin,&origin);
    if(!targets->location){w->error=1008;return;}
    uint64_t root=*(uint64_t*)(uintptr_t)(b->base+bridge_profile.registry_root_rva);
    if(!root){w->world_stage=0;return;}
    const uint32_t offsets[]={bridge_profile.primary,bridge_profile.alternate};
    for(unsigned table_index=0;table_index<2;++table_index){
        uint64_t at=root+offsets[table_index];
        uint64_t table=*(uint64_t*)(uintptr_t)at;
        uint32_t count=*(uint32_t*)(uintptr_t)(at+bridge_profile.table_count);
        if(!table || count>FC_AI_MAX_REGISTRY_SLOTS)continue;
        for(uint32_t i=0;i<count;++i){
            w->world_stage=3;
            uint64_t slot=table+(uint64_t)i*bridge_profile.stride;
            if(*(uint32_t*)(uintptr_t)slot!=0xfffffffeu)continue;
            uint64_t owner=*(uint64_t*)(uintptr_t)(slot+bridge_profile.slot_owner);
            if(!owner)continue;
            uint64_t tag=*(uint64_t*)(uintptr_t)(owner+0x18);
            int item=tag==FCAI_ITEM_TAG;
            if(item ? (!targets->items || targets->item_count>=FC_AI_MAX_WORLD_ITEMS) :
               (tag!=FCAI_DESTRUCTIBLE_TAG || !targets->destructibles ||
                targets->destructible_count>=FC_AI_MAX_WORLD_DESTRUCTIBLES))continue;
            uint64_t obj=*(uint64_t*)(uintptr_t)(owner+bridge_profile.owner_data);
            if(!obj)continue;
            uint64_t full=*(uint64_t*)(uintptr_t)(obj+bridge_profile.object_handle);
            uint32_t rawcode=*(uint32_t*)(uintptr_t)(obj+bridge_profile.object_rawcode);
            if(!rawcode || (!item && !FCAIDestructibleSelectable(w,rawcode)) ||
               BridgeProfileResolveOwner(b->base,full,1)!=owner)continue;
            w->world_stage=4;
            FCAIWidget target={.full=full,.native=b->convert(obj,1),.rawcode=rawcode};
            if(!target.native || !FCAIWidgetVisible(w,targets->location,&target,item))continue;
            if(item){
                target.instant=FCAIItemCanUseOnPickup(w,targets,target.native);
                if(target.instant)target.primary=FCAIBookAttribute(w,targets,target.native);
                targets->items[targets->item_count++]=target;
            }
            else targets->destructibles[targets->destructible_count++]=target;
        }
    }
    w->world_items=targets->item_count;
    w->world_destructibles=targets->destructible_count;
    w->world_stage=0;
}

static void FCAICollectWidgetTargets(FCAITargetList *list,FCAIWidget *widgets,uint32_t count,
                                    uint32_t kind,float x,float y,float maximum,
                                    const FCAIPickupRoster *roster,const FCAIPickupHero *picker) {
    for(uint32_t i=0;i<count;++i){
        FCAIWidget *widget=&widgets[i];
        if(!widget->native)continue;
        float dx=widget->x-x,dy=widget->y-y,distance=dx*dx+dy*dy;
        if(!FullCloneFinite(distance) || distance>maximum)continue;
        if(picker && ((!picker->space && !widget->instant) ||
                      !FCAIIsBestPickupHero(roster,picker,widget,maximum)))continue;
        FCAIConsiderTarget(list,(FCAITarget){0,widget,distance,kind},maximum);
    }
}

static int FCAIOrderWidget(FCLocalAIWork *w,uint64_t unit,const FCAIWorldTargets *targets,
                           FCAIWidget *widget,int item,float x,float y,float maximum) {
    const FCAIWorldBindings *b=&w->world;
    uint64_t tag=item?FCAI_ITEM_TAG:FCAI_DESTRUCTIBLE_TAG;
    w->world_stage=4;
    uint64_t owner=BridgeProfileResolveOwner(b->base,widget->full,1);
    uint64_t obj=FCAIWidgetObject(owner,widget->full,widget->rawcode,tag);
    int valid=obj && b->convert(obj,1)==widget->native && FCAIWidgetVisible(w,targets->location,widget,item);
    w->world_stage=0;
    if(!valid){widget->native=0;return 0;}
    float dx=widget->x-x,dy=widget->y-y;
    if(dx*dx+dy*dy>maximum)return 0;
    if(item){
        int space=FCAIInventorySpace(w,unit);
        if(space<0 || (!space && !FCAIItemCanUseOnPickup(w,targets,widget->native)))return 0;
    }
    w->world_stage=9;
    int ordered=w->attack(unit,item?FC_AI_ORDER_SMART:FC_AI_ORDER_ATTACK,widget->native);
    w->world_stage=0;
    if(item && ordered)widget->native=0;
    return ordered;
}

static int FCAIOrderClosestTarget(FCLocalAIWork *w,uint64_t nearby,uint64_t unit,uint64_t flying,
                                 int hits_ground,int hits_flying,uint32_t combat,FCAIWorldTargets *targets,
                                 const FCAIPickupRoster *roster,const FCAIPickupHero *picker) {
    float x=FullCloneReal(w->x(unit)),y=FullCloneReal(w->y(unit)),radius=(float)w->radius;
    if(!FullCloneFinite(x) || !FullCloneFinite(y))return 0;
    float maximum=radius*radius;
    FCAITargetList list={0};
    if(combat&FC_AI_CREEPS){
        int32_t hp=w->max_life(unit);
        if(hp<=0 || FullCloneReal(w->life(unit))<0.6f*(float)hp)combat&=~FC_AI_CREEPS;
    }
    if(combat)FCAICollectCombatTargets(w,nearby,unit,flying,hits_ground,hits_flying,combat,x,y,&list);
    if(picker)FCAICollectWidgetTargets(&list,targets->items,targets->item_count,FC_AI_TARGET_ITEM,
                                      x,y,maximum,roster,picker);
    if(hits_ground)FCAICollectWidgetTargets(&list,targets->destructibles,targets->destructible_count,
                                           FC_AI_TARGET_DESTRUCTIBLE,x,y,maximum,roster,0);
    for(unsigned i=0;i<list.count && !w->error;++i){
        if(!FCLocalAICanOrder(w,unit,0))return 0;
        FCAITarget *candidate=&list.rows[i];
        if(candidate->widget){
            if(FCAIOrderWidget(w,unit,targets,candidate->widget,candidate->kind==FC_AI_TARGET_ITEM,
                               x,y,maximum))return 1;
        }else if(FCAIAttackableUnit(w,candidate->unit) && w->attack(unit,FC_AI_ORDER_ATTACK,candidate->unit)){
            if(candidate->kind==FC_AI_TARGET_CREEP)++w->creeps;
            return 1;
        }
    }
    return 0;
}
