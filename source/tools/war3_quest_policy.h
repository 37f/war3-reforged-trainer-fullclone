/* R23 execution-only policy: do not change legacy custom-map reading. */
#ifndef WAR3_QUEST_POLICY_H
#define WAR3_QUEST_POLICY_H
#include <windows.h>
#include <stdint.h>
static inline DWORD war3_quest_override_policy(DWORD status,DWORD kind,DWORD value,
    uint64_t changed,uint64_t created) {
    if(status)return status;
    if(kind!=REG_DWORD || value>1)return ERROR_INVALID_DATA;
    if(value)return ERROR_NOT_SUPPORTED;
    return changed>created?ERROR_RETRY:ERROR_SUCCESS;
}

static inline DWORD war3_quest_no_local_override(uint64_t created) {
    typedef LSTATUS (WINAPI *OpenFn)(HKEY,LPCWSTR,DWORD,REGSAM,PHKEY);
    typedef LSTATUS (WINAPI *ValueFn)(HKEY,LPCWSTR,LPDWORD,LPDWORD,LPBYTE,LPDWORD);
    typedef LSTATUS (WINAPI *InfoFn)(HKEY,LPWSTR,LPDWORD,LPDWORD,LPDWORD,LPDWORD,LPDWORD,
        LPDWORD,LPDWORD,LPDWORD,LPDWORD,PFILETIME);
    typedef LSTATUS (WINAPI *CloseFn)(HKEY);
    HMODULE library=LoadLibraryExW(L"advapi32.dll",NULL,LOAD_LIBRARY_SEARCH_SYSTEM32);
    if(!library)return GetLastError();
    OpenFn open=(OpenFn)(void *)GetProcAddress(library,"RegOpenKeyExW");
    ValueFn value_fn=(ValueFn)(void *)GetProcAddress(library,"RegQueryValueExW");
    InfoFn info=(InfoFn)(void *)GetProcAddress(library,"RegQueryInfoKeyW");
    CloseFn close=(CloseFn)(void *)GetProcAddress(library,"RegCloseKey");
    DWORD error=ERROR_PROC_NOT_FOUND;HKEY key=NULL;
    if(open && value_fn && info && close) {
        error=open(HKEY_CURRENT_USER,L"Software\\Blizzard Entertainment\\Warcraft III",0,KEY_QUERY_VALUE,&key);
        if(error==ERROR_FILE_NOT_FOUND)error=ERROR_SUCCESS;
        else if(!error) {
            DWORD value=0,kind=REG_DWORD,size=sizeof(value);FILETIME changed={0};
            error=value_fn(key,L"Allow Local Files",NULL,&kind,(LPBYTE)&value,&size);
            if(error==ERROR_FILE_NOT_FOUND) {error=ERROR_SUCCESS;kind=REG_DWORD;value=0;size=sizeof(value);}
            if(!error && size!=sizeof(value))error=ERROR_INVALID_DATA;
            if(!error)error=info(key,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,&changed);
            error=war3_quest_override_policy(error,kind,value,
                ((uint64_t)changed.dwHighDateTime<<32)|changed.dwLowDateTime,created);
            close(key);
        }
    }
    FreeLibrary(library);return error;
}
#endif
