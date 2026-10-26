/* R23 bounded at-most-once state. The game-side caller owns serialization and
   persistent storage; reserve MUST finish before starting the original flow. */
#ifndef WAR3_QUEST_LEDGER_H
#define WAR3_QUEST_LEDGER_H
#include <stdint.h>
#include <string.h>

#define WAR3_QUEST_LEDGER_CAPACITY 128u
#define WAR3_QUEST_DISPATCHED 2u
#define WAR3_QUEST_COMPLETED 3u
#define WAR3_QUEST_UNKNOWN 4u
#define WAR3_QUEST_RESERVED 0u
#define WAR3_QUEST_DUPLICATE 1u
#define WAR3_QUEST_REQUEST_CONFLICT 2u
#define WAR3_QUEST_LEDGER_FULL 3u
#define WAR3_QUEST_LEDGER_INVALID 4u

typedef struct War3QuestKey {
    uint64_t token,vm,quest_full,quest_object;
} War3QuestKey;

typedef struct War3QuestRecord {
    War3QuestKey key;
    uint64_t request[2],plan[4],dispatch_tick;
    uint32_t status,error;
} War3QuestRecord;

typedef struct War3QuestLedger {
    uint32_t count,reserved;
    War3QuestRecord records[WAR3_QUEST_LEDGER_CAPACITY];
} War3QuestLedger;

static inline int war3_quest_same_instance(const War3QuestKey *a,const War3QuestKey *b) {
    /* Catalog errors/revalidation can retire a token without destroying the
       live quest. Its concrete VM/object generation remains non-repeatable. */
    return a->vm==b->vm && a->quest_full==b->quest_full && a->quest_object==b->quest_object;
}

static inline War3QuestRecord *war3_quest_find_request(War3QuestLedger *ledger,const uint64_t request[2]) {
    if(!ledger || ledger->count>WAR3_QUEST_LEDGER_CAPACITY || !request) return 0;
    for(uint32_t n=0;n<ledger->count;++n)
        if(!memcmp(ledger->records[n].request,request,16)) return &ledger->records[n];
    return 0;
}

static inline War3QuestRecord *war3_quest_find_instance(War3QuestLedger *ledger,const War3QuestKey *key) {
    if(!ledger || ledger->count>WAR3_QUEST_LEDGER_CAPACITY || !key) return 0;
    for(uint32_t n=0;n<ledger->count;++n)
        if(war3_quest_same_instance(&ledger->records[n].key,key)) return &ledger->records[n];
    return 0;
}

static inline int war3_quest_reserve(War3QuestLedger *ledger,const War3QuestKey *key,
    const uint64_t request[2],const uint64_t plan[4],uint64_t tick,War3QuestRecord **out) {
    War3QuestRecord *record;
    if(!out) return WAR3_QUEST_LEDGER_INVALID;
    *out=0;
    if(!ledger || !key || !request || !plan || !key->token || !key->vm || !key->quest_full ||
       !key->quest_object || !(request[0]|request[1]) || !(plan[0]|plan[1]|plan[2]|plan[3]) ||
       ledger->reserved || ledger->count>WAR3_QUEST_LEDGER_CAPACITY) return WAR3_QUEST_LEDGER_INVALID;
    for(uint32_t n=0;n<ledger->count;++n) {
        record=&ledger->records[n];
        if(!record->key.vm || !record->key.quest_full || !record->key.quest_object ||
           !(record->request[0]|record->request[1]) || record->status<WAR3_QUEST_DISPATCHED ||
           record->status>WAR3_QUEST_UNKNOWN) return WAR3_QUEST_LEDGER_INVALID;
    }
    record=war3_quest_find_request(ledger,request);
    if(record) {
        if(!war3_quest_same_instance(&record->key,key)) return WAR3_QUEST_REQUEST_CONFLICT;
        *out=record;return WAR3_QUEST_DUPLICATE;
    }
    record=war3_quest_find_instance(ledger,key);
    if(record) {*out=record;return WAR3_QUEST_DUPLICATE;}
    /* No eviction: a full ledger must not make old rewards repeatable. */
    if(ledger->count==WAR3_QUEST_LEDGER_CAPACITY) return WAR3_QUEST_LEDGER_FULL;
    record=&ledger->records[ledger->count];memset(record,0,sizeof(*record));
    record->key=*key;memcpy(record->request,request,16);memcpy(record->plan,plan,32);
    record->dispatch_tick=tick;record->status=WAR3_QUEST_DISPATCHED;
    ++ledger->count;*out=record;
    return WAR3_QUEST_RESERVED;
}
#endif
