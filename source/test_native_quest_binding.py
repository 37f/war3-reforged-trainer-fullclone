"""Exercise callback identity/list checks against concrete bounded C fixtures."""
from pathlib import Path
import shutil
import subprocess
import pytest

HARNESS=r'''
#include <windows.h>
#include <stdlib.h>
#include <wchar.h>
#include <stdint.h>
#include "war3_quest_wire.h"
typedef uint32_t (*War3NameHashFn)(const char *);
static int war3_readable_span(uint64_t p,size_t n) {
    MEMORY_BASIC_INFORMATION m;
    return p>65535 && VirtualQuery((void *)(uintptr_t)p,&m,sizeof(m))==sizeof(m) &&
        m.State==MEM_COMMIT && !(m.Protect&(PAGE_GUARD|PAGE_NOACCESS)) &&
        n<=(uintptr_t)m.BaseAddress+m.RegionSize-p;
}
static uint64_t war3_catalog_mix(uint64_t h,uint64_t v) {
    for(unsigned n=0;n<8;++n){h=(h^(uint8_t)v)*1099511628211ULL;v>>=8;}return h;
}
#include "war3_quest_binding.h"
static uint32_t hash(const char *name){return 11;}
static void q(void *p,size_t at,uint64_t v){memcpy((char *)p+at,&v,8);}
int wmain(int argc,wchar_t **argv) {
    if(argc!=2)return 90;int scenario=(int)wcstol(argv[1],0,10);
    uint8_t *image=calloc(1,8),*vm=calloc(1,0x4900),*trigger=calloc(1,0xb0);
    uint8_t *action=calloc(1,0x60),*callback=calloc(1,0x60),*list=calloc(1,24);
    uint8_t *table=calloc(1,0x48),*bucket=calloc(1,24),*symbol=calloc(1,0x40);
    uint8_t *references=calloc(1,24),*code=calloc(1,32);
    uint64_t entries[2]={0,(uint64_t)(uintptr_t)code};
    q(vm,0x48c8,(uintptr_t)table);q(vm,0x48d0,(uintptr_t)references);
    q(table,0,(uintptr_t)image+0x2466638);q(table,0x30,(uintptr_t)bucket);
    q(bucket,0x10,(uintptr_t)symbol);q(symbol,0,11);q(symbol,8,1);
    q(symbol,0x28,(uintptr_t)"FinishAction");q(symbol,0x30,(uintptr_t)code);
    q(trigger,0x98,(uintptr_t)list);q(list,8,1);q(list,0x10,(uintptr_t)action);
    q(action,0,(uintptr_t)image+0x23d8448);q(action,0x18,100);q(action,0x58,(uintptr_t)callback);
    q(callback,0,(uintptr_t)image+0x23d7d50);q(callback,0x18,101);q(callback,0x58,1);
    q(references,0,2);q(references,8,(uintptr_t)entries);q(references,16,2);
    War3QuestBinding binding={0};binding.count=1;
    binding.actions[0].text="FinishAction";binding.actions[0].length=12;
    if(scenario==1)q(trigger,0x80,(uintptr_t)list);
    if(scenario==2)q(callback,0,0);
    if(scenario==3)entries[1]=0;
    if(scenario==4)q(list,8,(uintptr_t)list);
    if(scenario==5)q(callback,0x58,2);
    if(scenario==6)q(symbol,0x28,(uintptr_t)"OtherAction");
    if(scenario==7)q(references,16,1);
    uint64_t fingerprint=1;DWORD error=war3_quest_check_binding(image,(uintptr_t)vm,
        (uintptr_t)trigger,&binding,hash,&fingerprint);
    return scenario==0?(error || fingerprint==1?91:0):(!error?92:0);
}
'''

@pytest.fixture(scope='module')
def binding_executable(tmp_path_factory):
    compiler=shutil.which('clang');assert compiler
    folder=tmp_path_factory.mktemp('r23-binding');src=folder/'binding.c';exe=folder/'binding.exe'
    src.write_text(HARNESS,encoding='utf8')
    result=subprocess.run([compiler,'-std=c11','-O2','-I',str(Path(__file__).parent/'tools'),
        str(src),'-o',str(exe)],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    return exe


@pytest.mark.parametrize('scenario',range(8),ids=['exact-action-reference','new-condition',
    'wrong-callback-type','changed-bytecode-reference','list-cycle','reference-out-of-range',
    'different-symbol','corrupt-capacity'])
def test_runtime_action_binding(binding_executable,scenario):
    result=subprocess.run([str(binding_executable),str(scenario)],capture_output=True,text=True)
    assert result.returncode==0,f'binding {scenario}: {result.returncode} {result.stderr}'
