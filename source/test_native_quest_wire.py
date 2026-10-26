"""The game-side parser consumes the exact Python encoder, including bad input."""
from pathlib import Path
import shutil
import struct
import subprocess
import pytest
from war3_native_quest import encode_quest_request
from test_native_quest import _plan
from war3_native_quest import _request

HARNESS=r'''
#include <stdio.h>
#include <stdlib.h>
#include <wchar.h>
#include "war3_quest_wire.h"
int wmain(int argc,wchar_t **argv) {
    if(argc!=3)return 90;
    FILE *f=_wfopen(argv[1],L"rb");if(!f)return 91;
    uint64_t words[WAR3_QUEST_MAX_WORDS+1];
    size_t n=fread(words,8,WAR3_QUEST_MAX_WORDS+1,f);fclose(f);
    War3QuestWire *wire=calloc(1,sizeof(*wire));if(!wire)return 92;
    int valid=war3_quest_wire_parse(words,(uint32_t)n,wire);
    if(valid && (wire->binding_count!=1 || wire->function_count!=1 ||
       !war3_quest_name_equal(wire->entry_function,wire->bindings[0].actions[0])))return 93;
    free(wire);return valid==(int)wcstol(argv[2],0,10)?0:94;
}
'''

@pytest.fixture(scope='module')
def wire_executable(tmp_path_factory):
    folder=tmp_path_factory.mktemp('r23-wire');src=folder/'wire.c';exe=folder/'wire.exe'
    src.write_text(HARNESS,encoding='utf8')
    compiler=shutil.which('clang');assert compiler
    result=subprocess.run([compiler,'-std=c11','-O2','-I',str(Path(__file__).parent/'tools'),
        str(src),'-o',str(exe)],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    return exe


@pytest.mark.parametrize('case',['valid','short','too-long','magic','version','mode',
    'zero-token','zero-file','inspect-address','bad-name','padding','huge-name','trailing'])
def test_game_side_wire_parser(wire_executable,tmp_path,case):
    words=list(encode_quest_request(_request(_plan(),'inspect')))
    if case=='short':words=words[:35]
    elif case=='too-long':words=[0]*8193
    elif case=='magic':words[0]^=1
    elif case=='version':words[1]=2
    elif case=='mode':words[2]=3
    elif case=='zero-token':words[3]=0
    elif case=='zero-file':words[6]=0
    elif case=='inspect-address':words[26]=0x20000
    elif case=='bad-name':words[37]=(words[37]&~255)|ord('-')
    elif case=='padding':
        length=words[36];assert length%8
        words[37+length//8]|=255<<(8*(length%8))
    elif case=='huge-name':words[36]=2**64-1
    elif case=='trailing':words.append(0)
    path=tmp_path/'request.bin';path.write_bytes(struct.pack('<'+'Q'*len(words),*words))
    result=subprocess.run([str(wire_executable),str(path),'1' if case=='valid' else '0'],capture_output=True,text=True)
    assert result.returncode==0,f'{case}: {result.returncode} {result.stderr}'
