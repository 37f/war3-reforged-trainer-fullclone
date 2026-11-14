/* Real x86 execution of the production command core, with isolated fake natives.
 * Does not open or communicate with a Warcraft process. */
#include <stdio.h>
#include <string.h>
#include <math.h>
#include "legacy_protocol.h"
static int checks=0,failed=0,writes=0,group_destroyed=0,old_map=0,selected[3]={0},cursor=0;
static int gold[28],wood[28],food[28],cap[28],level=1,strength=16,agility=15,intelligence=18;
static float life=200,mana=20;static int hero=1;static unsigned typ=0x456b6565;
static int replace_after_strength=0;
#define CHECK(expr) do{checks++;if(!(expr)){printf("FAIL line%d: %s\n",__LINE__,#expr);failed++;}}while(0)
static unsigned player(int i){return old_map&&i>=12&&i<16?i+12+100:i+100;}
static int player_id(unsigned p){int i=(int)p-100;return old_map&&i>=24?i-12:i;}
static unsigned local(void){return player(0);}
static int get_state(unsigned p,int kind){int i=player_id(p);return kind==1?gold[i]:kind==2?wood[i]:kind==4?cap[i]:food[i];}
static void set_state(unsigned p,int kind,int n){writes++;int i=player_id(p);if(kind==1)gold[i]=n;else if(kind==2)wood[i]=n;else if(kind==4)cap[i]=n;else food[i]=n;}
static unsigned slot(unsigned p){return player_id(p)<2?1:0;}
static unsigned unit_state(unsigned u,int kind){union{float f;unsigned i;}v;v.f=kind==0?life:kind==1?500:kind==2?mana:270;return v.i;}
static void set_unit(unsigned u,int kind,float* value){writes++;if(kind==0)life=*value;else if(kind==2)mana=*value;}
static int hero_level(unsigned u){return level;}
static void set_level(unsigned u,int n,int eye){writes++;level=n;}
static unsigned char strip(unsigned u,int n){writes++;level-=n;return 1;}
static int get_str(unsigned u,int bonus){CHECK(!bonus);return strength;}
static int get_agi(unsigned u,int bonus){CHECK(!bonus);return agility;}
static int get_int(unsigned u,int bonus){CHECK(!bonus);return intelligence;}
static void set_str(unsigned u,int n,int permanent){CHECK(permanent==1);writes++;strength=n;if(replace_after_strength)typ^=1;}
static void set_agi(unsigned u,int n,int permanent){CHECK(permanent==1);writes++;agility=n;}
static void set_int(unsigned u,int n,int permanent){CHECK(permanent==1);writes++;intelligence=n;}
static unsigned char unit_type(unsigned u,int kind){CHECK(kind==0);return hero;}
static unsigned owner(unsigned u){return player(0);}
static unsigned rawcode(unsigned u){return typ;}
static unsigned create(void){cursor=0;return 88;}
static void destroy(unsigned g){group_destroyed++;}
static void enumerate(unsigned g,unsigned p,unsigned filter){CHECK(filter==0);}
static unsigned first(unsigned g){return selected[cursor];}
static void remove_unit(unsigned g,unsigned u){CHECK(u==selected[cursor]);cursor++;}
static NativeFns n={local,player,player_id,get_state,set_state,slot,unit_state,set_unit,hero_level,set_level,strip,get_str,get_agi,get_int,set_str,set_agi,set_int,unit_type,owner,rawcode,create,destroy,enumerate,first,remove_unit};
static Packet snapshot(void){Packet p={0};p.world=123;p.player_count=28;CHECK(legacy_execute(&p,&n)==0);return p;}
static Packet command(int action){Packet r=snapshot();r.action=action;r.expected_world=r.world;r.expected_count=r.unit_count;r.expected_player=r.players[0].handle;
 for(unsigned i=0;i<r.unit_count;i++){r.expected_units[i]=r.units[i].handle;r.expected_types[i]=r.units[i].type;r.expected_owners[i]=r.units[i].owner;}r.player_count=28;r.applied=0;return r;}
int main(void){
 selected[0]=1000;gold[0]=420;wood[0]=110;food[0]=cap[0]=10;
 Packet p=snapshot();CHECK(p.player_count==28 && p.unit_count==1 && p.units[0].level==1);CHECK(writes==0 && group_destroyed>0);
 old_map=1;p=snapshot();CHECK(p.player_count==24 && p.players[12].handle==player(24));old_map=0;
 p=command(SET_RESOURCE);p.kind=1;p.a=999;CHECK(legacy_execute(&p,&n)==0 && gold[0]==999 && p.players[0].gold==999);
 p=command(SET_RESOURCE);p.kind=4;p.a=50;CHECK(legacy_execute(&p,&n)==0 && cap[0]==50);
 p=command(ADD_RESOURCES);p.a=100;CHECK(legacy_execute(&p,&n)==0 && gold[0]==1099 && wood[0]==210);
 p=command(FILL);CHECK(legacy_execute(&p,&n)==0 && life==500 && mana==270 && p.applied==1);
 p=command(LEVEL);p.a=1;p.delta=1;CHECK(legacy_execute(&p,&n)==0 && level==2);
 p=command(LEVEL);p.a=10;CHECK(legacy_execute(&p,&n)==0 && level==10);
 p=command(LEVEL);p.a=1;CHECK(legacy_execute(&p,&n)==0 && level==1);
 p=command(ATTRIBUTES);p.a=p.b=p.c=2;p.delta=1;CHECK(legacy_execute(&p,&n)==0 && strength==18 && agility==17 && intelligence==20);
 p=command(ATTRIBUTES);p.a=30;p.b=40;p.c=50;CHECK(legacy_execute(&p,&n)==0 && strength==30 && agility==40 && intelligence==50);
 int before=writes;p=command(LEVEL);p.expected_types[0]^=1;p.a=99;CHECK(legacy_execute(&p,&n)==105 && writes==before);
 p=command(LEVEL);p.expected_world=999;p.a=99;CHECK(legacy_execute(&p,&n)==105 && writes==before);
 p=command(SET_RESOURCE);p.expected_player=101;p.kind=1;p.a=99;CHECK(legacy_execute(&p,&n)==105 && writes==before);
 p=command(SET_RESOURCE);p.kind=1;p.a=100000001;CHECK(legacy_execute(&p,&n)==106 && writes==before);
 p=command(ATTRIBUTES);p.a=-1;CHECK(legacy_execute(&p,&n)==106 && writes==before);
 p=command(LEVEL);p.a=1001;CHECK(legacy_execute(&p,&n)==106 && writes==before);
 p=command(SET_RESOURCE);p.target=2;p.expected_player=player(2);p.kind=1;p.a=10;CHECK(legacy_execute(&p,&n)==110 && writes==before);
 hero=0;p=command(LEVEL);p.a=5;CHECK(legacy_execute(&p,&n)==0 && p.applied==0 && writes==before);
 p=command(ATTRIBUTES);p.a=p.b=p.c=2;CHECK(legacy_execute(&p,&n)==0 && p.applied==0 && writes==before);
 life=0;p=command(FILL);CHECK(legacy_execute(&p,&n)==0 && p.applied==0 && life==0 && writes==before);
 selected[0]=0;p=command(FILL);CHECK(legacy_execute(&p,&n)==0 && p.unit_count==0 && writes==before);
 selected[0]=1000;hero=1;replace_after_strength=1;p=command(ATTRIBUTES);p.a=10;p.b=11;p.c=12;before=writes;
 CHECK(legacy_execute(&p,&n)==105 && writes==before+1 && p.applied==1);CHECK(agility==40 && intelligence==50);
 printf("{\"ok\":%s,\"assertions\":%d,\"failed\":%d,\"x86_core_executed\":true,\"game_attached\":false}\n",failed?"false":"true",checks,failed);
 return failed?1:0;
}
