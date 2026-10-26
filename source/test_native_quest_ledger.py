"""Compile and exercise the real at-most-once ledger without loading a game."""
from pathlib import Path
import shutil
import subprocess
import pytest


HARNESS=r'''
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include "war3_quest_ledger.h"
static int run(int scenario) {
    War3QuestLedger ledger={0};
    War3QuestKey key={7,0x10000,100,0x20000};
    uint64_t request[2]={1,2},other_request[2]={3,4},plan[4]={5,6,7,8};
    War3QuestRecord *first=0,*second=0;
    if(scenario==0) {
        int dispatched=0;
        int a=war3_quest_reserve(&ledger,&key,request,plan,100,&first);
        if(a!=WAR3_QUEST_RESERVED || !first || first->status!=WAR3_QUEST_DISPATCHED) return 1;
        if(a==WAR3_QUEST_RESERVED) ++dispatched;
        key.token=8; /* source revalidation can retire a catalog token */
        int b=war3_quest_reserve(&ledger,&key,other_request,plan,101,&second);
        if(b==WAR3_QUEST_RESERVED) ++dispatched;
        if(b!=WAR3_QUEST_DUPLICATE || first!=second || dispatched!=1 || ledger.count!=1) return 2;
        return 0;
    }
    if(scenario==1) {
        if(war3_quest_reserve(&ledger,&key,request,plan,100,&first)!=WAR3_QUEST_RESERVED) return 3;
        key.quest_full=101;
        if(war3_quest_reserve(&ledger,&key,request,plan,101,&second)!=WAR3_QUEST_REQUEST_CONFLICT) return 4;
        if(second || ledger.count!=1 || first->key.quest_full!=100) return 5;
        return 0;
    }
    if(scenario==2) {
        if(war3_quest_reserve(&ledger,&key,request,plan,100,&first)!=WAR3_QUEST_RESERVED) return 6;
        /* A lost/late RPC reply never erases the pre-dispatch record. */
        first->status=WAR3_QUEST_UNKNOWN;
        if(war3_quest_reserve(&ledger,&key,other_request,plan,101,&second)!=WAR3_QUEST_DUPLICATE) return 7;
        if(first!=second || second->status!=WAR3_QUEST_UNKNOWN || ledger.count!=1) return 8;
        return 0;
    }
    if(scenario==3) {
        for(unsigned n=0;n<WAR3_QUEST_LEDGER_CAPACITY;++n) {
            key.quest_full=100+n;key.quest_object=0x20000+n*8;
            request[0]=n+1;
            if(war3_quest_reserve(&ledger,&key,request,plan,100+n,&first)!=WAR3_QUEST_RESERVED) return 9;
        }
        key.quest_full=9999;key.quest_object=0x50000;request[0]=9999;
        if(war3_quest_reserve(&ledger,&key,request,plan,9999,&second)!=WAR3_QUEST_LEDGER_FULL) return 10;
        key.quest_full=100;key.quest_object=0x20000;request[0]=1;
        if(war3_quest_reserve(&ledger,&key,request,plan,9999,&second)!=WAR3_QUEST_DUPLICATE) return 11;
        if(ledger.count!=WAR3_QUEST_LEDGER_CAPACITY) return 12;
        return 0;
    }
    if(scenario==4) {
        if(war3_quest_reserve(&ledger,&key,request,plan,100,&first)!=WAR3_QUEST_RESERVED) return 13;
        key.quest_full=101; /* recycled address, different concrete generation */
        if(war3_quest_reserve(&ledger,&key,other_request,plan,101,&second)!=WAR3_QUEST_RESERVED) return 14;
        if(first==second || ledger.count!=2) return 15;
        return 0;
    }
    if(scenario==5) {
        request[0]=request[1]=0;
        if(war3_quest_reserve(&ledger,&key,request,plan,100,&first)!=WAR3_QUEST_LEDGER_INVALID) return 16;
        if(first || ledger.count) return 17;
        return 0;
    }
    return 99;
}
int wmain(int argc,wchar_t **argv) {return argc==2?run((int)wcstol(argv[1],0,10)):98;}
'''


@pytest.fixture(scope='module')
def ledger_executable(tmp_path_factory):
    compiler=shutil.which('clang')
    assert compiler,'Use the documented existing R23/R22 clang toolchain on PATH'
    folder=tmp_path_factory.mktemp('r23-ledger');source=folder/'ledger.c';exe=folder/'ledger.exe'
    source.write_text(HARNESS,encoding='utf8')
    result=subprocess.run([compiler,'-std=c11','-O2','-I',str(Path(__file__).parent/'tools'),
        str(source),'-o',str(exe)],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    return exe


@pytest.mark.parametrize('scenario',range(6),ids=[
    'record-before-dispatch-and-token-refresh','request-conflict','unknown-never-retries',
    'capacity-never-evicts','recycled-object-generation','invalid-request'])
def test_native_ledger_contract(ledger_executable,scenario):
    result=subprocess.run([str(ledger_executable),str(scenario)],capture_output=True,text=True)
    assert result.returncode==0,f'ledger scenario {scenario}: exit={result.returncode} {result.stdout} {result.stderr}'
