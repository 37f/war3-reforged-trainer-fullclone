/* Compiled ONLY into a separate test-native DLL. Not present in shipped helper.
 * Authorized test-map driver uses tracked created handles, never arbitrary scan. */
static int legacy_test_setup(Packet* p,NativeFns* n){
    if(p->world!=p->expected_world || !p->target || n->GetUnitTypeId(p->target)!=(uint32_t)p->b)return 105;
    uint32_t u=p->target;
    if(p->kind==3){
        for(int i=0;i<6;i++){uint32_t h=n->UnitItemInSlot(u,i);if(h)n->RemoveItem(h);}
        n->RemoveUnit(u);p->applied=1;return legacy_collect(p,n);
    }
    if(p->kind==1 || p->kind==2){
        for(unsigned i=0;i<p->unit_count;i++)n->SelectUnit(p->units[i].handle,0);
        n->SelectUnit(u,1);
    }
    if(p->kind==4)n->SelectUnit(u,1);
    if(p->kind==2){
        n->PauseUnit(u,0);n->SuspendHeroXP(u,0);int level=n->GetHeroLevel(u);if(level>1)n->UnitStripHeroLevel(u,level-1);n->SetHeroXP(u,1100,0);n->SetHeroLevel(u,4,0);
        n->SetHeroStr(u,30,1);n->SetHeroAgi(u,40,1);n->SetHeroInt(u,50,1);
        n->UnitAddAbility(u,0x41456572);n->SetUnitAbilityLevel(u,0x41456572,2);
        n->UnitModifySkillPoints(u,1-n->GetHeroSkillPoints(u));n->SuspendHeroXP(u,1);
        float x=real(n->GetUnitX(u)),y=real(n->GetUnitY(u));
        uint32_t h=n->CreateItem(0x72617466,&x,&y);if(!h)return 124;
        n->SetItemCharges(h,7);float item_life=25;n->SetWidgetLife(h,&item_life);n->SetItemInvulnerable(h,1);n->SetItemPawnable(h,0);
        if(!n->UnitAddItem(u,h) || !n->UnitDropItemSlot(u,h,2))return 124;
        n->BlzSetUnitMaxHP(u,1234);n->BlzSetUnitMaxMana(u,456);
        float life=700,mana=123;n->SetUnitState(u,0,&life);n->SetUnitState(u,2,&mana);n->PauseUnit(u,1);p->applied=1;
    }
    return legacy_collect(p,n);
}
