"""Offline verification executed by the packaged trainer, without a game hook."""

import ctypes
import hashlib
import json
from pathlib import Path
import sys
import traceback


def quest_self_check():
    """R22 offline path only: no process discovery, injection or game queries."""
    import time
    from war3_current_map_script import ScriptSnapshot,CurrentMapScriptClient
    from war3_quest_analysis import analyze_quests
    from war3_quest_ui import QuestAnalysisController
    script=b'''globals
quest q=null
integer count=0
endglobals
function main takes nothing returns nothing
set q=CreateQuest()
call QuestSetTitle(q,"Offline quest")
call QuestSetCompleted(q,false)
if count >= 4 then
call QuestSetCompleted(q,true)
endif
call CustomDefeatBJ(Player(0),"Test")
endfunction
'''
    snapshot=ScriptSnapshot('offline',1,'offline-fixture::war3map.j','jass',script,b'',
        hashlib.sha256(script).hexdigest(),hashlib.sha256(b'').hexdigest(),time.monotonic(),('offline-fixture',),())
    def query(*,snapshot=None,cancelled=lambda:False):return fixture if snapshot is None else True
    fixture=snapshot;client=CurrentMapScriptClient(query,lambda:'offline')
    source_ok=client.read()==fixture and client.check(fixture)
    report=analyze_quests(snapshot)
    q=report.quests[0]
    analysis_ok=(q.title=='Offline quest' and len(q.completed)==1 and len(q.resets)==1 and
        'count >= 4' in q.completed[0].paths[0].guard and len(report.outcomes)==1 and report.outcomes[0].kind=='defeat')
    controller=QuestAnalysisController(lambda:None)
    try:
        controller.tick(True)
        idle_ok=controller.report is None and controller.state=='idle' and not controller.started
        controller.detect();controller.tick(True)
        controller_ok=idle_ok and controller.report is None and controller.state=='disconnected' and controller.started
    finally:controller.close()
    return {'quest_source_model_ok':source_ok,'quest_analysis_ok':analysis_ok,'quest_controller_ok':controller_ok}


def quest_text_self_check():
    from war3_current_map_script import ScriptSnapshot
    from war3_quest_analysis import analyze_quests
    from war3_quest_text import QuestText
    script=b"globals\nquest q=null\ninteger count=0\nendglobals\nfunction main takes nothing returns nothing\nset q=CreateQuest()\ncall QuestSetRequired(q,true)\nif count>=4 then\ncall QuestSetCompleted(q,true)\nendif\nendfunction"
    snap=ScriptSnapshot('offline',1,'offline::war3map.j','jass',script,b'',
        hashlib.sha256(script).hexdigest(),hashlib.sha256(b'').hexdigest(),0.,('offline fixture',),())
    report=analyze_quests(snap);text=QuestText(report).quest(report.quests[0])
    return {'quest_readable_text_ok':all(word in text for word in ('主线任务','完成条件','不少于 4','失败条件'))}


def run(output_path):
    report = {"ok": False, "frozen": bool(getattr(sys, "frozen", False))}
    try:
        import capstone

        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        decoder = Path(capstone._cs._name).resolve()
        report["decoder"] = str(decoder)
        report["decoder_sha256"] = hashlib.sha256(decoder.read_bytes()).hexdigest()
        if report["frozen"] and not decoder.is_relative_to(base.resolve()):
            raise RuntimeError("Decoder was loaded from outside the executable bundle")
        # C3 inside a mov instruction is not a return; E8 inside an immediate
        # is not a call. Both caused false instruction boundaries previously.
        code = bytes.fromhex("448bc3b8e8000000e803000000c3")
        decoded = list(capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64).disasm(code, 0x1000))
        if [ins.mnemonic for ins in decoded] != ["mov", "mov", "call", "ret"]:
            raise RuntimeError("Decoder instruction-boundary check failed")
        report["instructions"] = [ins.mnemonic for ins in decoded]
        helper = base / "tools" / "war3_native_helper.dll"
        library = ctypes.WinDLL(str(helper))
        getattr(library, "War3HookProc")
        protocol=library.War3NativeProtocol;protocol.argtypes=[];protocol.restype=ctypes.c_uint32
        report['helper_protocol']=int(protocol())
        if report['helper_protocol']!=80:raise RuntimeError('Packaged helper protocol mismatch')
        report["helper_sha256"] = hashlib.sha256(helper.read_bytes()).hexdigest()
        # R20: also verify offline archive dependency from the frozen bundle.
        from war3_campaign_catalog import _storm_library
        from war3_custom_objects import parse_object_data
        archive_library = _storm_library()
        archive_path = Path(archive_library._name).resolve()
        if report["frozen"] and not archive_path.is_relative_to(base.resolve()):
            raise RuntimeError("Archive library was loaded from outside the executable bundle")
        report["stormlib_sha256"] = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        report["catalog_parser_ok"] = parse_object_data(bytes.fromhex("020000000000000000000000"), "unit") == ()
        if not report["catalog_parser_ok"]:
            raise RuntimeError("Offline object parser check failed")
        from war3_current_map_catalog import parse_catalog_header, MAGIC
        report['current_map_parser_ok']=parse_catalog_header((MAGIC,1,123,64,14,33))==(123,(64,14,33))
        if not report['current_map_parser_ok']:
            raise RuntimeError('Current-map protocol parser check failed')
        report.update(quest_self_check())
        report.update(quest_text_self_check())
        from war3_casc_source import _load_library,CASC_DLL_SHA256
        casc=_load_library();casc_path=Path(casc._name).resolve()
        if report['frozen'] and not casc_path.is_relative_to(base.resolve()):
            raise RuntimeError('CASC library was loaded from outside the executable bundle')
        report['casclib_sha256']=hashlib.sha256(casc_path.read_bytes()).hexdigest()
        if report['casclib_sha256']!=CASC_DLL_SHA256:raise RuntimeError('CASC dependency mismatch')
        if not all(report[name] for name in ('quest_source_model_ok','quest_analysis_ok','quest_controller_ok')):
            raise RuntimeError('Offline quest model/analysis/controller check failed')
        if not report['quest_readable_text_ok']:raise RuntimeError('Offline readable quest explanation failed')
        report["ok"] = True
    except Exception:
        report["error"] = traceback.format_exc()
    Path(output_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
