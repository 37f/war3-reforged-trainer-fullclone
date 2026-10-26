"""Execution cannot trust script provenance while loose overrides are enabled."""
from pathlib import Path
import shutil
import subprocess
import pytest
HARNESS=r'''
#include <windows.h>
#include <stdlib.h>
#include <wchar.h>
#include "war3_quest_policy.h"
int wmain(int argc,wchar_t **argv) {
    if(argc!=2)return 90;int n=(int)wcstol(argv[1],0,10);
    DWORD kind=REG_DWORD,value=0,status=0;uint64_t changed=10,created=20;
    if(n==1)value=1;
    if(n==2)changed=21;
    if(n==3)kind=REG_SZ;
    if(n==4)status=ERROR_ACCESS_DENIED;
    if(n==5)value=2;
    DWORD e=war3_quest_override_policy(status,kind,value,changed,created);
    return n==0?(e?91:0):(!e?92:0);
}
'''
@pytest.mark.parametrize('scenario',range(6))
def test_source_override_policy(tmp_path,scenario):
    src=tmp_path/'policy.c';exe=tmp_path/'policy.exe';src.write_text(HARNESS,encoding='utf8')
    compiler=shutil.which('clang');assert compiler
    result=subprocess.run([compiler,'-std=c11','-O2','-I',str(Path(__file__).parent/'tools'),
        str(src),'-o',str(exe)],capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    result=subprocess.run([str(exe),str(scenario)],capture_output=True,text=True)
    assert result.returncode==0,f'policy {scenario}: {result.returncode} {result.stderr}'
