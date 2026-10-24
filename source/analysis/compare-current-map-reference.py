"""Compare retained runtime results with explicitly selected read-only chapter files."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from war3_campaign_catalog import list_campaign,detect_campaign

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--campaign',type=Path,required=True)
parser.add_argument('--chapter',required=True)
parser.add_argument('--snapshot',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
before=args.campaign.stat().st_mtime_ns
info=list_campaign(args.campaign);chapter=next(c for c in info.chapters if c.path.lower()==args.chapter.lower())
reference=detect_campaign(info,chapter)
live=json.loads(args.snapshot.read_text(encoding='utf8'))
report={'chapter':asdict(chapter),'source_sha256':info.sha256,'snapshots':[]}
for snapshot in live['snapshots']:
    result={}
    for kind in ('unit','item','ability'):
        expected={r.rawcode:asdict(r) for r in reference.entries[kind]}
        found={r['rawcode']:r for r in snapshot['result']['entries'][kind]}
        mismatches=[]
        for code in expected.keys()&found.keys():
            fields=[key for key in ('name','base_id','object_type') if expected[code][key]!=found[code][key]]
            if fields:mismatches.append({'id':code,'fields':fields,'expected':expected[code],'found':found[code]})
        result[kind]={'file_count':len(expected),'runtime_count':len(found),'missing':sorted(expected.keys()-found.keys()),'extra':sorted(found.keys()-expected.keys()),'mismatches':mismatches}
    report['snapshots'].append(result)
report['source_unchanged']=(before==args.campaign.stat().st_mtime_ns and info.sha256==hashlib.sha256(args.campaign.read_bytes()).hexdigest())
report['ok']=report['source_unchanged'] and all(not v['missing'] and not v['extra'] and not v['mismatches'] for s in report['snapshots'] for v in s.values())
args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(report,ensure_ascii=False,indent=2))
raise SystemExit(0 if report['ok'] else 1)
