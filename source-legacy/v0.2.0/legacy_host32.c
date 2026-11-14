/* An explicit x86 host installs only a thread-specific message hook in the
 * verified target. Closing the controller removes the hook; no file patches.
 */
#include <windows.h>
#include <tlhelp32.h>
#include <stdio.h>
#include <stdint.h>
#include <wchar.h>
#include "legacy_protocol.h"
#include "profile_native.h"
int wmain(int argc,wchar_t** argv){
    if(argc==2 && !wcscmp(argv[1],L"--schema")){printf("{\"packet_bytes\":%u,\"unit_bytes\":%u,\"player_bytes\":%u}\n",(unsigned)sizeof(Packet),(unsigned)sizeof(UnitRow),(unsigned)sizeof(PlayerRow));return 0;}
    if(argc!=3)return 2;
    DWORD pid=wcstoul(argv[1],0,10),window_pid=0;HWND window=(HWND)(uintptr_t)wcstoul(argv[2],0,10);
    DWORD tid=GetWindowThreadProcessId(window,&window_pid);if(!tid || window_pid!=pid)return 3;
    wchar_t mutex_name[128];swprintf(mutex_name,128,L"Local\\War3Legacy129-Owner-%lu",pid);
    HANDLE mutex=CreateMutexW(NULL,FALSE,mutex_name);if(!mutex || GetLastError()==ERROR_ALREADY_EXISTS)return 4;
    HANDLE modules=CreateToolhelp32Snapshot(TH32CS_SNAPMODULE,pid);MODULEENTRY32W module={0};module.dwSize=sizeof(module);
    if(modules==INVALID_HANDLE_VALUE || !Module32FirstW(modules,&module))return 5;
    CloseHandle(modules);HANDLE process=OpenProcess(PROCESS_VM_READ|PROCESS_QUERY_LIMITED_INFORMATION,FALSE,pid);if(!process)return 6;
    IMAGE_DOS_HEADER dos;IMAGE_NT_HEADERS32 pe;SIZE_T got=0;
    if(!ReadProcessMemory(process,module.modBaseAddr,&dos,sizeof(dos),&got) || dos.e_magic!=IMAGE_DOS_SIGNATURE || !ReadProcessMemory(process,module.modBaseAddr+dos.e_lfanew,&pe,sizeof(pe),&got))return 7;
    CloseHandle(process);
    if(pe.FileHeader.Machine!=IMAGE_FILE_MACHINE_I386 || pe.FileHeader.TimeDateStamp!=PROFILE_TIMESTAMP || pe.OptionalHeader.SizeOfImage!=PROFILE_SIZE)return 8;
    wchar_t library[MAX_PATH];if(!GetModuleFileNameW(NULL,library,MAX_PATH))return 9;
    wchar_t* end=wcsrchr(library,L'\\');if(!end)return 9;wcscpy(end+1,L"legacy_bridge32_v2.dll");
    HMODULE dll=LoadLibraryW(library);if(!dll)return 10;
    HOOKPROC proc=(HOOKPROC)GetProcAddress(dll,"LegacyHook");if(!proc)return 11;
    HHOOK hook=SetWindowsHookExW(WH_GETMESSAGE,proc,dll,tid);if(!hook){fprintf(stderr,"HOOK_ERROR %lu\n",GetLastError());return 12;}
    printf("READY %lu\n",tid);fflush(stdout);
    char byte;DWORD count;while(ReadFile(GetStdHandle(STD_INPUT_HANDLE),&byte,1,&count,NULL) && count){if(byte=='Q')break;}
    UnhookWindowsHookEx(hook);FreeLibrary(dll);CloseHandle(mutex);return 0;
}
