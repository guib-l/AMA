import os
import sys
import time

def progressbar(it, prefix="", size=80, out=sys.stdout): 
    count = len(it)
    def show(j):
        x = int(size*j/count)
        print("{}[{}{}] {}/{}".format(prefix, u'█'*x, "."*(size-x), j, count), 
                end='\r', file=out, flush=True)
    show(0)
    for i, item in enumerate(it):
        yield item
        show(i+1)
    print("\n", flush=True, file=out)



def updateIter(out=sys.stdout):
    i = 0
    def show(n):
        nonlocal i
        msg = f" > Loading {n}"
        print(msg.ljust(40), end="\r", file=out, flush=True)
        i += 1
    return show










