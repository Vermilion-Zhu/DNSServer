import os
import json
import random

def gen_from_csv(filepath:str=None, l:int=10**3, maximum:int=10**5):
    """Use the Tranco list* [1] generated on 06 June 2026 to produce a list of casual domains.
    * Available at https://tranco-list.eu/list/WVV59."""
    filename = os.listdir(filepath)
    for name in filename:
        if name.endswith('.csv'):
            print(f'Generating a list of casual domains from {name}...')
            with open(name) as f:
                content = f.readlines()[:max(l,maximum)]
                random.shuffle(content)
                domainlist = [d.split(',')[-1].rstrip('\n') for d in content[:l]]
                data = {"domains": domainlist}
            with open(f'{name.rstrip('.csv')}_{l}.json','w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

def gen_malicious(l:int=10**3, lower:int=7, upper:int=15, evenly:bool=True):
    """Generate a json file consists of random malicious domains to stimulate DNS attacks.
    If evenly == True, the domain names follow a uniform distribution of English characters. 
    Else follow the weighted one that is closer to reality"""
    
    ALPHABET = 'abcdefghijklmnopqrstuvwxyz' if evenly \
        else 'eeeeeeeeeeeeetttttttttaaaaaaaaoooooooiiiiiiinnnnnnnsssssshhhhhhrrrrrrddddllllcccuuummwwffggyyppbvkjxqz'
    SUFFICES = ['.com', '.org', '.net', '.info', '.xyz', '.top', '.gov', '.edu', '.shop', '.live']
    domainlist = []
    print('Generating random malicious domains...')
    for _ in range(l):
        length = random.randint(lower,upper)
        pos = [random.randint(0,len(ALPHABET)-1) for i in range(length)]
        name = ''.join([ALPHABET[p] for p in pos]) + SUFFICES[random.randint(0,len(SUFFICES)-1)]
        domainlist.append(name)
    data = {"domains": domainlist}
    with open(f'malicious_e_{l}.json' if evenly else f'malicious_u_{l}.json','w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

if __name__ == '__main__':
    #gen_from_csv()
    gen_malicious(500)
    print('Generation completed.')