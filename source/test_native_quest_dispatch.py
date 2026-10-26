"""Real coordinator + persistent store; controlled game boundary only."""
from pathlib import Path
import shutil
import struct
import subprocess
import pytest
from war3_native_quest import encode_quest_request,_request
from test_native_quest import _plan

HARNESS=r'''
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>
#include "war3_quest_wire.h"
#include "war3_quest_store.h"
#include "war3_quest_dispatch.h"
static unsigned calls=0,checks=0,scenario=0;
static DWORD inspect(const War3QuestWire *wire,War3QuestView *view,uint32_t *message) {
    ++checks;memset(view,0,sizeof(*view));
    uint64_t r[8]={0x10000,100,0x20000,1000,101,0x30000,1001,999};
    memcpy(view->resolved,r,sizeof(r));view->flags=4;
    if(scenario==4 && calls) {view->flags|=1;}
    if(scenario==5 && checks>1){*message=1;return ERROR_RETRY;}
    if(scenario==6 && calls){*message=2;return ERROR_RETRY;}
    if(scenario==7 && checks>1)view->resolved[3]=1002;
    if(scenario==8)view->flags|=1;
    return 0;
}
static DWORD dispatch(const War3QuestView *view) {
    if(g_quest_store.state->ledger.count!=1 ||
       g_quest_store.state->ledger.records[0].status!=WAR3_QUEST_DISPATCHED)return ERROR_INVALID_DATA;
    ++calls;if(scenario==3)RaiseException(0xe1230001,0,0,0);return 0;
}
int wmain(int argc,wchar_t **argv) {
    if(argc!=3)return 90;scenario=(unsigned)wcstol(argv[2],0,10);
    FILE *f=_wfopen(argv[1],L"rb");if(!f)return 91;
    uint64_t h[8192],reply[32];uint32_t count=(uint32_t)fread(h,8,8192,f);fclose(f);
    War3QuestWire *wire=calloc(1,sizeof(*wire));if(!war3_quest_wire_parse(h,count,wire))return 92;
    if(war3_quest_transaction(wire,reply,inspect,dispatch))return 93;
    if(scenario==8)return reply[23]==1 && !calls?0:94;
    if(reply[23]!=0)return 95;
    h[2]=1;memcpy(h+22,reply+8,16);memcpy(h+24,reply+10,16);
    memcpy(h+26,reply+12,8*8);h[34]=1;h[35]=2;
    if(scenario==2)g_quest_store.state->proofs[0].tick=GetTickCount64()-3000;
    if(war3_quest_transaction(wire,reply,inspect,dispatch))return 96;
    if(scenario==2 || scenario==5 || scenario==7)
        return reply[23]==1 && !calls && !g_quest_store.state->ledger.count?0:97;
    if(scenario==3 || scenario==6)return reply[23]==4 && calls==1 && (reply[29]&1)?0:98;
    if(scenario==4 && (reply[23]!=3 || !(reply[22]&1)))return 99;
    if(scenario==0 && (reply[23]!=2 || calls!=1))return 100;
    if(scenario==1) {
        h[34]=3;h[35]=4;h[3]=8; /* another request/catalog token, same live quest */
        if(war3_quest_transaction(wire,reply,inspect,dispatch))return 101;
        return calls==1 && (reply[29]&3)==3 && reply[27]==1 && reply[28]==2?0:102;
    }
    if(scenario==9) {
        h[2]=2;scenario=4;
        if(war3_quest_transaction(wire,reply,inspect,dispatch))return 103;
        return calls==1 && reply[23]==3 && (reply[29]&1)?0:104;
    }
    return calls==1?0:105;
}
'''

@pytest.fixture(scope='module')
def dispatch_executable(tmp_path_factory):
    compiler=shutil.which('clang');assert compiler
    folder=tmp_path_factory.mktemp('r23-dispatch');src=folder/'dispatch.c';exe=folder/'dispatch.exe'
    src.write_text(HARNESS,encoding='utf8')
    result=subprocess.run([compiler,'-std=c11','-O2','-I',str(Path(__file__).parent/'tools'),
        str(src),'-o',str(exe)],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    return exe


@pytest.mark.parametrize('scenario',range(10),ids=['dispatch-recorded-first','duplicate-token-change',
    'expired-proof','exception-after-dispatch','observed-complete','source-changed-before',
    'map-changed-after','instance-changed','already-complete','observe-without-retry'])
def test_native_dispatch_coordinator(dispatch_executable,tmp_path,scenario):
    words=encode_quest_request(_request(_plan(),'inspect'));path=tmp_path/'request.bin'
    path.write_bytes(struct.pack('<'+'Q'*len(words),*words))
    result=subprocess.run([str(dispatch_executable),str(path),str(scenario)],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,f'dispatch {scenario}: {result.returncode} {result.stderr}'
