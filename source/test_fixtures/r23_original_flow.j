// Private runtime fixture v2. No campaign cache, save, victory or level change.
globals
    quest udg_R23SyncQuest = null
    quest udg_R23DelayQuest = null
    trigger gg_trg_R23Sync = null
    trigger gg_trg_R23Delay = null
    trigger gg_trg_R23Followup = null
    unit udg_R23Hero = null
    integer udg_R23SyncCount = 0
    integer udg_R23DelayCount = 0
endglobals

function R23Followup takes nothing returns nothing
    local unit recruit = CreateUnit(Player(0), 'hfoo', GetUnitX(udg_R23Hero)+160.0, GetUnitY(udg_R23Hero), 270.0)
    set udg_R23SyncCount = udg_R23SyncCount + 1
    call DisplayTimedTextToPlayer(Player(0),0.0,0.0,20.0,"R23：同步原流程后续已执行，新增一名步兵。")
    set recruit = null
endfunction

function R23CompleteSync takes nothing returns nothing
    local item reward = UnitAddItemById(udg_R23Hero, 'ratf')
    call SetPlayerState(Player(0),PLAYER_STATE_RESOURCE_GOLD,GetPlayerState(Player(0),PLAYER_STATE_RESOURCE_GOLD)+100)
    call TriggerExecute(gg_trg_R23Followup)
    call QuestSetCompleted(udg_R23SyncQuest,true)
    set reward = null
endfunction

function R23CompleteDelay takes nothing returns nothing
    call SetPlayerState(Player(0),PLAYER_STATE_RESOURCE_GOLD,GetPlayerState(Player(0),PLAYER_STATE_RESOURCE_GOLD)+50)
    call DisplayTimedTextToPlayer(Player(0),0.0,0.0,20.0,"R23：延迟原流程已开始，等待2秒。")
    call TriggerSleepAction(2.0)
    set udg_R23DelayCount = udg_R23DelayCount + 1
    call QuestSetCompleted(udg_R23DelayQuest,true)
    call DisplayTimedTextToPlayer(Player(0),0.0,0.0,20.0,"R23：延迟后续完成。")
endfunction

function R23CreateQuests takes nothing returns nothing
    set udg_R23SyncQuest = CreateQuest()
    call QuestSetTitle(udg_R23SyncQuest,"R23 同步奖励测试")
    call QuestSetDescription(udg_R23SyncQuest,"原流程：增加100金币，给予圣骑士一个ratf物品，调用原后续触发器创建一名步兵。")
    call QuestSetRequired(udg_R23SyncQuest,true)
    call QuestSetDiscovered(udg_R23SyncQuest,true)
    set udg_R23DelayQuest = CreateQuest()
    call QuestSetTitle(udg_R23DelayQuest,"R23 延迟后续测试")
    call QuestSetDescription(udg_R23DelayQuest,"原流程：先增加50金币，再等待2秒，由原脚本标记任务完成并显示后续文字。")
    call QuestSetRequired(udg_R23DelayQuest,true)
    call QuestSetDiscovered(udg_R23DelayQuest,true)
endfunction

function R23InitTriggers takes nothing returns nothing
    set gg_trg_R23Followup = CreateTrigger()
    call TriggerAddAction(gg_trg_R23Followup,function R23Followup)
    set gg_trg_R23Sync = CreateTrigger()
    call TriggerRegisterPlayerChatEvent(gg_trg_R23Sync,Player(0),"__R23_NATIVE_SYNC_TEST__",true)
    call TriggerAddAction(gg_trg_R23Sync,function R23CompleteSync)
    set gg_trg_R23Delay = CreateTrigger()
    call TriggerRegisterPlayerChatEvent(gg_trg_R23Delay,Player(0),"__R23_NATIVE_DELAY_TEST__",true)
    call TriggerAddAction(gg_trg_R23Delay,function R23CompleteDelay)
endfunction

function config takes nothing returns nothing
    local integer i = 1
    call SetMapName("R23 原任务流程验证 v2")
    call SetMapDescription("独立测试地图：同步奖励与2秒延迟后续。不会操作战役进度或存档。")
    call SetPlayers(1)
    call SetTeams(1)
    call SetGameTypeSupported(GAME_TYPE_USE_MAP_SETTINGS,true)
    call SetGamePlacement(MAP_PLACEMENT_USE_MAP_SETTINGS)
    call DefineStartLocation(0,-3859.1,2748.8)
    call SetPlayerStartLocation(Player(0),0)
    call SetPlayerTeam(Player(0),0)
    call SetPlayerController(Player(0),MAP_CONTROL_USER)
    call SetPlayerRacePreference(Player(0),RACE_PREF_HUMAN)
    call SetPlayerRaceSelectable(Player(0),false)
    loop
        exitwhen i >= 24
        call SetPlayerController(Player(i),MAP_CONTROL_NONE)
        set i = i + 1
    endloop
endfunction

function main takes nothing returns nothing
    call InitBlizzard()
    call FogEnable(false)
    call FogMaskEnable(false)
    set udg_R23Hero = CreateUnit(Player(0),'Hpal',-3859.1,2748.8,270.0)
    call SetPlayerState(Player(0),PLAYER_STATE_RESOURCE_GOLD,500)
    call SetPlayerState(Player(0),PLAYER_STATE_RESOURCE_LUMBER,200)
    call SetPlayerState(Player(0),PLAYER_STATE_RESOURCE_FOOD_CAP,99)
    call R23CreateQuests()
    call R23InitTriggers()
    call PanCameraToTimed(-3859.1,2748.8,0.0)
    call SelectUnit(udg_R23Hero,true)
    call DisplayTimedTextToPlayer(Player(0),0.0,0.0,60.0,"R23 v2独立测试：初始500金币、一名圣骑士。请等待修改器检查，不会自动执行任务。")
endfunction
