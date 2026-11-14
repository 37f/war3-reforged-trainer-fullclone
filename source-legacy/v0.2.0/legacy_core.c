/* Only verified native signatures are used. All input is checked again here,
 * before the first mutation. Readback decides success; void setters do not.
 */
#include <string.h>
#include <math.h>
#include "legacy_protocol.h"
static float unit_value(NativeFns* n,uint32_t u,int state){union{uint32_t i;float f;}v;v.i=n->GetUnitState(u,state);return v.f;}
static int same_unit(NativeFns* n,UnitRow* r){return n->GetUnitTypeId(r->handle)==r->type && n->GetPlayerId(n->GetOwningPlayer(r->handle))==(int)r->owner;}
int legacy_collect(Packet* p,NativeFns* n){
    p->stage=20;uint32_t local=n->GetLocalPlayer(),group=0,u=0;
    p->unit_count=0;
    if(!local)return 104;
    p->stage=21;int owner=n->GetPlayerId(local);if(owner<0 || owner>=MAX_PLAYERS)return 104;
    p->local_player=(uint32_t)owner;
    p->stage=22;if(p->player_count<1 || p->player_count>MAX_PLAYERS)return 104;
    uint32_t capacity=p->player_count;p->player_count=0;
    for(uint32_t i=0;i<capacity;i++){
        p->stage=2300+i;uint32_t h=n->Player(i);if(!h)return 104;
        int actual=n->GetPlayerId(h);
        /* The supplied Player/GetPlayerId natives explicitly remap old map
         * slots12..15 to the internal neutral24..27. Do not list the aliases
         * twice or reject a valid old campaign as an unready map. */
        if(actual!=(int)i){if(i>=24 && actual==(int)i-12 && n->Player(actual)==h)continue;return 104;}
        PlayerRow* r=&p->players[p->player_count++];
        r->slot=i;r->handle=h;r->state=n->GetPlayerSlotState(h);
        r->gold=n->GetPlayerState(h,1);r->lumber=n->GetPlayerState(h,2);
        r->food_used=n->GetPlayerState(h,5);r->food_cap=n->GetPlayerState(h,4);
    }
    p->stage=25;group=n->CreateGroup();if(!group)return 104;
    p->stage=26;n->GroupEnumUnitsSelected(group,local,0);
    while((u=n->FirstOfGroup(group))!=0){
        if(p->unit_count>=MAX_UNITS){n->DestroyGroup(group);return 111;}
        UnitRow* r=&p->units[p->unit_count++];memset(r,0,sizeof(*r));r->handle=u;
        r->type=n->GetUnitTypeId(u);r->owner=n->GetPlayerId(n->GetOwningPlayer(u));
        r->hero=n->IsUnitType(u,0)?1:0;
        r->hp=unit_value(n,u,0);r->max_hp=unit_value(n,u,1);r->mp=unit_value(n,u,2);r->max_mp=unit_value(n,u,3);
        if(!r->type || r->owner>=28 || !isfinite(r->hp) || !isfinite(r->max_hp) || !isfinite(r->mp) || !isfinite(r->max_mp)){
            n->DestroyGroup(group);return 104;
        }
        if(r->hero){r->level=n->GetHeroLevel(u);r->strength=n->GetHeroStr(u,0);r->agility=n->GetHeroAgi(u,0);r->intelligence=n->GetHeroInt(u,0);}
        n->GroupRemoveUnit(group,u);
        if(n->FirstOfGroup(group)==u){n->DestroyGroup(group);return 104;}
    }
    n->DestroyGroup(group);p->stage=900;return 0;
}
int legacy_execute(Packet* p,NativeFns* n){
    int err=legacy_collect(p,n);if(err || p->action==READ)return err;
    if(p->action>=CLONE)return legacy_clone_execute(p,n);
    if(p->action>ATTRIBUTES || (p->delta!=0 && p->delta!=1))return 106;
    if(p->world!=p->expected_world)return 105;
    if(p->action==SET_RESOURCE || p->action==ADD_RESOURCES){
        if(p->target>=p->player_count)return 106;
        PlayerRow before=p->players[p->target];if(before.handle!=p->expected_player)return 105;
        int neutral=0;for(int i=24;i<28;i++)if(n->Player(i)==before.handle)neutral=1;
        if(!neutral && before.state!=1)return 110;
        if(p->action==SET_RESOURCE){
            if(!(p->kind==1 || p->kind==2 || p->kind==4 || p->kind==5) || p->a<0 || p->a>100000000)return 106;
            p->applied=1;n->SetPlayerState(before.handle,p->kind,p->a);
            if(n->GetPlayerState(before.handle,p->kind)!=p->a)return 109;
        }else{
            int64_t gold=(int64_t)before.gold+p->a,lumber=(int64_t)before.lumber+p->a;
            if(p->a<0 || gold<0 || lumber<0 || gold>100000000 || lumber>100000000)return 106;
            p->applied=1;n->SetPlayerState(before.handle,1,(int)gold);n->SetPlayerState(before.handle,2,(int)lumber);
            if(n->GetPlayerState(before.handle,1)!=gold || n->GetPlayerState(before.handle,2)!=lumber)return 109;
        }
    }else{
        if(p->expected_count!=p->unit_count)return 105;
        for(uint32_t i=0;i<p->unit_count;i++){
            UnitRow* r=&p->units[i];int found=0;
            for(uint32_t j=0;j<p->expected_count;j++)if(p->expected_units[j]==r->handle && p->expected_types[j]==r->type && p->expected_owners[j]==r->owner)found=1;
            if(!found)return 105;
            if(r->hero && p->action==LEVEL){int64_t level=p->delta?(int64_t)r->level+p->a:p->a;if(level<1 || level>1000)return 106;}
            if(r->hero && p->action==ATTRIBUTES){
                int64_t a=p->delta?(int64_t)r->strength+p->a:p->a,b=p->delta?(int64_t)r->agility+p->b:p->b,c=p->delta?(int64_t)r->intelligence+p->c:p->c;
                if(a<0 || b<0 || c<0 || a>100000 || b>100000 || c>100000)return 106;
            }
        }
        for(uint32_t i=0;i<p->unit_count;i++){
            UnitRow before=p->units[i];uint32_t u=before.handle;
            if(p->action==FILL){
                if(before.hp<=0.405f || before.max_hp<=0)continue;
                p->applied++;float hp=before.max_hp,mp=before.max_mp;n->SetUnitState(u,0,&hp);if(!same_unit(n,&before))return 105;
                if(mp>0)n->SetUnitState(u,2,&mp);if(!same_unit(n,&before))return 105;
                if(fabsf(unit_value(n,u,0)-hp)>0.05f || (mp>0 && fabsf(unit_value(n,u,2)-mp)>0.05f))return 109;
            }else if(before.hero && p->action==LEVEL){
                int level=p->delta?before.level+p->a:p->a;p->applied++;
                if(level<before.level)n->UnitStripHeroLevel(u,before.level-level);else if(level>before.level)n->SetHeroLevel(u,level,0);
                if(!same_unit(n,&before))return 105;
                if(n->GetHeroLevel(u)!=level)return 109;
            }else if(before.hero && p->action==ATTRIBUTES){
                int a=p->delta?before.strength+p->a:p->a,b=p->delta?before.agility+p->b:p->b,c=p->delta?before.intelligence+p->c:p->c;
                p->applied++;n->SetHeroStr(u,a,1);if(!same_unit(n,&before))return 105;
                n->SetHeroAgi(u,b,1);if(!same_unit(n,&before))return 105;
                n->SetHeroInt(u,c,1);if(!same_unit(n,&before))return 105;
                if(n->GetHeroStr(u,0)!=a || n->GetHeroAgi(u,0)!=b || n->GetHeroInt(u,0)!=c)return 109;
            }
        }
    }
    return legacy_collect(p,n);
}
