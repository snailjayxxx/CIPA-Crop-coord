"""FindsBlur standalone experimental tester. NO reference loading in analysis.

The algorithm entrypoint `_analyze_without_oracle` never accepts or reads
reference TXT. The `compare` operation pairs its independent result records
with the user's official TXT afterward, solely for an explicit audit table.
"""
from __future__ import annotations
import argparse
import csv
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import json
import os
import sys
from time import perf_counter
from zipfile import ZipFile
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from phase11.replay_407170_4077eb import replay_from_image
from phase12.whole_image_until_flags import analyze_to_flags
from phase12.recovered_measurement_region_402b90 import mark_measurement_402b90
from phase12.recovered_final_width_403e30 import measure_403e30
from phase12.trace_scanlines_403e30 import trace_scanlines_403e30

CODE_BLOCKER='BLOCKED_MEASUREMENT_REGION_UNRESOLVED'


def _images(path:Path):
    if path.is_file() and path.suffix.lower() in ('.jpg','.jpeg','.bmp'):
        return [path]
    if not path.is_dir(): raise ValueError(f'Image path missing: {path}')
    images=[p for p in path.rglob('*') if p.is_file() and p.suffix.lower() in ('.jpg','.jpeg','.bmp')]
    return sorted(images,key=lambda p:(p.name.lower(),str(p)))


def _parse_reference(path:Path):
    # Strictly comparison-side only, never called by `_analyze_without_oracle`.
    entries={}
    # BOM, Japanese Windows locales and conventional ASCII compatible.
    raw=path.read_bytes()
    for codec in ('utf-8-sig','cp932'):
        try:text=raw.decode(codec);break
        except UnicodeDecodeError:continue
    else:raise UnicodeError(f'Unsupported reference TXT encoding: {path}')
    for lineno,line in enumerate(text.splitlines(),1):
        part=line.strip().split()
        if not part:continue
        if len(part)!=5:
            raise ValueError(f'Invalid reference TXT line {lineno}: expected name + 4 floats')
        name=Path(part[0].replace('\\','/')).name
        if name in entries:raise ValueError(f'Duplicate reference image: {name}')
        entries[name]=tuple(float(v) for v in part[1:])
    return entries


def _analyze_without_oracle(path:Path, mode:str,diag:Path|None):
    """Important: no oracle/reference argument and no oracle import."""
    started=perf_counter()
    row={'file':path.name,'source_sha256':sha256(path.read_bytes()).hexdigest(),
        'width':None,'height':None,'stage':'start','status':'unprocessed',
        'candidate_values':None,'elapsed_seconds':0.0,'details':{}}
    try:
        if mode=='threshold':
            v=replay_from_image(path,halt_after='threshold',diagnostics_directory=diag)
            row.update(width=v.width,height=v.height,stage='threshold',
                       status='PARTIAL_PREPROCESSING_ONLY',
                       details={'normalization':v.stats.get('normalization'),'timings':v.timings,
                                'threshold_nonzero':v.stats.get('10-threshold-C0-405750',{}).get('nonzero_in_roi')})
        else:
            v=analyze_to_flags(path,diagnostics_directory=diag)
            row.update(width=v.width,height=v.height,stage=v.stage,
                       status=CODE_BLOCKER if v.status=='partial' else 'FAILED_EXTENT_DETECTION',
                       details=v.metadata|{'preprocess_timings':v.preprocessing.timings})
            if mode=='calculate' and v.flags is not None:
                p=v.preprocessing.parameters
                rr=v.preprocessing.processed
                # Native 0x407911..0x407914: EDI++, EBP--, EBX++, ECX--.
                # The actual measurement uses this inset rectangle, NOT the
                # original preprocessing ROI. No reference data is read.
                inset=(rr.x0+1,rr.y0+1,rr.x1-1,rr.y1-1)
                selected=mark_measurement_402b90(v.flags,width=v.width,height=v.height,
                    processing_roi=inset,scan_roi=inset,ring_start=p.ring_start,
                    ring_width=p.ring_width,histogram_radius=p.field_0x844,
                    x_margin=p.x_margin,y_margin=p.y_margin,
                    nearby_distance=p.field_0x898)
                row['details']['native_normal_branch_402b90']={
                   'success':selected.success,'reason':selected.reason,
                   'candidate_lists':[len(selected.x_candidates),len(selected.y_candidates)],
                   'intersected_junctions':len(selected.intersections),
                   'junction_coordinates_xy':selected.intersections,
                   'measurement_rectangle':selected.region.outer if selected.region else None,
                   'inset_roi_xyxy':inset,'mode_decision':'normal branch selected for evaluation; original 0x408290 caller still requires validation'
                }
                if selected.success:
                    measurements=measure_403e30(selected.flags,width=v.width,height=v.height,
                        roi=inset,max_width=p.field_0x848,scale=p.final_scale,
                        save_debug=diag is not None)
                    row.update(stage='measurement-403e30',
                         status='COMPUTED_NUMERIC__NATIVE_JPEG_PARITY_UNVERIFIED',
                         candidate_values=list(measurements.values))
                    row['details']['width_scans']={
                        'line_counts':[measurements.x_row_valid_count,measurements.y_col_valid_count],
                        'line_sums':[measurements.x_line_rounded_sum,measurements.y_line_rounded_sum],
                        'sample_counts':[measurements.x_raw_samples,measurements.y_raw_samples],
                        'rejected_roi_boundaries':[measurements.x_rejected_boundary,measurements.y_rejected_boundary],
                        'over_width_limit':[measurements.x_over_limit,measurements.y_over_limit]}
                    if diag is not None:
                        # Independent scalar 0x403E30 scanline reconstruction.
                        # Does not take or read any official reference numbers.
                        trace=trace_scanlines_403e30(
                            selected.flags,width=v.width,height=v.height,
                            roi=inset,max_width=p.field_0x848,scale=p.final_scale)
                        diag.mkdir(parents=True,exist_ok=True)
                        (diag/'21-scanlines-403e30.json').write_text(
                            json.dumps(trace,ensure_ascii=False,indent=2),encoding='utf-8')
                        row['details']['scanline_trace']={
                            'scalar_and_optimized_identical':trace['scalar_and_optimized_identical'],
                            'horizontal_line_sum':trace['axes'][0]['total_rounded_width'],
                            'vertical_line_sum':trace['axes'][1]['total_rounded_width'],
                            'artifact':'21-scanlines-403e30.json'}
                        from PIL import Image
                        diag.mkdir(parents=True,exist_ok=True)
                        Image.frombytes('L',(v.width,v.height),selected.flags).save(diag/'19-measurement-flags-402b90.png')
                        if measurements.debug_width_image:
                            Image.frombytes('L',(v.width,v.height),measurements.debug_width_image).save(diag/'20-widths-403e30.png')
                else:
                    row.update(stage='measurement-402b90',status=CODE_BLOCKER)
                    if diag is not None:
                        # Even a failed image retains its selection-stage flags
                        # and reason, so CalcDebug can reveal the first failure.
                        from PIL import Image
                        diag.mkdir(parents=True,exist_ok=True)
                        Image.frombytes('L',(v.width,v.height),selected.flags).save(
                            diag/'19-selection-failed-flags-402b90.png',format='PNG')
                        (diag/'19-selection-failure.json').write_text(
                            json.dumps({'reason':selected.reason,
                                        'x_candidate_count':len(selected.x_candidates),
                                        'y_candidate_count':len(selected.y_candidates),
                                        'intersection_count':len(selected.intersections),
                                        'processed_roi':inset},ensure_ascii=False,indent=2),encoding='utf-8')
    except Exception as exc:
        row.update(status='FAILED_PIPELINE',details={'exception_type':type(exc).__name__,'message':str(exc)})
    row['elapsed_seconds']=round(perf_counter()-started,3)
    return row


def _csv_comparisons(results,reference:dict):
    header=['file','stage','status','elapsed_seconds',
            'official_1','official_2','official_3','official_4',
            'candidate_1','candidate_2','candidate_3','candidate_4',
            'delta_1','delta_2','delta_3','delta_4','difference_state','width','height','sha256']
    rows=[]
    for item in results:
        expected=reference.get(item['file']); actual=item.get('candidate_values')
        delta=[a-b for a,b in zip(actual,expected)] if (actual is not None and expected is not None) else None
        row={'file':item['file'],'stage':item['stage'],'status':item['status'],
             'elapsed_seconds':item['elapsed_seconds'],'difference_state':('PASS_6DP' if (actual is not None and expected is not None and all(f'{a:.6f}'==f'{b:.6f}' for a,b in zip(actual,expected))) else 'FAIL_6DP' if delta is not None else 'NO_REFERENCE' if actual is not None else 'NOT_COMPUTABLE__NO_CANDIDATE_VALUE'),'width':item['width'],
             'height':item['height'],'sha256':item['source_sha256']}
        for i in range(4):
            row[f'official_{i+1}']=f'{expected[i]:.6f}' if expected else ''
            row[f'candidate_{i+1}']=f'{actual[i]:.6f}' if actual else ''
            row[f'delta_{i+1}']=f'{delta[i]:+.6f}' if delta else ''
        rows.append(row)
    return header,rows


def run(args):
    source=Path(args.input).resolve()
    out=Path(args.output).resolve()
    if out.exists() and not args.resume:
        raise ValueError(f'Output directory already exists; use --resume only for matching partial run: {out}')
    references={}
    if args.reference:
        references=_parse_reference(Path(args.reference))
    out.mkdir(parents=True,exist_ok=args.resume)
    progress_path=out/'progress.jsonl'
    # Reuse completed calculations only when the algorithm source is identical.
    # Image SHA-256 checks alone are insufficient after a code change.
    # Invalidate old checkpoints whenever ANY imported instruction-reconstruction
    # module changes, not just the newest measurement modules. The legacy
    # pipeline also uses stages from phase3/4/5/6/7/8/9/10 transitively.
    algorithm_roots=('phase1','phase3','phase4','phase5','phase6','phase7',
                     'phase8','phase9','phase10','phase11','phase12','phase13',
                     'standalone')
    engine_paths=tuple(sorted(
        p.relative_to(ROOT).as_posix()
        for directory in algorithm_roots
        for p in (ROOT/directory).rglob('*.py')
        if p.is_file() and not p.name.startswith('test_')
        and '__pycache__' not in p.parts
    ))
    algorithm_hash=sha256()
    for rel in engine_paths:
        algorithm_hash.update(rel.encode('utf-8'))
        algorithm_hash.update((ROOT/rel).read_bytes())
    algorithm_sha256=algorithm_hash.hexdigest()
    resumed={}
    if args.resume:
        config_path=out/'input_config.json'
        if not config_path.is_file():
            raise ValueError(f'Cannot resume: missing input_config.json under {out}')
        cfg=json.loads(config_path.read_text(encoding='utf-8'))
        if cfg.get('engine_sha256')!=algorithm_sha256:
            raise ValueError('Cannot resume: source algorithm has changed since saved results; preserve old run and start a NEW output directory')
        if cfg.get('input')!=str(source) or cfg.get('mode')!=args.mode or cfg.get('reference')!=(str(Path(args.reference).resolve()) if args.reference else None):
            raise ValueError('Resume input, mode, or reference differs from original run')
        if progress_path.is_file():
            for line in progress_path.read_text(encoding='utf-8').splitlines():
                if not line.strip():continue
                item=json.loads(line)
                resumed[item['file']]=item
    else:
        (out/'input_config.json').write_text(json.dumps({'input':str(source),'mode':args.mode,'reference':str(Path(args.reference).resolve()) if args.reference else None,'engine_sha256':algorithm_sha256},ensure_ascii=False,indent=2),encoding='utf-8')
    manifest={'program':'FindsBlur standalone EXE-reconstruction experimental',
              'mode':args.mode,'generated_at':datetime.now(timezone.utc).isoformat(),
              'reference_used_for_algorithm':False,
              'reference_used_for_audit_only':bool(args.reference),
              'native_full_output_validated':False,
              'phase14_integration_executed':False,
              'engine_sha256':algorithm_sha256,
              'source_input':str(source),
              'note':'Native route 402B90+403E30 produces independent numeric measurements; native IJG8c decoder and exact Windows runtime parity remain unverified.'}
    results=[]
    with TemporaryDirectory(prefix='findsblur-private-input-') as temporary:
        if source.is_file() and source.suffix.lower()=='.zip':
            with ZipFile(source) as z:
                seen=set()
                for entry in z.infolist():
                    if not entry.filename.lower().endswith(('.jpg','.jpeg','.bmp')):continue
                    name=Path(entry.filename)
                    # Avoid zip-slip, only basename needed as official result lookup key.
                    if name.name!=entry.filename.split('/')[-1] or not name.name:continue
                    if entry.file_size > 100_000_000:
                        raise ValueError(f'Unsafe oversized ZIP image: {name.name}')
                    if name.name.lower() in seen:
                        raise ValueError(f'Duplicate filename inside image ZIP: {name.name}')
                    seen.add(name.name.lower())
                    (Path(temporary)/name.name).write_bytes(z.read(entry))
            images=_images(Path(temporary))
        else: images=_images(source)
        if args.max_images:images=images[:args.max_images]
        for i,img in enumerate(images,1):
            if img.name in resumed:
                item=resumed[img.name]
                # A resumed result is valid only for the exact original image bytes.
                if item.get('source_sha256')!=sha256(img.read_bytes()).hexdigest():
                    raise ValueError(f'Input changed since previous partial run: {img.name}')
                results.append(item)
                print(f'{i}/{len(images)} {img.name}: RESUMED {item["status"]}',flush=True)
                continue
            diag=(out/'diagnostics'/img.stem) if (args.diagnostics or args.trace_scanlines) else None
            item=_analyze_without_oracle(img,args.mode,diag)
            results.append(item)
            # A killed/timeout process must not lose all previously computed
            # numeric results: one append-only JSON record per completed image.
            with progress_path.open('a',encoding='utf-8') as stream:
                stream.write(json.dumps(item,ensure_ascii=False)+'\n')
                stream.flush()
                os.fsync(stream.fileno())
            print(f'{i}/{len(images)} {img.name}: {item["stage"]} / {item["status"]} ({item["elapsed_seconds"]:.2f}s)',flush=True)
    if references:
        missing=sorted(set(references)-{r['file'] for r in results})
        manifest['reference_count']=len(references)
        manifest['processed_count_with_reference']=sum(r['file'] in references for r in results)
        manifest['reference_without_processed_image']=missing
    manifest['processed_count']=len(results)
    manifest['official_numeric_parity_count']=sum(r['candidate_values'] is not None and r['file'] in references and
        all(f'{a:.6f}'==f'{b:.6f}' for a,b in zip(r['candidate_values'],references[r['file']])) for r in results)
    manifest['candidate_numeric_values_produced']=sum(r['candidate_values'] is not None for r in results)
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    header,rows=_csv_comparisons(results,references)
    with (out/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=header);writer.writeheader();writer.writerows(rows)
    print(f'Output: {out} | Images: {len(results)} | Final numeric results: {manifest["candidate_numeric_values_produced"]}')
    if not results or any(r['candidate_values'] is None for r in results):return 4
    # A reference-only run with no matching filenames is NOT a successful audit.
    # An unmatched processed image also retains NO_REFERENCE and fails coverage.
    if references and (manifest['processed_count_with_reference'] != len(results)
                       or manifest['official_numeric_parity_count'] != len(results)):
        return 1
    return 0


def main(argv=None):
    parser=argparse.ArgumentParser(description='Standalone original-EXE-based FindsBlur numeric calculator; official full parity still under verification.')
    parser.add_argument('input',help='A JPEG/BMP, image directory, or ZIP containing JPEG/BMP files')
    parser.add_argument('--output',required=True,help='A NEW output directory (refuses overwrite)')
    parser.add_argument('--reference',help='Official TXT only for comparison (never calculation)')
    parser.add_argument('--mode',choices=('calculate','threshold','flags'),default='calculate',help='calculate produces independent four numeric values; threshold/flags are diagnostic partial modes')
    parser.add_argument('--diagnostics',action='store_true',help='Export processing-stage PNGs (locally only)')
    parser.add_argument('--trace-scanlines',action='store_true',help='Save independent per-scanline 0x403E30 trace JSON and local diagnostic PNGs')
    parser.add_argument('--max-images',type=int,default=0)
    parser.add_argument('--resume',action='store_true',help='Resume a matching partial run from its append-only progress.jsonl')
    args=parser.parse_args(argv)
    try:return run(args)
    except Exception as e:
        print(f'ERROR: {type(e).__name__}: {e}',file=sys.stderr)
        return 2

if __name__=='__main__':raise SystemExit(main())
