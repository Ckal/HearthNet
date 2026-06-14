#!/usr/bin/env python3
"""Fix UTF-8 curly quotes in node.py"""

with open('hearthnet/node.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Replace curly quotes with regular quotes
content = content.replace('\u201c', '"')   # Left double quote
content = content.replace('\u201d', '"')   # Right double quote  
content = content.replace('\u2019', "'")   # Right single quote
content = content.replace('\u2018', "'")   # Left single quote
content = content.replace('\u2013', '-')   # En dash
content = content.replace('\u2014', '-')   # Em dash

# Write back
with open('hearthnet/node.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed all curly quotes in node.py')
