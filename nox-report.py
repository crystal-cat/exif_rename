import json
import sys

with open(sys.argv[1], 'r') as fh:
    report = json.load(fh)

print('## Nox\n')
for session in report['sessions']:
    # looks weird, but is literally how Nox creates a "friendly name"
    # for a session
    name = session['signatures'][0] \
        if session['signatures'] else session['name']

    result = session['result']
    if result == 'success':
        mark = 'heavy_check_mark'
    elif result == 'skipped':
        mark = 'large_blue_circle'
    else:
        mark = 'heavy_multiplication_x'

    print(f'* {name}: {result} :{mark}:')
