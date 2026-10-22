"""Live HTTP acceptance check. Writes synthetic reports only; does not change knowledge/rules."""
import json
import sys
import time
from pathlib import Path
import httpx

ROOT=Path(__file__).resolve().parents[1]


def verify():
    results=[]
    with httpx.Client(base_url='http://127.0.0.1:8046',timeout=30) as client:
        count=len(client.get('/api/knowledge').json())
        for name in ['stable','rising','impulse','missing']:
            raw=(ROOT/'samples'/f'{name}.zip').read_bytes()
            r=client.post('/api/cases',files={'file':(f'{name}.zip',raw,'application/zip')});r.raise_for_status();case=r.json()
            assert not case['warnings'],case
            r=client.post('/api/reports',json={'case_id':case['case_id'],'use_llm':True});r.raise_for_status();rid=r.json()['id']
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                r=client.get('/api/reports/'+rid);r.raise_for_status();report=r.json()
                if report['status']!='running':break
                time.sleep(1)
            assert report['status']=='done',report
            assert report['writer']['context']['knowledge_count']==len(report['knowledge'])==count
            assert report['writer']['mode']=='llm',report['writer']
            for file in ['report.docx','report.pdf','evidence.json','writer_input.json']:
                r=client.get(f'/api/reports/{rid}/files/{file}');r.raise_for_status();assert len(r.content)>100
            inp=client.get(f'/api/reports/{rid}/files/writer_input.json').json()
            assert len(inp['knowledge'])==count
            for key in ['device','uploaded_current_features','recomputed_features','history_features','trend_statistics','spectrum_peaks','decision','missing']:
                assert key in inp['facts']
            if name=='missing':
                assert report['analysis']['features']['velocity_rms'] is not None
                assert not report['analysis']['peaks'] and not report['analysis']['rpm_available']
            item={'sample':name,'id':rid,'writer':report['writer']['mode'],'knowledge_count':len(report['knowledge']),
                  'kurtosis':report['analysis']['features']['kurtosis'],'citations':report['text']['citations'],
                  'warnings':report['analysis']['warnings'],'pdf':report['pdf']['available']}
            results.append(item);print(json.dumps(item,ensure_ascii=False),flush=True)
    dest=ROOT/'workspace/qa/upload_validation.json';dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(results,ensure_ascii=False,indent=2));return results


if __name__=='__main__':verify()
