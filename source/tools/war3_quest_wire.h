/* R23 task-only bounded wire. Names reference validated ASCII in input storage;
   no caller-provided value is ever a callable address. */
#ifndef WAR3_QUEST_WIRE_H
#define WAR3_QUEST_WIRE_H
#include <stdint.h>
#include <string.h>
#define WAR3_QUEST_MAGIC 0x31515352u
#define WAR3_QUEST_MAX_WORDS 8192u
#define WAR3_QUEST_MAX_BINDINGS 32u
#define WAR3_QUEST_MAX_ACTIONS 16u
#define WAR3_QUEST_MAX_FUNCTIONS 256u
typedef struct War3QuestName {const char *text;uint32_t length;} War3QuestName;
typedef struct War3QuestBinding {
    War3QuestName trigger,actions[WAR3_QUEST_MAX_ACTIONS];uint32_t count;
} War3QuestBinding;
typedef struct War3QuestWire {
    const uint64_t *header;
    War3QuestName quest,entry_trigger,entry_function;
    uint32_t binding_count,function_count;
    War3QuestBinding bindings[WAR3_QUEST_MAX_BINDINGS];
    War3QuestName functions[WAR3_QUEST_MAX_FUNCTIONS];
} War3QuestWire;

static inline int war3_quest_name_equal(War3QuestName a,War3QuestName b) {
    return a.length==b.length && !memcmp(a.text,b.text,a.length);
}

static inline int war3_quest_wire_name(const uint64_t *words,uint32_t count,uint32_t *at,War3QuestName *out) {
    if(*at>=count)return 0;
    uint64_t length=words[(*at)++];
    if(!length || length>127u)return 0;
    uint32_t span=((uint32_t)length+7u)/8u;
    if(span>count-*at)return 0;
    const char *text=(const char *)(words+*at);
    for(uint32_t n=0;n<span*8u;++n) {
        unsigned char c=(unsigned char)text[n];
        if(n>=length) {if(c)return 0;continue;}
        if(!((c>='A' && c<='Z') || (c>='a' && c<='z') || c=='_' ||
             (n && c>='0' && c<='9')))return 0;
    }
    out->text=text;out->length=(uint32_t)length;*at+=span;return 1;
}

static inline int war3_quest_wire_parse(const uint64_t *words,uint32_t count,War3QuestWire *out) {
    if(!words || !out || count<36u || count>WAR3_QUEST_MAX_WORDS ||
       words[0]!=WAR3_QUEST_MAGIC || words[1]!=1 || words[2]>2 || !words[3] ||
       !words[4] || words[5]>UINT32_MAX || !words[6] || !words[7] || !words[9] ||
       words[8]>words[9] || !(words[10]|words[11]|words[12]|words[13]) ||
       !(words[14]|words[15]|words[16]|words[17]) ||
       !(words[18]|words[19]|words[20]|words[21]))return 0;
    if(!words[2]) {for(unsigned n=22;n<36;++n)if(words[n])return 0;}
    else if(!(words[22]|words[23]) || !(words[24]|words[25]) || !words[26] ||
            !words[27] || words[27]>UINT32_MAX || !words[28] || !words[29] ||
            !words[30] || words[30]>UINT32_MAX || !words[31] || !words[32] || !words[33] ||
            !(words[34]|words[35]))return 0;
    memset(out,0,sizeof(*out));out->header=words;uint32_t at=36,entry_count=0;
    if(!war3_quest_wire_name(words,count,&at,&out->quest) ||
       !war3_quest_wire_name(words,count,&at,&out->entry_trigger) ||
       !war3_quest_wire_name(words,count,&at,&out->entry_function) || at>=count)return 0;
    uint64_t bindings=words[at++];
    if(!bindings || bindings>WAR3_QUEST_MAX_BINDINGS)return 0;
    out->binding_count=(uint32_t)bindings;
    for(uint32_t n=0;n<out->binding_count;++n) {
        War3QuestBinding *binding=&out->bindings[n];
        if(!war3_quest_wire_name(words,count,&at,&binding->trigger) || at>=count)return 0;
        for(uint32_t k=0;k<n;++k)
            if(war3_quest_name_equal(out->bindings[k].trigger,binding->trigger))return 0;
        uint64_t actions=words[at++];if(!actions || actions>WAR3_QUEST_MAX_ACTIONS)return 0;
        binding->count=(uint32_t)actions;
        for(uint32_t k=0;k<binding->count;++k)
            if(!war3_quest_wire_name(words,count,&at,&binding->actions[k]))return 0;
        if(war3_quest_name_equal(binding->trigger,out->entry_trigger)) {
            if(binding->count!=1 || !war3_quest_name_equal(binding->actions[0],out->entry_function))return 0;
            ++entry_count;
        }
    }
    if(entry_count!=1 || at>=count)return 0;
    uint64_t functions=words[at++];if(!functions || functions>WAR3_QUEST_MAX_FUNCTIONS)return 0;
    out->function_count=(uint32_t)functions;entry_count=0;
    for(uint32_t n=0;n<out->function_count;++n) {
        if(!war3_quest_wire_name(words,count,&at,&out->functions[n]))return 0;
        for(uint32_t k=0;k<n;++k)
            if(war3_quest_name_equal(out->functions[k],out->functions[n]))return 0;
        if(war3_quest_name_equal(out->functions[n],out->entry_function))++entry_count;
    }
    return at==count && entry_count==1;
}
#endif
