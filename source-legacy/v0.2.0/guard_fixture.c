#include "guard32.h"
#include <stdio.h>
__attribute__((noinline)) uint32_t bad(void* a){return *(volatile uint32_t*)a;}
__attribute__((noinline)) uint32_t good(void* a){return (uintptr_t)a+7;}
int main(void){uint32_t fault=0;uint32_t r=guard_call(bad,0,&fault);printf("fault=%08x result=%u\n",fault,r);
 if(fault!=0xc0000005 || r!=0)return 1;
 r=guard_call(good,(void*)8,&fault);printf("fault=%08x result=%u\n",fault,r);return (r==15 && fault==0)?0:2;}
