import re

with open('app/api/v1/device.py', 'r') as f:
    content = f.read()

# Read the file and print relevant sections
print(content[:500])