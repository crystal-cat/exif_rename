import json
import sys

with open(sys.argv[1], 'r') as fh:
    report = json.load(fh)

print('## Nox\n')
for session in report['sessions']:
    result = session['result']
    if result == 'success':
        mark = 'heavy_check_mark'
    elif result == 'skipped':
        mark = 'large_blue_circle'
    else:
        mark = 'heavy_multiplication_x'
    print(f'* {session["name"]}: {result} :{mark}:')
