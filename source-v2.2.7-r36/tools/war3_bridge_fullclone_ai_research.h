/* Stock research menus from the installed four faction UnitFunc tables.
   A normal order delegates costs, building state and prerequisites to the game. */
typedef struct FCAIResearch {uint32_t code;int32_t levels;} FCAIResearch;
typedef struct FCAIResearchBuilding {uint32_t code;FCAIResearch tech[6];} FCAIResearchBuilding;

static int FCAIResearchOrder(FCLocalAIWork *w,uint64_t unit) {
    static const FCAIResearchBuilding buildings[]={
        /* Blacksmith (hbla) */
        {FC_AI_CODE('h','b','l','a'), {
            {FC_AI_CODE('R','h','m','e'),3},
            {FC_AI_CODE('R','h','a','r'),3},
            {FC_AI_CODE('R','h','r','a'),3},
            {FC_AI_CODE('R','h','l','a'),3},
        }},
        /* Lumber Mill (hlum) */
        {FC_AI_CODE('h','l','u','m'), {
            {FC_AI_CODE('R','h','l','h'),2},
            {FC_AI_CODE('R','h','a','c'),3},
        }},
        /* Human Barracks (hbar) */
        {FC_AI_CODE('h','b','a','r'), {
            {FC_AI_CODE('R','h','d','e'),1},
            {FC_AI_CODE('R','h','r','i'),1},
            {FC_AI_CODE('R','h','a','n'),1},
            {FC_AI_CODE('R','h','s','b'),1},
        }},
        /* War Mill (ofor) */
        {FC_AI_CODE('o','f','o','r'), {
            {FC_AI_CODE('R','o','m','e'),3},
            {FC_AI_CODE('R','o','a','r'),3},
            {FC_AI_CODE('R','o','r','a'),3},
            {FC_AI_CODE('R','o','s','p'),2},
            {FC_AI_CODE('R','o','r','b'),1},
        }},
        /* Orc Barracks (obar) */
        {FC_AI_CODE('o','b','a','r'), {
            {FC_AI_CODE('R','o','b','s'),1},
            {FC_AI_CODE('R','o','t','r'),1},
            {FC_AI_CODE('R','o','b','k'),1},
            {FC_AI_CODE('R','o','b','f'),1},
        }},
        /* Beastiary (obea) */
        {FC_AI_CODE('o','b','e','a'), {
            {FC_AI_CODE('R','o','e','n'),1},
            {FC_AI_CODE('R','o','v','s'),1},
            {FC_AI_CODE('R','w','d','m'),1},
            {FC_AI_CODE('R','o','l','f'),1},
        }},
        /* Graveyard (ugrv) */
        {FC_AI_CODE('u','g','r','v'), {
            {FC_AI_CODE('R','u','m','e'),3},
            {FC_AI_CODE('R','u','a','r'),3},
            {FC_AI_CODE('R','u','r','a'),3},
            {FC_AI_CODE('R','u','c','r'),3},
        }},
        /* Crypt (usep) */
        {FC_AI_CODE('u','s','e','p'), {
            {FC_AI_CODE('R','u','w','b'),1},
            {FC_AI_CODE('R','u','g','f'),1},
            {FC_AI_CODE('R','u','s','f'),1},
            {FC_AI_CODE('R','u','b','u'),1},
            {FC_AI_CODE('R','u','a','c'),1},
        }},
        /* Temple of the Damned (utod) */
        {FC_AI_CODE('u','t','o','d'), {
            {FC_AI_CODE('R','u','n','e'),2},
            {FC_AI_CODE('R','u','b','a'),2},
            {FC_AI_CODE('R','u','s','m'),1},
        }},
        /* Hunter's Hall (edob) */
        {FC_AI_CODE('e','d','o','b'), {
            {FC_AI_CODE('R','e','s','m'),3},
            {FC_AI_CODE('R','e','m','a'),3},
            {FC_AI_CODE('R','e','s','w'),3},
            {FC_AI_CODE('R','e','r','h'),3},
            {FC_AI_CODE('R','e','u','v'),1},
            {FC_AI_CODE('R','e','w','s'),1},
        }},
        /* Ancient of War (eaom) */
        {FC_AI_CODE('e','a','o','m'), {
            {FC_AI_CODE('R','e','i','b'),1},
            {FC_AI_CODE('R','e','m','k'),1},
            {FC_AI_CODE('R','e','s','c'),1},
            {FC_AI_CODE('R','e','m','g'),1},
            {FC_AI_CODE('R','e','p','b'),1},
        }},
        /* Ancient of Lore (eaoe) */
        {FC_AI_CODE('e','a','o','e'), {
            {FC_AI_CODE('R','e','s','i'),1},
            {FC_AI_CODE('R','e','d','c'),2},
            {FC_AI_CODE('R','e','r','s'),1},
            {FC_AI_CODE('R','e','h','s'),1},
            {FC_AI_CODE('R','e','e','b'),1},
        }},
        /* Ancient of Wind (eaow) */
        {FC_AI_CODE('e','a','o','w'), {
            {FC_AI_CODE('R','e','d','t'),2},
            {FC_AI_CODE('R','e','e','c'),1},
        }},
    };
    uint32_t kind=w->selection.unit_type_id(unit);
    for(uint32_t i=0;i<sizeof(buildings)/sizeof(buildings[0]);++i){
        if(kind!=buildings[i].code)continue;
        w->status|=FC_AI_RESEARCH_BUILDING;
        if(!w->allow_research || w->researched || !FCLocalAICanOrder(w,unit,0))return 0;
        for(uint32_t j=0;j<6 && buildings[i].tech[j].code;++j){
            FCAIResearch research=buildings[i].tech[j];
            int32_t allowed=w->tech_max(w->owner,research.code);
            int32_t level=w->tech_count(w->owner,research.code,1);
            if(allowed==0 || allowed< -1 || level<0 || level>=research.levels ||
               (allowed>0 && level>=allowed))continue;
            if(!FCLocalAICanOrder(w,unit,0))return 0;
            if(w->immediate(unit,research.code)){w->researched=1;return 1;}
        }
        return 0;
    }
    return 0;
}
