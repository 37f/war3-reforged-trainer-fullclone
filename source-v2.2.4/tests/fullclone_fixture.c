/* Local executable fixture: no game process is opened. */
#include "../tools/war3_bridge_24268.c"
__declspec(dllexport) uint64_t FCFixtureRun(void *payload,uint32_t kind){
    BridgeCommand command={0};command.work=payload;
    if(kind==1)command.tls_value=((FullCloneWork*)payload)->tls;
    else if(kind==2)command.tls_value=((FCItemsWork*)payload)->tls;
    else if(kind==3)command.tls_value=((FCQuestStatusWork*)payload)->tls;
    else return 0;
    g_dispatch=&command;
    uint64_t result=kind==1?BridgeFullCloneQuery():kind==2?BridgeFullCloneItemsQuery():BridgeFullCloneStatusQuery();
    g_dispatch=0;return result;
}
__declspec(dllexport) void FCFixtureRegistryRootZero(void){bridge_profile.registry_root_rva=0;}
static int32_t *fc_test_level;static uint32_t fc_test_write_before_fault;
__declspec(dllexport) void FCFixtureFaultLevelConfig(int32_t *level,uint32_t write_first){fc_test_level=level;fc_test_write_before_fault=write_first;}
__declspec(dllexport) void FCFixtureFaultLevel(uint64_t unit,int32_t level,uint32_t eye){
    (void)unit;(void)eye;
    if(fc_test_write_before_fault)*fc_test_level=level;
    RaiseException(0xe0310001,0,0,0);
}
static uint32_t *fc_test_alliance;static uint32_t fc_test_alliance_write,fc_test_alliance_fault;
__declspec(dllexport) void FCFixtureFaultAllianceConfig(uint32_t *flag,uint32_t write_first,uint32_t fault){
    fc_test_alliance=flag;fc_test_alliance_write=write_first;fc_test_alliance_fault=fault;
}
__declspec(dllexport) void FCFixtureFaultAlliance(uint64_t a,uint64_t b,uint64_t kind,uint32_t value){
    (void)a;(void)b;(void)kind;
    if(fc_test_alliance_write)*fc_test_alliance=value;
    RaiseException(fc_test_alliance_fault,0,0,0);
}
