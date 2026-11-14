#include <windows.h>
#include <stdio.h>
#include <string.h>
#include "guard32.h"
#include "legacy_protocol.h"
#include "profile_native.h"
static HANDLE mapping=0;static Packet* shared=0;static uint32_t cookie=0;static int poisoned=0;
static NativeFns n;
static uintptr_t (__cdecl *resolve_unit)(uint32_t);
static uintptr_t (__attribute__((thiscall)) *decode_link)(void*);
static int read_abilities(uint32_t unit,AbilityRow* rows,uint32_t* count,uint32_t* item_nodes){
    uintptr_t object=resolve_unit(unit);if(!object)return 120;
    uintptr_t seen[512];uint32_t visited=0;*count=0;*item_nodes=0;
    uint32_t* pair=(uint32_t*)(object+0x3e8);uintptr_t ability=((*pair&pair[1])==0xffffffffu)?0:decode_link(pair);
    while(ability){
        if(visited>=512)return 120;
        for(unsigned i=0;i<visited;i++)if(seen[i]==ability)return 120;
        seen[visited++]=ability;
        uint32_t raw=*(uint32_t*)(ability+0x34),flags=*(uint32_t*)(ability+0x20);
        int level=n.GetUnitAbilityLevel(unit,raw);
        if(level>0){
            if(*count>=MAX_ABILITIES)return 120;
            rows[*count]=(AbilityRow){raw,(uint32_t)level,flags};(*count)++;
            if(flags&0x20)(*item_nodes)++;
        }
        pair=(uint32_t*)(ability+0x24);ability=((*pair&pair[1])==0xffffffffu)?0:decode_link(pair);
    }
    return 0;
}
static int bind_native(uintptr_t base){
    IMAGE_DOS_HEADER* dos=(void*)base;IMAGE_NT_HEADERS32* pe=(void*)(base+dos->e_lfanew);
    if(dos->e_magic!=IMAGE_DOS_SIGNATURE || pe->Signature!=IMAGE_NT_SIGNATURE || pe->FileHeader.Machine!=IMAGE_FILE_MACHINE_I386 || pe->FileHeader.TimeDateStamp!=PROFILE_TIMESTAMP || pe->OptionalHeader.SizeOfImage!=PROFILE_SIZE)return 103;
    uintptr_t addresses[FN_COUNT];uint32_t shift=(uint32_t)base-0x400000;
    for(unsigned i=0;i<FN_COUNT;i++){
        const NativeProfile* spec=&NATIVE_PROFILE[i];unsigned char expected[36];memcpy(expected,spec->code,36);
        for(unsigned j=0;j<spec->reloc_count;j++){uint32_t v;memcpy(&v,expected+spec->reloc[j],4);v+=shift;memcpy(expected+spec->reloc[j],&v,4);}
        if(memcmp((void*)(base+spec->rva),expected,32))return 103;
        addresses[i]=base+spec->rva;
    }
    #define BIND(name) n.name=(void*)addresses[FN_##name]
    BIND(GetLocalPlayer);BIND(Player);BIND(GetPlayerId);BIND(GetPlayerState);BIND(SetPlayerState);BIND(GetPlayerSlotState);
    BIND(GetUnitState);BIND(SetUnitState);BIND(GetHeroLevel);BIND(SetHeroLevel);BIND(UnitStripHeroLevel);
    BIND(GetHeroStr);BIND(GetHeroAgi);BIND(GetHeroInt);BIND(SetHeroStr);BIND(SetHeroAgi);BIND(SetHeroInt);
    BIND(IsUnitType);BIND(GetOwningPlayer);BIND(GetUnitTypeId);BIND(CreateGroup);BIND(DestroyGroup);BIND(GroupEnumUnitsSelected);BIND(FirstOfGroup);BIND(GroupRemoveUnit);
    BIND(CreateUnit);BIND(RemoveUnit);BIND(GetUnitX);BIND(GetUnitY);BIND(GetUnitFacing);BIND(GetHeroXP);BIND(SetHeroXP);
    BIND(GetHeroSkillPoints);BIND(UnitModifySkillPoints);BIND(GetUnitAbilityLevel);BIND(UnitAddAbility);BIND(SetUnitAbilityLevel);
    BIND(UnitItemInSlot);BIND(GetItemTypeId);BIND(GetItemCharges);BIND(SetItemCharges);BIND(GetWidgetLife);BIND(SetWidgetLife);
    BIND(CreateItem);BIND(UnitAddItem);BIND(UnitDropItemSlot);BIND(UnitRemoveItem);BIND(RemoveItem);BIND(SelectUnit);
    BIND(IsUnitPaused);BIND(PauseUnit);BIND(IsItemInvulnerable);BIND(SetItemInvulnerable);BIND(IsItemPawnable);BIND(SetItemPawnable);
    BIND(BlzSetUnitMaxHP);BIND(BlzSetUnitMaxMana);BIND(IsSuspendedXP);BIND(SuspendHeroXP);
    resolve_unit=(void*)addresses[FN_ResolveUnit];decode_link=(void*)addresses[FN_DecodeAbilityLink];n.ReadAbilities=read_abilities;
    return 0;
}
static uint32_t __cdecl execute_guarded(void* arg){
    Packet* p=arg;p->stage=10;uintptr_t base=(uintptr_t)GetModuleHandleW(NULL);int error=bind_native(base);if(error)return error;
    p->stage=11;
    uint32_t world=*(uint32_t*)(base+WORLD_RVA);if(!world || *(uint32_t*)world!=base+WORLD_VTABLE_RVA)return 104;
    p->module_base=base;p->world=world;p->player_count=*(uint32_t*)(world+0x54);
    return legacy_execute(p,&n);
}
static int connect_mapping(uint32_t nonce){
    if(shared && cookie==nonce)return 1;
    if(shared){UnmapViewOfFile(shared);CloseHandle(mapping);shared=0;mapping=0;}
    wchar_t name[128];swprintf(name,128,L"Local\\War3Legacy129-V2-%lu-%08lx",GetCurrentProcessId(),(unsigned long)nonce);
    mapping=OpenFileMappingW(FILE_MAP_ALL_ACCESS,FALSE,name);if(!mapping)return 0;
    shared=MapViewOfFile(mapping,FILE_MAP_ALL_ACCESS,0,0,sizeof(Packet));
    if(!shared){CloseHandle(mapping);mapping=0;return 0;}
    if(shared->magic!=LEGACY_MAGIC || shared->version!=LEGACY_VERSION || shared->bytes!=sizeof(Packet) || shared->pid!=GetCurrentProcessId() || shared->nonce!=nonce){UnmapViewOfFile(shared);CloseHandle(mapping);shared=0;mapping=0;return 0;}
    cookie=nonce;poisoned=0;return 1;
}
__declspec(dllexport) LRESULT CALLBACK LegacyHook(int code,WPARAM w,LPARAM l){
    static UINT request=0;if(!request)request=RegisterWindowMessageW(L"War3Legacy129.BasicTrainer.v2");
    if(code==HC_ACTION){MSG* msg=(MSG*)l;
        if(msg->message==request && msg->wParam && connect_mapping((uint32_t)msg->wParam)){
            if(shared->seq && shared->ack!=shared->seq && InterlockedCompareExchange((LONG*)&shared->status,2,1)==1){
                Packet local;memcpy(&local,shared,sizeof(local));local.applied=0;uint32_t fault=0;
                uint32_t error=0;
                if(local.magic!=LEGACY_MAGIC || local.version!=LEGACY_VERSION || local.bytes!=sizeof(Packet) || local.pid!=GetCurrentProcessId() || local.nonce!=cookie)error=102;
                else error=poisoned?108:guard_call(execute_guarded,&local,&fault);
                if(fault){error=fault;poisoned=1;}
                uint32_t seq=local.seq;local.error=error;local.status=error?4:3;local.ack=0;
                memcpy(shared,&local,sizeof(local));MemoryBarrier();InterlockedExchange((LONG*)&shared->ack,seq);
            }
            msg->message=WM_NULL;msg->wParam=0;msg->lParam=0;
        }
    }
    return CallNextHookEx(NULL,code,w,l);
}
BOOL WINAPI DllMain(HINSTANCE instance,DWORD reason,LPVOID reserved){
    if(reason==DLL_PROCESS_ATTACH)DisableThreadLibraryCalls(instance);
    if(reason==DLL_PROCESS_DETACH){if(shared)UnmapViewOfFile(shared);if(mapping)CloseHandle(mapping);}
    return TRUE;
}
