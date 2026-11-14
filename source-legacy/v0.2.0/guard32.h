/* Isolated x86 SEH frame. The build fixture must pass before use in a game.
 * Do not let an invalid native pointer unwind through the game's window loop.
 */
#include <windows.h>
#include <stdint.h>
typedef struct { uint32_t previous,handler,esp,ebp,ebx,esi,edi,resume; } GuardFrame;
EXCEPTION_DISPOSITION __cdecl guard_handler(EXCEPTION_RECORD* e,void* frame,CONTEXT* c,void* dispatcher) {
    GuardFrame* f=(GuardFrame*)frame;
    if(e->ExceptionCode!=EXCEPTION_ACCESS_VIOLATION && e->ExceptionCode!=EXCEPTION_INT_DIVIDE_BY_ZERO) return ExceptionContinueSearch;
    if(e->ExceptionFlags&EXCEPTION_NONCONTINUABLE)return ExceptionContinueSearch;
    c->Eip=f->resume;c->Esp=f->esp;c->Ebp=f->ebp;c->Ebx=f->ebx;c->Esi=f->esi;c->Edi=f->edi;c->Eax=e->ExceptionCode;
    return ExceptionContinueExecution;
}
__attribute__((naked,noinline)) uint32_t guard_call(uint32_t (__cdecl *fn)(void*),void* arg,uint32_t* fault) {
    __asm__ volatile(
        "pushl %ebp\nmovl %esp,%ebp\npushl %ebx\npushl %esi\npushl %edi\nsubl $32,%esp\n"
        "movl %fs:0,%eax\nmovl %eax,0(%esp)\nmovl $_guard_handler,4(%esp)\n"
        "movl %esp,8(%esp)\nmovl %ebp,12(%esp)\nmovl %ebx,16(%esp)\nmovl %esi,20(%esp)\nmovl %edi,24(%esp)\n"
        "movl $1f,28(%esp)\nmovl %esp,%fs:0\npushl 12(%ebp)\ncall *8(%ebp)\naddl $4,%esp\nxorl %edx,%edx\njmp 2f\n"
        "1: movl %eax,%edx\nxorl %eax,%eax\n"
        "2: movl 0(%esp),%ecx\nmovl %ecx,%fs:0\nmovl 16(%ebp),%ecx\nmovl %edx,(%ecx)\n"
        "addl $32,%esp\npopl %edi\npopl %esi\npopl %ebx\npopl %ebp\nret\n");
}
