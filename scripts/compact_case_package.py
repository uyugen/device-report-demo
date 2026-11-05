"""Convert an existing accepted 1.1 ZIP; preserve CSV bytes and validate output."""
import argparse
import io
import json
import sys
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.case_data import parse_zip, check_snapshot
from app.input_format import compact_legacy
from app.real_data import members


def convert(raw):
    snapshot = parse_zip(raw)
    check_snapshot(snapshot)
    data = members(raw)
    c = compact_legacy(json.loads(data['case.json'].decode('utf-8-sig')))
    out = io.BytesIO()
    with ZipFile(out, 'w', ZIP_DEFLATED) as z:
        z.writestr('case.json', json.dumps(c, ensure_ascii=False, indent=2))
        for d in c['datasets']:
            z.writestr(d['data_file'], data[d['data_file']])
    result = out.getvalue()
    check_snapshot(parse_zip(result))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve() or args.output.exists():
        parser.error('输出须为新的ZIP路径，不覆盖已有文件')
    args.output.write_bytes(convert(args.source.read_bytes()))
    print('已生成1.2版输入包；CSV原值和字节未改变。')
