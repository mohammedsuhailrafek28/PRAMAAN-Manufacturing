"""Read-only QA of test-exported PDFs; test tooling only, no production PDF dependency."""
import argparse
import hashlib
import json
from pathlib import Path
from pypdf import PdfReader


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path, nargs='?', default=Path('.local/unified-validation'))
    parser.add_argument('--render', action='store_true', help='Read and rasterize with PyMuPDF for visual inspection')
    args = parser.parse_args()
    result = {}
    for name, motors in [('manufacturing', 9), ('five', 5), ('prefix', 9)]:
        path = args.directory / (name + '.pdf')
        reader = PdfReader(path, strict=True)
        assert not reader.is_encrypted and len(reader.pages) > 0
        text = '\n'.join(page.extract_text() or '' for page in reader.pages)
        normalized = ' '.join(text.split())
        assert f'{motors}-motor synthetic ledger demonstration' in normalized
        assert 'five-motor' not in normalized
        assert 'Daily Operations Report' in normalized
        assert 'Source event time' in normalized
        assert ('NOT CURRENT' in normalized) == (name == 'prefix')
        if name == 'prefix':
            assert 'Findings, actions, holds and decision changes are withheld' in normalized
        for page in reader.pages:
            assert abs(float(page.mediabox.width)-595.28) < .1
            assert abs(float(page.mediabox.height)-841.89) < .1
        args.directory.joinpath(name+'.txt').write_text(text, encoding='utf-8')
        result[name] = dict(pages=len(reader.pages), bytes=path.stat().st_size,
                            sha256=hashlib.sha256(path.read_bytes()).hexdigest(), selectableTextCharacters=len(text))
        if args.render:
            import fitz
            doc = fitz.open(path)
            out = args.directory/'pdf-render';out.mkdir(exist_ok=True)
            for i, page in enumerate(doc):
                for block in page.get_text('dict')['blocks']:
                    if block.get('type') != 0: continue
                    for line in block['lines']:
                        for span in line['spans']:
                            x0,y0,x1,y1 = span['bbox']
                            assert x0 >= -.5 and y0 >= -.5 and x1 <= page.rect.width+.5 and y1 <= page.rect.height+.5, (name,i,span['text'])
                page.get_pixmap(matrix=fitz.Matrix(1.25,1.25),alpha=False).save(out/f'{name}-{i+1}.png')
            doc.close()
    args.directory.joinpath('pdf-qa.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__ == '__main__': main()
