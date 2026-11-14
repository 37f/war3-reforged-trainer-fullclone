/* Stateful x86 fixture for the actual clone core. No game process is opened. */
#include <stdio.h>
#include <string.h>
#include <math.h>
#include "legacy_protocol.h"
#define HERO 0x456b6565u
#define HYDRA 0x7a687964u
#define ITEM 0x72617466u
#define SPELL 0x41456572u
#define INV 0x41496e76u
#define CHECK(x) do{checks++;if(!(x)){printf("FAIL %d %s\n",__LINE__,#x);failed++;}}while(0)
typedef struct {unsigned type,owner,hero,removed;int level,str,agi,intel,xp,points,paused,xpause;float hp,mhp,mp,mmp,x,y,f;unsigned items[6];int spell,inv;} FakeUnit;
typedef struct {unsigned type;int charges,invul,pawn;float life;} FakeItem;
static FakeUnit units[256];static FakeItem items[512];static unsigned next_unit,next_item,selection;
static int checks,failed,writes,old_map,fail_item,fail_state,change_owner,remove_calls;
static FakeUnit* U(unsigned u){return &units[u];}
static FakeItem* I(unsigned h){return &items[h-1000];}
static unsigned bits(float f){union{float f;unsigned i;}v;v.f=f;return v.i;}
static unsigned player(int i){return old_map&&i>=12&&i<16?100+i+12:100+i;}
static int player_id(unsigned p){int i=p-100;return old_map&&i>=24?i-12:i;}
static unsigned local(void){return player(0);}
static unsigned slot(unsigned p){return player_id(p)<2?1:0;}
static unsigned owner(unsigned u){return player(U(u)->owner);}
/* Removed handles deliberately retain type, as observed in Legacy. */
static unsigned type(unsigned u){return U(u)->type;}
static unsigned char ishero(unsigned u,int kind){return U(u)->hero;}
static unsigned state(unsigned u,int k){FakeUnit* a=U(u);return bits(k==0?a->hp:k==1?a->mhp:k==2?a->mp:a->mmp);}
static void set_state(unsigned u,int k,float* f){writes++;if(fail_state)return;if(k==0)U(u)->hp=*f;else if(k==2)U(u)->mp=*f;}
static void maxhp(unsigned u,int x){writes++;U(u)->mhp=x;}
static void maxmp(unsigned u,int x){writes++;U(u)->mmp=x;}
static int level(unsigned u){return U(u)->level;}
static void setlevel(unsigned u,int x,int e){writes++;U(u)->level=x;}
static unsigned char strip(unsigned u,int x){writes++;U(u)->level-=x;return 1;}
static int strength(unsigned u,int b){return U(u)->str;}
static int agility(unsigned u,int b){return U(u)->agi;}
static int intelligence(unsigned u,int b){return U(u)->intel;}
static void setstr(unsigned u,int x,int b){writes++;U(u)->str=x;}
static void setagi(unsigned u,int x,int b){writes++;U(u)->agi=x;}
static void setint(unsigned u,int x,int b){writes++;U(u)->intel=x;}
static unsigned getx(unsigned u){return bits(U(u)->x);}
static unsigned gety(unsigned u){return bits(U(u)->y);}
static unsigned facing(unsigned u){return bits(U(u)->f);}
static int xp(unsigned u){return U(u)->xp;}
static void setxp(unsigned u,int x,int b){writes++;U(u)->xp=x;}
static int points(unsigned u){return U(u)->points;}
static unsigned char modpoints(unsigned u,int x){writes++;U(u)->points+=x;return 1;}
static unsigned char paused(unsigned u){return U(u)->paused;}
static void pause(unsigned u,int x){writes++;U(u)->paused=x;}
static unsigned char xpaused(unsigned u){return U(u)->xpause;}
static void xpause(unsigned u,int x){writes++;U(u)->xpause=x;}
static unsigned create(unsigned p,int raw,float* x,float* y,float* f){
    writes++;if((unsigned)raw!=HERO && (unsigned)raw!=HYDRA)return 0;
    unsigned h=next_unit++;FakeUnit* a=U(h);memset(a,0,sizeof(*a));a->type=raw;a->owner=change_owner?1:player_id(p);a->hero=(unsigned)raw==HERO;a->level=a->hero?1:0;a->hp=a->mhp=500;a->mmp=270;a->x=*x;a->y=*y;a->f=*f;a->inv=a->hero;return h;
}
static void removeunit(unsigned u){writes++;U(u)->removed=1;remove_calls++;}
static void selectunit(unsigned u,int b){if(b)selection=u;}
static int ability(unsigned u,unsigned raw){return raw==SPELL?U(u)->spell:raw==INV?U(u)->inv:raw==0x41497466u?!!U(u)->items[2]:0;}
static unsigned char addability(unsigned u,unsigned raw){writes++;if(raw==SPELL)U(u)->spell=1;else if(raw==INV)U(u)->inv=1;else return 0;return 1;}
static int setability(unsigned u,unsigned raw,int x){writes++;if(raw==SPELL)U(u)->spell=x;return ability(u,raw);}
static int readabilities(unsigned u,AbilityRow* rows,unsigned* count,unsigned* itemnodes){
    rows[0]=(AbilityRow){SPELL,U(u)->spell,16};rows[1]=(AbilityRow){INV,U(u)->inv,144};*count=2;*itemnodes=0;
    if(U(u)->items[2]){rows[2]=(AbilityRow){0x41497466u,1,0x20};*count=3;*itemnodes=1;}return 0;
}
static unsigned itemslot(unsigned u,int i){return U(u)->items[i];}
static unsigned itemtype(unsigned h){return I(h)->type;}
static int charges(unsigned h){return I(h)->charges;}
static void setcharges(unsigned h,int x){writes++;I(h)->charges=x;}
static unsigned life(unsigned h){return bits(I(h)->life);}
static void setlife(unsigned h,float* x){writes++;I(h)->life=*x;}
static unsigned char invul(unsigned h){return I(h)->invul;}
static void setinvul(unsigned h,int x){writes++;I(h)->invul=x;}
static unsigned char pawn(unsigned h){return I(h)->pawn;}
static void setpawn(unsigned h,int x){writes++;I(h)->pawn=x;}
static unsigned createitem(unsigned raw,float* x,float* y){writes++;if(fail_item)return 0;unsigned h=next_item++;*I(h)=(FakeItem){raw,0,0,1,75};return h;}
static unsigned char additem(unsigned u,unsigned h){writes++;if(fail_item)return 0;for(int i=0;i<6;i++)if(!U(u)->items[i]){U(u)->items[i]=h;return 1;}return 0;}
static unsigned char dropslot(unsigned u,unsigned h,int slot){writes++;for(int i=0;i<6;i++)if(U(u)->items[i]==h){unsigned other=U(u)->items[slot];U(u)->items[slot]=h;U(u)->items[i]=other;return 1;}return 0;}
static void removeitemfromunit(unsigned u,unsigned h){writes++;for(int i=0;i<6;i++)if(U(u)->items[i]==h)U(u)->items[i]=0;}
static void removeitem(unsigned h){writes++;I(h)->type=0;}
static NativeFns n;
int legacy_collect(Packet* p,NativeFns* n){
    FakeUnit* a=U(selection);p->unit_count=a->removed?0:1;
    if(p->unit_count)p->units[0]=(UnitRow){selection,a->type,a->owner,a->hero,a->level,a->str,a->agi,a->intel,a->hp,a->mhp,a->mp,a->mmp};return 0;
}
static Packet command(int action){Packet p={0};p.action=action;p.world=p.expected_world=123;p.player_count=old_map?24:28;p.local_player=0;p.a=1;
    legacy_collect(&p,&n);p.expected_count=p.unit_count;if(p.unit_count){p.expected_units[0]=selection;p.expected_types[0]=U(selection)->type;p.expected_owners[0]=U(selection)->owner;}return p;}
static void reset(void){
    memset(units,0,sizeof(units));memset(items,0,sizeof(items));next_unit=2;next_item=1001;selection=1;writes=old_map=fail_item=fail_state=change_owner=remove_calls=0;
    units[1]=(FakeUnit){.type=HERO,.owner=1,.hero=1,.level=4,.str=30,.agi=40,.intel=50,.xp=1100,.points=1,.paused=1,.xpause=1,.hp=700,.mhp=1234,.mp=123,.mmp=456,.x=100,.y=200,.f=90,.spell=2,.inv=1};
    units[1].items[2]=1000;items[0]=(FakeItem){ITEM,7,1,0,25};
}
static void bind(void){
    n=(NativeFns){.GetLocalPlayer=local,.Player=player,.GetPlayerId=player_id,.GetPlayerSlotState=slot,.GetUnitState=state,.SetUnitState=set_state,
      .GetHeroLevel=level,.SetHeroLevel=setlevel,.UnitStripHeroLevel=strip,.GetHeroStr=strength,.GetHeroAgi=agility,.GetHeroInt=intelligence,
      .SetHeroStr=setstr,.SetHeroAgi=setagi,.SetHeroInt=setint,.IsUnitType=ishero,.GetOwningPlayer=owner,.GetUnitTypeId=type,
      .CreateUnit=create,.RemoveUnit=removeunit,.GetUnitX=getx,.GetUnitY=gety,.GetUnitFacing=facing,.GetHeroXP=xp,.SetHeroXP=setxp,
      .GetHeroSkillPoints=points,.UnitModifySkillPoints=modpoints,.GetUnitAbilityLevel=ability,.UnitAddAbility=addability,.SetUnitAbilityLevel=setability,
      .UnitItemInSlot=itemslot,.GetItemTypeId=itemtype,.GetItemCharges=charges,.SetItemCharges=setcharges,.GetWidgetLife=life,.SetWidgetLife=setlife,
      .CreateItem=createitem,.UnitAddItem=additem,.UnitDropItemSlot=dropslot,.UnitRemoveItem=removeitemfromunit,.RemoveItem=removeitem,.SelectUnit=selectunit,
      .IsUnitPaused=paused,.PauseUnit=pause,.IsItemInvulnerable=invul,.SetItemInvulnerable=setinvul,.IsItemPawnable=pawn,.SetItemPawnable=setpawn,
      .BlzSetUnitMaxHP=maxhp,.BlzSetUnitMaxMana=maxmp,.IsSuspendedXP=xpaused,.SuspendHeroXP=xpause,.ReadAbilities=readabilities};
}
int main(void){
    bind();reset();Packet p=command(PREVIEW);CHECK(legacy_clone_execute(&p,&n)==0 && writes==0 && p.detail.item_nodes==1);
    for(int mode=0;mode<3;mode++)for(int old=0;old<2;old++){
        reset();old_map=old;p=command(CLONE);p.kind=mode;p.target=old?15:27;p.a=3;FakeUnit before=units[1];FakeItem ibefore=items[0];
        CHECK(legacy_clone_execute(&p,&n)==0 && p.created_count==3 && p.applied==3);
        for(unsigned i=0;i<p.created_count;i++){
            FakeUnit* a=U(p.created[i]);CHECK(a->owner==(mode==0?0:mode==1?1:(old?15:27)));
            CHECK(a->spell==2 && a->str==30 && a->agi==40 && a->intel==50 && a->level==4 && a->xp==1100 && a->points==1);
            CHECK(a->hp==700 && a->mhp==1234 && a->mp==123 && a->mmp==456 && a->paused && a->xpause);
            unsigned h=a->items[2];CHECK(h!=1000 && I(h)->type==ITEM && I(h)->charges==7 && I(h)->life==25 && I(h)->invul && !I(h)->pawn);
            CHECK(a->items[0]==0 && a->items[1]==0 && a->items[3]==0);
        }
        CHECK(!memcmp(&before,&units[1],sizeof(before)) && !memcmp(&ibefore,&items[0],sizeof(ibefore)));
    }
    reset();p=command(REPLACE);p.b=HYDRA;CHECK(legacy_clone_execute(&p,&n)==0 && p.created_count==1 && remove_calls==1);
    CHECK(units[1].removed && units[1].type==HERO && units[1].items[2]==0);CHECK(units[selection].type==HYDRA && units[selection].items[2]==1000 && I(1000)->charges==7);CHECK(p.warnings&2);
    reset();p=command(REPLACE);p.b=HERO;CHECK(legacy_clone_execute(&p,&n)==0 && units[selection].xp==1100 && units[selection].points==1 && units[selection].items[2]==1000);
    reset();p=command(CLONE);p.expected_world=0;CHECK(legacy_clone_execute(&p,&n)==105 && writes==0);
    p=command(CLONE);p.expected_types[0]^=1;CHECK(legacy_clone_execute(&p,&n)==105 && writes==0);
    p=command(CLONE);p.a=201;CHECK(legacy_clone_execute(&p,&n)==106 && writes==0);
    p=command(CLONE);p.kind=2;p.target=3;CHECK(legacy_clone_execute(&p,&n)==110 && writes==0);
    p=command(REPLACE);p.b=0x21616263;CHECK(legacy_clone_execute(&p,&n)==106 && writes==0);
    units[1].hp=0;p=command(CLONE);CHECK(legacy_clone_execute(&p,&n)==126 && writes==0);
    reset();fail_item=1;p=command(CLONE);CHECK(legacy_clone_execute(&p,&n)==124 && !units[1].removed && units[1].items[2]==1000 && units[2].removed);
    reset();fail_state=1;p=command(REPLACE);p.b=HYDRA;CHECK(legacy_clone_execute(&p,&n)==125 && !units[1].removed && !units[2].removed && units[2].items[2]==1000);
    reset();p=command(TEST_SETUP);CHECK(legacy_clone_execute(&p,&n)==106 && writes==0);
    printf("{\"ok\":%s,\"assertions\":%d,\"failed\":%d,\"game_attached\":false}\n",failed?"false":"true",checks,failed);return failed?1:0;
}
