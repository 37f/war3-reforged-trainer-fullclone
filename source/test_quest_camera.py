"""The isolated camera path accepts coordinates, never units or script execution."""
import ctypes
from pathlib import Path
import shutil
import struct
import subprocess
import threading
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

HARNESS=r'''
#include <windows.h>
#include <stdint.h>
#include <string.h>
typedef struct {uint64_t unit_handle;uint32_t reserved,op_count;} NativeCommand;
typedef struct {uint32_t kind,rawcode;uint64_t handler,arg0,arg1,result;} NativeOp;
#define WAR3_NATIVE_OP_EXT_QUERY_CATALOG_HEADER 318u
static uint64_t token=7;static unsigned moved=0;static float actual_x,actual_y,actual_time;
static void camera(const float *x,const float *y,const float *t){++moved;actual_x=*x;actual_y=*y;actual_time=*t;}
static DWORD war3_catalog_query(NativeCommand *c,NativeOp *o,uint64_t **h,uint32_t *n){
 *h=HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,6*8);*n=6;(*h)[2]=token;return 0;
}
static DWORD war3_bootstrap_context(uint8_t **i,uint8_t **t){*i=*t=(uint8_t *)1;return 0;}
static int war3_bootstrap_index(const char *n){return strcmp(n,"PanCameraToTimed")?-1:5;}
static DWORD war3_bootstrap_query(uint8_t *i,uint8_t *t,uint32_t n,uint64_t *out){*out=(uintptr_t)camera;return 0;}
#include "war3_quest_camera.h"
int main(void){
 NativeCommand c={0};NativeOp op={0};c.op_count=1;op.arg1=7;
 float coordinates[2]={-125.5f,400.25f};memcpy(&op.arg0,coordinates,8);
 if(war3_quest_camera(&c,&op) || moved!=1 || actual_x!=-125.5f || actual_y!=400.25f || actual_time!=0.25f || op.result!=op.arg0)return 1;
 token=8;if(war3_quest_camera(&c,&op)!=ERROR_RETRY || moved!=1)return 2;
 token=7;op.handler=1;if(war3_quest_camera(&c,&op)!=ERROR_INVALID_PARAMETER || moved!=1)return 3;
 op.handler=0;c.unit_handle=1;if(war3_quest_camera(&c,&op)!=ERROR_INVALID_PARAMETER || moved!=1)return 4;
 c.unit_handle=0;op.arg0=0x7fc00000;if(war3_quest_camera(&c,&op)!=ERROR_INVALID_PARAMETER || moved!=1)return 5;
 op.arg0=0x7f800000;if(war3_quest_camera(&c,&op)!=ERROR_INVALID_PARAMETER || moved!=1)return 6;
 return 0;
}
'''


def test_actual_c_camera_guards_session_and_passes_real_pointer_arguments(tmp_path):
    compiler=shutil.which('clang');assert compiler
    src=tmp_path/'camera.c';exe=tmp_path/'camera.exe';src.write_text(HARNESS,encoding='utf8')
    built=subprocess.run([compiler,'-fms-extensions','-fseh-exceptions','-O2','-I',str(Path(__file__).parent/'tools'),
        str(src),'-o',str(exe)],capture_output=True,text=True)
    assert built.returncode==0,built.stdout+built.stderr
    ran=subprocess.run([str(exe)],capture_output=True,text=True)
    assert ran.returncode==0,f'{ran.returncode}: {ran.stdout} {ran.stderr}'


@pytest.mark.parametrize('valid',[True,False])
def test_python_camera_uses_only_new_command_and_rejects_stale_source(valid):
    from war3_reforged_trainer import War3Trainer
    trainer=object.__new__(War3Trainer);trainer._native_helper_lock=threading.RLock()
    client=SimpleNamespace(identity=lambda:'same',check=lambda snapshot:valid)
    trainer.current_map_script_client=lambda:client;trainer.focus=Mock()
    packed=struct.unpack('<Q',struct.pack('<ff',12.5,-24.))[0]
    trainer._run_native_helper_ops=Mock(return_value=[SimpleNamespace(kind=325,result=packed)])
    report=SimpleNamespace(snapshot=SimpleNamespace(identity='same',session_token=7))
    point=SimpleNamespace(x=12.5,y=-24.)
    if valid:
        trainer.show_quest_location(report,point)
        trainer._run_native_helper_ops.assert_called_once_with(0,((325,0,0,packed,7),),timeout_ms=5000)
        trainer.focus.assert_called_once()
    else:
        with pytest.raises(RuntimeError,match='来源已变化'):trainer.show_quest_location(report,point)
        trainer._run_native_helper_ops.assert_not_called()
        trainer.focus.assert_not_called()
