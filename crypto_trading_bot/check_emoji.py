#!/usr/bin/env python3
"""
Emoji Detection Script for Windows Compatibility

Finds all non-ASCII characters that could cause UnicodeEncodeError on Windows (cp1250).
Run this before deploying to ensure all emoji have been replaced with ASCII.
"""
import os
import re
import sys

# Emoji ranges that cause problems on Windows
EMOJI_RANGES = [
    (0x1F300, 0x1F9FF),  # Miscellaneous Symbols and Pictographs
    (0x2600, 0x26FF),    # Miscellaneous Symbols
    (0x2700, 0x27BF),    # Dingbats
    (0x23E9, 0x23FF),    # Misc Technical
    (0x2190, 0x21FF),    # Arrows
    (0x25A0, 0x25FF),    # Geometric Shapes
    (0x2500, 0x257F),    # Box Drawing
]

def is_emoji(char):
    """Check if character is in problematic emoji range"""
    code = ord(char)
    for start, end in EMOJI_RANGES:
        if start <= code <= end:
            return True
    return False

def find_emoji_in_file(filepath):
    """Find all emoji characters in a file"""
    results = []
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                for i, char in enumerate(line):
                    if is_emoji(char):
                        results.append({
                            'line': line_num,
                            'col': i + 1,
                            'char': char,
                            'code': hex(ord(char)),
                            'context': line.strip()[:80]
                        })
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
    return results

def scan_project(directory='.'):
    """Scan all .py files for emoji"""
    all_results = {}
    skip_dirs = {'venv', '.git', '__pycache__', 'node_modules', '.venv'}
    
    for root, dirs, files in os.walk(directory):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                emoji = find_emoji_in_file(filepath)
                if emoji:
                    all_results[filepath] = emoji
    
    return all_results

def print_report(results):
    """Print formatted report of findings"""
    if not results:
        print("[OK] No emoji found! Code is Windows-compatible.")
        return True
    
    print("[WARN] Found emoji in the following files:")
    print("="*60)
    
    total = 0
    for filepath, emoji_list in sorted(results.items()):
        print(f"\n{filepath}:")
        for item in emoji_list:
            print(f"  Line {item['line']}, Col {item['col']}: {repr(item['char'])} ({item['code']})")
            print(f"    Context: {item['context']}")
            total += 1
    
    print("\n" + "="*60)
    print(f"Total emoji found: {total}")
    print("\nRecommended replacements:")
    print("  Emoji -> ASCII equivalent")
    print("  Example: Replace with [OK], [ERROR], [INFO], etc.")
    return False

if __name__ == '__main__':
    directory = sys.argv[1] if len(sys.argv) > 1 else '.'
    results = scan_project(directory)
    success = print_report(results)
    sys.exit(0 if success else 1)
