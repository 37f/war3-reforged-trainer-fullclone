#ifndef LEGACY_PROTOCOL_H
#define LEGACY_PROTOCOL_H
#include <stdint.h>
#define LEGACY_MAGIC 0x4c313239u
#define LEGACY_VERSION 2u
#define MAX_PLAYERS 28
#define MAX_UNITS 64
enum { READ=0,SET_RESOURCE=1,ADD_RESOURCES=2,FILL=3,LEVEL=4,ATTRIBUTES=5,CLONE=6,REPLACE=7,PREVIEW=8,TEST_SETUP=9 };
#define MAX_ABILITIES 128
typedef struct {uint32_t rawcode,level,flags;} AbilityRow;
typedef struct {uint32_t handle,type;int32_t charges;float life;uint32_t invulnerable,pawnable;} ItemRow;
typedef struct { uint32_t slot,handle,state;int32_t gold,lumber,food_used,food_cap; } PlayerRow;
typedef struct {uint32_t handle,type,owner,hero;int32_t level,strength,agility,intelligence;float hp,max_hp,mp,max_mp;} UnitRow;
typedef struct {UnitRow base;float x,y,facing;uint32_t xp,points,paused,xp_paused,ability_count,item_nodes;AbilityRow abilities[MAX_ABILITIES];ItemRow items[6];} UnitSpec;
typedef struct {
    uint32_t magic,version,bytes,pid,nonce,seq,ack,status,error,action,target,kind;
    int32_t a,b,c,delta;
    uint32_t expected_world,expected_player,expected_count;
    uint32_t expected_units[MAX_UNITS],expected_types[MAX_UNITS],expected_owners[MAX_UNITS];
    uint32_t world,module_base,local_player,player_count,unit_count,applied,stage;
    PlayerRow players[MAX_PLAYERS];UnitRow units[MAX_UNITS];
    UnitSpec detail;
    uint32_t created_count,created[200],warnings;
} Packet;
typedef struct {
    uint32_t (__cdecl *GetLocalPlayer)(void);
    uint32_t (__cdecl *Player)(int);
    int (__cdecl *GetPlayerId)(uint32_t);
    int (__cdecl *GetPlayerState)(uint32_t,int);
    void (__cdecl *SetPlayerState)(uint32_t,int,int);
    uint32_t (__cdecl *GetPlayerSlotState)(uint32_t);
    uint32_t (__cdecl *GetUnitState)(uint32_t,int);
    void (__cdecl *SetUnitState)(uint32_t,int,float*);
    int (__cdecl *GetHeroLevel)(uint32_t);
    void (__cdecl *SetHeroLevel)(uint32_t,int,int);
    unsigned char (__cdecl *UnitStripHeroLevel)(uint32_t,int);
    int (__cdecl *GetHeroStr)(uint32_t,int);
    int (__cdecl *GetHeroAgi)(uint32_t,int);
    int (__cdecl *GetHeroInt)(uint32_t,int);
    void (__cdecl *SetHeroStr)(uint32_t,int,int);
    void (__cdecl *SetHeroAgi)(uint32_t,int,int);
    void (__cdecl *SetHeroInt)(uint32_t,int,int);
    unsigned char (__cdecl *IsUnitType)(uint32_t,int);
    uint32_t (__cdecl *GetOwningPlayer)(uint32_t);
    uint32_t (__cdecl *GetUnitTypeId)(uint32_t);
    uint32_t (__cdecl *CreateGroup)(void);
    void (__cdecl *DestroyGroup)(uint32_t);
    void (__cdecl *GroupEnumUnitsSelected)(uint32_t,uint32_t,uint32_t);
    uint32_t (__cdecl *FirstOfGroup)(uint32_t);
    void (__cdecl *GroupRemoveUnit)(uint32_t,uint32_t);
    uint32_t (__cdecl *CreateUnit)(uint32_t,int,float*,float*,float*);
    void (__cdecl *RemoveUnit)(uint32_t);
    uint32_t (__cdecl *GetUnitX)(uint32_t),(__cdecl *GetUnitY)(uint32_t),(__cdecl *GetUnitFacing)(uint32_t);
    int (__cdecl *GetHeroXP)(uint32_t);void (__cdecl *SetHeroXP)(uint32_t,int,int);
    int (__cdecl *GetHeroSkillPoints)(uint32_t);unsigned char (__cdecl *UnitModifySkillPoints)(uint32_t,int);
    int (__cdecl *GetUnitAbilityLevel)(uint32_t,uint32_t);unsigned char (__cdecl *UnitAddAbility)(uint32_t,uint32_t);
    int (__cdecl *SetUnitAbilityLevel)(uint32_t,uint32_t,int);
    uint32_t (__cdecl *UnitItemInSlot)(uint32_t,int),(__cdecl *GetItemTypeId)(uint32_t);
    int (__cdecl *GetItemCharges)(uint32_t);void (__cdecl *SetItemCharges)(uint32_t,int);
    uint32_t (__cdecl *GetWidgetLife)(uint32_t);void (__cdecl *SetWidgetLife)(uint32_t,float*);
    uint32_t (__cdecl *CreateItem)(uint32_t,float*,float*);
    unsigned char (__cdecl *UnitAddItem)(uint32_t,uint32_t),(__cdecl *UnitDropItemSlot)(uint32_t,uint32_t,int);
    void (__cdecl *UnitRemoveItem)(uint32_t,uint32_t),(__cdecl *RemoveItem)(uint32_t);
    void (__cdecl *SelectUnit)(uint32_t,int);
    unsigned char (__cdecl *IsUnitPaused)(uint32_t);void (__cdecl *PauseUnit)(uint32_t,int);
    unsigned char (__cdecl *IsItemInvulnerable)(uint32_t);void (__cdecl *SetItemInvulnerable)(uint32_t,int);
    unsigned char (__cdecl *IsItemPawnable)(uint32_t);void (__cdecl *SetItemPawnable)(uint32_t,int);
    void (__cdecl *BlzSetUnitMaxHP)(uint32_t,int),(__cdecl *BlzSetUnitMaxMana)(uint32_t,int);
    unsigned char (__cdecl *IsSuspendedXP)(uint32_t);void (__cdecl *SuspendHeroXP)(uint32_t,int);
    int (*ReadAbilities)(uint32_t,AbilityRow*,uint32_t*,uint32_t*);
} NativeFns;
int legacy_collect(Packet*,NativeFns*);
int legacy_execute(Packet*,NativeFns*);
int legacy_clone_execute(Packet*,NativeFns*);
#endif
