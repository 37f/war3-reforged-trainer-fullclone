/* v0.2: snapshot first, create with the final owner, verify before removing a
 * replaced source. Map-script state is deliberately not copied or executed. */
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include "legacy_protocol.h"
#define INVENTORY 0x41496e76u
static float real(uint32_t bits){union{uint32_t i;float f;}v;v.i=bits;return v.f;}
static int valid_id(uint32_t raw){for(int i=0;i<4;i++){unsigned c=(raw>>(i*8))&255;if(!((c>='0'&&c<='9')||(c>='A'&&c<='Z')||(c>='a'&&c<='z')))return 0;}return 1;}
static int same(NativeFns* n,const UnitRow* u){return n->GetUnitTypeId(u->handle)==u->type && n->GetPlayerId(n->GetOwningPlayer(u->handle))==(int)u->owner;}
static int read_source(UnitRow* row,UnitSpec* out,NativeFns* n){
    memset(out,0,sizeof(*out));out->base=*row;uint32_t u=row->handle;
    if(!same(n,row))return 105;
    out->x=real(n->GetUnitX(u));out->y=real(n->GetUnitY(u));out->facing=real(n->GetUnitFacing(u));
    if(!isfinite(out->x)||!isfinite(out->y)||!isfinite(out->facing))return 120;
    out->paused=n->IsUnitPaused(u)?1:0;
    if(row->hero){out->xp=n->GetHeroXP(u);out->points=n->GetHeroSkillPoints(u);out->xp_paused=n->IsSuspendedXP(u)?1:0;if(out->xp>2000000000u || out->points>1000000u)return 120;}
    int error=n->ReadAbilities(u,out->abilities,&out->ability_count,&out->item_nodes);if(error)return error;
    for(int i=0;i<6;i++){
        ItemRow* item=&out->items[i];item->handle=n->UnitItemInSlot(u,i);if(!item->handle)continue;
        item->type=n->GetItemTypeId(item->handle);item->charges=n->GetItemCharges(item->handle);item->life=real(n->GetWidgetLife(item->handle));
        item->invulnerable=n->IsItemInvulnerable(item->handle)?1:0;item->pawnable=n->IsItemPawnable(item->handle)?1:0;
        if(!valid_id(item->type)||item->charges<0||!isfinite(item->life)||item->life<0)return 120;
        for(int j=0;j<i;j++)if(out->items[j].handle==item->handle)return 120;
    }
    return same(n,row)?0:105;
}
static int ready_unit(NativeFns* n,uint32_t u,uint32_t raw,uint32_t owner){return n->GetUnitTypeId(u)==raw && n->GetPlayerId(n->GetOwningPlayer(u))==(int)owner;}
static int add_abilities(NativeFns* n,uint32_t unit,const UnitSpec* s,uint32_t* stage){
    for(unsigned i=0;i<s->ability_count;i++){
        AbilityRow a=s->abilities[i];
        /* Item-granted abilities are rebuilt by the new inventory, not added
         * again as ordinary unit abilities (which would double their bonuses). */
        if((a.flags&0x20) || !valid_id(a.rawcode))continue;
        *stage=a.rawcode;
        int level=n->GetUnitAbilityLevel(unit,a.rawcode);
        if(!level && !n->UnitAddAbility(unit,a.rawcode))return 123;
        if(n->GetUnitAbilityLevel(unit,a.rawcode)!=(int)a.level)n->SetUnitAbilityLevel(unit,a.rawcode,a.level);
        if(n->GetUnitAbilityLevel(unit,a.rawcode)!=(int)a.level)return 123;
    }
    return 0;
}
static int ensure_inventory(NativeFns* n,uint32_t unit,const UnitSpec* s){
    int needed=0;for(int i=0;i<6;i++){if(s->items[i].handle)needed=1;if(n->UnitItemInSlot(unit,i))return 124;}
    if(needed && !n->GetUnitAbilityLevel(unit,INVENTORY))n->UnitAddAbility(unit,INVENTORY);
    return needed && !n->GetUnitAbilityLevel(unit,INVENTORY)?124:0;
}
static int copy_items(NativeFns* n,uint32_t unit,const UnitSpec* s,uint32_t* owned){
    for(int slot=0;slot<6;slot++){
        ItemRow item=s->items[slot];if(!item.handle)continue;
        float x=s->x,y=s->y;uint32_t h=n->CreateItem(item.type,&x,&y);owned[slot]=h;
        if(!h || n->GetItemTypeId(h)!=item.type)return 124;
        n->SetItemCharges(h,item.charges);n->SetWidgetLife(h,&item.life);n->SetItemInvulnerable(h,item.invulnerable);n->SetItemPawnable(h,item.pawnable);
        if(!n->UnitAddItem(unit,h))return 124;
        if(n->UnitItemInSlot(unit,slot)!=h && !n->UnitDropItemSlot(unit,h,slot))return 124;
        if(n->UnitItemInSlot(unit,slot)!=h || n->GetItemTypeId(h)!=item.type || n->GetItemCharges(h)!=item.charges ||
           fabsf(real(n->GetWidgetLife(h))-item.life)>.05f || !!n->IsItemInvulnerable(h)!=!!item.invulnerable || !!n->IsItemPawnable(h)!=!!item.pawnable)return 124;
    }
    return 0;
}
static int set_state(NativeFns* n,uint32_t u,const UnitSpec* s,int target_hero,uint32_t* warnings){
    if(s->base.hero && target_hero){
        n->SuspendHeroXP(u,0);n->SetHeroXP(u,s->xp,0);
        int level=n->GetHeroLevel(u);if(level<s->base.level)n->SetHeroLevel(u,s->base.level,0);else if(level>s->base.level)n->UnitStripHeroLevel(u,level-s->base.level);
        n->SetHeroStr(u,s->base.strength,1);n->SetHeroAgi(u,s->base.agility,1);n->SetHeroInt(u,s->base.intelligence,1);
        n->UnitModifySkillPoints(u,(int)s->points-n->GetHeroSkillPoints(u));n->SuspendHeroXP(u,s->xp_paused);
        if(n->GetHeroLevel(u)!=s->base.level || n->GetHeroXP(u)!=(int)s->xp || n->GetHeroSkillPoints(u)!=(int)s->points ||
           n->GetHeroStr(u,0)!=s->base.strength || n->GetHeroAgi(u,0)!=s->base.agility || n->GetHeroInt(u,0)!=s->base.intelligence || !!n->IsSuspendedXP(u)!=!!s->xp_paused)return 125;
    }else if(s->base.hero && !target_hero)*warnings|=2;
    if(s->base.max_hp<1 || s->base.max_hp>100000000 || s->base.max_mp<0 || s->base.max_mp>100000000)return 120;
    int hp=(int)floorf(s->base.max_hp+.5f),mp=(int)floorf(s->base.max_mp+.5f);
    if(fabsf(hp-s->base.max_hp)>.01f || fabsf(mp-s->base.max_mp)>.01f)*warnings|=1;
    if(fabsf(real(n->GetUnitState(u,1))-hp)>.05f)n->BlzSetUnitMaxHP(u,hp);
    if(fabsf(real(n->GetUnitState(u,3))-mp)>.05f)n->BlzSetUnitMaxMana(u,mp);
    float life=s->base.hp,mana=s->base.mp;if(life>hp)life=(float)hp;if(mana>mp)mana=(float)mp;
    n->SetUnitState(u,0,&life);n->SetUnitState(u,2,&mana);n->PauseUnit(u,s->paused);
    if(fabsf(real(n->GetUnitState(u,0))-life)>.05f || fabsf(real(n->GetUnitState(u,2))-mana)>.05f ||
       fabsf(real(n->GetUnitState(u,1))-hp)>.05f || fabsf(real(n->GetUnitState(u,3))-mp)>.05f || !!n->IsUnitPaused(u)!=!!s->paused)return 125;
    return 0;
}
#ifdef LEGACY_TEST_ONLY
#include "legacy_test_support.h"
#endif
static int verify_contents(NativeFns* n,uint32_t u,const UnitSpec* s,int replacement){
    for(unsigned i=0;!replacement && i<s->ability_count;i++){
        AbilityRow a=s->abilities[i];if((a.flags&0x20) || !valid_id(a.rawcode))continue;
        if(n->GetUnitAbilityLevel(u,a.rawcode)!=(int)a.level)return 123;
    }
    for(int slot=0;slot<6;slot++){
        ItemRow item=s->items[slot];uint32_t h=n->UnitItemInSlot(u,slot);
        if(!item.handle){if(h)return 124;continue;}
        if(!h || (replacement?h!=item.handle:h==item.handle) || n->GetItemTypeId(h)!=item.type || n->GetItemCharges(h)!=item.charges ||
           fabsf(real(n->GetWidgetLife(h))-item.life)>.05f || !!n->IsItemInvulnerable(h)!=!!item.invulnerable || !!n->IsItemPawnable(h)!=!!item.pawnable)return 124;
    }
    return 0;
}
int legacy_clone_execute(Packet* p,NativeFns* n){
#ifdef LEGACY_TEST_ONLY
    if(p->action==TEST_SETUP)return legacy_test_setup(p,n);
#endif
    if(p->action!=CLONE && p->action!=REPLACE && p->action!=PREVIEW)return 106;
    if(p->world!=p->expected_world || p->expected_count!=p->unit_count)return 105;
    if(!p->unit_count)return 0;
    unsigned count=p->action==CLONE?(unsigned)p->a:1;
    if(!count || count>200 || p->unit_count>200/count || p->kind>2)return 106;
    if(p->action==REPLACE && !valid_id((uint32_t)p->b))return 106;
    for(unsigned i=0;i<p->unit_count;i++){
        UnitRow* u=&p->units[i];int found=0;
        for(unsigned j=0;j<p->expected_count;j++)if(p->expected_units[j]==u->handle && p->expected_types[j]==u->type && p->expected_owners[j]==u->owner)found=1;
        if(!found)return 105;
    }
    UnitSpec* sources=calloc(p->unit_count,sizeof(UnitSpec));if(!sources)return 120;int error=0;unsigned total=p->unit_count;
    for(unsigned i=0;i<total;i++){error=read_source(&p->units[i],&sources[i],n);if(error)goto finish;}
    p->detail=sources[0];if(p->action==PREVIEW)goto finish;
    for(unsigned i=0;i<total;i++)if(sources[i].base.hp<=.405f){error=126;goto finish;}
    for(unsigned i=0;i<total;i++){
        UnitSpec* s=&sources[i];uint32_t owner=p->action==REPLACE?s->base.owner:p->kind==0?p->local_player:p->kind==1?s->base.owner:p->target;
        if(owner>=p->player_count){error=106;goto finish;}
        uint32_t player=n->Player(owner);int neutral=0;for(int k=24;k<28;k++)if(n->Player(k)==player)neutral=1;
        if(!player || n->GetPlayerId(player)!=(int)owner || (!neutral && n->GetPlayerSlotState(player)!=1)){error=110;goto finish;}
        for(unsigned j=0;j<count;j++){
            if(!same(n,&s->base)){error=105;goto finish;}
            uint32_t raw=p->action==REPLACE?(uint32_t)p->b:s->base.type;
            float x=s->x,y=s->y,f=s->facing;
            if(p->action==CLONE){float angle=(float)(j+1)*2.39996323f,radius=64.f*sqrtf((float)j+1);x+=cosf(angle)*radius;y+=sinf(angle)*radius;}
            uint32_t u=n->CreateUnit(player,raw,&x,&y,&f),owned[6]={0};int transferred=0;
            if(!u){error=121;goto finish;}
            p->applied++;p->created[p->created_count++]=u;
            if(!ready_unit(n,u,raw,owner)){error=122;goto finish;}
            /* Replacement keeps the new unit type's own skill template. */
            if(p->action==CLONE){error=add_abilities(n,u,s,&p->stage);if(error)goto candidate_error;}
            error=ensure_inventory(n,u,s);if(error)goto candidate_error;
            if(p->action==CLONE){error=copy_items(n,u,s,owned);if(error)goto candidate_error;}
            if(!ready_unit(n,u,raw,owner) || !same(n,&s->base)){error=122;goto candidate_error;}
            if(p->action==REPLACE){
                for(int slot=0;slot<6;slot++){
                    ItemRow item=s->items[slot];if(!item.handle)continue;
                    if(n->UnitItemInSlot(s->base.handle,slot)!=item.handle || n->GetItemTypeId(item.handle)!=item.type){error=124;goto candidate_error;}
                    transferred=1;n->UnitRemoveItem(s->base.handle,item.handle);
                    if(n->GetItemTypeId(item.handle)!=item.type || !n->UnitAddItem(u,item.handle)){error=124;goto candidate_error;}
                    if(n->UnitItemInSlot(u,slot)!=item.handle && !n->UnitDropItemSlot(u,item.handle,slot)){error=124;goto candidate_error;}
                    if(n->UnitItemInSlot(u,slot)!=item.handle){error=124;goto candidate_error;}
                }
            }
            /* Item bonuses must be present before restoring maxima and HP/MP. */
            error=set_state(n,u,s,n->IsUnitType(u,0)?1:0,&p->warnings);if(error)goto candidate_error;
            error=verify_contents(n,u,s,p->action==REPLACE);if(error)goto candidate_error;
            if(p->action==REPLACE){
                /* Removing the old unit is the final irreversible step. */
                if(!same(n,&s->base) || !ready_unit(n,u,raw,owner)){error=122;goto candidate_error;}
                n->SelectUnit(u,1);n->RemoveUnit(s->base.handle);
                /* Legacy may retain a removed handle's type until references
                 * expire. Nonzero GetUnitTypeId is not a removal failure. */
                if(!ready_unit(n,u,raw,owner)){error=122;goto finish;}
            }
            continue;
candidate_error:
            /* Never delete a candidate carrying transferred original items.
             * Map triggers can invalidate identities; stop rather than guess. */
            if(!transferred && ready_unit(n,u,raw,owner)){
                for(int k=0;k<6;k++)if(owned[k] && n->GetItemTypeId(owned[k])==s->items[k].type)n->RemoveItem(owned[k]);
                n->RemoveUnit(u);
            }
            goto finish;
        }
    }
finish:
    free(sources);if(error)return error;
    return legacy_collect(p,n);
}
