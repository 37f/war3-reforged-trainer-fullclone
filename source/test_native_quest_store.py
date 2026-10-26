"""Real Windows mapping/mutex/reload checks, with no game attached."""
from pathlib import Path
import shutil
import subprocess
import pytest

LIBRARY=r'''
#include <windows.h>
#include "war3_quest_store.h"
__declspec(dllexport) DWORD check(unsigned action) {
    War3QuestStore store={0};DWORD e=war3_quest_store_lock(&store);if(e)return e;
    if(action==0) {
        War3QuestKey k={7,0x10000,100,0x20000};uint64_t r[2]={1,2},p[4]={3,4,5,6};
        War3QuestRecord *out=0;
        if(war3_quest_reserve(&store.state->ledger,&k,r,p,1,&out)!=WAR3_QUEST_RESERVED)e=10001;
    } else if(action==1) {
        if(store.state->ledger.count!=1 || store.state->ledger.records[0].request[0]!=1)e=10002;
    } else if(action==2)store.state->magic=0;
    else if(action==3)return 0; /* simulate transaction owner thread exiting */
    war3_quest_store_unlock(&store);return e;
}
'''
HARNESS=r'''
#include <windows.h>
#include <wchar.h>
#include "war3_quest_store.h"
typedef DWORD (*Check)(unsigned);
static DWORD WINAPI library_abandon(void *fn) {return ((Check)fn)(3);}
static DWORD WINAPI abandon(void *unused) {
    War3QuestStore store={0};return war3_quest_store_lock(&store);
}
int wmain(int argc,wchar_t **argv) {
    if(argc!=3)return 90;int scenario=(int)wcstol(argv[2],0,10);War3QuestStore store={0};
    if(scenario==1) {
        wchar_t name[128];uint64_t created=0;
        if(war3_quest_process_created(&created))return 91;
        war3_quest_store_name(name,L"mark",created);
        HANDLE marker=CreateEventW(0,TRUE,FALSE,name);if(!marker)return 92;
        return war3_quest_store_lock(&store)==ERROR_INVALID_DATA?0:93;
    }
    if(scenario==3) {
        HANDLE thread=CreateThread(0,0,abandon,0,0,0);if(!thread)return 94;
        WaitForSingleObject(thread,3000);DWORD code=1;GetExitCodeThread(thread,&code);CloseHandle(thread);
        if(code || war3_quest_store_lock(&store)!=ERROR_INVALID_DATA)return 95;
        return war3_quest_store_lock(&store)==ERROR_INVALID_DATA?0:104;
    }
    HMODULE lib=LoadLibraryW(argv[1]);if(!lib)return 96;
    Check fn=(Check)(void *)GetProcAddress(lib,"check");if(!fn || fn(0))return 97;
    if(scenario==2 && fn(2))return 98;
    if(scenario==4) {
        HANDLE thread=CreateThread(0,0,library_abandon,(void *)fn,0,0);if(!thread)return 105;
        WaitForSingleObject(thread,3000);CloseHandle(thread);
    }
    if(!FreeLibrary(lib))return 99;
    lib=LoadLibraryW(argv[1]);if(!lib)return 100;
    fn=(Check)(void *)GetProcAddress(lib,"check");if(!fn)return 101;
    if(scenario==4) {
        if(fn(1)!=ERROR_INVALID_DATA)return 106;
        return fn(1)==ERROR_INVALID_DATA?0:107;
    }
    DWORD result=fn(1);FreeLibrary(lib);
    return scenario==2?(result==ERROR_INVALID_DATA?0:102):(result?103:0);
}
'''

@pytest.fixture(scope='module')
def store_binaries(tmp_path_factory):
    compiler=shutil.which('clang');assert compiler
    folder=tmp_path_factory.mktemp('r23-store');inc=str(Path(__file__).parent/'tools')
    outputs=[]
    for stem,source,flags in [('store',LIBRARY,['-shared']),('harness',HARNESS,[])]:
        src=folder/(stem+'.c');out=folder/(stem+('.dll' if flags else '.exe'))
        src.write_text(source,encoding='utf8')
        result=subprocess.run([compiler,'-std=c11','-O2','-I',inc,*flags,str(src),'-o',str(out)],capture_output=True,text=True)
        assert result.returncode==0,result.stdout+result.stderr
        outputs.append(out)
    return outputs


@pytest.mark.parametrize('scenario',range(5),ids=['reload-preserves-ledger',
    'marker-without-mapping-refuses','corruption-never-resets','abandoned-mutex-refuses',
    'abandoned-lock-stays-refused-after-reload'])
def test_persistent_store(store_binaries,scenario):
    library,exe=store_binaries
    result=subprocess.run([str(exe),str(library),str(scenario)],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,f'store {scenario}: {result.returncode} {result.stdout} {result.stderr}'
