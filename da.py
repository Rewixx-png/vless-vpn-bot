import os
import argparse
import re
from pathlib import Path

DEFAULT_MAX_CHUNK_SIZE = 800 * 1024
OUTPUT_DIR = "project_chunks"

IGNORE_DIRS = {
    '.git', '.idea', '.vscode', '.github', 
    '__pycache__', 'node_modules', 'venv', 'env', 
    'build', 'dist', 'bin', 'obj', 'target',
    'project_chunks', 'migrations', 'coverage',
    '.pytest_cache', '.mypy_cache', 'Session',
    'logs', 'storage', 'uploads', 'assets', 'static'
}

IGNORE_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.ico', '.svg', '.webp', '.bmp', '.tiff', '.psd',
    '.exe', '.dll', '.so', '.dylib', '.class', '.o', '.a', '.lib',
    '.zip', '.tar', '.gz', '.7z', '.rar', '.jar', '.war',
    '.pdf', '.docx', '.xlsx', '.pptx', '.db', '.sqlite', '.sqlite3',
    '.pyc', '.pyo', '.pyd',
    'package-lock.json', 'yarn.lock', 'poetry.lock', 'Cargo.lock',
    '.session', '.session-journal',
    '.ttf', '.otf', '.woff', '.woff2', '.eot',
    '.map', '.min.js', '.min.css'
}

EXT_TO_LANG = {
    '.py': 'python', '.js': 'javascript', '.ts': 'typescript',
    '.html': 'html', '.css': 'css', '.json': 'json',
    '.md': 'markdown', '.yml': 'yaml', '.yaml': 'yaml',
    '.sh': 'bash', '.bash': 'bash', '.sql': 'sql',
    '.go': 'go', '.rs': 'rust', '.c': 'c', '.cpp': 'cpp',
    '.h': 'c', '.hpp': 'cpp', '.java': 'java', '.kt': 'kotlin'
}

def get_language(extension):
    return EXT_TO_LANG.get(extension.lower(), '')

def is_text_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            f.read(1024)
            return True
    except (UnicodeDecodeError, PermissionError, OSError):
        return False

def clean_content(text):
    return re.sub(r'\n\s*\n', '\n\n', text).strip()

def format_size(size):
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"

def generate_tree(source_path):
    tree_lines = ["### Project Structure\n```text"]
    source_path = Path(source_path)
    
    for root, dirs, files in os.walk(source_path):
        dirs[:] = sorted([d for d in dirs if d not in IGNORE_DIRS])
        files = sorted([f for f in files if Path(f).suffix.lower() not in IGNORE_EXTENSIONS])
        
        level = root.replace(str(source_path), '').count(os.sep)
        indent = '  ' * level
        
        current_dir_name = os.path.basename(root)
        if root == str(source_path):
            current_dir_name = "."
            
        tree_lines.append(f"{indent}{current_dir_name}/")
        
        subindent = '  ' * (level + 1)
        for f in files:
            f_path = os.path.join(root, f)
            if not os.path.isfile(f_path):
                continue
            try:
                size = os.path.getsize(f_path)
                size_str = format_size(size)
                tree_lines.append(f"{subindent}{f} ({size_str})")
            except OSError:
                tree_lines.append(f"{subindent}{f}")
            
    tree_lines.append("```\n")
    return "\n".join(tree_lines)

def get_chunk_header(chunk_number):
    return (
        f"This is chunk {chunk_number} of a codebase export.\n"
        "Please analyze the following files and maintain context.\n\n"
    )

def save_chunk(chunk_data, chunk_number, output_folder):
    if not chunk_data:
        return

    filename = os.path.join(output_folder, f"project_part_{chunk_number}.txt")
    content = "".join(chunk_data)
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
        
    size_kb = os.path.getsize(filename) / 1024
    print(f"📦 [Chunk {chunk_number}] Saved: {filename} ({size_kb:.2f} KB)")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default=".")
    parser.add_argument("--out", default=OUTPUT_DIR)
    parser.add_argument("--size", type=int, default=DEFAULT_MAX_CHUNK_SIZE)
    args = parser.parse_args()

    source_path = Path(args.source).resolve()
    output_path = Path(args.out)

    if not output_path.exists():
        os.makedirs(output_path)
    else:
        for f in output_path.glob("project_part_*.txt"):
            os.remove(f)

    print(f"🚀 Start: {source_path}")
    
    chunk_counter = 1
    project_tree = generate_tree(source_path)
    
    initial_header = get_chunk_header(chunk_counter)
    current_chunk = [initial_header, project_tree]
    current_size = len("".join(current_chunk).encode('utf-8'))

    script_name = os.path.basename(__file__)

    for root, dirs, files in os.walk(source_path):
        dirs[:] = sorted([d for d in dirs if d not in IGNORE_DIRS and d != args.out])
        files.sort()

        for file in files:
            file_path = Path(root) / file
            
            if file == script_name:
                continue

            if not file_path.is_file():
                continue

            if file_path.suffix.lower() in IGNORE_EXTENSIONS:
                continue

            if not is_text_file(file_path):
                continue

            try:
                relative_path = file_path.relative_to(source_path).as_posix()
                lang = get_language(file_path.suffix)
                
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    raw_content = f.read()

                cleaned_content = clean_content(raw_content)
                
                md_entry = (
                    f'### File: {relative_path}\n'
                    f'```{lang}\n'
                    f'{cleaned_content}\n'
                    f'```\n\n'
                )

                entry_size = len(md_entry.encode('utf-8'))

                if current_size + entry_size > args.size:
                    if len(current_chunk) > 1:
                        save_chunk(current_chunk, chunk_counter, output_path)
                        chunk_counter += 1
                        new_header = get_chunk_header(chunk_counter)
                        current_chunk = [new_header]
                        current_size = len(new_header.encode('utf-8'))

                current_chunk.append(md_entry)
                current_size += entry_size

            except Exception as e:
                print(f"⚠️ Error {file}: {e}")

    if len(current_chunk) > 1 or (len(current_chunk) == 1 and chunk_counter == 1):
        save_chunk(current_chunk, chunk_counter, output_path)

    print(f"\n✅ Done! Path: {output_path.absolute()}")

if __name__ == "__main__":
    main()
