"""Read the supplied 1.29.2 PE, never execute it or modify the installation."""
from pathlib import Path
import hashlib,json,struct
import pefile

ROOT=Path(__file__).resolve().parent
TARGET=Path(r'E:\Games\Warcraft III (Legacy)\Warcraft III.exe')
EXPECTED='3f2ed0120d80578bf07e4423296dade1adfb959d59a2d20a7584224559570eed'
NAMES=['GetPlayerState','SetPlayerState','GetPlayerId','GetLocalPlayer','Player','GetPlayerSlotState',
    'GetUnitState','SetUnitState','GetHeroLevel','SetHeroLevel','UnitStripHeroLevel',
    'GetHeroStr','SetHeroStr','GetHeroAgi','SetHeroAgi','GetHeroInt','SetHeroInt','IsSuspendedXP','SuspendHeroXP',
    'IsUnitType','GetOwningPlayer','GetUnitTypeId','CreateGroup','DestroyGroup','GroupEnumUnitsSelected','FirstOfGroup','GroupRemoveUnit',
    'CreateUnit','RemoveUnit','GetUnitX','GetUnitY','GetUnitFacing','GetHeroXP','SetHeroXP','GetHeroSkillPoints','UnitModifySkillPoints',
    'GetUnitAbilityLevel','UnitAddAbility','SetUnitAbilityLevel','UnitItemInSlot','GetItemTypeId','GetItemCharges','SetItemCharges',
    'GetWidgetLife','SetWidgetLife','CreateItem','UnitAddItem','UnitDropItemSlot','UnitRemoveItem','RemoveItem','SelectUnit',
    'IsUnitPaused','PauseUnit','IsItemInvulnerable','SetItemInvulnerable','IsItemPawnable','SetItemPawnable','BlzSetUnitMaxHP','BlzSetUnitMaxMana']

def extract():
    raw=TARGET.read_bytes();assert hashlib.sha256(raw).hexdigest()==EXPECTED
    pe=pefile.PE(data=raw);base=pe.OPTIONAL_HEADER.ImageBase
    assert pe.FILE_HEADER.Machine==0x14c
    def string(va):return pe.get_data(va-base,150).split(b'\0')[0].decode('ascii')
    entries={}
    for name in NAMES:
        start=0;candidates=[]
        while (at:=raw.find(name.encode()+b'\0',start))>=0:
            start=at+1;needle=struct.pack('<I',base+pe.get_rva_from_offset(at));pos=0
            while (r:=raw.find(needle,pos))>=0:
                pos=r+1
                if raw[r-6:r-5]!=b'\x68' or raw[r-1:r]!=b'\x68' or raw[r+4:r+5]!=b'\x68' or raw[r+9:r+10]!=b'\xe8':continue
                sig=struct.unpack_from('<I',raw,r-5)[0];fn=struct.unpack_from('<I',raw,r+5)[0]
                if string(sig).startswith('('):candidates.append((r,sig,fn))
        assert candidates,name
        r,sig,fn=min(candidates)
        rva=fn-base;relocations=[]
        for block in pe.DIRECTORY_ENTRY_BASERELOC:
            for item in block.entries:
                if item.type and rva<=item.rva<rva+32:
                    assert item.type==3
                    relocations.append(item.rva-rva)
        entries[name]=dict(rva=rva,signature=string(sig),code=pe.get_data(rva,36).hex(),relocations=relocations)
    # These read-only helpers and layout sites were traced from this exact PE's
    # GetUnitTypeId/GetUnitAbilityLevel. No address is borrowed from other builds.
    for name,rva,signature in [('ResolveUnit',0x83940,'(Hunit;)P:internal-cdecl'),('DecodeAbilityLink',0x3fc7e0,'(P)P:internal-thiscall'),
        ('AbilityHeadLayout',0x2d65ff,'layout-evidence'),('AbilityNodeLayout',0x2d6620,'layout-evidence'),('AbilityLevelLayout',0x97203,'layout-evidence')]:
        relocations=[i.rva-rva for b in pe.DIRECTORY_ENTRY_BASERELOC for i in b.entries if i.type==3 and rva<=i.rva<rva+32]
        entries[name]=dict(rva=rva,signature=signature,code=pe.get_data(rva,36).hex(),relocations=relocations)
    profile=dict(version='1.29.2.9231',sha256=EXPECTED,machine=332,timestamp=pe.FILE_HEADER.TimeDateStamp,
        image_size=pe.OPTIONAL_HEADER.SizeOfImage,image_base=base,world_rva=0xd3b6f4,
        world_vtable_rva=0xa6e73c,player_count_offset=0x54,natives=entries,
        ability_layout=dict(unit_head=0x3e8,next=0x24,flags=0x20,rawcode=0x34,level=0x50,item_flag=0x20))
    (ROOT/'profile.json').write_text(json.dumps(profile,indent=2),'utf8')
    h=['/* Generated only from the immutable supplied Legacy binary. */',f'#define PROFILE_TIMESTAMP {profile["timestamp"]}u',f'#define PROFILE_SIZE {profile["image_size"]}u',f'#define WORLD_RVA {profile["world_rva"]}u',f'#define WORLD_VTABLE_RVA {profile["world_vtable_rva"]}u']
    for i,(name,e) in enumerate(entries.items()):h.append(f'#define FN_{name} {i}')
    h.append(f'#define FN_COUNT {len(entries)}')
    h.append('typedef struct { unsigned int rva; unsigned char code[36]; unsigned char reloc[8]; unsigned int reloc_count; } NativeProfile;')
    h.append('static const NativeProfile NATIVE_PROFILE[FN_COUNT]={')
    for e in entries.values():h.append('{'+str(e['rva'])+',{'+','.join('0x'+e['code'][i:i+2] for i in range(0,72,2))+'},{'+','.join(map(str,e['relocations'] or [0]))+'},'+str(len(e['relocations']))+'},')
    h.append('};');(ROOT/'profile_native.h').write_text('\n'.join(h)+'\n','utf8')
    print('verified x86 profile:',len(entries),'native signatures')

if __name__=='__main__':extract()
