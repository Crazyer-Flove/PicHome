"""Public network probes only: never loads application settings or credentials."""
import ssl
import urllib.request
from urllib.parse import urlsplit

def run_checks():
    results = []
    for url in ('https://api.github.com/repos/Crazyer-Flove/PicHome',
                'https://raw.githubusercontent.com/Crazyer-Flove/PicHome/main/README.md'):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'Luma-Public-Diagnostics'})
            with urllib.request.urlopen(request, timeout=15) as result:
                results.append({'url': url, 'status': result.status})
        except Exception as error:
            results.append({'url': url, 'error': type(error).__name__})
    return results

if __name__ == '__main__':
    import json
    print(json.dumps(run_checks(), indent=2))
