/* R23 process-owned at-most-once state. Handles/views deliberately remain open
   until process exit: unloading/reloading the helper must not erase rewards'
   dispatch records. No game/native call belongs in this storage layer. */
#ifndef WAR3_QUEST_STORE_H
#define WAR3_QUEST_STORE_H
#include <windows.h>
#include <stdio.h>
#include "war3_quest_ledger.h"
#define WAR3_QUEST_STORE_MAGIC 0x31545351u
#define WAR3_QUEST_PROOFS 32u
typedef struct War3QuestStoredProof {
    uint64_t nonce[2],tick,header[31],resolved[8];
    uint32_t consumed,reserved;
} War3QuestStoredProof;
typedef struct War3QuestState {
    uint32_t magic,version,size,pid;
    uint64_t created,epoch[2];
    uint32_t next_proof,poisoned,busy,reserved;
    War3QuestLedger ledger;
    War3QuestStoredProof proofs[WAR3_QUEST_PROOFS];
} War3QuestState;
typedef struct War3QuestStore {
    HANDLE mutex,marker,mapping;War3QuestState *state;
} War3QuestStore;
static War3QuestStore g_quest_store={0};

static inline DWORD war3_quest_process_created(uint64_t *created) {
    FILETIME c,e,k,u;
    if(!GetProcessTimes(GetCurrentProcess(),&c,&e,&k,&u))return GetLastError();
    *created=((uint64_t)c.dwHighDateTime<<32)|c.dwLowDateTime;return ERROR_SUCCESS;
}

static inline void war3_quest_store_name(wchar_t name[128],const wchar_t *part,uint64_t created) {
    _snwprintf(name,128,L"Local\\War3FullCloneQuest.1.%lu.%016llx.%ls",
        GetCurrentProcessId(),(unsigned long long)created,part);name[127]=0;
}

static inline DWORD war3_quest_nonce(uint64_t nonce[2]) {
    typedef BOOLEAN (WINAPI *RandomFn)(PVOID,ULONG);
    HMODULE library=LoadLibraryExW(L"advapi32.dll",NULL,LOAD_LIBRARY_SEARCH_SYSTEM32);
    if(!library)return GetLastError();
    RandomFn random=(RandomFn)(void *)GetProcAddress(library,"SystemFunction036");
    BOOLEAN valid=random?random(nonce,16):FALSE;FreeLibrary(library);
    return valid && (nonce[0]|nonce[1])?ERROR_SUCCESS:ERROR_GEN_FAILURE;
}

static inline void war3_quest_store_unlock(War3QuestStore *store) {
    if(store && store->mutex)ReleaseMutex(store->mutex);
}

static inline DWORD war3_quest_store_lock(War3QuestStore *out) {
    if(!out)return ERROR_INVALID_PARAMETER;
    memset(out,0,sizeof(*out));uint64_t created=0;
    DWORD error=war3_quest_process_created(&created);if(error)return error;
    wchar_t name[128];
    if(!g_quest_store.mutex) {
        war3_quest_store_name(name,L"mutex",created);
        g_quest_store.mutex=CreateMutexW(NULL,FALSE,name);
        if(!g_quest_store.mutex)return GetLastError();
    }
    DWORD wait=WaitForSingleObject(g_quest_store.mutex,0);
    if(wait!=WAIT_OBJECT_0) {
        if(wait==WAIT_ABANDONED) {
            if(g_quest_store.state)g_quest_store.state->poisoned=1;
            /* A fresh DLL may not have mapped the shared state yet. Persist
               poison in the process-owned marker as well, before releasing. */
            if(!g_quest_store.marker) {
                war3_quest_store_name(name,L"mark",created);
                g_quest_store.marker=CreateEventW(NULL,TRUE,FALSE,name);
            }
            if(g_quest_store.marker)SetEvent(g_quest_store.marker);
            /* Never recover an interrupted possibly-dispatched transaction. */
            ReleaseMutex(g_quest_store.mutex);return ERROR_INVALID_DATA;
        }
        return wait==WAIT_TIMEOUT?ERROR_BUSY:GetLastError();
    }
    if(!g_quest_store.state) {
        war3_quest_store_name(name,L"mark",created);
        g_quest_store.marker=CreateEventW(NULL,TRUE,FALSE,name);
        if(!g_quest_store.marker) {error=GetLastError();goto failed;}
        int previous=GetLastError()==ERROR_ALREADY_EXISTS;
        if(WaitForSingleObject(g_quest_store.marker,0)==WAIT_OBJECT_0) {error=ERROR_INVALID_DATA;goto failed;}
        war3_quest_store_name(name,L"map",created);
        g_quest_store.mapping=previous?OpenFileMappingW(FILE_MAP_ALL_ACCESS,FALSE,name):
            CreateFileMappingW(INVALID_HANDLE_VALUE,NULL,PAGE_READWRITE,0,sizeof(War3QuestState),name);
        if(!g_quest_store.mapping) {error=previous?ERROR_INVALID_DATA:GetLastError();goto failed;}
        if(!previous && GetLastError()==ERROR_ALREADY_EXISTS) {error=ERROR_INVALID_DATA;goto failed;}
        g_quest_store.state=(War3QuestState *)MapViewOfFile(g_quest_store.mapping,FILE_MAP_ALL_ACCESS,0,0,sizeof(War3QuestState));
        if(!g_quest_store.state) {error=GetLastError();goto failed;}
        if(!previous) {
            War3QuestState *s=g_quest_store.state;memset(s,0,sizeof(*s));
            s->version=1;s->size=sizeof(*s);s->pid=GetCurrentProcessId();s->created=created;
            if((error=war3_quest_nonce(s->epoch)))goto failed;
            MemoryBarrier();s->magic=WAR3_QUEST_STORE_MAGIC;
        }
    }
    War3QuestState *s=g_quest_store.state;
    if(s->magic!=WAR3_QUEST_STORE_MAGIC || s->version!=1 || s->size!=sizeof(*s) ||
       s->pid!=GetCurrentProcessId() || s->created!=created || !(s->epoch[0]|s->epoch[1]) ||
       s->poisoned || s->reserved || WaitForSingleObject(g_quest_store.marker,0)!=WAIT_TIMEOUT ||
       s->ledger.reserved || s->ledger.count>WAR3_QUEST_LEDGER_CAPACITY ||
       s->next_proof>=WAR3_QUEST_PROOFS) {error=ERROR_INVALID_DATA;goto failed;}
    *out=g_quest_store;return ERROR_SUCCESS;
failed:
    ReleaseMutex(g_quest_store.mutex);return error;
}
#endif
