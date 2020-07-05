import os
import sys

log, src, dst = sys.argv[1:]
with open(log, 'a') as lh:
    os.rename(src, dst)
    print(f'{src} {dst}', file=lh)
