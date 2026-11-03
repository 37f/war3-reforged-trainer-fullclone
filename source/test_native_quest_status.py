"""Run the actual C binding/getter adapter against a bounded synthetic VM."""
from pathlib import Path
import shutil
import subprocess
import pytest

HARNESS=r'''
#include <windows.h>
#include <stdint.h>
#include <string.h>
typedef struct {uint64_t unit_handle;uint32_t op_count,reserved;} NativeCommand;
typedef struct {uint32_t kind,rawcode;uint64_t handler,arg0,arg1;} NativeOp;
typedef struct {uint32_t rva,size;uint64_t hash;} War3BootstrapCodeCheck;
typedef uint32_t (*War3NameHashFn)(const char *);
#define WAR3_BOOTSTRAP_HASH_RVA 0x2e6940u
#define WAR3_NATIVE_OP_EXT_QUERY_CATALOG_HEADER 318u
static int war3_readable_span(uint64_t p,size_t n){return p>=0x10000 && n>0;}
static DWORD war3_bootstrap_context(uint8_t **i,uint8_t **t){return ERROR_NOT_SUPPORTED;}
static DWORD war3_catalog_query(NativeCommand *c,NativeOp *o,uint64_t **p,uint32_t *n){return ERROR_NOT_SUPPORTED;}
static uint64_t war3_bootstrap_hash(const uint8_t *p,size_t n){return 0;}
static int war3_bootstrap_index(const char *n){return -1;}
static DWORD war3_bootstrap_query(uint8_t *i,uint8_t *t,uint32_t n,uint64_t *v){return ERROR_NOT_SUPPORTED;}
#include "war3_native_quest_status.h"
static void returns64(uint8_t *p,uint64_t value){p[0]=0x48;p[1]=0xb8;memcpy(p+2,&value,8);p[10]=0xc3;}
int main(void){
 uint8_t *image=VirtualAlloc(0,0xb00000,MEM_RESERVE|MEM_COMMIT,PAGE_EXECUTE_READWRITE);
 uint8_t *vm=HeapAlloc(GetProcessHeap(),HEAP_ZERO_MEMORY,0x4900);
 uint64_t table[10]={0},buckets[3]={0},node[8]={0},second[8]={0},object[32]={0},row[5]={0};
 if(!image || !vm)return 90;
 table[0]=(uintptr_t)image+0x2466598u;table[6]=(uintptr_t)buckets;table[8]=0;
 buckets[2]=(uintptr_t)node;node[0]=0x99;node[5]=(uintptr_t)"q";
 ((uint32_t *)node)[12]=7;((uint32_t *)node)[13]=7;node[7]=0x100001;
 *(uint64_t *)(vm+0x4878)=(uintptr_t)table;
 object[0]=(uintptr_t)image+0x23d8fe0u;object[3]=0x12000001;
 returns64(image+0xa0f100,(uintptr_t)object);returns64(image+WAR3_BOOTSTRAP_HASH_RVA,0x99);
 for(unsigned flags=0;flags<4;++flags){
  /* High bits deliberately nonzero even for false. This catches bool ABI regressions. */
  returns64(image+0x10000,0x1234500|(flags&1));returns64(image+0x10020,0x2345600|((flags>>1)&1));
  FlushInstructionCache(GetCurrentProcess(),image,0xb00000);
  DWORD e=war3_quest_status_one(image,(uintptr_t)vm,"q",1,(uintptr_t)(image+0x10000),(uintptr_t)(image+0x10020),row);
  if(e || row[4]!=flags || row[1]!=0x100001 || row[3]!=object[3])return 10+flags;
 }
 node[7]=0;if(war3_quest_status_one(image,(uintptr_t)vm,"q",1,0,0,row)!=ERROR_INVALID_HANDLE)return 20;
 node[7]=0x100001;object[3]=0;
 if(war3_quest_status_one(image,(uintptr_t)vm,"q",1,0,0,row)!=ERROR_INVALID_HANDLE)return 21;
 object[3]=1;((uint32_t *)node)[12]=8;
 if(war3_quest_status_one(image,(uintptr_t)vm,"q",1,0,0,row)!=ERROR_INVALID_DATA)return 22;
 ((uint32_t *)node)[12]=7;memcpy(second,node,sizeof(node));node[1]=(uintptr_t)second;
 uint64_t found=0;if(war3_quest_status_symbol(image,(uintptr_t)vm,"q",1,&found)!=ERROR_DUP_NAME)return 23;
 HeapFree(GetProcessHeap(),0,vm);VirtualFree(image,0,MEM_RELEASE);return 0;
}
'''


def test_c_adapter_rejects_ambiguous_stale_objects_and_reads_only_boolean_low_byte(tmp_path):
    compiler=shutil.which('clang')
    assert compiler,'SEH-capable clang is required for the native adapter acceptance check'
    source=tmp_path/'quest-status.c';exe=tmp_path/'quest-status.exe'
    source.write_text(HARNESS,encoding='utf8')
    command=[compiler,'-fms-extensions','-fseh-exceptions','-O2','-I',str(Path(__file__).parent/'tools'),
        str(source),'-o',str(exe)]
    built=subprocess.run(command,capture_output=True,text=True)
    assert built.returncode==0,built.stdout+built.stderr
    ran=subprocess.run([str(exe)],capture_output=True,text=True)
    assert ran.returncode==0,f'{ran.returncode}: {ran.stdout} {ran.stderr}'
