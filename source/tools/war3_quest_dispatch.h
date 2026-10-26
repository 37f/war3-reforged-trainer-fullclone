/* R23 transaction coordinator. Only its private, compiled game adapter supplies
   collect/dispatch. Neither function pointer can come from the wire. */
#ifndef WAR3_QUEST_DISPATCH_H
#define WAR3_QUEST_DISPATCH_H
#include "war3_quest_wire.h"
#include "war3_quest_store.h"
typedef struct War3QuestView {
    uint64_t resolved[8],execute_handler;uint32_t flags;
} War3QuestView;
typedef DWORD (*War3QuestCollectFn)(const War3QuestWire *,War3QuestView *,uint32_t *);
typedef DWORD (*War3QuestDispatchFn)(const War3QuestView *);

static void war3_quest_reply_view(uint64_t reply[32],const War3QuestView *view) {
    memcpy(reply+12,view->resolved,64);reply[22]=view->flags;
}
static void war3_quest_reply_record(uint64_t reply[32],const War3QuestRecord *record,int duplicate) {
    reply[23]=record->status;reply[24]=record->error;
    memcpy(reply+27,record->request,16);reply[29]=1u|(duplicate?2u:0u);
    reply[30]=duplicate?6u:record->status==3?13u:record->status==4?14u:9u;
}

static DWORD war3_quest_transaction(const War3QuestWire *wire,uint64_t reply[32],
    War3QuestCollectFn collect,War3QuestDispatchFn dispatch) {
    if(!wire || !wire->header || !reply || !collect || !dispatch)return ERROR_INVALID_PARAMETER;
    const uint64_t *h=wire->header;War3QuestStore store={0};
    War3QuestRecord *record=NULL;War3QuestView view={0};int reserved=0;
    ZeroMemory(reply,32*8u);reply[0]=WAR3_QUEST_MAGIC;reply[1]=1;reply[2]=h[2];reply[3]=h[3];
    memcpy(reply+4,h+10,32);memcpy(reply+25,h+34,16);reply[20]=h[5];reply[21]=h[6];
    reply[23]=1;reply[30]=7;
    DWORD error=war3_quest_store_lock(&store);
    if(error) {reply[24]=error;reply[30]=error==ERROR_BUSY?11u:7u;return ERROR_SUCCESS;}
    War3QuestState *state=store.state;memcpy(reply+8,state->epoch,16);
    if(state->busy) {reply[24]=ERROR_BUSY;reply[30]=11;war3_quest_store_unlock(&store);return ERROR_SUCCESS;}
    state->busy=1;
    __try {
        if(h[2]) {
            War3QuestKey expected={h[3],h[26],h[29],h[28]};
            record=war3_quest_find_request(&state->ledger,h+34);
            if(record && !war3_quest_same_instance(&record->key,&expected)) {
                error=ERROR_INVALID_DATA;reply[30]=10;__leave;
            }
            if(!record)record=war3_quest_find_instance(&state->ledger,&expected);
            if(record) {
                /* Read-only observation, even across a catalog token refresh.
                   Any failure is unknown; the original dispatch stays recorded. */
                uint32_t message=2;
                error=collect(wire,&view,&message);
                if(!error && view.resolved[0]==record->key.vm &&
                   view.resolved[2]==record->key.quest_object && view.resolved[3]==record->key.quest_full) {
                    war3_quest_reply_view(reply,&view);
                    if(view.flags&1u) {record->status=WAR3_QUEST_COMPLETED;record->error=0;}
                } else {record->status=WAR3_QUEST_UNKNOWN;record->error=error?error:ERROR_RETRY;}
                war3_quest_reply_record(reply,record,h[2]==1);error=0;__leave;
            }
            if(h[2]==2) {error=ERROR_NOT_FOUND;reply[30]=7;__leave;}
        }
        if(h[2]==1) {
            if(memcmp(h+22,state->epoch,16)) {error=ERROR_INVALID_DATA;reply[30]=7;__leave;}
            War3QuestStoredProof *proof=NULL;
            for(unsigned n=0;n<WAR3_QUEST_PROOFS;++n)
                if(!memcmp(state->proofs[n].nonce,h+24,16)) {proof=&state->proofs[n];break;}
            if(!proof || proof->consumed || GetTickCount64()-proof->tick>2000u) {
                error=ERROR_TIMEOUT;reply[30]=3;__leave;
            }
            if(memcmp(proof->header,h+3,19u*8u) || memcmp(proof->resolved,h+26,64)) {
                error=ERROR_INVALID_DATA;reply[30]=5;__leave;
            }
        }
        uint32_t message=10;error=collect(wire,&view,&message);
        if(error) {reply[30]=message;__leave;}
        war3_quest_reply_view(reply,&view);
        if(view.flags&3u) {error=ERROR_INVALID_HANDLE;reply[30]=4;__leave;}
        if(h[2]==0) {
            War3QuestStoredProof *proof=&state->proofs[state->next_proof];
            ZeroMemory(proof,sizeof(*proof));error=war3_quest_nonce(proof->nonce);if(error)__leave;
            proof->tick=GetTickCount64();memcpy(proof->header,h+3,31u*8u);
            memcpy(proof->resolved,view.resolved,64);memcpy(reply+10,proof->nonce,16);
            state->next_proof=(state->next_proof+1u)%WAR3_QUEST_PROOFS;reply[23]=0;reply[30]=0;__leave;
        }
        if(memcmp(view.resolved,h+26,64)) {error=ERROR_INVALID_DATA;reply[30]=5;__leave;}
        War3QuestKey key={h[3],view.resolved[0],view.resolved[3],view.resolved[2]};
        int result=war3_quest_reserve(&state->ledger,&key,h+34,h+10,GetTickCount64(),&record);
        if(result!=WAR3_QUEST_RESERVED) {
            error=result==WAR3_QUEST_LEDGER_FULL?ERROR_INSUFFICIENT_BUFFER:ERROR_INVALID_DATA;
            reply[30]=result==WAR3_QUEST_LEDGER_FULL?12u:7u;__leave;
        }
        reserved=1;
        for(unsigned n=0;n<WAR3_QUEST_PROOFS;++n)
            if(!memcmp(state->proofs[n].nonce,h+24,16))state->proofs[n].consumed=1;
        /* This barrier and durable-in-process record precede ANY original flow. */
        MemoryBarrier();error=dispatch(&view);
        if(error) {record->status=WAR3_QUEST_UNKNOWN;record->error=error;}
        else {
            War3QuestView after={0};message=2;error=collect(wire,&after,&message);
            if(error || memcmp(after.resolved,view.resolved,64)) {
                record->status=WAR3_QUEST_UNKNOWN;record->error=error?error:ERROR_RETRY;
            } else {
                war3_quest_reply_view(reply,&after);
                if(after.flags&1u)record->status=WAR3_QUEST_COMPLETED;
            }
        }
        war3_quest_reply_record(reply,record,0);error=0;
    } __except(EXCEPTION_EXECUTE_HANDLER) {
        error=GetExceptionCode();reply[30]=10;
        if(reserved && record) {
            record->status=WAR3_QUEST_UNKNOWN;record->error=error;
            war3_quest_reply_record(reply,record,0);error=0;
        }
    }
    if(error)reply[24]=error;
    MemoryBarrier();state->busy=0;war3_quest_store_unlock(&store);return ERROR_SUCCESS;
}
#endif
