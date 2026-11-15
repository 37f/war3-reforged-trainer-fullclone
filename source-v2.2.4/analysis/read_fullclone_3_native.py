import json,sys
from pathlib import Path
from war3_backend import ProcessMemory,find_war3_with_retry
from war3_game_session import GameSession
from war3_native_table import NativeTable24268
from war3_game_profile import profile_scope
from capstone import Cs,CS_ARCH_X86,CS_MODE_64
hwnd,pid=find_war3_with_retry(None);session=GameSession(pid,hwnd)
result={'pid':pid,'hwnd':hwnd,'read_only':True}
with ProcessMemory(pid,write=False) as pm:
 reg,context,mode=session.prepare(pm)
 result.update(base=reg.base,game=session.profile.data['game_version'],mode=mode.value,tls=mode.tls,context=mode.context,mode_object=mode.mode_object)
 with profile_scope(session.profile):
  table=NativeTable24268(pm,pm.read_u64(mode.tls+session.profile.section('context')['native_slot']))
  names=['GetPlayerName','GetPlayerId','GetOwningPlayer','EnumItemsInRect','GetEnumItem','GetItemTypeId','FirstOfGroup','GetWorldBounds','SetMapName','SetMapDescription','ExecuteFunc','IsQuestCompleted','IsQuestFailed','GetLocalizedString']
  md=Cs(CS_ARCH_X86,CS_MODE_64)
  result['natives']={}
  for name in names:
   e=table.entries.get(name)
   if not e:continue
   row=dict(name=e.name,signature=e.signature,handler=e.handler,rva=e.handler-reg.base)
   try:
    data=pm.read(e.handler,384);row['hex']=data.hex();row['disassembly']=[f'{i.address-reg.base:x}: {i.mnemonic} {i.op_str}' for i in md.disasm(data,e.handler)]
   except Exception as exc:row['error']=repr(exc)
   result['natives'][name]=row
Path('../native-readonly.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf8')
print(json.dumps({k:v for k,v in result.items() if k!='natives'},ensure_ascii=False))
print('native names',list(result.get('natives',{})))
