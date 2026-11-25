from war3_fullclone_ai_stock import FACTIONS, project_opening, project_wave


COMMON = """
    constant integer PEON = 'opeo'
    constant integer ALTAR = 'oalt'
    constant integer BURROW = 'otrb'
    constant integer FACTORY = 'obar'
    constant integer BARRACKS = FACTORY
    constant integer STRONGHOLD = 'ostr'
"""

SCRIPT = """
function build_sequence takes nothing returns nothing
    call InitBuildArray()
    if basic_opening then
        call SetBuildUnit(6, PEON)
        call SetBuildUnit(1, ALTAR)
        if variable then
            call SetBuildUnit(24, PEON)
            call SetBuildUnit(1, BARRACKS)
        endif
        call SetBuildNext(7, PEON)
        call SetBuildUnit(1, BURROW)
        call SetBuildNext(8, PEON)
        call SetBuildUnit(2, BURROW)
        call SetBuildUnit(11, PEON)
        call SetBuildUnit(1, BARRACKS) // recognized alias
        call SetBuildNext(14, PEON)
        call SetBuildUnit(1, STRONGHOLD)
        call SetBuildUnit(23, PEON)
    endif
    call SetBuildUnit(24, PEON)
endfunction
"""


def test_literal_stock_opening_keeps_order_and_ignores_dynamic_branches():
    assert project_opening(COMMON, SCRIPT, FACTIONS[1]) == (
        14, ((4, 1, 6), (1, 1, 7), (1, 2, 8), (2, 1, 11)))


def test_unknown_or_out_of_range_stock_targets_keep_static_fallback():
    assert project_opening(COMMON, SCRIPT.replace('1, ALTAR', '1, unavailable'), FACTIONS[1]) is None
    assert project_opening(COMMON, SCRIPT.replace('14, PEON', '99, PEON'), FACTIONS[1]) is None


def test_first_attack_wave_uses_only_literal_troops_in_attack_sequence():
    script = """
function build_sequence takes nothing returns nothing
    exitwhen c_grunt_done >= 10
endfunction
function attack_sequence takes nothing returns nothing
    exitwhen common_ready and c_grunt_done >= 2 // first wave
    exitwhen c_grunt_done >= 4
endfunction
"""
    assert project_wave(script, 'c_grunt_done') == 2
    assert project_wave(script, 'c_archer_done') == 0
    assert project_wave(script.replace('>= 2', '>= 20+extra').replace('>= 4', '>= extra'), 'c_grunt_done') == 0
