"""Operator-invoked read-only R22 source/condition evidence; never changes maps.

Use an already running supported game. Close other trainer instances first.
This uses the normal connection and query provider, not discovery addresses.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from war3_reforged_trainer import War3Trainer
from war3_quest_analysis import analyze_quests


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pid',type=int,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();trainer=None;started=time.monotonic()
    try:
        trainer=War3Trainer(args.pid);client=trainer.current_map_script_client()
        snapshot=client.read();report=analyze_quests(snapshot)
        valid=client.check(snapshot)
        evidence={'pid':args.pid,'protocol':trainer.NATIVE_HELPER_VERSION,'check':valid,
            'origin':snapshot.origin,'token':snapshot.session_token,'script_sha256':snapshot.script_sha256,
            'strings_sha256':snapshot.strings_sha256,'provenance':snapshot.provenance,
            'seconds':time.monotonic()-started,'partial':report.partial,'functions':report.functions,
            'quests':[asdict(q) for q in report.quests],'outcomes':[asdict(o) for o in report.outcomes],
            'unassociated':[asdict(o) for o in report.unassociated],'issues':report.issues}
        args.output.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'check':valid,'origin':snapshot.origin,'quests':len(report.quests),
            'outcomes':len(report.outcomes),'partial':report.partial},ensure_ascii=False))
        return 0 if valid else 1
    finally:
        if trainer is not None:trainer.close()


if __name__=='__main__':raise SystemExit(main())
