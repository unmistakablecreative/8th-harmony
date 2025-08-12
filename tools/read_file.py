import json
import os
import argparse
import pdfplumber


def read_file(params):
    import os
    import pdfplumber

    filename = params.get('filename')
    offset = int(params.get('offset', 0))
    max_chars = int(params.get('max_chars', 10000))
    full_stream = params.get('full_stream', False)

    if not filename:
        return {'status': 'error', 'message': "❌ 'filename' param is required."}

    def _safe_extract(path):
        try:
            with pdfplumber.open(path) as pdf:
                return '\n'.join(page.extract_text() or '' for page in pdf.pages)
        except Exception as e:
            return f'❌ PDF read error: {str(e)}'

    def _resolve_path(name):
        if os.path.isfile(name):
            return name
        name = os.path.basename(name)
        search_dirs = [
            '/Users/srinivas/Orchestrate Github/orchestrate-jarvis/data',
            '/Users/srinivas/Orchestrate Github/orchestrate-jarvis/tools',
            '/app/code_blueprints',
            '/app/compositions',
            '/Users/srinivas/Orchestrate Github/orchestrate-jarvis/ebooks_guides_manuals',
            '/Users/srinivas/Orchestrate Github/orchestrate-jarvis/finance',
            '/Users/srinivas/Orchestrate Github/orchestrate-jarvis/compiled_weekly',
            '/Users/srinivas/Orchestrate Github/orchestrate-jarvis/podcast_transcripts'  # Added new directory
        ]
        for directory in search_dirs:
            path = os.path.join(directory, name)
            if os.path.exists(path):
                return path
        return None

    path = _resolve_path(filename)
    if not path:
        return {'status': 'error', 'message': '❌ File not found in known directories or direct path.'}

    try:
        if filename.lower().endswith('.pdf'):
            content = _safe_extract(path)
        else:
            with open(path, 'r', encoding='utf-8') as file:
                content = file.read()

        total_len = len(content)

        if full_stream:
            end = min(offset + max_chars, total_len)
            chunk = content[offset:end]
            return {
                'status': 'partial_response',
                'mode': 'stream',
                'chunk': {
                    'offset': offset,
                    'length': len(chunk),
                    'data': chunk
                },
                'total_length': total_len,
                'next_offset': end if end < total_len else None
            }

        # fallback if stream not requested
        return {'status': 'success', 'data': content, 'length': total_len}

    except Exception as e:
        return {'status': 'error', 'message': f'❌ Failed to read file: {str(e)}'}





def main():
    parser = argparse.ArgumentParser(description='Orchestrate Tool Template')
    parser.add_argument('action', help='Action to perform')
    parser.add_argument('--params', type=str, required=False, help=
        'JSON-encoded parameters for the action')
    args = parser.parse_args()
    try:
        params = json.loads(args.params) if args.params else {}
    except json.JSONDecodeError:
        print(json.dumps({'status': 'error', 'message':
            '❌ Invalid JSON format.'}, indent=4))
        return
    if args.action == 'read_file':
        result = read_file(params)
    else:
        result = {'status': 'error', 'message':
            f'❌ Unknown action: {args.action}'}
    print(json.dumps(result, indent=4))


if __name__ == '__main__':
    main()
