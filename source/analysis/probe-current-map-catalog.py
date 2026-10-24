"""Read definitions through the matched persistent helper; no gameplay actions."""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from war3_reforged_trainer import War3Trainer

class CatalogProbeTrainer(War3Trainer):
    def _start_persistent_bootstrap(self):
        # Isolate this read-only query; do not run unrelated selection polling.
        pass

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--pid',type=int,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--watch-seconds',type=int,default=0)
parser.add_argument('--dll',type=Path)
args=parser.parse_args()
if args.dll:
    CatalogProbeTrainer._native_helper_dll_path=lambda self:args.dll.resolve()
trainer=None
try:
    trainer=CatalogProbeTrainer(args.pid)
    client=trainer.current_map_catalog_client()
    snapshots=[]
    if args.watch_seconds:
        events=[];last=None;deadline=time.monotonic()+args.watch_seconds
        while time.monotonic()<deadline:
            try:
                header=tuple(client.query(318))
                status=('ready',header[2],header[3:])
            except Exception as exc:
                status=('unavailable',str(exc))
            if status!=last:
                last=status;events.append({'time':time.time(),'state':status})
                print(events[-1],flush=True)
                args.output.parent.mkdir(parents=True,exist_ok=True)
                args.output.write_text(json.dumps({'pid':args.pid,'protocol':trainer.NATIVE_HELPER_VERSION,'events':events},ensure_ascii=False,indent=2),encoding='utf8')
            time.sleep(1)
        raise SystemExit(0)
    for _ in range(3):
        snapshot=client.read()
        snapshots.append(asdict(snapshot))
        print('counts',snapshot.counts,'ms',round(snapshot.elapsed_ms,2),'checked',client.check(snapshot),'issues',len(snapshot.result.issues),flush=True)
        time.sleep(0.2)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps({'pid':args.pid,'protocol':trainer.NATIVE_HELPER_VERSION,'snapshots':snapshots},ensure_ascii=False,indent=2),encoding='utf8')
except Exception:
    if trainer:
        import struct
        data=trainer._read_native_helper_command(trainer._native_helper_command_path())
        if data: print('command diagnostic',trainer.NATIVE_HELPER_OP_STRUCT.unpack_from(data,32),flush=True)
    raise
finally:
    if trainer: trainer.close()
