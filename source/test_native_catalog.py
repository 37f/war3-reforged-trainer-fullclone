"""Exercise the real bounded C reader against owned synthetic process memory."""
import ctypes as C
from pathlib import Path
import shutil
import struct
import subprocess

import pytest

from war3_current_map_catalog import parse_catalog_header,parse_catalog_page

ROOT=Path(__file__).parent
HARNESS=r'''
#include "HELPER_SOURCE"
__declspec(dllexport) DWORD catalog_test(uint64_t *roots,unsigned op,unsigned kind,uint64_t start,
    uint64_t token,uint64_t *output,unsigned capacity,unsigned *count) {
    War3CatalogRoots view={0}; uint64_t *data=NULL; uint32_t words=0;
    view.context=1;view.state=2;view.jass=3;view.image=(uint8_t *)0x180000000ULL;
    for(unsigned i=0;i<3;++i) view.definitions[i]=roots[i];
    DWORD error=war3_catalog_from_roots(&view,op,kind,start,token,&data,&words);
    *count=words;
    if(!error && words>capacity) error=ERROR_INSUFFICIENT_BUFFER;
    if(!error && words) memcpy(output,data,words*8);
    if(data) HeapFree(GetProcessHeap(),0,data);
    return error;
}
__declspec(dllexport) void catalog_invalidate(void) {war3_catalog_retire();}
static uint8_t ui_object[0x10];static unsigned ui_available,ui_bad;
static void *catalog_fake_ui(uint8_t create,uint8_t async) {
    if(create || async) ++ui_bad;
    return ui_available?ui_object:NULL;
}
__declspec(dllexport) DWORD catalog_ui_test(unsigned available) {
    uint64_t value=0;ui_available=available;ui_bad=0;
    g_catalog_ui_module=(uint8_t *)GetModuleHandleW(NULL);
    g_catalog_ui_getter=catalog_fake_ui;
    DWORD error=war3_catalog_existing_ui(g_catalog_ui_module,&value);
    return ui_bad?999:error;
}
'''


@pytest.fixture(scope='module')
def native(tmp_path_factory):
    compiler=shutil.which('clang')
    assert compiler,'existing SEH-enabled clang must be on PATH'
    path=tmp_path_factory.mktemp('native-catalog')
    source=path/'harness.c';dll=path/'harness.dll'
    source.write_text(HARNESS.replace('HELPER_SOURCE',(ROOT/'tools/war3_native_helper.c').as_posix()),encoding='utf8')
    subprocess.run([compiler,'-shared','-O2','-Wno-microsoft-goto',str(source),'-o',str(dll),'-luser32'],check=True,capture_output=True,text=True)
    library=C.WinDLL(str(dll))
    library.catalog_test.argtypes=[C.POINTER(C.c_uint64),C.c_uint,C.c_uint,C.c_uint64,C.c_uint64,C.POINTER(C.c_uint64),C.c_uint,C.POINTER(C.c_uint)]
    library.catalog_test.restype=C.c_uint32
    return library


class Memory:
    def __init__(self): self.blocks=[]
    def block(self,size):
        value=C.create_string_buffer(size);self.blocks.append(value);return C.addressof(value)
    def put(self,address,fmt,*values): C.memmove(address,struct.pack(fmt,*values),struct.calcsize(fmt))
    def definitions(self,names=('队长',),base=b'hfoo',raw=b'H600',custom=True):
        root=self.block(0x80);row=self.block(40)
        self.put(root,'<Q',0x180000000+0x242c6b0)
        self.put(root+(32 if custom else 8),'<I4xQI',1,row,1)
        self.put(row,'<4s4sQQQ',base,raw if custom else b'\0'*4,1,self.block(8),1)
        table=C.c_uint64.from_address(row+16).value
        node=self.block(40);self.put(table,'<Q',node)
        mods=self.block(72*len(names))
        self.put(node+8,'<I4xI4xQI',0,len(names),mods,len(names))
        for index,name in enumerate(names):
            data=name.encode('utf8');text=self.block(len(data)+1);C.memmove(text,data,len(data))
            self.put(mods+72*index,'<4sIII',b'unam',3,0,0)
            self.put(mods+72*index+24,'<QQQ',text,len(data),len(data))
        return root,row,node,mods


def query(native,roots,op=318,kind=0,start=0,token=0):
    output=(C.c_uint64*32768)();count=C.c_uint()
    error=native.catalog_test((C.c_uint64*3)(*roots),op,kind,start,token,output,len(output),C.byref(count))
    return error,tuple(output[:count.value]) if not error else ()


def test_real_c_reader_roundtrip_and_no_source_writes(native):
    memory=Memory();root,row,node,mods=memory.definitions()
    before=[bytes(b) for b in memory.blocks]
    error,header=query(native,(root,0,0));assert error==0
    token,counts=parse_catalog_header(header);assert counts==(1,0,0)
    error,data=query(native,(root,0,0),319,token=token);assert error==0
    record=parse_catalog_page(data,token,'unit',0).records[0]
    assert record.rawcode==b'H600' and record.names[0].value=='队长'
    assert before==[bytes(b) for b in memory.blocks]


@pytest.mark.parametrize('fault',('count','vtable','row_pointer','buckets','cycle','field_count','name_length','bad_pointer','wrong_name_type'))
def test_real_c_reader_rejects_invalid_memory(native,fault):
    m=Memory();root,row,node,mods=m.definitions()
    if fault=='count': m.put(root+32,'<I',100001)
    if fault=='vtable': m.put(root,'<Q',0)
    if fault=='row_pointer': m.put(root+40,'<Q',1)
    if fault=='buckets': m.put(row+8,'<Q',65537)
    if fault=='cycle': m.put(node,'<Q',node)
    if fault=='field_count': m.put(node+16,'<I',1000001)
    if fault=='name_length': m.put(mods+32,'<Q',65537)
    if fault=='bad_pointer': m.put(mods+24,'<Q',1)
    if fault=='wrong_name_type': m.put(mods+4,'<I',0)
    assert query(native,(root,0,0))[0]!=0


def test_real_c_reader_names_and_stale_content_or_reused_context(native):
    m=Memory();root,row,node,mods=m.definitions(('甲','乙'))
    error,header=query(native,(root,0,0));token,_=parse_catalog_header(header)
    error,data=query(native,(root,0,0),319,token=token)
    assert [n.value for n in parse_catalog_page(data,token,'unit',0).records[0].names]==['甲','乙']
    text=C.c_uint64.from_address(mods+24).value;m.put(text,'<3s','丙'.encode())
    assert query(native,(root,0,0),319,token=token)[0]!=0
    fresh=parse_catalog_header(query(native,(root,0,0))[1])[0]
    native.catalog_invalidate()
    assert query(native,(root,0,0),319,token=fresh)[0]!=0


def test_real_c_reader_empty_table_and_cursor_validation(native):
    error,header=query(native,(0,0,0));assert error==0 and parse_catalog_header(header)[1]==(0,0,0)
    m=Memory();root,*_=m.definitions(raw=b'hfoo',custom=False)
    token,_=parse_catalog_header(query(native,(root,0,0))[1])
    assert query(native,(root,0,0),319,start=1,token=token)[0]!=0
    assert query(native,(root,0,0),319,kind=3,token=token)[0]!=0


def test_menu_cached_definitions_require_existing_game_ui_without_initialization(native):
    assert native.catalog_ui_test(0)==21  # ERROR_NOT_READY, never create a UI.
    assert native.catalog_ui_test(1)==0
